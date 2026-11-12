"""Sổ ngân sách riêng theo khách và tiền tệ; phát sinh bất biến sau thực thi."""
from decimal import Decimal
from typing import Optional
from datetime import datetime
from sqlalchemy import ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime


class ClientBalance(Base):
    __tablename__ = "client_balances"
    __table_args__ = (UniqueConstraint("customer_id", "currency", name="uq_client_balance_currency"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    currency: Mapped[str] = mapped_column(String(8))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    low_threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    deposit_info: Mapped[Optional[str]] = mapped_column(Text)
    low_alert_active: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    currency: Mapped[str] = mapped_column(String(8))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    kind: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    source_ledger_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ledger_entries.id"), unique=True)
    evidence: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="CREATED")
    requested_by: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    executed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
