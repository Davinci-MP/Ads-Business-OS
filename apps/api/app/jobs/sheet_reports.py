"""Scheduler riêng cho nguồn Sheets; không bật hay gọi Meta sync."""
import logging
import socket
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import settings
from app.db import SessionLocal
from app.models.sheet_reports import SheetReportSource, SheetReportSyncAttempt
from app.services.sheet_report_store import SyncBusy, sync_source
from app.jobs.sheets_sync import run_customer_sheets_sync

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None
_socket: socket.socket | None = None


def scheduler_status() -> dict:
    job = _scheduler.get_job("sheets_reports") if _scheduler is not None else None
    return {
        "running_here": bool(_scheduler and _scheduler.running and job),
        "next_run_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }


SCHEDULE_MINUTES = 15
TICK_SECONDS = 60
MAX_BACKOFF_MINUTES = SCHEDULE_MINUTES


def _local_naive(value: datetime) -> datetime:
    return value.astimezone().replace(tzinfo=None) if value.tzinfo else value


def next_due_at(db, source_id: int) -> datetime | None:
    """Mốc đến hạn dựa trên lần thử gần nhất (mọi loại trigger); None nếu chưa có lần thử nào.

    Thành công hoặc PARTIAL: đủ 15 phút. ERROR liên tiếp: backoff 1, 2, 4, 8 phút, tối đa 15 phút.
    """
    attempts = db.scalars(select(SheetReportSyncAttempt).where(
        SheetReportSyncAttempt.source_id == source_id).order_by(SheetReportSyncAttempt.id.desc()).limit(8)).all()
    if not attempts:
        return None
    last = attempts[0]
    reference = _local_naive(last.finished_at or last.started_at)
    if last.status == "RUNNING":
        return _local_naive(last.started_at) + timedelta(minutes=SCHEDULE_MINUTES)
    failures = 0
    for item in attempts:
        if item.status != "ERROR":
            break
        failures += 1
    if failures:
        return reference + timedelta(minutes=min(2 ** (failures - 1), MAX_BACKOFF_MINUTES))
    return reference + timedelta(minutes=SCHEDULE_MINUTES)


def sync_enabled_sources(now: datetime | None = None) -> None:
    current = _local_naive(now) if now else datetime.now()
    with SessionLocal() as db:
        ids = db.scalars(select(SheetReportSource.id).where(
            SheetReportSource.active.is_(True), SheetReportSource.sync_enabled.is_(True))).all()
        due = []
        for source_id in ids:
            when = next_due_at(db, source_id)
            if when is None or when <= current:
                due.append(source_id)
    for source_id in due:
        with SessionLocal() as db:
            try:
                sync_source(db, source_id, "SCHEDULED")
            except SyncBusy:
                logger.info("Nguồn Sheets %s đang đồng bộ; bỏ qua lượt lịch.", source_id)
            except Exception:
                logger.exception("Lỗi đồng bộ nguồn Sheets %s", source_id)


def start_sheet_scheduler() -> None:
    global _scheduler, _socket
    if _scheduler is not None or not settings.sheets_scheduler_enabled:
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", settings.sheets_scheduler_lock_port))
    except OSError:
        sock.close()
        logger.info("Scheduler Sheets đã được worker khác giữ.")
        return
    _socket = sock
    _scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    _scheduler.add_job(sync_enabled_sources, IntervalTrigger(seconds=TICK_SECONDS), id="sheets_reports",
                       max_instances=1, coalesce=True,
                       next_run_time=datetime.now(timezone.utc) + timedelta(seconds=5))
    _scheduler.add_job(run_customer_sheets_sync, IntervalTrigger(seconds=TICK_SECONDS), id="customer_sheets_sync",
                       max_instances=1, coalesce=True,
                       next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10))
    _scheduler.start()


def stop_sheet_scheduler() -> None:
    global _scheduler, _socket
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _socket is not None:
        _socket.close()
        _socket = None
