"""S17.2 — audit chất lượng logic tài chính + đối chiếu thủ công.

Mỗi test ở đây tái hiện một lỗi đã xác nhận bằng code (INSPECT → REPRODUCE → FIX).
Quy tắc tham chiếu: D-041/D-042 (manual review), D-021 (fee), D-038 (tolerance).
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.models import AdAccount, Campaign, ManualReview, ManualReviewObservation, SpendSnapshot
from app.models.campaign import RECOGNITION_CONFIRMED
from app.services import reports, reviews
from app.services.reviews import (
    REVIEW_MANUAL,
    REVIEW_NEEDS_CONFIRMATION,
)
from tests.conftest import add_snapshot, datetime_utc, make_campaign, make_customer


def _clear(db):
    db.execute(delete(ManualReviewObservation))
    db.execute(delete(ManualReview))
    db.execute(delete(SpendSnapshot))
    db.commit()


def _obs_count(db, review_id):
    return db.execute(
        select(func.count(ManualReviewObservation.id)).where(ManualReviewObservation.review_id == review_id)
    ).scalar()


# ---------- F1: mỗi lần kiểm tra thực tế phải lưu được observation ----------

def test_new_check_same_amount_creates_new_observation(db):
    """09:00 = 100, 12:00 = 100 (không đổi số) → PHẢI có 2 observation (2 lần kiểm tra thực)."""
    _clear(db)
    customer = make_customer(db, "S172-A")
    first = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000101",
        campaign_meta_id="cmp_a",
        observed_spend="100.00",
        sheet_spend="100.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
        observed_at=datetime(2026, 10, 26, 2, 0, tzinfo=timezone.utc),
    )
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000101",
        campaign_meta_id="cmp_a",
        observed_spend="100.00",  # cùng số tiền
        sheet_spend="100.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
        observed_at=datetime(2026, 10, 26, 5, 0, tzinfo=timezone.utc),  # lần kiểm tra mới
    )
    assert _obs_count(db, first.id) == 2, "lần kiểm tra mới cùng số tiền bị mất (idempotency suy từ nội dung)"

    # và lần 3 số tăng → vẫn append
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000101",
        campaign_meta_id="cmp_a",
        observed_spend="105.00",
        sheet_spend="100.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
        observed_at=datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc),
    )
    assert _obs_count(db, first.id) == 3


def test_retry_same_key_same_instant_no_duplicate(db):
    """Retry sau lỗi mạng: cùng key + cùng observed_at → không ghi thêm."""
    _clear(db)
    customer = make_customer(db, "S172-B")
    payload = dict(
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000102",
        campaign_meta_id="cmp_b",
        observed_spend="50.00",
        sheet_spend="50.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
        observed_at=datetime(2026, 10, 26, 3, 0, tzinfo=timezone.utc),
        idempotency_key="s172-retry-1",
    )
    r1 = reviews.create_review(db, **payload)
    reviews.create_review(db, **payload)
    assert _obs_count(db, r1.id) == 1


def test_idempotency_key_reused_for_different_payload_rejected(db):
    """Cùng idempotency_key nhưng nội dung khác → phải báo lỗi, KHÔNG trả review của request khác."""
    _clear(db)
    customer = make_customer(db, "S172-C")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000103",
        campaign_meta_id="cmp_c1",
        observed_spend="10.00",
        idempotency_key="s172-dup-key",
    )
    with pytest.raises(ValueError):
        reviews.create_review(
            db,
            customer_id=customer.id,
            business_date=date(2026, 10, 26),
            ad_account_meta_id="155000000000103",
            campaign_meta_id="cmp_c2",  # nội dung khác
            observed_spend="20.00",
            idempotency_key="s172-dup-key",
        )


def test_currency_change_same_campaign_rejected_not_500(db):
    """Đổi currency cho cùng campaign/ngày/account → từ chối rõ ràng (không IntegrityError, không trộn nhóm)."""
    _clear(db)
    customer = make_customer(db, "S172-D")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000104",
        campaign_meta_id="cmp_d",
        observed_spend="10.00",
        currency="USD",
    )
    with pytest.raises(ValueError):
        reviews.create_review(
            db,
            customer_id=customer.id,
            business_date=date(2026, 10, 26),
            ad_account_meta_id="155000000000104",
            campaign_meta_id="cmp_d",
            observed_spend="10.00",
            currency="VND",
        )
    # không được để lại observation rác
    assert db.execute(select(func.count(ManualReviewObservation.id))).scalar() == 1


# ---------- F2: kết luận account+ngày ----------

def test_conflicting_baseline_needs_confirmation(db):
    """Cùng account+ngày nhưng 2 campaign mang baseline Sheets khác nhau → xung đột, KHÔNG tự phán."""
    _clear(db)
    customer = make_customer(db, "S172-E")
    for camp, baseline in (("cmp_e1", "500.00"), ("cmp_e2", "400.00")):
        reviews.create_review(
            db,
            customer_id=customer.id,
            business_date=date(2026, 10, 26),
            ad_account_meta_id="155000000000105",
            campaign_meta_id=camp,
            observed_spend="200.00",
            sheet_spend=baseline,
            sheet_baseline_confirmed=True,
            campaign_set_complete=True,
        )
    summary = reviews.summarize_by_account_day(db, customer_id=customer.id, business_date=date(2026, 10, 26))
    assert summary[0]["match_status"] == REVIEW_NEEDS_CONFIRMATION, "baseline xung đột phải NEEDS_CONFIRMATION"


# ---------- F3: báo cáo tài chính ----------

def test_meta_and_manual_same_campaign_not_double_counted(db):
    """Cùng campaign/ngày vừa có snapshot Meta VERIFIED vừa có quan sát tay → chỉ tính MỘT lần (Meta)."""
    _clear(db)
    customer = make_customer(db, "S172-F")
    campaign = make_campaign(db, "cmp_f_meta", customer=customer)
    campaign.report_period_start = date(2026, 10, 26)
    campaign.report_period_end = date(2026, 10, 26)
    db.commit()
    add_snapshot(db, campaign, datetime_utc(2026, 10, 26, 8), "100.00")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000106",
        campaign_meta_id="cmp_f_meta",
        observed_spend="100.00",
        sheet_spend="100.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    row = [
        r
        for r in reports.daily_spend_rows(db, customer_id=customer.id)["rows"]
        if r["business_date"] == "2026-10-26"
    ][0]
    assert row["meta_spend"] == 100.0
    assert row["manual_spend"] == 0.0, "quan sát tay cho campaign đã có Meta VERIFIED không được cộng trùng"
    assert row["fee"] == 4.0, "phí phải tính trên chi tiêu thực MỘT lần"
    assert row["billing_total"] == 104.0


def test_profit_none_when_account_cost_missing(db):
    """Có phí nhưng CHƯA có chi phí account → lợi nhuận None + CHƯA ĐỦ DỮ LIỆU (không lấy phí làm lợi nhuận)."""
    _clear(db)
    customer = make_customer(db, "S172-G")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2027, 3, 1),
        ad_account_meta_id="155000000000107",
        campaign_meta_id="cmp_g",
        observed_spend="100.00",
        currency="USD",
    )
    kpi = reports.company_kpi(db, date_from=date(2027, 3, 1), date_to=date(2027, 3, 2))
    assert kpi["service_fee_revenue"]["amount"] == 4.0
    assert kpi["profit_provisional"]["amount"] is None, "thiếu chi phí account → không được coi chi phí = 0"
    assert kpi["profit_provisional"]["data_state"] == reports.STATE_INSUFFICIENT


def test_fee_rounding_half_up(db):
    """Làm tròn tiền theo Decimal ROUND_HALF_UP: 2.90 × 5% = 0.145 → 0.15 (không 0.14)."""
    _clear(db)
    customer = make_customer(db, "S172-H", fee_rate=Decimal("0.05"))
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000108",
        campaign_meta_id="cmp_h",
        observed_spend="2.90",
        currency="USD",
    )
    row = [
        r
        for r in reports.daily_spend_rows(db, customer_id=customer.id)["rows"]
        if r["business_date"] == "2026-10-26"
    ][0]
    assert row["fee"] == 0.15, f"ROUND_HALF_UP phải ra 0.15, nhận {row['fee']}"


def test_campaigns_green_counts_confirmed_only(db):
    """campaigns_green chỉ đếm campaign CONFIRMED (không đếm campaign UNRECOGNIZED)."""
    _clear(db)
    customer = make_customer(db, "S172-I")
    make_campaign(db, "cmp_i_confirmed", customer=customer)
    bad = make_campaign(db, "cmp_i_unrecognized", customer=customer)
    bad.recognition_status = "UNRECOGNIZED"  # có khách nhưng chưa xác nhận → KHÔNG phải campaign xanh
    db.commit()
    kpi = reports.company_kpi(db, date_from=date(2027, 4, 1), date_to=date(2027, 4, 2))
    expected = db.execute(
        select(func.count()).where(Campaign.recognition_status == RECOGNITION_CONFIRMED)
    ).scalar()
    assert kpi["campaigns_green"] == expected, "chỉ đếm campaign CONFIRMED"
