"""Kiểm thử toàn diện Multi-VIA Farm Manager, Proxy Routing, TOTP 2FA, Check Live UID, 1-Click Login & BM Share Memory."""

import base64
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db import get_db
from app.main import app
from app.models.base import Base
from app.models.client_bm_preference import ClientBMPreference
from app.models.client_task import ClientTask, TASK_TYPE_ADD_MAIL_TO_BM
from app.models.customer import Customer
from app.models.via import SyncedBM, ViaProfile
from app.services.auto_fulfillment import (
    apply_admin_bm_selection,
    get_available_bms,
    route_and_fulfill_client_task,
    save_or_update_client_bm_preference,
)
from app.services.via_manager import (
    bulk_import_vias,
    check_bulk_uids_live,
    check_uid_live_status,
    create_or_update_via,
    decrypt_via_credentials,
    encrypt_via_credentials,
    generate_totp_code,
    get_deterministic_user_agent,
    get_isolated_profile_dir,
    login_via_profile,
    normalize_proxy_config,
    parse_bulk_via_text,
    parse_via_string_line,
    sync_via_bm_assets,
    toggle_synced_bm_primary_rental,
)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app, base_url="http://127.0.0.1")
    yield test_client
    app.dependency_overrides.clear()


# ==============================================================================
# 1. TEST PARSER & PROFILE DIR & USER AGENT
# ==============================================================================

def test_parse_via_string_line():
    # Chuẩn 6 phần: UID|PASS|2FA|mail|pass mail|Mail back up
    line1 = "100012345678|SecretPass123|JBSWY3DPEHPK3PXP|user1@gmail.com|MailPass456|backup@gmail.com"
    parsed1 = parse_via_string_line(line1)
    assert parsed1 is not None
    assert parsed1["uid"] == "100012345678"
    assert parsed1["password"] == "SecretPass123"
    assert parsed1["two_fa_secret"] == "JBSWY3DPEHPK3PXP"
    assert parsed1["email"] == "user1@gmail.com"
    assert parsed1["email_password"] == "MailPass456"
    assert parsed1["backup_email"] == "backup@gmail.com"

    # Chỉ có UID|PASS
    line2 = "  615999888777 | ShortPass999  "
    parsed2 = parse_via_string_line(line2)
    assert parsed2 is not None
    assert parsed2["uid"] == "615999888777"
    assert parsed2["password"] == "ShortPass999"
    assert parsed2["two_fa_secret"] == ""

    # Dòng rác / comment
    assert parse_via_string_line("# Comment line") is None
    assert parse_via_string_line("// Another comment") is None
    assert parse_via_string_line("") is None
    assert parse_via_string_line("justonepart") is None


def test_bulk_parse_text_and_profile_isolation():
    # Giả lập nhập 100 dòng VIA
    lines = []
    for i in range(1, 105):
        uid = f"1000{i:08d}"
        lines.append(f"{uid}|Pass_{i}|2FA_SECRET_{i}|mail{i}@agency.vn|mpass{i}|backup{i}@gmail.com")

    bulk_text = "\n".join(lines)
    parsed_list = parse_bulk_via_text(bulk_text)
    assert len(parsed_list) == 104

    # Kiểm tra tính cách ly profile_dir và User Agent nhất quán
    uid_sample = "100000000042"
    dir1 = get_isolated_profile_dir(uid_sample)
    dir2 = get_isolated_profile_dir(uid_sample)
    assert dir1 == dir2
    assert dir1 == "profiles/via_100000000042"

    ua1 = get_deterministic_user_agent(uid_sample)
    ua2 = get_deterministic_user_agent(uid_sample)
    assert ua1 == ua2
    assert "Mozilla/5.0" in ua1


# ==============================================================================
# 2. TEST TOTP 2FA LIVE GENERATOR
# ==============================================================================

