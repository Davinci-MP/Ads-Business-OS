"""Model manual_reviews + manual_review_observations (S17 / S17.1, D-041 / D-042).

Bất biến:
- MANUAL_REVIEWED (nhập Campaign ID + số quan sát) / VISUALLY_REVIEWED (không số).
- KHÔNG BAO GIỜ tự coi quan sát tay là META_API_VERIFIED.
- `manual_reviews` = trạng thái HIỆN HÀNH theo unique
  (customer, business_date, ad_account, campaign, review_kind) — chống ghi trùng.
- `manual_review_observations` = lịch sử APPEND-ONLY từng lần quan sát (D-042):
  mỗi lần kiểm tra hợp lệ tạo 1 dòng, có observed_at (thời điểm quan sát thực)
  + recorded_at + idempotency_key UNIQUE (retry cùng key trả kết quả cũ).
- MATCH/DIFF kết luận ở mức Customer + Account + Business Date + Currency
  (tổng tích lũy các campaign cộng với baseline Sheets 1 lần) — không phán per-campaign.
- Quan sát đến muộn (observed_at nhỏ hơn hiện hành) vẫn lưu lịch sử, KHÔNG ghi đè hiện hành.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime

REVIEW_MANUAL = "MANUAL_REVIEWED"
REVIEW_VISUAL = "VISUALLY_REVIEWED"

REVIEW_MATCH = "MATCHED"
REVIEW_DIFF = "DIFF"
REVIEW_VISUAL_ONLY = "VISUAL_ONLY"
REVIEW_NEEDS_SHEET = "NEEDS_SHEET_BASELINE"
# D-042: verdict levels khi thiếu điều kiện kết luận
REVIEW_INCOMPLETE = "INCOMPLETE"  # chưa xác nhận đủ tập campaign cần tính
REVIEW_NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"  # mapping chưa CONFIRMED / xung đột / thiếu tỷ giá
REVIEW_RECORDED = "RECORDED"  # đã ghi nhận, chưa đủ điều kiện phán (per-campaign)


class ManualReview(Base):
    __tablename__ = "manual_reviews"
    __table_args__ = (
        UniqueConstraint(
            "customer_id", "business_date", "ad_account_meta_id", "campaign_meta_id", "review_kind",
            name="uq_manual_review",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    business_date: Mapped[date] = mapped_column(Date)
    ad_account_meta_id: Mapped[str] = mapped_column(String(64))
    campaign_meta_id: Mapped[Optional[str]] = mapped_column(String(64))
    campaign_name: Mapped[Optional[str]] = mapped_column(Text)
    observed_spend: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    sheet_spend: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    delta: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    review_kind: Mapped[str] = mapped_column(String(32), default=REVIEW_MANUAL)
    match_status: Mapped[str] = mapped_column(String(32), default=REVIEW_VISUAL_ONLY)
    sheet_key: Mapped[Optional[str]] = mapped_column(String(128))
    sheet_name: Mapped[Optional[str]] = mapped_column(String(128))
    note: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by: Mapped[str] = mapped_column(String(64), default="owner")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    # S17.1 (D-042)
    last_observed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    sheet_baseline_confirmed: Mapped[bool] = mapped_column(default=False)
    campaign_set_complete: Mapped[bool] = mapped_column(default=False)


class ManualReviewObservation(Base):
    """Lịch sử quan sát — APPEND-ONLY, không update/xoá dòng đã ghi (D-042)."""

    __tablename__ = "manual_review_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("manual_reviews.id"))
    observed_spend: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))  # None = VISUAL
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    sheet_baseline: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))  # baseline account+ngày
    delta_account_day: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    match_status: Mapped[str] = mapped_column(String(32), default=REVIEW_RECORDED)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime())  # thời điểm quan sát thực tế
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    reviewed_by: Mapped[str] = mapped_column(String(64), default="owner")
    note: Mapped[Optional[str]] = mapped_column(Text)
