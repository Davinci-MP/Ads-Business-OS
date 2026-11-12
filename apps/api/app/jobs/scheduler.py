"""Scheduler S4 — APScheduler cron theo Asia/Ho_Chi_Minh.

- Job hằng giờ: đồng bộ chi tiêu tích lũy + phát hiện campaign mới theo D-026 +
  poll campaign cũ/đã dừng để bắt tiền trôi (D-023).
- Job riêng 09:00 VN hằng ngày: checkpoint (D-029). Ghi MỘT lần mỗi campaign/kỳ;
  chạy lỗi/trễ ngoài cửa sổ → MISSED_CHECKPOINT, không giả snapshot. 09:00 hai job
  cùng chạy → đúng MỘT lượt fetch Meta (D-030).
- KHÔNG fallback live→mock khi Meta lỗi.
- KHÔNG ghi Google Sheets thật — scheduler chỉ chạy meta sync.
- Tắt bằng env ADSOS_SCHEDULER_ENABLED=0. Nhiều uvicorn worker → chỉ 1 worker chạy
  scheduler nhờ port-lock (ADSOS_SCHEDULER_LOCK_PORT, D-030).
"""

from __future__ import annotations

import socket

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings

VN_TZ = "Asia/Ho_Chi_Minh"

_lock_socket: socket.socket | None = None
_running_scheduler: BackgroundScheduler | None = None


def acquire_scheduler_port_lock(port: int) -> socket.socket | None:
    """Port-lock để nhiều uvicorn worker không chạy scheduler song song (D-030)."""
    global _lock_socket
    if _lock_socket is not None:
        return _lock_socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))  # không SO_REUSEADDR — bind trùng phải fail
        _lock_socket = sock
        return sock
    except OSError:
        sock.close()
        return None


def build_scheduler() -> BackgroundScheduler:
    from app.jobs.asset_sync import scheduled_asset_sync
    from app.jobs.meta_sync_job import checkpoint_9h_job, meta_sync_job
    from app.jobs.meta_risk_job import meta_risk_job
    from app.jobs.prepaid_job import prepaid_billing_job
    from app.jobs.token_keepalive import auto_verify_via_tokens

    scheduler = BackgroundScheduler(timezone=VN_TZ)
    scheduler.add_job(prepaid_billing_job, "interval", minutes=1, id="prepaid_billing",
                      max_instances=1, coalesce=True, replace_existing=True)
    scheduler.add_job(meta_risk_job, "interval", minutes=5, id="meta_risk_monitor",
                      max_instances=1, coalesce=True, replace_existing=True)
    scheduler.add_job(
        auto_verify_via_tokens,
        "interval",
        hours=max(1, settings.via_token_keepalive_interval_hours),
        id="via_token_keepalive",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_asset_sync,
        "interval",
        hours=max(1, settings.via_asset_sync_interval_hours),
        id="via_asset_sync",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        meta_sync_job,
        CronTrigger(hour="*", minute=0, timezone=VN_TZ),
        id="meta_sync_hourly",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        checkpoint_9h_job,
        CronTrigger(hour=9, minute=0, timezone=VN_TZ),
        id="checkpoint_9h",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def start_scheduler(port_lock: bool = True) -> BackgroundScheduler | None:
    global _running_scheduler
    if _running_scheduler is not None:
        return None  # scheduler đã chạy trong process này — không start lần hai
    if not settings.scheduler_enabled:
        return None
    if port_lock and acquire_scheduler_port_lock(settings.scheduler_lock_port) is None:
        # worker khác đang giữ lock → worker này không chạy scheduler (D-030)
        return None
    _running_scheduler = build_scheduler()
    _running_scheduler.start()
    return _running_scheduler


def stop_scheduler() -> None:
    global _running_scheduler, _lock_socket
    if _running_scheduler is not None:
        _running_scheduler.shutdown(wait=False)
        _running_scheduler = None
    if _lock_socket is not None:
        try:
            _lock_socket.close()
        except OSError:
            pass
        _lock_socket = None
