"""Kiểm thử tính năng tối ưu hoá MetaAdsConnector (Connection Pooling, Rate-limit, Batching, Decryption, Redaction)."""

from decimal import Decimal
import json
import httpx
import pytest

from app.connectors.meta import (
    MetaAdsConnector,
    RateLimitTelemetry,
    decrypt_token_if_encrypted,
    encrypt_meta_token,
    redact_sensitive,
)
from app.core.config import settings


def test_redact_sensitive_cleans_tokens():
    raw_error = "Meta error: access_token=EAAB123456789xyz&appsecret_proof=deadbeef1234 on request"
    cleaned = redact_sensitive(raw_error)
    assert "EAAB123456789xyz" not in cleaned
    assert "deadbeef1234" not in cleaned
    assert "access_token=[REDACTED]" in cleaned
    assert "appsecret_proof=[REDACTED]" in cleaned


def test_rate_limit_telemetry_parsing():
    telemetry = RateLimitTelemetry()
    assert not telemetry.should_throttle
    assert telemetry.max_util_pct == 0.0

    headers = httpx.Headers(
        {
            "x-ad-account-usage": json.dumps({"acc_id_util_pct": 82.5}),
            "x-app-usage": json.dumps({"call_count": 50, "total_cputime": 30, "total_time": 40}),
            "x-business-use-case-usage": json.dumps(
                {"act_123": [{"call_count": 85, "total_cputime": 10, "total_time": 20}]}
            ),
        }
    )
    telemetry.update_from_headers(headers)
    assert telemetry.max_util_pct == 85.0
    assert telemetry.should_throttle is True

    telemetry_dict = telemetry.to_dict()
    assert telemetry_dict["max_util_pct"] == 85.0
    assert telemetry_dict["should_throttle"] is True


def test_fernet_token_encryption_and_decryption(monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "exchange_master_key", key)

    raw_token = "EAAB_super_secret_meta_token_12345"
    encrypted = encrypt_meta_token(raw_token)
    assert encrypted.startswith("gAAAAA")
    assert raw_token not in encrypted

    decrypted = decrypt_token_if_encrypted(encrypted)
    assert decrypted == raw_token

    # Non-encrypted token passes through as-is
    plain = "plain_token"
    assert decrypt_token_if_encrypted(plain) == plain


def test_meta_connector_batch_and_billing_mock():
    connector = MetaAdsConnector(use_mock=True)

    # 1. Billing health check
    health = connector.get_ad_account_billing_health("act_mock_1")
    assert health["meta_ad_account_id"] == "act_mock_1"
    assert health["account_status_label"] == "Hoạt động"
    assert health["disable_reason_label"] == "Không có vi phạm"
    assert health["amount_spent"] > 0
    assert health["balance"] > 0

    # 2. Performance insights
    insights = connector.get_performance_insights("act_mock_1", date_preset="today")
    assert len(insights) > 0
    row = insights[0]
    assert "spend" in row
    assert "impressions" in row
    assert "clicks" in row
    assert "ctr" in row

    # 3. Batch API
    batch_res = connector.batch_request([{"method": "GET", "relative_url": "act_mock_1"}])
    assert len(batch_res) == 1
    assert batch_res[0]["code"] == 200


def test_graph_get_paginated_cursor():
    pages_visited = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "after=page2_cursor" in url_str:
            pages_visited.append("page2")
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "item_3"}, {"id": "item_4"}],
                    "paging": {"cursors": {"after": None}},
                },
            )
        else:
            pages_visited.append("page1")
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "item_1"}, {"id": "item_2"}],
                    "paging": {"cursors": {"after": "page2_cursor"}},
                },
            )

    transport = httpx.MockTransport(mock_handler)
    connector = MetaAdsConnector(access_token="test_tok", transport=transport)
    items = connector._graph_get_paginated("act_123/campaigns", {"fields": "id"}, limit_pages=3)
    assert len(items) == 4
    assert [i["id"] for i in items] == ["item_1", "item_2", "item_3", "item_4"]
    assert pages_visited == ["page1", "page2"]
    connector.close()
