from datetime import datetime, timedelta, timezone

import alembic.command
import alembic.config
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.ad_account import AdAccount, AdAccountAssignment
from app.models.customer import Customer
from app.models.finance import AuditLog
from app.models.sheet_reports import (
    SheetReportCustomerLink, SheetReportSettings, SheetReportSnapshot, SheetReportSource, SheetReportTabDismissal,
)
from app.services import sheet_report_store as store
from app.services.customer_setup import SetupError, apply_setup, setup_proposals
from app.services.operations_overview import operations_list, operations_overview


@pytest.fixture
def db(tmp_path):
    database = tmp_path / "ops.db"
    cfg = alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    alembic.command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _tab(sheet_id, title, balance, accounts=(), profile="CONFIRMED_PARTIAL"):
    rows = [{"row_number": 5 + i, "business_date": f"2026-10-{i + 1:02d}", "account_id": acc, "account_currency": "USD",
             "cells": [{"address": f"E{5 + i}", "value": spend}], "missing_inputs": [], "status": "PREVIEW"}
            for i, (acc, spend) in enumerate(accounts)]
    totals = {"current_balance": {"value": balance}} if balance is not None else {}
    return {"source_sheet": title, "sheet_id": sheet_id, "profile_status": profile, "tab_source_totals": totals,
            "source_analysis": {"columns": [{"column_letter": "E", "header": "USD"}]}, "account_rows": rows}


def _setup(db, tabs, issues=()):
    source = SheetReportSource(period="2026-10", spreadsheet_id="wb1", name="s", mapping_version=store.MAPPING_VERSION,
                               mapping_config=store.MAPPING_CONFIG.copy(), active=True, sync_enabled=False)
    db.add(source)
    db.flush()
    db.add(SheetReportSettings(id=1, default_source_id=source.id))
    db.add(SheetReportSnapshot(source_id=source.id, read_at=datetime.now(timezone.utc), mapping_version=source.mapping_version,
                               mapping_config=source.mapping_config, quality="PARTIAL",
                               report={"customers": tabs, "issues": list(issues)}))
    db.commit()
    return source


def test_counts_unique_accounts_unlinked_tabs_and_card_equals_list(db):
    _setup(db, [_tab(1, "A", "-5", [("111", "0"), ("111", "4"), ("act_222", "0")]),
                _tab(2, "B", "50", [("333", "1")]), _tab(3, "C", None), _tab(4, "D", "7", profile="STRUCTURE_ERROR")])
    alice, bob = Customer(name="Alice", budget_alert_threshold_vnd=100), Customer(name="Bob")
    db.add_all([alice, bob])
    db.flush()
    db.add_all([SheetReportCustomerLink(source_id=1, sheet_id=2, source_title="B", customer_id=alice.id, active=True),
                SheetReportCustomerLink(source_id=1, sheet_id=1, source_title="A", customer_id=bob.id, active=True)])
    db.commit()
    data = operations_overview(db)
    metrics = data["metrics"]
    assert metrics["customers"]["count"] == 4 and metrics["customers"]["linked"] == 2
    assert metrics["accounts"] == {"count": 3, "spending": 2, "spend_unknown": 0}
    assert metrics["negative_balance"]["count"] == 1
    assert metrics["needs_topup"]["count"] == 1 and metrics["needs_topup"]["thresholds_missing"] == 1
    for metric, card in [("customers", "customers"), ("accounts", "accounts"), ("negative_balance", "negative_balance"),
                         ("needs_topup", "needs_topup"), ("accounts_spending", None), ("unlinked", None)]:
        if card:
            assert len(operations_list(db, metric)["rows"]) == metrics[card]["count"]
    assert {r["source_sheet"] for r in operations_list(db, "unlinked")["rows"]} == {"C", "D"}
    # số dư âm và nhắc nạp không trùng nhau; tab lỗi/ô trống không có số dư
    negative = {r["sheet_id"] for r in operations_list(db, "negative_balance")["rows"]}
    topup = {r["sheet_id"] for r in operations_list(db, "needs_topup")["rows"]}
    assert not negative & topup
    assert metrics["negative_balance"]["balance_missing"] == 2


def test_missing_threshold_and_missing_balance_are_not_zero_or_safe(db):
    _setup(db, [_tab(1, "A", None), _tab(2, "B", "0")])
    a, b = Customer(name="A"), Customer(name="B")
    db.add_all([a, b])
    db.flush()
    db.add_all([SheetReportCustomerLink(source_id=1, sheet_id=1, source_title="A", customer_id=a.id, active=True),
                SheetReportCustomerLink(source_id=1, sheet_id=2, source_title="B", customer_id=b.id, active=True)])
    db.commit()
    metrics = operations_overview(db)["metrics"]
    assert metrics["needs_topup"]["count"] == 0 and metrics["needs_topup"]["thresholds_missing"] == 2
    assert metrics["negative_balance"]["count"] == 0 and metrics["negative_balance"]["balance_missing"] == 1
    b.budget_alert_threshold_vnd = 0
    db.commit()
    assert operations_overview(db)["metrics"]["needs_topup"]["count"] == 1


