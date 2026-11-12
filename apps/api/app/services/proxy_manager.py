"""Proxy Manager — quản lý & luân chuyển Proxy riêng từng VIA (MaxCare nut 1: TMProxy/MinProxy/XProxy).

Nguyên tắc:
- KHÔNG tự đặt/suy đoán proxy. Proxy tĩnh gán thủ công qua `assign_proxy_to_via`.
- Proxy luân chuyển provider (rotate) chỉ chạy khi có API key env tương ứng (hoặc http_get được inject cho test).
- Shared proxy pool đọc từ env ADSOS_SHARED_PROXY_POOL; phân bổ theo ít người dùng nhất (least-used).
- Không lưu secret provider vào log; chỉ trả/ghi hiển thị dạng host:port(:user:pass).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Optional

import httpx
from sqlalchemy import func, select

from app.models.customer import utcnow
from app.models.via import ViaProfile
from app.services.via_manager import normalize_proxy_config

logger = logging.getLogger(__name__)

# Proxy luân chuyển provider: URL rotate + parse response
PROVIDER_INFO: dict[str, dict[str, Any]] = {
    "tmproxy": {
        "label": "TMProxy",
        "key_env": "ADSOS_TMPROXY_API_KEY",
        "rotate_url": "https://api.tmproxy.com/api/rotate?key={key}",
    },
    "minproxy": {
        "label": "MinProxy",
        "key_env": "ADSOS_MINPROXY_API_KEY",
        "rotate_url": "https://minproxy.vn/api/v1/rotate?key={key}",
    },
    "xproxy": {
        "label": "XProxy",
        "key_env": "ADSOS_XPROXY_API_KEY",
        "rotate_url": "https://api.xproxy.io/v1/rotate?key={key}",
    },
}

_PROXY_PATTERN = re.compile(
    r"(?P<host>\d{1,3}(?:\.\d{1,3}){3}):(?P<port>\d{2,5})"
    r"(?::(?P<user>[^\s:|]+):(?P<pass>[^\s|]+))?"
)

_SHARED_POOL_ENV = "ADSOS_SHARED_PROXY_POOL"


def extract_proxy_from_text(text: str) -> Optional[str]:
    """Trích chuỗi proxy (host:port:user:pass hoặc host:port) đầu tiên từ phản hồi provider."""
    if not text:
        return None
    match = _PROXY_PATTERN.search(text)
    if not match:
        return None
    user = match.group("user")
    pwd = match.group("pass")
    base = f"{match.group('host')}:{match.group('port')}"
    if user and pwd:
        return f"{base}:{user}:{pwd}"
    return base


def assign_proxy_to_via(session, via: ViaProfile, proxy_str: str) -> dict[str, Any]:
    """Gán proxy tĩnh (IP:Port:User:Pass hoặc URL) cho 1 VIA profile."""
    normalized = normalize_proxy_config(proxy_str)
    if not normalized or not normalized.get("raw"):
        raise ValueError(f"Proxy không hợp lệ: {proxy_str!r}")
    via.proxy_config = normalized["raw"]
    via.proxy_status = "UNKNOWN"
    session.commit()
    return {
        "via_id": via.id,
        "uid": via.uid,
        "proxy": normalized["display"],
        "proxy_status": via.proxy_status,
    }


def rotate_proxy_for_via(
    session,
    via: ViaProfile,
    provider: Optional[str] = None,
    http_get: Optional[Callable[[str], Any]] = None,
) -> dict[str, Any]:
    """Luân chuyển (rotate) 1 proxy mới từ provider và gán cho VIA.

    http_get: callable(url) -> object có .status_code/.text (inject cho test);
    môi trường thật dùng httpx.Client.get qua internet.
    Trả: {rotated: bool, message: str, proxy: str|None}
    - Không có API key và không có http_get -> rotated=False, KHÔNG đụng proxy hiện hữu.
    - Lỗi / phản hồi không trích được proxy -> giữ nguyên proxy cũ (không ghi đè bằng rỗng).
    """
    provider_name = (provider or os.getenv("ADSOS_PROXY_PROVIDER", "tmproxy")).strip().lower()
    info = PROVIDER_INFO.get(provider_name)
    if not info:
        return {"rotated": False, "message": f"Provider proxy chưa hỗ trợ: {provider_name}", "proxy": None}

    api_key = os.getenv(info["key_env"], "").strip()
    rotate_url = info["rotate_url"].format(key=api_key) if api_key else None

    response = None
    if http_get is not None:
        response = http_get(rotate_url or info["rotate_url"].format(key="TEST_KEY"))
    elif rotate_url:
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(rotate_url)
        except Exception as exc:
            logger.info("Rotate proxy %s cho VIA %s gặp ngoại lệ: %s", provider_name, via.uid, exc)
            return {
                "rotated": False,
                "message": f"Kiểm tra proxy mới ({info['label']}) thất bại; giữ proxy cũ.",
                "proxy": None,
            }
    else:
        return {
            "rotated": False,
            "message": f"Chưa cấu hình {info['key_env']} — proxy hiện tại của VIA giữ nguyên.",
            "proxy": None,
        }

    status = getattr(response, "status_code", None)
    text = getattr(response, "text", "") or ""
    if status is not None and status >= 400:
        return {
            "rotated": False,
            "message": f"Provider {info['label']} trả lỗi HTTP {status}; giữ proxy cũ.",
            "proxy": None,
        }

    new_proxy = extract_proxy_from_text(text)
    if not new_proxy:
        return {
            "rotated": False,
            "message": f"Phản hồi {info['label']} không chứa proxy hợp lệ; giữ proxy cũ.",
            "proxy": None,
        }

    normalized = normalize_proxy_config(new_proxy)
    old_proxy = via.proxy_config or ""
    via.proxy_config = normalized["raw"]
    via.proxy_status = "UNKNOWN"
    session.commit()
    changed = old_proxy != via.proxy_config
    return {
        "rotated": True,
        "message": f"Đã rotate proxy mới từ {info['label']}."
        if changed
        else f"Provider {info['label']} trả lại cùng proxy cũ (chưa đổi IP).",
        "proxy": normalized["display"],
    }


def get_shared_proxy_pool() -> list[str]:
    """Đọc shared proxy pool từ env (phân cách bằng xuống dòng, ';' hoặc ',')."""
    raw = os.getenv(_SHARED_POOL_ENV, "").strip()
    if not raw:
        return []
    pool: list[str] = []
    for chunk in re.split(r";|,|\n", raw):
        item = chunk.strip()
        if item and item not in pool:
            pool.append(item)
    return pool


def assign_next_shared_proxy(session, via: ViaProfile, pool: Optional[list[str]] = None) -> dict[str, Any]:
    """Phân bổ proxy ít người dùng nhất từ shared pool cho VIA."""
    entries = pool if pool is not None else get_shared_proxy_pool()
    if not entries:
        return {"assigned": False, "message": "Shared proxy pool trống (env ADSOS_SHARED_PROXY_POOL).", "proxy": None}

    counts: dict[str, int] = {entry: 0 for entry in entries}
    for profile in session.scalars(select(ViaProfile).where(ViaProfile.proxy_config.isnot(None))):
        label = (profile.proxy_config or "").strip()
        if label in counts:
            counts[label] += 1

    chosen = min(entries, key=lambda entry: (counts.get(entry, 0), entries.index(entry)))
    normalized = normalize_proxy_config(chosen)
    via.proxy_config = normalized["raw"]
    via.proxy_status = "UNKNOWN"
    session.commit()
    return {
        "assigned": True,
        "message": f"Đã gán proxy ít dùng nhất ({counts.get(chosen, 0)} VIA khác đang dùng).",
        "proxy": normalized["display"],
    }


def serialize_proxy_action(result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result)
    if payload.get("proxies_in_use"):
        payload["proxies_in_use"] = sorted(payload["proxies_in_use"])
    payload.setdefault("timestamp", utcnow().isoformat())
    return payload
