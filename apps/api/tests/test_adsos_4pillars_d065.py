"""Kiểm thử toàn diện Kiến trúc 4 Trụ Cột và Quyết định D-065 (Decision D-065).

Bao gồm:
- BrowserNode Model & Mã hóa Fernet cho Session Tokens (EAAG, EAAB, Cookie, DTSG).
- Control Hub Heartbeat & Polling (/api/v1/control-hub/nodes/heartbeat, /nodes).
- Remote Command Dispatch (/api/v1/control-hub/dispatch) và Task Pulling.
- 70 Workflow Templates (/api/v1/ads-check/workflows) & Custom Workflow.
- Super Target Explorer (/api/v1/ads-check/super-target).
- Lên Camp Hàng Loạt với quy đổi tiền tệ tự động & Trạng thái ACTIVE / PAUSED (D-065).
- Ads Save Quản lý Tài Sản (/api/v1/ads-check/ads-save).
- Đồng bộ Ingest Extension với Session Credentials & Thuộc tính mở rộng (hidden_limit, card_bin, pixel_list).
"""

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.extension_remote import (
    BrowserNode,
    ExtensionRemoteTask,
    SavedAdAsset,
    WorkflowTemplate,
)
from app.models.via import SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.via_manager import encrypt_via_credentials
from app.services.workflow_presets import seed_workflow_presets


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app, base_url="http://127.0.0.1")
    yield test_client
    app.dependency_overrides.clear()


def test_browser_node_fernet_encryption(db):
    """Kiểm tra BrowserNode mã hóa Fernet các trường nhạy cảm ở tầng Database."""
    node = BrowserNode(
        node_uid="adspower_profile_99",
        node_name="Profile Marketing AdsPower",
        browser_type="ADSPOWER",
        fb_uid="1000888999111",
        status="ONLINE",
    )
    # Gán session credentials qua property setters
    node.eaag_token = "EAAG_TEST_TOKEN_SECRET_123"
    node.eaab_token = "EAAB_TEST_TOKEN_SECRET_456"
    node.cookie = "c_user=1000888999111; xs=secret_xs_session;"
    node.fb_dtsg = "AQH_secret_dtsg_token"

    db.add(node)
    db.commit()
    db.refresh(node)

    # 1. Getter phải giải mã ra đúng plaintext ban đầu
    assert node.eaag_token == "EAAG_TEST_TOKEN_SECRET_123"
    assert node.eaab_token == "EAAB_TEST_TOKEN_SECRET_456"
    assert node.cookie == "c_user=1000888999111; xs=secret_xs_session;"
    assert node.fb_dtsg == "AQH_secret_dtsg_token"

    # 2. Các cột _enc thô trong Database PHẢI là chuỗi mã hóa, KHÔNG chứa plaintext
    assert node.eaag_token_enc != "EAAG_TEST_TOKEN_SECRET_123"
    assert node.eaab_token_enc != "EAAB_TEST_TOKEN_SECRET_456"
    assert "secret_xs_session" not in (node.cookie_enc or "")
    assert "AQH_secret_dtsg_token" not in (node.fb_dtsg_enc or "")


def test_control_hub_heartbeat_and_nodes_listing(client, db):
    """Kiểm tra heartbeat từ Extension/Antidetect profile và API danh sách node."""
    payload = {
        "node_uid": "chrome_node_vn_01",
        "node_name": "Chrome VIA Hà Nội 01",
        "browser_type": "CHROME",
        "fb_uid": "100099887766554",
        "eaag_token": "EAAG_HEARTBEAT_TOKEN",
        "eaab_token": "EAAB_HEARTBEAT_TOKEN",
        "cookie": "c_user=100099887766554; xs=session_xs;",
        "fb_dtsg": "AQH_dtsg_live",
        "status": "ONLINE",
    }

    # Gửi heartbeat
    res = client.post("/api/v1/control-hub/nodes/heartbeat", json=payload)
    assert res.status_code == 200
    hb_data = res.json()
    assert hb_data["success"] is True
    assert hb_data["node_uid"] == "chrome_node_vn_01"
    assert isinstance(hb_data["pending_tasks"], list)

    # Lấy danh sách nodes
    res_list = client.get("/api/v1/control-hub/nodes")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["total"] >= 1
    assert list_data["online_count"] >= 1

    node_found = next(
        (n for n in list_data["nodes"] if n["node_uid"] == "chrome_node_vn_01"), None
    )
    assert node_found is not None
    assert node_found["node_name"] == "Chrome VIA Hà Nội 01"
    assert node_found["browser_type"] == "CHROME"
    assert node_found["status"] == "ONLINE"
    assert node_found["has_eaag"] is True
    assert node_found["has_eaab"] is True
    assert node_found["has_cookie"] is True
    assert node_found["has_fb_dtsg"] is True


