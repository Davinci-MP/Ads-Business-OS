from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.customer import RECON_PROFIT_SHARE, Customer, utcnow
from app.models.finance import (
    ADJ_APPROVED,
    ADJ_APPLIED,
    ADJ_DRAFT,
    ENTRY_FINAL,
    ENTRY_MANUAL_ADJUSTMENT,
    ENTRY_SERVICE_FEE,
    ENTRY_TEMP,
    Approval,
    AuditLog,
    LedgerEntry,
    ManualAdjustment,
)
from app.models.spend import DATA_VERIFIED, DriftRecord, SpendSnapshot
from app.services.finance import compute_drift, compute_service_fee

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

PROFIT_SHARE_PENDING_MESSAGE = (
    "Công thức chia lợi nhuận 30/70 chưa được duyệt chính thức (Q-004/D-022). "
    "KHÔNG tự implement cho tới khi docs/DECISIONS.md có công thức."
)
MODE_DISABLED_MESSAGE = (
    "Chế độ điều chỉnh thủ công (30/70) mặc định TẮT; chỉ bật khi chủ dự án cấu hình cho khách được chọn (D-022)."
)


class ReconError(Exception):
    pass


class ModeNotEnabledError(ReconError):
    pass


class PolicyNotConfirmedError(ReconError):
    pass


def compute_profit_split(*args, **kwargs):
    raise PolicyNotConfirmedError(PROFIT_SHARE_PENDING_MESSAGE)


def _to_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _vn_date(value: datetime) -> date:
    return _to_aware_utc(value).astimezone(VN_TZ).date()


