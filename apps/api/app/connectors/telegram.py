"""Telegram Bot connector — thông báo quản trị viên (S4).

Chuẩn: Bot API chính thức (`https://api.telegram.org/bot<token>/sendMessage`).
- Token/chat id chỉ từ biến môi trường (`ADSOS_TELEGRAM_BOT_TOKEN`,
  `ADSOS_TELEGRAM_ADMIN_CHAT_ID`); KHÔNG hardcode, KHÔNG log token.
- Chưa có token → mode mock (buffer in-memory) phục vụ kiểm thử.
- S4 chỉ gửi thông báo admin; KHÔNG xây bot hỗ trợ khách (theo yêu cầu chủ dự án).
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

BOT_TOKEN_ENV = "ADSOS_TELEGRAM_BOT_TOKEN"
ADMIN_CHAT_ENV = "ADSOS_TELEGRAM_ADMIN_CHAT_ID"


class TelegramAPIError(Exception):
    pass


class TelegramBotConnector:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        admin_chat_id: Optional[str] = None,
        timeout: float = 30.0,
        use_mock: Optional[bool] = None,
    ) -> None:
        self.admin_chat_id = admin_chat_id or os.environ.get(ADMIN_CHAT_ENV, "")
        self._timeout = timeout
        token = bot_token if bot_token is not None else os.environ.get(BOT_TOKEN_ENV, "")
        self._use_mock = not token if use_mock is None else use_mock
        if self._use_mock:
            self.sent_messages: list[dict[str, Any]] = []
        else:
            self._token = token
            self.sent_messages = None  # live: không giữ nội dung trong bộ nhớ

    @property
    def mode(self) -> str:
        return "mock" if self._use_mock else "live"

    def __repr__(self) -> str:  # phòng thủ: không lộ token
        return f"TelegramBotConnector(mode={self.mode})"

    def send_admin_message(self, text: str) -> dict[str, Any]:
        """Gửi thông báo cho admin. Mock → buffer; không raise khi chưa cấu hình chat."""
        if self._use_mock:
            self.sent_messages.append({"chat_id": self.admin_chat_id, "text": text})
            return {"mode": "mock", "queued": True}
        if not self.admin_chat_id:
            raise TelegramAPIError("Chưa cấu hình ADSOS_TELEGRAM_ADMIN_CHAT_ID")
        response = httpx.post(
            f"https://api.telegram.org/bot{self._token}/sendMessage",
            json={"chat_id": self.admin_chat_id, "text": text, "parse_mode": "HTML"},
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise TelegramAPIError(
                f"Telegram API trả lỗi (HTTP {response.status_code}) gửi cho admin"
            )
        return {"mode": "live", "queued": False}
