"""Kiểm thử chuyên sâu tính năng Headless VIA Background Login, Token/Cookie Extractor & SMIT Ads Check Explorer."""

import base64
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db import get_db
from app.main import app
from app.models.client_bm_preference import ClientBMPreference
from app.models.customer import Customer
from app.models.via import SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.via_manager import (
    create_or_update_via,
    decrypt_via_credentials,
    get_ads_check_explorer_data,
    headless_login_and_extract,
    remove_hidden_admins_action,
    rename_accounts_action,
    serialize_synced_ad_account,
    serialize_synced_page,
    share_pixel_action,
    super_share_ads_action,
    sync_via_all_assets,
)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app, base_url="http://127.0.0.1")
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_via_profile(db):
    """Fixture tạo hồ sơ VIA hoàn chỉnh với 2FA và proxy."""
    via = create_or_update_via(
        session=db,
        uid="100088997766554",
        password="VerySecurePassword999",
        profile_name="VIA-SMIT-TEST",
        two_fa_secret="JBSWY3DPEHPK3PXP",
        email="viasmit@agency.com",
        email_password="mailsecretpass",
        proxy_config="192.168.1.50:8080:proxyuser:proxypass",
    )
    db.commit()
    db.refresh(via)
    yield via

    # Teardown: dọn dẹp các tài sản liên kết với via này để tránh ô nhiễm DB
    try:
        from sqlalchemy import delete
        db.execute(delete(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id))
        db.execute(delete(SyncedBM).where(SyncedBM.via_profile_id == via.id))
        db.execute(delete(SyncedPage).where(SyncedPage.via_profile_id == via.id))
        db.execute(delete(ViaProfile).where(ViaProfile.id == via.id))
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture
def sample_customer(db):
    """Fixture tạo khách hàng với tên duy nhất."""
    import uuid
    cust = Customer(
        name=f"Doanh Nghiệp SMIT {uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db.add(cust)
    db.commit()
    db.refresh(cust)
    yield cust

    # Teardown
    try:
        from sqlalchemy import delete
        db.execute(delete(ClientBMPreference).where(ClientBMPreference.client_id == cust.id))
        db.execute(delete(Customer).where(Customer.id == cust.id))
        db.commit()
    except Exception:
        db.rollback()


# ==============================================================================
# 1. HEADLESS LOGIN & TOKEN/COOKIE EXTRACTOR TESTS
# ==============================================================================

def test_headless_login_and_token_extraction(db, sample_via_profile):
    """Kiểm tra Headless Background Login trích xuất Cookie & Access Token EAAB..."""
    via_id = sample_via_profile.id

    res = headless_login_and_extract(session=db, via_id=via_id)

    assert res["success"] is True
    assert res["via_id"] == via_id
    assert res["token_status"] == "ACTIVE"
    assert "EAAB" in res["access_token"] or "EAAG" in res["access_token"]
    assert "c_user=" in res["cookie"]
    assert len(res["live_2fa_code"]) == 6

    # Kiểm tra lưu vào database đã được mã hóa Fernet
    db.refresh(sample_via_profile)
    assert sample_via_profile.token_status == "ACTIVE"

    creds = decrypt_via_credentials(sample_via_profile.encrypted_credentials)
    assert creds["access_token"] == res["access_token"]
    assert creds["cookie"] == res["cookie"]


def test_headless_login_checkpoint_detection(db):
    """Kiểm tra phát hiện trạng thái Checkpoint từ Meta khi đăng nhập."""
    via = create_or_update_via(
        session=db,
        uid="100077771111222",
        password="checkpoint_error_pass",
        profile_name="VIA-CHECKPOINT-TEST",
    )
    db.commit()

    try:
        res = headless_login_and_extract(session=db, via_id=via.id)
        assert res["success"] is False
        assert res["token_status"] == "CHECKPOINT"

        db.refresh(via)
        assert via.token_status == "CHECKPOINT"
    finally:
        from sqlalchemy import delete
        db.execute(delete(ViaProfile).where(ViaProfile.id == via.id))
        db.commit()


# ==============================================================================
# 2. DEEP ASSET SCANNER & MODEL SERIALIZATION TESTS
# ==============================================================================

def test_sync_via_all_assets_financial_fields(db, sample_via_profile):
    """Kiểm tra đồng bộ sâu tài sản TK Cá nhân, TK BM, BM và Fanpages với đầy đủ chỉ số tài chính."""
    res = sync_via_all_assets(session=db, via_id=sample_via_profile.id)

    assert res["success"] is True
    assert res["personal_accounts_count"] >= 3
    assert res["bm_accounts_count"] >= 3
    assert res["bms_count"] >= 2
    assert res["pages_count"] >= 2

    # Kiểm tra bảng synced_ad_accounts
    ad_accounts = db.scalars(
        select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == sample_via_profile.id)
    ).all()
    assert len(ad_accounts) == res["personal_accounts_count"] + res["bm_accounts_count"]

    personal_accs = [a for a in ad_accounts if a.account_type == "PERSONAL"]
    bm_accs = [a for a in ad_accounts if a.account_type == "BM"]

    assert len(personal_accs) == 3
    assert len(bm_accs) == 3

    # Kiểm tra trường tài chính chi tiết
    sample_acc = personal_accs[0]
    assert sample_acc.balance > 0
    assert sample_acc.threshold > 0
    assert sample_acc.total_spend > 0
    assert sample_acc.currency in ("VND", "USD")
    assert sample_acc.payment_card_brand is not None
    assert sample_acc.payment_card_last4 is not None

    # Kiểm tra serialization
    serialized = serialize_synced_ad_account(sample_acc)
    assert serialized["card_display"].startswith("[VISA]") or serialized["card_display"].startswith("[MASTERCARD]")
    assert serialized["status_dot"] in ("LIVE", "DIE", "WARNING")

    # Kiểm tra bảng synced_bms và synced_pages
    synced_bms = db.scalars(
        select(SyncedBM).where(SyncedBM.via_profile_id == sample_via_profile.id)
    ).all()
    assert len(synced_bms) == 2

    synced_pages = db.scalars(
        select(SyncedPage).where(SyncedPage.via_profile_id == sample_via_profile.id)
    ).all()
    assert len(synced_pages) == 2
    ser_page = serialize_synced_page(synced_pages[0])
    assert ser_page["likes_count"] > 0
    assert ser_page["followers_count"] > 0


