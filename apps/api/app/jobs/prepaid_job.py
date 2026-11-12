"""Xử lý đề nghị ngân sách đã duyệt; cảnh báo gửi sau khi ghi sổ thành công."""
from app.core.config import settings
from app.db import SessionLocal
from app.jobs.meta_sync_job import flush_outbox
from app.services.prepaid import process_approved_transactions
from app.services.telegram_bot import get_configured_telegram_connector


def prepaid_billing_job():
    if settings.app_env != "local":
        return 0
    with SessionLocal() as db:
        count = process_approved_transactions(db)
        db.commit()
        flush_outbox(db, get_configured_telegram_connector(db))
        db.commit()
        return count
