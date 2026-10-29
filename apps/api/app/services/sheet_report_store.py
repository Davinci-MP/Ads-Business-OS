"""Persistence for read-only Sheets reports, independent of financial ledgers."""
from __future__ import annotations

import hashlib
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.connectors.sheets import GoogleSheetsConnector, SheetsAPIError, SheetsAuthError
from app.models.sheet_reports import (
    SheetReportClosure, SheetReportCustomerLink, SheetReportSnapshot,
    SheetReportSource, SheetReportSyncAttempt,
)
from app.services.sheets_compare import tolerance_for_currency
from app.services.sheets_report import build_sheets_source_report

MAPPING_VERSION = "D-047-v1"
MAPPING_CONFIG = {
    "opening_balance": "J1", "budget_deposits_vnd": "K1", "spend_vnd": "F1",
    "fee": "G1", "billing_total": "H1", "current_balance": "L1",
    "profit_convention": "G1", "usdt_receipts": "J4:J",
}
CONFIRMED_MAPPING_VERSION = "D-049-v2"
CONFIRMED_MAPPING_CONFIG = {
    **MAPPING_CONFIG,
    "blank_usdt_header_tabs": ["JACK", "VKL", "SONA", "VIKTOR"],
    "inactive_tabs_by_period": {"2026-10": ["VKL", "SONA", "VIKTOR"]},
}
SEPARATOR_MAPPING_VERSION = "D-050-v3"
SEPARATOR_MAPPING_CONFIG = {
    **CONFIRMED_MAPPING_CONFIG,
    "separator_rows_by_period": {"2026-10": {"JACK": [6, 9], "VIKTOR": [6]}},
}
MAX_READ_SECONDS = 240


class SyncBusy(Exception):
    pass


@contextmanager
def source_lock(session: Session, source_id: int) -> Iterator[None]:
    """A connection/OS lock survives multiple workers and is released on process death."""
    engine = session.get_bind()
    dialect = engine.dialect.name
    if dialect == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(f"adsos-sheets:{source_id}".encode()).digest()[:8], "big", signed=True)
        with engine.connect() as conn:
            acquired = conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id}).scalar_one()
            if not acquired:
                raise SyncBusy()
            try:
                yield
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})
        return
    if dialect != "sqlite":
        raise RuntimeError(f"Không hỗ trợ khóa đồng bộ cho database {dialect}")
    database = engine.url.database
    if not database or database == ":memory:":
        raise RuntimeError("Khóa đồng bộ SQLite yêu cầu database trên đĩa")
    path = Path(database).resolve().with_name(f"{Path(database).name}.sheets-{source_id}.lock")
    with path.open("a+b") as lock_file:
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise SyncBusy() from exc
        else:
            import fcntl
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SyncBusy() from exc
        try:
            yield
        finally:
            lock_file.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def latest_snapshot(session: Session, source_id: int) -> SheetReportSnapshot | None:
    return session.scalar(
        select(SheetReportSnapshot).where(SheetReportSnapshot.source_id == source_id)
        .order_by(SheetReportSnapshot.id.desc()).limit(1)
    )


def read_source_report(spreadsheet_id: str, connector_factory=None, source_period=None, mapping_config=None) -> dict:
    deadline = time.monotonic() + MAX_READ_SECONDS
    factory = connector_factory or (
        lambda: GoogleSheetsConnector(spreadsheet_id=spreadsheet_id, use_mock=False, deadline=deadline)
    )
    for retry in range(2):
        try:
            report = build_sheets_source_report(
                factory(), source_period=source_period, mapping_config=mapping_config,
            )
            break
        except SheetsAuthError:
            raise
        except SheetsAPIError:
            if retry or time.monotonic() >= deadline:
                raise
    if time.monotonic() >= deadline:
        raise SheetsAPIError("Đã hết thời gian đọc báo cáo Sheets")
    if not any(c.get("profile_status") not in ("SOURCE_ERROR", "STRUCTURE_ERROR")
               for c in report["customers"]):
        raise SheetsAPIError("Không đọc được tab khách có cấu trúc phù hợp; giữ bản lưu gần nhất.")
    return report


