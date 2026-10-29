from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.finance import ENTRY_MANUAL_ADJUSTMENT, ADJ_APPROVED, ADJ_APPLIED, LedgerEntry, ManualAdjustment
from app.services import recon
from app.services.recon import ModeNotEnabledError, PolicyNotConfirmedError, ReconError
from conftest import make_customer, make_profit_share_customer

PERIOD_START = date(2026, 10, 20)
PERIOD_END = date(2026, 10, 26)
PAYLOAD = {"amount": "3500000", "currency": "VND", "source": "manual-by-owner"}


def test_manual_adjustment_rejected_for_normal_customer(db):
    customer = make_customer(db, "KH-ADJ-NORMAL-01")
    with pytest.raises(ModeNotEnabledError):
        recon.create_manual_adjustment(
            db, customer.id, PERIOD_START, PERIOD_END, PAYLOAD, created_by="owner"
        )
    rows = db.execute(select(ManualAdjustment)).scalars().all()
    assert rows == []


def test_manual_adjustment_flow_for_enabled_customer(db):
    customer = make_profit_share_customer(db, "KH-ADJ-PROFIT-01")
    adjustment = recon.create_manual_adjustment(
        db, customer.id, PERIOD_START, PERIOD_END, PAYLOAD, created_by="owner"
    )
    assert adjustment.status == "DRAFT"
    with pytest.raises(ReconError):
        recon.apply_manual_adjustment(db, adjustment.id)
    approved = recon.approve_manual_adjustment(db, adjustment.id, approved_by="owner")
    assert approved.status == ADJ_APPROVED
    entry = recon.apply_manual_adjustment(db, adjustment.id)
    assert adjustment.status == ADJ_APPLIED
    assert entry.entry_kind == ENTRY_MANUAL_ADJUSTMENT
    assert entry.amount == Decimal("3500000")
    assert entry.ref_id == str(adjustment.id)


def test_actual_spend_untouched_by_manual_adjustment(db):
    customer = make_profit_share_customer(db, "KH-ADJ-PROFIT-02")
    adjustment = recon.create_manual_adjustment(
        db, customer.id, PERIOD_START, PERIOD_END, {"amount": "1"}, created_by="owner"
    )
    recon.approve_manual_adjustment(db, adjustment.id, approved_by="owner")
    recon.apply_manual_adjustment(db, adjustment.id)
    actual_rows = db.execute(
        select(LedgerEntry).where(
            LedgerEntry.customer_id == customer.id, LedgerEntry.entry_kind == "ACTUAL_SPEND"
        )
    ).scalars().all()
    assert actual_rows == []


def test_profit_split_formula_blocked_until_ratified():
    with pytest.raises(PolicyNotConfirmedError):
        recon.compute_profit_split(Decimal("1000"), Decimal("0.7"))


def test_reapply_after_apply_is_rejected(db):
    customer = make_profit_share_customer(db, "KH-ADJ-PROFIT-03")
    adjustment = recon.create_manual_adjustment(
        db, customer.id, PERIOD_START, PERIOD_END, PAYLOAD, created_by="owner"
    )
    recon.approve_manual_adjustment(db, adjustment.id, approved_by="owner")
    recon.apply_manual_adjustment(db, adjustment.id)
    with pytest.raises(ReconError):
        recon.apply_manual_adjustment(db, adjustment.id)
