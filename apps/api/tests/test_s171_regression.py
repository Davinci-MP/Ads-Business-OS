"""S17.1 regression — lịch sử quan sát (F1), verdict account+ngày (F3), tiền nhiều loại (F4).

Viết TRƯỚC khi sửa code: các test này phải FAIL trên hành vi cũ.
Phê duyệt: D-042 (append-only observations + MATCH/DIFF theo Customer+Account+Ngày+Nghiệp vụ+Currency).
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select

from app.models import ManualReview, ManualReviewObservation, SpendSnapshot
from app.services import reports, reviews
from app.services.reviews import (
    REVIEW_DIFF,
    REVIEW_INCOMPLETE,
    REVIEW_MANUAL,
    REVIEW_MATCH,
    REVIEW_NEEDS_CONFIRMATION,
    REVIEW_NEEDS_SHEET,
    REVIEW_VISUAL,
    REVIEW_VISUAL_ONLY,
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


# ---------- F1: lịch sử quan sát + idempotency ----------

def test_new_observation_when_value_increases(db):
    """Nhập lại cùng campaign với giá trị tăng (09:00 → 15:00) → PHẢI lưu quan sát mới, giữ lịch sử."""
    _clear(db)
    customer = make_customer(db, "S171-A")
    first = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000001",
        campaign_meta_id="cmp_f1",
        observed_spend="100.00",
        sheet_spend="100.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
        observed_at=datetime(2026, 10, 26, 2, 0, tzinfo=timezone.utc),
    )
    second = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000001",
        campaign_meta_id="cmp_f1",
        observed_spend="120.00",
        sheet_spend="120.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
        observed_at=datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc),
    )
    assert _obs_count(db, first.id) == 2, "quan sát 09:00 bị mất khi nhập lại lúc 15:00"
    # hiện hành = quan sát mới nhất
    assert str(second.observed_spend) == "120.00"
    history = reviews.list_observations(db, first.id)
    assert len(history) == 2
    assert history[0]["observed_spend"] == "120.00"  # mới nhất trước
    assert history[1]["observed_spend"] == "100.00"  # cũ còn nguyên


def test_retry_same_request_no_new_observation(db):
    """Retry cùng request (cùng nội dung) → không tạo bản ghi trùng."""
    _clear(db)
    customer = make_customer(db, "S171-B")
    payload = dict(
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000002",
        campaign_meta_id="cmp_retry",
        observed_spend="50.00",
        sheet_spend="50.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
        idempotency_key="req-abc-123",
    )
    r1 = reviews.create_review(db, **payload)
    r2 = reviews.create_review(db, **payload)
    assert _obs_count(db, r1.id) == 1, "retry cùng idempotency_key không được tạo thêm observation"


def test_retry_without_key_derived_from_content(db):
    """Không có idempotency_key → suy từ nội dung + observed_at:
    cùng nội dung & cùng thời điểm = retry (không trùng); khác thời điểm = lần kiểm tra mới."""
    _clear(db)
    customer = make_customer(db, "S171-C")
    kwargs = dict(
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000003",
        campaign_meta_id="cmp_c",
        observed_spend="50.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
        observed_at=datetime(2026, 10, 26, 3, 0, tzinfo=timezone.utc),
    )
    r1 = reviews.create_review(db, **kwargs)
    reviews.create_review(db, **kwargs)  # retry y hệt (cùng thời điểm) → không ghi thêm
    assert _obs_count(db, r1.id) == 1
    reviews.create_review(db, **{**kwargs, "observed_at": datetime(2026, 10, 26, 6, 0, tzinfo=timezone.utc)})
    assert _obs_count(db, r1.id) == 2, "lần kiểm tra mới (khác thời điểm) phải lưu observation"


def test_late_observation_recorded_but_not_overwrite_current(db):
    """Quan sát đến muộn (observed_at nhỏ hơn hiện hành) → lưu lịch sử nhưng KHÔNG ghi đè hiện hành."""
    _clear(db)
    customer = make_customer(db, "S171-D")
    newer = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000004",
        campaign_meta_id="cmp_late",
        observed_spend="120.00",
        sheet_spend="120.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
        observed_at=datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc),
    )
    late = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000004",
        campaign_meta_id="cmp_late",
        observed_spend="100.00",
        observed_at=datetime(2026, 10, 26, 2, 0, tzinfo=timezone.utc),  # 09:00 VN — đến muộn
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    current = db.get(ManualReview, newer.id)
    assert str(current.observed_spend) == "120.00", "quan sát đến muộn không được ghi đè hiện hành mới hơn"
    assert _obs_count(db, newer.id) == 2, "quan sát đến muộn vẫn phải nằm trong lịch sử"
    history = reviews.list_observations(db, newer.id)
    late_entry = [h for h in history if h["observed_spend"] == "100.00"][0]
    assert late_entry["observed_at"] is not None


def test_manual_not_marked_as_meta_verified(db):
    """Quan sát nhập tay không bao giờ mang nhãn META_API_VERIFIED / checkpoint 09:00."""
    _clear(db)
    customer = make_customer(db, "S171-E")
    review = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000005",
        campaign_meta_id="cmp_e",
        observed_spend="10.00",
        sheet_spend="10.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    for obs in reviews.list_observations(db, review.id):
        assert "META_API_VERIFIED" not in str(obs.get("match_status", ""))
        assert not obs.get("is_checkpoint_9h", False)
    assert review.match_status != "META_API_VERIFIED"


def test_visual_observation_history(db):
    _clear(db)
    customer = make_customer(db, "S171-F")
    review = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000006",
        review_kind=REVIEW_VISUAL,
    )
    assert review.match_status == REVIEW_VISUAL_ONLY
    history = reviews.list_observations(db, review.id)
    assert len(history) == 1
    assert history[0]["observed_spend"] is None


# ---------- F3: verdict theo Customer + Account + Ngày + Currency ----------

def test_match_requires_confirmed_baseline(db):
    """Baseline preview (mapping chưa CONFIRMED) → NEEDS_CONFIRMATION, KHÔNG MATCH dù số khớp."""
    _clear(db)
    customer = make_customer(db, "S171-G")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000007",
        campaign_meta_id="cmp_g",
        observed_spend="500.00",
        sheet_spend="500.00",
        sheet_baseline_confirmed=False,  # preview NEEDS_MAPPING
        campaign_set_complete=True,
    )
    summary = reviews.summarize_by_account_day(db, customer_id=customer.id, business_date=date(2026, 10, 26))
    assert summary[0]["match_status"] == REVIEW_NEEDS_CONFIRMATION


def test_match_requires_campaign_set_complete(db):
    _clear(db)
    customer = make_customer(db, "S171-H")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000008",
        campaign_meta_id="cmp_h",
        observed_spend="500.00",
        sheet_spend="500.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=False,  # chưa xác nhận đủ tập campaign
    )
    summary = reviews.summarize_by_account_day(db, customer_id=customer.id, business_date=date(2026, 10, 26))
    assert summary[0]["match_status"] == REVIEW_INCOMPLETE


def test_two_campaigns_sum_vs_account_baseline_match(db):
    """Nhiều campaign cùng account/ngày → tổng tích lũy mỗi campaign cộng với baseline account 1 lần."""
    _clear(db)
    customer = make_customer(db, "S171-I")
    for camp, spend in (("cmp_i1", "200.00"), ("cmp_i2", "300.00")):
        reviews.create_review(
            db,
            customer_id=customer.id,
            business_date=date(2026, 10, 26),
            ad_account_meta_id="155000000000009",
            campaign_meta_id=camp,
            observed_spend=spend,
            sheet_spend="500.00",  # baseline account+ngày (cùng một số trên Sheets)
            sheet_baseline_confirmed=True,
            campaign_set_complete=True,
        )
    summary = reviews.summarize_by_account_day(db, customer_id=customer.id, business_date=date(2026, 10, 26))
    assert len(summary) == 1
    assert summary[0]["total_observed"] == 500.0
    assert summary[0]["total_sheet"] == 500.0, "baseline account+ngày KHÔNG được cộng 2 lần"
    assert summary[0]["match_status"] == REVIEW_MATCH
    assert len(summary[0]["campaigns"]) == 2, "mỗi Campaign ID chỉ đếm 1 lần"


def test_account_day_diff(db):
    _clear(db)
    customer = make_customer(db, "S171-J")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000010",
        campaign_meta_id="cmp_j1",
        observed_spend="480.00",
        sheet_spend="500.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    summary = reviews.summarize_by_account_day(db, customer_id=customer.id, business_date=date(2026, 10, 26))
    assert summary[0]["match_status"] == REVIEW_DIFF


def test_mixed_currency_not_summed(db):
    """USD + VND cùng account/ngày → tách nhóm currency, KHÔNG cộng trực tiếp."""
    _clear(db)
    customer = make_customer(db, "S171-K")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000011",
        campaign_meta_id="cmp_k_usd",
        observed_spend="100.00",
        sheet_spend="100.00",
        currency="USD",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000011",
        campaign_meta_id="cmp_k_vnd",
        observed_spend="2000000",
        sheet_spend="2000000",
        currency="VND",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    summary = reviews.summarize_by_account_day(db, customer_id=customer.id, business_date=date(2026, 10, 26))
    assert len(summary) == 2, "USD và VND phải tách nhóm theo currency"
    currencies = {s["currency"] for s in summary}
    assert currencies == {"USD", "VND"}
    for group in summary:
        assert group["match_status"] == REVIEW_MATCH  # từng nhóm tự so với baseline cùng đơn vị


def test_vnd_tolerance_one_dong(db):
    """Tolerance theo đơn vị: lệch 0.5 VND (≤ 1 đ) vẫn MATCH; USD giữ 0.01."""
    _clear(db)
    customer = make_customer(db, "S171-L")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000012",
        campaign_meta_id="cmp_l",
        observed_spend="5000000.50",
        sheet_spend="5000000.00",
        currency="VND",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    summary = reviews.summarize_by_account_day(db, customer_id=customer.id, business_date=date(2026, 10, 26))
    assert summary[0]["match_status"] == REVIEW_MATCH, "lệch 0.5 VND phải nằm trong tolerance 1 đ"


def test_gbp_without_rate_needs_confirmation(db):
    _clear(db)
    customer = make_customer(db, "S171-M")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000013",
        campaign_meta_id="cmp_m",
        observed_spend="100.00",
        sheet_spend="100.00",
        currency="GBP",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    summary = reviews.summarize_by_account_day(db, customer_id=customer.id, business_date=date(2026, 10, 26))
    assert summary[0]["match_status"] == REVIEW_NEEDS_CONFIRMATION, "GBP chưa có tolerance/tỷ giá duyệt"


# ---------- F4: báo cáo không trộn tiền tệ ----------

def test_daily_report_currency_grouping(db):
    """Manual VND không được cộng vào dòng USD; fee tính riêng theo từng currency."""
    _clear(db)
    customer = make_customer(db, "S171-N")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000014",
        campaign_meta_id="cmp_n_usd",
        observed_spend="10.00",
        currency="USD",
    )
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000014",
        campaign_meta_id="cmp_n_vnd",
        observed_spend="5000000",
        currency="VND",
    )
    result = reports.daily_spend_rows(db, customer_id=customer.id)
    row = [r for r in result["rows"] if r["business_date"] == "2026-10-26"][0]
    assert row["manual_spend"] == 10.0, "manual_spend (dòng USD) không được chứa VND"
    assert row["manual_by_currency"]["VND"] == 5000000.0
    assert row["manual_by_currency"]["USD"] == 10.0
    assert row["fee"] == 0.4  # 4% của 10 USD — KHÔNG tính trên 5.000.000 VND lẫn USD
    assert row["fee_by_currency"]["VND"] == 200000.0
    assert row["billing_by_currency"]["VND"] == 5200000.0


def test_kpi_fee_grouped_by_currency(db):
    _clear(db)
    customer = make_customer(db, "S171-O")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000015",
        campaign_meta_id="cmp_o_vnd",
        observed_spend="10000000",
        currency="VND",
    )
    kpi = reports.company_kpi(db, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
    assert kpi["service_fee_revenue"]["amount"] is None or kpi["service_fee_revenue"]["amount"] == 0.0
    by_cur = kpi.get("service_fee_revenue_by_currency") or {}
    assert by_cur.get("VND") == 400000.0, "phí VND phải hiện theo đơn vị của nó"
    # profit chỉ tính phần USD — không quy đổi VND khi chưa có tỷ giá;
    # thiếu chi phí account → CHƯA ĐỦ DỮ LIỆU (S17.2: không coi chi phí = 0)
    assert kpi["profit_final"]["amount"] is None
    assert kpi["profit_provisional"]["amount"] is None
    assert kpi["profit_provisional"]["data_state"] == reports.STATE_INSUFFICIENT


def test_kpi_partial_coverage_labeled(db):
    """Mới có dữ liệu 1 khách → không được gọi là số liệu hoàn chỉnh toàn công ty."""
    _clear(db)
    customer = make_customer(db, "S171-P")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="155000000000016",
        campaign_meta_id="cmp_p",
        observed_spend="10.00",
        currency="USD",
        sheet_spend="10.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    kpi = reports.company_kpi(db, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
    state = kpi.get("company_data_state")
    assert state in ("MỘT PHẦN", "CHƯA ĐỦ DỮ LIỆU"), f"phải nhãn rõ độ phủ dữ liệu, nhận {state!r}"
    assert state != "ĐẦY ĐỦ"