def _audit(
    session: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    session.add(
        AuditLog(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id, detail=detail)
    )


def get_current_spend_snapshot(session: Session, campaign_id: int) -> Optional[SpendSnapshot]:
    return session.execute(
        select(SpendSnapshot)
        .where(
            SpendSnapshot.campaign_id == campaign_id,
            SpendSnapshot.data_status == DATA_VERIFIED,
        )
        .order_by(SpendSnapshot.snapshot_at.desc(), SpendSnapshot.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_checkpoint_spend_snapshot(session: Session, campaign_id: int, at: datetime) -> Optional[SpendSnapshot]:
    target_date = _vn_date(at)
    rows = session.execute(
        select(SpendSnapshot).where(
            SpendSnapshot.campaign_id == campaign_id,
            SpendSnapshot.is_checkpoint_9h.is_(True),
        )
    ).scalars().all()
    for row in rows:
        if _vn_date(row.snapshot_at) == target_date:
            return row
    return None


def record_drift(session: Session, campaign_id: int, at: datetime, actor: str = "system") -> Optional[DriftRecord]:
    checkpoint = get_checkpoint_spend_snapshot(session, campaign_id, at)
    latest = get_current_spend_snapshot(session, campaign_id)
    if checkpoint is None or latest is None:
        return None
    drift = compute_drift(Decimal(latest.spend_amount), Decimal(checkpoint.spend_amount))
    existing = session.execute(
        select(DriftRecord).where(
            DriftRecord.campaign_id == campaign_id,
            DriftRecord.checkpoint_snapshot_id == checkpoint.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.latest_snapshot_id = latest.id
        existing.drift_amount = drift
        session.commit()
        return existing
    record = DriftRecord(
        campaign_id=campaign_id,
        checkpoint_snapshot_id=checkpoint.id,
        latest_snapshot_id=latest.id,
        drift_amount=drift,
        currency=latest.currency,
    )
    session.add(record)
    _audit(
        session,
        actor,
        "drift_recorded",
        "campaign",
        str(campaign_id),
        {"drift": str(drift), "checkpoint_snapshot_id": checkpoint.id},
    )
    session.commit()
    return record


def write_ledger_entry(
    session: Session,
    customer: Customer,
    entry_kind: str,
    period_start: date,
    period_end: date,
    amount: Decimal,
    currency: str = "VND",
    ref_type: Optional[str] = None,
    ref_id: Optional[str] = None,
    note: Optional[str] = None,
    actor: str = "system",
) -> LedgerEntry:
    rows = session.execute(
        select(LedgerEntry)
        .where(
            LedgerEntry.customer_id == customer.id,
            LedgerEntry.entry_kind == entry_kind,
            LedgerEntry.period_start == period_start,
        )
        .order_by(LedgerEntry.version.desc())
    ).scalars().all()
    if rows:
        user_final = next((r for r in rows if r.state == ENTRY_FINAL), None)
        if user_final is not None:
            return user_final
        version = rows[0].version + 1
    else:
        version = 1
    entry = LedgerEntry(
        customer_id=customer.id,
        entry_kind=entry_kind,
        amount=amount,
        currency=currency,
        period_start=period_start,
        period_end=period_end,
        version=version,
        state=ENTRY_TEMP,
        ref_type=ref_type,
        ref_id=ref_id,
        note=note,
    )
    session.add(entry)
    _audit(
        session,
        actor,
        "ledger_entry_created",
        "ledger_entry",
        f"{customer.id}:{entry_kind}:{period_start}:v{version}",
        {"amount": str(amount), "state": ENTRY_TEMP},
    )
    session.commit()
    return entry


def write_service_fee(
    session: Session,
    customer: Customer,
    period_start: date,
    period_end: date,
    actual_spend: Decimal,
    actor: str = "system",
) -> tuple[LedgerEntry, Decimal]:
    fee = compute_service_fee(Decimal(actual_spend), Decimal(customer.fee_rate))
    entry = write_ledger_entry(
        session,
        customer,
        ENTRY_SERVICE_FEE,
        period_start,
        period_end,
        fee,
        note=f"Phí {Decimal(customer.fee_rate) * 100}% trên chi tiêu thực {actual_spend}",
        actor=actor,
    )
    return entry, fee


def finalize_entry(session: Session, entry: LedgerEntry, approved_by: str) -> LedgerEntry:
    entry.state = ENTRY_FINAL
    session.add(
        Approval(
            entity_type="ledger_entry",
            entity_id=str(entry.id),
            status="APPROVED",
            requested_by=approved_by,
            approved_by=approved_by,
            approved_at=utcnow(),
        )
    )
    _audit(
        session,
        approved_by,
        "ledger_finalized",
        "ledger_entry",
        str(entry.id),
        {"amount": str(entry.amount), "kind": entry.entry_kind},
    )
    session.commit()
    return entry


def create_manual_adjustment(
    session: Session,
    customer_id: int,
    period_start: date,
    period_end: date,
    payload: dict[str, Any],
    created_by: str,
    note: Optional[str] = None,
) -> ManualAdjustment:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise ReconError("Không tìm thấy khách hàng")
    if customer.recon_mode != RECON_PROFIT_SHARE or not customer.profit_share_enabled:
        raise ModeNotEnabledError(MODE_DISABLED_MESSAGE)
    adjustment = ManualAdjustment(
        customer_id=customer.id,
        period_start=period_start,
        period_end=period_end,
        payload=payload,
        note=note,
        created_by=created_by,
    )
    session.add(adjustment)
    _audit(session, created_by, "manual_adjustment_created", "manual_adjustment", str(adjustment.id))
    session.commit()
    return adjustment


def approve_manual_adjustment(session: Session, adjustment_id: int, approved_by: str) -> ManualAdjustment:
    adjustment = session.get(ManualAdjustment, adjustment_id)
    if adjustment is None:
        raise ReconError("Không tìm thấy bản điều chỉnh")
    if adjustment.status != ADJ_DRAFT:
        raise ReconError("Chỉ bản DRAFT mới được phê duyệt")
    adjustment.status = ADJ_APPROVED
    adjustment.approved_by = approved_by
    adjustment.approved_at = utcnow()
    _audit(session, approved_by, "manual_adjustment_approved", "manual_adjustment", str(adjustment.id))
    session.commit()
    return adjustment


def apply_manual_adjustment(session: Session, adjustment_id: int) -> LedgerEntry:
    adjustment = session.get(ManualAdjustment, adjustment_id)
    if adjustment is None:
        raise ReconError("Không tìm thấy bản điều chỉnh")
    if adjustment.status != ADJ_APPROVED:
        raise ReconError("Bản điều chỉnh phải được APPROVED trước khi áp dụng")
    amount = Decimal(str(adjustment.payload.get("amount", "0")))
    currency = str(adjustment.payload.get("currency", "VND"))
    customer = session.get(Customer, adjustment.customer_id)
    entry = write_ledger_entry(
        session,
        customer,
        ENTRY_MANUAL_ADJUSTMENT,
        adjustment.period_start,
        adjustment.period_end,
        amount,
        currency=currency,
        ref_type="manual_adjustment",
        ref_id=str(adjustment.id),
        note=adjustment.note,
        actor=adjustment.approved_by or "system",
    )
    adjustment.status = ADJ_APPLIED
    _audit(session, adjustment.approved_by or "system", "manual_adjustment_applied", "manual_adjustment", str(adjustment.id))
    session.commit()
    return entry
