"""USDT ví chung TRC20 — CHỈ ĐỌC số dư (độc lập với tháng/năm báo cáo).

- Mock mode khi chưa cấu hình địa chỉ ví: mode=mock, balance=None (KHÔNG giả 0).
- Live: parse TrongGrid v1/accounts; token vắng trong `trc20` → đọc trực tiếp
  `balanceOf` (constant call) — thành công → số dư xác định (kể cả "0");
  reading lỗi → `TronAPIError`, không 0 giả.
- Lỗi TrongGrid → không fallback mock; endpoint trả 502.
- Số dư là điểm đọc: KHÔNG đối chiếu với L1/đến kỳ tháng cũ, không cộng L1 nhiều tháng.
"""
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connectors.tron import USDT_TRC20_CONTRACT, TronAPIError, TronConnector
from app.main import app

CONTRACT = USDT_TRC20_CONTRACT
ABI_ZERO = {"result": {"result": True}, "constant_result": ["0" * 64]}


def _halves(account: httpx.Response, constant: httpx.Response):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("triggerconstantcontract"):
            return constant
        return account
    return handler


def _connector(wallet="TVhbricktestwalletaddr12345", transport=None) -> TronConnector:
    return TronConnector(wallet_address=wallet, transport=transport)


def _account_response(raw: str) -> httpx.Response:
    return httpx.Response(200, json={"data": [{"address": "TVbr", "trc20": [{CONTRACT: raw}]}], "success": True})


def test_mock_mode_when_no_wallet_configured():
    connector = _connector(wallet="")
    assert connector.mock_mode is True
    payload = connector.wallet_balance()
    assert payload["mode"] == "mock" and payload["balance"] is None
    assert "không giả 0" in payload["note"]


def test_wallet_balance_parses_usdt_trc20_exact_decimal():
    connector = _connector(transport=httpx.MockTransport(lambda request: _account_response("1234567")))
    payload = connector.wallet_balance()
    assert payload["mode"] == "live"
    assert Decimal(payload["balance"]) == Decimal("1.234567")
    assert payload["read_at"] and payload["contract"] == CONTRACT
    assert payload["wallet_configured"] is True


def test_wallet_without_trc20_data_reads_constant_call_determined_zero():
    """Token vắng trong `trc20` → đọc trực tiếp `balanceOf`; xác định 0 → hiển thị "0"."""
    connector = _connector(
        wallet="TPVT4NSNjCCEeaR5FpAq3Q9g65hXF8Uh9r",
        transport=httpx.MockTransport(_halves(
            httpx.Response(200, json={"data": [{"address": "TVbr", "trc20": []}], "success": True}),
            httpx.Response(200, json=ABI_ZERO),
        )),
    )
    payload = connector.wallet_balance()
    assert payload["balance"] == "0" and payload["note"] is None


def test_unknown_account_is_none_not_zero():
    connector = _connector(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [], "success": True})
    ))
    payload = connector.wallet_balance()
    assert payload["balance"] is None and "không giả 0" in payload["note"]


def test_non_numeric_token_balance_does_not_crash():
    """Giá trị token không phải số trong `trc20` → bỏ qua danh sách, đọc `balanceOf` trực tiếp."""
    connector = _connector(
        wallet="TPVT4NSNjCCEeaR5FpAq3Q9g65hXF8Uh9r",
        transport=httpx.MockTransport(_halves(
            httpx.Response(200, json={"data": [{"trc20": [{CONTRACT: ""}]}], "success": True}),
            httpx.Response(200, json=ABI_ZERO),
        )),
    )
    payload = connector.wallet_balance()
    assert payload["balance"] == "0"  # balanceOf xác định, không phải giá trị rác từ trc20


def test_http_error_keeps_live_mode_raises_clearly():
    connector = _connector(transport=httpx.MockTransport(
        lambda request: httpx.Response(503, json={"error": "upstream"})
    ))
    with pytest.raises(TronAPIError) as excinfo:
        connector.wallet_balance()
    assert "503" in str(excinfo.value)


def test_connection_error_raises_without_mock_fallback():
    def fail(request):
        raise httpx.ConnectError("boom")
    connector = _connector(transport=httpx.MockTransport(fail))
    with pytest.raises(TronAPIError):
        connector.wallet_balance()
    assert connector.mock_mode is False  # live mode không tự chuyển mock


def test_endpoint_mock_mode_without_wallet(db):
    from app.core.config import settings
    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    saved = settings.tron_wallet_address
    settings.tron_wallet_address = ""
    try:
        response = client.get("/api/v1/usdt/wallet-balance")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "mock" and payload["balance"] is None
        assert payload["wallet_configured"] is False
        assert len(payload["disclaimers"]) >= 3
        assert "thời điểm đọc" in payload["disclaimers"][0]
        assert payload.get("wallet_address") is None
    finally:
        settings.tron_wallet_address = saved
        app.dependency_overrides.clear()


def test_endpoint_live_mode_and_502(db, monkeypatch):
    from app.core.config import settings
    from app.api.v1 import usdt as usdt_api
    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    saved = settings.tron_wallet_address

    class Stub:
        def __init__(self, wallet="", api_key=""):
            self.wallet = wallet

        def wallet_balance(self):
            return {
                "mode": "live", "wallet_configured": True, "wallet_address": self.wallet,
                "balance": "42.5", "contract": CONTRACT, "read_at": "2026-10-29T00:00:00+00:00",
                "note": None,
            }

    monkeypatch.setattr(usdt_api, "TronConnector", Stub)
    settings.tron_wallet_address = "TVbr"
    try:
        response = client.get("/api/v1/usdt/wallet-balance")
        assert response.status_code == 200
        payload = response.json()
        assert payload["balance"] == "42.5" and payload["wallet_address"] == "TVbr"
        assert payload["disclaimers"] == usdt_api.DISCLAIMERS
    finally:
        settings.tron_wallet_address = saved

    class Boom:
        def __init__(self, wallet="", api_key=""):
            pass

        def wallet_balance(self):
            raise TronAPIError("TrongGrid down")

    monkeypatch.setattr(usdt_api, "TronConnector", Boom)
    settings.tron_wallet_address = "TVbr"
    try:
        assert client.get("/api/v1/usdt/wallet-balance").status_code == 502
    finally:
        settings.tron_wallet_address = saved
        app.dependency_overrides.clear()


def test_abi_parameter_encoding_strips_prefix_and_checksum_and_left_pads():
    from app.connectors.tron import _abi_parameter
    # TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t:
    # 25-byte raw: 41 + a614f803b6fd780986a42c78ec9c7f77e6ded13c + 710277f5
    param = _abi_parameter("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    assert len(param) == 64
    assert param.startswith("0" * 24)
    # The 20-byte address must match without 0x41 prefix and without 4-byte checksum
    assert param[24:] == "a614f803b6fd780986a42c78ec9c7f77e6ded13c"


def test_balance_of_direct_sends_proper_abi_parameter():
    import json
    captured_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        if "triggerconstantcontract" in request.url.path:
            captured_body = json.loads(request.content)
            return httpx.Response(200, json=ABI_ZERO)
        return httpx.Response(200, json={"data": [{"address": "TR7N", "trc20": []}], "success": True})

    connector = TronConnector(
        wallet_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        transport=httpx.MockTransport(handler),
    )
    result = connector.wallet_balance()
    assert result["balance"] == "0"
    assert captured_body["function_selector"] == "balanceOf(address)"
    assert captured_body["parameter"] == "000000000000000000000000a614f803b6fd780986a42c78ec9c7f77e6ded13c"

