"""Provider kết nối tới Google Gemini API (v1beta) qua REST HTTPX.

Hỗ trợ Function Calling native, streaming/non-streaming, cấu hình API Key từ .env.
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

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = (api_key or settings.gemini_api_key or "").strip()
        self.model = (model or settings.gemini_model or "gemini-3-flash-preview").strip()
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_instruction: str = "",
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                text=(
                    "⚠️ <b>Chưa cấu hình Gemini API Key</b>\n\n"
                    "Vui lòng thêm biến môi trường <code>GEMINI_API_KEY=AIzaSy...</code> vào file <code>.env</code> "
                    "hoặc cấu hình <code>LLM_PROVIDER=ollama</code> để sử dụng mô hình local."
                )
            )

        # Chuyển đổi các tin nhắn sang định dạng contents của Gemini
        contents: list[dict[str, Any]] = []
        for msg in messages:
            if msg.raw_content:
                # Bảo toàn nguyên vẹn candidate["content"] từ Gemini (giữ nguyên parts, thought_signature, thoughts)
                turn = dict(msg.raw_content)
                turn["role"] = "model"
                contents.append(turn)
            elif msg.role == "user":
                contents.append({"role": "user", "parts": [{"text": msg.content or " "}]})
            elif msg.role in ("assistant", "model"):
                # Tin nhắn từ lịch sử hội thoại trước đó (chỉ giữ nội dung text, tuyệt đối không tự tạo functionCall thiếu thought_signature)
                contents.append({"role": "model", "parts": [{"text": msg.content or " "}]})
            elif msg.role == "tool":
                # Phản hồi từ function execution — vai trò bắt buộc là "user" theo chuẩn Gemini REST v1beta
                if msg.function_responses:
                    contents.append({
                        "role": "user",
                        "parts": msg.function_responses,
                    })
                else:
                    tool_result = msg.content
                    if isinstance(tool_result, str):
                        try:
                            tool_result = json.loads(tool_result)
                        except Exception:
                            pass
                    if not isinstance(tool_result, dict):
                        tool_result = {"result": tool_result}

                    fn_resp: dict[str, Any] = {
                        "name": msg.tool_name or "tool",
                        "response": {
                            "name": msg.tool_name or "tool",
                            "content": tool_result,
                        },
                    }
                    if msg.tool_call_id:
                        fn_resp["id"] = msg.tool_call_id

                    contents.append({
                        "role": "user",
                        "parts": [{"functionResponse": fn_resp}],
                    })

        payload: dict[str, Any] = {"contents": contents}

        if system_instruction:
            payload["system_instruction"] = {
                "parts": [{"text": system_instruction}]
            }

        if tools:
            payload["tools"] = [{
                "function_declarations": [t.to_gemini_declaration() for t in tools]
            }]

        models_to_try = [self.model]
        for fallback in ("gemini-3-flash-preview", "gemini-3.8-flash", "gemini-flash-latest"):
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        res = None
        last_error = ""

        with httpx.Client(timeout=self.timeout) as client:
            for current_model in models_to_try:
                url = GEMINI_API_ENDPOINT.format(model=current_model)
                try:
                    res = client.post(
                        url,
                        params={"key": self.api_key},
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if res.status_code == 200:
                        break
                    last_error = f"HTTP {res.status_code}: {res.text}"
                    # Nếu gặp lỗi 503 (quá tải) hoặc 404 (mô hình không hỗ trợ), tự động thử mô hình tiếp theo
                    if res.status_code in (503, 404):
                        logger.warning("Mô hình %s trả về %s, đang thử model dự phòng...", current_model, res.status_code)
                        continue
                    break
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {str(exc)}"
                    logger.warning("Lỗi kết nối model %s: %s", current_model, exc)
                    continue

        if res is None or res.status_code != 200:
            logger.error("Toàn bộ yêu cầu tới Google Gemini API thất bại: %s", last_error)
            return LLMResponse(
                text=f"❌ Không thể nhận phản hồi từ Google Gemini API ({last_error}). Vui lòng thử lại sau giây lát."
            )

        data = res.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return LLMResponse(text="Không nhận được phản hồi từ mô hình Gemini.")

        candidate = candidates[0]
        raw_content = candidate.get("content", {})
        content_parts = raw_content.get("parts", [])

        accumulated_text = []
        tool_calls: list[ToolCall] = []

        for p in content_parts:
            if "text" in p and not p.get("thought"):
                accumulated_text.append(p["text"])
            if "functionCall" in p:
                fc = p["functionCall"]
                tool_calls.append(
                    ToolCall(
                        name=fc.get("name", ""),
                        args=fc.get("args", {}),
                        call_id=fc.get("id"),
                        raw_part=p,
                    )
                )

        return LLMResponse(
            text="\n".join(accumulated_text).strip(),
            tool_calls=tool_calls,
            raw=data,
            raw_content=raw_content,
        )
