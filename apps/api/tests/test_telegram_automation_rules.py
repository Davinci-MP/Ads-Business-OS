"""Kiểm thử Automation Rules Engine và các API quản trị Telegram Bot & Quy tắc."""

from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.connectors.meta import MetaAdsConnector
from app.connectors.telegram import TelegramBotConnector
from app.main import app
from app.models.ad_account import AdAccount
from app.models.campaign import Campaign
from app.models.extension_remote import RemoteViaCommand
from app.models.spend import SpendSnapshot
from app.models.telegram import AutomationRule, TelegramActivityLog
from app.services.automation_rules import ensure_default_rules, evaluate_automation_rules


def test_ensure_default_rules(db):
    rules = ensure_default_rules(db)
    assert len(rules) >= 4
    rule_types = [r.rule_type for r in rules]
    assert "AUTO_PAUSE_SPEND_LIMIT" in rule_types
    assert "ALERT_LOW_VCC_BALANCE" in rule_types
    assert "DAILY_REPORT_SCHEDULE" in rule_types


def test_evaluate_automation_rules_auto_pause(db):
    ensure_default_rules(db)
    db.add(
        AutomationRule(
            name="Quy tắc queue riêng cho test auto pause",
            rule_type="AUTO_PAUSE_SPEND_LIMIT",
            threshold=Decimal("10000000"),
            currency="VND",
            target_entity_id="cmp_auto_test_1",
            action_type="AUTO_PAUSE",
            is_enabled=True,
        )
    )

    # Tạo campaign ACTIVE và snapshot vượt ngưỡng 10,000,000 VND
    account = AdAccount(
        meta_ad_account_id="act_993000001",
        name="TKQC quy tắc",
        timezone_name="Asia/Ho_Chi_Minh",
    )
    db.add(account)
    db.flush()
    camp = Campaign(
        meta_campaign_id="cmp_auto_test_1",
        ad_account_id=account.id,
        name="Chiến dịch Test Tự động dừng",
        meta_status="ACTIVE",
    )
    db.add(camp)
    db.flush()

    from datetime import datetime, timezone
    snap = SpendSnapshot(
        campaign_id=camp.id,
        spend_amount=Decimal("15000000"),  # > 10,000,000 VND
        snapshot_at=datetime.now(timezone.utc),
        is_checkpoint_9h=False,
    )
    db.add(snap)
    db.commit()

    meta = MetaAdsConnector(use_mock=True)
    telegram = TelegramBotConnector(admin_chat_id="12345", use_mock=True)

    res = evaluate_automation_rules(db, meta_connector=meta, telegram_connector=telegram)
    assert res["rules_checked"] >= 4
    assert res["triggered_count"] >= 1

    # Backend giữ nguyên dữ liệu local và chỉ xếp lệnh PAUSED cho Extension
    db.refresh(camp)
    assert camp.meta_status == "ACTIVE"
    command = db.scalar(
        select(RemoteViaCommand).where(
            RemoteViaCommand.command_type == "SET_CAMPAIGN_STATUS",
            RemoteViaCommand.act_id == "act_993000001",
        )
    )
    assert command is not None
    assert command.payload == {"campaign_id": "cmp_auto_test_1", "status": "PAUSED"}

    # Kiểm tra tin nhắn cảnh báo gửi đi
    assert len(telegram.sent_messages) >= 1
    assert any("QUY TẮC TỰ ĐỘNG" in message["text"] for message in telegram.sent_messages)


def test_telegram_connection_and_config_api(db):
    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)

        # 1. Test connection
        res = client.post("/api/v1/telegram/test-connection")
        assert res.status_code == 200
        assert res.json()["success"] is True
        assert "Bot" in res.json()["message"]

        # 2. Update config
        cfg_payload = {
            "admin_chat_id": "998877",
            "allowed_chat_ids": "998877, 112233",
            "webhook_url": "https://example.com/api/v1/telegram/webhook",
        }
        res_update = client.post("/api/v1/telegram/config", json=cfg_payload)
        assert res_update.status_code == 200
        assert res_update.json()["success"] is True

        # 3. Get config
        res_get = client.get("/api/v1/telegram/config")
        assert res_get.status_code == 200
        assert res_get.json()["admin_chat_id"] == "998877"
        assert "112233" in res_get.json()["allowed_chat_ids"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_telegram_rules_crud_and_activity_logs():
    client = TestClient(app)

    # 1. List rules
    res_list = client.get("/api/v1/telegram/rules")
    assert res_list.status_code == 200
    rules = res_list.json()
    assert len(rules) >= 4

    # 2. Create new rule
    new_rule = {
        "name": "Quy tắc Test Tạo Mới",
        "rule_type": "AUTO_PAUSE_SPEND_LIMIT",
        "threshold": 5000000,
        "currency": "VND",
        "action_type": "AUTO_PAUSE",
        "is_enabled": True,
    }
    res_create = client.post("/api/v1/telegram/rules", json=new_rule)
    assert res_create.status_code == 200
    rule_id = res_create.json()["rule_id"]

    # 3. Patch rule (toggle status)
    res_patch = client.patch(f"/api/v1/telegram/rules/{rule_id}", json={"is_enabled": False})
    assert res_patch.status_code == 200
    assert res_patch.json()["is_enabled"] is False

    # 4. Run rules evaluation
    res_eval = client.post("/api/v1/telegram/rules/run-check")
    assert res_eval.status_code == 200
    assert "summary" in res_eval.json()

    # 5. Delete rule
    res_del = client.delete(f"/api/v1/telegram/rules/{rule_id}")
    assert res_del.status_code == 200

    # 6. Dispatch command and verify activity log
    res_disp = client.post(
        "/api/v1/telegram/dispatch",
        json={"command": "/status", "actor": "test_runner"},
    )
    assert res_disp.status_code == 200

    res_logs = client.get("/api/v1/telegram/activity-logs?limit=5")
    assert res_logs.status_code == 200
    logs = res_logs.json()
    assert len(logs) >= 1
    assert any(l["command"] == "/status" for l in logs)
