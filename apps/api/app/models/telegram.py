"""Database models cho Telegram Bot Configuration, Automation Rules và Activity Logs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime


class TelegramBotConfig(Base):
    """Cấu hình động cho Telegram Bot Agent (hỗ trợ lưu và quản lý qua UI Dashboard)."""

    __tablename__ = "telegram_bot_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    encrypted_bot_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    encrypted_webhook_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    allowed_chat_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class AutomationRule(Base):
    """Quy tắc tự động hoá (tự động tắt campaign khi vượt ngân sách, cảnh báo thẻ VCC, báo cáo định kỳ)."""

    __tablename__ = "automation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    rule_type: Mapped[str] = mapped_column(String(64))  # AUTO_PAUSE_SPEND_LIMIT, ALERT_LOW_VCC_BALANCE, DAILY_REPORT_SCHEDULE, ALERT_HIGH_DRIFT_SPEND
    threshold: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(16), default="VND")
    target_entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), default="TELEGRAM_ALERT")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    trigger_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class TelegramActivityLog(Base):
    """Nhật ký lệnh và phản hồi của Telegram Bot Agent."""

    __tablename__ = "telegram_activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    update_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    chat_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    command: Mapped[str] = mapped_column(String(255))
    response_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="SUCCESS")  # SUCCESS, REJECTED, ERROR
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
