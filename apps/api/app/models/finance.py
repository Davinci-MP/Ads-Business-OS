from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import JSON, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime

ENTRY_ACTUAL_SPEND = "ACTUAL_SPEND"
ENTRY_SERVICE_FEE = "SERVICE_FEE"
ENTRY_CONTRACT_RECON = "CONTRACT_RECON"
ENTRY_ACCOUNT_FEE = "ACCOUNT_FEE"
ENTRY_CARD_FEE = "CARD_FEE"
ENTRY_MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
ENTRY_PROFIT_SPLIT = "PROFIT_SPLIT"

ENTRY_TEMP = "TEMP"
ENTRY_FINAL = "FINAL"

ADJ_DRAFT = "DRAFT"
ADJ_APPROVED = "APPROVED"
ADJ_REJECTED = "REJECTED"
ADJ_APPLIED = "APPLIED"

USDT_UNMATCHED = "UNMATCHED"
USDT_MATCHED = "MATCHED"

USDT_NETWORK_TRON_MAINNET = "tron_mainnet"
USDT_BALANCE_MANUAL = "MANUAL"
USDT_BALANCE_AUTO = "AUTO"

OUTBOX_PENDING = "PENDING"
OUTBOX_SENT = "SENT"
OUTBOX_FAILED = "FAILED"


class TelegramOutbox(Base):
    """Hàng đợi thông báo Telegram (D-031): lỗi gửi → ghi PENDING để gửi lại ở lần chạy sau."""
    __tablename__ = "telegram_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=OUTBOX_PENDING)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint("customer_id", "entry_kind", "period_start", "version", name="uq_ledger_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    entry_kind: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(default=1)
    state: Mapped[str] = mapped_column(String(16), default=ENTRY_TEMP)
    ref_type: Mapped[Optional[str]] = mapped_column(String(64))
    ref_id: Mapped[Optional[str]] = mapped_column(String(64))
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ManualAdjustment(Base):
    __tablename__ = "manual_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    note: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default=ADJ_DRAFT)
    created_by: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    approved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())


class UsdtTransaction(Base):
    __tablename__ = "usdt_transactions"
    __table_args__ = (UniqueConstraint("tx_hash", name="uq_usdt_tx_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tx_hash: Mapped[str] = mapped_column(String(255), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    currency: Mapped[str] = mapped_column(String(8), default="USDT")
    wallet_address: Mapped[str] = mapped_column(String(128))
    confirmations: Mapped[Optional[int]] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    match_status: Mapped[str] = mapped_column(String(16), default=USDT_UNMATCHED)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"))
    matched_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class UsdtWallet(Base):
    """Cấu hình ví USDT TRC20 được theo dõi — chỉ một địa chỉ công khai, chỉ đọc on-chain.

    Không lưu private key/seed; địa chỉ đã lưu là bất biến (không ghi đè ví khác —
    đổi địa chỉ phải gỡ theo dõi rõ ràng, không tự xoá lịch sử).
    """
    __tablename__ = "usdt_wallets"
    __table_args__ = (
        UniqueConstraint("wallet_address", name="uq_usdt_wallet_address"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_name: Mapped[str] = mapped_column(String(255))
    wallet_address: Mapped[str] = mapped_column(String(128), unique=True)
    network: Mapped[str] = mapped_column(String(32), default=USDT_NETWORK_TRON_MAINNET)
    contract: Mapped[str] = mapped_column(String(64))
    auto_sync: Mapped[bool] = mapped_column(default=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_ok_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class UsdtWalletBalance(Base):
    """Lịch sử số dư ví (append-only): mỗi lần đọc thành công = 1 dòng; lỗi không ghi dòng False."""
    __tablename__ = "usdt_wallet_balances"
    __table_args__ = (
        UniqueConstraint("wallet_id", "read_at", "source", name="uq_usdt_wallet_balance_read"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("usdt_wallets.id"))
    wallet_address: Mapped[str] = mapped_column(String(128))
    balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 6))
    note: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))
    read_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(8))
    quote_currency: Mapped[str] = mapped_column(String(8))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime())
    source: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    requested_by: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    approved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
