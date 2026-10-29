from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime


class SheetReportSource(Base):
    __tablename__ = "sheet_report_sources"
    __table_args__ = (
        UniqueConstraint("period", "spreadsheet_id", name="uq_sheet_source_period_workbook"),
        Index("uq_sheet_active_period", "period", unique=True,
              sqlite_where=text("active = 1"), postgresql_where=text("active")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    spreadsheet_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mapping_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class SheetReportSettings(Base):
    __tablename__ = "sheet_report_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    default_source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sheet_report_sources.id"))


class SheetReportSnapshot(Base):
    __tablename__ = "sheet_report_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sheet_report_sources.id"), index=True, nullable=False)
    read_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mapping_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    quality: Mapped[str] = mapped_column(String(32), nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class SheetReportSyncAttempt(Base):
    __tablename__ = "sheet_report_sync_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sheet_report_sources.id"), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    snapshot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sheet_report_snapshots.id"))
    error: Mapped[Optional[str]] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(String(24), nullable=False)


class SheetReportClosure(Base):
    __tablename__ = "sheet_report_closures"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sheet_report_sources.id"), unique=True, nullable=False)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("sheet_report_snapshots.id"), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    actor: Mapped[Optional[str]] = mapped_column(String(255))


class SheetReportTabDismissal(Base):
    """Tab người vận hành xác nhận không phải khách; không xóa dữ liệu nguồn."""
    __tablename__ = "sheet_report_tab_dismissals"
    __table_args__ = (
        Index("uq_sheet_tab_dismissal", "source_id", "sheet_id", unique=True,
              sqlite_where=text("active = 1"), postgresql_where=text("active")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sheet_report_sources.id"), nullable=False)
    sheet_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    actor: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class SheetReportCustomerLink(Base):
    __tablename__ = "sheet_report_customer_links"
    __table_args__ = (
        Index("uq_sheet_source_customer_tab", "source_id", "sheet_id", unique=True,
              sqlite_where=text("active = 1"), postgresql_where=text("active")),
        Index("uq_sheet_source_customer", "source_id", "customer_id", unique=True,
              sqlite_where=text("active = 1"), postgresql_where=text("active")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sheet_report_sources.id"), nullable=False)
    sheet_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
