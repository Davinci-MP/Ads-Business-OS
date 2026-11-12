from datetime import datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import socket
import time

import alembic.command
import alembic.config
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, OperationalError
from fastapi.testclient import TestClient

from app.connectors.sheets import SheetsAPIError
from app.api.v1 import sheet_report_sources as source_api
from app.db import get_db
from app.main import app
from app.models.customer import Customer
from app.models.ad_account import AdAccount, AdAccountAssignment
from app.models.finance import AuditLog
from app.models.sheet_reports import (
    SheetReportClosure, SheetReportCustomerLink, SheetReportSnapshot,
    SheetReportSource, SheetReportSyncAttempt,
)
from app.services import sheet_report_store as store
from app.services.sheet_year_summary import build_year_summary
from app.services.customer_sheets import customer_sheets_overview
from app.services.reports import _account_costs, company_kpi
from app.services.accounts import AccountError, transfer_account
from app.jobs import sheet_reports as scheduler


@pytest.fixture
def db(tmp_path):
    database = tmp_path / "report-test.db"
    cfg = alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    alembic.command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _source(db, period="2026-10", name="first"):
    source = SheetReportSource(period=period, spreadsheet_id=name, name=name,
                               mapping_version=store.MAPPING_VERSION, mapping_config=store.MAPPING_CONFIG.copy(), active=True, sync_enabled=True)
    db.add(source)
    db.commit()
    return source


def _report(value="10", sheet_id=7, title="SYNTHETIC"):
    return {
        "summary_tabs": [{"title": "TỔNG", "header_row": 1, "rows": [
            {"summary_row": 1, "cells": [{"address": f"{col}1", "value": label}
             for col, label in zip("ABCDEFG", ["Tên", "ĐÃ BANK", "Kỳ trước", "RUN", "PHÍ", "TỔNG", "CÒN"])]},
            {"summary_row": 30, "customer_label": "TỔNG", "cells": [
                {"address": "C30", "value": value}, {"address": "G30", "value": value}]}]}],
        "read_at": datetime.now(timezone.utc).isoformat(), "status": "PARTIAL", "mode": "live",
        "customers": [{"source_sheet": title, "sheet_id": sheet_id, "profile_status": "NEEDS_CONFIRMATION",
                       "tab_source_totals": {"current_balance": {"value": value}},
                       "opening_balance": {"value": value}}],
    }


def test_customer_overview_uses_only_confirmed_source_link_and_latest_snapshot(db):
    source = _source(db)
    other = _source(db, period="2026-11", name="other")
    alice = Customer(name="Alice")
    similar = Customer(name="Alice renamed")
    db.add_all([alice, similar])
    db.flush()
    db.add(SheetReportCustomerLink(source_id=source.id, sheet_id=7, source_title="SYNTHETIC",
                                   customer_id=alice.id, active=True))
    for owner, value in [(source, "10"), (source, "-20.50"), (other, "999")]:
        db.add(SheetReportSnapshot(source_id=owner.id, read_at=datetime.now(timezone.utc),
                                   mapping_version=owner.mapping_version, mapping_config=owner.mapping_config,
                                   quality="PARTIAL", report=_report(value)))
    db.flush()
    account = AdAccount(meta_ad_account_id="act_customer_overview", name="a", timezone_name="UTC")
    db.add(account)
    db.flush()
    now = datetime.now(timezone.utc)
    db.add(AdAccountAssignment(customer_id=alice.id, ad_account_id=account.id,
                               valid_from=now - timedelta(days=1)))
    db.add(SheetReportSyncAttempt(source_id=source.id, status="ERROR", error="read failed", trigger="MANUAL"))
    db.commit()
    result = customer_sheets_overview(db, source)
    rows = {item["customer_id"]: item for item in result["customers"]}
    assert rows[alice.id]["current_balance"] == "-20.50"
    assert rows[alice.id]["budget_deposits_vnd"] is None
    assert rows[alice.id]["account_count"] == 1
    assert rows[similar.id]["link_status"] == "UNLINKED"
    assert rows[similar.id]["current_balance"] is None
    assert result["last_attempt"]["status"] == "ERROR"
    assert result["period"] == "2026-10"
    assert customer_sheets_overview(db, other)["customers"][0]["current_balance"] is None


def test_customer_overview_refuses_renamed_tab_and_overlapping_assignments(db):
    source = _source(db)
    alice, bob = Customer(name="Alice"), Customer(name="Bob")
    db.add_all([alice, bob])
    db.flush()
    db.add(SheetReportCustomerLink(source_id=source.id, sheet_id=7, source_title="OLD",
                                   customer_id=alice.id, active=True))
    db.add(SheetReportSnapshot(source_id=source.id, read_at=datetime.now(timezone.utc),
                               mapping_version=source.mapping_version, mapping_config=source.mapping_config,
                               quality="PARTIAL", report=_report("-5", title="NEW")))
    account = AdAccount(meta_ad_account_id="act_conflict", name="a", timezone_name="UTC")
    db.add(account)
    db.flush()
    for customer in (alice, bob):
        db.add(AdAccountAssignment(customer_id=customer.id, ad_account_id=account.id,
                                   valid_from=datetime.now(timezone.utc) - timedelta(days=1),
                                   valid_to=(datetime.now(timezone.utc) + timedelta(days=1)) if customer is bob else None))
    db.commit()
    rows = {item["customer_id"]: item for item in customer_sheets_overview(db, source)["customers"]}
    assert rows[alice.id]["link_status"] == "LINK_REVIEW"
    assert rows[alice.id]["current_balance"] is None
    assert rows[alice.id]["account_count"] == 0
    assert rows[alice.id]["conflicting_accounts"] == 1
    assert rows[bob.id]["conflicting_accounts"] == 1


