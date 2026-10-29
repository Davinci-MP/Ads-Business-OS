"""REST endpoints đối chiếu thủ công (S17/S17.1 — D-041/D-042, KHÔNG cần Meta token)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import reviews

router = APIRouter(prefix="/manual-reviews", tags=["manual-reviews"])


class ReviewCreate(BaseModel):
    customer_id: int
    business_date: str  # YYYY-MM-DD
    ad_account_meta_id: str
    review_kind: str = reviews.REVIEW_MANUAL  # MANUAL_REVIEWED | VISUALLY_REVIEWED
    campaign_meta_id: Optional[str] = None
    campaign_name: Optional[str] = None
    observed_spend: Optional[str] = None
    sheet_spend: Optional[str] = None  # baseline account+ngày (một lần, không cộng theo campaign)
    currency: str = "USD"
    sheet_key: Optional[str] = None
    sheet_name: Optional[str] = None
    note: Optional[str] = None
    reviewed_by: str = "owner"
    observed_at: Optional[str] = None  # ISO — thời điểm quan sát thực tế (không phải lúc ghi)
    idempotency_key: Optional[str] = None  # retry cùng key → trả kết quả cũ
    sheet_baseline_confirmed: bool = False  # baseline từ mapping CONFIRMED?
    campaign_set_complete: bool = False  # đã kiểm tra đủ tập campaign account/ngày?
    account_conflict: bool = False  # xung đột phân bổ tài khoản (D-039)


def _parse(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} không hợp lệ (YYYY-MM-DD)") from exc


@router.post("")
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    observed_dt: Optional[datetime] = None
    if payload.observed_at:
        try:
            observed_dt = datetime.fromisoformat(payload.observed_at.replace("Z", "+00:00"))
            if observed_dt.tzinfo is None:
                observed_dt = observed_dt.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="observed_at không hợp lệ (ISO 8601)") from exc
    try:
        review = reviews.create_review(
            db,
            customer_id=payload.customer_id,
            business_date=_parse(payload.business_date, "business_date"),
            ad_account_meta_id=payload.ad_account_meta_id,
            review_kind=payload.review_kind,
            campaign_meta_id=payload.campaign_meta_id,
            campaign_name=payload.campaign_name,
            observed_spend=payload.observed_spend,
            sheet_spend=payload.sheet_spend,
            currency=payload.currency,
            sheet_key=payload.sheet_key,
            sheet_name=payload.sheet_name,
            note=payload.note,
            reviewed_by=payload.reviewed_by,
            observed_at=observed_dt,
            idempotency_key=payload.idempotency_key,
            sheet_baseline_confirmed=payload.sheet_baseline_confirmed,
            campaign_set_complete=payload.campaign_set_complete,
            account_conflict=payload.account_conflict,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": review.id,
        "review_kind": review.review_kind,
        "match_status": review.match_status,
        "delta": str(review.delta) if review.delta is not None else None,
        "currency": review.currency,
        "last_observed_at": review.last_observed_at.isoformat() if review.last_observed_at else None,
        "note": review.note,
    }


@router.get("")
def list_reviews(
    customer_id: Optional[int] = Query(None),
    business_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return reviews.list_reviews(
        db, customer_id=customer_id, business_date=_parse(business_date, "business_date") if business_date else None
    )


@router.get("/summary")
def reviews_summary(
    customer_id: Optional[int] = Query(None),
    business_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    day = _parse(business_date, "business_date") if business_date else None
    return reviews.summarize_by_account_day(db, customer_id=customer_id, business_date=day)


@router.get("/{review_id}/observations")
def review_observations(review_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Lịch sử quan sát append-only của 1 review (mới trước)."""
    return reviews.list_observations(db, review_id)


@router.get("/campaigns/{customer_id}")
def campaigns_for_review(customer_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return reviews.campaigns_for_customer(db, customer_id)
