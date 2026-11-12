"""Ví USDT TRC20 — cấu hình/lịch sử chỉ đọc, không ký giao dịch, không ghi 0 khi lỗi.

- Địa chỉ sai định dạng → 400, không lưu.
- Lưu thành công chỉ sau khi kiểm tra kết nối thành công (ok=True).
- Có ví khác đã lưu → 409 xung đột, KHÔNG ghi đè.
- Lịch sử số dư: mỗi lần đọc ok = 1 dòng; lỗi → không thêm dòng, không ghi 0.
- Bật/tắt auto_sync qua PUT; toggle chỉ khi đã lưu ví.
"""
from datetime import datetime, timezone

import alembic.command
import alembic.config
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.connectors.tron import TronAPIError
from app.db import get_db
from app.main import app
from app.models.finance import UsdtWallet, UsdtWalletBalance
from app.services.usdt_wallet import WalletError, read_balance, validate_address
from app.api.v1 import usdt as usdt_api

ADDR_OK = "TPVT4NSNjCCEeaR5FpAq3Q9g65hXF8Uh9r"
ADDR_OTHER = "TKhViEt4NSNjCCEeaR5FpAq3Q9g65hXF8XkZ9Y"


@pytest.fixture
def db(tmp_path):
    database = tmp_path / "wallet-test.db"
    cfg = alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    alembic.command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


class FakeTransport(httpx.BaseTransport):
    """Trả về phản hồi TrongGrid cố định cho test connector/service.

    GET `v1/accounts` → trả account + `trc20` cố định.
    POST `wallet/triggerconstantcontract` → mô phỏng `balanceOf(address)`.
    `trc20_raw=None` → bỏ token USDT khỏi danh sách `trc20`.
    `constant_raw`: hex uint256 mô phỏng; `constant_mode`: ok|computeFail|malformed|httpError.
    """

    def __init__(self, status_code: int = 200, trc20_raw: str = "12345600"):
        self.status_code = status_code
        self.trc20_raw = trc20_raw
        self.constant_raw: str | None = None
        self.constant_mode = "ok"

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("triggerconstantcontract"):
            if self.constant_mode == "httpError":
                return httpx.Response(status_code=500, json={"error": "fake"})
            if self.constant_mode == "computeFail":
                return httpx.Response(status_code=200, json={"result": {"result": False}})
            if self.constant_mode == "malformed":
                return httpx.Response(status_code=200, json={
                    "result": {"result": True}, "constant_result": ["ZZZ"]})
            import json as _json
            req_json = _json.loads(request.read().decode())
            from app.connectors.tron import USDT_TRC20_CONTRACT, _abi_parameter
            assert req_json["function_selector"] == "balanceOf(address)"
            assert req_json["contract_address"] == USDT_TRC20_CONTRACT
            assert req_json["owner_address"] == ADDR_OK
            assert req_json["parameter"] == _abi_parameter(ADDR_OK)
            raw = self.constant_raw if self.constant_raw is not None else "0" * 64
            return httpx.Response(status_code=200, json={
                "result": {"result": True}, "constant_result": [raw]})
        if self.status_code != 200:
            return httpx.Response(status_code=self.status_code, json={"error": "boom"})
        if self.trc20_raw is None:
            body = {"data": [{"address": ADDR_OK, "trc20": []}]}
        else:
            body = {"data": [{"address": ADDR_OK, "trc20": [
                {"TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": self.trc20_raw}]}]}
        return httpx.Response(status_code=200, json=body)


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _wallets_ok(*_args, **_kwargs):
    return {"ok": True, "balance": "12.3456", "read_at": "2026-10-29T00:00:00+00:00",
            "note": None, "contract": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "mode": "live"}


def test_validate_address_rejects_invalid():
    with pytest.raises(WalletError):
        validate_address("0xA1234567890123456789012345678901234567890")
    with pytest.raises(WalletError):
        validate_address("TOIVT4NSNjCCEeaR5FpAq3Q9g65hXF8Uh9")  # chứa O/I + sai độ dài
    assert validate_address(f"  {ADDR_OK} ") == ADDR_OK


