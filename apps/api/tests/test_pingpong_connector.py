"""Fixtures follow the published Issuing 2.7.1 contract; no permission API is invented."""
import logging
import httpx
import pytest
from app.connectors.pingpong import (
    PingPongConnector, PingPongError, PingPongAuthError, PingPongRateLimitError,
    DEFAULT_PINGPONG_BASE_URL, TOKEN_PATH, BALANCE_PATH, CARDS_PATH,
    build_string_to_sign, generate_signature,
)


def ok(data):
    return httpx.Response(200, json={"code": 6666, "message": "success", "data": data})


class MockPingPongTransport(httpx.BaseTransport):
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.history = []

    def handle_request(self, request):
        # Snapshot request before the connector clears secret query parameters for logging.
        self.history.append((request.method, request.url.path, dict(request.url.params), dict(request.headers)))
        path = request.url.path
        if path in self.responses:
            reply = self.responses[path]
            return reply(request) if callable(reply) else reply
        if path == TOKEN_PATH:
            return ok({"access_token": "fixture-access-token", "expires_in": 7200})
        if path == BALANCE_PATH:
            return ok([{"currency": c, "balance": a, "pending_balance": "0", "total_balance": a,
                        "budget_id": "fixture-budget-"+c, "budget_name": "Fixture"}
                       for c, a in [("USD", "15420.50"), ("EUR", "8200.00"), ("SGD", "4500.75")]])
        if path == CARDS_PATH:
            return ok({"list": [
                {"pp_card_id": "vcc_001", "remark": "Media Buyer FB 01", "card_number": "411122***4567",
                 "billing_currency": "USD", "card_status": "ACTIVE", "type": "SHARE"},
                {"pp_card_id": "vcc_002", "remark": "TikTok Ads Team", "card_number": "555566***8888",
                 "billing_currency": "EUR", "card_status": "REVOKED", "type": "SHARE"}]})
        return httpx.Response(404)


def connector(transport=None, **kwargs):
    return PingPongConnector(client_id="fixture-app-id", client_secret="fixture-app-secret",
                             transport=transport or MockPingPongTransport(), **kwargs)


def test_official_token_and_balance_contract_cached_token():
    t = MockPingPongTransport()
    with connector(t) as c:
        balances = c.funding_balances()
        c.virtual_cards()
        c.funding_balances()
    token_calls = [r for r in t.history if r[1] == TOKEN_PATH]
    assert len(token_calls) == 1
    assert token_calls[0][0] == "GET"
    assert token_calls[0][2] == {"app_id": "fixture-app-id", "app_secret": "fixture-app-secret"}
    assert t.history[1][3]["authorization"] == "Bearer fixture-access-token"
    assert t.history[2][3]["authorization"] == "fixture-access-token"
    assert not any("x-signature" in r[3] or "x-account-id" in r[3] for r in t.history)
    assert all(r[0] == "GET" for r in t.history)
    assert balances[0]["available_balance"] == "15420.50"


def test_expired_token_is_refetched():
    t = MockPingPongTransport()
    with connector(t) as c:
        c.funding_balances()
        c._token_expires_at = 0
        c.funding_balances()
    assert sum(r[1] == TOKEN_PATH for r in t.history) == 2


@pytest.mark.parametrize("url", ["https://pingpongx.com", "https://api.pingpongx.com", "http://127.0.0.1", "https://example.invalid"])
def test_unapproved_hosts_rejected_before_credentials_are_sent(url):
    t = MockPingPongTransport()
    with pytest.raises(PingPongError):
        connector(t, base_url=url)
    assert t.history == []


@pytest.mark.parametrize("method,path", [("POST", BALANCE_PATH), ("GET", "/v2/vcc/open/card/apply"), ("GET", "https://example.invalid")])
def test_write_and_arbitrary_endpoints_are_blocked(method, path):
    t = MockPingPongTransport()
    with connector(t) as c, pytest.raises(PingPongError):
        c._request(method, path)
    assert t.history == []


def test_redirect_is_not_followed_and_location_is_not_echoed():
    t = MockPingPongTransport({TOKEN_PATH: httpx.Response(301, headers={"Location": "https://example.invalid/?token=hidden"})})
    with connector(t) as c, pytest.raises(PingPongError) as e:
        c.funding_balances()
    assert "hidden" not in str(e.value)
    assert len(t.history) == 1


