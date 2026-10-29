"""Service đối chiếu thủ công (S17/S17.1 — D-041/D-042, không cần Meta token).

Quy tắc:
- VISUALLY_REVIEWED → KHÔNG tự coi MATCH (VISUAL_ONLY).
- Quan sát nhập tay KHÔNG BAO GIỜ nhãn META_API_VERIFIED / checkpoint 09:00.
- Lịch sử APPEND-ONLY qua manual_review_observations; idempotency_key UNIQUE
  (retry cùng key → trả kết quả cũ, không ghi thêm).
- MATCH/DIFF kết luận ở mức Customer + Account + Business Date + Currency (D-042):
  tổng tích lũy các campaign (mỗi Campaign ID đếm 1 lần) so với baseline Sheets
  account+ngày MỘT lần; thiếu điều kiện → INCOMPLETE / NEEDS_CONFIRMATION /
  NEEDS_SHEET_BASELINE, không tự phán.
- Đọc Google Sheets nằm trên route/connector — service chỉ nhận baseline đã đọc.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Campaign, Customer, ManualReview, ManualReviewObservation
from app.models.customer import utcnow
from app.models.manual_review import (
    REVIEW_DIFF,
    REVIEW_INCOMPLETE,
    REVIEW_MANUAL,
    REVIEW_MATCH,
    REVIEW_NEEDS_CONFIRMATION,
    REVIEW_NEEDS_SHEET,
    REVIEW_RECORDED,
    REVIEW_VISUAL,
    REVIEW_VISUAL_ONLY,
)
from app.services.sheets_compare import tolerance_for_currency

_VERDICT_CURRENCIES = ("USD", "VND")  # GBP/EUR chưa có tolerance/tỷ giá duyệt → NEEDS_CONFIRMATION


def _parse_decimal(value: Any, field: str) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field} không phải số hợp lệ") from exc


def _derive_key(
    customer_id: int,
    business_date: date,
    ad_ref: str,
    campaign_meta_id: Optional[str],
    kind: str,
    observed: Optional[Decimal],
    sheet_spend: Optional[Decimal],
    currency: str,
    observed_at: Optional[datetime] = None,
) -> str:
    """Key suy ra từ nội dung — CHỈ là lưới an toàn cho client không gửi key.

    Gồm `observed_at` để hai lần kiểm tra thực khác thời điểm (kể cả cùng số tiền)
    KHÔNG bị coi là trùng (D-042: mỗi lần kiểm tra hợp lệ phải lưu được observation).
    """
    raw = "|".join(
        [
            str(customer_id),
            business_date.isoformat(),
            ad_ref,
            campaign_meta_id or "",
            kind,
            str(observed) if observed is not None else "",
            str(sheet_spend) if sheet_spend is not None else "",
            currency,
            observed_at.isoformat() if observed_at is not None else "",
        ]
    )
    return "content:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _group_reviews(
    db: Session,
    customer_id: int,
    business_date: date,
    ad_account_meta_id: str,
    currency: str,
) -> list[ManualReview]:
    """Tất cả review MANUAL cùng (customer, ngày, account, currency) — mỗi campaign 1 dòng (unique)."""
    rows = db.execute(
        select(ManualReview).where(
            ManualReview.customer_id == customer_id,
            ManualReview.business_date == business_date,
            ManualReview.ad_account_meta_id == ad_account_meta_id,
            ManualReview.currency == currency,
            ManualReview.review_kind == REVIEW_MANUAL,
        )
    ).scalars().all()
    return list(rows)


def _recompute_group_verdict(
    db: Session,
    customer_id: int,
    business_date: date,
    ad_account_meta_id: str,
    currency: str,
    account_conflict: bool = False,
) -> tuple[Optional[str], Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    """Kết luận ở mức Customer+Account+Ngày+Currency.

    Trả (verdict, total_observed, baseline, delta). Baseline = max sheet_spend
    trong nhóm (baseline account+ngày chỉ đếm MỘT lần — không cộng theo campaign).
    """
    rows = _group_reviews(db, customer_id, business_date, ad_account_meta_id, currency)
    if not rows:
        return None, None, None, None
    total_observed = sum((r.observed_spend or Decimal("0")) for r in rows)
    baselines = [r.sheet_spend for r in rows if r.sheet_spend is not None]
    baseline = max(baselines) if baselines else None

    if currency not in _VERDICT_CURRENCIES:
        return REVIEW_NEEDS_CONFIRMATION, total_observed, baseline, None
    if baseline is None:
        return REVIEW_NEEDS_SHEET, total_observed, None, None
    if len({Decimal(b) for b in baselines}) > 1:
        # nhiều baseline khác nhau cho cùng account+ngày → xung đột phân bổ, không tự chọn số lớn nhất
        return REVIEW_NEEDS_CONFIRMATION, total_observed, baseline, None
    if account_conflict or not all(r.sheet_baseline_confirmed for r in rows):
        # baseline preview (mapping chưa CONFIRMED) hoặc xung đột phân bổ tài khoản (D-039)
        return REVIEW_NEEDS_CONFIRMATION, total_observed, baseline, None
    if not all(r.campaign_set_complete for r in rows):
        return REVIEW_INCOMPLETE, total_observed, baseline, None
    delta = total_observed - baseline
    tol = Decimal(str(tolerance_for_currency(currency)))
    verdict = REVIEW_MATCH if abs(delta) <= tol else REVIEW_DIFF
    return verdict, total_observed, baseline, delta


def create_review(
    db: Session,
    customer_id: int,
    business_date: date,
    ad_account_meta_id: Optional[str],
    review_kind: str = REVIEW_MANUAL,
    campaign_meta_id: Optional[str] = None,
    campaign_name: Optional[str] = None,
    observed_spend: Any = None,
    sheet_spend: Any = None,
    currency: str = "USD",
    sheet_key: Optional[str] = None,
    sheet_name: Optional[str] = None,
    note: Optional[str] = None,
    reviewed_by: str = "owner",
    observed_at: Optional[datetime] = None,
    idempotency_key: Optional[str] = None,
    sheet_baseline_confirmed: bool = False,
    campaign_set_complete: bool = False,
    account_conflict: bool = False,
) -> ManualReview:
    """Ghi 1 lần kiểm tra (tạo/cập nhật hiện hành + append observation, 1 transaction).

    - MANUAL_REVIEWED: cần campaign_meta_id + observed_spend.
    - VISUALLY_REVIEWED: không nhập số → match_status luôn VISUAL_ONLY.
    - retry cùng idempotency_key (hoặc cùng nội dung) → trả kết quả cũ, không ghi thêm.
    - quan sát đến muộn (observed_at < hiện hành) → lưu lịch sử, KHÔNG ghi đè hiện hành.
    """
    kind = (review_kind or REVIEW_MANUAL).strip().upper()
    if kind not in (REVIEW_MANUAL, REVIEW_VISUAL):
        raise ValueError(f"review_kind phải là {REVIEW_MANUAL} hoặc {REVIEW_VISUAL}")

    ad_ref = (ad_account_meta_id or "").strip()
    if not ad_ref:
        raise ValueError("thiếu ad_account_meta_id")

    observed = _parse_decimal(observed_spend, "observed_spend")
    baseline_input = _parse_decimal(sheet_spend, "sheet_spend")
    campaign_meta_id = (campaign_meta_id or "").strip() or None
    currency = (currency or "USD").strip().upper()

    if kind == REVIEW_VISUAL:
        observed = None
    else:
        if campaign_meta_id is None or observed is None:
            raise ValueError("MANUAL_REVIEWED cần campaign_meta_id + observed_spend")

    now = utcnow()
    observed_dt = observed_at or now
    if observed_dt.tzinfo is None:
        observed_dt = observed_dt.replace(tzinfo=timezone.utc)

    key = idempotency_key or _derive_key(
        customer_id,
        business_date,
        ad_ref,
        campaign_meta_id,
        kind,
        observed,
        baseline_input,
        currency,
        observed_dt,
    )
    if len(key) > 128:
        raise ValueError("idempotency_key quá dài (tối đa 128 ký tự)")
    existing_obs = db.execute(
        select(ManualReviewObservation).where(ManualReviewObservation.idempotency_key == key)
    ).scalar_one_or_none()
    if existing_obs is not None:
        # retry cùng request → trả kết quả cũ, không ghi thêm (idempotent)
        existing_review = db.get(ManualReview, existing_obs.review_id)
        if existing_review is None or (
            existing_review.customer_id,
            existing_review.business_date,
            existing_review.ad_account_meta_id,
            existing_review.campaign_meta_id,
            existing_review.review_kind,
        ) != (customer_id, business_date, ad_ref, campaign_meta_id, kind):
            # cùng key nhưng nội dung khác → KHÔNG được trả kết quả của request khác
            raise ValueError("idempotency_key đã dùng cho một request khác — dùng key mới cho lần kiểm tra mới")
        return existing_review

    review = db.execute(
        select(ManualReview).where(
            ManualReview.customer_id == customer_id,
            ManualReview.business_date == business_date,
            ManualReview.ad_account_meta_id == ad_ref,
            ManualReview.campaign_meta_id == campaign_meta_id,
            ManualReview.review_kind == kind,
        )
    ).scalar_one_or_none()
    if review is not None and (review.currency or "USD").upper() != currency:
        # không tự đổi đơn vị của một campaign đã ghi — tránh trộn nhóm và IntegrityError
        raise ValueError(
            f"campaign {campaign_meta_id or ''} của account {ad_ref} đã ghi với currency "
            f"{(review.currency or 'USD').upper()} — không tự đổi sang {currency}; cần xử lý riêng"
        )
    if review is None:
        review = ManualReview(
            customer_id=customer_id,
            business_date=business_date,
            ad_account_meta_id=ad_ref,
            campaign_meta_id=campaign_meta_id,
            campaign_name=campaign_name,
            review_kind=kind,
            currency=currency,
            sheet_key=sheet_key,
            sheet_name=sheet_name,
            reviewed_by=reviewed_by,
        )
        db.add(review)

    # Quan sát đến muộn KHÔNG ghi đè hiện hành — quyết định trước khi recompute nhóm
    is_late = review.last_observed_at is not None and observed_dt < review.last_observed_at

    # baseline account+ngày cung cấp trong lần này → gánh vào dòng hiện hành trước khi recomput nhóm
    if baseline_input is not None and not is_late:
        review.sheet_spend = baseline_input
    review.sheet_baseline_confirmed = bool(sheet_baseline_confirmed) or bool(review.sheet_baseline_confirmed)
    review.campaign_set_complete = bool(campaign_set_complete) or bool(review.campaign_set_complete)
    if review.campaign_name is None and campaign_name:
        review.campaign_name = campaign_name
    # ghi số quan sát TRƯỚC khi recompute để tổng nhóm phản ánh lần này (chỉ hiện hành, không đụng nếu muộn)
    if kind == REVIEW_MANUAL and not is_late:
        review.observed_spend = observed
    db.flush()

    if kind == REVIEW_VISUAL:
        verdict = REVIEW_VISUAL_ONLY
        total_observed = None
        baseline = None
        delta = None
    else:
        verdict, total_observed, baseline, delta = _recompute_group_verdict(
            db, customer_id, business_date, ad_ref, currency, account_conflict=account_conflict
        )
        verdict = verdict or REVIEW_RECORDED

    observation = ManualReviewObservation(
        review_id=review.id,
        observed_spend=observed,
        currency=currency,
        sheet_baseline=baseline,
        delta_account_day=delta,
        match_status=verdict,
        idempotency_key=key,
        observed_at=observed_dt,
        recorded_at=now,
        reviewed_by=reviewed_by,
        note=note,
    )
    db.add(observation)

    # Cập nhật hiện hành: quan sát đến muộn KHÔNG ghi đè trạng thái mới hơn
    if not is_late:
        review.match_status = verdict
        review.delta = delta
        review.last_observed_at = observed_dt
    else:
        observation.note = ((observation.note + " | ") if observation.note else "") + "quyền đến muộn: không ghi đè hiện hành"

    db.add(
        AuditLog(
            actor=reviewed_by,
            action="MANUAL_REVIEW_LATE_OBSERVATION" if is_late else "MANUAL_REVIEW_RECORDED",
            entity_type="manual_review",
            entity_id=str(review.id),
            detail={
                "customer_id": customer_id,
                "business_date": business_date.isoformat(),
                "ad_account": ad_ref,
                "campaign": campaign_meta_id,
                "observed": str(observed) if observed is not None else None,
                "baseline": str(baseline) if baseline is not None else None,
                "delta_account_day": str(delta) if delta is not None else None,
                "review_kind": kind,
                "match_status": verdict,
                "observed_at": observed_dt.isoformat(),
                "idempotency_key": key,
            },
        )
    )
    db.commit()
    return review


def list_observations(db: Session, review_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Lịch sử quan sát của 1 review — mới trước (append-only, không sửa/xoá)."""
    rows = db.execute(
        select(ManualReviewObservation)
        .where(ManualReviewObservation.review_id == review_id)
        .order_by(ManualReviewObservation.observed_at.desc(), ManualReviewObservation.recorded_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "id": r.id,
            "review_id": r.review_id,
            "observed_spend": str(r.observed_spend) if r.observed_spend is not None else None,
            "currency": r.currency,
            "sheet_baseline": str(r.sheet_baseline) if r.sheet_baseline is not None else None,
            "delta_account_day": str(r.delta_account_day) if r.delta_account_day is not None else None,
            "match_status": r.match_status,
            "observed_at": r.observed_at.isoformat() if r.observed_at else None,
            "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            "reviewed_by": r.reviewed_by,
            "note": r.note,
        }
        for r in rows
    ]


