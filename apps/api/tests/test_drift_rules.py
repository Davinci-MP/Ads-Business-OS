from datetime import date
from decimal import Decimal

import pytest

from app.models.spend import DATA_UNVERIFIED
from app.services import recon
from conftest import add_snapshot, datetime_utc, make_campaign, make_customer

CHECKPOINT_AT = datetime_utc(2026, 10, 26, 2, 0)
LATEST_AT = datetime_utc(2026, 10, 26, 8, 0)


def test_drift_record_uses_current_minus_9h_checkpoint(db):
    customer = make_customer(db, "KH-DRIFT-01")
    campaign = make_campaign(db, "1001", customer=customer)
    checkpoint = add_snapshot(db, campaign, CHECKPOINT_AT, "1000.00", is_checkpoint_9h=True)
    add_snapshot(db, campaign, LATEST_AT, "1300.00")
    record = recon.record_drift(db, campaign.id, LATEST_AT)
    assert record.drift_amount == Decimal("300.00")
    assert record.checkpoint_snapshot_id == checkpoint.id


def test_drift_record_is_deduplicated_and_updated_per_checkpoint(db):
    customer = make_customer(db, "KH-DRIFT-02")
    campaign = make_campaign(db, "1002", customer=customer)
    add_snapshot(db, campaign, CHECKPOINT_AT, "1000.00", is_checkpoint_9h=True)
    first = recon.record_drift(db, campaign.id, LATEST_AT)
    second = recon.record_drift(db, campaign.id, LATEST_AT)
    assert second.id == first.id
    add_snapshot(db, campaign, datetime_utc(2026, 10, 26, 9, 0), "1500.00")
    third = recon.record_drift(db, campaign.id, datetime_utc(2026, 10, 26, 9, 0))
    assert third.id == first.id
    assert third.drift_amount == Decimal("500.00")


def test_snapshot_unique_key_prevents_double_count(db):
    from sqlalchemy.exc import IntegrityError

    customer = make_customer(db, "KH-DRIFT-03")
    campaign = make_campaign(db, "1003", customer=customer)
    add_snapshot(db, campaign, CHECKPOINT_AT, "500.00")
    with pytest.raises(IntegrityError):
        add_snapshot(db, campaign, CHECKPOINT_AT, "500.00")


def test_unverified_snapshot_never_becomes_current_spend(db):
    customer = make_customer(db, "KH-DRIFT-04")
    campaign = make_campaign(db, "1004", customer=customer)
    add_snapshot(db, campaign, CHECKPOINT_AT, "1000.00", is_checkpoint_9h=True)
    add_snapshot(db, campaign, LATEST_AT, "424242.00", data_status=DATA_UNVERIFIED)
    record = recon.record_drift(db, campaign.id, LATEST_AT)
    assert record.drift_amount == Decimal("0")
    latest = recon.get_current_spend_snapshot(db, campaign.id)
    assert latest.spend_amount == Decimal("1000.00")
    assert latest.is_checkpoint_9h is True


def test_drift_skipped_when_no_checkpoint(db):
    customer = make_customer(db, "KH-DRIFT-05")
    campaign = make_campaign(db, "1005", customer=customer)
    add_snapshot(db, campaign, LATEST_AT, "1300.00")
    assert recon.record_drift(db, campaign.id, LATEST_AT) is None


def test_stopped_campaign_still_tracked_for_drift(db):
    customer = make_customer(db, "KH-DRIFT-06")
    campaign = make_campaign(
        db, "1006", customer=customer, meta_status="PAUSED", stopped_at=datetime_utc(2026, 10, 25, 12, 0)
    )
    add_snapshot(db, campaign, CHECKPOINT_AT, "1000.00", is_checkpoint_9h=True)
    add_snapshot(db, campaign, LATEST_AT, "1180.00")
    record = recon.record_drift(db, campaign.id, LATEST_AT)
    assert record.drift_amount == Decimal("180.00")
    assert campaign.meta_status == "PAUSED"
    assert campaign.stopped_at is not None
