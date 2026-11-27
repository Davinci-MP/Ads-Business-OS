"""Định nghĩa cấu trúc Tool (Function Calling) chuẩn cho AI Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from sqlalchemy.orm import Session


@dataclass
class ToolContext:
    """Ngữ cảnh thực thi tool: phân quyền nhân viên hoặc thông tin khách hàng."""
    role: str  # "staff" hoặc "customer"
    staff_user_id: Optional[int] = None
    staff_username: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None


@dataclass
class ToolDefinition:
    """Mô tả một công cụ AI với JSON Schema cho tham số và hàm xử lý nghiệp vụ."""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    handler: Optional[Callable[..., Any]] = None

    def to_gemini_declaration(self) -> dict[str, Any]:
        """Chuyển đổi sang format function_declaration của Google Gemini."""
        gemini_params = {
            "type": "OBJECT",
            "properties": {},
            "required": self.parameters.get("required", []),
        }
        for prop_name, prop_meta in self.parameters.get("properties", {}).items():
            p_type = prop_meta.get("type", "string").upper()
            if p_type == "NUMBER":
                p_type = "NUMBER"
            elif p_type in ("INT", "INTEGER"):
                p_type = "INTEGER"
            elif p_type == "BOOLEAN":
                p_type = "BOOLEAN"
            elif p_type == "ARRAY":
                p_type = "ARRAY"
            else:
                p_type = "STRING"

            gemini_params["properties"][prop_name] = {
                "type": p_type,
                "description": prop_meta.get("description", ""),
            }
        return {
            "name": self.name,
            "description": self.description,
            "parameters": gemini_params,
        }

    def to_ollama_declaration(self) -> dict[str, Any]:
        """Chuyển đổi sang format tools (OpenAI-compatible) của Ollama."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
