from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models.customer import Customer, DEFAULT_FEE_RATE, RECON_SIMPLE_FEE
from app.models.finance import ENTRY_FINAL, ENTRY_SERVICE_FEE, LedgerEntry
from app.services import recon
from app.services.finance import compute_drift, compute_service_fee, compute_total_with_fee
from conftest import make_customer

PERIOD_START = date(2026, 10, 25)
PERIOD_END = date(2026, 10, 25)


def test_default_fee_rate_is_4pct_on_actual_spend():
    assert DEFAULT_FEE_RATE == Decimal("0.04")


def test_fee_and_total_formulas():
    assert compute_service_fee(Decimal("1000.00")) == Decimal("40")
    assert compute_total_with_fee(Decimal("1000.00")) == Decimal("1040")
    assert compute_service_fee(Decimal("1250.75")) == Decimal("50.03")


def test_fee_recalculated_on_current_spend():
    assert compute_service_fee(Decimal("1500"), Decimal("0.04")) == Decimal("60")


def test_drift_formula_current_minus_9h_checkpoint():
    assert compute_drift(Decimal("1300.00"), Decimal("1000.00")) == Decimal("300")
    assert compute_drift(Decimal("900.00"), Decimal("1000.00")) == Decimal("-100")


def test_normal_customer_gets_default_simple_fee_mode(db):
    customer = make_customer(db, "KH-THONG-THUONG-01")
    assert customer.fee_rate == Decimal("0.04")
    assert customer.recon_mode == RECON_SIMPLE_FEE
    assert customer.profit_share_enabled is False


def test_service_fee_is_separate_ledger_kind(db):
    customer = make_customer(db, "KH-FEE-KHOAN-01")
    entry, fee = recon.write_service_fee(db, customer, PERIOD_START, PERIOD_END, Decimal("2000.00"))
    actual = recon.write_ledger_entry(
        db, customer, "ACTUAL_SPEND", PERIOD_START, PERIOD_END, Decimal("2000.00"), currency="USD"
    )
    assert fee == Decimal("80.00")
    assert entry.entry_kind == ENTRY_SERVICE_FEE
    assert actual.entry_kind == "ACTUAL_SPEND"
    assert entry.amount == Decimal("80.00")
    assert actual.amount == Decimal("2000.00")


def test_fee_recalc_creates_new_temp_version_and_keeps_final_lock(db):
    customer = make_customer(db, "KH-FEE-RECALC-01")
    period_start = period_end = date(2026, 10, 26)
    first, fee1 = recon.write_service_fee(db, customer, period_start, period_end, Decimal("1000.00"))
    assert first.version == 1 and fee1 == Decimal("40")
    second, fee2 = recon.write_service_fee(db, customer, period_start, period_end, Decimal("1200.00"))
    assert second.version == 2 and fee2 == Decimal("48") and second.state == "TEMP"
    recon.finalize_entry(db, second, approved_by="owner")
    locked, _ = recon.write_service_fee(db, customer, period_start, period_end, Decimal("5000.00"))
    assert locked.id == second.id
    assert locked.state == ENTRY_FINAL
    assert locked.amount == Decimal("48")
    rows = db.execute(
        select(LedgerEntry).where(
            LedgerEntry.customer_id == customer.id, LedgerEntry.entry_kind == ENTRY_SERVICE_FEE
        )
    ).scalars().all()
    assert sorted(r.version for r in rows) == [1, 2]