def test_control_hub_command_dispatch(client, db):
    """Kiểm tra phát lệnh điều khiển từ xa (dispatch) và nhận task qua heartbeat."""
    # Tạo node trước
    node = BrowserNode(
        node_uid="gologin_profile_02",
        node_name="GoLogin Team Alpha",
        browser_type="GOLOGIN",
        status="ONLINE",
    )
    db.add(node)
    db.commit()

    # Dispatch command tới node này
    dispatch_res = client.post(
        "/api/v1/control-hub/dispatch",
        json={
            "node_uid": "gologin_profile_02",
            "command": "REMOVE_HIDDEN_ADMIN",
            "payload": {"account_ids": ["12345678", "87654321"]},
        },
    )
    assert dispatch_res.status_code == 200
    dispatch_data = dispatch_res.json()
    assert dispatch_data["success"] is True
    task_id = dispatch_data["task_id"]
    assert task_id > 0

    # Heartbeat tiếp theo của node phải nhận được task này
    hb_res = client.post(
        "/api/v1/control-hub/nodes/heartbeat",
        json={"node_uid": "gologin_profile_02", "status": "ONLINE"},
    )
    assert hb_res.status_code == 200
    pending = hb_res.json()["pending_tasks"]
    assert len(pending) >= 1
    task_received = next(
        (t for t in pending if t.get("numeric_id") == task_id or str(t.get("id")) == str(task_id)),
        None,
    )
    assert task_received is not None
    assert (task_received.get("task_type") or task_received.get("command_type")) == "REMOVE_HIDDEN_ADMIN"


def test_workflow_templates_seeded_and_custom(client, db):
    """Kiểm tra 70 kịch bản quy trình (Pillar 2) được seed sẵn và tạo mới kịch bản tùy biến."""
    # Đảm bảo workflow đã được seed
    seed_workflow_presets(db)

    # 1. Lấy tất cả workflows
    res = client.get("/api/v1/ads-check/workflows")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 70

    # 2. Lọc theo danh mục "Quản lý TKQC"
    res_cat = client.get("/api/v1/ads-check/workflows?category=Quản lý TKQC")
    assert res_cat.status_code == 200
    cat_data = res_cat.json()
    assert cat_data["total"] >= 10
    for wf in cat_data["workflows"]:
        assert "Quản lý TKQC" in wf["category"]

    # 3. Tạo workflow tùy biến
    custom_wf_res = client.post(
        "/api/v1/ads-check/workflows",
        json={
            "code": "CUSTOM_FLOW_01",
            "name": "Kịch bản tùy biến nuôi Page và đẩy Camp",
            "category": "Lên Camp & Boost Post",
            "steps": [
                {"action": "WARM_PAGE", "label": "Nuôi Page tương tác"},
                {"action": "CREATE_AD_SET", "label": "Tạo nhóm quảng cáo"},
            ],
            "jitter_min_ms": 1200,
            "jitter_max_ms": 2500,
        },
    )
    assert custom_wf_res.status_code == 200
    created = custom_wf_res.json()["workflow"]
    assert created["code"] == "CUSTOM_FLOW_01"
    assert created["is_builtin"] is False


def test_super_target_explorer(client):
    """Kiểm tra tính năng Super Target quét hơn 500 sở thích ẩn Meta."""
    res = client.get("/api/v1/ads-check/super-target?keyword=sneaker&limit=50")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["keyword"] == "sneaker"
    assert len(data["data"]) > 0

    first_item = data["data"][0]
    assert "id" in first_item
    assert "name" in first_item
    assert "audience_size_lower_bound" in first_item
    assert "topic" in first_item


def test_bulk_camp_currency_conversion_and_status(client, db):
    """Kiểm tra tạo chiến dịch hàng loạt tự quy đổi tiền tệ và hỗ trợ trạng thái ACTIVE/PAUSED per D-065."""
    # Tạo 2 TKQC với các loại tiền tệ khác nhau
    via = ViaProfile(
        uid="1000111222333",
        profile_name="VIA Lên Camp Test",
        profile_dir="profiles/1000111222333",
        user_agent="Mozilla/5.0 Chrome/120.0.0.0",
        encrypted_credentials=encrypt_via_credentials({"access_token": "TEST_TOKEN"}),
    )
    db.add(via)
    db.commit()

    acc_vnd = SyncedAdAccount(
        via_profile_id=via.id,
        act_id="11111111",
        name="TKQC Tiền VND",
        currency="VND",
        account_status=1,
    )
    acc_usd = SyncedAdAccount(
        via_profile_id=via.id,
        act_id="22222222",
        name="TKQC Tiền USD",
        currency="USD",
        account_status=1,
    )
    db.add_all([acc_vnd, acc_usd])
    db.commit()

    # 1. Tạo Camp với trạng thái ACTIVE (theo D-065 cho phép bật chạy ngay)
    res_active = client.post(
        "/api/v1/ads-check/bulk-camp",
        json={
            "act_ids": ["11111111", "22222222"],
            "name": "Camp Tết Sale 2026",
            "objective": "OUTCOME_ENGAGEMENT",
            "base_daily_budget_vnd": 500000,
            "status": "ACTIVE",
        },
    )
    assert res_active.status_code == 200
    data_active = res_active.json()
    assert data_active["success"] is True
    assert data_active["status"] == "ACTIVE"
    assert data_active["total_accounts"] == 2

    # Kiểm tra chuyển đổi tiền tệ
    res_map = {r["act_id"]: r for r in data_active["results"]}
    assert res_map["11111111"]["currency"] == "VND"
    assert res_map["11111111"]["budget_in_currency"] == 500000.0

    assert res_map["22222222"]["currency"] == "USD"
    # 500,000 VND / 25,400 ~ 19.69 USD
    assert 19.0 <= res_map["22222222"]["budget_in_currency"] <= 21.0

    # 2. Tạo Camp với trạng thái PAUSED
    res_paused = client.post(
        "/api/v1/ads-check/bulk-camp",
        json={
            "act_ids": ["11111111"],
            "name": "Camp Draft Chờ Duyệt",
            "base_daily_budget_vnd": 200000,
            "status": "PAUSED",
        },
    )
    assert res_paused.status_code == 200
    assert res_paused.json()["status"] == "PAUSED"

    # Dọn dẹp dữ liệu test
    db.delete(acc_vnd)
    db.delete(acc_usd)
    db.delete(via)
    db.commit()


