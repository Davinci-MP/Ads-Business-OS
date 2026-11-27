"""Mock LLM Provider phục vụ kiểm thử đơn vị và môi trường giả lập offline."""

from __future__ import annotations

import json
from typing import Any, Optional

from app.services.ai.providers.base import BaseLLMProvider, LLMMessage, LLMResponse, ToolCall
from app.services.ai.tools.base import ToolDefinition


class MockLLMProvider(BaseLLMProvider):
    def __init__(self, canned_responses: Optional[dict[str, str]] = None) -> None:
        self.canned_responses = canned_responses or {}
        self.call_history: list[list[LLMMessage]] = []

    def chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_instruction: str = "",
    ) -> LLMResponse:
        self.call_history.append(messages)

        last_msg = messages[-1] if messages else LLMMessage(role="user", content="")

        # Nếu tin nhắn cuối cùng là tool output (kết quả thực thi tool)
        if last_msg.role == "tool":
            return LLMResponse(
                text=f"Dựa trên dữ liệu tra cứu thành công từ hệ thống: {last_msg.content[:180]}..."
            )

        user_content = last_msg.content.lower()

        # Kiểm tra nếu prompt chứa từ khóa cần gọi tool và tools có sẵn
        available_tool_names = {t.name for t in tools} if tools else set()

        if ("tổng quan" in user_content or "hôm nay" in user_content) and "get_system_overview" in available_tool_names:
            return LLMResponse(
                text="Tôi sẽ lấy dữ liệu tổng quan hệ thống cho bạn.",
                tool_calls=[ToolCall(name="get_system_overview", args={})],
            )

        if ("chiến dịch" in user_content or "camp" in user_content) and "search_campaigns" in available_tool_names:
            return LLMResponse(
                text="Đang tra cứu danh sách chiến dịch...",
                tool_calls=[ToolCall(name="search_campaigns", args={"limit": 5})],
            )

        if ("số dư" in user_content or "balance" in user_content) and "get_my_balance" in available_tool_names:
            return LLMResponse(
                text="Đang tra cứu số dư của bạn...",
                tool_calls=[ToolCall(name="get_my_balance", args={})],
            )

        if ("chiến dịch của tôi" in user_content or "camp của tôi" in user_content) and "get_my_campaigns" in available_tool_names:
            return LLMResponse(
                text="Đang lấy danh sách chiến dịch của bạn...",
                tool_calls=[ToolCall(name="get_my_campaigns", args={})],
            )

        if ("nạp tiền" in user_content or "chuyển khoản" in user_content) and "get_deposit_instructions" in available_tool_names:
            return LLMResponse(
                text="Đang lấy thông tin chuyển khoản nạp ngân sách...",
                tool_calls=[ToolCall(name="get_deposit_instructions", args={})],
            )

        # Trả lời hội thoại thông thường
        return LLMResponse(
            text=f"Xin chào! Tôi là Trợ lý AI Copilot. Bạn vừa hỏi: '{last_msg.content}'. Tôi có thể hỗ trợ gì thêm?"
        )
