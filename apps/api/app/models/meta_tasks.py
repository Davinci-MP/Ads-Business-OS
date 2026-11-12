"""Model lưu lịch sử tác vụ tạo chiến dịch Meta Ads có kiểm soát (Controlled Write Path)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime


class MetaCampaignTask(Base):
    """Lịch sử tác vụ tạo chiến dịch Meta Ads qua Bot/Pipeline có kiểm soát (audit & tracking)."""

    __tablename__ = "meta_campaign_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    ad_account_id: Mapped[str] = mapped_column(String(64), index=True)
    campaign_name: Mapped[str] = mapped_column(String(255))
    objective: Mapped[str] = mapped_column(String(64))
    daily_budget: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    meta_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    meta_adset_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    meta_ad_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="telegram_bot")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