def sync_source(session: Session, source_id: int, trigger: str, connector_factory=None) -> SheetReportSyncAttempt:
    with source_lock(session, source_id):
        source = session.get(SheetReportSource, source_id)
        if source is None or not source.active:
            raise ValueError("Nguồn không tồn tại hoặc đã ngừng sử dụng")
        session.execute(
            update(SheetReportSyncAttempt)
            .where(SheetReportSyncAttempt.source_id == source_id, SheetReportSyncAttempt.status == "RUNNING")
            .values(status="INTERRUPTED", finished_at=_utcnow(), error="Lần trước bị gián đoạn khi backend dừng.")
        )
        attempt = SheetReportSyncAttempt(source_id=source_id, status="RUNNING", trigger=trigger)
        session.add(attempt)
        session.commit()
        try:
            supported = (
                source.mapping_version == MAPPING_VERSION and source.mapping_config == MAPPING_CONFIG
            ) or (
                source.mapping_version == CONFIRMED_MAPPING_VERSION
                and source.mapping_config == CONFIRMED_MAPPING_CONFIG
            ) or (
                source.mapping_version == SEPARATOR_MAPPING_VERSION
                and source.mapping_config == SEPARATOR_MAPPING_CONFIG
            )
            if not supported:
                raise SheetsAPIError("Phiên bản mapping không còn được hỗ trợ; giữ nguyên bản lưu và kiểm tra cấu trúc.")
            report = read_source_report(source.spreadsheet_id, connector_factory, source.period, source.mapping_config)
            read_at = datetime.fromisoformat(report["read_at"])
            snapshot = SheetReportSnapshot(
                source_id=source_id, read_at=read_at, mapping_version=source.mapping_version, mapping_config=source.mapping_config,
                quality=report["status"], report=report,
            )
            session.add(snapshot)
            session.flush()
            attempt.snapshot_id = snapshot.id
            attempt.status = report["status"]
        except SheetsAPIError as exc:
            session.rollback()
            attempt = session.get(SheetReportSyncAttempt, attempt.id)
            attempt.status = "ERROR"
            attempt.error = str(exc)
        except Exception:
            session.rollback()
            attempt = session.get(SheetReportSyncAttempt, attempt.id)
            attempt.status = "ERROR"
            attempt.error = "Lỗi nội bộ khi đọc báo cáo; xem log backend."
            attempt.finished_at = _utcnow()
            session.commit()
            raise
        attempt.finished_at = _utcnow()
        session.commit()
        return attempt


def confirm_current_source_mapping(session: Session, source_id: int) -> None:
    """Apply the owner's D-049 confirmation to the selected October source only."""
    with source_lock(session, source_id):
        source = session.get(SheetReportSource, source_id)
        if source is None or not source.active or source.period != "2026-10":
            raise ValueError("Chỉ xác nhận nguồn đang hoạt động của kỳ 2026-10.")
        if source.mapping_version == CONFIRMED_MAPPING_VERSION and source.mapping_config == CONFIRMED_MAPPING_CONFIG:
            return
        if source.mapping_version != MAPPING_VERSION or source.mapping_config != MAPPING_CONFIG:
            raise ValueError("Cấu hình mapping hiện tại không khớp D-047; không tự ghi đè.")
        source.mapping_version = CONFIRMED_MAPPING_VERSION
        source.mapping_config = {
            **MAPPING_CONFIG,
            "blank_usdt_header_tabs": CONFIRMED_MAPPING_CONFIG["blank_usdt_header_tabs"].copy(),
            "inactive_tabs_by_period": {"2026-10": CONFIRMED_MAPPING_CONFIG["inactive_tabs_by_period"]["2026-10"].copy()},
        }
        session.commit()