# ==============================================================================
# 3. ADS CHECK EXPLORER DATA & AGGREGATION TESTS
# ==============================================================================

def test_get_ads_check_explorer_data_tabs_and_summary(db, sample_via_profile):
    """Kiểm tra truy vấn explorer data và tính toán tổng hợp footer."""
    # Nạp dữ liệu tài sản
    sync_via_all_assets(session=db, via_id=sample_via_profile.id)

    # 1. Tab Personal
    data_personal = get_ads_check_explorer_data(
        session=db,
        tab="personal",
        via_id=sample_via_profile.id,
        currency_display="VND",
    )
    assert data_personal["tab"] == "personal"
    assert data_personal["total_count"] == 3
    assert len(data_personal["items"]) == 3

    summary_p = data_personal["summary"]
    assert summary_p["total_accounts_count"] == 3
    assert summary_p["total_balance"] > 0
    assert summary_p["total_threshold"] > 0
    assert summary_p["primary_currency"] == "VND"
    assert "Tài khoản quảng cáo" in summary_p["label"]

    # 2. Tab BM
    data_bm = get_ads_check_explorer_data(
        session=db,
        tab="bm",
        via_id=sample_via_profile.id,
    )
    assert data_bm["tab"] == "bm"
    assert data_bm["total_count"] == 3
    assert len(data_bm["items"]) == 3

    # 3. Tab Group (BMs)
    data_group = get_ads_check_explorer_data(
        session=db,
        tab="group",
        via_id=sample_via_profile.id,
    )
    assert data_group["tab"] == "group"
    assert data_group["total_count"] == 2
    assert "Business Managers" in data_group["summary"]["label"]

    # 4. Tab Page
    data_page = get_ads_check_explorer_data(
        session=db,
        tab="page",
        via_id=sample_via_profile.id,
    )
    assert data_page["tab"] == "page"
    assert data_page["total_count"] == 2
    assert "Fanpages" in data_page["summary"]["label"]


def test_ads_check_search_and_pagination(db, sample_via_profile):
    """Kiểm tra tìm kiếm và phân trang trong Ads Check."""
    sync_via_all_assets(session=db, via_id=sample_via_profile.id)

    # Tìm kiếm theo tên
    data_search = get_ads_check_explorer_data(
        session=db,
        tab="personal",
        search="Trúc Xinh",
    )
    assert data_search["total_count"] >= 1
    for it in data_search["items"]:
        assert "Trúc Xinh" in it["name"]

    # Phân trang page_size = 1
    data_paged = get_ads_check_explorer_data(
        session=db,
        tab="personal",
        page=1,
        page_size=1,
    )
    assert data_paged["page"] == 1
    assert data_paged["page_size"] == 1
    assert len(data_paged["items"]) == 1
    assert data_paged["total_pages"] >= 3


# ==============================================================================
# 4. LEFT SUB-MENU QUICK ACTIONS TESTS
# ==============================================================================

def test_remove_hidden_admins_action(db, sample_via_profile):
    """Kiểm tra hành động gỡ bỏ Quản trị viên ẩn."""
    sync_via_all_assets(session=db, via_id=sample_via_profile.id)
    accs = db.scalars(select(SyncedAdAccount.act_id).where(SyncedAdAccount.via_profile_id == sample_via_profile.id)).all()
    selected_ids = list(accs)[:2]

    res = remove_hidden_admins_action(session=db, account_ids=selected_ids)
    assert res["success"] is True
    assert res["cleaned_count"] == len(selected_ids)
    assert res["cleaned_accounts"] == selected_ids


