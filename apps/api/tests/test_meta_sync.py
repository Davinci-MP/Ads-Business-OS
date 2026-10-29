"""Kiểm thử S3 Meta sync (mock mode) — bắt buộc theo skill meta-ads-sync:

- Nhận diện campaign D-026 (MMDD/DDMM, mã lưỡng nghĩa → UNRECOGNIZED, không tự gán).
- Idempotency: chạy 2 lần → số snapshot không đổi.
- Checkpoint 9h D-009: flag đúng theo giờ VN.
- API lỗi → giữ snapshot cũ, ghi audit lỗi (D-011).
- Chi tiêu giảm → UNVERIFIED, không đè số đã xác nhận (D-011).
- Tiền trôi = hiện tại − mốc 09:00 (D-023), unique theo (campaign, checkpoint).
- Token không bao giờ lộ trong repr/endpoint.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, delete

from app.connectors.meta import MetaAdsConnector
from app.db import get_db
from app.main import app
from app.models import AdAccount, AdAccountAssignment, AuditLog, Campaign, Customer, DriftRecord, SpendSnapshot
from app.models.campaign import RECOGNITION_CONFIRMED, RECOGNITION_UNRECOGNIZED
from app.models.spend import DATA_UNVERIFIED, DATA_VERIFIED
from app.services.meta_sync import extract_report_dates, run_meta_sync


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean_meta_sync_tables(db):
    """Dọn dữ liệu meta-sync giữa các test (seed trong test dùng commit thật)."""
    yield
    db.rollback()
    db.execute(delete(DriftRecord))
    db.execute(delete(SpendSnapshot))
    db.execute(delete(Campaign))
    db.execute(delete(AuditLog))
    db.execute(delete(AdAccountAssignment))
    db.execute(delete(AdAccount))
    db.execute(delete(Customer))
    db.commit()


def mock_connector(**kwargs):
    return MetaAdsConnector(use_mock=True, **kwargs)


def seed_customers_and_accounts(session, connector):
    """Seed 3 khách + 2 account + assignment; đổi tên mock campaign cho khớp tên khách."""
    alpha = Customer(name="KH-MSYNC-Alpha")
    beta = Customer(name="KH-MSYNC-Beta")
    gamma = Customer(name="KH-MSYNC-Gamma")
    session.add_all([alpha, beta, gamma])
    session.flush()
    acc1 = AdAccount(
        meta_ad_account_id="act_mock_1",
        name="Acc 1",
        business_manager_id="bm_mock_a",
        timezone_name="Asia/Ho_Chi_Minh",
    )
    acc2 = AdAccount(
        meta_ad_account_id="act_mock_2",
        name="Acc 2",
        business_manager_id="bm_mock_b",
        timezone_name="America/Los_Angeles",
    )
    session.add_all([acc1, acc2])
    session.flush()
    session.add_all(
        [
            AdAccountAssignment(customer_id=alpha.id, ad_account_id=acc1.id, valid_from=utc(2026, 10, 1)),
            AdAccountAssignment(customer_id=beta.id, ad_account_id=acc1.id, valid_from=utc(2026, 10, 1)),
            AdAccountAssignment(customer_id=gamma.id, ad_account_id=acc2.id, valid_from=utc(2026, 10, 1)),
        ]
    )
    # Tên mock campaign phải chứa đúng tên khách đã seed để đủ 4 tiêu chí D-026
    connector.mock.rename_campaign("cmp_1001", f"{alpha.name} 1025")  # MMDD
    connector.mock.rename_campaign("cmp_1002", f"{beta.name} 2510")  # DDMM
    connector.mock.rename_campaign("cmp_1003", f"{alpha.name} 1102")  # mã lưỡng nghĩa
    connector.mock.rename_campaign("cmp_1004", f"{alpha.name} 1025 retired")  # PAUSED
    connector.mock.rename_campaign("cmp_2001", f"{gamma.name} 1026")  # ENDED
    session.commit()
    return acc1, acc2


def get_campaign(session, meta_campaign_id):
    return session.execute(
        select(Campaign).where(Campaign.meta_campaign_id == meta_campaign_id)
    ).scalar_one()


def snap_count(session):
    return session.execute(select(func.count(SpendSnapshot.id))).scalar_one()


# --- nhận diện campaign (D-026) ---


def test_extract_report_dates_d026_both_formats_and_ambiguity():
    assert str(extract_report_dates("Tên KH 1025")) == "2026-10-25"  # MMDD
    assert str(extract_report_dates("Tên KH 2510")) == "2026-10-25"  # DDMM — cùng ngày
    # Mã lưỡng nghĩa: 02/11 (MMDD) hay 11/02 (DDMM) → không xác định được ngày
    assert extract_report_dates("Tên KH 1102") is None
    assert extract_report_dates("no date code") is None
    assert extract_report_dates("123 pseudo") is None


def test_sync_mock_creates_and_recognizes(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    summary = run_meta_sync(db, conn, now=utc(2026, 10, 26, 4, 0))  # 11h VN, không checkpoint
    assert summary["accounts_synced"] == 2
    assert summary["campaigns_synced"] == 5

    cmp_1 = get_campaign(db, "cmp_1001")
    assert cmp_1.recognition_status == RECOGNITION_CONFIRMED
    assert db.get(Customer, cmp_1.customer_id).name == "KH-MSYNC-Alpha"
    assert str(cmp_1.report_period_end) == "2026-10-25"

    cmp_2 = get_campaign(db, "cmp_1002")
    assert cmp_2.recognition_status == RECOGNITION_CONFIRMED  # DDMM cũng được nhận diện

    cmp_3 = get_campaign(db, "cmp_1003")
    assert cmp_3.recognition_status == RECOGNITION_UNRECOGNIZED
    assert cmp_3.customer_id is None  # KHÔNG tự ghép khi không xác định được ngày
    assert "cmp_1003" in summary["unrecognized"]

    # cmp_1001, cmp_1002, cmp_1004 (PAUSED vẫn poll), cmp_2001 — 4 snapshot
    assert summary["snapshots_added"] == 4
    assert snap_count(db) == 4


def test_sync_never_assigns_customer_without_account_assignment(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    db.add(Customer(name="KH-MSYNC-Delta"))  # có tên, chưa được giao ad account nào
    db.commit()
    summary = run_meta_sync(db, conn, now=utc(2026, 10, 26, 4, 0))
    assert summary["snapshots_added"] == 4  # chỉ 4 campaign đủ tiêu chí mới có snapshot
    assert snap_count(db) == 4


# --- idempotency + checkpoint 9h (D-009) ---


def test_run_twice_is_idempotent(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    now = utc(2026, 10, 26, 4, 0)
    run_meta_sync(db, conn, now=now)
    before = snap_count(db)
    summary = run_meta_sync(db, conn, now=now)
    assert snap_count(db) == before
    assert summary["snapshots_added"] == 0


def test_checkpoint_9h_flag(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    summary = run_meta_sync(db, conn, now=utc(2026, 10, 26, 2, 0))  # 09:00 giờ VN
    assert summary["checkpoints_9h"] == 4
    rows = db.execute(select(SpendSnapshot).where(SpendSnapshot.is_checkpoint_9h.is_(True))).scalars().all()
    assert len(rows) == 4

    summary = run_meta_sync(db, conn, now=utc(2026, 10, 26, 3, 0))  # 10:00 VN
    assert summary["checkpoints_9h"] == 0


# --- lỗi API & chi tiêu bất thường (D-011) ---


def test_api_error_keeps_old_snapshot(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    run_meta_sync(db, conn, now=utc(2026, 10, 26, 4, 0))
    conn.mock.fail_insights("cmp_1001")
    summary = run_meta_sync(db, conn, now=utc(2026, 10, 26, 5, 0))
    assert any("cmp_1001" in err for err in summary["api_errors"])
    audits = db.execute(select(AuditLog).where(AuditLog.action == "spend_api_error")).scalars().all()
    assert audits
    # Snapshot VERIFIED cũ giữ nguyên 1234.56, không đè
    rows = db.execute(
        select(SpendSnapshot).where(SpendSnapshot.campaign_id == get_campaign(db, "cmp_1001").id)
    ).scalars().all()
    verified = [r for r in rows if r.data_status == DATA_VERIFIED]
    assert len(verified) == 1 and str(verified[0].spend_amount) == "1234.56"


def test_non_monotonic_spend_is_unverified_then_recovers(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    run_meta_sync(db, conn, now=utc(2026, 10, 26, 4, 0))
    conn.mock.set_insight_spend("cmp_1001", 100.0)  # thấp hơn snapshot trước → nghi lỗi
    summary = run_meta_sync(db, conn, now=utc(2026, 10, 26, 5, 0))
    assert summary["unverified"]
    rows = db.execute(
        select(SpendSnapshot).where(SpendSnapshot.campaign_id == get_campaign(db, "cmp_1001").id)
    ).scalars().all()
    assert any(r.data_status == DATA_UNVERIFIED for r in rows)
    old_verified = [r for r in rows if r.data_status == DATA_VERIFIED]
    assert len(old_verified) == 1 and str(old_verified[0].spend_amount) == "1234.56"
    # phục hồi: giá trị tăng trở lại → snapshot VERIFIED mới
    conn.mock.set_insight_spend("cmp_1001", 1300.0)
    run_meta_sync(db, conn, now=utc(2026, 10, 26, 6, 0))
    verified = db.execute(
        select(SpendSnapshot).where(
            SpendSnapshot.campaign_id == get_campaign(db, "cmp_1001").id,
            SpendSnapshot.data_status == DATA_VERIFIED,
        )
    ).scalars().all()
    assert {str(r.spend_amount) for r in verified} == {"1234.56", "1300.00"}


# --- tiền trôi (D-023) ---


def test_drift_current_minus_checkpoint(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    checkpoint_summary = run_meta_sync(db, conn, now=utc(2026, 10, 26, 2, 0))  # mốc 09h VN
    assert checkpoint_summary["checkpoints_9h"] == 4
    conn.mock.set_insight_spend("cmp_1004", 1500.0)  # PAUSED vẫn poll
    conn.mock.set_insight_spend("cmp_2001", 1010.0)
    drift_summary = run_meta_sync(db, conn, now=utc(2026, 10, 26, 10, 0))
    assert drift_summary["drift_records"] == 2
    records = {r.campaign_id: r for r in db.execute(select(DriftRecord)).scalars().all()}
    assert str(records[get_campaign(db, "cmp_1004").id].drift_amount) == "100.00"  # 1500 − mốc 09h 1400
    assert str(records[get_campaign(db, "cmp_2001").id].drift_amount) == "19.10"  # 1010 − 990.90
    # idempotent: chạy lại cùng checkpoint → không tạo record trùng
    run_meta_sync(db, conn, now=utc(2026, 10, 26, 11, 0))
    assert db.execute(select(func.count(DriftRecord.id))).scalar_one() == 2


# --- an toàn token & endpoint ---


def test_connector_repr_never_leaks_token():
    connector = MetaAdsConnector(access_token="VERY_SECRET_TOKEN_XYZ", token_map={"bm_1": "OTHER_SECRET"})
    assert "VERY_SECRET" not in repr(connector)
    assert connector.mode == "live"


def test_meta_sync_endpoints_mock(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        run_meta_sync(db, conn, now=utc(2026, 10, 26, 2, 0))  # checkpoint 9h
        run_meta_sync(db, conn, now=utc(2026, 10, 26, 3, 0))

        resp = client.post("/api/v1/meta-sync/run")
        assert resp.status_code == 200
        assert resp.json()["mode"] == "mock"

        campaigns = client.get("/api/v1/meta-sync/campaigns?status=CONFIRMED").json()
        assert len(campaigns) == 4
        assert "cmp_1003" not in {c["meta_campaign_id"] for c in campaigns}

        snapshots = client.get("/api/v1/meta-sync/snapshots?meta_campaign_id=cmp_1001").json()
        assert snapshots[0]["spend_amount"] == "1234.56"

        drift = client.get("/api/v1/meta-sync/drift").json()
        # chưa có tiền trôi: chi tiêu không đổi sau checkpoint
        assert drift == []

        # không bao giờ trả token trong bất kỳ endpoint nào
        for url in ("/api/v1/meta-sync/mode", "/api/v1/meta-sync/campaigns", "/api/v1/meta-sync/snapshots"):
            assert "token" not in client.get(url).text.lower()
    finally:
        app.dependency_overrides.pop(get_db, None)