def test_customer_overview_ignores_future_and_finished_assignments(db):
    source = _source(db)
    customer = Customer(name="Alice")
    db.add(customer)
    account = AdAccount(meta_ad_account_id="act_history", name="a", timezone_name="UTC")
    db.add(account)
    db.flush()
    now = datetime.now(timezone.utc)
    db.add_all([
        AdAccountAssignment(customer_id=customer.id, ad_account_id=account.id,
                            valid_from=now - timedelta(days=2), valid_to=now - timedelta(days=1)),
        AdAccountAssignment(customer_id=customer.id, ad_account_id=account.id,
                            valid_from=now + timedelta(days=1)),
    ])
    db.commit()
    row = customer_sheets_overview(db, source)["customers"][0]
    assert row["account_count"] == 0
    assert row["conflicting_accounts"] == 0


def test_budget_threshold_is_optional_audited_and_uses_exact_sheet_balance(db):
    source = _source(db)
    customer = Customer(name="Alice")
    db.add(customer)
    db.flush()
    db.add(SheetReportCustomerLink(source_id=source.id, sheet_id=7, source_title="SYNTHETIC",
                                   customer_id=customer.id, active=True))
    db.add(SheetReportSnapshot(source_id=source.id, read_at=datetime.now(timezone.utc),
                               mapping_version=source.mapping_version, mapping_config=source.mapping_config,
                               quality="PARTIAL", report=_report("100.01")))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        url = f"/api/v1/customers/{customer.id}/budget-alert"
        row = customer_sheets_overview(db, source)["customers"][0]
        assert row["budget_alert_threshold_vnd"] is None
        assert row["low_balance"] is False
        for invalid in ("-1", "1.001", "NaN"):
            assert client.patch(url, json={"threshold_vnd": invalid}).status_code == 422
        assert client.patch(url, json={"threshold_vnd": "100.00"}).status_code == 200
        assert customer_sheets_overview(db, source)["customers"][0]["low_balance"] is False
        assert client.patch(url, json={"threshold_vnd": "100.01"}).status_code == 200
        assert customer_sheets_overview(db, source)["customers"][0]["low_balance"] is True
        assert client.patch(url, json={"threshold_vnd": None}).status_code == 200
        row = customer_sheets_overview(db, source)["customers"][0]
        assert row["budget_alert_threshold_vnd"] is None
        assert row["low_balance"] is False
        audits = db.scalars(select(AuditLog).where(AuditLog.action == "customer_budget_alert_threshold_set")).all()
        assert [item.detail["value"] for item in audits] == ["100.00", "100.01", None]
    finally:
        app.dependency_overrides.clear()


def test_legacy_account_costs_without_currency_are_not_summed(db):
    db.add_all([
        AdAccount(meta_ad_account_id="act_legacy_a", name="a", timezone_name="UTC", purchase_cost=Decimal("10")),
        AdAccount(meta_ad_account_id="act_legacy_b", name="b", timezone_name="UTC", purchase_cost=Decimal("20")),
    ])
    db.commit()
    result = _account_costs(db, None, None)
    assert result["count"] == 2
    assert result["amount"] is None
    assert result["data_state"] == "CHƯA ĐỦ DỮ LIỆU"
    kpi = company_kpi(db)
    assert kpi["account_costs"]["currency"] is None
    assert kpi["profit_provisional"]["amount"] is None


def test_concurrent_transfers_do_not_create_two_open_assignments(db):
    alice, bob, cara = Customer(name="Alice"), Customer(name="Bob"), Customer(name="Cara")
    account = AdAccount(meta_ad_account_id="act_concurrent_transfer", name="a", timezone_name="UTC")
    db.add_all([alice, bob, cara, account])
    db.flush()
    initial = AdAccountAssignment(customer_id=alice.id, ad_account_id=account.id,
                                  valid_from=datetime.now(timezone.utc) - timedelta(days=1))
    db.add(initial)
    db.commit()
    account_id, initial_id = account.id, initial.id
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    barrier = Barrier(2)
    def run(customer_id):
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                from app.api.v1.dashboard import _lock_sqlite_assignments
                _lock_sqlite_assignments(session)
                transfer_account(session, account_id, customer_id, initial_id)
                session.commit()
                return "committed"
            except (AccountError, IntegrityError, OperationalError):
                session.rollback()
                return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [bob.id, cara.id]))
    db.expire_all()
    history = db.scalars(select(AdAccountAssignment).where(AdAccountAssignment.ad_account_id == account_id)).all()
    assert sorted(results) == ["committed", "rejected"]
    assert len(history) == 2
    assert sum(item.valid_to is None for item in history) == 1
    assert db.scalar(select(AuditLog).where(AuditLog.action == "account_transferred")) is not None


def test_sync_history_preserves_prior_snapshot_after_change_and_error(db, monkeypatch):
    source = _source(db)
    values = iter([_report("10"), _report("12"), SheetsAPIError("test read error")])
    def read(*args):
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(store, "read_source_report", read)
    first = store.sync_source(db, source.id, "MANUAL")
    second = store.sync_source(db, source.id, "SCHEDULED")
    error = store.sync_source(db, source.id, "MANUAL")
    assert first.snapshot_id != second.snapshot_id
    assert error.status == "ERROR"
    assert store.latest_snapshot(db, source.id).report["customers"][0]["tab_source_totals"]["current_balance"]["value"] == "12"
    assert len(db.scalars(select(SheetReportSnapshot)).all()) == 2
    assert len(db.scalars(select(SheetReportSyncAttempt)).all()) == 3


def test_confirmed_mapping_is_scoped_and_preserves_history_and_closure(db, monkeypatch):
    source = _source(db)
    other = _source(db, period="2026-11", name="other")
    monkeypatch.setattr(store, "read_source_report", lambda *args: _report())
    old_attempt = store.sync_source(db, source.id, "MANUAL")
    old = db.get(SheetReportSnapshot, old_attempt.snapshot_id)
    closure = SheetReportClosure(source_id=source.id, snapshot_id=old.id)
    db.add(closure)
    db.commit()
    store.confirm_current_source_mapping(db, source.id)
    store.confirm_current_source_mapping(db, source.id)
    with pytest.raises(ValueError):
        store.confirm_current_source_mapping(db, other.id)
    new_attempt = store.sync_source(db, source.id, "MANUAL")
    new = db.get(SheetReportSnapshot, new_attempt.snapshot_id)
    db.refresh(old)
    db.refresh(closure)
    assert other.mapping_version == store.MAPPING_VERSION
    assert old.mapping_version == store.MAPPING_VERSION
    assert old.mapping_config == store.MAPPING_CONFIG
    assert new.mapping_version == store.CONFIRMED_MAPPING_VERSION
    assert new.mapping_config == store.CONFIRMED_MAPPING_CONFIG
    assert closure.snapshot_id == old.id
    assert len(db.scalars(select(SheetReportSnapshot).where(SheetReportSnapshot.source_id == source.id)).all()) == 2


