"""Xác thực nhân sự bằng token HMAC, không phụ thuộc thư viện JWT bên ngoài."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.staff import StaffAuditLog, StaffUser, hash_password, verify_password

_bearer = HTTPBearer(auto_error=False)
_local_signing_key = secrets.token_bytes(32)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _signing_key() -> bytes:
    configured = settings.staff_auth_secret.strip()
    if configured:
        return configured.encode("utf-8")
    if settings.app_env == "production":
        raise RuntimeError("ADSOS_STAFF_AUTH_SECRET là bắt buộc trong production")
    return _local_signing_key


def create_access_token(subject: str | int, expires_delta: int | None = None) -> str:
    lifetime = expires_delta or settings.staff_access_token_expires_minutes * 60
    payload = _b64encode(
        json.dumps(
            {"sub": str(subject), "exp": int(time.time()) + lifetime},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signature = _b64encode(hmac.new(_signing_key(), payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def _token_subject(token: str) -> int:
    try:
        payload, supplied_signature = token.split(".", 1)
        expected_signature = _b64encode(
            hmac.new(_signing_key(), payload.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError
        data = json.loads(_b64decode(payload))
        if int(data["exp"]) <= int(time.time()):
            raise ValueError
        return int(data["sub"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> StaffUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bạn chưa đăng nhập.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(StaffUser, _token_subject(credentials.credentials))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Tài khoản nhân sự không còn hoạt động.")
    return user


def get_optional_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> StaffUser | None:
    if credentials is None:
        return None
    return get_current_staff(credentials, db)


def require_owner(current_staff: StaffUser = Depends(get_current_staff)) -> StaffUser:
    if current_staff.role != "OWNER":
        raise HTTPException(status_code=403, detail="Chỉ OWNER được phép thực hiện thao tác này.")
    return current_staff


def mask_sensitive_data(user: StaffUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "assigned_customer_ids": user.assigned_customer_ids or [],
        "is_active": user.is_active,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def log_staff_action(
    db_session: Session,
    staff: StaffUser,
    action_type: str,
    *,
    target_bm_id: str | None = None,
    target_account_ids: list[str] | None = None,
    recipient_info: str | None = None,
    status_value: str = "SUCCESS",
    detail: str | None = None,
) -> StaffAuditLog:
    entry = StaffAuditLog(
        staff_id=staff.id,
        username=staff.username,
        role=staff.role,
        action_type=action_type,
        target_bm_id=target_bm_id,
        target_account_ids=target_account_ids,
        recipient_info=recipient_info,
        status=status_value,
        detail=detail,
    )
    db_session.add(entry)
    return entry


def seed_default_owner() -> None:
    if not settings.staff_seed_default_owner or settings.app_env != "local":
        return
    from sqlalchemy.exc import OperationalError
    from app.db import SessionLocal

    with SessionLocal() as db:
        try:
            if db.query(StaffUser).filter(StaffUser.username == "admin").first() is None:
                db.add(
                    StaffUser(
                        username="admin",
                        full_name="Quản trị hệ thống",
                        email="admin@adsos.local",
                        password_hash=hash_password("Admin@123"),
                        role="OWNER",
                        is_active=True,
                    )
                )
                db.commit()
        except OperationalError:
            db.rollback()
