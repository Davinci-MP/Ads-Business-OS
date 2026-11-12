"""Unit tests for Daily Profit Inspector and VIA-to-Google-Sheets Writeback."""

from datetime import datetime, timezone
from decimal import Decimal
import alembic.command
import alembic.config
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.ad_account import AdAccount, AdAccountAssignment
from app.models.customer import Customer
from app.models.sheet_reports import (
    SheetReportCustomerLink,
    SheetReportSnapshot,
    SheetReportSource,
)
from app.models.via import AdAccountSnapshot, MaxcareActivityLog, SyncedAdAccount, ViaProfile
from app.services.sheet_writer import (
    calculate_via_daily_reporting_rows,
    writeback_reporting_rows_to_sheets,
)
from app.services.sheet_year_summary import (
    build_year_summary,
    compute_daily_profit_breakdown,
)


@pytest.fixture
def db(tmp_path):
    database = tmp_path / "daily-profit-test.db"
    cfg = alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    alembic.command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def test_compute_daily_profit_breakdown_tier1(db):
    """Test Tier 1 DAILY_ROW extraction from sheet report snapshot."""
    # Create customer with 5% fee
    cust = Customer(name="ALICE", fee_rate=Decimal("0.05"), is_active=True)
    db.add(cust)

    source = SheetReportSource(
        period="2026-10",
        spreadsheet_id="test_sheet",
        name="Source Oct",
        mapping_version="v1",
        mapping_config={},
        active=True,
        sync_enabled=True,
    )
    db.add(source)
    db.flush()

    report_payload = {
        "status": "VALID",
        "customers": [
            {
                "source_sheet": "ALICE",
                "sheet_id": 101,
                "daily": [
                    {
                        "business_date": "2026-10-15",
                        "spend_vnd": "20000000",
                        "fee_by_currency": {"VND": "1000000"},
                        "billing_by_currency": {"VND": "21000000"},
                    },
                    {
                        "business_date": "2026-10-16",
                        "spend_vnd": "10000000",
                        "fee_by_currency": {"VND": "500000"},
                        "billing_by_currency": {"VND": "10500000"},
                    },
                ],
                "deposits": [
                    {
                        "business_date": "2026-10-15",
                        "amount_vnd": "25000000",
                        "amount_usdt": "1000",
                        "kind": "RECEIPT",
                        "included": True,
                    }
                ],
                "source_rows": [],
            }
        ],
        "all_customer_totals": {
            "metrics": {
                "spend_vnd": {"value": "30000000", "status": "COMPLETE"},
                "fee": {"value": "1500000", "status": "COMPLETE"},
            }
        },
    }
    snap = SheetReportSnapshot(
        source_id=source.id,
        read_at=datetime.now(timezone.utc),
        mapping_version="v1",
        mapping_config={},
        quality="FULL",
        report=report_payload,
    )
    db.add(snap)
    db.commit()

    breakdown = compute_daily_profit_breakdown(
        session=db,
        year=2026,
        basis="current",
        target_month="10",
        selected_date_str="2026-10-15",
    )

    daily_list = breakdown["daily_breakdown"]
    assert len(daily_list) == 31

    day15 = next(d for d in daily_list if d["date"] == "2026-10-15")
    assert day15["spend_vnd"] == "20000000"
    assert day15["fee"] == "1000000"
    assert day15["source_type"] == "DAILY_ROW"
    assert day15["budget_deposits_vnd"] == "25000000"
    assert day15["usdt_net"] == "1000.00"

    # Check client breakdown for 2026-10-15
    client_list = breakdown["client_daily_breakdown"]
    assert len(client_list) == 1
    assert client_list[0]["customer_name"] == "ALICE"
    assert client_list[0]["spend_vnd"] == "20000000"
    assert client_list[0]["fee"] == "1000000"

    # Check 4 Daily KPI highlights
    summary = breakdown["daily_summary"]
    assert summary["selected_date"] == "2026-10-15"
    assert summary["profit_selected_date"] == "1000000"
    assert summary["avg_daily_profit"] == "750000"  # (1,000,000 + 500,000) / 2
    assert summary["peak_profit_date"]["date"] == "2026-10-15"
    assert summary["effective_fee_rate_pct"] == "5.00"


