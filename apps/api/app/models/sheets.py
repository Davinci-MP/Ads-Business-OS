from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime

MAPPING_PROPOSED = "PROPOSED"
MAPPING_CONFIRMED = "CONFIRMED"


class SheetMapping(Base):
    """Mapping cấu trúc Google Sheets (S6, D-024/D-028): sheet/cột → vai trò đối soát.

    Chỉ là cấu hình nội bộ trong DB — KHÔNG đụng bảng Sheets thật.
    Trạng thái: `PROPOSED` (do module phân tích đề xuất) → `CONFIRMED` (chủ dự án xác nhận).
    Cấu trúc thật của bảng đang vận hành vẫn chờ xác nhận (Q-007).
    Unique key chống ghi trùng: `(spreadsheet_key, sheet_name, column_index)`.
    """

    __tablename__ = "sheet_mappings"
    __table_args__ = (
        UniqueConstraint("spreadsheet_key", "sheet_name", "column_index", name="uq_sheet_mapping_column"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    spreadsheet_key: Mapped[str] = mapped_column(String(128))
    sheet_name: Mapped[str] = mapped_column(String(128))
    column_index: Mapped[int] = mapped_column()
    column_letter: Mapped[Optional[str]] = mapped_column(String(4))
    header: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[Optional[str]] = mapped_column(String(32))
    field: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=MAPPING_PROPOSED)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
