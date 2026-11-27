"""Kiểm thử tính năng lọc & làm sạch dữ liệu nhạy cảm (Data Sanitizer) cho AI Copilot.

Đảm bảo TUÂN THỦ TUYỆT ĐỐI REQ-3:
Lọc bỏ triệt để password, 2fa_secret, cookie, token trước khi nạp dữ liệu cho AI.
"""

from decimal import Decimal
from app.services.ai.sanitizer import is_sensitive_key, sanitize_data_for_ai, sanitize_string


def test_is_sensitive_key():
    assert is_sensitive_key("password") is True
    assert is_sensitive_key("fb_password") is True
    assert is_sensitive_key("2fa_secret") is True
    assert is_sensitive_key("totp") is True
    assert is_sensitive_key("cookie") is True
    assert is_sensitive_key("session_cookie") is True
    assert is_sensitive_key("access_token") is True
    assert is_sensitive_key("bot_token") is True
    assert is_sensitive_key("master_key") is True
    assert is_sensitive_key("encrypted_credentials") is True
    assert is_sensitive_key("c_user") is True
    assert is_sensitive_key("xs") is True
    assert is_sensitive_key("datr") is True

    # Khóa an toàn không được lọc nhầm
    assert is_sensitive_key("campaign_name") is False
    assert is_sensitive_key("spend") is False
    assert is_sensitive_key("currency") is False
    assert is_sensitive_key("customer_id") is False


def test_sanitize_string_redaction():
    # 1. Meta / Facebook Access Token
    raw_fb = "Tài khoản chạy với token EAABwz1234567890abcdefghijklmnopqrstuvwxyz"
    cleaned_fb = sanitize_string(raw_fb)
    assert "EAABwz1234567890abcdefghijklmnopqrstuvwxyz" not in cleaned_fb
    assert "[REDACTED_FB_TOKEN]" in cleaned_fb

    # 2. Bearer Token
    raw_bearer = "Header Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
    cleaned_bearer = sanitize_string(raw_bearer)
    assert "Bearer [REDACTED_TOKEN]" in cleaned_bearer

    # 3. Telegram Bot Token
    raw_tg = "Bot token là 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789"
    cleaned_tg = sanitize_string(raw_tg)
    assert "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in cleaned_tg
    assert "[REDACTED_TELEGRAM_TOKEN]" in cleaned_tg

    # 4. Cookie Header
    raw_cookie = "Cookie: c_user=10008899; xs=42%3Asome_secret_hash; datr=abc_token"
    cleaned_cookie = sanitize_string(raw_cookie)
    assert "10008899" not in cleaned_cookie
    assert "[REDACTED_COOKIE]" in cleaned_cookie


def test_sanitize_nested_dictionary():
    payload = {
        "customer_id": 42,
        "customer_name": "Cong ty TNHH Quang Cao",
        "fb_password": "super_secret_password_123",
        "2fa_secret": "JBSWY3DPEHPK3PXP",
        "cookie": "c_user=12345; xs=xyz;",
        "access_token": "EAAGtoken1234567890abcdef",
        "balance": Decimal("5000000.50"),
        "accounts": [
            {
                "account_id": "act_1001",
                "name": "TKQC So 1",
                "encrypted_credentials": "gAAAAABlxyz...",
                "notes": "Token x: EAAB12345678901234567890123456",
            }
        ],
    }

    sanitized = sanitize_data_for_ai(payload)

    # Các key nhạy cảm phải bị thay thế hoàn toàn
    assert sanitized["fb_password"] == "[FILTERED_SENSITIVE]"
    assert sanitized["2fa_secret"] == "[FILTERED_SENSITIVE]"
    assert sanitized["cookie"] == "[FILTERED_SENSITIVE]"
    assert sanitized["access_token"] == "[FILTERED_SENSITIVE]"

    # Các thông tin an toàn giữ nguyên
    assert sanitized["customer_id"] == 42
    assert sanitized["customer_name"] == "Cong ty TNHH Quang Cao"
    assert sanitized["balance"] == 5000000.50

    # Lồng nhau trong danh sách
    nested_acc = sanitized["accounts"][0]
    assert nested_acc["account_id"] == "act_1001"
    assert nested_acc["encrypted_credentials"] == "[FILTERED_SENSITIVE]"
    assert "EAAB1234567890" not in nested_acc["notes"]
    assert "[REDACTED_FB_TOKEN]" in nested_acc["notes"]
