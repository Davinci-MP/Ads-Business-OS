"""Kiểm thử tính năng ADSOS CHECK & 1-Click Chrome VIA Profile Launcher + Full Toolbox."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.customer import Customer
from app.models.via import SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.chrome_launcher import (
    build_extension_bootstrap,
    find_system_browser,
    launch_chrome_for_via,
    resolve_asset_via,
    resolve_target_url,
)
from app.services.via_manager import (
    create_or_update_via,
    decrypt_via_credentials,
    export_adsos_check_data,
    extended_payment_action,
    get_ads_check_explorer_data,
    is_real_facebook_cookie,
    parse_via_string_line,
    remove_hidden_admins_action,
    rename_accounts_action,
    save_synced_browser_cookie,
    share_pixel_action,
    super_share_ads_action,
    super_target_action,
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
def seed_via_and_assets(db):
    """Tạo VIA và tài sản kiểm thử để chạy tests."""
    via = create_or_update_via(
        session=db,
        uid="100088997711223",
        password="TestViaPassword123",
        profile_name="VIA-TEST-LAUNCHER",
        two_fa_secret="JBSWY3DPEHPK3PXP",
        email="testvia_launcher@domain.com",
        proxy_config="103.152.118.25:8080:proxyuser:proxypass",
        cookie="c_user=100088997711223; xs=mock_xs_test; fr=mock_fr_test; datr=mock_datr_test",
        access_token="EAAB1000889977XwZ9M8TESTTOKEN123",
    )
    db.commit()

    # Đồng bộ tài sản
    sync_res = sync_via_all_assets(db, via_id=via.id)
    assert sync_res["success"] is True

    yield via

    # Teardown
    db.query(SyncedAdAccount).filter(SyncedAdAccount.via_profile_id == via.id).delete()
    db.query(SyncedBM).filter(SyncedBM.via_profile_id == via.id).delete()
    db.query(SyncedPage).filter(SyncedPage.via_profile_id == via.id).delete()
    db.delete(via)
    db.commit()


@pytest.fixture(autouse=True)
def mock_browser_process(monkeypatch):
    """Không mở trình duyệt thật hoặc đăng nhập tài khoản khi chạy pytest."""
    from unittest.mock import Mock
    from app.services import chrome_launcher
    monkeypatch.setattr(chrome_launcher, "find_system_browser", lambda: "test-browser.exe")
    monkeypatch.setattr(chrome_launcher.subprocess, "Popen", Mock(return_value=Mock(pid=123)))
    monkeypatch.setattr(chrome_launcher, "initialize_browser_session", Mock())


# ==============================================================================
# 1. TEST BROWSER DETECTION & EXTENSION BOOTSTRAP GENERATION
# ==============================================================================

def test_find_system_browser():
    browser = find_system_browser()
    # Trên Windows hoặc Linux, hàm trả về string hoặc None nếu chạy trong container tối giản
    if browser:
        assert isinstance(browser, str)
        assert Path(browser).exists()


def test_build_extension_bootstrap(tmp_path):
    ext_dir = tmp_path / "test_adsos_ext"
    creds = {
        "uid": "1000998877",
        "password": "SecretPassword",
        "email": "test@mail.com",
    }
    raw_cookie = "c_user=1000998877; xs=abc123xs; fr=testfr; datr=datr123"
    proxy_info = {"protocol": "http", "host": "1.2.3.4", "port": 8080, "display": "1.2.3.4:8080"}

    build_extension_bootstrap(
        ext_dir=ext_dir,
        via_uid="1000998877",
        profile_name="VIA-001",
        raw_cookie=raw_cookie,
        creds=creds,
        totp_code="123456",
        proxy_info=proxy_info,
    )

    manifest_file = ext_dir / "manifest.json"
    bg_file = ext_dir / "background.js"
    content_file = ext_dir / "content.js"

    assert manifest_file.exists()
    assert bg_file.exists()
    assert content_file.exists()

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    assert manifest_data["manifest_version"] == 3
    assert "metaOs Helper" in manifest_data["name"]

    bg_content = bg_file.read_text(encoding="utf-8")
    assert "c_user" in bg_content
    assert "abc123xs" in bg_content

    content_text = content_file.read_text(encoding="utf-8")
    assert "metaOs" in content_text
    assert "123456" in content_text


# ==============================================================================
# 2. TEST TARGET URL & ASSET RESOLUTION
# ==============================================================================

def test_resolve_target_url():
    # Ads Manager
    url1 = resolve_target_url("ADS_MANAGER", act_id="123456789")
    assert url1 == "https://adsmanager.facebook.com/adsmanager/manage/campaigns?act=123456789"

    # Billing
    url2 = resolve_target_url("BILLING", act_id="123456789")
    assert url2 == "https://business.facebook.com/billing_hub/payment_settings?asset_id=123456789"

    # BM Settings
    url3 = resolve_target_url("BM_SETTINGS", bm_id="998877")
    assert url3 == "https://business.facebook.com/settings/ad-accounts?business_id=998877"

    # Fanpage
    url4 = resolve_target_url("PAGE", page_id="PAGE_112233")
    assert url4 == "https://www.facebook.com/PAGE_112233"

    # FB Home fallback
    url5 = resolve_target_url("FB_HOME")
    assert url5 == "https://adsmanager.facebook.com/adsmanager/manage/accounts"


def test_resolve_asset_via(db, seed_via_and_assets):
    via = seed_via_and_assets
    # Lấy 1 ad account của via
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id).limit(1))
    assert acc is not None

    resolved_via, resolved_type, asset_id = resolve_asset_via(session=db, act_id=acc.act_id)
    assert resolved_via.id == via.id
    assert resolved_type == "AD_ACCOUNT"
    assert asset_id == acc.act_id


# ==============================================================================
# 3. TEST LAUNCH CHROME SERVICE & ENDPOINT
# ==============================================================================

def test_launch_chrome_for_via_service(db, seed_via_and_assets):
    via = seed_via_and_assets
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id).limit(1))

    res = launch_chrome_for_via(
        session=db,
        via_id=via.id,
        act_id=acc.act_id,
        target_type="ADS_MANAGER",
    )
    assert res["success"] is True
    assert res["via_uid"] == via.uid
    assert "adsmanager.facebook.com" in res["target_url"]
    assert f"act={acc.act_id}" in res["target_url"]
    assert "via_" in res["profile_dir"]
    from app.services import chrome_launcher
    command = chrome_launcher.subprocess.Popen.call_args.args[0]
    assert "--remote-debugging-address=127.0.0.1" in command
    assert any(arg.startswith("--remote-debugging-port=") for arg in command)
    assert any("adsmanager.facebook.com" in arg for arg in command)
    assert any("--load-extension=" in arg for arg in command)
    assert not any("favicon.ico" in arg for arg in command)


def test_launch_failure_is_reported(db, seed_via_and_assets, monkeypatch):
    from unittest.mock import Mock
    from app.services import chrome_launcher
    monkeypatch.setattr(chrome_launcher, "initialize_browser_session", Mock(side_effect=TimeoutError()))
    with pytest.raises(ValueError, match="Không khởi tạo"):
        launch_chrome_for_via(db, via_id=seed_via_and_assets.id)


def test_missing_browser_is_reported(db, seed_via_and_assets, monkeypatch):
    from app.services import chrome_launcher
    monkeypatch.setattr(chrome_launcher, "find_system_browser", lambda: None)
    with pytest.raises(ValueError, match="Không tìm thấy Chrome/Edge"):
        launch_chrome_for_via(db, via_id=seed_via_and_assets.id)


def test_open_in_via_endpoint(client, db, seed_via_and_assets):
    via = seed_via_and_assets
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id).limit(1))

    resp = client.post(
        "/api/v1/vias/ads-check/open-in-via",
        json={
            "act_id": acc.act_id,
            "target_type": "ADS_MANAGER",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["via_uid"] == via.uid
    assert f"act={acc.act_id}" in data["target_url"]


def test_launch_via_browser_endpoint(client, seed_via_and_assets):
    via = seed_via_and_assets
    resp = client.post(
        f"/api/v1/vias/{via.id}/launch-browser",
        json={"target_type": "FB_HOME"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["via_id"] == via.id


# ==============================================================================
# 4. TEST EXTENDED PAYMENT ACTIONS
# ==============================================================================

def test_extended_payment_actions(db, seed_via_and_assets):
    via = seed_via_and_assets
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id).limit(1))
    assert acc is not None

    # 1. PAY_NOW
    acc.balance = 5000000.0
    acc.disable_reason = "UNSETTLED"
    db.commit()

    res_pay = extended_payment_action(
        session=db,
        account_ids=[acc.act_id],
        action="PAY_NOW",
        amount=5000000.0,
    )
    assert res_pay["success"] is True
    db.refresh(acc)
    assert acc.balance == 0.0
    assert acc.disable_reason == "NONE"

    # 2. SET_PRIMARY_CARD
    res_card = extended_payment_action(
        session=db,
        account_ids=[acc.act_id],
        action="SET_PRIMARY_CARD",
        card_brand="MASTERCARD",
        card_last4="4321",
    )
    assert res_card["success"] is True
    db.refresh(acc)
    assert acc.payment_card_brand == "MASTERCARD"
    assert acc.payment_card_last4 == "4321"

    # 3. FETCH_INVOICES
    res_inv = extended_payment_action(
        session=db,
        account_ids=[acc.act_id],
        action="FETCH_INVOICES",
    )
    assert res_inv["success"] is True
    assert len(res_inv["invoices"]) == 1
    assert res_inv["invoices"][0]["act_id"] == acc.act_id


# ==============================================================================
# 5. TEST RENAME ACCOUNTS EXTENDED (TIMEZONE, TAX, COUNTRY, TEMPLATE)
# ==============================================================================

def test_rename_accounts_extended(db, seed_via_and_assets):
    via = seed_via_and_assets
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id).limit(1))

    res = rename_accounts_action(
        session=db,
        account_ids=[acc.act_id],
        prefix="[VIP]",
        suffix="- 2024",
        new_name="Campaign Brand {index}",
        currency="USD",
        timezone_name="Asia/Bangkok | GMT+7",
        country_code="TH",
        tax_status="ĐÃ KHAI THUẾ",
    )
    assert res["success"] is True
    db.refresh(acc)
    assert "[VIP]" in acc.name
    assert "- 2024" in acc.name
    assert "01" in acc.name
    assert acc.currency == "USD"
    assert acc.timezone_name == "Asia/Bangkok | GMT+7"
    assert acc.country_code == "TH"
    assert acc.tax_status == "ĐÃ KHAI THUẾ"


# ==============================================================================
# 6. TEST SHARE PIXEL & REMOVE HIDDEN ADMINS
# ==============================================================================

def test_share_pixel_and_remove_hidden_admins(db, seed_via_and_assets):
    via = seed_via_and_assets
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id).limit(1))

    # Gán admin ẩn
    acc.hidden_admin_count = 3
    db.commit()

    # Gỡ admin ẩn
    res_clean = remove_hidden_admins_action(session=db, account_ids=[acc.act_id])
    assert res_clean["success"] is True
    db.refresh(acc)
    assert acc.hidden_admin_count == 0

    # Share Pixel
    res_pixel = share_pixel_action(session=db, pixel_id="998877665544", target_account_ids=[acc.act_id])
    assert res_pixel["success"] is True
    db.refresh(acc)
    assert acc.pixel_id == "998877665544"


# ==============================================================================
# 7. TEST SUPER TARGET & APPEAL
# ==============================================================================

def test_super_target_and_appeal(db, seed_via_and_assets):
    via = seed_via_and_assets
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id).limit(1))

    # Search interests
    res_kw = super_target_action(session=db, keyword="bất động sản", action="SEARCH_INTERESTS")
    assert res_kw["success"] is True
    assert len(res_kw["interests"]) > 0

    # Appeal account
    acc.status_dot = "DIE"
    db.commit()

    res_appeal = super_target_action(
        session=db,
        action="APPEAL_ACCOUNT",
        account_ids=[acc.act_id],
        appeal_reason="Đề nghị mở lại TKQC.",
    )
    assert res_appeal["success"] is True
    db.refresh(acc)
    assert acc.status_dot == "WARNING"


# ==============================================================================
# 8. TEST ADSOS CHECK EXPORT (CSV & TXT)
# ==============================================================================

def test_ads_check_export(client, db, seed_via_and_assets):
    via = seed_via_and_assets

    # Direct function export CSV
    csv_res = export_adsos_check_data(session=db, tab="personal", via_id=via.id, format_type="csv")
    assert csv_res["filename"].endswith(".csv")
    assert "ID Tài Khoản" in csv_res["content"]
    assert via.uid in csv_res["content"]

    # Direct function export TXT
    txt_res = export_adsos_check_data(session=db, tab="group", via_id=via.id, format_type="txt")
    assert txt_res["filename"].endswith(".txt")
    assert "ID BM" in txt_res["content"]

    # Endpoint export
    resp = client.get(f"/api/v1/vias/ads-check/export?tab=personal&via_id={via.id}&format_type=csv")
    assert resp.status_code == 200
    assert "attachment; filename=" in resp.headers.get("content-disposition", "")


# ==============================================================================
# 9. TEST REAL FACEBOOK COOKIE DETECTION, MULTI-POSITION PARSING & SYNC
# ==============================================================================

def test_is_real_facebook_cookie():
    # 1. Cookie Facebook thật chuẩn
    real_cookie = "c_user=100088997711223; xs=34%3Aj7aK98L2xP01mQ%3A2%3A1715420000%3A-1%3A-1; datr=xYz1234567890; fr=0abc123def456;"
    assert is_real_facebook_cookie(real_cookie) is True

    # 2. Cookie giả lập / mock
    assert is_real_facebook_cookie("c_user=100088997711223; xs=mock_xs_test; fr=mock_fr;") is False
    assert is_real_facebook_cookie("c_user=100088997711223; xs=simulated_test; fr=fr;") is False
    assert is_real_facebook_cookie("c_user=100088997711223; xs=placeholder; fr=fr;") is False

    # 3. Cookie thiếu trường hoặc quá ngắn
    assert is_real_facebook_cookie("c_user=100088997711223; datr=xYz123;") is False
    assert is_real_facebook_cookie("xs=34%3Aj7aK98L2xP01mQ;") is False
    assert is_real_facebook_cookie("c_user=100088997711223; xs=short;") is False
    assert is_real_facebook_cookie("") is False
    assert is_real_facebook_cookie(None) is False


def test_flexible_multi_position_via_parsing():
    # Trường hợp 1: Token và Cookie ở vị trí pipe 3 & 4
    line1 = "100012345678|PassWord123|c_user=100012345678; xs=real_session_token_1234567890;|EAABw1234567890abcdef1234567890"
    p1 = parse_via_string_line(line1)
    assert p1 is not None
    assert p1["uid"] == "100012345678"
    assert p1["password"] == "PassWord123"
    assert "c_user=" in p1["cookie"]
    assert p1["access_token"].startswith("EAAB")

    # Trường hợp 2: 2FA trước Cookie và Token
    line2 = "100012345678|PassWord123|JBSWY3DPEHPK3PXP|c_user=100012345678; xs=real_session_token_1234567890;|EAAG1234567890abcdef1234567890"
    p2 = parse_via_string_line(line2)
    assert p2 is not None
    assert p2["two_fa_secret"] == "JBSWY3DPEHPK3PXP"
    assert "c_user=" in p2["cookie"]
    assert p2["access_token"].startswith("EAAG")

    # Trường hợp 3: Mail trước 2FA
    line3 = "100012345678|PassWord123|agency@domain.com|JBSWY3DPEHPK3PXP|MailPass123"
    p3 = parse_via_string_line(line3)
    assert p3 is not None
    assert p3["email"] == "agency@domain.com"
    assert p3["two_fa_secret"] == "JBSWY3DPEHPK3PXP"
    assert p3["email_password"] == "MailPass123"


def test_two_way_cookie_sync_endpoint(client, db, seed_via_and_assets):
    via = seed_via_and_assets
    real_cookie_payload = "c_user=100088997711223; xs=99%3AxYzRealFacebookSessionXs123456; datr=live_datr_123; fr=live_fr_123"

    resp = client.post(
        f"/api/v1/vias/{via.id}/sync-browser-cookie",
        json={"cookie": real_cookie_payload},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["token_status"] == "ACTIVE"
    assert data["uid_live_status"] == "LIVE"

    # Kiểm tra đã lưu vào DB trong vault mã hóa Fernet
    db.refresh(via)
    assert via.token_status == "ACTIVE"
    assert via.uid_live_status == "LIVE"
    creds = decrypt_via_credentials(via.encrypted_credentials)
    assert creds["cookie"] == real_cookie_payload


def test_launch_chrome_bootstrap_url_logic(db, seed_via_and_assets):
    via = seed_via_and_assets
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id).limit(1))

    # Khi via chỉ có mock_cookie (seed_via_and_assets có mock_xs):
    res_mock = launch_chrome_for_via(
        session=db,
        via_id=via.id,
        act_id=acc.act_id,
        target_type="ADS_MANAGER",
    )
    assert res_mock["has_real_cookie"] is False
    assert "adsmanager.facebook.com" in res_mock["bootstrap_url"]
    assert "adsmanager.facebook.com" in res_mock["target_url"]

    # Cập nhật via có cookie thật
    save_synced_browser_cookie(
        session=db,
        via=via,
        raw_cookie="c_user=100088997711223; xs=34%3Aj7aK98L2xP01mQ%3A2%3A1715420000%3A-1%3A-1; datr=xYz1234567890; fr=0abc123def456;",
    )
    db.refresh(via)

    res_real = launch_chrome_for_via(
        session=db,
        via_id=via.id,
        act_id=acc.act_id,
        target_type="ADS_MANAGER",
    )
    assert res_real["has_real_cookie"] is True
    assert res_real["bootstrap_url"] == res_real["target_url"]
    assert "adsmanager.facebook.com" in res_real["target_url"]


# ==============================================================================
# 9. UNIT TESTS: INLINE PROFILE & NOTE EDITING, HEADLESS AUTO-LOGIN & ZERO FAVICON
# ==============================================================================

def test_patch_via_profile_name_and_note(client, db, seed_via_and_assets):
    via = seed_via_and_assets
    # 1. PATCH profile_name & note
    resp = client.patch(
        f"/api/v1/vias/{via.id}",
        json={
            "profile_name": "VIA Cầm BM Tổng - Minh",
            "note": "Nuôi từ 2024, chuyên chạy thời trang",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["via"]["profile_name"] == "VIA Cầm BM Tổng - Minh"
    assert data["via"]["note"] == "Nuôi từ 2024, chuyên chạy thời trang"

    # 2. PUT profile_name, note & proxy_url
    resp_put = client.put(
        f"/api/v1/vias/{via.id}",
        json={
            "profile_name": "VIA Agency VIP 01",
            "note": "BM 2500$ NOLIMIT",
            "proxy_url": "103.152.118.99:8080:user:pass",
        },
    )
    assert resp_put.status_code == 200
    put_data = resp_put.json()
    assert put_data["via"]["profile_name"] == "VIA Agency VIP 01"
    assert put_data["via"]["note"] == "BM 2500$ NOLIMIT"

    # 3. Kiểm tra DB lưu trữ chính xác
    db.refresh(via)
    assert via.profile_name == "VIA Agency VIP 01"
    assert via.note == "BM 2500$ NOLIMIT"
    assert "103.152.118.99" in via.proxy_config


def test_headless_login_and_extract_flow(db):
    from app.services.chrome_launcher import get_via_profile_dir
    from app.services.via_manager import headless_login_and_extract
    via = create_or_update_via(
        session=db,
        uid="100099887766554",
        password="ValidPassword123!",
        profile_name="VIA-EXPIRED-TEST",
        two_fa_secret="JBSWY3DPEHPK3PXP",
    )
    via.token_status = "EXPIRED"
    via.uid_live_status = "UNKNOWN"
    db.commit()

    res = headless_login_and_extract(session=db, via_id=via.id)
    assert res["success"] is True
    assert res["token_status"] == "ACTIVE"
    assert res["uid_live_status"] == "LIVE"

    # Kiểm tra DB lưu trữ credentials và trạng thái ACTIVE
    db.refresh(via)
    assert via.token_status == "ACTIVE"
    assert via.uid_live_status == "LIVE"
    creds = decrypt_via_credentials(via.encrypted_credentials)
    assert "c_user=100099887766554" in creds["cookie"]
    assert "xs=" in creds["cookie"]
    assert creds["access_token"].startswith("EAAB") or creds["access_token"].startswith("EAAG")

    # Kiểm tra tự động phát hiện tài sản (Asset Discovery)
    assert via.bm_count > 0 or via.ad_account_count > 0

    # Kiểm tra extension đã được sinh sẵn trong thư mục profile độc lập
    p_dir = get_via_profile_dir(via.uid)
    ext_dir = p_dir / "adsos_helper_ext"
    assert (ext_dir / "manifest.json").exists()
    assert (ext_dir / "background.js").exists()
    assert (ext_dir / "content.js").exists()

    # Dọn dẹp
    db.query(SyncedAdAccount).filter(SyncedAdAccount.via_profile_id == via.id).delete()
    db.query(SyncedBM).filter(SyncedBM.via_profile_id == via.id).delete()
    db.query(SyncedPage).filter(SyncedPage.via_profile_id == via.id).delete()
    db.delete(via)
    db.commit()


def test_chrome_launcher_regenerates_extension_zero_favicon(db, seed_via_and_assets):
    via = seed_via_and_assets
    from app.services.chrome_launcher import get_via_profile_dir
    p_dir = get_via_profile_dir(via.uid)
    ext_dir = p_dir / "adsos_helper_ext"
    ext_dir.mkdir(parents=True, exist_ok=True)

    # Đặt file rác mô phỏng extension cũ bị lỗi favicon
    dirty_file = ext_dir / "favicon.ico"
    dirty_file.write_text("old favicon data", encoding="utf-8")
    assert dirty_file.exists()

    # Khởi chạy Chrome
    res = launch_chrome_for_via(
        session=db,
        via_id=via.id,
        target_type="ADS_MANAGER",
    )
    assert res["success"] is True

    # Kiểm tra file rác đã bị dọn dẹp sạch sẽ
    assert not dirty_file.exists()

    # Kiểm tra tất cả các file trong ext_dir không chứa bất kỳ URL favicon.ico nào
    manifest_txt = (ext_dir / "manifest.json").read_text(encoding="utf-8")
    bg_txt = (ext_dir / "background.js").read_text(encoding="utf-8")
    content_txt = (ext_dir / "content.js").read_text(encoding="utf-8")

    assert "favicon.ico" not in manifest_txt
    assert "favicon.ico" not in bg_txt
    assert "favicon.ico" not in content_txt
    assert "adsos_boot=1" not in bg_txt

    from app.services import chrome_launcher
    command = chrome_launcher.subprocess.Popen.call_args.args[0]
    assert not any("favicon.ico" in arg for arg in command)
    assert any("--load-extension=" in arg for arg in command)
    assert any("adsmanager.facebook.com" in arg for arg in command)
