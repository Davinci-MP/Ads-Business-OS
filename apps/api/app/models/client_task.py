"""Model quản lý tác vụ khách hàng tự động phân loại từ Telegram bot / webhooks."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.customer import Customer, utcnow
from app.models.types import UTCDateTime

TASK_TYPE_ADD_MAIL_TO_BM = "ADD_MAIL_TO_BM"
TASK_TYPE_ADD_AD_ACCOUNT = "ADD_AD_ACCOUNT"
TASK_TYPE_SETTLE_DEBT = "SETTLE_DEBT"
TASK_TYPE_TOPUP_BUDGET = "TOPUP_BUDGET"
TASK_TYPE_CHECK_BALANCE = "CHECK_BALANCE"
TASK_TYPE_GENERAL_SUPPORT = "GENERAL_SUPPORT"

TASK_STATUS_PENDING = "PENDING"
TASK_STATUS_IN_PROGRESS = "IN_PROGRESS"
TASK_STATUS_COMPLETED = "COMPLETED"
TASK_STATUS_CANCELLED = "CANCELLED"

PRIORITY_LOW = "LOW"
PRIORITY_NORMAL = "NORMAL"
PRIORITY_HIGH = "HIGH"
PRIORITY_URGENT = "URGENT"


class ClientTask(Base):
    """Tác vụ yêu cầu từ khách hàng qua Telegram, được phân loại tự động bằng AI/Regex."""

    __tablename__ = "client_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    telegram_chat_id: Mapped[str] = mapped_column(String(64), index=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sender_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    raw_message: Mapped[str] = mapped_column(Text)
    extracted_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=TASK_STATUS_PENDING, index=True)
    priority: Mapped[str] = mapped_column(String(16), default=PRIORITY_NORMAL)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    customer: Mapped[Optional[Customer]] = relationship("Customer")
