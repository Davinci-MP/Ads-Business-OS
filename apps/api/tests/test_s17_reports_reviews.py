"""S17 — đối chiếu thủ công dùng mắt (reviews.py) + bộ máy báo cáo chung (reports.py).

Quy tắc kiểm: VISUAL không MATCH; manual có số → MATCH/DIFF; idempotent;
KPI thiếu dữ liệu → None (KHÔNG 0 giả); fee 4% khoản riêng; không cộng trùng checkpoint.
"""

from datetime import date

from sqlalchemy import delete

from app.models import ManualReview, SpendSnapshot, UsdtTransaction
from app.services import reports, reviews
from app.services.reviews import (
    REVIEW_DIFF,
    REVIEW_MANUAL,
    REVIEW_MATCH,
    REVIEW_NEEDS_SHEET,
    REVIEW_VISUAL,
    REVIEW_VISUAL_ONLY,
)
from tests.conftest import add_snapshot, datetime_utc, make_campaign, make_customer


def _clear_reviews(db):
    db.execute(delete(ManualReview))
    db.execute(delete(SpendSnapshot))
    db.commit()


def test_visual_review_not_match(db):
    """Quy tắc: đánh dấu đã kiểm tra bằng mắt (không nhập số) → VISUAL_ONLY, KHÔNG tự coi MATCH."""
    customer = make_customer(db, "SPAN17-A")
    review = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 25),
        ad_account_meta_id="111111111111171",
        review_kind=REVIEW_VISUAL,
    )
    assert review.match_status == REVIEW_VISUAL_ONLY
    assert review.observed_spend is None


def test_manual_review_match_and_diff(db):
    """S17.1 (D-042): verdict theo nhóm Customer+Account+Ngày+Currency — 1 campaign/account vẫn MATCH/DIFF."""
    customer = make_customer(db, "SPAN17-B")
    review_match = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 25),
        ad_account_meta_id="111111111111172",
        review_kind=REVIEW_MANUAL,
        campaign_meta_id="cmp_match",
        observed_spend="10.00",
        sheet_spend="10.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    review_diff = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 25),
        ad_account_meta_id="111111111111182",  # account khác → nhóm khác
        review_kind=REVIEW_MANUAL,
        campaign_meta_id="cmp_diff",
        observed_spend="12.50",
        sheet_spend="10.00",
        sheet_baseline_confirmed=True,
        campaign_set_complete=True,
    )
    assert review_match.match_status == REVIEW_MATCH
    assert review_diff.match_status == REVIEW_DIFF
    assert str(review_diff.delta) == "2.50"


def test_manual_review_needs_sheet_baseline(db):
    """Có số quan sát nhưng chưa có baseline Sheets → NEEDS_SHEET_BASELINE, không phán MATCH."""
    customer = make_customer(db, "SPAN17-C")
    review = reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 25),
        ad_account_meta_id="111111111111173",
        campaign_meta_id="cmp_nb",
        observed_spend="5.00",
    )
    assert review.match_status == REVIEW_NEEDS_SHEET


def test_review_idempotent_no_dup(db):
    """Challenges ghi trùng: tạo 2 lần cùng key → 1 bản (idempotent)."""
    customer = make_customer(db, "SPAN17-D")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 25),
        ad_account_meta_id="111111111111174",
        campaign_meta_id="cmp_dup",
        observed_spend="5.00",
        sheet_spend="5.00",
    )
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 25),
        ad_account_meta_id="111111111111174",
        campaign_meta_id="cmp_dup",
        observed_spend="5.00",
        sheet_spend="5.00",
    )
    count = len(db.execute(
        __import__("sqlalchemy").select(ManualReview).where(ManualReview.customer_id == customer.id)
    ).scalars().all())
    assert count == 1


def test_review_invalid_input_rejected(db):
    customer = make_customer(db, "SPAN17-E")
    try:
        reviews.create_review(
            db,
            customer_id=customer.id,
            business_date=date(2026, 10, 25),
            ad_account_meta_id="111111111111175",
            review_kind=REVIEW_MANUAL,
            observed_spend="5.00",
        )
    except ValueError as exc:
        assert "campaign_meta_id" in str(exc)
    else:
        raise AssertionError("thiếu campaign_meta_id phải bị từ chối")