def summarize_by_account_day(
    db: Session,
    customer_id: Optional[int],
    business_date: Optional[date],
) -> list[dict[str, Any]]:
    """Tổng hợp theo (ngày nghiệp vụ, account, currency) — verdict tính lại từ hiện hành.

    - Mỗi Campaign ID chỉ đếm 1 lần (unique row hiện hành).
    - Baseline account+ngày đếm MỘT lần (max trong nhóm), không cộng theo campaign.
    - Nhóm khác currency KHÔNG cộng chéo.
    """
    query = select(ManualReview)
    if customer_id is not None:
        query = query.where(ManualReview.customer_id == customer_id)
    if business_date is not None:
        query = query.where(ManualReview.business_date == business_date)
    reviews = db.execute(query.order_by(ManualReview.business_date.asc())).scalars().all()
    grouped: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for review in reviews:
        key = (review.business_date.isoformat(), review.ad_account_meta_id, review.currency, review.customer_id)
        entry = grouped.setdefault(
            key,
            {
                "business_date": review.business_date.isoformat(),
                "customer_id": review.customer_id,
                "ad_account_meta_id": review.ad_account_meta_id,
                "currency": review.currency,
                "campaigns": [],
                "total_observed": None,
                "total_sheet": None,
                "match_status": None,
                "delta_account_day": None,
                "baseline_confirmed": True,
                "campaign_set_complete": True,
            },
        )
        entry["campaigns"].append(
            {
                "campaign_meta_id": review.campaign_meta_id,
                "campaign_name": review.campaign_name,
                "observed_spend": str(review.observed_spend) if review.observed_spend is not None else None,
                "review_kind": review.review_kind,
                # per-campaign KHÔNG phán MATCH/DIFF (baseline là account+ngày)
                "match_status": REVIEW_VISUAL_ONLY if review.review_kind == REVIEW_VISUAL else REVIEW_RECORDED,
                "last_observed_at": review.last_observed_at.isoformat() if review.last_observed_at else None,
            }
        )
        entry["baseline_confirmed"] = entry["baseline_confirmed"] and bool(review.sheet_baseline_confirmed)
        entry["campaign_set_complete"] = entry["campaign_set_complete"] and bool(review.campaign_set_complete)
        if review.review_kind == REVIEW_VISUAL:
            if entry["match_status"] is None:
                entry["match_status"] = REVIEW_VISUAL_ONLY
            continue
        if review.observed_spend is not None:
            entry["total_observed"] = float(entry.get("total_observed") or 0) + float(review.observed_spend)

    for (day, account, currency, cust_id), entry in grouped.items():
        if entry["total_observed"] is None:
            continue  # chỉ VISUAL — không có số
        verdict, total, baseline, delta = _recompute_group_verdict(
            db, cust_id, date.fromisoformat(day), account, currency
        )
        entry["match_status"] = verdict or REVIEW_RECORDED
        entry["total_observed"] = float(total) if total is not None else entry["total_observed"]
        entry["total_sheet"] = float(baseline) if baseline is not None else None
        entry["delta_account_day"] = float(delta) if delta is not None else None
    return list(grouped.values())