def test_separator_confirmation_is_scoped_locked_and_preserves_closure(db, monkeypatch):
    source = _source(db)
    other = _source(db, period="2026-11", name="other")
    store.confirm_current_source_mapping(db, source.id)
    monkeypatch.setattr(store, "read_source_report", lambda *args: _report())
    old_attempt = store.sync_source(db, source.id, "MANUAL")
    old = db.get(SheetReportSnapshot, old_attempt.snapshot_id)
    closure = SheetReportClosure(source_id=source.id, snapshot_id=old.id)
    db.add(closure)
    db.commit()
    with store.source_lock(db, source.id):
        with pytest.raises(store.SyncBusy):
            store.confirm_separator_mapping(db, source.id)
    store.confirm_separator_mapping(db, source.id)
    store.confirm_separator_mapping(db, source.id)
    with pytest.raises(ValueError):
        store.confirm_separator_mapping(db, other.id)
    new_attempt = store.sync_source(db, source.id, "MANUAL")
    new = db.get(SheetReportSnapshot, new_attempt.snapshot_id)
    db.refresh(old)
    db.refresh(closure)
    assert old.mapping_version == store.CONFIRMED_MAPPING_VERSION
    assert old.mapping_config == store.CONFIRMED_MAPPING_CONFIG
    assert new.mapping_config == store.SEPARATOR_MAPPING_CONFIG
    assert closure.snapshot_id == old.id
    assert other.mapping_version == store.MAPPING_VERSION


def test_hidden_customer_disappears_only_from_new_snapshot(db, monkeypatch):
    source = _source(db)
    initial = _report()
    initial["customers"].append({"sheet_id": 88, "source_sheet": "HIDDEN_LATER"})
    after = _report()
    reports = iter([initial, after])
    monkeypatch.setattr(store, "read_source_report", lambda *args: next(reports))
    first = store.sync_source(db, source.id, "MANUAL")
    second = store.sync_source(db, source.id, "SCHEDULED")
    assert len(db.get(SheetReportSnapshot, first.snapshot_id).report["customers"]) == 2
    assert len(db.get(SheetReportSnapshot, second.snapshot_id).report["customers"]) == 1


def test_cross_connection_lock_prevents_overlap(db):
    source = _source(db)
    with store.source_lock(db, source.id):
        with pytest.raises(store.SyncBusy):
            with store.source_lock(db, source.id):
                pass
    with store.source_lock(db, source.id):
        pass


def test_interrupted_attempt_recovers_after_restart(db, monkeypatch):
    source = _source(db)
    old = SheetReportSyncAttempt(source_id=source.id, status="RUNNING", trigger="SCHEDULED")
    db.add(old)
    db.commit()
    monkeypatch.setattr(store, "read_source_report", lambda *args: _report())
    store.sync_source(db, source.id, "SCHEDULED")
    db.refresh(old)
    assert old.status == "INTERRUPTED"
    assert old.finished_at is not None


def test_source_and_unchanged_snapshots_survive_session_restart(db, monkeypatch):
    source = _source(db)
    monkeypatch.setattr(store, "read_source_report", lambda *args: _report())
    store.sync_source(db, source.id, "MANUAL")
    store.sync_source(db, source.id, "SCHEDULED")
    source_id = source.id
    engine = db.get_bind()
    db.close()
    reopened = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        assert reopened.get(SheetReportSource, source_id).sync_enabled is True
        snapshots = reopened.scalars(select(SheetReportSnapshot).where(SheetReportSnapshot.source_id == source_id)).all()
        # Cơ chế deduplication: dữ liệu không đổi chỉ lưu 1 snapshot và tái sử dụng
        assert len(snapshots) == 1
        assert snapshots[0].report["customers"] is not None
        attempts = reopened.scalars(select(SheetReportSyncAttempt).where(SheetReportSyncAttempt.source_id == source_id)).all()
        assert len(attempts) == 2
        assert attempts[0].snapshot_id == attempts[1].snapshot_id == snapshots[0].id
        assert snapshots[0].mapping_config == store.MAPPING_CONFIG
    finally:
        reopened.close()