def test_live_totp_generation():
    # RFC 6238 test secret "JBSWY3DPEHPK3PXP" (base32 của "12345678901234567890")
    code, remaining = generate_totp_code("JBSWY3DPEHPK3PXP")
    assert len(code) == 6
    assert code.isdigit()
    assert 0 <= remaining <= 30

    # Test secret có dấu cách hoặc chữ thường
    code2, _ = generate_totp_code("jbsw y3dp ehpk 3pxp")
    assert code2 == code

    # Secret rỗng hoặc sai
    empty_code, empty_rem = generate_totp_code("")
    assert empty_code == ""
    assert empty_rem == 0


# ==============================================================================
# 3. TEST PROXY NORMALIZATION
# ==============================================================================

def test_normalize_proxy_config():
    # IP:Port:User:Pass
    p1 = normalize_proxy_config("123.45.67.89:8080:puser:ppass")
    assert p1 is not None
    assert p1["host"] == "123.45.67.89"
    assert p1["port"] == 8080
    assert p1["user"] == "puser"
    assert p1["password"] == "ppass"
    assert p1["url"] == "http://puser:ppass@123.45.67.89:8080"

    # URL socks5
    p2 = normalize_proxy_config("socks5://admin:pass123@10.0.0.1:1080")
    assert p2 is not None
    assert p2["protocol"] == "socks5"
    assert p2["host"] == "10.0.0.1"
    assert p2["port"] == 1080

    # IP:Port (không auth)
    p3 = normalize_proxy_config("192.168.1.100:3128")
    assert p3 is not None
    assert p3["url"] == "http://192.168.1.100:3128"


# ==============================================================================
# 4. TEST CHECK LIVE / DIE UID
# ==============================================================================

class MockLiveTransport(httpx.BaseTransport):
    """Mock redirect tới CDN ảnh scontent của Facebook (LIVE)."""
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://scontent.fhan14-2.fna.fbcdn.net/v/t39.30808-1/avatar.jpg"},
            request=request,
        )


class MockDieTransport(httpx.BaseTransport):
    """Mock trả về 404 hoặc silhouette của Facebook (DIE)."""
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://static.xx.fbcdn.net/rsrc.php/v3/yo/r/UlIqmHJn-SK.gif"},
            request=request,
        )


def test_check_uid_live_and_die(db):
    via_live = create_or_update_via(db, uid="100011112222", password="pwd")
    via_die = create_or_update_via(db, uid="100033334444", password="pwd")
    db.commit()

    # Kiểm tra LIVE
    status_live = check_uid_live_status(db, via_live, client_transport=MockLiveTransport())
    assert status_live == "LIVE"
    assert via_live.uid_live_status == "LIVE"
    assert via_live.last_live_check_at is not None

    # Kiểm tra DIE
    status_die = check_uid_live_status(db, via_die, client_transport=MockDieTransport())
    assert status_die == "DIE"
    assert via_die.uid_live_status == "DIE"

    # Kiểm tra Bulk check
    bulk_res = check_bulk_uids_live(db, via_ids=[via_live.id, via_die.id], client_transport=MockLiveTransport())
    assert bulk_res["total_checked"] == 2
    assert bulk_res["live_count"] == 2


# ==============================================================================
# 5. TEST 1-CLICK LOGIN & BM ASSET DISCOVERY & PRIMARY TOGGLE
# ==============================================================================

