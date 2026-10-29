"""Tự đồng bộ số dư sàn (mặc định TẮT qua ADSOS_EXCHANGE_SCHEDULER_ENABLED=0).

Chống chạy chồng: port-lock riêng + max_instances=1. Lỗi từng connection: ghi
last_error + lịch sử (không 0 giả), tick tiếp theo theo interval/backoff x2.
"""
from __future__ import annotations

import logging
import socket
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import settings
from app.db import SessionLocal
from app.models.exchange import EXCH_SOURCE_AUTO, EXCH_STATUS_ACTIVE, ExchangeConnection
from app.services.exchange_connections import read_balances

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None
_socket: socket.socket | None = None

TICK_SECONDS = 60


def scheduler_status() -> dict:
    job = _scheduler.get_job("exchange_wallet_sync") if _scheduler is not None else None
    return {
        "running_here": bool(_scheduler and _scheduler.running and job),
        "next_run_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }


def _due(connection: ExchangeConnection, now: datetime) -> bool:
    if connection.last_checked_at is None:
        return True
    interval = max(5, settings.exchange_sync_interval_minutes)
    if bool(connection.last_error) and connection.last_ok_at and connection.last_checked_at > connection.last_ok_at:
        interval *= 2
    return connection.last_checked_at + timedelta(minutes=interval) <= now


def sync_exchange_balances() -> None:
    with SessionLocal() as db:
        connections = db.scalars(
            select(ExchangeConnection).where(
                ExchangeConnection.auto_sync.is_(True),
                ExchangeConnection.status == EXCH_STATUS_ACTIVE,
            )
        ).all()
        now = datetime.now(timezone.utc)
        for connection in connections:
            if not _due(connection, now):
                continue
            try:
                read_balances(db, connection.id, source=EXCH_SOURCE_AUTO)
                db.expire_all()
            except Exception:
                logger.warning("Tự đồng bộ sàn %s thất bại; xem lịch sử kết nối", connection.id)


def start_exchange_scheduler() -> None:
    global _scheduler, _socket
    if _scheduler is not None or not settings.exchange_scheduler_enabled:
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", settings.exchange_scheduler_lock_port))
    except OSError:
        sock.close()
        logger.info("Scheduler sàn đã được worker khác giữ.")
        return
    _socket = sock
    _scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    _scheduler.add_job(
        sync_exchange_balances,
        IntervalTrigger(seconds=TICK_SECONDS),
        id="exchange_wallet_sync",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=5),
    )
    _scheduler.start()


def stop_exchange_scheduler() -> None:
    global _scheduler, _socket
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _socket is not None:
        _socket.close()
        _socket = None
