"""Kết nối sàn Binance (D-056) — chỉ đọc + credentials mã hóa + snapshot append-only.

- Connector: HMAC-SHA256 hex trên query string; timestamp từ /api/v3/time; -1021 re-sync; 429/418; -2014/-2015; timeout→retry.
- Service: verify chặt (canRead && !canTrade && !canWithdraw); master key thiếu → không lưu; credentials chỉ ciphertext.
- API: loopback-only (host lạ → 404); Origin lạ → 403; disclaimers có.
- Idempotency: cùng (connection, wallet, asset, read_at) → không cộng trùng.
"""
from datetime import datetime, timezone

import alembic.command
import alembic.config
import httpx
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db import get_db
from app.main import app
from app.models.exchange import ExchangeBalanceSnapshot, ExchangeCredentials
from app.api.v1.wallets import _guard_local
from app.connectors.binance import (
    BinanceConnector,
    BinanceAuthError,
    BinanceRateLimitError,
    BinanceTransportError,
)
from app.services import exchange_connections as svc


@pytest.fixture
def patch_connector(monkeypatch):
    """Inject HappyTransport vào BinanceConnector của service — chặn gọi mạng thật trong tests."""
    def _factory(**kwargs):
        kwargs.pop("transport", None)
        return BinanceConnector(**kwargs, transport=HappyTransport())

    monkeypatch.setattr(svc, "BinanceConnector", _factory)


API_KEY = "TESTKEY123456"


class AuthFailedTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v3/time":
            return httpx.Response(status_code=200, json={"serverTime": 1770000000000})
        if "apiRestrictions" in path:
            return httpx.Response(status_code=401, json={"code": -2014, "msg": "IP timeout"})
        return httpx.Response(status_code=200, json={"balances": []})


class TimeoutTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("fake timeout")


class TimestampDriftTransport(httpx.BaseTransport):
    """Sync time ban đầu trả serverTime lệch; lần sau trả serverTime chuẩn + gọi được signed."""
    calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        path = request.url.path
        if path == "/api/v3/time":
            if self.calls <= 1:
                return httpx.Response(status_code=200, json={"serverTime": 1})  # mốc lệch quá xa
            return httpx.Response(status_code=200, json={"serverTime": 1770000000000})
        if "restrictions" in path:
            return httpx.Response(status_code=200, json=self._fake_restrictions())
        if "get-funding-asset" in path:
            return httpx.Response(status_code=200, json=self._fake_funding())
        # spot: lần 1 → trả lỗi -1021; lần 2 → OK
        if self.calls == 2:
            return httpx.Response(status_code=400, json={"code": -1021, "msg": "Timestamp outside recvWindow"})
        return httpx.Response(status_code=200, json=self._fake_spot())

    @staticmethod
    def _fake_restrictions() -> dict:
        return {"enableReading": True, "enableSpotAndMarginTrading": False, "enableWithdrawals": False, "permitsUniversalTransfer": False, "enableInternalTransfer": False}

    @staticmethod
    def _fake_spot() -> dict:
        return {"balances": [{"asset": "USDT", "free": "1.5", "locked": "0"}]}

    @staticmethod
    def _fake_funding() -> list[dict]:
        return [{"asset": "USDT", "free": "3.25", "locked": "0", "freeze": "0.5", "withdrawing": "0.1"}]


class HappyTransport(httpx.BaseTransport):
    """Spot 1.5 + Funding 3.25 USDT; dùng chung cho các test API qua monkeypatch svc.BinanceConnector."""
    history: dict[str, int]

    def __init__(self) -> None:  # noqa: D401
        self.history = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        whoami = request.url.path
        self.history[whoami] = self.history.get(whoami, 0) + 1
        path = request.url.path
        if path == "/api/v3/time":
            return httpx.Response(status_code=200, json={"serverTime": 1770000000000})
        if path == "/sapi/v1/account/apiRestrictions":
            return httpx.Response(status_code=200, json={"enableReading": True, "enableSpotAndMarginTrading": False, "enableWithdrawals": False, "permitsUniversalTransfer": False, "enableInternalTransfer": False})
        if path == "/api/v3/account":
            assert "signature=" in str(request.url), "signed query string theo docs"
            return httpx.Response(status_code=200, json={"balances": [{"asset": "USDT", "free": "1.5", "locked": "0"}]})
        if path == "/sapi/v1/asset/get-funding-asset":
            assert request.method == "POST" and "signature=" in str(request.url)
            return httpx.Response(status_code=200, json=[{"asset": "USDT", "free": "3.25", "locked": "0", "freeze": "0.5", "withdrawing": "0.1"}])
        raise AssertionError(path)


