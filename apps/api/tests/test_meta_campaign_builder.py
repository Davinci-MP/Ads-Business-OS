"""Kiểm thử Controlled Campaign Builder Pipeline (Budget Cap Guard, Safe Default Status, Audit Log)."""

from decimal import Decimal
import pytest
from sqlalchemy import select

from app.connectors.meta import MetaAdsConnector
from app.core.config import settings
from app.models.ad_account import AdAccount
from app.models.campaign import Campaign
from app.models.extension_remote import RemoteViaCommand
from app.models.finance import AuditLog
from app.services.meta_campaign_builder import (
    CampaignCreationRequest,
    build_and_create_campaign,
    toggle_campaign_status,
    validate_budget_cap,
)


def test_budget_cap_guard_raises_error(monkeypatch):
    monkeypatch.setattr(settings, "meta_max_daily_budget", 50_000_000.0)

    # Valid budget: 10,000,000 VND -> Pass
    validate_budget_cap(Decimal("10000000"))

    # Exceeding budget: 60,000,000 VND -> Error
    with pytest.raises(ValueError) as exc:
        validate_budget_cap(Decimal("60000000"))
    assert "vượt quá hạn mức an toàn" in str(exc.value)


def test_build_and_create_campaign_pipeline(db):
    connector = MetaAdsConnector(use_mock=True)

    req = CampaignCreationRequest(
        ad_account_id="act_991000001",
        campaign_name="Chiến dịch Chuyển đổi Khách Hàng",
        objective="OUTCOME_LEADS",
        daily_budget=Decimal("500000"),
        page_id="page_123",
        post_id="post_456",
        created_by="test_user",
    )

    res = build_and_create_campaign(db, connector, req)

    assert res["success"] is True
    assert res["status"] == "PENDING"
    assert res["target_status"] == "PAUSED"

    command = db.get(RemoteViaCommand, res["task_id"])
    assert command.status == "PENDING"
    assert command.command_type == "SET_CAMP"
    assert command.payload["status"] == "PAUSED"
    assert command.payload["daily_budget"] == "500000"

    # Kiểm tra AuditLog
    audit = db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == command.public_id,
            AuditLog.action == "QUEUE_META_CAMPAIGN_CREATE",
        )
    ).scalar_one()
    assert audit.actor == "test_user"
    assert audit.detail["status"] == "PAUSED"


def test_toggle_campaign_status(db):
    connector = MetaAdsConnector(use_mock=True)

    account = AdAccount(
        meta_ad_account_id="act_992000001",
        name="TKQC kiểm thử queue",
        timezone_name="Asia/Ho_Chi_Minh",
    )
    db.add(account)
    db.flush()
    meta_cid = "cmp_1001"
    db.add(Campaign(meta_campaign_id=meta_cid, ad_account_id=account.id, name="Camp kiểm thử"))
    db.commit()

    res_active = toggle_campaign_status(db, connector, meta_cid, "ACTIVE", actor="admin_bot")
    assert res_active["status"] == "PENDING"
    assert res_active["target_status"] == "ACTIVE"

    res_pause = toggle_campaign_status(db, connector, meta_cid, "PAUSED", actor="admin_bot")
    assert res_pause["status"] == "PENDING"
    assert res_pause["target_status"] == "PAUSED"

    # Kiểm tra AuditLog
    audits = db.execute(
        select(AuditLog).where(
            AuditLog.actor == "admin_bot",
        )
    ).scalars().all()
    actions = [a.action for a in audits]
    assert "QUEUE_CAMPAIGN_ACTIVE" in actions
    assert "QUEUE_CAMPAIGN_PAUSED" in actions
