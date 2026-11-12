"""Giới hạn bảng quản trị nội bộ trên máy local, hoặc ủy quyền qua Client Extension Key."""
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


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