def test_sheet_writeback_upsert_and_deposits(db):
    """Test smart upsert and deposit preservation in sheet_writer."""
    cust = Customer(name="BOB", fee_rate=Decimal("0.04"), is_active=True)
    db.add(cust)
    db.flush()

    # Create VIA Profile and synced ad account
    via = ViaProfile(
        uid="100099887766",
        profile_name="VIA-01",
        profile_dir="profiles/via_100099887766",
        user_agent="Mozilla/5.0",
        encrypted_credentials="enc",
    )
    db.add(via)
    db.flush()

    synced_acc = SyncedAdAccount(
        via_profile_id=via.id,
        act_id="act_123456789",
        name="TKQC Bob 01",
        balance=0.0,
        daily_budget=5000000.0,
        total_spend=15000000.0,
    )
    db.add(synced_acc)

    ad_acc = AdAccount(
        meta_ad_account_id="act_123456789",
        name="TKQC Bob 01",
        timezone_name="Asia/Ho_Chi_Minh",
    )
    db.add(ad_acc)
    db.flush()

    # Assign ad account to BOB
    assign = AdAccountAssignment(
        customer_id=cust.id,
        ad_account_id=ad_acc.id,
        valid_from=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    db.add(assign)

    # Active source for 2026-11
    source = SheetReportSource(
        period="2026-11",
        spreadsheet_id="test_sheet_nov",
        name="Source Nov",
        mapping_version="v1",
        mapping_config={},
        active=True,
    )
    db.add(source)
    db.flush()

    # Snapshot with an existing row for 2026-11-02 preserving Column J (USDT)
    existing_cells = [
        {"address": "A25", "value": "2026-11-02", "formatted_value": "02/11/2026"},
        {"address": "B25", "value": "Cũ"},
        {"address": "F25", "value": "10000000"},
        {"address": "J25", "value": "500"},  # 500 USDT deposit preserved!
        {"address": "K25", "value": "12000000"},  # 12,000,000 VND deposit preserved!
    ]
    report_data = {
        "status": "VALID",
        "customers": [
            {
                "source_sheet": "BOB",
                "sheet_id": 201,
                "daily": [
                    {
                        "business_date": "2026-11-02",
                        "spend_vnd": "10000000",
                        "fee_by_currency": {"VND": "400000"},
                        "billing_by_currency": {"VND": "10400000"},
                        "account_rows": [25],
                    }
                ],
                "source_rows": [{"row_number": 25, "cells": existing_cells}],
            }
        ],
    }
    snap = SheetReportSnapshot(
        source_id=source.id,
        read_at=datetime.now(timezone.utc),
        mapping_version="v1",
        mapping_config={},
        quality="FULL",
        report=report_data,
    )
    db.add(snap)
    db.commit()

    # 1. Test Dry Run Calculation
    preview = calculate_via_daily_reporting_rows(db, "2026-11-02")
    assert preview["total_clients"] == 1
    proposal = preview["clients"][0]
    assert proposal["customer_name"] == "BOB"
    assert proposal["action"] == "UPDATED_EXISTING_ROW"
    assert proposal["row_index"] == 25
    assert proposal["previous_spend_vnd"] == "10000000"
    assert proposal["new_spend_vnd"] == "5000000"  # From synced daily_budget
    assert proposal["fee_vnd"] == "200000"  # 5,000,000 * 4%
    assert proposal["total_vnd"] == "5200000"
    assert proposal["preserved_deposits"]["usdt_received"] == "500"
    assert proposal["preserved_deposits"]["budget_deposits_vnd"] == "12000000"

    # 2. Test Non-Dry-Run Execution (Local Fallback mode)
    commit_res = writeback_reporting_rows_to_sheets(db, "2026-11-02", dry_run=False)
    assert commit_res["success"] is True
    assert commit_res["dry_run"] is False
    assert commit_res["execution_status"] == "SIMULATED_SUCCESS_LOCAL_FALLBACK"

    # Verify audit log was recorded in MaxcareActivityLog
    logs = db.scalars(select(MaxcareActivityLog).where(MaxcareActivityLog.action == "SHEET_WRITEBACK")).all()
    assert len(logs) == 1
    assert "Kẻ & Ghi báo cáo 1 khách" in logs[0].detail


def test_api_endpoints_integration():
    """Test FastAPI endpoints for daily profit and writeback."""
    client = TestClient(app)

    # 1. Year Summary with scope=day & date
    res = client.get("/api/v1/sheets/sources/year-summary?year=2026&scope=day&date=2026-10-01")
    assert res.status_code == 200
    data = res.json()
    assert "daily_breakdown" in data
    assert "client_daily_breakdown" in data
    assert "daily_summary" in data
    assert data["daily_summary"]["selected_date"] == "2026-10-01"

    # 2. Sheet Writeback Preview (Dry-Run)
    res_wb = client.post(
        "/api/v1/sheets/writeback-from-vias",
        json={"report_date": "2026-10-01", "dry_run": True, "auto_create_borders": True},
    )
    assert res_wb.status_code == 200
    wb_data = res_wb.json()
    assert wb_data["success"] is True
    assert wb_data["dry_run"] is True
    assert "clients" in wb_data
    assert "summary" in wb_data


def test_daily_missing_then_entered_data_ignores_account_snapshots(db):
    source = SheetReportSource(period='2026-11', spreadsheet_id='fixture', name='November',
        mapping_version='v1', mapping_config={}, active=True, sync_enabled=True)
    db.add(source)
    db.flush()
    payload = {'customers': [{'source_sheet': 'ALICE', 'daily': [
        {'business_date': '2026-11-01', 'spend_vnd': '100', 'fee_by_currency': {'VND': '4'}}]}]}
    snapshot = SheetReportSnapshot(source_id=source.id, read_at=datetime(2026,11,3,tzinfo=timezone.utc),
        mapping_version='v1', mapping_config={}, quality='PARTIAL', report=payload)
    db.add(snapshot)
    db.add_all([AdAccountSnapshot(act_id='same-account', total_spend=445707502,
        snapshot_at=datetime(2026,11,3,h,tzinfo=timezone.utc)) for h in [1,2]])
    db.commit()
    def calculate():
        return compute_daily_profit_breakdown(db,2026,target_month='11',selected_date_str='2026-11-03')
    before = calculate()
    assert before['daily_breakdown'][2]['spend_vnd'] is None
    assert before['daily_breakdown'][2]['fee'] is None
    assert before['daily_breakdown'][2]['source_type'] == 'NO_DATA'
    assert before['daily_summary']['profit_selected_date'] is None
    assert before['daily_summary']['days_with_data'] == 1
    assert before['daily_summary']['peak_profit_date']['date'] == '2026-11-01'
    from copy import deepcopy
    updated = deepcopy(payload)
    updated['customers'][0]['daily'].append({'business_date':'2026-11-03',
        'spend_vnd':'1000', 'fee_by_currency':{'VND':'50'}})
    db.add(SheetReportSnapshot(source_id=source.id, read_at=datetime(2026,11,3,9,tzinfo=timezone.utc),
        mapping_version='v1', mapping_config={}, quality='PARTIAL', report=updated))
    db.commit()
    after = calculate()
    assert after['daily_breakdown'][2]['spend_vnd'] == '1000'
    assert after['daily_breakdown'][2]['fee'] == '50'
    assert after['daily_breakdown'][2]['fee_rate_pct'] == '5.00'
    assert after['daily_summary']['profit_selected_date'] == '50'
    assert after['daily_summary']['peak_profit_date']['date'] == '2026-11-03'
    assert after['daily_summary']['avg_daily_profit'] == '27'
    # Missing source fee must not silently become a default 4% charge.
    updated = deepcopy(updated)
    updated['customers'][0]['daily'][1]['fee_by_currency'] = {}
    db.add(SheetReportSnapshot(source_id=source.id, read_at=datetime(2026,11,3,10,tzinfo=timezone.utc),
        mapping_version='v1', mapping_config={}, quality='PARTIAL', report=updated))
    db.commit()
    assert calculate()['daily_breakdown'][2]['fee'] is None
