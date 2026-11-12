"""Comprehensive Security, Data Isolation, Real-Sync Enforcement & Optimization Tests.

Tuân thủ nghiêm ngặt các quy định trong AGENTS.md:
1. Telegram Auth, Webhook Secret Verification & Admin RBAC.
2. Cấm fallback plaintext 'plain::' khi thiếu hoặc sai master key Fernet.
3. Client Portal Temporal & Scope Isolation (valid_from/valid_to) & Multi-Currency Decimal Math.
4. Tách biệt Real Meta Sync khỏi Mock/Demo mode; bảo lưu dữ liệu cũ khi lỗi.
5. Tối ưu SQL aggregation và loại bỏ N+1 query.
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import pytest
from fastapi.testclient import TestClient
import httpx
from cryptography.fernet import Fernet

from app.api.v1.portal import router as portal_router
from app.api.v1.telegram_bot import router as telegram_router
from app.api.v1.unified import router as unified_router
from app.api.v1.vias import router as vias_router
from app.api.v1.inventory import encrypt_credentials
from app.connectors.meta import encrypt_meta_token
from app.connectors.telegram import TelegramBotConnector
from app.core.config import settings
from app.db import get_db
from app.main import app
from app.models.ad_account import AdAccount, AdAccountAssignment
from app.models.campaign import Campaign
from app.models.customer import Customer
from app.models.prepaid import ClientBalance
from app.models.spend import DATA_VERIFIED, SpendSnapshot
from app.models.telegram import TelegramBotConfig
from app.models.via import SyncedAdAccount, SyncedBM, ViaProfile
from app.services.task_dispatcher import (
    TASK_TYPE_CHECK_BALANCE,
    dispatch_client_message,
    match_or_create_customer,
)
from app.services.telegram_bot import TelegramBotAgent
from app.services.via_manager import (
    encrypt_via_credentials,
    headless_login_and_extract,
    sync_via_all_assets,
)
from conftest import datetime_utc, make_customer


@pytest.fixture
def client(db):
    """Client kết nối trực tiếp session db của test fixture."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ==============================================================================
# PRIORITY 1: TELEGRAM AUTH, WEBHOOK SECRET & ADMIN RBAC
# ==============================================================================

def test_telegram_config_endpoint_admin_guard(client, monkeypatch):
    """Kiểm tra chỉ admin nội bộ mới được xem hoặc ghi cấu hình bot Telegram."""
    # 1. Non-local / unauthorized access bị từ chối 403
    unauth_client = TestClient(app, base_url="http://remote.hacker.com")
    res_unauth = unauth_client.get("/api/v1/telegram/config", headers={"host": "remote.hacker.com", "origin": "http://evil.com"})
    assert res_unauth.status_code == 403

    # 2. Local admin access thành công
    res_auth = client.get("/api/v1/telegram/config")
    assert res_auth.status_code == 200
    assert "has_token" in res_auth.json()


def test_telegram_dispatch_requires_valid_chat_id_or_admin(client):
    """Bắt buộc có chat_id trong whitelist hoặc phiên admin; unwhitelisted bị từ chối."""
    # 1. Caller remote không có chat_id -> 403
    unauth_client = TestClient(app, base_url="http://external.domain.com")
    res_no_chat = unauth_client.post(
        "/api/v1/telegram/dispatch",
        json={"command": "/status", "actor": "stranger"},
        headers={"host": "external.domain.com", "origin": "http://stranger.com"},
    )
    assert res_no_chat.status_code == 403

    # 2. Caller gửi chat_id lạ không nằm trong whitelist -> 403
    res_unwhitelisted = client.post(
        "/api/v1/telegram/dispatch",
        json={"command": "/status", "chat_id": "9999999999", "actor": "unknown_user"},
    )
    assert res_unwhitelisted.status_code == 403
    assert "không có trong danh sách phân quyền" in res_unwhitelisted.json()["detail"]