def test_login_and_asset_discovery(db):
    via = create_or_update_via(
        db,
        uid="100088889999",
        password="PassWord123",
        two_fa_secret="JBSWY3DPEHPK3PXP",
        email="testvia@gmail.com",
    )
    db.commit()

    # 1. Test Login thành công
    login_res = login_via_profile(db, via.id, access_token="EAAB_TEST_TOKEN")
    assert login_res["success"] is True
    assert login_res["token_status"] == "ACTIVE"
    assert len(login_res["live_2fa_code"]) == 6

    # 2. Test Checkpoint
    checkpoint_res = login_via_profile(db, via.id, access_token="CHECKPOINT_REQUIRED")
    assert checkpoint_res["token_status"] == "CHECKPOINT"

    # 3. Test Đồng bộ BM Assets
    sync_res = sync_via_bm_assets(
        db,
        via.id,
        mock_bms=[
            {"bm_id": "BM_RENTAL_01", "name": "Agency Main Rental BM 01", "ad_account_count": 10, "page_count": 5},
            {"bm_id": "BM_BACKUP_02", "name": "Backup Holding BM 02", "ad_account_count": 4, "page_count": 2},
        ],
    )
    assert sync_res["success"] is True
    assert sync_res["bms_synced"] == 2
    assert sync_res["ad_account_count"] == 14
    assert sync_res["page_count"] == 7

    # 4. Test Toggle BM Chính Cho Thuê (is_primary_rental)
    bm_toggled = toggle_synced_bm_primary_rental(db, "BM_RENTAL_01", is_primary=True)
    assert bm_toggled.is_primary_rental is True

    # Đồng bộ lại: cờ is_primary_rental phải được giữ nguyên
    sync_res2 = sync_via_bm_assets(db, via.id)
    bm_check = db.scalar(select(SyncedBM).where(SyncedBM.bm_id == "BM_RENTAL_01"))
    assert bm_check.is_primary_rental is True


# ==============================================================================
# 6. TEST BM SELECTION & AUTO-REMEMBER ROUTING
# ==============================================================================

def test_bm_selection_and_routing_with_via(db):
    # Tạo khách hàng
    client = Customer(name="Công ty TNHH Thời Trang ABC")
    db.add(client)
    db.commit()

    # Tạo VIA và gắn BM chính cho thuê
    via = create_or_update_via(db, uid="100077778888", password="pwd", profile_name="VIA-VIP-01")
    via.proxy_config = "1.2.3.4:8080:user:pass"
    db.flush()

    bm = SyncedBM(
        bm_id="BM_PRIMARY_VIP",
        name="BM Chính Cho Thuê VIP 01",
        via_profile_id=via.id,
        is_primary_rental=True,
        ad_account_count=20,
    )
    db.add(bm)
    db.commit()

    # Kiểm tra get_available_bms ưu tiên BM chính cho thuê
    available_bms = get_available_bms(db)
    assert len(available_bms) >= 1
    assert available_bms[0]["id"] == "BM_PRIMARY_VIP"
    assert available_bms[0]["is_primary_rental"] is True
    assert available_bms[0]["via_uid"] == "100077778888"

    # Lưu cấu hình ưu tiên (Auto-Remember)
    pref = save_or_update_client_bm_preference(
        session=db,
        client_id=client.id,
        preferred_bm_id="BM_PRIMARY_VIP",
        via_profile_id=via.id,
        bm_role="EMPLOYEE",
        ad_account_access_type="PARTIAL",
        partial_permissions=["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE"],
    )
    assert pref.preferred_bm_id == "BM_PRIMARY_VIP"
    assert pref.via_profile_id == via.id

    # Tạo ClientTask và tự động định tuyến
    task = ClientTask(
        customer_id=client.id,
        telegram_chat_id="12345678",
        task_type=TASK_TYPE_ADD_MAIL_TO_BM,
        raw_message="Add mail marketer@abc.com vào BM giúp mình",
        extracted_data=json.dumps({"email": "marketer@abc.com"}),
    )
    db.add(task)
    db.commit()

    route_res = route_and_fulfill_client_task(db, task)
    assert route_res["status"] == "AUTO_ROUTED"

    # Kiểm tra thông tin định tuyến đã ghi nhớ trong task
    ext = json.loads(task.extracted_data)
    fulfillment = ext["fulfillment"]
    assert fulfillment["preferred_bm_id"] == "BM_PRIMARY_VIP"
    assert fulfillment["via_uid"] == "100077778888"
    assert fulfillment["proxy_routing"] == "1.2.3.4:8080:user:pass"
    assert fulfillment["is_primary_rental"] is True


# ==============================================================================
# 7. TEST FASTAPI ENDPOINTS
# ==============================================================================

