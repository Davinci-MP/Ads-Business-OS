from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime

DATA_VERIFIED = "VERIFIED"
DATA_UNVERIFIED = "UNVERIFIED"
DATA_API_ERROR = "API_ERROR"

SOURCE_META_API = "META_API"


class SpendSnapshot(Base):
    __tablename__ = "spend_snapshots"
    __table_args__ = (UniqueConstraint("campaign_id", "snapshot_at", name="uq_snapshot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    snapshot_at: Mapped[datetime] = mapped_column(UTCDateTime())
    spend_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    source: Mapped[str] = mapped_column(String(64), default=SOURCE_META_API)
    is_checkpoint_9h: Mapped[bool] = mapped_column(Boolean, default=False)
    data_status: Mapped[str] = mapped_column(String(32), default=DATA_VERIFIED)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class DriftRecord(Base):
    __tablename__ = "drift_records"
    __table_args__ = (
        UniqueConstraint("campaign_id", "checkpoint_snapshot_id", name="uq_drift"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    checkpoint_snapshot_id: Mapped[int] = mapped_column(ForeignKey("spend_snapshots.id"))
    latest_snapshot_id: Mapped[int] = mapped_column(ForeignKey("spend_snapshots.id"))
    drift_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
