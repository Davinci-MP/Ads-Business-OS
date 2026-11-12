"""Mô hình dữ liệu Thẻ ảo VCC PingPong và Giao dịch thẻ phục vụ Quản trị Rủi ro & Đối soát."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime


class VccCard(Base):
    """Bảng lưu trữ thông tin thẻ ảo VCC PingPong Issuing (an toàn, mask PAN, chỉ giữ last4)."""

    __tablename__ = "vcc_cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    card_number_masked: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_four: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(16), default="USD")
    allocated_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0"))
    available_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0"))
    low_balance_threshold: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("5.0"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    transactions: Mapped[list[VccTransaction]] = relationship(
        "VccTransaction", back_populates="card", cascade="all, delete-orphan"
    )


class VccTransaction(Base):
    """Bảng lưu trữ lịch sử giao dịch/uỷ quyền (Authorization / Clearing) thẻ VCC PingPong."""

    __tablename__ = "vcc_transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    card_id: Mapped[str] = mapped_column(
        ForeignKey("vcc_cards.id", ondelete="CASCADE"), index=True, nullable=False
    )
    auth_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0"))
    settle_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0"))
    currency: Mapped[str] = mapped_column(String(16), default="USD")
    merchant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="SETTLED")
    transaction_time: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    card: Mapped[VccCard] = relationship("VccCard", back_populates="transactions")
