from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
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
    telegram_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    fee_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=DEFAULT_FEE_RATE)
    recon_mode: Mapped[str] = mapped_column(String(32), default=RECON_SIMPLE_FEE)
    profit_share_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sheet_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    sheet_tab_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sync_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True, index=True)
    budget_alert_threshold_vnd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    portal_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class CustomerSheetSyncRun(Base):
    __tablename__ = "customer_sheet_sync_runs"
    __table_args__ = (
        UniqueConstraint("customer_id", "scheduled_for", name="uq_customer_sheet_sync_run"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    report_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    rows_json: Mapped[Optional[list]] = mapped_column(JSON)
    backup_json: Mapped[Optional[list]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    executed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
