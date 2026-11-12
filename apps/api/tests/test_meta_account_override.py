from decimal import Decimal
import pytest
from sqlalchemy import select, delete
from app.models.ad_account import AdAccount
from app.models.finance import AuditLog
from app.models.extension_remote import RemoteViaCommand
from app.connectors.meta import MetaAdsConnector
from app.services.meta_account_policy import set_violation_override, validate_account_policy
from app.services.meta_campaign_builder import build_and_create_campaign, CampaignCreationRequest


@pytest.fixture(autouse=True)
def cleanup_override_accounts(db):
    yield
    db.rollback()
    from app.models.meta_tasks import MetaCampaignTask
    db.execute(delete(MetaCampaignTask).where(MetaCampaignTask.meta_campaign_id == "override_activation_task"))
    db.execute(delete(AuditLog).where(AuditLog.entity_id == "override_activation_task"))
    db.execute(delete(AuditLog).where(AuditLog.action == "SET_ACCOUNT_VIOLATION_OVERRIDE"))
    db.execute(delete(AdAccount).where(AdAccount.meta_ad_account_id.like("act_override_%")))
    db.execute(delete(AdAccount).where(AdAccount.meta_ad_account_id.like("act_994%")))
    db.commit()


def account(db, suffix, *, numeric=False):
    account_id = f"act_{suffix}" if numeric else f"act_override_{suffix}"
    row = AdAccount(meta_ad_account_id=account_id, name="Tài khoản thử", timezone_name="UTC")
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize("status,balance,threshold", [(2, "0", None), (3, "0", None), (1, "100", "100")])
def test_violation_requires_account_specific_override(db, monkeypatch, status, balance, threshold):
    row = account(db, f"{status}_{threshold}")
    other = account(db, f"other_{status}_{threshold}")
    connector = MetaAdsConnector(use_mock=True)
    monkeypatch.setattr(connector, "get_ad_account_billing_health", lambda _: {"account_status": status, "balance": balance, "billing_threshold": threshold})
    with pytest.raises(ValueError, match="Đặc cách"):
        validate_account_policy(db, connector, row.meta_ad_account_id)
    set_violation_override(db, other.meta_ad_account_id, True)
    with pytest.raises(ValueError, match="Đặc cách"):
        validate_account_policy(db, connector, row.meta_ad_account_id)
    set_violation_override(db, row.meta_ad_account_id, True)
    validate_account_policy(db, connector, row.meta_ad_account_id)
    set_violation_override(db, row.meta_ad_account_id, False)
    with pytest.raises(ValueError, match="Đặc cách"):
        validate_account_policy(db, connector, row.meta_ad_account_id)


def test_override_audit_normalized_account_and_staging_guard(db, monkeypatch):
    from app.core.config import settings
    row = account(db, "audit")
    assert row.allow_violated_accounts is False
    set_violation_override(db, "override_audit", True)
    audit = db.execute(select(AuditLog).where(AuditLog.entity_id == str(row.id), AuditLog.action == "SET_ACCOUNT_VIOLATION_OVERRIDE")).scalars().all()
    assert audit[-1].detail == {"previous": False, "enabled": True}
    monkeypatch.setattr(settings, "app_env", "staging")
    with pytest.raises(ValueError, match="chỉ cho phép đọc"):
        set_violation_override(db, row.meta_ad_account_id, False)
    assert row.allow_violated_accounts is True


def test_invalid_health_never_bypassed(db, monkeypatch):
    row = account(db, "invalid")
    set_violation_override(db, row.meta_ad_account_id, True)
    connector = MetaAdsConnector(use_mock=True)
    monkeypatch.setattr(connector, "get_ad_account_billing_health", lambda _: {})
    with pytest.raises(ValueError, match="Chưa xác minh"):
        validate_account_policy(db, connector, row.meta_ad_account_id)


def test_builder_blocks_before_any_meta_write(db, monkeypatch):
    row = account(db, "994000001", numeric=True)
    connector = MetaAdsConnector(use_mock=True)
    monkeypatch.setattr(connector, "get_ad_account_billing_health", lambda _: {"account_status": 2, "balance": "0"})
    writes = []
    monkeypatch.setattr(connector, "create_campaign", lambda *args: writes.append(args))
    req = CampaignCreationRequest(ad_account_id=row.meta_ad_account_id, campaign_name="Chiến dịch thử nghiệm", daily_budget=Decimal("10000"))
    with pytest.raises(ValueError, match="Đặc cách"):
        build_and_create_campaign(db, connector, req)
    assert writes == []


def test_reporting_validation_blocks_before_insights(db, monkeypatch):
    from fastapi import HTTPException
    from app.api.v1 import meta_mgmt
    row = account(db, "report")
    connector = MetaAdsConnector(use_mock=True)
    monkeypatch.setattr(connector, "get_ad_account_billing_health", lambda _: {"account_status": 2, "balance": "0"})
    calls = []
    monkeypatch.setattr(connector, "get_performance_insights", lambda *args, **kwargs: calls.append(args) or [])
    monkeypatch.setattr(meta_mgmt, "MetaAdsConnector", lambda: connector)
    with pytest.raises(HTTPException) as exc:
        meta_mgmt.get_account_insights(row.meta_ad_account_id, db=db, date_preset="today")
    assert exc.value.status_code == 400
    assert calls == []
    set_violation_override(db, row.meta_ad_account_id, True)
    assert meta_mgmt.get_account_insights(row.meta_ad_account_id, db=db, date_preset="today") == []
    assert len(calls) == 1


def test_activation_uses_task_account_before_sync(db, monkeypatch):
    from app.models.meta_tasks import MetaCampaignTask
    from app.services.meta_campaign_builder import toggle_campaign_status
    row = account(db, "994000002", numeric=True)
    db.add(MetaCampaignTask(ad_account_id=row.meta_ad_account_id, campaign_name="Thử kích hoạt", objective="OUTCOME_LEADS", daily_budget=Decimal("10000"), status="SUCCESS", created_by="test", meta_campaign_id="override_activation_task"))
    db.commit()
    connector = MetaAdsConnector(use_mock=True)
    monkeypatch.setattr(connector, "get_ad_account_billing_health", lambda _: {"account_status": 2, "balance": "0"})
    calls = []
    monkeypatch.setattr(connector, "update_campaign_status", lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="Đặc cách"):
        toggle_campaign_status(db, connector, "override_activation_task", "ACTIVE")
    assert calls == []
    set_violation_override(db, row.meta_ad_account_id, True)
    toggle_campaign_status(db, connector, "override_activation_task", "ACTIVE")
    assert calls == []
    command = db.scalar(
        select(RemoteViaCommand).where(
            RemoteViaCommand.act_id == row.meta_ad_account_id,
            RemoteViaCommand.command_type == "SET_CAMPAIGN_STATUS",
        )
    )
    assert command is not None
    assert command.payload["status"] == "ACTIVE"