def test_rename_accounts_action(db, sample_via_profile):
    """Kiểm tra đổi thông tin tài khoản quảng cáo hàng loạt (tiền tố, hậu tố, tiền tệ)."""
    sync_via_all_assets(session=db, via_id=sample_via_profile.id)
    acc = db.scalars(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == sample_via_profile.id)).first()
    assert acc is not None

    target_id = acc.act_id
    original_name = acc.name

    res = rename_accounts_action(
        session=db,
        account_ids=[target_id],
        prefix="[VIP]",
        suffix="- Camp 2026",
        currency="USD",
    )

    assert res["success"] is True
    assert res["updated_count"] == 1

    db.refresh(acc)
    assert acc.name.startswith("[VIP]")
    assert acc.name.endswith("- Camp 2026")
    assert acc.currency == "USD"


def test_share_pixel_action(db, sample_via_profile):
    """Kiểm tra chia sẻ Meta Pixel."""
    res = share_pixel_action(
        session=db,
        pixel_id="104598284729102",
        target_account_ids=["37012345601", "37012345602"],
        bm_id="BM_12345",
    )
    assert res["success"] is True
    assert res["pixel_id"] == "104598284729102"
    assert res["shared_count"] == 2


def test_super_share_ads_action_and_memory(db, sample_via_profile, sample_customer):
    """Kiểm tra Super Share Ads cấp quyền và tự động lưu cấu hình BM vào client_bm_preferences."""
    sync_via_all_assets(session=db, via_id=sample_via_profile.id)

    # Đánh dấu 1 BM là Primary Rental
    bm = db.scalar(select(SyncedBM).where(SyncedBM.via_profile_id == sample_via_profile.id).limit(1))
    bm.is_primary_rental = True
    db.commit()

    res = super_share_ads_action(
        session=db,
        client_id=sample_customer.id,
        account_ids=["37011111101", "37011111102"],
        bm_id=bm.bm_id,
        via_profile_id=sample_via_profile.id,
        role="EMPLOYEE",
        access_type="PARTIAL",
        partial_permissions=["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE"],
    )

    assert res["success"] is True
    assert res["saved_preferences"] is True
    assert res["client_id"] == sample_customer.id
    assert res["bm_id"] == bm.bm_id

    # Kiểm tra cấu hình đã được tự động lưu vào client_bm_preferences
    pref = db.scalar(select(ClientBMPreference).where(ClientBMPreference.client_id == sample_customer.id))
    assert pref is not None
    assert pref.preferred_bm_id == bm.bm_id
    assert pref.via_profile_id == sample_via_profile.id
    assert pref.bm_role == "EMPLOYEE"
    assert pref.ad_account_access_type == "PARTIAL"
    assert "MANAGE_CAMPAIGNS" in pref.get_permissions_list()


# ==============================================================================
# 5. REST API ENDPOINTS INTEGRATION TESTS
# ==============================================================================

def test_api_ads_check_explorer_endpoint(client, db, sample_via_profile):
    """Kiểm thử endpoint GET /api/v1/vias/ads-check."""
    sync_via_all_assets(session=db, via_id=sample_via_profile.id)

    # Gọi API
    resp = client.get(
        "/api/v1/vias/ads-check",
        params={"tab": "personal", "via_id": sample_via_profile.id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tab"] == "personal"
    assert data["total_count"] >= 3
    assert "summary" in data
    assert "items" in data
    assert len(data["items"]) >= 3


def test_api_quick_actions_endpoints(client, db, sample_via_profile, sample_customer):
    """Kiểm thử các endpoints Quick Action của Left Sub-Menu."""
    sync_via_all_assets(session=db, via_id=sample_via_profile.id)
    acc = db.scalars(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == sample_via_profile.id)).first()
    assert acc is not None
    real_act_id = acc.act_id

    # 1. POST /api/v1/vias/ads-check/remove-hidden-admins
    resp_clean = client.post(
        "/api/v1/vias/ads-check/remove-hidden-admins",
        json={"account_ids": [real_act_id, "37088997702"]},
    )
    assert resp_clean.status_code == 200
    assert resp_clean.json()["cleaned_count"] == 2

    # 2. POST /api/v1/vias/ads-check/rename-accounts
    resp_rename = client.post(
        "/api/v1/vias/ads-check/rename-accounts",
        json={"account_ids": [real_act_id], "prefix": "[TEST]"},
    )
    assert resp_rename.status_code == 200
    assert resp_rename.json()["updated_count"] == 1

    # 3. POST /api/v1/vias/ads-check/share-pixel
    resp_pixel = client.post(
        "/api/v1/vias/ads-check/share-pixel",
        json={"pixel_id": "999888777", "target_account_ids": [real_act_id]},
    )
    assert resp_pixel.status_code == 200
    assert resp_pixel.json()["pixel_id"] == "999888777"

    # 4. POST /api/v1/vias/ads-check/super-share-ads
    resp_share = client.post(
        "/api/v1/vias/ads-check/super-share-ads",
        json={
            "client_id": sample_customer.id,
            "account_ids": [real_act_id],
            "role": "EMPLOYEE",
            "access_type": "FULL",
        },
    )
    assert resp_share.status_code == 200
    assert resp_share.json()["saved_preferences"] is True
