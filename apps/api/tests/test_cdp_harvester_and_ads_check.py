"""Tests for CDP Harvester, Manual Credentials Endpoint, and Live Asset Sync."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.via import SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.chrome_launcher import (
    get_via_debug_port,
    harvest_from_running_chrome_cdp,
    launch_chrome_for_via,
    save_harvested_session_to_via,
)
from app.services.via_manager import (
    create_or_update_via,
    decrypt_via_credentials,
    extract_tokens_from_cookie,
    harvest_session_from_profile_or_cdp,
    sync_via_all_assets,
)


@pytest.fixture(autouse=True)
def mock_browser_process(monkeypatch):
    """Không mở trình duyệt thật hoặc đăng nhập tài khoản khi chạy pytest."""
    from app.services import chrome_launcher
    monkeypatch.setattr(chrome_launcher, "find_system_browser", lambda: "test-browser.exe")
    monkeypatch.setattr(chrome_launcher.subprocess, "Popen", Mock(return_value=Mock(pid=123)))
    monkeypatch.setattr(chrome_launcher, "initialize_browser_session", Mock())


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app, base_url="http://127.0.0.1")
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def via_test_profile(db):
    from app.services.via_manager import encrypt_via_credentials
    profile = db.scalar(select(ViaProfile).where(ViaProfile.uid == "999888777666555"))
    if not profile:
        profile = create_or_update_via(
            session=db,
            uid="999888777666555",
            password="TestSecretPassword123",
            profile_name="VIA-CDP-TEST",
            two_fa_secret="JBSWY3DPEHPK3PXP",
        )
    profile.encrypted_credentials = encrypt_via_credentials({
        "password": "TestSecretPassword123",
        "two_fa_secret": "JBSWY3DPEHPK3PXP",
        "cookie": "",
        "access_token": "",
    })
    profile.token_status = "EXPIRED"
    profile.uid_live_status = "UNKNOWN"
    db.commit()
    db.refresh(profile)
    return profile


def test_get_via_debug_port():
    assert get_via_debug_port(0) == 9222
    assert get_via_debug_port(1) == 9223
    assert get_via_debug_port(500) == 9222
    assert get_via_debug_port(501) == 9223
    assert 9222 <= get_via_debug_port(12345) < 9722


def test_launch_chrome_includes_deterministic_debug_port(db, via_test_profile):
    via = via_test_profile
    expected_port = get_via_debug_port(via.id)

    res = launch_chrome_for_via(
        session=db,
        via_id=via.id,
        target_type="FB_HOME",
    )
    assert res["success"] is True
    assert res["debug_port"] == expected_port

    from app.services import chrome_launcher
    command = chrome_launcher.subprocess.Popen.call_args.args[0]
    assert "--remote-debugging-address=127.0.0.1" in command
    assert f"--remote-debugging-port={expected_port}" in command
    assert "--remote-debugging-port=0" not in command
    assert "--remote-allow-origins=*" in command


def test_manual_credentials_endpoint(client, db, via_test_profile):
    via = via_test_profile
    real_cookie = "c_user=100088402955133; xs=99%3AxYzRealFacebookSessionXs123456; datr=datr_val_123; fr=fr_val_123;"
    real_token = "EAABtestManualAccessToken1234567890"

    resp = client.post(
        f"/api/v1/vias/{via.id}/manual-credentials",
        json={
            "cookie": real_cookie,
            "access_token": real_token,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["token_status"] == "ACTIVE"
    assert data["uid_live_status"] == "LIVE"
    assert "Đã lưu thông tin đăng nhập" in data["message"]

    db.refresh(via)
    assert via.token_status == "ACTIVE"
    assert via.uid_live_status == "LIVE"
    creds = decrypt_via_credentials(via.encrypted_credentials)
    assert creds["cookie"] == real_cookie
    assert creds["access_token"] == real_token


def test_manual_credentials_empty_payload_rejected(client, via_test_profile):
    via = via_test_profile
    resp = client.post(
        f"/api/v1/vias/{via.id}/manual-credentials",
        json={"cookie": "", "access_token": ""},
    )
    assert resp.status_code == 400
    assert "Vui lòng cung cấp ít nhất" in resp.json()["detail"]


def test_harvest_session_endpoint(client, db, via_test_profile):
    via = via_test_profile

    # Khi Chrome chưa mở và chưa có session hợp lệ
    resp = client.post(f"/api/v1/vias/{via.id}/harvest-session")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False, f"source={data.get('source')}, msg={data.get('message')}"
    assert "Chưa phát hiện" in data["message"] or "Không kết nối được" in data["message"]

    # Nạp session hợp lệ vào vault rồi gọi harvest
    real_cookie = "c_user=100088402955133; xs=99%3AxYzRealFacebookSessionXs123456; datr=datr_val_123; fr=fr_val_123;"
    creds = decrypt_via_credentials(via.encrypted_credentials)
    creds["cookie"] = real_cookie
    from app.services.via_manager import encrypt_via_credentials
    via.encrypted_credentials = encrypt_via_credentials(creds)
    db.commit()

    resp_valid = client.post(f"/api/v1/vias/{via.id}/harvest-session")
    assert resp_valid.status_code == 200
    data_valid = resp_valid.json()
    assert data_valid["success"] is True
    assert data_valid["token_status"] == "ACTIVE"
    assert data_valid["source"] == "VAULT"


def test_extract_tokens_from_cookie_with_mock_transport():
    html_response = """
    <!DOCTYPE html>
    <html>
      <head>
        <script>
          requireLazy(["DTSGInitialData"], function(d) {
            d.token = "NAcTestLiveDtsgToken12345";
          });
        </script>
      </head>
      <body>
        <div>Meta Ads Manager</div>
        <script>
          window.__accessToken = "EAABLiveTestAccessToken1234567890abcdef";
          var account_data = {"account_id": "123456789", "name": "TKQC Test"};
        </script>
      </body>
    </html>
    """
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_response)

    transport = httpx.MockTransport(mock_handler)
    test_cookie = "c_user=100088402955133; xs=99%3AxYzRealFacebookSessionXs123456; datr=datr_val_123; fr=fr_val_123;"

    token, dtsg, accs = extract_tokens_from_cookie(
        raw_cookie=test_cookie,
        client_transport=transport,
    )
    assert token is not None
    assert token.startswith("EAAB")
    assert len(accs) > 0
    assert accs[0]["act_id"] == "123456789"


def test_sync_via_all_assets_populates_synced_records(db, via_test_profile):
    via = via_test_profile
    res = sync_via_all_assets(db, via_id=via.id, mock_mode=True)
    assert res["success"] is True
    assert res["total_ad_accounts"] > 0
    assert res["bms_synced"] > 0

    db.refresh(via)
    assert via.ad_account_count > 0
    assert via.bm_count > 0

    acts = db.scalars(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id)).all()
    assert len(acts) > 0
    bms = db.scalars(select(SyncedBM).where(SyncedBM.via_profile_id == via.id)).all()
    assert len(bms) > 0
