"""Provider kết nối tới mô hình Ollama chạy Local trên máy trạm.

Hỗ trợ giao tiếp trực tiếp qua REST API http://localhost:11434/api/chat với Tool Calling.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.services.ai.providers.base import BaseLLMProvider, LLMMessage, LLMResponse, ToolCall
from app.services.ai.tools.base import ToolDefinition

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url or "http://localhost:11434").rstrip("/")
        self.model = (model or settings.ollama_model or "llama3").strip()
        self.timeout = timeout

    def chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_instruction: str = "",
    ) -> LLMResponse:
        ollama_messages: list[dict[str, Any]] = []

        if system_instruction:
            ollama_messages.append({"role": "system", "content": system_instruction})

        for msg in messages:
            if msg.role == "tool":
                if msg.function_responses:
                    for fr in msg.function_responses:
                        fn_obj = fr.get("functionResponse", {})
                        ollama_messages.append({
                            "role": "tool",
                            "name": fn_obj.get("name"),
                            "content": json.dumps(fn_obj.get("response", {}).get("content", {}), ensure_ascii=False),
                        })
                else:
                    ollama_messages.append({
                        "role": "tool",
                        "content": msg.content if isinstance(msg.content, str) else json.dumps(msg.content, ensure_ascii=False),
                    })
            elif msg.role in ("assistant", "model"):
                m_dict: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    m_dict["tool_calls"] = [
                        {
                            "function": {
                                "name": tc.name,
                                "arguments": tc.args,
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                ollama_messages.append(m_dict)
            else:
                ollama_messages.append({"role": msg.role, "content": msg.content})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
        }

        if tools:
            payload["tools"] = [t.to_ollama_declaration() for t in tools]

        url = f"{self.base_url}/api/chat"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(url, json=payload)
        except Exception as exc:
            logger.warning("Không thể kết nối tới Ollama tại %s: %s", self.base_url, exc)
            return LLMResponse(
                text=(
                    f"⚠️ <b>Không thể kết nối tới máy chủ Ollama tại {self.base_url}</b>\n\n"
                    "Vui lòng đảm bảo Ollama đã được cài đặt và đang chạy lệnh <code>ollama serve</code> "
                    f"hoặc đã tải mô hình <code>ollama run {self.model}</code>."
                )
            )

        if res.status_code != 200:
            return LLMResponse(
                text=f"❌ Ollama API trả về lỗi (HTTP {res.status_code}): {res.text}"
            )

        data = res.json()
        resp_msg = data.get("message", {})
        content = resp_msg.get("content", "")
        raw_tools = resp_msg.get("tool_calls", [])

        tool_calls: list[ToolCall] = []
        for rt in raw_tools:
            fn = rt.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if name:
                tool_calls.append(ToolCall(name=name, args=args))

        return LLMResponse(
            text=content.strip(),
            tool_calls=tool_calls,
            raw=data,
        )
