"""Bộ máy báo cáo DÙNG CHUNG cho dữ liệu Manual + Meta API (S17).

Quy tắc nguồn dữ liệu (D-040/D-041):
- Nguồn Meta: snapshot VERIFIED + campaign CONFIRMED (mỗi Campaign ID chỉ đếm lần
  mới nhất — tổng tích lũy D-008; KHÔNG cộng trùng checkpoint 09:00).
- Nguồn Manual: manual_reviews (MANUAL_REVIEWED có số quan sát tay; VISUALLY_REVIEWED
  KHÔNG có số → không được vào tổng tiền, chỉ đếm "đã kiểm tra bằng mắt").
- PHÂN LOẠI nguồn hiển thị: mỗi con số đều mang `source_label`
  (META_API_VERIFIED / MANUAL_REVIEWED / VISUALLY_REVIEWED / MOCK_DATA khi
  Meta connector đang mode mock) — không trộn nhãn.
- Phí dịch vụ: `customer.fee_rate` (mặc định 4% — D-021), tính trên chi tiêu đã
  đối soát; là KHOẢN RIÊNG (finance.py), không gộp vào chi tiêu Meta.
- KPI thiếu dữ liệu → None + `data_state = "CHƯA ĐỦ DỮ LIỆU"`, KHÔNG hiển thị 0 giả.
- Lợi nhuận: chỉ tính khi đủ hai nguồn (doanh thu phí + chi phí) → nhãn TẠM TÍNH;
  chưa đủ → None. KHÔNG tự nghĩ công thức mới (Q-004 chưa duyệt → không tính 30/70).
- Công nợ ≠ lợi nhuận ≠ dòng tiền; tiền nạp USDT giữ đơn vị riêng, không cộng VND.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AdAccount,
    AdAccountAssignment,
    Campaign,
    Customer,
    ManualReview,
    SpendSnapshot,
    UsdtTransaction,
)
from app.models.finance import ENTRY_FINAL, ENTRY_TEMP, LedgerEntry
from app.models.manual_review import REVIEW_MANUAL
from app.models.spend import DATA_VERIFIED
from app.services.finance import compute_service_fee, compute_total_with_fee

META_LABEL_LIVE = "META_API_VERIFIED"
META_LABEL_MOCK = "MOCK_DATA"

# nhãn trạng thái báo cáo
STATE_PROVISIONAL = "TẠM TÍNH"
STATE_FINAL = "ĐÃ CHỐT"
STATE_INSUFFICIENT = "CHƯA ĐỦ DỮ LIỆU"
STATE_PARTIAL = "MỘT PHẦN"
STATE_COMPLETE = "ĐẦY ĐỦ"

_CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    """Làm tròn tiền ROUND_HALF_UP (không dùng banker's rounding của float)."""
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def _money_f(value: Decimal) -> float:
    return float(_money(value))


def meta_connector_mode() -> str:
    from app.connectors.meta import build_connector

    return build_connector().mode


def _meta_source_label() -> str:
    return META_LABEL_MOCK if meta_connector_mode() == "mock" else META_LABEL_LIVE


def _latest_verified_snapshot_per_campaign(db: Session) -> dict[int, SpendSnapshot]:
    """Snapshot VERIFIED mới nhất mỗi campaign (không cộng trùng checkpoint)."""
    snapshots = db.execute(
        select(SpendSnapshot)
        .where(SpendSnapshot.data_status == DATA_VERIFIED)
        .order_by(SpendSnapshot.snapshot_at.asc())
    ).scalars().all()
    latest: dict[int, SpendSnapshot] = {}
    for snapshot in snapshots:
        latest[snapshot.campaign_id] = snapshot  # snapshot_at asc → cứ ghi đè, kết quả là mới nhất
    return latest


def daily_spend_rows(
    db: Session,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
) -> dict[str, Any]:
    """Chi tiêu theo (ngày nghiệp vụ, khách) — trộn nguồn Manual + Meta, TÁCH currency (D-042/F4).

    Meta: campaign CONFIRMED + snapshot VERIFIED → cộng theo ngày nghiệp vụ
    `report_period_end` (mã ngày trong tên — D-026); KHÔNG dùng ngày Meta.
    KHÔNG cộng USD/VND/GBP/EUR/USDT chéo: legacy `meta_spend`/`manual_spend`/`fee`/
    `billing_total` chỉ là phần USD; phần còn lại nằm trong `*_by_currency`.
    """
    latest = _latest_verified_snapshot_per_campaign(db)
    campaigns = db.execute(select(Campaign).where(Campaign.recognition_status == "CONFIRMED")).scalars().all()
    if customer_id is not None:
        campaigns = [c for c in campaigns if c.customer_id == customer_id]
    customer_map = {c.id: c for c in db.execute(select(Customer)).scalars().all()}

    days: dict[str, dict[str, Any]] = {}
    # (customer, ngày nghiệp vụ, campaign) đã có số Meta VERIFIED → quan sát tay cùng campaign KHÔNG cộng trùng
    meta_campaign_keys: set[tuple[int, date, str]] = set()

    def _bump(bucket: dict[str, Decimal], currency: str, amount: Decimal) -> None:
        bucket[currency] = bucket.get(currency, Decimal("0")) + amount

    def day_entry(day: date, c_id: Optional[int]) -> dict[str, Any]:
        key = f"{day.isoformat()}:{c_id}"
        customer = customer_map.get(c_id)
        return days.setdefault(
            key,
            {
                "business_date": day.isoformat(),
                "customer_id": c_id,
                "customer_name": customer.name if customer else None,
                "meta_spend": Decimal("0"),  # USD-only (legacy — UI hiển thị $)
                "manual_spend": Decimal("0"),  # USD-only (legacy)
                "fee": Decimal("0"),  # USD-only (legacy)
                "billing_total": Decimal("0"),  # USD-only (legacy)
                "meta_by_currency": {},
                "manual_by_currency": {},
                "fee_by_currency": {},
                "billing_by_currency": {},
                "meta_source": _meta_source_label(),
                "campaign_count": 0,
            },
        )

    for campaign in campaigns:
        if campaign.report_period_end is None:
            continue  # không có ngày nghiệp vụ → không ôm vào ngày khác (không suy diễn)
        if date_from is not None and campaign.report_period_end < date_from:
            continue
        if date_to is not None and campaign.report_period_end > date_to:
            continue
        snapshot = latest.get(campaign.id)
        if snapshot is None:
            continue  # chưa có dữ liệu → không cộng 0 giả
        entry = day_entry(campaign.report_period_end, campaign.customer_id)
        cur = (snapshot.currency or "USD").upper()
        amount = Decimal(snapshot.spend_amount)
        _bump(entry["meta_by_currency"], cur, amount)
        if cur == "USD":
            entry["meta_spend"] += amount
        entry["campaign_count"] += 1
        if campaign.customer_id is not None:
            meta_campaign_keys.add((campaign.customer_id, campaign.report_period_end, campaign.meta_campaign_id))

    # Manual: MANUAL_REVIEWED có số quan sát; VISUALLY_REVIEWED KHÔNG vào tổng tiền
    reviews = db.execute(select(ManualReview)).scalars().all()
    if customer_id is not None:
        reviews = [r for r in reviews if r.customer_id == customer_id]
    for review in reviews:
        if date_from is not None and review.business_date < date_from:
            continue
        if date_to is not None and review.business_date > date_to:
            continue
        if review.review_kind != REVIEW_MANUAL or review.observed_spend is None:
            continue
        if (
            review.campaign_meta_id
            and (review.customer_id, review.business_date, review.campaign_meta_id) in meta_campaign_keys
        ):
            continue  # đã có chi tiêu Meta VERIFIED cho campaign này → không cộng lần hai
        entry = day_entry(review.business_date, review.customer_id)
        cur = (review.currency or "USD").upper()
        amount = Decimal(review.observed_spend)
        _bump(entry["manual_by_currency"], cur, amount)
        if cur == "USD":
            entry["manual_spend"] += amount

    missing_customers: list[int] = []
    rows: list[dict[str, Any]] = []
    for key in sorted(days):
        entry = days[key]
        customer = customer_map.get(entry["customer_id"]) if entry["customer_id"] else None
        if customer is not None:
            fee_rate = Decimal(customer.fee_rate or 0)
            # fee/billing tính RIÊNG theo từng currency — không quy đổi khi thiếu tỷ giá (D-042)
            currencies = set(entry["meta_by_currency"]) | set(entry["manual_by_currency"])
            for cur in currencies:
                actual = entry["meta_by_currency"].get(cur, Decimal("0")) + entry["manual_by_currency"].get(
                    cur, Decimal("0")
                )
                fee = compute_service_fee(actual, fee_rate)
                total = compute_total_with_fee(actual, fee_rate)
                entry["fee_by_currency"][cur] = _money(fee)
                entry["billing_by_currency"][cur] = _money(total)
            entry["fee"] = entry["fee_by_currency"].get("USD", Decimal("0"))
            entry["billing_total"] = entry["billing_by_currency"].get("USD", Decimal("0"))
        else:
            missing_customers.append(entry["customer_id"])
        rows.append(
            {
                **entry,
                "fee": _money_f(entry["fee"]),
                "billing_total": _money_f(entry["billing_total"]),
                "meta_spend": _money_f(entry["meta_spend"]),
                "manual_spend": _money_f(entry["manual_spend"]),
                "fee_by_currency": {c: _money_f(v) for c, v in entry["fee_by_currency"].items()},
                "billing_by_currency": {c: _money_f(v) for c, v in entry["billing_by_currency"].items()},
                "meta_by_currency": {c: _money_f(v) for c, v in entry["meta_by_currency"].items()},
                "manual_by_currency": {c: _money_f(v) for c, v in entry["manual_by_currency"].items()},
            }
        )

    chart_buckets: dict[str, dict[str, dict[str, Decimal]]] = {}
    chart_fields = (
        "meta_by_currency",
        "manual_by_currency",
        "fee_by_currency",
        "billing_by_currency",
    )
    for entry in days.values():
        bucket = chart_buckets.setdefault(
            entry["business_date"],
            {field: {} for field in chart_fields},
        )
        for field in chart_fields:
            for currency, amount in entry[field].items():
                bucket[field][currency] = bucket[field].get(currency, Decimal("0")) + amount

    chart_rows = [
        {
            "business_date": business_date,
            **{
                field: {currency: _money_f(amount) for currency, amount in bucket[field].items()}
                for field in chart_fields
            },
        }
        for business_date, bucket in sorted(chart_buckets.items())
    ]

    return {
        "meta_source_label": _meta_source_label(),
        "meta_mode": meta_connector_mode(),
        "rows": rows,
        "chart_rows": chart_rows,
        "note": (
            "ngày = ngày nghiệp vụ từ mã ngày tên campaign (D-026) + manual_reviews; "
            "fee = fee_rate từng khách trên chi tiêu đã có nguồn (D-021), tính riêng từng currency "
            "(USD/VND/GBP/EUR — không quy đổi khi thiếu tỷ giá duyệt, D-042); "
            "khách chưa có fee_rate cấu hình → không tự tính fee"
        ),
    }


def _deposits_usdt(db: Session, date_from: Optional[date], date_to: Optional[date]) -> dict[str, Any]:
    rows = db.execute(select(UsdtTransaction).where(UsdtTransaction.match_status == "MATCHED")).scalars().all()
    total = Decimal("0")
    count = 0
    for row in rows:
        day = row.occurred_at.date() if row.occurred_at else None
        if day is None:
            continue
        if date_from is not None and day < date_from:
            continue
        if date_to is not None and day > date_to:
            continue
        total += Decimal(row.amount)
        count += 1
    if count == 0:
        return {"amount": None, "currency": "USDT", "count": 0, "data_state": STATE_INSUFFICIENT}
    return {"amount": _money_f(total), "currency": "USDT", "count": count, "data_state": STATE_PROVISIONAL}


def _account_costs(db: Session, date_from: Optional[date], date_to: Optional[date]) -> dict[str, Any]:
    accounts = db.execute(select(AdAccount).where(AdAccount.purchase_cost.isnot(None))).scalars().all()
    count = 0
    for account in accounts:
        created_day = account.created_at.date() if account.created_at else None
        if created_day is None:
            continue
        if date_from is not None and created_day < date_from:
            continue
        if date_to is not None and created_day > date_to:
            continue
        count += 1
    reason = ("Chi phí cũ không có đơn vị, không thể cộng hoặc trừ vào lợi nhuận."
              if count else "Chưa có dữ liệu chi phí tài khoản có đơn vị.")
    return {"amount": None, "count": count, "data_state": STATE_INSUFFICIENT, "reason": reason}


def company_kpi(
    db: Session,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> dict[str, Any]:
    """10 KPI theo brief — số thiếu → None + CHƯA ĐỦ DỮ LIỆU (KHÔNG 0 giả).

    D-042/F4: tiền tách theo currency — không cộng USD/VND/GBP/EUR/USDT;
    không quy đổi khi thiếu tỷ giá duyệt; profit chỉ tính phần USD đã có nguồn.
    """
    daily = daily_spend_rows(db, date_from=date_from, date_to=date_to)
    rows = daily["rows"]
    meta_usd = sum(r["meta_spend"] for r in rows)
    manual_usd = sum(r["manual_spend"] for r in rows)
    fee_usd = sum(r["fee"] for r in rows)
    billing_usd = sum(r["billing_total"] for r in rows)

    def _merge_by_currency(field: str) -> dict[str, float]:
        merged: dict[str, Decimal] = {}
        for r in rows:
            for cur, val in (r.get(field) or {}).items():
                merged[cur] = merged.get(cur, Decimal("0")) + Decimal(str(val))
        return {cur: _money_f(val) for cur, val in merged.items()}

    meta_by_currency = _merge_by_currency("meta_by_currency")
    manual_by_currency = _merge_by_currency("manual_by_currency")
    fee_by_currency = _merge_by_currency("fee_by_currency")
    billing_by_currency = _merge_by_currency("billing_by_currency")

    deposits = _deposits_usdt(db, date_from, date_to)
    costs = _account_costs(db, date_from, date_to)

    customers = db.execute(select(Customer)).scalars().all()
    checked_ids: set[int] = set()
    for review in db.execute(select(ManualReview)).scalars().all():
        if date_to is not None and review.business_date > date_to:
            continue
        if date_from is not None and review.business_date < date_from:
            continue
        checked_ids.add(review.customer_id)
    with_data_ids: set[int] = set(checked_ids)
    for r in rows:
        if r["customer_id"] is not None and (
            r["meta_spend"] or r["manual_spend"] or r["meta_by_currency"] or r["manual_by_currency"]
        ):
            with_data_ids.add(r["customer_id"])
    campaigns_green = sum(
        1
        for c in db.execute(select(Campaign)).scalars().all()
        if c.recognition_status == "CONFIRMED" and c.customer_id is not None
    )

    # Độ phủ dữ liệu (D-042): ĐẦY ĐỦ chỉ khi live Meta + mọi khách có dữ liệu trong kỳ
    if not with_data_ids:
        company_state = STATE_INSUFFICIENT
    elif len(with_data_ids) >= len(customers) and _meta_source_label() == META_LABEL_LIVE:
        company_state = STATE_COMPLETE
    else:
        company_state = STATE_PARTIAL

    profit = None
    profit_state = STATE_INSUFFICIENT

    return {
        "window": {
            "from": date_from.isoformat() if date_from else None,
            "to": date_to.isoformat() if date_to else None,
        },
        "meta_source_label": _meta_source_label(),
        "meta_mode": meta_connector_mode(),
        "company_data_state": company_state,
        "coverage": {"customers_with_data": len(with_data_ids), "customers_total": len(customers)},
        "meta_spend": {
            "amount": _money_f(Decimal(str(meta_usd))) if meta_usd else None,
            "currency": "USD",
            "by_currency": meta_by_currency,
            "data_state": STATE_PROVISIONAL if meta_usd else STATE_INSUFFICIENT,
        },
        "service_fee_revenue": {
            "amount": _money_f(Decimal(str(fee_usd))) if fee_usd else None,
            "currency": "USD",
            "by_currency": fee_by_currency,
            "data_state": STATE_PROVISIONAL if fee_usd else STATE_INSUFFICIENT,
        },
        "service_fee_revenue_by_currency": fee_by_currency,
        "manual_spend_by_currency": manual_by_currency,
        "deposits": deposits,  # USDT — giữ đơn vị riêng, KHÔNG cộng VND (D-013/Q-005)
        "account_costs": {
            **costs,
            "currency": None,
        },
        "operating_costs": {"amount": None, "data_state": STATE_INSUFFICIENT},  # chưa có nguồn (Q-008)
        "profit_provisional": {
            "amount": profit,
            "data_state": profit_state,
            "note": (
                "Chưa đủ dữ liệu chi phí account có đơn vị để trừ vào phí. "
                "Các loại tiền giữ riêng, không quy đổi khi thiếu tỷ giá được duyệt."
            ),
        },
        "profit_final": {"amount": None, "data_state": STATE_INSUFFICIENT},
        "billing_total": {
            "amount": _money_f(Decimal(str(billing_usd))) if billing_usd else None,
            "currency": "USD",
            "by_currency": billing_by_currency,
        },
        "receivable": {
            "amount": None,
            "data_state": STATE_INSUFFICIENT,
            "note": "cần tỷ giá duyệt USDT→VND (Q-005) và billing đã chốt mới có công nợ chính xác",
        },
        "customers_checked": len(checked_ids),
        "customers_unchecked": len(customers) - len(checked_ids),
        "campaigns_green": campaigns_green,
    }


def recent_transactions(db: Session, limit: int = 5, customer_id: Optional[int] = None) -> dict[str, Any]:
    """Read recent recorded USDT transactions; this adapter does not invent ledger transactions."""
    statement = (
        select(UsdtTransaction, Customer.name)
        .outerjoin(Customer, Customer.id == UsdtTransaction.customer_id)
        .order_by(UsdtTransaction.occurred_at.desc(), UsdtTransaction.id.desc())
        .limit(limit)
    )
    if customer_id is not None:
        statement = statement.where(UsdtTransaction.customer_id == customer_id)

    transactions = db.execute(statement).all()
    return {
        "rows": [
            {
                "id": transaction.id,
                "tx_hash": transaction.tx_hash,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "occurred_at": transaction.occurred_at.isoformat(),
                "status": transaction.match_status,
                "customer_id": transaction.customer_id,
                "customer_name": customer_name,
            }
            for transaction, customer_name in transactions
        ],
        "source": "usdt_transactions",
    }


def ledger_state_mix(db: Session) -> dict[str, int]:
    entries = db.execute(select(LedgerEntry)).scalars().all()
    final_count = sum(1 for e in entries if e.state == ENTRY_FINAL)
    temp_count = sum(1 for e in entries if e.state == ENTRY_TEMP)
    return {STATE_FINAL: final_count, STATE_PROVISIONAL: temp_count}


def customer_report(
    db: Session,
    customer_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> dict[str, Any]:
    """Báo cáo chi tiết 1 khách — dữ liệu chỉ lấy từ DB, không suy diễn (Phần 3)."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        return {"error": "customer không tồn tại"}
    kpi = company_kpi(db, date_from=date_from, date_to=date_to, )  # tổng công ty chỉ để tham chiếu nhãn
    daily = daily_spend_rows(db, date_from=date_from, date_to=date_to, customer_id=customer_id)
    from app.services.reviews import list_reviews, summarize_by_account_day

    assignments = db.execute(
        select(AdAccountAssignment).where(AdAccountAssignment.customer_id == customer_id)
    ).scalars().all()
    account_map = {a.id: a for a in db.execute(select(AdAccount)).scalars().all()}
    accounts_history = [
        {
            "ad_account_meta_id": account_map[h.ad_account_id].meta_ad_account_id if h.ad_account_id in account_map else None,
            "status": account_map[h.ad_account_id].status if h.ad_account_id in account_map else None,
            "valid_from": h.valid_from.isoformat() if h.valid_from else None,
            "valid_to": h.valid_to.isoformat() if h.valid_to else None,
        }
        for h in sorted(assignments, key=lambda a: (a.valid_to is None, a.valid_to or datetime.min.replace(tzinfo=timezone.utc)))
    ]
    deposits_usdt = db.execute(
        select(UsdtTransaction).where(
            UsdtTransaction.customer_id == customer_id,
            UsdtTransaction.match_status == "MATCHED",
        )
    ).scalars().all()
    return {
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "fee_rate": str(customer.fee_rate),
            "recon_mode": customer.recon_mode,
            "profit_share_enabled": customer.profit_share_enabled,
        },
        "meta_source_label": _meta_source_label(),
        "company_reference_state": kpi["meta_spend"]["data_state"],
        "daily_spend": daily,
        "accounts_history": accounts_history,
        "campaigns": [
            {
                "meta_campaign_id": c.meta_campaign_id,
                "name": c.name,
                "recognition_status": c.recognition_status,
                "report_period_start": c.report_period_start.isoformat() if c.report_period_start else None,
                "report_period_end": c.report_period_end.isoformat() if c.report_period_end else None,
                "meta_status": c.meta_status,
            }
            for c in db.execute(select(Campaign).where(Campaign.customer_id == customer_id)).scalars().all()
        ],
        "deposits_usdt": [
            {
                "tx_hash": t.tx_hash[:8] + "…",
                "amount": str(t.amount),
                "currency": t.currency,
                "occurred_at": t.occurred_at.isoformat() if t.occurred_at else None,
            }
            for t in deposits_usdt
        ],
        "account_summary_by_day": summarize_by_account_day(
            db, customer_id=customer_id, business_date=None,
        ),
        "reviews": list_reviews(db, customer_id=customer_id),
        "fee_note": (
            f"fee_rate = {customer.fee_rate} theo cấu hình khách (D-021/D-037); "
            "khách khác 4% chưa được duyệt → vẫn hiển thị cấu hình nhưng không tự xác nhận"
        ),
    }