def test_year_summary_uses_one_snapshot_per_active_month_and_never_adds_balances(db, monkeypatch):
    january = _source(db, "2026-01", "jan")
    february = _source(db, "2026-02", "feb")
    old_march = _source(db, "2026-03", "old-mar")

    def report(spend, balance, opening, receipts):
        result = _report(balance)
        customer = result["customers"][0]
        customer["opening_balance"] = {"value": opening, "source": "J1"}
        customer["tab_source_totals"].update({
            "budget_deposits_vnd": {"value": "0", "source": "K1"},
            "spend_vnd": {"value": spend, "source": "F1"},
            "fee": {"value": "0.49", "source": "G1"},
            "billing_total": {"value": spend, "source": "H1"},
        })
        customer["deposits"] = receipts
        result["summary_tabs"][0]["rows"][1]["cells"] = [
            {"address": f"{col}30", "value": val}
            for col, val in zip("BCDEFG", ["0", opening, spend, "0.49", spend, balance])
        ]
        customer["usdt_receipts_state"] = "HAS_RECORDS" if receipts else "NO_RECORDED"
        return result

    reports = iter([
        report("0.49", "100", "10", [{"included": True, "amount_usdt": "1.25", "business_date": "2026-01-03", "source_cells": ["J4"]}]),
        report("99", "999", "99", []),
        report("0.49", "-20", "100", []),
        report("500", "500", "500", []),
        report("0", "0", "-20", []),
    ])
    monkeypatch.setattr(store, "read_source_report", lambda *args: next(reports))
    january_first = store.sync_source(db, january.id, "MANUAL")
    db.add(SheetReportClosure(source_id=january.id, snapshot_id=january_first.snapshot_id))
    db.commit()
    january_second = store.sync_source(db, january.id, "MANUAL")
    store.sync_source(db, february.id, "MANUAL")
    store.sync_source(db, old_march.id, "MANUAL")
    old_march.active = False
    db.commit()
    march = _source(db, "2026-03", "new-mar")
    store.sync_source(db, march.id, "MANUAL")

    result = build_year_summary(db, 2026)
    assert result["months_with_data"] == 3
    # current: bản chốt KHÔNG tự thắng — dùng bản đọc mới nhất của nguồn hiệu lực, kèm closure_note.
    assert result["months"][0]["state"] == "PROVISIONAL"
    assert result["months"][0]["snapshot_id"] == january_second.snapshot_id
    assert result["months"][0].get("closure_note")
    assert result["months"][1]["state"] == "PROVISIONAL"
    assert result["months"][2]["source_id"] == march.id
    assert result["months"][3]["state"] == "MISSING_SOURCE"
    assert result["flows"]["spend_vnd"]["value"] == "99.49"
    assert result["flows"]["spend_vnd"]["months_with_value"] == 3
    assert result["flows"]["spend_vnd"]["status"] == "PARTIAL"
    assert result["flows"]["usdt_received"]["value"] == "0"
    assert result["flows"]["usdt_received"]["months_with_value"] == 3
    assert result["opening_balance"]["metric"]["value"] == "99"
    assert result["closing_balance"]["period"] == "2026-03"
    assert result["closing_balance"]["metric"]["value"] == "0"


def test_year_summary_missing_january_and_zero_are_distinct(db, monkeypatch):
    source = _source(db, "2026-10")
    monkeypatch.setattr(store, "read_source_report", lambda *args: _report("0"))
    store.sync_source(db, source.id, "MANUAL")
    result = build_year_summary(db, 2026)
    assert result["opening_balance"] is None
    assert result["closing_balance"]["period"] == "2026-10"
    assert result["closing_balance"]["metric"]["value"] == "0"
    assert result["flows"]["spend_vnd"]["value"] is None
    assert result["months_with_data"] == 1


def test_year_summary_current_uses_newest_active_read_not_closed_snapshot(db, monkeypatch):
    old = _source(db, "2026-01", "closed-old")
    monkeypatch.setattr(store, "read_source_report", lambda *args: _report("10"))
    first = store.sync_source(db, old.id, "MANUAL")
    db.add(SheetReportClosure(source_id=old.id, snapshot_id=first.snapshot_id))
    old.active = False
    db.commit()
    replacement = _source(db, "2026-01", "new-link")
    monkeypatch.setattr(store, "read_source_report", lambda *args: _report("20"))
    second = store.sync_source(db, replacement.id, "MANUAL")
    def failed_read(*args):
        raise SheetsAPIError("synthetic read failure")
    monkeypatch.setattr(store, "read_source_report", failed_read)
    store.sync_source(db, replacement.id, "MANUAL")
    # current: nguồn hiệu lực có bản đọc thành công mới nhất (bản "20") — không tự quay về bản chốt của nguồn đã thay.
    result = build_year_summary(db, 2026)
    january = result["months"][0]
    assert january["source_id"] == replacement.id
    assert january["snapshot_id"] == second.snapshot_id
    assert january["state"] == "PROVISIONAL"
    assert january.get("closure_note")
    assert january["active_source_id"] == replacement.id
    assert january["last_attempt"]["status"] == "ERROR"
    assert january["latest_read_at"] == db.get(SheetReportSnapshot, second.snapshot_id).read_at
    assert result["opening_balance"]["metric"]["value"] == "20"
    db.add(SheetReportClosure(source_id=replacement.id, snapshot_id=second.snapshot_id))
    db.commit()
    result = build_year_summary(db, 2026)
    assert result["months"][0]["state"] == "CONFLICTING_CLOSURES"
    assert result["opening_balance"] is None


