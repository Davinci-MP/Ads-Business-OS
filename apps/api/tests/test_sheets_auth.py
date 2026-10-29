"""Kiểm thử xác thực Google Sheets — service account google-auth (D-034, chỉ đọc).

Không dùng credentials thật; token/service account chỉ qua env, không log, không lộ.
"""

import sys
from types import SimpleNamespace

import pytest

from app.connectors.sheets import (
    ACCESS_TOKEN_ENV,
    GOOGLE_APP_CREDENTIALS_ENV,
    SERVICE_ACCOUNT_FILE_ENV,
    SERVICE_ACCOUNT_JSON_ENV,
    SPREADSHEET_ID_ENV,
    GoogleSheetsConnector,
    SheetsAuthError,
    _ServiceAccountTokenProvider,
    build_connector,
    service_account_configured,
)
from app.main import app
from app.db import get_db

_AUTH_ENVS = (ACCESS_TOKEN_ENV, SERVICE_ACCOUNT_FILE_ENV, SERVICE_ACCOUNT_JSON_ENV, GOOGLE_APP_CREDENTIALS_ENV, SPREADSHEET_ID_ENV)


def _clear_auth_env(monkeypatch):
    for name in _AUTH_ENVS:
        monkeypatch.delenv(name, raising=False)


def test_sa_configured_detection(monkeypatch):
    _clear_auth_env(monkeypatch)
    assert service_account_configured() is False
    monkeypatch.setenv(SERVICE_ACCOUNT_FILE_ENV, "C:/secrets/sa.json")
    assert service_account_configured() is True
    monkeypatch.delenv(SERVICE_ACCOUNT_FILE_ENV)
    monkeypatch.setenv(GOOGLE_APP_CREDENTIALS_ENV, "C:/secrets/sa2.json")
    assert service_account_configured() is True


def test_build_connector_auth_resolution(monkeypatch):
    _clear_auth_env(monkeypatch)
    connector = build_connector()
    assert connector.mode == "mock"
    assert connector.auth_method == "none"

    monkeypatch.setenv(ACCESS_TOKEN_ENV, "S3cret-Token-XYZ")
    monkeypatch.setenv(SPREADSHEET_ID_ENV, "sheet_id_x")
    connector = build_connector()
    assert connector.mode == "live"
    assert connector.auth_method == "access_token"
    assert "S3cret-Token-XYZ" not in repr(connector)

    for name in (ACCESS_TOKEN_ENV,):
        monkeypatch.delenv(name)
    monkeypatch.setenv(SERVICE_ACCOUNT_FILE_ENV, "C:/secrets/sa.json")
    connector = build_connector()
    assert connector.mode == "live"
    assert connector.auth_method == "service_account"
    assert "sa.json" not in repr(connector)  # không lộ đường dẫn key qua repr/log


class FakeCreds:
    def __init__(self):
        self.token = None
        self._valid = False
        self.refresh_count = 0

    @property
    def valid(self):
        return self._valid and self.token is not None

    def refresh(self, request):
        self.refresh_count += 1
        self.token = f"tok{self.refresh_count}"
        self._valid = True


def test_sa_provider_refresh_flow(monkeypatch):
    fake = FakeCreds()
    provider = _ServiceAccountTokenProvider()
    monkeypatch.setattr(provider, "_load", lambda: fake)
    import types

    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", types.SimpleNamespace(Request=lambda: None))

    assert provider.bearer_token() == "tok1"
    assert fake.refresh_count == 1
    assert provider.bearer_token() == "tok1"  # còn hạn → không refresh lại
    assert fake.refresh_count == 1
    fake._valid = False  # hết hạn
    assert provider.bearer_token() == "tok2"
    assert fake.refresh_count == 2


def test_sa_provider_load_missing_file(monkeypatch):
    monkeypatch.setenv(SERVICE_ACCOUNT_FILE_ENV, "C:/nonexistent-sa-does-not-exist.json")
    provider = _ServiceAccountTokenProvider()
    with pytest.raises(SheetsAuthError) as excinfo:
        provider.bearer_token()
    assert "không đọc được" in str(excinfo.value)
    assert "C:/nonexistent" not in str(excinfo.value)  # không lộ đường dẫn key trong lỗi


def test_sa_provider_load_json_env(monkeypatch):
    import json
    import types

    import app.connectors.sheets as sheets_module

    _clear_auth_env(monkeypatch)
    monkeypatch.setenv(
        SERVICE_ACCOUNT_JSON_ENV, json.dumps({"type": "service_account", "project_id": "proj", "client_email": "x@proj.iam"})
    )
    captured: dict = {}

    class FakeSACreds:
        def __init__(self):
            self.token = None
            self.valid = False

        def refresh(self, request):
            self.token = "sa-token"
            self.valid = True

    def fake_from_info(info, scopes=None):
        captured["info"] = info
        captured["scopes"] = scopes
        return FakeSACreds()

    def fake_from_file(*_args, **_kwargs):
        raise AssertionError("json env phải dùng from_service_account_info, không phải file")

    fake_sa_module = types.SimpleNamespace(
        Credentials=types.SimpleNamespace(from_service_account_info=fake_from_info, from_service_account_file=fake_from_file)
    )
    monkeypatch.setitem(sys.modules, "google.oauth2", types.SimpleNamespace(service_account=fake_sa_module))
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", fake_sa_module)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", types.SimpleNamespace(Request=lambda: None))

    provider = _ServiceAccountTokenProvider()
    assert provider.bearer_token() == "sa-token"
    assert captured["scopes"] == [sheets_module.SHEETS_READONLY_SCOPE]
    assert captured["info"]["project_id"] == "proj"
    assert "x@proj.iam" != "sa-token"  # không dùng email service account làm token


def test_mode_endpoint_reports_auth(monkeypatch):
    _clear_auth_env(monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/api/v1/sheets/mode")
    assert response.status_code == 200
    data = response.json()
    assert data == {"mode": "mock", "spreadsheet_id_configured": False, "auth": "none"}


def test_analyze_without_any_auth_returns_400(monkeypatch):
    _clear_auth_env(monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.post(
        "/api/v1/sheets/analyze",
        json={"spreadsheet": "https://docs.google.com/spreadsheets/d/1AbC_def-GHIJKLmnopQRs_tuV/edit"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "ADSOS_GOOGLE_SERVICE_ACCOUNT_FILE" in detail or "ADSOS_GOOGLE_SHEETS_ACCESS_TOKEN" in detail


def test_analyze_with_sa_env_but_bad_file_returns_401(monkeypatch):
    monkeypatch.setenv(SERVICE_ACCOUNT_FILE_ENV, "C:/nonexistent-sa-does-not-exist.json")
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.post(
        "/api/v1/sheets/analyze",
        json={"spreadsheet": "https://docs.google.com/spreadsheets/d/1AbC_def-GHIJKLmnopQRs_tuV/edit"},
    )
    assert response.status_code == 401
    assert "không đọc được" in response.json()["detail"]