@pytest.fixture
def master_key_env(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "exchange_master_key", key)
    return key


@pytest.fixture
def master_missing(monkeypatch):
    monkeypatch.setattr(settings, "exchange_master_key", "")


@pytest.fixture
def db(tmp_path):
    database = tmp_path / "exchange-test.db"
    cfg = alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    alembic.command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(settings, "exchange_admin_token", "test-admin-token-" * 4)
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, headers={"x-adsos-wallet-token": "test-admin-token-" * 4})
    app.dependency_overrides.clear()


GOOD_LABEL = "Binance chính"

_NOW = datetime(2026, 10, 29, 7, 0, tzinfo=timezone.utc)


def test_connector_signature_hex_and_hmac_payload():
    """HMAC-SHA256 trên query string — hex; timestamp + recvWindow."""
    captured: list[str] = []

    def spy(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return HappyTransport().handle_request(request)

    connector = BinanceConnector(
        api_key=API_KEY, api_secret="s3cretVALUE",
        transport=httpx.MockTransport(spy),
    )
    connector.spot_balances()
    assert captured, "spot_balances đã gọi"
    url = captured[-1]
    qs = url.split("?", 1)[1]
    signature = qs.split("signature=")[-1]
    assert len(signature) == 64 and all(ch in "0123456789abcdef" for ch in signature), "hex HMAC-SHA256"
    assert "timestamp=" in qs and "recvWindow=5000" in qs


def test_connector_rate_limit_tries_honor_retry_after():
    """429 (trên spot, sau server-time 200) → BinanceRateLimitError với Retry-After từ header."""

    class TimeOkThen429(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v3/time":
                return httpx.Response(status_code=200, json={"serverTime": 1770000000000})
            return httpx.Response(status_code=429, headers={"Retry-After": "3"}, json={})

    connector = BinanceConnector(api_key=API_KEY, api_secret="xyz", transport=TimeOkThen429())
    with pytest.raises(BinanceRateLimitError) as err:
        connector.spot_balances()
    assert err.value.retry_after_s == 3.0


def test_connector_ip_ban_signal_unit():
    class BadAll(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v3/time":
                return httpx.Response(status_code=200, json={"serverTime": 1770000000000})
            return httpx.Response(status_code=418, json={})

    connector = BinanceConnector(api_key=API_KEY, api_secret="xyz", transport=BadAll())
    with pytest.raises(BinanceRateLimitError):
        connector.spot_balances()


def test_connector_auth_failed_keeps_message_redacted():
    connector = BinanceConnector(api_key="MYKEY", api_secret="MYSECRETXYZ", transport=AuthFailedTransport())
    with pytest.raises(BinanceAuthError) as err:
        connector.api_restrictions()
    assert "MYSECRETXYZ" not in err.value.message and "MYKEY" not in err.value.message


def test_connector_timeout_retries_and_raises_transport():
    connector = BinanceConnector(api_key=API_KEY, api_secret="xyz", transport=TimeoutTransport())
    with pytest.raises(BinanceTransportError):
        connector.spot_balances()


def test_connector_timestamp_drift_retries_once_after_resync():
    """Binance trả -1021 → re-sync server time rồi thử lại một lần (T2-S7)."""
    transport = TimestampDriftTransport()
    connector = BinanceConnector(api_key=API_KEY, api_secret="xyz", transport=transport)
    rows = connector.spot_balances()
    assert rows[0]["asset"] == "USDT"
    assert transport.calls > 2  # cả lần đầu bị lỗi + resync + lần thử lại


def test_verify_strict_read_only_enforced():
    """Verify chặt: canRead True && canTrade False && canWithdraw False — khóa có quyền ghi từ chối."""
    transport = HappyTransport()
    result = svc.verify_connection(API_KEY, "s3cretVALUE", transport=transport)
    assert result["read_only_verified"] is True
    assert result["permissions"]["enableWithdrawals"] is False

    class Writable(HappyTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/sapi/v1/account/apiRestrictions":
                return httpx.Response(status_code=200, json={"enableReading": True, "enableSpotAndMarginTrading": True, "enableWithdrawals": False})
            return super().handle_request(request)

    with pytest.raises(svc.ExchangeVerificationFailed):
        svc.verify_connection(API_KEY, "s3cretVALUE", transport=Writable())

    class NoRead(Writable):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/sapi/v1/account/apiRestrictions":
                return httpx.Response(status_code=200, json={"enableReading": False, "enableSpotAndMarginTrading": False, "enableWithdrawals": False})
            return super().handle_request(request)

    with pytest.raises(svc.ExchangeVerificationFailed):
        svc.verify_connection(API_KEY, "s3cretVALUE", transport=NoRead())


def test_master_key_missing_prevents_save(db, master_missing):
    with pytest.raises(svc.ExchangeMasterKeyMissing):
        svc.save_connection(db, GOOD_LABEL, API_KEY, "s3cretVALUE", transport=HappyTransport())
    assert db.scalars(select(ExchangeCredentials)).first() is None  # không lưu plaintext


def test_save_encrypted_and_list_view_masks(db, master_key_env):
    connection = svc.save_connection(db, GOOD_LABEL, API_KEY, "s3cretVALUE", transport=HappyTransport())
    assert connection.id > 0
    credential = db.scalars(select(ExchangeCredentials)).first()
    assert credential.encrypted_api_key != API_KEY
    assert credential.api_key_last4 == API_KEY[-4:]
    assert "s3cretVALUE" not in repr(credential).lower()

    rows = svc.list_connections(db)
    assert rows[0]["id"] == connection.id
    assert rows[0]["api_key_last4"] == API_KEY[-4:]
    assert "api_key" not in rows[0] and "encrypted_api" not in "".join(rows[0].keys())


def test_read_balances_partially_keeps_other_wallet_data(db, master_key_env):
    """Một ví lỗi → giữ phần thành công, status PARTIAL; 0 giả không tự dán."""
    class FundingDown(HappyTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/sapi/v1/asset/get-funding-asset":
                return httpx.Response(status_code=500, json={})
            return super().handle_request(request)

    connection = svc.save_connection(db, GOOD_LABEL, API_KEY, "s3cretVALUE", transport=HappyTransport())
    db.expire_all()
    row, result = svc.read_balances(db, connection.id, transport=FundingDown(), now=_NOW)
    assert result["status"] == "PARTIAL"
    assert result["wallets"]["spot"]["ok"] is True
    assert result["wallets"]["funding"]["ok"] is False
    snaps = db.scalars(select(ExchangeBalanceSnapshot)).all()
    assert len(snaps) == 1 and snaps[0].wallet_type == "spot" and str(snaps[0].free) == "1.50000000"
    assert "Funding" in (connection.last_error or "") or "funding" in (connection.last_error or "")


def test_read_balances_all_error_keeps_no_snapshot(db, master_key_env):
    class AllDown(HappyTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if request.url.path in ("/sapi/v1/asset/get-funding-asset", "/api/v3/account"):
                return httpx.Response(status_code=503, json={})
            return super().handle_request(request)

    connection = svc.save_connection(db, GOOD_LABEL, API_KEY, "s3cretVALUE", transport=HappyTransport())
    db.expire_all()
    row, result = svc.read_balances(db, connection.id, transport=AllDown(), now=_NOW)
    assert result["status"] == "ERROR"
    snapshot_count = len(db.scalars(select(ExchangeBalanceSnapshot)).all())
    assert snapshot_count == 0
    assert connection.last_error is not None


def test_read_balances_idempotent_same_read_at(db, master_key_env):
    connection = svc.save_connection(db, GOOD_LABEL, API_KEY, "s3cretVALUE", transport=HappyTransport())
    db.expire_all()
    first_connection, first_result = svc.read_balances(db, connection.id, transport=HappyTransport(), now=_NOW)
    _, second_result = svc.read_balances(db, connection.id, transport=HappyTransport(), now=_NOW)
    assert first_connection.last_error is None
    assert second_result["status"] == "OK"
    snapshot_count = len(db.scalars(select(ExchangeBalanceSnapshot)).all())
    assert snapshot_count and snapshot_count <= 2  # không cộng trùng


def test_update_credentials_keeps_secret_if_blank(db, master_key_env):
    connection = svc.save_connection(db, GOOD_LABEL, API_KEY, "s3cretVALUE", transport=HappyTransport())
    credential = db.scalars(select(ExchangeCredentials)).first()
    original_secret_cipher = credential.encrypted_api_secret
    svc.update_credentials(db, connection.id, label="Binance backup")
    credential = db.scalars(select(ExchangeCredentials)).first()
    assert credential.encrypted_api_secret == original_secret_cipher
    assert connection.label == "Binance backup"

    with pytest.raises(svc.ExchangeCredentialsError):
        svc.update_credentials(db, connection.id, api_key="NEWKEY12345678")  # thiếu secret


def test_audit_log_no_secrets(db, master_key_env):
    svc.save_connection(db, GOOD_LABEL, API_KEY, "s3cretVALUE", transport=HappyTransport())
    from app.models.finance import AuditLog
    events = db.scalars(select(AuditLog)).all()
    assert any(e.action == "EXCHANGE_CONNECTION_SAVED" for e in events)
    blob = repr([(e.action, e.detail) for e in events])
    assert API_KEY not in blob and "s3cretVALUE" not in blob


def test_loopback_guard_blocks_remote_origin_and_host(monkeypatch):
    monkeypatch.setattr(settings, "exchange_admin_token", "test-admin-token-" * 4)
    class FakeRequest:
        def __init__(self, host, headers=None):
            self.client = type("C", (), {"host": host})()
            self.headers = dict(headers or {})

    with pytest.raises(HTTPException) as excinfo:
        _guard_local(FakeRequest("8.8.8.8"))
    assert excinfo.value.status_code == 404
    with pytest.raises(HTTPException) as excinfo:
        _guard_local(FakeRequest("203.0.113.5"))
    assert excinfo.value.status_code == 404
    with pytest.raises(HTTPException) as excinfo:
        _guard_local(FakeRequest("127.0.0.1", {"origin": "http://evil.example.com"}))
    assert excinfo.value.status_code == 403
    _guard_local(FakeRequest("127.0.0.1", {"origin": "http://localhost:3000", "x-adsos-wallet-token": "test-admin-token-" * 4}))  # không raise


def test_api_flow_requires_master_key_then_saves(db, client, patch_connector, monkeypatch):
    monkeypatch.setattr(settings, "exchange_master_key", "")
    missing = client.post("/api/v1/exchange/verify", json={"api_key": API_KEY, "api_secret": "s3cretVALUE"})
    assert missing.status_code == 503

    monkeypatch.setattr(settings, "exchange_master_key", Fernet.generate_key().decode())
    saved = client.post("/api/v1/exchange/connections", json={
        "label": GOOD_LABEL, "api_key": API_KEY, "api_secret": "s3cretVALUE"
    })
    assert saved.status_code == 200
    assert saved.json()["saved"] is True

    listed = client.get("/api/v1/exchange/connections")
    assert listed.status_code == 200
    assert listed.json()["connections"][0]["label"] == GOOD_LABEL

    read_response = client.post("/api/v1/exchange/connections/1/read-balances")
    assert read_response.status_code == 200
    response_json = read_response.json()
    assert response_json["result"]["status"] == "OK"

    snapshots = client.get("/api/v1/exchange/connections/1/snapshots")
    assert snapshots.status_code == 200
    assert len(snapshots.json()["snapshots"]) == 2

    history = client.get("/api/v1/exchange/connections/1/history")
    assert history.status_code == 200
    assert history.json()["history"][-1]["status"] == "OK"


def test_api_duplicate_label_conflict(db, client, patch_connector, master_key_env):
    first = client.post("/api/v1/exchange/connections", json={
        "label": GOOD_LABEL, "api_key": API_KEY, "api_secret": "s3cretVALUE"
    })
    assert first.status_code == 200
    second = client.post("/api/v1/exchange/connections", json={
        "label": GOOD_LABEL, "api_key": API_KEY, "api_secret": "s3cretVALUE2"
    })
    assert second.status_code == 409


def test_api_disconnect_keeps_history(db, client, patch_connector, master_key_env):
    client.post("/api/v1/exchange/connections", json={
        "label": GOOD_LABEL, "api_key": API_KEY, "api_secret": "s3cretVALUE"
    })
    client.post("/api/v1/exchange/connections/1/read-balances")
    disconnected = client.delete("/api/v1/exchange/connections/1")
    assert disconnected.status_code == 200
    assert disconnected.json()["connection"]["status"] == "REMOVED"

    assert client.get("/api/v1/exchange/connections").json()["connections"] == []
    assert client.get("/api/v1/exchange/connections/1/snapshots").json()["snapshots"]  # lịch sử giữ nguyên
    assert client.get("/api/v1/exchange/connections/1/history").json()["history"]  # không xoá


def test_real_permission_fields_and_transfer_rejection():
    from app.connectors.binance import validate_read_permissions, BinanceError
    valid = {"enableReading": True, "enableWithdrawals": False, "enableSpotAndMarginTrading": False,
             "enableInternalTransfer": False, "permitsUniversalTransfer": False}
    validate_read_permissions(valid)
    with pytest.raises(BinanceError):
        validate_read_permissions({**valid, "enableInternalTransfer": True})
    with pytest.raises(BinanceError):
        validate_read_permissions({"canRead": True, "canTrade": False})
    with pytest.raises(BinanceError):
        validate_read_permissions({key: value for key, value in valid.items() if key != "enableWithdrawals"})


def test_funding_components_and_strict_missing_fields():
    from app.connectors.binance import _parse_rows, BinanceError
    row = {"asset": "USDT", "free": "1.23456789", "locked": "2", "freeze": "3", "withdrawing": "4"}
    assert _parse_rows([row], funding=True)[0] == row
    assert _parse_rows([], funding=True)[0]["free"] == "0"
    for key in ("free", "locked", "freeze", "withdrawing"):
        with pytest.raises(BinanceError):
            _parse_rows([{k:v for k,v in row.items() if k != key}], funding=True)
    for value in ("NaN", "Infinity", "-1", None):
        with pytest.raises(BinanceError):
            _parse_rows([{**row, "free": value}], funding=True)


def test_api_secrets_never_echoed_on_validation(client):
    response = client.post("/api/v1/exchange/connections", json={"label":"safe", "api_key":123, "api_secret":"do-not-echo-this"})
    assert response.status_code == 422
    assert "do-not-echo-this" not in response.text


def test_api_admin_token_required(client):
    assert client.get("/api/v1/exchange/connections", headers={"x-adsos-wallet-token":"wrong"}).status_code == 401
    assert client.get("/api/v1/exchange/connections", headers={"origin":"https://evil.example"}).status_code == 403


def test_funding_fields_persist_and_zero_appends(db, master_key_env):
    connection = svc.save_connection(db, GOOD_LABEL, API_KEY, "s3cretVALUE", transport=HappyTransport())
    svc.read_balances(db, connection.id, transport=HappyTransport())
    row = next(r for r in svc.list_snapshots(db, connection.id) if r["wallet_type"] == "funding")
    assert row["freeze"] == "0.50000000" and row["withdrawing"] == "0.10000000"
    class Empty(HappyTransport):
        def handle_request(self, request):
            if request.url.path == "/sapi/v1/asset/get-funding-asset":
                return httpx.Response(200,json=[])
            return super().handle_request(request)
    svc.read_balances(db, connection.id, transport=Empty())
    row = next(r for r in svc.list_snapshots(db, connection.id) if r["wallet_type"] == "funding")
    assert row["free"] == "0.00000000"


def test_scheduler_utc_and_manual_read_lock(db, master_key_env):
    import socket
    from app.jobs.exchange_wallets import _due
    connection = svc.save_connection(db, GOOD_LABEL, API_KEY, "s3cretVALUE", transport=HappyTransport())
    svc.read_balances(db, connection.id, transport=HappyTransport())
    assert not _due(connection, datetime.now(timezone.utc))
    with socket.socket() as lock:
        lock.bind(("127.0.0.1",8913))
        with pytest.raises(svc.ExchangeConflict):
            svc.read_balances(db,connection.id,transport=HappyTransport())


def test_exchange_migration_round_trip(tmp_path):
    database = tmp_path / "round-trip.db"
    cfg = alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    alembic.command.upgrade(cfg, "head")
    alembic.command.downgrade(cfg, "c9f8a3b1d2e6")
    alembic.command.upgrade(cfg, "head")
    import sqlite3
    with sqlite3.connect(database) as con:
        fields = {r[1] for r in con.execute("pragma table_info(exchange_balance_snapshots)")}
        assert {"freeze", "withdrawing"} <= fields


def test_rate_limit_defers_following_reads(db, master_key_env):
    connection = svc.save_connection(db, GOOD_LABEL, API_KEY, "s3cretVALUE", transport=HappyTransport())
    class Limited(HappyTransport):
        def handle_request(self, request):
            if request.url.path == "/api/v3/account":
                return httpx.Response(429, headers={"Retry-After":"3600"}, json={})
            return super().handle_request(request)
    _, result = svc.read_balances(db, connection.id, transport=Limited())
    assert result["status"] == "ERROR"
    with pytest.raises(svc.ExchangeConflict):
        svc.read_balances(db, connection.id, transport=HappyTransport())