def list_reviews(
    db: Session,
    customer_id: Optional[int] = None,
    business_date: Optional[date] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    query = select(ManualReview).order_by(ManualReview.created_at.desc()).limit(limit)
    if customer_id is not None:
        query = query.where(ManualReview.customer_id == customer_id)
    if business_date is not None:
        query = query.where(ManualReview.business_date == business_date)
    reviews = db.execute(query).scalars().all()
    customer_map = {c.id: c.name for c in db.execute(select(Customer)).scalars().all()}
    result = []
    for r in reviews:
        result.append(
            {
                "id": r.id,
                "customer_id": r.customer_id,
                "customer_name": customer_map.get(r.customer_id),
                "business_date": r.business_date.isoformat(),
                "ad_account_meta_id": r.ad_account_meta_id,
                "campaign_meta_id": r.campaign_meta_id,
                "campaign_name": r.campaign_name,
                "observed_spend": str(r.observed_spend) if r.observed_spend is not None else None,
                "sheet_spend": str(r.sheet_spend) if r.sheet_spend is not None else None,
                "delta": str(r.delta) if r.delta is not None else None,
                "currency": r.currency,
                "review_kind": r.review_kind,
                "match_status": r.match_status,
                "sheet_baseline_confirmed": bool(r.sheet_baseline_confirmed),
                "campaign_set_complete": bool(r.campaign_set_complete),
                "last_observed_at": r.last_observed_at.isoformat() if r.last_observed_at else None,
                "sheet_name": r.sheet_name,
                "note": r.note,
                "reviewed_by": r.reviewed_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "observations": list_observations(db, r.id, limit=10),
            }
        )
    return result


def campaigns_for_customer(db: Session, customer_id: int) -> list[dict[str, Any]]:
    """Danh sách campaign liên quan khách (kể cả account REPLACED) cho form review."""
    rows = db.execute(
        select(Campaign).where(Campaign.customer_id == customer_id).order_by(Campaign.id.desc())
    ).scalars().all()
    return [
        {
            "meta_campaign_id": c.meta_campaign_id,
            "name": c.name,
            "recognition_status": c.recognition_status,
            "report_period_end": c.report_period_end.isoformat() if c.report_period_end else None,
        }
        for c in rows
    ]