def test_api_vias_endpoints(client, db):
    # 1. Bulk import qua API
    import_payload = {
        "raw_text": (
            "10009901|pwd01|JBSWY3DPEHPK3PXP|m1@a.com|p1|b1@a.com\n"
            "10009902|pwd02|JBSWY3DPEHPK3PXP|m2@a.com|p2|b2@a.com\n"
            "10009903|pwd03|JBSWY3DPEHPK3PXP|m3@a.com|p3|b3@a.com"
        ),
        "default_proxy": "10.20.30.40:8080:usr:pwd",
    }
    res_import = client.post("/api/v1/vias/bulk", json=import_payload)
    assert res_import.status_code == 200
    assert res_import.json()["imported"] == 3

    # 2. List VIAs
    res_list = client.get("/api/v1/vias?search=100099")
    assert res_list.status_code == 200
    data = res_list.json()
    assert len(data["vias"]) == 3
    assert data["stats"]["total_vias"] >= 3
    via_id = data["vias"][0]["id"]

    # 3. Get Live 2FA
    res_2fa = client.get(f"/api/v1/vias/{via_id}/2fa")
    assert res_2fa.status_code == 200
    assert len(res_2fa.json()["code"]) == 6

    # 4. Update Proxy
    res_proxy = client.patch(
        f"/api/v1/vias/{via_id}/proxy",
        json={"proxy_config": "99.88.77.66:3128:testuser:testpass"},
    )
    assert res_proxy.status_code == 200
    assert "99.88.77.66:3128" in res_proxy.json()["via"]["proxy"]["display"]

    # 5. 1-Click Login
    res_login = client.post(
        f"/api/v1/vias/{via_id}/login",
        json={"access_token": "EAA_TOKEN_TEST"},
    )
    assert res_login.status_code == 200
    assert res_login.json()["token_status"] == "ACTIVE"

    # 6. Đồng bộ BM Assets
    res_sync = client.post(f"/api/v1/vias/{via_id}/sync-assets")
    assert res_sync.status_code == 200
    assert res_sync.json()["bms_synced"] > 0

    # 7. List Synced BMs & Toggle Primary Rental
    res_bms = client.get("/api/v1/vias/bms/synced")
    assert res_bms.status_code == 200
    bms = res_bms.json()["bms"]
    assert len(bms) > 0
    target_bm = bms[0]["bm_id"]

    res_toggle = client.patch(
        f"/api/v1/vias/bms/{target_bm}/primary",
        json={"is_primary_rental": True},
    )
    assert res_toggle.status_code == 200
    assert res_toggle.json()["bm"]["is_primary_rental"] is True

    # 8. Check BM Routing Options qua API clients
    res_options = client.get("/api/v1/clients/bm-options")
    assert res_options.status_code == 200
    assert res_options.json()["available_bms"][0]["is_primary_rental"] is True


def test_create_via_without_password_for_oauth(client, db):
    """VIA chỉ dùng cấp quyền OAuth chính thức: tạo được khi không có mật khẩu."""
    res = client.post(
        "/api/v1/vias",
        json={"uid": "100012345678901", "profile_name": "VIA-OAUTH-ONLY"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["via"]["uid"] == "100012345678901"
    assert body["via"]["profile_name"] == "VIA-OAUTH-ONLY"

    via = db.scalar(select(ViaProfile).where(ViaProfile.uid == "100012345678901"))
    assert via is not None
    assert decrypt_via_credentials(via.encrypted_credentials)["password"] == ""


def test_update_via_blank_password_keeps_old_credentials(db):
    """Cập nhật VIA mà bỏ trống mật khẩu/2FA/email thì giữ giá trị cũ, không ghi đè rỗng."""
    create_or_update_via(
        session=db,
        uid="100099988877766",
        password="OldSecretPass",
        two_fa_secret="JBSWY3DPEHPK3PXP",
        email="old@example.com",
    )
    db.commit()

    via = create_or_update_via(session=db, uid="100099988877766", profile_name="Đổi tên")
    db.commit()

    creds = decrypt_via_credentials(via.encrypted_credentials)
    assert creds["password"] == "OldSecretPass"
    assert creds["two_fa_secret"] == "JBSWY3DPEHPK3PXP"
    assert creds["email"] == "old@example.com"
    assert via.profile_name == "Đổi tên"