def test_connector_parses_usdt_not_trx_and_no_key_leak():
    connector = usdt_api.TronConnector(ADDR_OK, transport=FakeTransport())
    payload = connector.wallet_balance()
    assert payload["balance"] == "12.3456"  # 12345600 / 10^6 — đúng decimals USDT, không phải TRX
    assert payload["wallet_address"] == ADDR_OK
    assert "api_key" not in repr(connector)
    assert "***" in repr(usdt_api.TronConnector(ADDR_OK, api_key="secret"))


def test_save_requires_verify_then_persists(db, client):
    original = usdt_api.verify_address
    usdt_api.verify_address = _wallets_ok
    try:
        bad = client.post("/api/v1/usdt/wallet", json={"wallet_name": "Ví chung", "address": "sai"})
        assert bad.status_code == 400
        response = client.post("/api/v1/usdt/wallet", json={"wallet_name": "Ví chung", "address": ADDR_OK})
    finally:
        usdt_api.verify_address = original
    assert response.status_code == 200
    assert response.json()["saved"] is True
    wallets = db.scalars(select(UsdtWallet)).all()
    assert len(wallets) == 1 and wallets[0].wallet_address == ADDR_OK


def test_save_conflict_does_not_overwrite(db, client):
    db.add(UsdtWallet(wallet_name="Cũ", wallet_address=ADDR_OTHER, network="tron_mainnet",
                      contract="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"))
    db.commit()
    original = usdt_api.verify_address
    usdt_api.verify_address = _wallets_ok
    try:
        response = client.post("/api/v1/usdt/wallet", json={"wallet_name": "Mới", "address": ADDR_OK})
    finally:
        usdt_api.verify_address = original
    assert response.status_code == 409
    assert response.json()["detail"]["saved_wallet_address"] == ADDR_OTHER
    wallets = db.scalars(select(UsdtWallet)).all()
    assert len(wallets) == 1 and wallets[0].wallet_name == "Cũ"


def test_read_balance_history_and_error_keeps_value(db):
    db.add(UsdtWallet(wallet_name="Chung", wallet_address=ADDR_OK, network="tron_mainnet",
                      contract="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"))
    db.commit()
    wallet, payload = read_balance(db, transport=FakeTransport(),
                                   now=datetime.now(timezone.utc))
    assert wallet is not None and payload["balance"] == "12.3456"
    history = db.scalars(select(UsdtWalletBalance).order_by(UsdtWalletBalance.id)).all()
    assert len(history) == 1
    assert str(history[0].balance) == "12.345600"  # DB lưu đủ 6 chữ số thập phân
    assert wallet.last_error is None

    with pytest.raises(TronAPIError):
        read_balance(db, transport=FakeTransport(status_code=500),
                     now=datetime.now(timezone.utc))
    history = db.scalars(select(UsdtWalletBalance).order_by(UsdtWalletBalance.id)).all()
    assert len(history) == 1  # lỗi KHÔNG thêm dòng, không ghi 0
    assert "500" in (wallet.last_error or "")


def test_autosync_toggle_requires_saved_wallet(db, client):
    response = client.put("/api/v1/usdt/wallet", json={"auto_sync": True})
    assert response.status_code == 400
    db.add(UsdtWallet(wallet_name="Chung", wallet_address=ADDR_OK, network="tron_mainnet",
                      contract="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"))
    db.commit()
    assert client.put("/api/v1/usdt/wallet", json={"auto_sync": True}).status_code == 200
    assert db.scalars(select(UsdtWallet)).first().auto_sync is True
    assert client.put("/api/v1/usdt/wallet", json={"auto_sync": False}).status_code == 200
    assert db.scalars(select(UsdtWallet)).first().auto_sync is False