def test_ads_save_crud(client, db):
    """Kiểm tra tính năng Ads Save (Kho lưu trữ đối tượng và bài viết quảng cáo)."""
    # 1. Lưu tài sản mới
    save_res = client.post(
        "/api/v1/ads-check/ads-save",
        json={
            "asset_type": "SUPER_TARGET_SET",
            "name": "Tập Sở Thích Thời Trang Nữ GenZ",
            "payload": {
                "interests": ["sneaker", "fashion", "dress"],
                "age_min": 18,
                "age_max": 28,
            },
        },
    )
    assert save_res.status_code == 200
    save_data = save_res.json()
    assert save_data["success"] is True
    asset_id = save_data["asset"]["id"]

    # 2. Lấy danh sách tài sản đã lưu
    get_res = client.get("/api/v1/ads-check/ads-save?asset_type=SUPER_TARGET_SET")
    assert get_res.status_code == 200
    list_assets = get_res.json()["assets"]
    assert any(a["id"] == asset_id for a in list_assets)

    # 3. Xóa tài sản
    del_res = client.delete(f"/api/v1/ads-check/ads-save/{asset_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_extension_ingest_retains_session_and_extended_metadata(client, db):
    """Kiểm tra ingest payload từ Extension lưu trữ encrypted session và metadata mở rộng."""
    ingest_payload = {
        "via_uid": "1000777888999",
        "profile_name": "VIA Agency VIP 01",
        "cookie": "c_user=1000777888999; xs=session_secret_cookie;",
        "access_token": "EAAX_FALLBACK_TOKEN",
        "eaag_token": "EAAG_FULL_SESSION_TOKEN",
        "eaab_token": "EAAB_FULL_SESSION_TOKEN",
        "fb_dtsg": "AQH_SESSION_DTSG",
        "bms": [
            {
                "bm_id": "999888777",
                "name": "BM 2500 Kháng",
                "hidden_admin_count": 0,
            }
        ],
        "ad_accounts": [
            {
                "act_id": "888999111",
                "name": "TKQC No Limit Scan",
                "currency": "USD",
                "ad_trust_dsl": 50000000,
                "hidden_limit": 50000000,
                "funding_source_summary": "Visa Ending 9988",
                "card_bin": "411111",
                "location_verified": True,
                "appeal_status": "NONE",
                "pixel_list": ["px_1001", "px_1002"],
            }
        ],
        "pages": [
            {
                "page_id": "777666555",
                "name": "Fanpage Thời Trang Cao Cấp",
                "is_published": True,
                "appeal_status": "APPROVED",
            }
        ],
    }

    res = client.post("/api/v1/vias/extension-ingest", json=ingest_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True

    # Kiểm tra trong DB
    via = db.execute(
        select(ViaProfile).where(ViaProfile.uid == "1000777888999")
    ).scalar_one_or_none()
    assert via is not None
    # Token & Cookie phải được mã hóa tại rest
    assert via.cookie is not None
    assert "session_secret_cookie" in via.cookie

    # Kiểm tra TKQC có metadata mở rộng
    acc = db.execute(
        select(SyncedAdAccount).where(SyncedAdAccount.act_id == "888999111")
    ).scalar_one_or_none()
    assert acc is not None
    assert acc.hidden_limit == 50000000
    assert acc.funding_source_summary == "Visa Ending 9988"
    assert acc.card_bin == "411111"
    assert acc.location_verified is True
    assert acc.appeal_status == "NONE"
    assert acc.pixel_list == ["px_1001", "px_1002"]

    # Kiểm tra Page có appeal_status
    page = db.execute(
        select(SyncedPage).where(SyncedPage.page_id == "777666555")
    ).scalar_one_or_none()
    assert page is not None
    assert page.is_published is True
    assert page.appeal_status == "APPROVED"

    # Dọn dẹp dữ liệu test để không ảnh hưởng các test suite khác
    db.delete(acc)
    db.delete(page)
    bm = db.execute(select(SyncedBM).where(SyncedBM.bm_id == "999888777")).scalar_one_or_none()
    if bm:
        db.delete(bm)
    db.delete(via)
    db.commit()
