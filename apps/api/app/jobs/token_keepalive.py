"""Kiểm tra định kỳ tình trạng token VIA bằng Meta Graph API chính thức.

D-027/D-040 cấm lấy token từ cookie hoặc phiên Facebook. Vì vậy tác vụ này chỉ
xác thực token đã được cấu hình, giữ ấm kết nối HTTP và cập nhật trạng thái; nó
không mở Chrome, không đọc cookie và không thay thế token bí mật.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import random
import time
from typing import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.meta_proof import with_appsecret_proof
from app.db import SessionLocal
from app.models.via import ViaProfile
from app.services.via_manager import clean_meta_token, is_synthetic_meta_token

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenValidationResult:
    active: bool
    status: str
    message: str


def validate_via_token(via: ViaProfile) -> TokenValidationResult:
    """Xác thực token qua ``/me``; không đưa token vào URL hoặc log."""
    token = clean_meta_token(via.access_token)
    if not token or is_synthetic_meta_token(token):
        return TokenValidationResult(False, "EXPIRED", "VIA chưa có token Meta hợp lệ.")

    try:
        response = httpx.get(
            f"https://graph.facebook.com/{settings.meta_api_version}/me",
            params=with_appsecret_proof({"fields": "id"}, token),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15.0,
        )
    except httpx.HTTPError:
        return TokenValidationResult(False, "WARNING", "Không thể kết nối Meta Graph API.")

    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, dict) and payload.get("id"):
            return TokenValidationResult(True, "ACTIVE", "Token Meta đang hoạt động.")

    error_code = None
    try:
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            error_code = payload["error"].get("code")
    except ValueError:
        pass
    status = "EXPIRED" if response.status_code in (400, 401, 403) or error_code in (102, 190) else "WARNING"
    return TokenValidationResult(False, status, "Token Meta không còn được Graph API xác thực.")


def auto_verify_via_tokens(
    *,
    session_factory: sessionmaker[Session] = SessionLocal,
    validator: Callable[[ViaProfile], TokenValidationResult] = validate_via_token,
    now: datetime | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    uniform_fn: Callable[[float, float], float] = random.uniform,
) -> dict[str, int | str]:
    """Xác thực mọi token ACTIVE, cô lập transaction và lỗi theo từng VIA."""
    if not settings.via_token_keepalive_enabled:
        return {"status": "DISABLED", "checked": 0, "active": 0, "failed": 0, "skipped": 0}

    stamp = now or datetime.now(timezone.utc)
    with session_factory() as db:
        via_ids = list(
            db.scalars(
                select(ViaProfile.id)
                .where(ViaProfile.token_status == "ACTIVE")
                .order_by(ViaProfile.id)
            )
        )

    summary = {"status": "OK", "checked": 0, "active": 0, "failed": 0, "skipped": 0}
    for index, via_id in enumerate(via_ids):
        with session_factory() as db:
            try:
                via = db.get(ViaProfile, via_id)
                if via is None:
                    continue
                result = validator(via)
                summary["checked"] += 1
                if result.active:
                    via.last_token_refresh = stamp
                    if via.token_expires_at and via.token_expires_at <= stamp + timedelta(hours=24):
                        via.token_status = "WARNING"
                        summary["failed"] += 1
                    else:
                        via.token_status = "ACTIVE"
                        summary["active"] += 1
                else:
                    via.token_status = result.status
                    summary["failed"] += 1
                db.commit()
                if via.token_status == "ACTIVE":
                    logger.info("Đã xác thực token VIA #%s: ACTIVE", via_id)
                else:
                    logger.warning("Cảnh báo token VIA #%s: %s", via_id, via.token_status)
            except Exception as exc:  # cô lập tuyệt đối từng VIA; không log nội dung có thể chứa secret
                db.rollback()
                summary["checked"] += 1
                summary["failed"] += 1
                logger.error("Kiểm tra token VIA #%s thất bại (%s).", via_id, type(exc).__name__)

        if index < len(via_ids) - 1:
            low = max(0.0, settings.via_token_jitter_min_seconds)
            high = max(low, settings.via_token_jitter_max_seconds)
            sleep_fn(uniform_fn(low, high))

    return summary
