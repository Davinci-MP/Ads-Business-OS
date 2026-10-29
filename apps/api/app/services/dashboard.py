"""Đọc dữ liệu cho Dashboard S5 (chỉ đọc DB; không ghi Sheets, không suy diễn số tiền).

Mọi con số lấy từ snapshot/ledger đã có; không sinh số mới. Checkpoint lấy theo
snapshot is_checkpoint_9h gần nhất.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.connectors.meta import build_connector
from app.models import AuditLog, AdAccount, AdAccountAssignment, Campaign, Customer, DriftRecord, SpendSnapshot
from app.models.spend import DATA_UNVERIFIED, DATA_VERIFIED


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _latest_snapshot(session: Session, campaign_id: int) -> SpendSnapshot | None:
    return session.execute(
        select(SpendSnapshot)
        .where(SpendSnapshot.campaign_id == campaign_id, SpendSnapshot.data_status == DATA_VERIFIED)
        .order_by(SpendSnapshot.snapshot_at.desc(), SpendSnapshot.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _latest_checkpoint(session: Session, campaign_id: int) -> SpendSnapshot | None:
    return session.execute(
        select(SpendSnapshot)
        .where(SpendSnapshot.campaign_id == campaign_id, SpendSnapshot.is_checkpoint_9h.is_(True))
        .order_by(SpendSnapshot.snapshot_at.desc(), SpendSnapshot.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _latest_drift(session: Session, campaign_id: int) -> DriftRecord | None:
    return session.execute(
        select(DriftRecord)
        .where(DriftRecord.campaign_id == campaign_id)
        .order_by(DriftRecord.computed_at.desc(), DriftRecord.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _current_customer(session: Session, account_id: int) -> tuple[int | None, str | None, str, int | None]:
    now = datetime.now(timezone.utc)
    rows = session.execute(
        select(AdAccountAssignment)
        .where(
            AdAccountAssignment.ad_account_id == account_id,
            AdAccountAssignment.valid_from <= now,
            or_(AdAccountAssignment.valid_to.is_(None), AdAccountAssignment.valid_to > now),
        )
    ).scalars().all()
    if not rows:
        return None, None, "UNASSIGNED", None
    if len(rows) != 1:
        return None, None, "CONFLICT", None
    row = rows[0]
    customer = session.get(Customer, row.customer_id)
    return customer.id, customer.name, "ASSIGNED", row.id


def overview(session: Session) -> dict[str, Any]:
    customers = session.execute(select(Customer)).scalars().all()
    accounts = session.execute(select(AdAccount)).scalars().all()
    assignments = session.execute(
        select(AdAccountAssignment).where(AdAccountAssignment.valid_to.is_(None))
    ).scalars().all()
    campaigns = session.execute(select(Campaign)).scalars().all()
    last_sync = session.execute(
        select(SpendSnapshot.snapshot_at).order_by(SpendSnapshot.snapshot_at.desc()).limit(1)
    ).scalar_one_or_none()
    from app.models.ad_account import (
        ACCOUNT_ACTIVE,
        ACCOUNT_DEAD,
        ACCOUNT_RESTRICTED,
        ACCOUNT_REPLACED,
    )

    return {
        "mode": build_connector().mode,
        "totals": {
            "customers": len(customers),
            "accounts_total": len(accounts),
            "accounts_active": sum(1 for a in accounts if a.status == ACCOUNT_ACTIVE),
            "accounts_restricted": sum(1 for a in accounts if a.status == ACCOUNT_RESTRICTED),
            "accounts_replaced": sum(1 for a in accounts if a.status == ACCOUNT_REPLACED),
            "accounts_dead": sum(1 for a in accounts if a.status == ACCOUNT_DEAD),
            "assignments_active": len(assignments),
            "campaigns_total": len(campaigns),
            "campaigns_confirmed": sum(1 for c in campaigns if c.customer_id is not None),
            "campaigns_need_check": sum(1 for c in campaigns if c.customer_id is None),
        },
        "students": [
            {"id": c.id, "name": c.name, "recon_mode": c.recon_mode, "fee_rate": str(c.fee_rate),
             "budget_alert_threshold_vnd": str(c.budget_alert_threshold_vnd)
             if c.budget_alert_threshold_vnd is not None else None}
            for c in customers
        ],
        "last_sync_at": _iso(last_sync),
    }


def campaign_rows(session: Session) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    campaigns = session.execute(select(Campaign).order_by(Campaign.id)).scalars().all()
    account_map = {a.id: a for a in session.execute(select(AdAccount)).scalars().all()}
    customer_map = {c.id: c.name for c in session.execute(select(Customer)).scalars().all()}
    for campaign in campaigns:
        latest = _latest_snapshot(session, campaign.id)
        checkpoint = _latest_checkpoint(session, campaign.id)
        drift = _latest_drift(session, campaign.id)
        account = account_map.get(campaign.ad_account_id)
        rows.append(
            {
                "campaign_id": campaign.id,
                "meta_campaign_id": campaign.meta_campaign_id,
                "campaign_name": campaign.name,
                "customer_id": campaign.customer_id,
                "customer_name": customer_map.get(campaign.customer_id),
                "ad_account_id": account.meta_ad_account_id if account else None,
                "timezone_name": account.timezone_name if account else None,
                "meta_status": campaign.meta_status,
                "report_period_start": (
                    campaign.report_period_start.isoformat() if campaign.report_period_start else None
                ),
                "report_period_end": (
                    campaign.report_period_end.isoformat() if campaign.report_period_end else None
                ),
                "checkpoint_9h_spend": str(checkpoint.spend_amount) if checkpoint else None,
                "checkpoint_9h_at": _iso(checkpoint.snapshot_at) if checkpoint else None,
                "latest_spend": str(latest.spend_amount) if latest else None,
                "latest_spend_at": _iso(latest.snapshot_at) if latest else None,
                "drift_amount": str(drift.drift_amount) if drift else None,
                "recognition_status": campaign.recognition_status,
                "unverified": session.execute(
                    select(SpendSnapshot.id)
                    .where(SpendSnapshot.campaign_id == campaign.id, SpendSnapshot.data_status == DATA_UNVERIFIED)
                    .limit(1)
                ).scalar_one_or_none() is not None,
                "updated_at": _iso(latest.snapshot_at) if latest else None,
            }
        )
    return rows


def account_rows(session: Session) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for account in session.execute(select(AdAccount).order_by(AdAccount.id)).scalars().all():
        customer_id, customer_name, assignment_status, current_assignment_id = _current_customer(session, account.id)
        history = session.execute(
            select(AdAccountAssignment)
            .where(AdAccountAssignment.ad_account_id == account.id)
            .order_by(AdAccountAssignment.valid_from.desc())
        ).scalars().all()
        replaced_by = session.get(AdAccount, account.replaced_by_id) if account.replaced_by_id else None
        rows.append(
            {
                "account_id": account.id,
                "meta_ad_account_id": account.meta_ad_account_id,
                "name": account.name,
                "business_manager_id": account.business_manager_id,
                "timezone_name": account.timezone_name,
                "status": account.status,
                "restricted_at": _iso(account.restricted_at),
                "purchase_cost": str(account.purchase_cost) if account.purchase_cost is not None else None,
                "customer_id": customer_id,
                "customer_name": customer_name,
                "assignment_status": assignment_status,
                "current_assignment_id": current_assignment_id,
                "replaced_by": replaced_by.meta_ad_account_id if replaced_by else None,
                "assignment_history": [
                    {
                        "customer_id": h.customer_id,
                        "customer_name": customer_map_name(session, h.customer_id),
                        "valid_from": _iso(h.valid_from),
                        "valid_to": _iso(h.valid_to),
                    }
                    for h in history
                ],
            }
        )
    return rows


def customer_map_name(session: Session, customer_id: int) -> str | None:
    customer = session.get(Customer, customer_id)
    return customer.name if customer else None


def system_rows(session: Session) -> dict[str, Any]:
    last_sync = session.execute(
        select(SpendSnapshot.snapshot_at).order_by(SpendSnapshot.snapshot_at.desc()).limit(1)
    ).scalar_one_or_none()
    api_errors = session.execute(
        select(AuditLog)
        .where(AuditLog.action == "spend_api_error")
        .order_by(AuditLog.created_at.desc())
        .limit(10)
    ).scalars().all()
    missed = session.execute(
        select(AuditLog)
        .where(AuditLog.action == "checkpoint_missed")
        .order_by(AuditLog.created_at.desc())
        .limit(10)
    ).scalars().all()
    campaigns = session.execute(select(Campaign)).scalars().all()
    unverified = session.execute(
        select(SpendSnapshot).where(SpendSnapshot.data_status == DATA_UNVERIFIED)
        .order_by(SpendSnapshot.snapshot_at.desc())
        .limit(20)
    ).scalars().all()
    campaign_names = {c.id: c.meta_campaign_id for c in campaigns}
    return {
        "mode": build_connector().mode,
        "last_sync_at": _iso(last_sync),
        "api_errors": [
            {
                "entity": e.entity_id,
                "detail": e.detail.get("error") if e.detail else None,
                "at": _iso(e.created_at),
            }
            for e in api_errors
        ],
        "missed_checkpoints": [
            {
                "at": (e.detail or {}).get("checkpoint_at") or _iso(e.created_at),
            }
            for e in missed
        ],
        "campaigns_need_verification": [
            {"meta_campaign_id": c.meta_campaign_id, "name": c.name, "status": c.recognition_status}
            for c in campaigns
            if c.customer_id is None
        ],
        "unverified_snapshots": [
            {
                "meta_campaign_id": campaign_names.get(s.campaign_id, str(s.campaign_id)),
                "snapshot_at": _iso(s.snapshot_at),
                "spend_amount": str(s.spend_amount),
            }
            for s in unverified
        ],
    }
