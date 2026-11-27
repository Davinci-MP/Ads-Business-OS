"""Cấu trúc dữ liệu và giao diện Provider LLM trừu tượng."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.ai.tools.base import ToolDefinition


@dataclass
class ToolCall:
    """Yêu cầu gọi Tool từ LLM."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    call_id: Optional[str] = None
    raw_part: Optional[dict[str, Any]] = None


@dataclass
class LLMMessage:
    """Một tin nhắn trong luồng hội thoại với LLM."""
    role: str  # "user", "assistant" / "model", "system", "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    raw_content: Optional[dict[str, Any]] = None
    function_responses: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LLMResponse:
    """Kết quả phản hồi từ LLM Provider."""
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
    raw_content: Optional[dict[str, Any]] = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class BaseLLMProvider(ABC):
    """Lớp trừu tượng cho các nhà cung cấp mô hình ngôn ngữ lớn (Gemini, Ollama, v.v.)."""

    @abstractmethod
    def chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_instruction: str = "",
    ) -> LLMResponse:
        """Gửi lịch sử hội thoại cùng danh mục tools tới LLM và nhận phản hồi."""
        raise NotImplementedError