def confirm_separator_mapping(session: Session, source_id: int) -> None:
    with source_lock(session, source_id):
        source = session.get(SheetReportSource, source_id)
        if source is None or not source.active or source.period != "2026-10":
            raise ValueError("Chỉ xác nhận nguồn đang hoạt động của kỳ 2026-10.")
        if source.mapping_version == SEPARATOR_MAPPING_VERSION and source.mapping_config == SEPARATOR_MAPPING_CONFIG:
            return
        if source.mapping_version != CONFIRMED_MAPPING_VERSION or source.mapping_config != CONFIRMED_MAPPING_CONFIG:
            raise ValueError("Cấu hình mapping hiện tại không khớp D-049; không tự ghi đè.")
        source.mapping_version = SEPARATOR_MAPPING_VERSION
        source.mapping_config = {
            **source.mapping_config,
            "separator_rows_by_period": {"2026-10": {"JACK": [6, 9], "VIKTOR": [6]}},
        }
        session.commit()


def _customer_by_sheet(snapshot: SheetReportSnapshot, sheet_id: int, title: str) -> dict | None:
    matches = [
        item for item in snapshot.report.get("customers", [])
        if item.get("sheet_id") == sheet_id and item.get("source_sheet") == title
    ]
    return matches[0] if len(matches) == 1 else None


def compare_rollover(session: Session, previous_id: int, next_id: int) -> list[dict]:
    closure = session.scalar(select(SheetReportClosure).where(SheetReportClosure.source_id == previous_id))
    # Chưa chốt: đối chiếu tạm bằng snapshot mới nhất của kỳ trước; đối chiếu chính thức chỉ dựa bản chốt.
    previous = session.get(SheetReportSnapshot, closure.snapshot_id) if closure else latest_snapshot(session, previous_id)
    current = latest_snapshot(session, next_id)
    old_links = session.scalars(select(SheetReportCustomerLink).where(SheetReportCustomerLink.source_id == previous_id)).all()
    new_links = session.scalars(select(SheetReportCustomerLink).where(SheetReportCustomerLink.source_id == next_id)).all()
    by_old = {link.customer_id: link for link in old_links if link.active}
    by_new = {link.customer_id: link for link in new_links if link.active}
    tolerance = Decimal(str(tolerance_for_currency("VND")))
    result = []
    for customer_id in sorted(by_old.keys() | by_new.keys()):
        old_link, new_link = by_old.get(customer_id), by_new.get(customer_id)
        old_history = [link for link in old_links if old_link and link.customer_id == customer_id and link.sheet_id == old_link.sheet_id]
        old_match = next((link for link in old_history if previous and _customer_by_sheet(previous, link.sheet_id, link.source_title)), None)
        old = _customer_by_sheet(previous, old_match.sheet_id, old_match.source_title) if previous and old_match else None
        new = _customer_by_sheet(current, new_link.sheet_id, new_link.source_title) if current and new_link else None
        old_value = (old or {}).get("tab_source_totals", {}).get("current_balance", {}).get("value")
        new_value = (new or {}).get("opening_balance", {}).get("value")
        item = {
            "customer_id": customer_id,
            "previous_source": f"{old_match.source_title}!L1" if old_match else (f"{old_link.source_title}!L1" if old_link else None),
            "next_source": f"{new_link.source_title}!J1" if new_link else None,
            "previous_value": old_value,
            "next_value": new_value,
            "currency": "VND",
            "status": "MISSING",
            "difference": None,
            "tolerance": str(tolerance),
            "basis": "CLOSED" if closure else "PROVISIONAL_UNCLOSED",
            "previous_snapshot_id": previous.id if previous else None,
        }
        if old_value is not None and new_value is not None:
            difference = Decimal(str(new_value)) - Decimal(str(old_value))
            item["difference"] = str(difference)
            item["status"] = "MATCH" if abs(difference) <= tolerance else "DIFF"
        result.append(item)
    return result
