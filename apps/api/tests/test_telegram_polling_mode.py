"""Kiểm thử chế độ Polling (ENV=development/local) vs Webhook (ENV=production) cho Telegram Bot."""

from app.core.config import settings
from app.jobs.telegram_polling import is_polling_mode_active, start_telegram_polling, stop_telegram_polling


def test_polling_mode_auto_switching(monkeypatch):
    # 1. Khi môi trường là local / development -> Polling BẬT
    monkeypatch.setattr(settings, "telegram_polling_enabled", None)
    monkeypatch.setattr(settings, "app_env", "development")
    assert is_polling_mode_active() is True

    monkeypatch.setattr(settings, "app_env", "local")
    assert is_polling_mode_active() is True

    monkeypatch.setattr(settings, "app_env", "dev")
    assert is_polling_mode_active() is True

    # 2. Khi môi trường là production / staging -> Chuyển sang Webhook (Polling TẮT)
    monkeypatch.setattr(settings, "app_env", "production")
    assert is_polling_mode_active() is False

    monkeypatch.setattr(settings, "app_env", "staging")
    assert is_polling_mode_active() is False

    # 3. Ghi đè chủ động bằng biến TELEGRAM_POLLING_ENABLED
    monkeypatch.setattr(settings, "telegram_polling_enabled", True)
    assert is_polling_mode_active() is True

    monkeypatch.setattr(settings, "telegram_polling_enabled", False)
    assert is_polling_mode_active() is False


def test_polling_lifecycle(monkeypatch):
    # Chạy thử start và stop trong môi trường local
    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(settings, "telegram_polling_enabled", True)
    # Cấu hình port giả định để không đụng port chính
    monkeypatch.setattr(settings, "telegram_polling_lock_port", 18913)

    started = start_telegram_polling()
    assert started is True

    # Thử start lần 2 khi đã có worker chạy -> fail do port lock
    started_second = start_telegram_polling()
    assert started_second is False

    stop_telegram_polling()
