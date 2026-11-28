"""Giới hạn bảng quản trị nội bộ trên máy local, hoặc ủy quyền qua Client Extension Key."""
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db

_optional_bearer = HTTPBearer(auto_error=False)


def require_local_admin(request: Request) -> None:
    path = request.url.path

    # Ping & Health check luôn mở tự do để Extension tự động dò tìm máy chủ kết nối
    if path.endswith("/ping") or path in {"/health", "/api/v1/vias/ping"}:
        return

    # Cho phép các endpoint Extension kết nối từ xa khi có Client Key hoặc từ chrome-extension
    if (
        path.startswith("/api/v1/vias/extension-")
        or "/remote-commands" in path
        or "/campaign-drafts" in path
        or path.endswith("/customer-spend-summary")
        or path.endswith("/download-extension")
        or path.endswith("/sync-browser-cookie")
    ):
        client_key = request.headers.get("x-adsos-client-key") or request.headers.get("X-AdsOS-Client-Key")
        if client_key:
            return
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).scheme == "chrome-extension":
            return
        if not request.client or request.client.host in {"127.0.0.1", "::1", "localhost", "testclient"}:
            return

    if not request.client or request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(403, "Chức năng quản trị chỉ được truy cập từ máy local hoặc yêu cầu Client Key.")
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme == "chrome-extension":
            return
        if request.url.path.endswith("/sync-browser-cookie"):
            return
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(403, "Nguồn yêu cầu không được phép quản trị.")


def require_local_admin_or_owner(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    db: Session = Depends(get_db),
) -> None:
    """Cho phép nếu (1) hợp lệ theo require_local_admin (máy local / Client Key / extension),
    HOẶC (2) là OWNER đã đăng nhập (JWT). Dùng cho thao tác quản trị cần chạy trên server
    công khai — ví dụ luồng OAuth Meta để quay video App Review. Vẫn chặn công khai: chỉ
    OWNER (vai trò cao nhất) mới qua được khi không ở máy local.
    """
    try:
        require_local_admin(request)
        return
    except HTTPException:
        pass

    if credentials is not None and credentials.scheme.lower() == "bearer":
        from app.core.security import get_current_staff  # lazy: tránh import vòng

        try:
            user = get_current_staff(credentials, db)
        except HTTPException:
            user = None
        if user is not None and getattr(user, "role", None) == "OWNER" and getattr(user, "is_active", False):
            return

    raise HTTPException(
        403,
        "Chức năng quản trị: cần máy local, Client Key, hoặc đăng nhập OWNER.",
    )