def test_sheets_scheduler_runs_on_start_then_every_15_minutes_without_meta(db, monkeypatch):
    source = _source(db)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    monkeypatch.setattr(scheduler.settings, "sheets_scheduler_enabled", True)
    monkeypatch.setattr(scheduler.settings, "sheets_scheduler_lock_port", port)
    monkeypatch.setattr(scheduler, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(store, "read_source_report", lambda *args: _report())
    scheduler.start_sheet_scheduler()
    try:
        jobs = scheduler._scheduler.get_jobs()
        jobs_by_id = {job.id: job for job in jobs}
        assert set(jobs_by_id) == {"sheets_reports", "customer_sheets_sync"}
        assert jobs_by_id["sheets_reports"].trigger.interval == timedelta(seconds=scheduler.TICK_SECONDS)
        assert jobs_by_id["customer_sheets_sync"].trigger.interval == timedelta(seconds=scheduler.TICK_SECONDS)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            db.expire_all()
            if store.latest_snapshot(db, source.id):
                break
            time.sleep(0.25)
        assert store.latest_snapshot(db, source.id) is not None
        assert db.scalar(select(SheetReportSyncAttempt).where(
            SheetReportSyncAttempt.source_id == source.id)).trigger == "SCHEDULED"
    finally:
        scheduler.stop_sheet_scheduler()


def test_scheduler_tick_only_syncs_due_sources_and_partial_does_not_loop(db, monkeypatch):
    source = _source(db)
    monkeypatch.setattr(scheduler, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    calls = []

    def fake_read(*args):
        calls.append(1)
        return _report()

    monkeypatch.setattr(store, "read_source_report", fake_read)
    start = datetime.now()
    scheduler.sync_enabled_sources(start)
    assert len(calls) == 1
    for seconds in (5, 40, 300, 14 * 60):
        scheduler.sync_enabled_sources(start + timedelta(seconds=seconds))
    assert len(calls) == 1
    scheduler.sync_enabled_sources(start + timedelta(minutes=16))
    assert len(calls) == 2
    rows = db.scalars(select(SheetReportSyncAttempt).where(SheetReportSyncAttempt.source_id == source.id)).all()
    assert [row.trigger for row in rows] == ["SCHEDULED", "SCHEDULED"]
    assert {row.status for row in rows} == {"PARTIAL"}


def test_scheduler_counts_manual_attempt_and_backs_off_after_errors(db, monkeypatch):
    source = _source(db)
    monkeypatch.setattr(scheduler, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(store, "read_source_report", lambda *args: _report())
    store.sync_source(db, source.id, "MANUAL")
    calls = []
    monkeypatch.setattr(store, "read_source_report", lambda *args: calls.append(1) or (_ for _ in ()).throw(SheetsAPIError("boom")))
    now = datetime.now()
    scheduler.sync_enabled_sources(now + timedelta(minutes=1))
    assert calls == []
    scheduler.sync_enabled_sources(now + timedelta(minutes=16))
    assert len(calls) == 1
    db.expire_all()
    rows = db.scalars(select(SheetReportSyncAttempt).order_by(SheetReportSyncAttempt.id)).all()
    assert [row.trigger for row in rows] == ["MANUAL", "SCHEDULED"]
    assert rows[1].status == "ERROR"
    failed_at = rows[1].finished_at
    local_failed = scheduler._local_naive(failed_at)
    assert scheduler.next_due_at(db, source.id) == local_failed + timedelta(minutes=1)
    for expected in (2, 4, 8, 15, 15):
        db.add(SheetReportSyncAttempt(source_id=source.id, started_at=failed_at, finished_at=failed_at,
                                      status="ERROR", error="boom", trigger="SCHEDULED"))
        db.commit()
        assert scheduler.next_due_at(db, source.id) == local_failed + timedelta(minutes=expected)
    assert store.latest_snapshot(db, source.id) is not None


def test_add_past_month_without_replace_prompt_and_without_changing_default(db, monkeypatch):
    monkeypatch.setattr(source_api, "read_source_report", lambda *_: _report())
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        current = client.post("/api/v1/sheets/sources", json={
            "spreadsheet": "A" * 25, "period": "2026-10", "name": "Hiện tại", "set_default": True}).json()
        past = client.post("/api/v1/sheets/sources", json={
            "spreadsheet": "B" * 25, "period": "2025-08", "name": "Tháng 8/2025"})
        assert past.status_code == 201
        assert past.json()["is_default"] is False and past.json()["sync_enabled"] is False
        saved = {item["id"]: item for item in client.get("/api/v1/sheets/sources").json()["sources"]}
        assert saved[current["id"]]["is_default"] is True
        assert client.post("/api/v1/sheets/sources", json={
            "spreadsheet": "B" * 25, "period": "2025-08", "name": "lặp"}).status_code == 409
        assert len(client.get("/api/v1/sheets/sources").json()["sources"]) == 2
        year = client.get("/api/v1/sheets/sources/year-summary?year=2025").json()
        assert year["months"][7]["active_source_id"] == past.json()["id"]
    finally:
        app.dependency_overrides.clear()


def test_add_source_keeps_configuration_when_initial_read_fails_then_retry(db, monkeypatch):
    def denied(*_):
        raise SheetsAPIError("Google Sheets API trả lỗi", status_code=403)

    monkeypatch.setattr(source_api, "read_source_report", denied)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        response = client.post("/api/v1/sheets/sources", json={
            "spreadsheet": "D" * 25, "period": "2025-07", "name": "Không quyền"})
        assert response.status_code == 201
        saved = response.json()
        assert saved["latest_snapshot"] is None
        assert saved["last_attempt"]["status"] == "ERROR" and saved["last_attempt"]["trigger"] == "INITIAL"
        assert saved["is_default"] is False
        monkeypatch.setattr(store, "read_source_report", lambda *args: _report())
        retry = client.post(f"/api/v1/sheets/sources/{saved['id']}/sync")
        assert retry.status_code == 200 and retry.json()["trigger"] == "MANUAL"
        assert retry.json()["status"] == "PARTIAL"
        assert len(client.get("/api/v1/sheets/sources").json()["sources"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_failed_read_does_not_replace_existing_same_period_source(db, monkeypatch):
    monkeypatch.setattr(source_api, "read_source_report", lambda *_: _report())
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        first = client.post("/api/v1/sheets/sources", json={
            "spreadsheet": "A" * 25, "period": "2025-06", "name": "cũ"}).json()
        monkeypatch.setattr(source_api, "read_source_report", lambda *_: (_ for _ in ()).throw(SheetsAPIError("x")))
        response = client.post("/api/v1/sheets/sources", json={
            "spreadsheet": "B" * 25, "period": "2025-06", "name": "mới", "replace_existing": True})
        assert response.status_code == 502
        saved = client.get("/api/v1/sheets/sources").json()["sources"]
        assert [(item["id"], item["active"]) for item in saved] == [(first["id"], True)]
    finally:
        app.dependency_overrides.clear()


def test_closure_stays_fixed_and_rollover_uses_confirmed_customer_ids(db):
    old, new = _source(db, "2026-09", "old"), _source(db, "2026-10", "new")
    customer = Customer(name="Synthetic customer")
    db.add(customer)
    db.flush()
    old_snapshot = SheetReportSnapshot(source_id=old.id, read_at=datetime.now(timezone.utc),
                                       mapping_version=store.MAPPING_VERSION, mapping_config=store.MAPPING_CONFIG.copy(), quality="PARTIAL", report=_report("10", 11))
    new_snapshot = SheetReportSnapshot(source_id=new.id, read_at=datetime.now(timezone.utc),
                                       mapping_version=store.MAPPING_VERSION, mapping_config=store.MAPPING_CONFIG.copy(), quality="PARTIAL", report=_report("11.5", 22))
    db.add_all([old_snapshot, new_snapshot])
    db.flush()
    db.add_all([
        SheetReportClosure(source_id=old.id, snapshot_id=old_snapshot.id),
        SheetReportCustomerLink(source_id=old.id, sheet_id=11, source_title="SYNTHETIC", customer_id=customer.id),
        SheetReportCustomerLink(source_id=new.id, sheet_id=22, source_title="SYNTHETIC", customer_id=customer.id),
    ])
    db.commit()
    result = store.compare_rollover(db, old.id, new.id)
    assert result[0]["status"] == "DIFF"
    assert result[0]["difference"] == "1.5"
    old_newer = SheetReportSnapshot(source_id=old.id, read_at=datetime.now(timezone.utc),
                                    mapping_version=store.MAPPING_VERSION, mapping_config=store.MAPPING_CONFIG.copy(), quality="READY", report=_report("999", 11))
    db.add(old_newer)
    db.commit()
    assert store.compare_rollover(db, old.id, new.id)[0]["previous_value"] == "10"
    assert store.compare_rollover(db, old.id, new.id)[0]["previous_source"] == "SYNTHETIC!L1"
    assert result[0]["basis"] == "CLOSED"


def test_unclosed_previous_period_gives_provisional_rollover_only_for_linked_customers(db):
    old, new = _source(db, "2026-09", "old"), _source(db, "2026-10", "new")
    linked, other = Customer(name="Synthetic linked"), Customer(name="Synthetic other")
    db.add_all([linked, other])
    db.flush()
    db.add_all([
        SheetReportSnapshot(source_id=old.id, read_at=datetime.now(timezone.utc), mapping_version=store.MAPPING_VERSION,
                            mapping_config=store.MAPPING_CONFIG.copy(), quality="PARTIAL", report=_report("10", 11)),
        SheetReportSnapshot(source_id=new.id, read_at=datetime.now(timezone.utc), mapping_version=store.MAPPING_VERSION,
                            mapping_config=store.MAPPING_CONFIG.copy(), quality="PARTIAL", report=_report("11.5", 22)),
    ])
    assert store.compare_rollover(db, old.id, new.id) == []
    db.add_all([
        SheetReportCustomerLink(source_id=old.id, sheet_id=11, source_title="SYNTHETIC", customer_id=linked.id),
        SheetReportCustomerLink(source_id=new.id, sheet_id=22, source_title="SYNTHETIC", customer_id=linked.id),
    ])
    db.commit()
    assert db.scalar(select(SheetReportClosure)) is None
    result = store.compare_rollover(db, old.id, new.id)
    assert [item["customer_id"] for item in result] == [linked.id]
    assert result[0]["basis"] == "PROVISIONAL_UNCLOSED"
    assert result[0]["difference"] == "1.5"
    assert db.scalar(select(SheetReportClosure)) is None


def test_source_api_requires_explicit_replace_and_partial_closure_acknowledgement(db, monkeypatch):
    monkeypatch.setattr(source_api, "read_source_report", lambda *_: _report())
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        body = {"spreadsheet": "A" * 25, "period": "2026-10", "name": "Synthetic"}
        response = client.post("/api/v1/sheets/sources", json=body)
        assert response.status_code == 201
        source = response.json()
        assert source["sync_enabled"] is False
        assert source["latest_snapshot"]["quality"] == "PARTIAL"
        assert client.post("/api/v1/sheets/sources", json=body).status_code == 409
        second = {**body, "spreadsheet": "B" * 25}
        assert client.post("/api/v1/sheets/sources", json=second).status_code == 409
        snapshot_id = source["latest_snapshot"]["id"]
        closure = f"/api/v1/sheets/sources/{source['id']}/closure"
        assert client.post(closure, json={"snapshot_id": snapshot_id}).status_code == 409
        assert client.post(closure, json={"snapshot_id": snapshot_id, "acknowledge_partial": True}).status_code == 200
        assert client.post(closure, json={"snapshot_id": snapshot_id, "acknowledge_partial": True}).status_code == 409
        response = client.post("/api/v1/sheets/sources", json={**second, "replace_existing": True})
        assert response.status_code == 201
        replacement = response.json()
        assert client.post(f"/api/v1/sheets/sources/{replacement['id']}/closure", json={
            "snapshot_id": replacement["latest_snapshot"]["id"], "acknowledge_partial": True,
        }).status_code == 409
        year_current = client.get("/api/v1/sheets/sources/year-summary?year=2026").json()
        # current: nguồn hiệu lực có bản đọc mới → dùng bản đó; bản chốt (nguồn đã thay) chỉ thắng ở basis closed.
        assert year_current["months"][9]["snapshot_id"] != snapshot_id
        assert year_current["months"][9]["source_id"] == replacement["id"]
        year_closed = client.get("/api/v1/sheets/sources/year-summary?year=2026&basis=closed").json()
        assert year_closed["months"][9]["snapshot_id"] == snapshot_id
        assert year_closed["months"][9]["active_source_id"] == replacement["id"]
        saved = client.get("/api/v1/sheets/sources").json()["sources"]
        assert sum(item["active"] for item in saved) == 1
        assert next(item for item in saved if item["id"] == source["id"])["closure"]["snapshot_id"] == snapshot_id
    finally:
        app.dependency_overrides.clear()


def test_renamed_tab_requires_confirmation_and_preserves_old_link(db, monkeypatch):
    monkeypatch.setattr(source_api, "read_source_report", lambda *_: _report(title="OLD"))
    customer = Customer(name="Synthetic mapping customer")
    db.add(customer)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        source = client.post("/api/v1/sheets/sources", json={
            "spreadsheet": "C" * 25, "period": "2026-10", "name": "Synthetic"
        }).json()
        endpoint = f"/api/v1/sheets/sources/{source['id']}/links"
        body = {"sheet_id": 7, "customer_id": customer.id}
        assert client.post(endpoint, json=body).status_code == 200
        db.add(SheetReportSnapshot(
            source_id=source["id"], read_at=datetime.now(timezone.utc), mapping_version=store.MAPPING_VERSION,
            mapping_config=store.MAPPING_CONFIG.copy(), quality="PARTIAL", report=_report(title="NEW"),
        ))
        db.commit()
        assert client.post(endpoint, json=body).status_code == 409
        assert client.post(endpoint, json={**body, "confirm_renamed": True}).status_code == 200
        links = db.scalars(select(SheetReportCustomerLink).where(
            SheetReportCustomerLink.source_id == source["id"]).order_by(SheetReportCustomerLink.id)).all()
        assert [(link.source_title, link.active) for link in links] == [("OLD", False), ("NEW", True)]
    finally:
        app.dependency_overrides.clear()


def test_snapshot_and_history_lists_are_paginated_metadata_only(db, monkeypatch):
    monkeypatch.setattr(source_api, "read_source_report", lambda *_: _report())
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        source = client.post("/api/v1/sheets/sources", json={
            "spreadsheet": "A" * 25, "period": "2026-10", "name": "Synthetic"}).json()
        source_id = source["id"]
        db.add_all([
            SheetReportSnapshot(source_id=source_id, read_at=datetime.now(timezone.utc), mapping_version=store.MAPPING_VERSION,
                                mapping_config=store.MAPPING_CONFIG.copy(), quality="PARTIAL", report=_report())
            for _ in range(15)
        ])
        db.commit()
        client.post(f"/api/v1/sheets/sources/{source_id}/sync")
        client.post(f"/api/v1/sheets/sources/{source_id}/sync")
        snapshots = client.get(f"/api/v1/sheets/sources/{source_id}/snapshots?limit=5&offset=3").json()
        assert snapshots["total"] == 16
        assert [item["id"] for item in snapshots["snapshots"]] == [13, 12, 11, 10, 9]
        history = client.get(f"/api/v1/sheets/sources/{source_id}/history?limit=6&offset=2").json()
        # 1 INITIAL + 2 MANUAL; danh sách xếp giảm theo id
        assert history["total"] == 3
        assert len(history["history"]) == 1
        assert [item["id"] for item in history["history"]] == [1]
        full = client.get(f"/api/v1/sheets/sources/{source_id}/history").json()
        assert full["total"] == 3 and len(full["history"]) == 3
    finally:
        app.dependency_overrides.clear()


def test_same_period_current_and_closed_pick_different_snapshots(db, monkeypatch):
    """Cùng một kỳ có bản chốt và bản đọc mới hơn: current dùng bản đọc, closed dùng bản chốt."""
    source = _source(db, "2026-04", "apr")
    reports = iter([_report("100"), _report("40")])
    monkeypatch.setattr(store, "read_source_report", lambda *args: next(reports))
    first = store.sync_source(db, source.id, "MANUAL")
    db.add(SheetReportClosure(source_id=source.id, snapshot_id=first.snapshot_id))
    db.commit()
    store.sync_source(db, source.id, "MANUAL")
    current = build_year_summary(db, 2026, "current")
    closed = build_year_summary(db, 2026, "closed")
    april_current, april_closed = current["months"][3], closed["months"][3]
    assert april_current["snapshot_id"] != first.snapshot_id
    assert april_current["state"] == "PROVISIONAL" and april_current.get("closure_note")
    assert april_closed["snapshot_id"] == first.snapshot_id
    assert april_closed["state"] == "CLOSED"
    assert april_closed["closure_snapshot_id"] == first.snapshot_id
    assert april_closed.get("closure_note")  # current basis có bản đọc mới hơn → closed vẫn báo rõ


def _customer_year_report(spend, balance, receipts=None):
    result = _report(balance)
    customer = result["customers"][0]
    customer["opening_balance"] = {"value": "90", "source": "J1"}
    customer["tab_source_totals"].update({
        "budget_deposits_vnd": {"value": "1000", "source": "K1"},
        "spend_vnd": {"value": spend, "source": "F1"},
        "fee": {"value": "0.19", "source": "G1"},
        "billing_total": {"value": str(float(spend) + 0.19), "source": "H1"},
    })
    if receipts:
        customer["deposits"] = receipts
        customer["usdt_receipts_state"] = "HAS_RECORDS"
    return result


def test_customer_year_summary_months_totals_ranking_and_balances(db, monkeypatch):
    from app.services.sheet_year_summary import build_customer_year_summary

    january = _source(db, "2026-01", "jan")
    february = _source(db, "2026-02", "feb")
    customer = Customer(name="Synthetic year customer")
    other = Customer(name="AAA other customer")
    db.add_all([customer, other])
    db.commit()
    reports = iter([
        _customer_year_report("100", "101", [{"included": True, "amount_usdt": "10", "business_date": "2026-01-05", "source_cells": ["J4"]}]),
        _customer_year_report("40", "60"),
        _customer_year_report("5", "70"),
        _customer_year_report("1000", "900"),
    ])
    monkeypatch.setattr(store, "read_source_report", lambda *args: next(reports))
    jan_first = store.sync_source(db, january.id, "MANUAL")
    db.add(SheetReportClosure(source_id=january.id, snapshot_id=jan_first.snapshot_id))
    db.add_all([
        SheetReportCustomerLink(source_id=january.id, sheet_id=7, source_title="SYNTHETIC", customer_id=customer.id),
        SheetReportCustomerLink(source_id=february.id, sheet_id=7, source_title="SYNTHETIC", customer_id=customer.id),
    ])
    db.commit()
    store.sync_source(db, january.id, "MANUAL")
    store.sync_source(db, february.id, "MANUAL")

    result = build_customer_year_summary(db, 2026, "closed", customer.id, rank_by="spend_vnd")
    january_entry = result["months"][0]
    assert january_entry["link_state"] == "LINKED" and january_entry["state"] == "CLOSED"
    assert january_entry["values"]["spend_vnd"]["value"] == "100"
    assert january_entry["values"]["spend_vnd"]["source"] == "F1"
    assert january_entry["values"]["usdt_received"]["value"] == "10"
    assert january_entry["values"]["usdt_net"]["value"] == "10"
    # Tháng 2 có nguồn nhưng chưa chốt (closed basis) → không tự thay bằng bản hiện hành, không 0 giả.
    february_entry = result["months"][1]
    assert february_entry["state"] == "NOT_CLOSED" and february_entry["link_state"] is None and february_entry["values"] == {}
    assert result["totals"]["spend_vnd"]["value"] == "100"  # chỉ đếm tháng liên kết
    assert result["totals"]["spend_vnd"]["months_with_value"] == 1
    assert result["months_with_value"]["usdt_net"] == 1
    assert result["opening_balance"]["value"] == "90" and result["opening_balance"]["period"] == "2026-01"
    # bản chốt tháng 1 là bản mới nhất có số dư cuối
    assert result["closing_balance"]["value"] == "101" and result["closing_balance"]["period"] == "2026-01"
    assert result["ranking"][0]["customer_id"] == customer.id  # AAA unlinked nhưng spend 0-cột → đứng sau
    assert result["ranking"][1]["totals"]["spend_vnd"] is None

    # current: bản chốt KHÔNG tự thắng — dùng bản đọc mới hơn bản chốt của nguồn hiệu lực
    # (câu "bản chốt luôn thắng" chỉ áp dụng basis closed), tháng chưa chốt dùng bản hiện hành.
    current = build_customer_year_summary(db, 2026, "current", customer.id)
    assert current["months"][0]["state"] == "PROVISIONAL"
    assert current["months"][0]["snapshot_id"] != jan_first.snapshot_id
    assert current["months"][0].get("closure_note")
    assert current["months"][0]["values"]["spend_vnd"]["value"] == "40"
    assert current["months"][1]["state"] == "PROVISIONAL"
    assert current["months"][1]["values"]["spend_vnd"]["value"] == "5"
    assert current["months"][1]["values"]["current_balance"]["value"] == "70"
    assert current["totals"]["spend_vnd"]["value"] == "45"
    assert current["closing_balance"]["value"] == "70" and current["closing_balance"]["period"] == "2026-02"

    # basis closed với kỳ chưa chốt → báo rõ, không lấy bản hiện hành
    march = _source(db, "2026-03", "mar")
    db.add(SheetReportCustomerLink(source_id=march.id, sheet_id=7, source_title="SYNTHETIC", customer_id=customer.id))
    db.add(SheetReportClosure(source_id=february.id, snapshot_id=db.scalar(
        select(SheetReportSnapshot.id).where(SheetReportSnapshot.source_id == february.id).order_by(SheetReportSnapshot.id.desc()).limit(1))))
    monkeypatch.setattr(store, "read_source_report", lambda *args: _customer_year_report("77", "77"))
    store.sync_source(db, march.id, "MANUAL")
    closed = build_customer_year_summary(db, 2026, "closed", customer.id)
    assert closed["months"][2]["state"] == "NOT_CLOSED" and closed["months"][2]["values"] == {}
    assert closed["months"][1]["values"]["spend_vnd"]["value"] == "5"
    assert closed["totals"]["spend_vnd"]["value"] == "105"


def test_customer_year_summary_api_guards(db, monkeypatch):
    customer = Customer(name="Synthetic rank customer")
    db.add(customer)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        missing = client.get("/api/v1/sheets/sources/customer-year-summary?year=2026&customer_id=99999")
        assert missing.status_code == 404
        bad = client.get(f"/api/v1/sheets/sources/customer-year-summary?year=2026&customer_id={customer.id}&rank_by=nope")
        assert bad.status_code in (400, 422)
        monkeypatch.setattr(source_api, "read_source_report", lambda *_: _report())
        source = client.post("/api/v1/sheets/sources", json={
            "spreadsheet": "A" * 25, "period": "2026-10", "name": "Synthetic"}).json()
        response = client.get(
            f"/api/v1/sheets/sources/customer-year-summary?year=2026&customer_id={customer.id}&rank_by=spend_vnd")
        assert response.status_code == 200
        assert response.json()["rank_by"] == "spend_vnd"
        assert len(response.json()["months"]) == 12
        no_rank = client.get(f"/api/v1/sheets/sources/customer-year-summary?year=2026&customer_id={customer.id}")
        assert no_rank.status_code == 200 and no_rank.json()["rank_by"] is None
        assert source is not None
    finally:
        app.dependency_overrides.clear()


def test_sync_source_deduplicates_identical_snapshots(db, monkeypatch):
    source = _source(db)
    monkeypatch.setattr(store, "read_source_report", lambda *_: _report("50"))
    first = store.sync_source(db, source.id, "MANUAL")
    second = store.sync_source(db, source.id, "SCHEDULED")
    assert first.snapshot_id == second.snapshot_id
    assert len(db.scalars(select(SheetReportSnapshot).where(SheetReportSnapshot.source_id == source.id)).all()) == 1
    assert len(db.scalars(select(SheetReportSyncAttempt).where(SheetReportSyncAttempt.source_id == source.id)).all()) == 2

    # When report changes, a new snapshot is created
    monkeypatch.setattr(store, "read_source_report", lambda *_: _report("60"))
    third = store.sync_source(db, source.id, "SCHEDULED")
    assert third.snapshot_id != second.snapshot_id
    assert len(db.scalars(select(SheetReportSnapshot).where(SheetReportSnapshot.source_id == source.id)).all()) == 2
    assert len(db.scalars(select(SheetReportSyncAttempt).where(SheetReportSyncAttempt.source_id == source.id)).all()) == 3


def test_year_summary_uses_company_row_instead_of_customer_sum(db, monkeypatch):
    source = _source(db, '2026-11')
    report = _report('15')
    report['customers'][0]['tab_source_totals']['spend_vnd'] = {'value': '100'}
    report['summary_tabs'][0]['rows'][1]['cells'].append({'address': 'D30', 'value': '120'})
    monkeypatch.setattr(store, 'read_source_report', lambda *args: report)
    store.sync_source(db, source.id, 'MANUAL')
    result = build_year_summary(db, 2026)
    metric = result['months'][10]['metrics']['spend_vnd']
    assert metric['value'] == '120'
    assert metric['source'] == 'TỔNG!D30'
    assert metric['difference'] == '20'
    assert result['flows']['spend_vnd']['value'] == '120'