def test_telegram_webhook_secret_token_verification(db, client, monkeypatch):
    """Webhook chỉ chấp nhận request có đúng X-Telegram-Bot-Api-Secret-Token."""
    secret_key = "MySuperSecretTelegramWebhookKey123"

    # Cấu hình webhook secret mã hóa vào DB
    cfg = TelegramBotConfig(
        encrypted_webhook_secret=encrypt_meta_token(secret_key),
        admin_chat_id="111222333",
        allowed_chat_ids="111222333",
    )
    db.add(cfg)
    db.commit()

    dummy_payload = {
        "update_id": 99999,
        "message": {
            "message_id": 1,
            "chat": {"id": 111222333},
            "from": {"id": 111222333, "username": "admin"},
            "text": "/status",
        },
    }

    # 1. Thiếu header secret -> 403
    res_missing = client.post("/api/v1/telegram/webhook", json=dummy_payload)
    assert res_missing.status_code == 403

    # 2. Sai header secret -> 403
    res_wrong = client.post(
        "/api/v1/telegram/webhook",
        json=dummy_payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "WrongSecretToken"},
    )
    assert res_wrong.status_code == 403

    # 3. Đúng header secret -> 200 OK
    res_ok = client.post(
        "/api/v1/telegram/webhook",
        json=dummy_payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": secret_key},
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "ok"


def test_non_admin_rejected_on_set_bm_command(db):
    """Client thường dù trong whitelist cũng không được thực thi lệnh admin /set_bm."""
    admin_chat_id = "888888"
    client_chat_id = "777777"

    connector = TelegramBotConnector(
        admin_chat_id=admin_chat_id,
        allowed_chat_ids=[admin_chat_id, client_chat_id],
        use_mock=True,
    )
    agent = TelegramBotAgent(telegram_connector=connector)

    # Khách thường (chat 777777) cố gọi /set_bm
    update = {
        "update_id": 101,
        "message": {
            "message_id": 10,
            "chat": {"id": int(client_chat_id)},
            "from": {"id": int(client_chat_id), "username": "client_tester"},
            "text": "/set_bm 1 BM_01 ADMIN FULL",
        },
    }
    result = agent.process_update(db, update)
    assert result is not None
    assert result["status"] == "rejected"
    assert result["reason"] == "admin_only"

    # Admin (chat 888888) thực thi -> thành công (hoặc báo cú pháp/thực thi bình thường)
    admin_update = {
        "update_id": 102,
        "message": {
            "message_id": 11,
            "chat": {"id": int(admin_chat_id)},
            "from": {"id": int(admin_chat_id), "username": "super_admin"},
            "text": "/status",
        },
    }
    admin_res = agent.process_update(db, admin_update)
    assert admin_res["status"] == "processed"


def test_prevent_balance_leakage_on_name_mention(db):
    """Chat Telegram chưa liên kết dù có nhắc tên khách hàng cũng TUYỆT ĐỐI không lộ số dư ví."""
    cust = make_customer(db, "Tập Đoàn Bất Động Sản Phúc Khang")
    cust.telegram_chat_id = "555111222"
    cust.telegram_username = "phuckhang_official"
    db.commit()

    bal = ClientBalance(customer_id=cust.id, currency="VND", amount=Decimal("99000000.00"))
    db.add(bal)
    db.commit()

    # Kẻ lạ (chat_id = 99999999, username = hacker) nhắn tin hỏi số dư và nhắc tên Phúc Khang
    res = dispatch_client_message(
        session=db,
        chat_id="99999999",
        username="hacker_impersonator",
        sender_name="Kẻ Giả Mạo",
        message_text="Cho em xem số dư ví của Tập Đoàn Bất Động Sản Phúc Khang với",
    )

    # Phải ghi nhận task dạng unverified lead nhưng không gắn customer_id
    assert res["customer_id"] is None
    # Nội dung phản hồi TUYỆT ĐỐI không có số tiền số dư 99,000,000
    assert "99,000,000" not in res["reply_text"]
    assert "99000000" not in res["reply_text"]
    assert "chưa liên kết" in res["reply_text"]
    assert "bảo mật" in res["reply_text"]


# ==============================================================================
# PRIORITY 2: STRICT FERNET ENCRYPTION — NO PLAINTEXT FALLBACK
# ==============================================================================

def test_refuse_plaintext_when_master_key_missing(monkeypatch):
    """Từ chối lưu thông tin VIA và kho tài nguyên khi thiếu khóa master Fernet."""
    monkeypatch.setattr(settings, "exchange_master_key", "")

    # 1. via_manager.encrypt_via_credentials phải raise RuntimeError
    with pytest.raises(RuntimeError) as exc_via:
        encrypt_via_credentials({"password": "secret_password_123"})
    assert "ADSOS_EXCHANGE_MASTER_KEY" in str(exc_via.value)

    # 2. inventory.encrypt_credentials phải raise RuntimeError
    with pytest.raises(RuntimeError) as exc_inv:
        encrypt_credentials("1000888999|secret_pass|2FA_KEY")
    assert "ADSOS_EXCHANGE_MASTER_KEY" in str(exc_inv.value)


# ==============================================================================
# PRIORITY 3 & 5: CLIENT PORTAL TEMPORAL ISOLATION & MULTI-CURRENCY DECIMAL
# ==============================================================================

def test_portal_temporal_isolation_and_multi_currency(db, client):
    """Cổng khách hàng chỉ thấy chi tiêu trong kỳ [valid_from, valid_to] và tách riêng tiền tệ Decimal."""
    c1 = make_customer(db, "Khách Hàng Renter 1")
    c2 = make_customer(db, "Khách Hàng Renter 2")

    acc = AdAccount(meta_ad_account_id="act_shared_account_99", name="Shared Ad Account", timezone_name="Asia/Ho_Chi_Minh")
    db.add(acc)
    db.flush()

    # Renter 1 thuê từ 01/10 đến 15/10/2026
    t_start = datetime_utc(2026, 10, 1)
    t_handoff = datetime_utc(2026, 10, 15)
    t_end = datetime_utc(2026, 10, 31)

    assign_c1 = AdAccountAssignment(customer_id=c1.id, ad_account_id=acc.id, valid_from=t_start, valid_to=t_handoff)
    # Renter 2 thuê từ 15/10/2026 đến nay
    assign_c2 = AdAccountAssignment(customer_id=c2.id, ad_account_id=acc.id, valid_from=t_handoff, valid_to=None)
    db.add_all([assign_c1, assign_c2])
    db.flush()

    camp_c1 = Campaign(meta_campaign_id="cmp_c1_oct", ad_account_id=acc.id, customer_id=c1.id, name="Camp Renter 1", meta_status="PAUSED")
    camp_c2_vnd = Campaign(meta_campaign_id="cmp_c2_vnd", ad_account_id=acc.id, customer_id=c2.id, name="Camp Renter 2 VND", meta_status="ACTIVE")
    camp_c2_usd = Campaign(meta_campaign_id="cmp_c2_usd", ad_account_id=acc.id, customer_id=c2.id, name="Camp Renter 2 USD", meta_status="ACTIVE")
    db.add_all([camp_c1, camp_c2_vnd, camp_c2_usd])
    db.flush()

    # Spend của Renter 1 vào ngày 10/10: 5,000,000 VND
    s1 = SpendSnapshot(campaign_id=camp_c1.id, snapshot_at=datetime_utc(2026, 10, 10), spend_amount=Decimal("5000000.00"), currency="VND", data_status=DATA_VERIFIED)
    # Spend của Renter 2 vào ngày 20/10: 12,000,000 VND và 450.00 USD
    s2_vnd = SpendSnapshot(campaign_id=camp_c2_vnd.id, snapshot_at=datetime_utc(2026, 10, 20), spend_amount=Decimal("12000000.00"), currency="VND", data_status=DATA_VERIFIED)
    s2_usd = SpendSnapshot(campaign_id=camp_c2_usd.id, snapshot_at=datetime_utc(2026, 10, 22), spend_amount=Decimal("450.00"), currency="USD", data_status=DATA_VERIFIED)
    db.add_all([s1, s2_vnd, s2_usd])
    db.commit()

    # Tạo portal token cho Renter 2
    res_token = client.post(f"/api/v1/portal/customers/{c2.id}/generate-token")
    assert res_token.status_code == 200
    token2 = res_token.json()["portal_token"]

    # Đọc dữ liệu cổng Renter 2
    res_portal = client.get(f"/api/v1/portal/{token2}")
    assert res_portal.status_code == 200
    portal_data = res_portal.json()

    # 1. Renter 2 KHÔNG ĐƯỢC thấy chi tiêu 5,000,000 VND của Renter 1 (trước 15/10)
    assert "totals_by_currency" in portal_data
    totals = portal_data["totals_by_currency"]
    # Chi tiêu VND của Renter 2 phải chính xác là 12,000,000 (không bị cộng gộp 5,000,000 của Renter 1)
    assert totals.get("VND") == "12000000.00"
    # Chi tiêu USD của Renter 2 phải là 450.00 và giữ nguyên riêng biệt
    assert totals.get("USD") == "450.00"


# ==============================================================================
# PRIORITY 4: REAL META SYNC VS MOCK MODE & ERROR PRESERVATION
# ==============================================================================

def test_real_sync_error_handling_without_overwriting_or_fabricating(db, monkeypatch):
    """Khi mock_mode=False và Meta API trả lỗi, bảo lưu nguyên vẹn dữ liệu cũ, không tạo fake BMs/accounts."""
    # Tạo VIA với dữ liệu có sẵn
    via = ViaProfile(
        uid="100088991122334",
        profile_name="VIA Chạy Thật Cần Bảo Vệ",
        profile_dir="profiles/via_100088991122334",
        user_agent="Mozilla/5.0 Chrome/120.0.0.0",
        encrypted_credentials=encrypt_via_credentials({"access_token": "EAAB_EXPIRED_TOKEN_123"}),
        token_status="ACTIVE",
    )
    db.add(via)
    db.flush()

    # Thêm 1 BM và 1 TKQC thật trước đó
    old_bm = SyncedBM(bm_id="BM_OLD_REAL_001", via_profile_id=via.id, name="Old Real Holding BM")
    old_acc = SyncedAdAccount(via_profile_id=via.id, act_id="111222333", name="Old Real Ad Account", total_spend=88000.0)
    db.add_all([old_bm, old_acc])
    db.commit()

    # Giả lập httpx client transport trả về lỗi 401 Token Expired (Lỗi 190 của Meta)
    def fake_handler(request: httpx.Request):
        return httpx.Response(
            401,
            json={"error": {"message": "Error validating access token: Session has expired.", "type": "OAuthException", "code": 190}},
        )

    transport = httpx.MockTransport(fake_handler)

    # Chạy sync với mock_mode=False
    res = sync_via_all_assets(
        session=db,
        via_id=via.id,
        mock_data=None,
        client_transport=transport,
        mock_mode=False,
    )

    # 1. Phải báo lỗi rõ ràng bằng tiếng Việt và ghi nhận status EXPIRED
    assert res["success"] is False
    assert res["status"] == "EXPIRED"
    assert "Mã 190" in res["message"] or "hết hạn" in res["message"]

    # 2. Dữ liệu cũ trong database PHẢI ĐƯỢC GIỮ NGUYÊN HOÀN TOÀN
    db.refresh(via)
    assert via.token_status == "EXPIRED"

    remaining_bms = db.scalars(db.query(SyncedBM).filter(SyncedBM.via_profile_id == via.id).statement).all()
    remaining_accs = db.scalars(db.query(SyncedAdAccount).filter(SyncedAdAccount.via_profile_id == via.id).statement).all()
    assert len(remaining_bms) == 1
    assert remaining_bms[0].bm_id == "BM_OLD_REAL_001"
    assert len(remaining_accs) == 1
    assert remaining_accs[0].act_id == "111222333"

    # 3. Tuyệt đối KHÔNG sinh fake BM Holding 01 hoặc Agency Rental BM
    assert not any("Holding BM 01" in b.name for b in remaining_bms)


# ==============================================================================
# PRIORITY 5: QUERY OPTIMIZATION & UNIFIED CONNECTOR HEALTH STATUS
# ==============================================================================

def test_vias_sql_aggregation_and_pagination(db, client):
    """Kiểm tra thống kê VIA bằng SQL aggregation và phân trang limit/offset."""

    # Tạo 3 VIA
    v1 = ViaProfile(
        uid="9000000001",
        profile_name="VIA Page Test 1",
        profile_dir="profiles/v1",
        user_agent="Chrome",
        encrypted_credentials=encrypt_via_credentials({"access_token": "token1"}),
        uid_live_status="LIVE",
        token_status="ACTIVE",
        ad_account_count=2,
        page_count=1,
    )
    v2 = ViaProfile(
        uid="9000000002",
        profile_name="VIA Page Test 2",
        profile_dir="profiles/v2",
        user_agent="Chrome",
        encrypted_credentials=encrypt_via_credentials({"access_token": "token2"}),
        uid_live_status="DIE",
        token_status="NONE",
        ad_account_count=0,
        page_count=0,
    )
    db.add_all([v1, v2])
    db.commit()

    # Gọi API phân trang limit=1, offset=0
    res = client.get("/api/v1/vias?limit=1&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert len(data["vias"]) == 1
    assert "stats" in data
    stats = data["stats"]
    assert stats["total_vias"] >= 2
    assert stats["live_count"] >= 1
    assert stats["die_count"] >= 1


def test_unified_connector_health_derivation(db, client):
    """Trạng thái connector trong /unified/overview phản ánh mode và health chuẩn xác."""
    res = client.get("/api/v1/unified/overview")
    assert res.status_code == 200
    ov = res.json()
    connectors = ov["connectors"]

    # Meta Ads
    assert "meta_ads" in connectors
    assert connectors["meta_ads"]["mode"] in ("live", "mock", "unconfigured")
    assert connectors["meta_ads"]["health"] in ("HEALTHY", "DEGRADED", "ERROR")

    # Binance & PingPong
    assert "binance" in connectors
    assert "health" in connectors["binance"]
    assert "pingpong" in connectors
    assert "health" in connectors["pingpong"]