def test_summarize_by_account_day(db):
    """S17.1 (D-042): observed cộng nhiều campaign; baseline account+ngày chỉ MỘT lần."""
    customer = make_customer(db, "SPAN17-F")
    for camp, spend in (("cmp_sum1", "3.00"), ("cmp_sum2", "4.00")):
        reviews.create_review(
            db,
            customer_id=customer.id,
            business_date=date(2026, 10, 26),
            ad_account_meta_id="111111111111176",
            campaign_meta_id=camp,
            observed_spend=spend,
            sheet_spend="7.00",  # baseline account+ngày (một số trên Sheets)
            sheet_baseline_confirmed=True,
            campaign_set_complete=True,
        )
    summary = reviews.summarize_by_account_day(db, customer_id=customer.id, business_date=date(2026, 10, 26))
    assert len(summary) == 1
    assert summary[0]["total_observed"] == 7.0
    assert summary[0]["total_sheet"] == 7.0, "baseline account+ngày không được cộng theo campaign"
    assert summary[0]["match_status"] == REVIEW_MATCH
    assert len(summary[0]["campaigns"]) == 2


def test_daily_report_mixes_manual_and_meta(db):
    """Bộ máy chung: chi tiêu ngày gồm Meta snapshot VERIFIED + manual observed — không cộng trùng checkpoint."""
    _clear_reviews(db)
    customer = make_customer(db, "SPAN17-G")
    campaign = make_campaign(db, "cmp_sp17_mix", customer=customer, name="1025-KH")
    campaign.report_period_start = date(2026, 10, 25)
    campaign.report_period_end = date(2026, 10, 25)
    db.commit()
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 2), 1000.00, is_checkpoint_9h=True)
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 13), 1002.84)
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="111111111111177",
        campaign_meta_id="cmp_manual_observed",
        observed_spend="12.00",
        sheet_spend="12.00",
    )
    # visually reviewed ngày 26 — không tính vào manual_spend
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="111111111111178",
        review_kind=REVIEW_VISUAL,
    )
    result = reports.daily_spend_rows(db)
    assert result["meta_mode"] == "mock"
    assert result["meta_source_label"] == reports.META_LABEL_MOCK  # mock mode — nhãn rõ, không nói VERIFIED Meta thật
    by_day = {(r["business_date"], r["customer_id"]): r for r in result["rows"]}
    row_meta = by_day[("2026-10-25", customer.id)]
    assert row_meta["meta_spend"] == 1002.84  # tổng tích lũy — checkpoint không cộng trùng
    row_manual = by_day[("2026-10-26", customer.id)]
    assert row_manual["manual_spend"] == 12.0
    assert row_manual["meta_spend"] == 0.0
    # fee 4% trên tổng chi tiêu nguồn (D-021); 12.00 → 0.48; billing 12.48
    assert row_manual["fee"] == 0.48
    assert row_manual["billing_total"] == 12.48


def test_daily_chart_rows_group_by_day_without_mixing_currencies(db):
    _clear_reviews(db)
    usd_customer = make_customer(db, "S17-CHART-USD")
    vnd_customer = make_customer(db, "S17-CHART-VND")
    business_date = date(2026, 10, 27)
    for customer, account_id, campaign_id, spend, currency in (
        (usd_customer, "chart-usd-account", "chart-usd-campaign", "10.00", "USD"),
        (vnd_customer, "chart-vnd-account", "chart-vnd-campaign", "1000.00", "VND"),
    ):
        reviews.create_review(
            db,
            customer_id=customer.id,
            business_date=business_date,
            ad_account_meta_id=account_id,
            campaign_meta_id=campaign_id,
            observed_spend=spend,
            currency=currency,
        )

    result = reports.daily_spend_rows(db, date_from=business_date, date_to=business_date)

    assert len(result["chart_rows"]) == 1
    chart_row = result["chart_rows"][0]
    assert chart_row["business_date"] == business_date.isoformat()
    assert chart_row["manual_by_currency"] == {"USD": 10.0, "VND": 1000.0}
    assert chart_row["fee_by_currency"] == {"USD": 0.4, "VND": 40.0}
    assert chart_row["billing_by_currency"] == {"USD": 10.4, "VND": 1040.0}


