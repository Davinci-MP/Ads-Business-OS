"""Model lưu cấu hình ưu tiên phân quyền Business Manager (BM) cho từng khách hàng."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.customer import Customer, utcnow
from app.models.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.via import ViaProfile

BM_ROLE_EMPLOYEE = "EMPLOYEE"
BM_ROLE_ADMIN = "ADMIN"

ACCESS_TYPE_FULL = "FULL"
ACCESS_TYPE_PARTIAL = "PARTIAL"

DEFAULT_PARTIAL_PERMISSIONS = ["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE", "CREATIVE_HUB"]


class ClientBMPreference(Base):
    """Cấu hình ghi nhớ phân quyền và định tuyến BM tự động theo từng khách hàng."""

    __tablename__ = "client_bm_preferences"
    __table_args__ = (UniqueConstraint("client_id", name="uq_client_bm_preference_client"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, unique=True, index=True)
    preferred_bm_id: Mapped[str] = mapped_column(String(64), default="BM_01")
    via_profile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("via_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    bm_role: Mapped[str] = mapped_column(String(32), default=BM_ROLE_EMPLOYEE)
    ad_account_access_type: Mapped[str] = mapped_column(String(32), default=ACCESS_TYPE_FULL)
    partial_permissions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    customer: Mapped[Customer] = relationship("Customer", foreign_keys=[client_id])
    via_profile: Mapped[Optional[ViaProfile]] = relationship("ViaProfile", foreign_keys=[via_profile_id])

    @property
    def customer_id(self) -> int:
        return self.client_id

    @customer_id.setter
    def customer_id(self, val: int) -> None:
        self.client_id = val

    def get_permissions_list(self) -> list[str]:
        if not self.partial_permissions:
            return list(DEFAULT_PARTIAL_PERMISSIONS)
        try:
            val = json.loads(self.partial_permissions)
            return list(val) if isinstance(val, list) else list(DEFAULT_PARTIAL_PERMISSIONS)
        except Exception:
            return list(DEFAULT_PARTIAL_PERMISSIONS)

    def set_permissions_list(self, perms: list[str]) -> None:
        self.partial_permissions = json.dumps(perms, ensure_ascii=False)
