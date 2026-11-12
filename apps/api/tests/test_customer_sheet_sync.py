from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select

from app.jobs.sheets_sync import run_customer_sheets_sync
from app.models import AdAccount, Campaign, Customer, CustomerSheetSyncRun, SpendSnapshot, SyncedAdAccount
from app.models.customer import DEFAULT_FEE_RATE
from app.services.dashboard import operational_dashboard
from app.models.via import ViaProfile


def test_customer_sheet_job_filters_exact_sync_time_and_is_idempotent(db):
    customer = Customer(
        name="Khách lịch Sheets 0900",
        fee_rate=DEFAULT_FEE_RATE,
        sheet_url="https://docs.google.com/spreadsheets/d/12345678901234567890/edit",
        sheet_tab_name="JOKER",
        sync_time="09:00",
        is_active=True,
    )
    other = Customer(name="Khách lịch Sheets 0901", sync_time="09:01", is_active=True)
    db.add_all([customer, other])
    db.flush()
    via = ViaProfile(
        uid="via-sheet-0900",
        profile_name="VIA Sheets",
        profile_dir="profiles/via-sheet-0900",
        user_agent="test-agent",
        encrypted_credentials="test-only",
    )
    db.add(via)
    db.flush()
    synced = SyncedAdAccount(
        via_profile_id=via.id,
        customer_id=customer.id,
        act_id="sheet-sync-0900",
        name="TKQC Sheets",
        status_dot="LIVE",
        currency="USD",
    )
    account = AdAccount(
        meta_ad_account_id="act_sheet-sync-0900",
        name="TKQC Sheets",
        timezone_name="Asia/Ho_Chi_Minh",
    )
    db.add_all([synced, account])
    db.flush()
    campaign = Campaign(
        meta_campaign_id="campaign-sheet-sync-0900",
        ad_account_id=account.id,
        customer_id=customer.id,
        name="Khách lịch Sheets 1109",
        recognition_status="CONFIRMED",
        report_period_start=date(2026, 11, 9),
        report_period_end=date(2026, 11, 9),
    )
    db.add(campaign)
    db.flush()
    db.add(SpendSnapshot(
        campaign_id=campaign.id,
        snapshot_at=datetime(2026, 11, 9, 1, 59, tzinfo=timezone.utc),
        spend_amount=Decimal("125.50"),
        currency="USD",
        source="META_API",
        data_status="VERIFIED",
    ))
    db.commit()

    first = run_customer_sheets_sync(now=datetime(2026, 11, 9, 2, 0, tzinfo=timezone.utc), session=db)
    second = run_customer_sheets_sync(now=datetime(2026, 11, 9, 2, 0, 30, tzinfo=timezone.utc), session=db)
    run = db.scalar(select(CustomerSheetSyncRun).where(CustomerSheetSyncRun.customer_id == customer.id))
    assert first == {"matched": 1, "created": 1, "executed": 0, "skipped": 0, "failed": 0}
    assert second["matched"] == 1
    assert second["skipped"] == 1
    assert run.status == "NEEDS_CONFIRMATION"
    assert len(run.rows_json) == 1
    assert len(run.rows_json[0]) == 10
    assert run.rows_json[0][:7] == ["09/11/2026", "TKQC Sheets (USD)", "sheet-sync-0900", "", "125.50", "", "4.00"]
    assert db.scalar(select(CustomerSheetSyncRun).where(CustomerSheetSyncRun.customer_id == other.id)) is None

    db.execute(delete(CustomerSheetSyncRun).where(CustomerSheetSyncRun.customer_id.in_((customer.id, other.id))))
    db.execute(delete(SpendSnapshot).where(SpendSnapshot.campaign_id == campaign.id))
    db.delete(campaign)
    db.delete(synced)
    db.delete(account)
    db.delete(via)
    db.delete(customer)
    db.delete(other)
    db.commit()


def test_operational_dashboard_excludes_unassigned_accounts(db):
    customer = Customer(name="Khách dashboard gán", fee_rate=Decimal("0.04"), is_active=True)
    db.add(customer)
    db.flush()
    via = ViaProfile(
        uid="via-dashboard-scope",
        profile_name="VIA Dashboard",
        profile_dir="profiles/via-dashboard-scope",
        user_agent="test-agent",
        encrypted_credentials="test-only",
    )
    db.add(via)
    db.flush()
    assigned = SyncedAdAccount(
        via_profile_id=via.id, customer_id=customer.id, act_id="dashboard-assigned",
        name="TKQC đã gán", status_dot="LIVE", currency="USD", balance=Decimal("250.25"),
    )
    unassigned = SyncedAdAccount(
        via_profile_id=via.id, customer_id=None, act_id="dashboard-unassigned",
        name="TKQC chưa gán", status_dot="LIVE", currency="USD", balance=Decimal("999.00"),
    )
    db.add_all([assigned, unassigned])
    db.flush()
    ad_assigned = AdAccount(meta_ad_account_id="act_dashboard-assigned", name="TKQC đã gán", timezone_name="Asia/Ho_Chi_Minh")
    ad_unassigned = AdAccount(meta_ad_account_id="act_dashboard-unassigned", name="TKQC chưa gán", timezone_name="Asia/Ho_Chi_Minh")
    db.add_all([ad_assigned, ad_unassigned])
    db.flush()
    campaigns = [
        Campaign(meta_campaign_id="campaign-dashboard-assigned", ad_account_id=ad_assigned.id,
                 customer_id=customer.id, name="Khách dashboard 1109", recognition_status="CONFIRMED",
                 report_period_start=date(2026, 11, 9), report_period_end=date(2026, 11, 9)),
        Campaign(meta_campaign_id="campaign-dashboard-unassigned", ad_account_id=ad_unassigned.id,
                 customer_id=customer.id, name="Khách dashboard 1109 phụ", recognition_status="CONFIRMED",
                 report_period_start=date(2026, 11, 9), report_period_end=date(2026, 11, 9)),
    ]
    db.add_all(campaigns)
    db.flush()
    db.add_all([
        SpendSnapshot(campaign_id=campaigns[0].id, snapshot_at=datetime(2026, 11, 9, 2, tzinfo=timezone.utc),
                      spend_amount=Decimal("100.00"), currency="USD", source="META_API", data_status="VERIFIED"),
        SpendSnapshot(campaign_id=campaigns[1].id, snapshot_at=datetime(2026, 11, 9, 2, tzinfo=timezone.utc),
                      spend_amount=Decimal("999.00"), currency="USD", source="META_API", data_status="VERIFIED"),
    ])
    db.commit()

    result = operational_dashboard(
        db,
        date_from=date(2026, 11, 9),
        date_to=date(2026, 11, 9),
        now=datetime(2026, 11, 9, 3, tzinfo=timezone.utc),
    )
    assert result["metrics"]["today_spend_by_currency"] == {"USD": "100.00"}
    assert result["metrics"]["fee_by_currency"] == {"USD": "4.0000"}
    assert result["metrics"]["debt_threshold_by_currency"] == {"USD": "250.25"}
    assert result["metrics"]["active_accounts"] == 1
    assert [row["act_id"] for row in result["top_accounts"]] == ["dashboard-assigned"]

    for campaign in campaigns:
        db.execute(delete(SpendSnapshot).where(SpendSnapshot.campaign_id == campaign.id))
        db.delete(campaign)
    db.delete(assigned)
    db.delete(unassigned)
    db.delete(ad_assigned)
    db.delete(ad_unassigned)
    db.delete(via)
    db.delete(customer)
    db.commit()
