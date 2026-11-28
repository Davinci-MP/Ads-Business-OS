"""Đồng bộ tài sản Meta định kỳ cho các VIA có token ACTIVE."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db import SessionLocal
from app.models.via import ViaProfile
from app.services.meta_scan import scan_via_job

logger = logging.getLogger(__name__)
ASSET_SYNC_LOCK = Lock()


def scheduled_asset_sync(
    *,
    session_factory: sessionmaker[Session] = SessionLocal,
    sync_callable: Callable[..., dict[str, Any]] = scan_via_job,
) -> dict[str, int | str]:
    """Đồng bộ từng VIA trong transaction riêng, giữ batch chạy khi một VIA lỗi."""
    if not settings.via_asset_sync_enabled:
        return {"status": "DISABLED", "total": 0, "success": 0, "failed": 0}
    if not ASSET_SYNC_LOCK.acquire(blocking=False):
        return {"status": "SKIPPED_CONCURRENT_RUN", "total": 0, "success": 0, "failed": 0}

    try:
        with session_factory() as db:
            via_ids = list(
                db.scalars(
                    select(ViaProfile.id)
                    .where(ViaProfile.token_status == "ACTIVE")
                    .order_by(ViaProfile.id)
                )
            )

        summary = {"status": "OK", "total": len(via_ids), "success": 0, "failed": 0}
        for via_id in via_ids:
            with session_factory() as db:
                try:
                    result = sync_callable(
                        session=db,
                        via_id=via_id,
                        allow_cookie_token_recovery=False,
                        mark_missing_inactive=True,
                    )
                    if result.get("success"):
                        summary["success"] += 1
                    else:
                        summary["failed"] += 1
                    logger.info("Đồng bộ tài sản VIA #%s: %s", via_id, result.get("status", "UNKNOWN"))
                except Exception as exc:
                    db.rollback()
                    summary["failed"] += 1
                    logger.error("Đồng bộ tài sản VIA #%s thất bại (%s).", via_id, type(exc).__name__)
        return summary
    finally:
        ASSET_SYNC_LOCK.release()
