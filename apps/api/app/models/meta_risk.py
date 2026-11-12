from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime


class MetaAccountRisk(Base):
    __tablename__ = "meta_account_risks"

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_status: Mapped[Optional[int]]
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    debt: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 6))
    debt_threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 6))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_code: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    data_status: Mapped[str] = mapped_column(String(16), default="UNVERIFIED")
    checked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_error: Mapped[Optional[str]] = mapped_column(Text)
