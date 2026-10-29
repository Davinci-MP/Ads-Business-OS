"""Tự đọc số dư ví USDT (mặc định TẮT — chỉ chạy khi ví đã lưu bật auto_sync).

Chống chạy chồng: port-lock riêng (ADSOS_USDT_SCHEDULER_LOCK_PORT) + max_instances=1.
Lỗi đọc: ghi last_error, KHÔNG ghi 0, tick vẫn tiếp tục theo interval/backoff đơn giản.
"""
from __future__ import annotations

import logging
import socket
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import settings
from app.db import SessionLocal
from app.models.finance import USDT_BALANCE_AUTO, UsdtWallet
from app.services.usdt_wallet import read_balance

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None
_socket: socket.socket | None = None

TICK_SECONDS = 60


def scheduler_status() -> dict:
    job = _scheduler.get_job("usdt_wallet_sync") if _scheduler is not None else None
    return {
        "running_here": bool(_scheduler and _scheduler.running and job),
        "next_run_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }


def _due(wallet: UsdtWallet, now: datetime) -> bool:
    if wallet.last_checked_at is None:
        return True
    interval = max(5, settings.usdt_sync_interval_minutes)
    if wallet.last_error and wallet.last_ok_at and wallet.last_checked_at > wallet.last_ok_at:
        interval *= 2  # backoff x2 ngay sau lần đọc lỗi gần nhất
    return wallet.last_checked_at + timedelta(minutes=interval) <= now


def sync_wallet_balances() -> None:
    with SessionLocal() as db:
        wallets = db.scalars(select(UsdtWallet).where(UsdtWallet.auto_sync.is_(True))).all()
        now = datetime.now()
        for wallet in wallets:
            if not _due(wallet, now):
                continue
            try:
                _, payload = read_balance(db, source=USDT_BALANCE_AUTO)
                if wallet.id:
                    db.expire_all()  # re-read sau commit của read_balance
            except Exception:
                logger.exception("Tự đọc số dư ví %s thất bại", wallet.id)


def start_usdt_scheduler() -> None:
    global _scheduler, _socket
    if _scheduler is not None or not settings.usdt_scheduler_enabled:
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", settings.usdt_scheduler_lock_port))
    except OSError:
        sock.close()
        logger.info("Scheduler ví USDT đã được worker khác giữ.")
        return
    _socket = sock
    _scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    _scheduler.add_job(sync_wallet_balances, IntervalTrigger(seconds=TICK_SECONDS),
                       id="usdt_wallet_sync", max_instances=1, coalesce=True,
                       next_run_time=datetime.now() + timedelta(seconds=5))
    _scheduler.start()


def stop_usdt_scheduler() -> None:
    global _scheduler, _socket
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _socket is not None:
        _socket.close()
        _socket = None
