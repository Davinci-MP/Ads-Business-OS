"""Telegram Bot connector — thông báo & điều khiển quản trị (S4 & Controlled Agent).

Chuẩn: Bot API chính thức (`https://api.telegram.org/bot<token>/sendMessage`).
- Token/chat id từ biến môi trường (`ADSOS_TELEGRAM_BOT_TOKEN`,
  `ADSOS_TELEGRAM_ADMIN_CHAT_ID`, `ADSOS_TELEGRAM_ALLOWED_CHAT_IDS`); KHÔNG hardcode, KHÔNG log token.
- Phân quyền whitelist chặt chẽ: Chỉ các Chat ID nằm trong danh sách cho phép mới được tương tác.
- Chưa có token → mode mock (buffer in-memory) phục vụ kiểm thử.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BOT_TOKEN_ENV = "ADSOS_TELEGRAM_BOT_TOKEN"
ADMIN_CHAT_ENV = "ADSOS_TELEGRAM_ADMIN_CHAT_ID"
ALLOWED_CHATS_ENV = "ADSOS_TELEGRAM_ALLOWED_CHAT_IDS"


class TelegramAPIError(Exception):
    pass


class TelegramBotConnector:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        admin_chat_id: Optional[str] = None,
        allowed_chat_ids: Optional[list[str]] = None,
        timeout: float = 30.0,
        use_mock: Optional[bool] = None,
    ) -> None:
        self.admin_chat_id = admin_chat_id or settings.telegram_admin_chat_id or os.environ.get(ADMIN_CHAT_ENV, "")
        self._timeout = timeout
        token = bot_token if bot_token is not None else settings.telegram_bot_token or os.environ.get(BOT_TOKEN_ENV, "")
        self._use_mock = not token if use_mock is None else use_mock

        if allowed_chat_ids is not None:
            self.allowed_chat_ids = set(str(c).strip() for c in allowed_chat_ids if str(c).strip())
        else:
            raw_allowed = settings.telegram_allowed_chat_ids or os.environ.get(ALLOWED_CHATS_ENV, "")
            self.allowed_chat_ids = set(c.strip() for c in raw_allowed.split(",") if c.strip())

        if self.admin_chat_id:
            self.allowed_chat_ids.add(str(self.admin_chat_id).strip())

        if self._use_mock:
            self.sent_messages: list[dict[str, Any]] = []
        else:
            self._token = token
            self.sent_messages = None

    @property
    def mode(self) -> str:
        return "mock" if self._use_mock else "live"

    def __repr__(self) -> str:  # phòng thủ: không lộ token
        return f"TelegramBotConnector(mode={self.mode}, allowed_count={len(self.allowed_chat_ids)})"

    def is_chat_allowed(self, chat_id: Any) -> bool:
        """Kiểm tra chat ID có nằm trong danh sách whitelist được phép truy cập hay không."""
        cid_str = str(chat_id).strip()
        # Nếu chưa cấu hình whitelist nào thì chỉ cho phép admin_chat_id nếu có
        if not self.allowed_chat_ids:
            return cid_str == str(self.admin_chat_id).strip() if self.admin_chat_id else False
        return cid_str in self.allowed_chat_ids

    def send_message(self, chat_id: Any, text: str, parse_mode: str = "HTML") -> dict[str, Any]:
        """Gửi tin nhắn Telegram tới chat_id cụ thể."""
        cid_str = str(chat_id).strip()
        if self._use_mock:
            self.sent_messages.append({"chat_id": cid_str, "text": text, "parse_mode": parse_mode})
            return {"mode": "mock", "queued": True, "chat_id": cid_str}

        if not cid_str:
            raise TelegramAPIError("Thiếu chat_id để gửi tin nhắn Telegram")

        response = httpx.post(
            f"https://api.telegram.org/bot{self._token}/sendMessage",
            json={"chat_id": cid_str, "text": text, "parse_mode": parse_mode},
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise TelegramAPIError(
                f"Telegram API trả lỗi (HTTP {response.status_code}) khi gửi tới chat {cid_str}"
            )
        return {"mode": "live", "queued": False, "chat_id": cid_str}

    def send_admin_message(self, text: str) -> dict[str, Any]:
        """Gửi thông báo cho admin. Mock → buffer; không raise khi chưa cấu hình chat."""
        if self._use_mock:
            self.sent_messages.append({"chat_id": self.admin_chat_id, "text": text})
            return {"mode": "mock", "queued": True}
        if not self.admin_chat_id:
            raise TelegramAPIError("Chưa cấu hình ADSOS_TELEGRAM_ADMIN_CHAT_ID")
        return self.send_message(self.admin_chat_id, text)

    def get_updates(self, offset: Optional[int] = None, limit: int = 100) -> list[dict[str, Any]]:
        """Lấy danh sách updates mới từ Telegram Bot API (cho polling)."""
        if self._use_mock:
            return []
        params: dict[str, Any] = {"limit": limit}
        if offset is not None:
            params["offset"] = offset
        response = httpx.get(
            f"https://api.telegram.org/bot{self._token}/getUpdates",
            params=params,
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise TelegramAPIError(f"Không thể lấy updates từ Telegram (HTTP {response.status_code})")
        payload = response.json()
        return payload.get("result", [])

    def get_me(self) -> dict[str, Any]:
        """Lấy thông tin định danh của Bot từ Telegram API (kiểm tra token còn sống)."""
        if self._use_mock:
            return {
                "ok": True,
                "result": {
                    "id": 123456789,
                    "is_bot": True,
                    "first_name": "AdsBusinessOS_Bot",
                    "username": "adsbusinessos_bot",
                    "can_join_groups": True,
                    "can_read_all_group_messages": False,
                    "supports_inline_queries": False,
                },
            }
        response = httpx.get(
            f"https://api.telegram.org/bot{self._token}/getMe",
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise TelegramAPIError(f"Telegram API getMe lỗi (HTTP {response.status_code}): {response.text}")
        return response.json()

    def set_webhook(self, webhook_url: str, secret_token: Optional[str] = None) -> dict[str, Any]:
        """Cấu hình Webhook URL cho bot, hỗ trợ secret token xác thực tiêu đề HTTP."""
        if self._use_mock:
            return {"ok": True, "result": True, "description": f"Mock webhook set to {webhook_url}"}
        payload: dict[str, Any] = {"url": webhook_url}
        if secret_token:
            payload["secret_token"] = secret_token
        response = httpx.post(
            f"https://api.telegram.org/bot{self._token}/setWebhook",
            json=payload,
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise TelegramAPIError(f"Không thể thiết lập Webhook (HTTP {response.status_code}): {response.text}")
        return response.json()

    def get_webhook_info(self) -> dict[str, Any]:
        """Lấy trạng thái và sức khoẻ của Webhook hiện tại."""
        if self._use_mock:
            return {
                "ok": True,
                "result": {
                    "url": "",
                    "has_custom_certificate": False,
                    "pending_update_count": 0,
                    "max_connections": 40,
                },
            }
        response = httpx.get(
            f"https://api.telegram.org/bot{self._token}/getWebhookInfo",
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise TelegramAPIError(f"Không thể lấy thông tin Webhook (HTTP {response.status_code})")
        return response.json()

    def delete_webhook(self) -> dict[str, Any]:
        """Xoá cấu hình Webhook (để chuyển sang chế độ Polling)."""
        if self._use_mock:
            return {"ok": True, "result": True, "description": "Mock webhook deleted"}
        response = httpx.post(
            f"https://api.telegram.org/bot{self._token}/deleteWebhook",
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise TelegramAPIError(f"Không thể xoá Webhook (HTTP {response.status_code})")
        return response.json()