def test_wallet_config_shape(db, client):
    response = client.get("/api/v1/usdt/wallet")
    assert response.status_code == 200
    payload = response.json()
    assert payload["wallet"] is None
    assert payload["network"] == "TRON Mainnet"
    assert any("KHÔNG đại diện" in d for d in payload["disclaimers"])


def test_token_missing_in_list_constant_zero_determined(db):
    """Token vắng trong `trc20`, `balanceOf` xác định 0 → hiển thị "0" (xác định được), không null."""
    transport = FakeTransport(trc20_raw=None)
    connector = usdt_api.TronConnector(ADDR_OK, transport=transport)
    payload = connector.wallet_balance()
    assert payload["balance"] == "0"
    assert payload["note"] is None


def test_constant_positive_balance_using_usdt_decimals():
    """`balanceOf` > 0 → lượng USDT đúng decimals 6 (không áp decimals TRX)."""
    transport = FakeTransport(trc20_raw=None)
    transport.constant_raw = hex(123456771)[2:].rjust(64, "0")  # 123.456771 USDT
    connector = usdt_api.TronConnector(ADDR_OK, transport=transport)
    payload = connector.wallet_balance()
    assert payload["balance"] == "123.456771"


def test_constant_response_invalid_keeps_error_not_zero():
    """`result=false` / thiếu `constant_result` / hex hỏng → lỗi rõ, KHÔNG ghi 0 giả."""
    for mode in ("computeFail", "malformed"):
        transport = FakeTransport(trc20_raw=None)
        transport.constant_mode = mode
        connector = usdt_api.TronConnector(ADDR_OK, transport=transport)
        with pytest.raises(TronAPIError):
            connector.wallet_balance()


def test_constant_http_error_propagates():
    transport = FakeTransport(trc20_raw=None)
    transport.constant_mode = "httpError"
    connector = usdt_api.TronConnector(ADDR_OK, transport=transport)
    with pytest.raises(TronAPIError):
        connector.wallet_balance()


def test_trc20_list_value_still_wins_without_constant_call():
    """Có giá trị trong danh sách `trc20` → dùng luôn, không gọi balanceOf."""
    transport = FakeTransport(trc20_raw="987654321")
    connector = usdt_api.TronConnector(ADDR_OK, transport=transport)
    payload = connector.wallet_balance()
    assert payload["balance"] == "987.654321"


def test_abi_parameter_matches_chain_bytes():
    from app.connectors.tron import _abi_parameter, USDT_DECIMALS
    param = _abi_parameter(ADDR_OK)
    # ABI parameter cho address trong Solidity: 20 byte địa chỉ thực, đệm 24 ký tự 0 phía trước
    assert len(param) == 64 and param.startswith("0" * 24)
    assert USDT_DECIMALS == 6
    # balanceOf của địa chỉ rỗng ABI trở uint256 0 → "0"
    from app.connectors.tron import _parse_balance_of_hex
    assert _parse_balance_of_hex("0" * 64) == "0"
    assert _parse_balance_of_hex("0x" + "0" * 64) == "0"
    assert _parse_balance_of_hex(hex(90)[2:].rjust(64, "0")) == "0.00009"  # 90 / 10^6


def test_read_balance_determined_zero_saved_and_audited(db):
    """Luồng có: `balanceOf`=0 xác định → lưu dòng lịch sử balance=0 (append, không sửa dòng cũ)."""
    from decimal import Decimal
    db.add(UsdtWallet(wallet_name="Chung", wallet_address=ADDR_OK, network="tron_mainnet",
                      contract="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"))
    db.commit()
    wallet, payload = read_balance(db, transport=FakeTransport(trc20_raw=None),
                                   now=datetime.now(timezone.utc))
    assert wallet.last_error is None
    assert payload["balance"] == "0"
    history = db.scalars(select(UsdtWalletBalance).order_by(UsdtWalletBalance.id)).all()
    assert len(history) == 1 and history[0].balance == Decimal("0")