def test_default_active_mock_campaign_stay_internal_and_not_confirmed(db):
    _setup(db, [_tab(1, "A", "1", [("999", "1")])])
    db.add(AdAccount(meta_ad_account_id="act_mock_1", name="m", timezone_name="UTC"))
    db.commit()
    data = operations_overview(db)
    assert data["internal"]["manual_status"] == {"updated": 0, "not_updated": 1}
    assert "campaign" not in data["metrics"]
    assert not any("campaign" in t["label"].lower() for t in data["tasks"])
    assert data["metrics"]["accounts"]["count"] == 1  # chỉ ID từ nguồn Sheets


def test_assigned_source_account_is_not_in_unassigned_task(db):
    _setup(db, [_tab(1, "A", "1", [("111", "1"), ("222", "1")])])
    cust, acc = Customer(name="X"), AdAccount(meta_ad_account_id="act_111", name="a", timezone_name="UTC")
    db.add_all([cust, acc])
    db.flush()
    db.add(AdAccountAssignment(customer_id=cust.id, ad_account_id=acc.id, valid_from=datetime.now(timezone.utc) - timedelta(days=1)))
    db.commit()
    assert [r["account_id"] for r in operations_list(db, "accounts_unassigned")["rows"]] == ["222"]


def test_no_default_source_and_no_snapshot_are_not_zero(db):
    assert operations_overview(db)["metrics"] is None
    source = SheetReportSource(period="2026-10", spreadsheet_id="w", name="s", mapping_version=store.MAPPING_VERSION,
                               mapping_config=store.MAPPING_CONFIG.copy(), active=True, sync_enabled=False)
    db.add(source)
    db.flush()
    db.add(SheetReportSettings(id=1, default_source_id=source.id))
    db.commit()
    assert operations_overview(db)["metrics"] is None


def test_setup_is_explicit_idempotent_and_never_writes_money(db):
    source = _setup(db, [_tab(1, "Khách A", "5"), _tab(2, "Tổng hợp", "1"), _tab(3, "Lỗi", None, profile="SOURCE_ERROR")])
    existing = Customer(name="S17.1-TEST")
    db.add(existing)
    db.commit()
    proposals = setup_proposals(db, source)
    assert all(r["status"] == "UNLINKED" for r in proposals["rows"])
    assert db.scalar(select(func.count()).select_from(SheetReportCustomerLink)) == 0
    items = [{"sheet_id": 1, "action": "create", "name": "Khách A", "expected_source_sheet": "Khách A"},
             {"sheet_id": 2, "action": "dismiss", "expected_source_sheet": "Tổng hợp"}]
    first = apply_setup(db, source, items)
    second = apply_setup(db, source, items)
    assert first["results"][0]["result"] == "created_and_linked" and second["results"][0]["result"] == "unchanged"
    assert db.scalar(select(func.count()).select_from(Customer)) == 2
    created = db.scalar(select(Customer).where(Customer.name == "Khách A"))
    assert created.budget_alert_threshold_vnd is None and created.telegram_chat_id is None
    assert db.scalar(select(func.count()).select_from(AdAccountAssignment)) == 0
    assert db.scalar(select(func.count()).select_from(SheetReportTabDismissal)) == 1
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "sheet_tab_linked")) == 1
    # tab bỏ qua không còn là khách trong tổng quan
    assert operations_overview(db)["metrics"]["customers"]["count"] == 2


def test_setup_rejects_batch_atomically_and_stale_names(db):
    source = _setup(db, [_tab(1, "A", "5"), _tab(2, "B", "5"), _tab(3, "Lỗi", None, profile="STRUCTURE_ERROR")])
    other = Customer(name="Other")
    db.add(other)
    db.commit()
    with pytest.raises(SetupError):
        apply_setup(db, source, [{"sheet_id": 1, "action": "create", "name": "New", "expected_source_sheet": "A"},
                                 {"sheet_id": 3, "action": "link", "customer_id": other.id, "expected_source_sheet": "Lỗi"}])
    assert db.scalar(select(func.count()).select_from(Customer)) == 1
    with pytest.raises(SetupError):
        apply_setup(db, source, [{"sheet_id": 1, "action": "link", "customer_id": other.id, "expected_source_sheet": "Tên cũ"}])
    with pytest.raises(SetupError):
        apply_setup(db, source, [{"sheet_id": 1, "action": "link", "customer_id": other.id, "expected_source_sheet": "A"},
                                 {"sheet_id": 2, "action": "link", "customer_id": other.id, "expected_source_sheet": "B"}])
    with pytest.raises(SetupError):
        apply_setup(db, source, [{"sheet_id": 1, "action": "create", "name": "Other", "expected_source_sheet": "A"}])
    assert db.scalar(select(func.count()).select_from(SheetReportCustomerLink)) == 0
    apply_setup(db, source, [{"sheet_id": 1, "action": "link", "customer_id": other.id, "expected_source_sheet": "A"}])
    with pytest.raises(SetupError):
        apply_setup(db, source, [{"sheet_id": 1, "action": "dismiss", "expected_source_sheet": "A"}])
    with pytest.raises(SetupError):
        apply_setup(db, source, [{"sheet_id": 1, "action": "link", "customer_id": other.id + 99, "expected_source_sheet": "A"}])


def test_setup_warns_same_name_without_auto_linking(db):
    source = _setup(db, [_tab(1, "Bob", "5")])
    db.add(Customer(name="bob"))
    db.commit()
    row = setup_proposals(db, source)["rows"][0]
    assert row["status"] == "UNLINKED" and row["customer_id"] is None and row["name_exists"]
