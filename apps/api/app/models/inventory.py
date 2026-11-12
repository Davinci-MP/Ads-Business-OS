"""Model quản lý kho tài nguyên VIA, Business Manager (BM), Fanpage, Proxy có mã hóa."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.customer import Customer, utcnow
from app.models.types import UTCDateTime

ITEM_TYPE_VIA = "VIA"
ITEM_TYPE_BM = "BM"
ITEM_TYPE_PAGE = "PAGE"
ITEM_TYPE_PROXY = "PROXY"

STATUS_AVAILABLE = "AVAILABLE"
STATUS_ASSIGNED = "ASSIGNED"
STATUS_DEAD = "DEAD"


class InventoryItem(Base):
    """Tài nguyên tài khoản quảng cáo (VIA, BM, Fanpage, Proxy). Thông tin đăng nhập được mã hóa Fernet."""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    encrypted_credentials: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default=STATUS_AVAILABLE, index=True)
    assigned_customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    assigned_ad_account_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    customer: Mapped[Optional[Customer]] = relationship("Customer")