def test_business_error_http_200_does_not_mean_success():
    t = MockPingPongTransport({BALANCE_PATH: httpx.Response(200, json={"code": 5000, "message": "secret=hidden", "data": []})})
    with connector(t) as c, pytest.raises(PingPongError) as e:
        c.funding_balances()
    assert "hidden" not in str(e.value)


def test_token_failure_stops_before_business_requests():
    t = MockPingPongTransport({TOKEN_PATH: httpx.Response(401)})
    with connector(t) as c, pytest.raises(PingPongAuthError):
        c.funding_balances()
    assert len(t.history) == 1


def test_token_query_is_not_in_httpx_logs(caplog):
    caplog.set_level(logging.INFO, logger="httpx")
    with connector() as c:
        c.funding_balances()
    assert "fixture-app-secret" not in caplog.text
    assert "app_secret=" not in caplog.text


def test_transport_error_does_not_leak_token_query():
    def fail(request):
        raise httpx.ConnectError("simulated failure", request=request)
    with connector(MockPingPongTransport({TOKEN_PATH: fail})) as c, pytest.raises(PingPongError) as e:
        c.funding_balances()
    assert "fixture-app-secret" not in str(e.value)
    assert e.value.__cause__ is None


def test_repeated_card_page_fails_instead_of_returning_partial_cards():
    rows = [{"pp_card_id": str(i), "billing_currency": "USD", "card_status": "ACTIVE"} for i in range(100)]
    with connector(MockPingPongTransport({CARDS_PATH: ok({"list": rows})})) as c, pytest.raises(PingPongError):
        c.virtual_cards()


@pytest.mark.parametrize("bad", [None, "NaN", "Infinity", True])
def test_invalid_or_missing_balance_is_not_zero(bad):
    t = MockPingPongTransport({BALANCE_PATH: ok([{"currency": "USD", "balance": bad, "pending_balance": "0", "total_balance": "0"}])})
    with connector(t) as c, pytest.raises(PingPongError):
        c.funding_balances()


def test_zero_and_empty_balances_are_valid():
    t = MockPingPongTransport({BALANCE_PATH: ok([{"currency": "USD", "balance": 0, "pending_balance": 0, "total_balance": 0}])})
    with connector(t) as c:
        assert c.funding_balances()[0]["available_balance"] == "0"
    with connector(MockPingPongTransport({BALANCE_PATH: ok([])})) as c:
        assert c.funding_balances() == []


def test_duplicate_currency_budgets_are_not_silently_discarded_or_added():
    row = {"currency": "USD", "balance": "1", "pending_balance": "0", "total_balance": "1"}
    with connector(MockPingPongTransport({BALANCE_PATH: ok([row, row])})) as c, pytest.raises(PingPongError):
        c.funding_balances()


def test_cards_mask_and_paginate():
    def page(request):
        i = int(request.url.params["start_page"])
        rows = [{"pp_card_id": str(n), "card_number": "4111222233334567", "billing_currency": "USD", "card_status": "ACTIVE"}
                for n in range(100)] if i == 1 else []
        return ok({"list": rows})
    t = MockPingPongTransport({CARDS_PATH: page})
    with connector(t) as c:
        cards = c.virtual_cards()
    assert len(cards) == 100
    assert cards[0]["last4"] == "4567"
    assert "4111222233334567" not in str(cards)
    assert "card_number" not in cards[0]
    assert cards[0]["available_balance"] is None
    assert [r[2]["start_page"] for r in t.history if r[1] == CARDS_PATH] == ["1", "2"]


def test_rate_limit_and_retry():
    t = MockPingPongTransport({BALANCE_PATH: httpx.Response(429, headers={"Retry-After": "120"})})
    with connector(t) as c, pytest.raises(PingPongRateLimitError) as e:
        c.funding_balances()
    assert e.value.retry_after_s == 120
    calls = []

    def flaky(request):
        calls.append(1)
        return httpx.Response(502) if len(calls) == 1 else ok([])
    with connector(MockPingPongTransport({BALANCE_PATH: flaky})) as c:
        assert c.funding_balances() == []
    assert len(calls) == 2


# ======================== KIỂM THỬ MỚI BUBBLE UP LỖI & CHỮ KÝ ========================

