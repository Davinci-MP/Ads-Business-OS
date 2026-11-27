"""Module bảo mật & làm sạch dữ liệu (Data Sanitizer) cho AI Copilot.

TUÂN THỦ BẮT BUỘC THEO QUY TẮC DỰ ÁN & REQ-3:
Tuyệt đối lọc bỏ password, 2fa_secret, cookie, token, secret, api key
trước khi gửi dữ liệu cho AI/LLM.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any, Mapping, Sequence

# Tập các từ khóa nhạy cảm cần loại bỏ/che giấu trong key của dictionary (case-insensitive)
SENSITIVE_KEY_PATTERNS = {
    "password",
    "pwd",
    "pass",
    "fb_password",
    "2fa",
    "2fa_secret",
    "two_factor",
    "two_factor_secret",
    "totp",
    "cookie",
    "cookies",
    "session_cookie",
    "c_user",
    "xs",
    "datr",
    "sb",
    "fr",
    "token",
    "access_token",
    "refresh_token",
    "auth_token",
    "bot_token",
    "jwt",
    "secret",
    "app_secret",
    "webhook_secret",
    "master_key",
    "api_key",
    "private_key",
    "encrypted_credentials",
    "encrypted_bot_token",
    "encrypted_webhook_secret",
    "credentials",
    "authorization",
}

# Regex nhận diện token / cookie / secret trong chuỗi văn bản tự do
RE_FB_TOKEN = re.compile(r"\b(EAAB|EAAG|EAAW|EAAC|EAAE|EAA)[A-Za-z0-9]{20,}\b")
RE_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9\-_\.=]{15,}\b", re.IGNORECASE)
RE_TG_TOKEN = re.compile(r"\b\d{8,11}:[A-Za-z0-9_-]{35}\b")
RE_API_KEY = re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|AIzaSy[A-Za-z0-9_-]{33})\b")
RE_COOKIE_STR = re.compile(r"(c_user=\d+|xs=[^;\s\n]+|datr=[^;\s\n]+|sb=[^;\s\n]+)", re.IGNORECASE)
RE_FERNET = re.compile(r"\bgAAAAAB[A-Za-z0-9_-]{50,}={0,2}\b")


def is_sensitive_key(key: str) -> bool:
    """Kiểm tra tên thuộc tính hoặc key có chứa thông tin nhạy cảm hay không."""
    lower_key = str(key).strip().lower()
    for sensitive in SENSITIVE_KEY_PATTERNS:
        if sensitive == lower_key or f"_{sensitive}" in lower_key or f"{sensitive}_" in lower_key:
            return True
    return False


def sanitize_string(value: str) -> str:
    """Khử trùng chuỗi ký tự tự do, thay thế các token/cookie/secret bằng nhãn [REDACTED]."""
    if not value:
        return value

    text = RE_FB_TOKEN.sub("[REDACTED_FB_TOKEN]", value)
    text = RE_BEARER.sub("Bearer [REDACTED_TOKEN]", text)
    text = RE_TG_TOKEN.sub("[REDACTED_TELEGRAM_TOKEN]", text)
    text = RE_API_KEY.sub("[REDACTED_API_KEY]", text)
    text = RE_COOKIE_STR.sub("[REDACTED_COOKIE]", text)
    text = RE_FERNET.sub("[REDACTED_ENCRYPTED_SECRET]", text)
    return text


def sanitize_data_for_ai(data: Any, max_depth: int = 8) -> Any:
    """Hàm khử trùng đệ quy cho mọi cấu trúc dữ liệu trước khi gửi sang LLM.
    
    1. Lọc bỏ / che giấu toàn bộ các trường nhạy cảm (password, 2fa_secret, cookie, token).
    2. Quét regex khử trùng các chuỗi nhúng token hay cookie.
    3. Chuẩn hóa Decimal, Date, Datetime thành kiểu dữ liệu JSON-safe.
    """
    if max_depth <= 0:
        return "[MAX_DEPTH_REACHED]"

    if data is None:
        return None

    if isinstance(data, (bool, int, float)):
        return data

    if isinstance(data, Decimal):
        return float(data)

    if isinstance(data, (datetime, date)):
        return data.isoformat()

    if isinstance(data, str):
        return sanitize_string(data)

    if isinstance(data, Mapping):
        cleaned_dict: dict[str, Any] = {}
        for k, v in data.items():
            str_k = str(k)
            if is_sensitive_key(str_k):
                cleaned_dict[str_k] = "[FILTERED_SENSITIVE]"
            else:
                cleaned_dict[str_k] = sanitize_data_for_ai(v, max_depth - 1)
        return cleaned_dict

    if isinstance(data, (Sequence, set)) and not isinstance(data, (str, bytes)):
        return [sanitize_data_for_ai(item, max_depth - 1) for item in data]

    # Xử lý SQLAlchemy model hoặc object tùy biến
    if hasattr(data, "__dict__"):
        obj_dict: dict[str, Any] = {}
        for attr, val in data.__dict__.items():
            if attr.startswith("_"):
                continue
            if is_sensitive_key(attr):
                obj_dict[attr] = "[FILTERED_SENSITIVE]"
            else:
                obj_dict[attr] = sanitize_data_for_ai(val, max_depth - 1)
        return obj_dict

    return sanitize_string(str(data))
