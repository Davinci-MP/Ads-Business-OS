from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime

RECON_SIMPLE_FEE = "SIMPLE_FEE"
RECON_PROFIT_SHARE = "PROFIT_SHARE"

DEFAULT_FEE_RATE = Decimal("0.04")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64))
    fee_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=DEFAULT_FEE_RATE)
    recon_mode: Mapped[str] = mapped_column(String(32), default=RECON_SIMPLE_FEE)
    profit_share_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    budget_alert_threshold_vnd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
