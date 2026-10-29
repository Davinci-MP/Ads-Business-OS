"""Job callable cho scheduler (S4 + hardening D-030/D-031).

Nguyên tắc:
- IDEMPOTENT — chạy lại không sinh snapshot trùng (unique (campaign_id, snapshot_at)).
- Token nạp từ biến môi trường trong connector; KHÔNG log token (D-027/D-031).
- KHÔNG fallback live→mock khi Meta lỗi (yêu cầu chủ dự án): trả/ghi nhận lỗi,
  giữ nguyên dữ liệu cũ.
- Production + mock → TỪ CHỐI chạy (không ghi số liệu giả lập vào production).
- 09:00 hai job cùng chạy → đúng MỘT lượt fetch Meta (D-030): lượt sau bỏ qua khi
  checkpoint cho kỳ đã có hoặc một sync đã hoàn thành rất gần đây.
- Telegram lỗi → message ghi vào telegram_outbox, gửi lại lần chạy sau (D-031).

Job functions nhận inject `session`/`connector`/`notifier`/`now` để kiểm thử;
scheduler wrapper gọi default (SessionLocal + connector/notifier từ env).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from app.connectors.meta import MetaAPIError, MetaAuthError, build_connector
from app.connectors.telegram import TelegramAPIError, TelegramBotConnector
from app.core.config import settings
from app.db import SessionLocal
from app.models import AuditLog, TelegramOutbox
from app.models.finance import OUTBOX_PENDING, OUTBOX_SENT
from app.services import notify
from app.services.meta_sync import (
    checkpoint_exists_for,
    is_checkpoint_time,
    is_recent_sync_completed,
    run_meta_sync,
)

CHECKPOINT_TITLE = "⏰ Đồng bộ checkpoint 09:00"
HOURLY_TITLE = "🔄 Đồng bộ chi tiêu hằng giờ"


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def flush_outbox(session: Any, notifier: TelegramBotConnector) -> int:
    """Gửi lại các thông báo PENDING trong outbox (D-031). Lỗi lần này giữ PENDING."""
    sent = 0
    pending = session.execute(
        select(TelegramOutbox).where(TelegramOutbox.status == OUTBOX_PENDING)
    ).scalars().all()
    for row in pending:
        try:
            notifier.send_admin_message(row.message)
            row.status = OUTBOX_SENT
            row.sent_at = datetime.now(timezone.utc)
            row.last_error = None
            sent += 1
        except TelegramAPIError as exc:
            row.attempts += 1
            row.last_error = f"{type(exc).__name__}: {exc}"
    session.flush()
    return sent


def send_or_queue(
    session: Any, notifier: TelegramBotConnector, title: str, summary: dict[str, Any], mode: str
) -> None:
    """Gửi thông báo; Telegram lỗi → ghi outbox PENDING để gửi lại lần chạy sau (D-031)."""
    try:
        notify.notify_sync_result(title, summary, mode, notifier)
    except TelegramAPIError as exc:
        session.add(TelegramOutbox(message=notify.format_sync_report(title, summary, mode), last_error=str(exc)))
        session.flush()


def meta_sync_job(
    session: Optional[Any] = None,
    connector: Optional[Any] = None,
    now: Optional[datetime] = None,
    notifier: Optional[TelegramBotConnector] = None,
) -> Optional[dict[str, Any]]:
    """Job đồng bộ hằng giờ. Không tự tạo connector mock khi live lỗi."""
    own_session = session is None
    session = session or SessionLocal()
    connector = connector or build_connector()
    notifier = notifier or TelegramBotConnector()
    if settings.app_env == "production" and connector.mode == "mock":
        # Guard: production không bao giờ ghi mock data (yêu cầu S4/S5).
        return {"status": "MOCK_NOT_ALLOWED_IN_PRODUCTION"}
    now = now or _default_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if is_checkpoint_time(now) and is_recent_sync_completed(now):
        # D-030: lượt 09:00 đã fetch xong rất gần đây → bỏ qua, không gọi Meta trùng
        return {"status": "SKIPPED_RECENT_RUN", "at": now.isoformat()}
    summary: dict[str, Any] | None = None
    try:
        flush_outbox(session, notifier)
        session.commit()  # retry outbox (D-031) commit riêng — không dính rollback của sync
        summary = run_meta_sync(session, connector, now=now)
        session.commit()  # 1 lượt job = 1 transaction; thành công thì commit luôn
    except MetaAuthError as exc:
        session.rollback()  # token hết hạn — KHÔNG fallback mock, giữ nguyên dữ liệu cũ
        summary = {"api_errors": [f"{type(exc).__name__}: {exc}"], "status": "AUTH_ERROR"}
    except MetaAPIError as exc:
        session.rollback()  # API không phản hồi — giữ nguyên dữ liệu trước đó
        summary = {"api_errors": [f"{type(exc).__name__}: {exc}"], "status": "API_ERROR"}
    finally:
        if own_session:
            session.close()
    if summary is not None and any(summary.get("api_errors", [])):
        send_or_queue(session, notifier, HOURLY_TITLE, summary, connector.mode)
        session.commit()  # outbox (D-031) phải chịu được rollback này — thông báo không bị mất
    return summary


# alias cho tên đã dùng ở S4 docs
run_meta_sync_job = meta_sync_job


def checkpoint_9h_job(
    session: Optional[Any] = None,
    connector: Optional[Any] = None,
    notifier: Optional[TelegramBotConnector] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Job checkpoint 09:00 riêng — chạy bằng APScheduler cron 09:00 Asia/Ho_Chi_Minh (D-029).

    - Trong cửa sổ grace: checkpoint snapshot_at = giờ fetch THỰC TẾ (không gán cứng 09:00).
    - Checkpoint kỳ này đã có / sync đã fetch gần đây → bỏ qua KHÔNG gọi Meta trùng (D-030).
    - Trễ ngoài cửa sổ → MISSED_CHECKPOINT, KHÔNG dùng dữ liệu sau giả làm 09:00.
    """
    own_session = session is None
    session = session or SessionLocal()
    connector = connector or build_connector()
    notifier = notifier or TelegramBotConnector()
    now = now or _default_now()
    try:
        if not is_checkpoint_time(now):
            missed: dict[str, Any] = {
                "status": "MISSED_CHECKPOINT",
                "checkpoint_at": now.isoformat(),
                "mode": connector.mode,
            }
            session.add(
                AuditLog(
                    actor="scheduler",
                    action="checkpoint_missed",
                    entity_type="checkpoint",
                    entity_id=now.isoformat(),
                    detail={"checkpoint_at": now.isoformat(), "mode": connector.mode},
                )
            )
            send_or_queue(session, notifier, CHECKPOINT_TITLE, {**missed, "checkpoints_9h": "MISSED"}, connector.mode)
            session.commit()  # outbox (D-031) + marker MISSED_CHECKPOINT cho dashboard
            return missed
        if checkpoint_exists_for(session, now):
            # D-030: lượt 09:00 khác (job hằng giờ) đã ghi checkpoint → bỏ qua, 0 lần gọi Meta
            return {"status": "SKIPPED_CHECKPOINT_EXISTS", "at": now.isoformat()}
        summary = meta_sync_job(session=session, connector=connector, now=now, notifier=notifier)
        if summary is not None and not summary.get("api_errors"):
            # lỗi đã thông báo trong meta_sync_job — chỉ thêm biên bản thành công
            send_or_queue(session, notifier, CHECKPOINT_TITLE, summary, connector.mode)
            session.commit()  # outbox (D-031)
            summary.setdefault("status", "OK")
        return summary or {"status": "OK"}
    finally:
        if own_session:
            session.close()
