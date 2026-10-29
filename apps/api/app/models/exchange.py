"""Kết nối sàn giao dịch (D-056) — chỉ đọc số dư USDT Spot/Funding.

- `exchange_connections`: cấu hình 1 connection cho 1 provider (Binance/OKX/MEXC);
  ngắt kết nối chỉ đổi status (REMOVED) — KHÔNG xoá lịch sử snapshot/history.
- `exchange_credentials`: API key/secret CHỈ lưu dạng mã hóa (Fernet) — không plaintext;
  mỗi connection tối đa 1 dòng (unique connection_id).
- `exchange_balance_snapshots`: snapshot append-only, unique (connection_id, wallet_type,
  asset, read_at) — chống ghi trùng khi job chạy lại cùng thời điểm.
- `exchange_sync_history`: mỗi lần đồng bộ 1 dòng (OK/PARTIAL/ERROR), detail không chứa secret.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime

EXCH_PROVIDER_BINANCE = "binance"
EXCH_PROVIDER_OKX = "okx"
EXCH_PROVIDER_MEXC = "mexc"

EXCH_STATUS_ACTIVE = "ACTIVE"
EXCH_STATUS_REMOVED = "REMOVED"

EXCH_WALLET_SPOT = "spot"
EXCH_WALLET_FUNDING = "funding"

EXCH_SOURCE_MANUAL = "MANUAL"
EXCH_SOURCE_AUTO = "AUTO"

EXCH_HISTORY_STARTED = "STARTED"
EXCH_HISTORY_OK = "OK"
EXCH_HISTORY_PARTIAL = "PARTIAL"
EXCH_HISTORY_ERROR = "ERROR"


class ExchangeConnection(Base):
    __tablename__ = "exchange_connections"
    __table_args__ = (
        UniqueConstraint("provider", "label", name="uq_exchange_connection_label"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=EXCH_STATUS_ACTIVE)
    wallet_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    read_only_verified: Mapped[bool] = mapped_column(default=False)
    auto_sync: Mapped[bool] = mapped_column(default=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_ok_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class ExchangeCredentials(Base):
    __tablename__ = "exchange_credentials"
    __table_args__ = (
        UniqueConstraint("connection_id", name="uq_exchange_credentials_connection"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("exchange_connections.id"), unique=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    encrypted_api_secret: Mapped[str] = mapped_column(Text)
    api_key_last4: Mapped[str] = mapped_column(String(8), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class ExchangeBalanceSnapshot(Base):
    __tablename__ = "exchange_balance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "wallet_type", "asset", "read_at",
            name="uq_exchange_snapshot_read",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("exchange_connections.id"))
    wallet_type: Mapped[str] = mapped_column(String(16))
    asset: Mapped[str] = mapped_column(String(16))
    free: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 8))
    locked: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 8))
    freeze: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 8))
    withdrawing: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 8))
    source: Mapped[str] = mapped_column(String(16))
    read_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ExchangeSyncHistory(Base):
    __tablename__ = "exchange_sync_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("exchange_connections.id"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    completed: Mapped[Optional[bool]] = mapped_column()
    status: Mapped[str] = mapped_column(String(16), default=EXCH_HISTORY_STARTED)
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