def test_exact_business_error_bubbling():
    """Trích xuất lỗi nghiệp vụ thật từ JSON payload, loại bỏ câu chữ chung chung."""
    assert issubclass(PingPongError, ValueError)

    # 1. Invalid Signature -> PingPongAuthError với thông báo cụ thể
    t1 = MockPingPongTransport({
        BALANCE_PATH: httpx.Response(200, json={"code": "1004", "message": "Invalid Signature"})
    })
    with connector(t1) as c, pytest.raises(PingPongAuthError) as exc_info:
        c.funding_balances()
    assert str(exc_info.value) == "PingPong API Error [1004]: Invalid Signature"
    assert exc_info.value.code == "1004"

    # 2. IP not whitelisted -> PingPongAuthError với thông báo cụ thể
    t2 = MockPingPongTransport({
        BALANCE_PATH: httpx.Response(200, json={"code": 1005, "msg": "Client IP 1.2.3.4 is not in whitelist"})
    })
    with connector(t2) as c, pytest.raises(PingPongAuthError) as exc_info:
        c.funding_balances()
    assert "PingPong API Error [1005]: Client IP 1.2.3.4 is not in whitelist" in str(exc_info.value)

    # 3. Business error with bizMsg -> PingPongError với thông báo cụ thể
    t3 = MockPingPongTransport({
        BALANCE_PATH: httpx.Response(200, json={"bizCode": "CARD_LIMIT_EXCEEDED", "bizMsg": "Spending limit reached"})
    })
    with connector(t3) as c, pytest.raises(PingPongError) as exc_info:
        c.funding_balances()
    assert str(exc_info.value) == "PingPong API Error [CARD_LIMIT_EXCEEDED]: Spending limit reached"

    # 4. Các mã thành công 0, 00000, 200, 6666, success=True không báo lỗi
    for succ_code in (0, "0", "00000", 200, "200", 6666, "6666"):
        t_succ = MockPingPongTransport({
            BALANCE_PATH: httpx.Response(200, json={"code": succ_code, "data": []})
        })
        with connector(t_succ) as c:
            assert c.funding_balances() == []

    t_succ_flag = MockPingPongTransport({
        BALANCE_PATH: httpx.Response(200, json={"success": True, "data": []})
    })
    with connector(t_succ_flag) as c:
        assert c.funding_balances() == []


def test_request_headers_strict_compliance():
    """Kiểm tra request headers chứa đầy đủ PingPong-Client-Id, Timestamp, Signature, Content-Type."""
    t = MockPingPongTransport()
    with connector(t) as c:
        c.funding_balances()
    balance_req = [r for r in t.history if r[1] == BALANCE_PATH][0]
    headers = balance_req[3]
    assert headers["content-type"] == "application/json"
    assert headers["pingpong-client-id"] == "fixture-app-id"
    assert headers["pingpong-timestamp"].isdigit()
    assert len(headers["pingpong-signature"]) == 64
    assert headers["authorization"] == "Bearer fixture-access-token"


def test_build_string_to_sign_alphabetical_and_clean():
    """Chuỗi ký được sắp xếp alphabet, không khoảng trắng thừa và chuẩn hóa URI + timestamp."""
    # Sắp xếp các tham số alphabet
    s1 = build_string_to_sign("/v2/cards", "1700000000000", params={"start_page": 2, "row": 50})
    assert s1 == "/v2/cards?row=50&start_page=2&timestamp=1700000000000"

    # Loại bỏ sign, signature khỏi chuỗi ký
    s2 = build_string_to_sign("/v2/cards", "1700000000000", params={"sign": "xxx", "signature": "yyy", "status": "ACTIVE"})
    assert s2 == "/v2/cards?status=ACTIVE&timestamp=1700000000000"

    # Khi không có tham số
    s3 = build_string_to_sign("/v2/balance", "1700000000000")
    assert s3 == "/v2/balance?timestamp=1700000000000"

    # Chuỗi query sẵn trong path được chuẩn hóa và sắp xếp
    s4 = build_string_to_sign("/v2/cards?z=9&a=1", "1700000000000", params={"m": "5"})
    assert s4 == "/v2/cards?a=1&m=5&z=9&timestamp=1700000000000"


def test_rsa_and_hmac_signature_generation():
    """Kiểm tra ký HMAC-SHA256 và RSA-SHA256 PKCS1v15 với key PEM."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    # Test HMAC
    hmac_sig = generate_signature("my-secret-key", "/v2/test?timestamp=1000")
    assert len(hmac_sig) == 64
    assert all(c in "0123456789abcdef" for c in hmac_sig)

    # Test RSA
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_str = pem_bytes.decode("ascii")
    rsa_sig = generate_signature(pem_str, "/v2/test?timestamp=1000")
    assert isinstance(rsa_sig, str)
    assert len(rsa_sig) > 0
