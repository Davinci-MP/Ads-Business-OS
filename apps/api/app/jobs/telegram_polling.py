"""Dịch vụ chạy Telegram Bot ở chế độ Polling khi ENV=development / local.

TUÂN THỦ THEO REQ-2:
- Tự động chạy Polling khi ENV=development/local (tiện test trên máy cá nhân không cần domain/SSL).
- Tự động chuyển sang Webhook khi ENV=production (tắt Polling worker).
- Sử dụng port-lock để chống nhiều worker uvicorn kéo trùng update (D-030).
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Optional

from app.connectors.telegram import TelegramBotConnector
from app.core.config import settings
from app.db import SessionLocal
from app.services.telegram_bot import TelegramBotAgent, get_configured_telegram_connector

logger = logging.getLogger(__name__)

_polling_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_lock_socket: Optional[socket.socket] = None


def is_polling_mode_active() -> bool:
    """Xác định hệ thống nên chạy Polling hay Webhook dựa trên biến môi trường."""
    if settings.telegram_polling_enabled is not None:
        return bool(settings.telegram_polling_enabled)
    env_str = (settings.app_env or "local").strip().lower()
    return env_str in ("local", "dev", "development", "test")


def acquire_polling_port_lock(port: int) -> Optional[socket.socket]:
    """Port lock chống nhiều worker uvicorn chạy Polling song song."""
    global _lock_socket
    if _lock_socket is not None:
        return _lock_socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        _lock_socket = sock
        return sock
    except OSError:
        sock.close()
        return None


def _polling_worker(connector: TelegramBotConnector) -> None:
    """Worker chạy vòng lặp long polling getUpdates."""
    logger.info("Bắt đầu tiến trình Telegram Polling Worker (mode=%s)...", connector.mode)

    # Nếu đang có live token, xoá webhook cũ trên Telegram để chuyển sang nhận polling mượt mà
    if connector.mode == "live":
        try:
            connector.delete_webhook()
            logger.info("Đã xoá Webhook trên Telegram để kích hoạt chế độ Polling.")
        except Exception as exc:
            logger.warning("Không thể xoá Webhook khi bắt đầu Polling: %s", exc)

    offset: Optional[int] = None
    agent = TelegramBotAgent(telegram_connector=connector)

    while not _stop_event.is_set():
        try:
            # Nếu là mock mode, nghỉ để tránh chiếm CPU
            if connector.mode == "mock":
                time.sleep(2.0)
                continue

            updates = connector.get_updates(offset=offset, timeout_seconds=2)
            if updates:
                with SessionLocal() as db_session:
                    for update in updates:
                        up_id = update.get("update_id")
                        if up_id is not None:
                            offset = up_id + 1
                        try:
                            agent.process_update(db_session, update)
                        except Exception as proc_err:
                            logger.error("Lỗi khi xử lý Telegram update %s: %s", up_id, proc_err)

        except Exception as exc:
            if not _stop_event.is_set():
                logger.warning("Lỗi Telegram Polling (thử lại sau 3s): %s", exc)
                time.sleep(3.0)

        interval = max(0.2, settings.telegram_polling_interval_seconds)
        time.sleep(interval)

    logger.info("Telegram Polling Worker đã dừng an toàn.")


def start_telegram_polling() -> bool:
    """Khởi động Telegram Polling nếu môi trường là development/local."""
    global _polling_thread, _stop_event

    if _polling_thread is not None and _polling_thread.is_alive():
        logger.info("Telegram Polling đã đang chạy trong tiến trình này.")
        return False

    if not is_polling_mode_active():
        logger.info(
            "Telegram Bot: Đang chạy ở chế độ WEBHOOK (ENV=%s). Bỏ qua Polling nền.",
            settings.app_env,
        )
        return False

    port = settings.telegram_polling_lock_port
    sock = acquire_polling_port_lock(port)
    if not sock:
        logger.info("Telegram Polling đã được worker khác giữ lock trên port %s.", port)
        return False

    _stop_event.clear()
    connector = get_configured_telegram_connector()

    _polling_thread = threading.Thread(
        target=_polling_worker,
        args=(connector,),
        daemon=True,
        name="telegram_polling_worker",
    )
    _polling_thread.start()
    logger.info("Đã khởi chạy Telegram Polling nền thành công (ENV=%s, port=%s).", settings.app_env, port)
    return True


def stop_telegram_polling() -> None:
    """Dừng tiến trình Polling và giải phóng port lock."""
    global _polling_thread, _stop_event, _lock_socket
    _stop_event.set()

    if _polling_thread and _polling_thread.is_alive():
        _polling_thread.join(timeout=3.0)
    _polling_thread = None

    if _lock_socket is not None:
        try:
            _lock_socket.close()
        except Exception:
            pass
        _lock_socket = None

    logger.info("Đã giải phóng tài nguyên Telegram Polling.")
