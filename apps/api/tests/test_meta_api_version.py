"""S16: cấu hình phiên bản Marketing API + kiểm tra token (GET-only, D-027)."""

from app.connectors.meta import MetaAPIError, MetaAdsConnector


def test_default_api_version_is_v26(monkeypatch):
    monkeypatch.delenv("ADSOS_META_API_VERSION", raising=False)
    connector = MetaAdsConnector(use_mock=True)
    assert connector.api_version == "v26.0"


def test_api_version_env_override(monkeypatch):
    monkeypatch.setenv("ADSOS_META_API_VERSION", "v27.0")
    connector = MetaAdsConnector(use_mock=True)
    assert connector.api_version == "v27.0"


def test_api_version_param_wins(monkeypatch):
    monkeypatch.setenv("ADSOS_META_API_VERSION", "v27.0")
    connector = MetaAdsConnector(use_mock=True, api_version="v26.0")
    assert connector.api_version == "v26.0"


def test_check_access_mock_rejected_without_fallback(monkeypatch):
    monkeypatch.delenv("ADSOS_META_API_VERSION", raising=False)
    connector = MetaAdsConnector(use_mock=True)
    try:
        connector.check_access()
    except MetaAPIError as exc:
        assert "token" in str(exc).lower()
    else:
        raise AssertionError("mock phải bị chặn check live")


def test_check_access_url_uses_configured_version(monkeypatch):
    """S16: GET /me/adaccounts phải đi qua phiên bản cấu hình (v26.0 mặc định)."""
    calls: list[str] = []

    class Stub(MetaAdsConnector):
        def get_ad_accounts(self):  # noqa: D102 — thay thế fetch thật
            calls.append(self.api_version)
            return [
                {
                    "meta_ad_account_id": "act_112233445566778",
                    "name": "JOKER acc",
                    "business_manager_id": "bm_1",
                    "timezone_name": "Asia/Ho_Chi_Minh",
                    "currency": "USD",
                }
            ]

    monkeypatch.delenv("ADSOS_META_API_VERSION", raising=False)
    connector = Stub(access_token="stub-token")
    report = connector.check_access()
    assert report["mode"] == "live"
    assert report["api_version"] == "v26.0"
    assert report["accounts_accessible"][0]["meta_ad_account_id"] == "act_112233445566778"
    assert calls == ["v26.0"]
    assert "stub-token" not in repr(report)


def test_meta_connector_client_reuse_and_close():
    import httpx

    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"data": [{"id": "act_123", "name": "Acc 123"}]})

    transport = httpx.MockTransport(handler)
    with MetaAdsConnector(access_token="test_token", transport=transport) as connector:
        client1 = connector._get_client()
        res1 = connector._graph_get("me/adaccounts", {"fields": "id,name"})
        client2 = connector._get_client()
        assert client1 is client2
        res2 = connector._graph_get("me/adaccounts", {"fields": "id,name"})
        assert len(captured_requests) == 2
        assert not client1.is_closed

    assert client1.is_closed
    assert connector._client is None

