"""Cổng quản trị trên server công khai: chặn ẩn danh non-local, cho OWNER đăng nhập qua.

TestClient có host 'testclient' nằm trong whitelist local nên không bắt được nhánh non-local;
ở đây dựng Request giả với client non-local để kiểm tra đúng hành vi trên server.
"""

import itertools

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.api.v1.telegram_bot import require_telegram_admin
from app.core.config import settings
from app.core.local_admin import require_local_admin_or_owner
from app.core.security import create_access_token, hash_password
from app.models.staff import StaffUser

_seq = itertools.count(1)


def _request(host: str = "203.0.113.9", headers: dict | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http", "http_version": "1.1", "method": "GET", "scheme": "https",
        "path": "/api/v1/telegram/test-connection", "raw_path": b"/api/v1/telegram/test-connection",
        "query_string": b"", "headers": raw, "client": (host, 12345), "server": ("api", 443),
    }
    return Request(scope)


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_user(db, role: str, active: bool = True) -> StaffUser:
    n = next(_seq)
    user = StaffUser(username=f"gate_{role.lower()}_{n}", full_name=role,
                     password_hash=hash_password("Secret123!"), role=role, is_active=active)
    db.add(user)
    db.commit()
    return user


def test_non_local_an_danh_bi_chan(db):
    with pytest.raises(HTTPException) as exc:
        require_local_admin_or_owner(_request(), None, db)
    assert exc.value.status_code == 403


def test_non_local_owner_dang_nhap_qua_duoc(db):
    owner = _make_user(db, "OWNER")
    require_local_admin_or_owner(_request(), _bearer(create_access_token(owner.id)), db)  # không raise


def test_non_local_staff_thuong_bi_chan(db):
    staff = _make_user(db, "STAFF_SUPPORT")
    with pytest.raises(HTTPException) as exc:
        require_local_admin_or_owner(_request(), _bearer(create_access_token(staff.id)), db)
    assert exc.value.status_code == 403


def test_non_local_owner_bi_khoa_bi_chan(db):
    owner = _make_user(db, "OWNER", active=False)
    with pytest.raises(HTTPException):
        require_local_admin_or_owner(_request(), _bearer(create_access_token(owner.id)), db)


def test_telegram_gate_cho_owner_va_x_admin_token(db, monkeypatch):
    owner = _make_user(db, "OWNER")
    # OWNER đăng nhập
    require_telegram_admin(_request(), _bearer(create_access_token(owner.id)), db)
    # Ẩn danh non-local bị chặn
    with pytest.raises(HTTPException):
        require_telegram_admin(_request(), None, db)
    # x-admin-token khớp exchange_admin_token (>=16 ký tự) được qua
    monkeypatch.setattr(settings, "exchange_admin_token", "x" * 40)
    require_telegram_admin(_request(headers={"x-admin-token": "x" * 40}), None, db)
    # x-admin-token sai bị chặn
    with pytest.raises(HTTPException):
        require_telegram_admin(_request(headers={"x-admin-token": "sai"}), None, db)
