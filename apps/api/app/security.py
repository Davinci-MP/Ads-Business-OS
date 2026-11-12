"""Lớp tương thích cho các import bảo mật cũ.

Mã xác thực chính nằm tại ``app.core.security``.
"""

from app.core.security import (
    create_access_token,
    get_current_staff,
    get_optional_current_staff,
    log_staff_action,
    mask_sensitive_data,
    require_owner,
    seed_default_owner,
)
from app.models.staff import hash_password as get_password_hash
from app.models.staff import verify_password

__all__ = [
    "create_access_token",
    "get_current_staff",
    "get_optional_current_staff",
    "get_password_hash",
    "log_staff_action",
    "mask_sensitive_data",
    "require_owner",
    "seed_default_owner",
    "verify_password",
]
