from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime

ACCOUNT_ACTIVE = "ACTIVE"
ACCOUNT_RESTRICTED = "RESTRICTED"
ACCOUNT_REPLACED = "REPLACED"
ACCOUNT_DEAD = "DEAD"


class AdAccount(Base):
    __tablename__ = "ad_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    meta_ad_account_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    business_manager_id: Mapped[Optional[str]] = mapped_column(String(64))
    timezone_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default=ACCOUNT_ACTIVE)
    purchase_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    opened_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    restricted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    replaced_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ad_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    replaced_by = relationship("AdAccount", remote_side="AdAccount.id")


class AdAccountAssignment(Base):
    __tablename__ = "ad_account_assignments"
    __table_args__ = (
        UniqueConstraint("customer_id", "ad_account_id", "valid_from", name="uq_assignment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    ad_account_id: Mapped[int] = mapped_column(ForeignKey("ad_accounts.id"))
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime())
    valid_to: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