def test_recent_transactions_reads_only_existing_records_and_respects_filters(db):
    customer = make_customer(db, "S17-TRANSACTION-CUSTOMER")
    tx_hashes = ("s17-transaction-first", "s17-transaction-second")
    try:
        first = UsdtTransaction(
            tx_hash=tx_hashes[0],
            amount="12.500000",
            currency="USDT",
            wallet_address="T-test-wallet",
            occurred_at=datetime_utc(2026, 10, 26, 10),
            match_status="MATCHED",
            customer_id=customer.id,
        )
        second = UsdtTransaction(
            tx_hash=tx_hashes[1],
            amount="7.250000",
            currency="USDT",
            wallet_address="T-test-wallet",
            occurred_at=datetime_utc(2026, 10, 27, 10),
            match_status="UNMATCHED",
            customer_id=None,
        )
        db.add_all([first, second])
        db.commit()

        result = reports.recent_transactions(db, limit=1, customer_id=customer.id)
        empty = reports.recent_transactions(db, customer_id=999999)

        assert len(result["rows"]) == 1
        assert result["rows"][0]["tx_hash"] == tx_hashes[0]
        assert result["rows"][0]["amount"] == "12.500000"
        assert result["rows"][0]["status"] == "MATCHED"
        assert result["rows"][0]["customer_name"] == customer.name
        assert empty["rows"] == []
    finally:
        db.execute(delete(UsdtTransaction).where(UsdtTransaction.tx_hash.in_(tx_hashes)))
        db.commit()


def test_kpi_null_not_fake_zero(db):
    """KPI thiếu dữ liệu → None + CHƯA ĐỦ DỮ LIỆU (không 0 giả)."""
    _clear_reviews(db)
    make_customer(db, "SPAN17-H")
    result = reports.company_kpi(db, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
    assert result["meta_spend"]["amount"] is None
    assert result["meta_spend"]["data_state"] == reports.STATE_INSUFFICIENT
    assert result["deposits"]["amount"] is None
    assert result["deposits"]["data_state"] == reports.STATE_INSUFFICIENT
    assert result["profit_final"]["amount"] is None
    assert result["meta_source_label"] == reports.META_LABEL_MOCK


def test_kpi_with_manual_data_provisional(db):
    _clear_reviews(db)
    customer = make_customer(db, "SPAN17-I")
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id="111111111111179",
        campaign_meta_id="cmp_kpi",
        observed_spend="100.00",
        sheet_spend="100.00",
    )
    result = reports.company_kpi(db, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
    assert result["service_fee_revenue"]["amount"] == 4.0  # fee 4% từ manual obs
    # S17.2: chưa có chi phí account (purchase_cost) → không được coi chi phí = 0
    assert result["profit_provisional"]["amount"] is None
    assert result["profit_provisional"]["data_state"] == reports.STATE_INSUFFICIENT
    assert result["customers_checked"] == 1  # SPAN17-I có review; khách cũ của test khác không đếm nhầm


def test_customer_report_missing_customer(db):
    result = reports.customer_report(db, 999999)
    assert result.get("error")


def test_customer_report_full_flow(db):
    _clear_reviews(db)
    customer = make_customer(db, "SPAN17-J")
    campaign = make_campaign(db, "cmp_sp17_cust", customer=customer, name="1026-KH")
    campaign.report_period_start = date(2026, 10, 26)
    campaign.report_period_end = date(2026, 10, 26)
    db.commit()
    add_snapshot(db, campaign, datetime_utc(2026, 10, 26, 9), 50.0)
    reviews.create_review(
        db,
        customer_id=customer.id,
        business_date=date(2026, 10, 26),
        ad_account_meta_id=f"act_cmp_sp17_cust",
        campaign_meta_id="cmp_sp17_cust",
        observed_spend="50.00",
        sheet_spend="49.50",
        sheet_baseline_confirmed=True,  # S17.1: baseline phải từ mapping CONFIRMED mới phán DIFF
        campaign_set_complete=True,
    )
    result = reports.customer_report(db, customer.id)
    assert result["customer"]["name"] == "SPAN17-J"
    assert result["customer"]["fee_rate"] in ("0.0400", "0.04")  # SQLite Numeric mất scale trailing zeros
    assert len(result["campaigns"]) == 1
    assert len(result["reviews"]) == 1
    assert result["reviews"][0]["match_status"] == REVIEW_DIFF
    # account/campaignGHÉP minh xác theo ngày nghiệp vụ (report_period_end) ngày 26/10
    assert result["daily_spend"]["rows"][0]["business_date"] == "2026-10-26"
