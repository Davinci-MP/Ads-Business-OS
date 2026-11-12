"""Kiểm thử Telegram Bot Agent (Whitelist, Command Dispatching, Webhook, REST APIs)."""

from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.connectors.meta import MetaAdsConnector
from app.connectors.telegram import TelegramBotConnector
from app.core.config import settings
from app.main import app
from app.services.telegram_bot import TelegramBotAgent


def test_telegram_connector_whitelist():
    connector = TelegramBotConnector(
        admin_chat_id="123456",
        allowed_chat_ids=["789012", "345678"],
        use_mock=True,
    )

    assert connector.is_chat_allowed("123456") is True  # Admin
    assert connector.is_chat_allowed("789012") is True  # Whitelisted
    assert connector.is_chat_allowed(345678) is True    # Whitelisted as int
    assert connector.is_chat_allowed("999999") is False # Stranger


def test_telegram_agent_unauthorized_rejection(db):
    tg_mock = TelegramBotConnector(
        admin_chat_id="100",
        allowed_chat_ids=["200"],
        use_mock=True,
    )
    meta_mock = MetaAdsConnector(use_mock=True)
    agent = TelegramBotAgent(meta_connector=meta_mock, telegram_connector=tg_mock)

    update = {
        "message": {
            "chat": {"id": 999},  # Unauthorized
            "text": "/tk",
            "from": {"username": "stranger"},
        }
    }
    res = agent.process_update(db, update)
    assert res["status"] == "rejected"
    assert res["reason"] == "unauthorized"
    assert len(tg_mock.sent_messages) == 1
    assert "Từ chối truy cập" in tg_mock.sent_messages[0]["text"]


def test_telegram_agent_commands(db):
    tg_mock = TelegramBotConnector(
        admin_chat_id="100",
        allowed_chat_ids=["100"],
        use_mock=True,
    )
    meta_mock = MetaAdsConnector(use_mock=True)
    agent = TelegramBotAgent(meta_connector=meta_mock, telegram_connector=tg_mock)

    # 1. /help
    help_out = agent.dispatch_command(db, "/help")
    assert "ADS BUSINESS OS" in help_out
    assert "/setcamp" in help_out

    # 2. /status
    status_out = agent.dispatch_command(db, "/status")
    assert "TRẠNG THÁI HỆ THỐNG" in status_out

    # 3. /tk
    tk_out = agent.dispatch_command(db, "/tk")
    assert "DANH SÁCH TÀI KHOẢN" in tk_out
    assert "act_mock_1" in tk_out

    # 4. /baocao
    report_out = agent.dispatch_command(db, "/baocao act_mock_1 today")
    assert "BÁO CÁO HIỆU SUẤT" in report_out
    assert "Chi phí" in report_out

    # 5. Các lệnh ghi Meta cũ không còn được backend thực thi
    dry_out = agent.dispatch_command(db, "/lencamp act_mock_1 Camp_Preview 500000 OUTCOME_LEADS --dry-run")
    assert "Backend không tạo chiến dịch trực tiếp" in dry_out

    # 6. /lencamp create
    create_out = agent.dispatch_command(db, "/lencamp act_mock_1 Camp_Live 500000 OUTCOME_LEADS")
    assert "Backend không tạo chiến dịch trực tiếp" in create_out

    # 7. /batcamp and /tatcamp
    bat_out = agent.dispatch_command(db, "/batcamp cmp_1001")
    assert "Không hỗ trợ bật chiến dịch từ backend" in bat_out

    tat_out = agent.dispatch_command(db, "/tatcamp cmp_1001")
    assert "Chrome Extension" in tat_out


def test_telegram_and_meta_api_endpoints(db):
    from app.db import get_db
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        _telegram_and_meta_api_endpoints()
    finally:
        app.dependency_overrides.pop(get_db, None)


def _telegram_and_meta_api_endpoints():
    client = TestClient(app)

    # 1. GET /api/v1/telegram/status
    res = client.get("/api/v1/telegram/status")
    assert res.status_code == 200
    assert "mode" in res.json()

    # 2. GET /api/v1/meta/accounts/billing
    res = client.get("/api/v1/meta/accounts/billing")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["account_status_label"] == "Hoạt động"

    # 3. GET /api/v1/meta/telemetry
    res = client.get("/api/v1/meta/telemetry")
    assert res.status_code == 200
    assert "max_util_pct" in res.json()

    # 4. POST /api/v1/meta/campaigns/create
    payload = {
        "ad_account_id": "act_990000001",
        "campaign_name": "API Test Campaign",
        "daily_budget": 1000000,
        "objective": "OUTCOME_LEADS",
    }
    res = client.post("/api/v1/meta/campaigns/create", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "PENDING"
    assert res.json()["command"]["payload"]["status"] == "PAUSED"

    # 5. GET /api/v1/meta/campaigns/tasks
    res = client.get("/api/v1/meta/campaigns/tasks")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
