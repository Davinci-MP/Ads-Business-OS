from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime

RECOGNITION_UNRECOGNIZED = "UNRECOGNIZED"
RECOGNITION_CONFIRMED = "CONFIRMED"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    meta_campaign_id: Mapped[str] = mapped_column(String(64), unique=True)
    ad_account_id: Mapped[int] = mapped_column(ForeignKey("ad_accounts.id"))
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"))
    name: Mapped[str] = mapped_column(String(500))
    recognition_status: Mapped[str] = mapped_column(String(32), default=RECOGNITION_UNRECOGNIZED)
    report_period_start: Mapped[Optional[date]] = mapped_column(Date)
    report_period_end: Mapped[Optional[date]] = mapped_column(Date)
    meta_status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    stopped_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
