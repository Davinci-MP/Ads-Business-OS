"""API Endpoints cho AI Copilot (Web CRM) dùng chung AI Orchestrator."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_staff
from app.db import get_db
from app.models.staff import StaffUser
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.tools.staff_tools import STAFF_TOOLS

router = APIRouter(prefix="/copilot", tags=["ai-copilot"])


class CopilotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="Nội dung câu hỏi hoặc yêu cầu")
    history: list[dict[str, str]] = Field(default_factory=list, description="Lịch sử các lượt chat trước")


class CopilotChatResponse(BaseModel):
    reply: str
    tools_used: list[str] = Field(default_factory=list)
    provider: str = ""
    status: str = "success"


class CopilotStatusResponse(BaseModel):
    provider: str
    model: str
    is_configured: bool
    app_env: str
    staff_tools_count: int
    staff_tools: list[str]


@router.get("/status", response_model=CopilotStatusResponse)
def get_copilot_status() -> dict[str, Any]:
    """Kiểm tra cấu hình LLM Provider, Model và danh mục STAFF_TOOLS sẵn có."""
    provider_name = settings.llm_provider.lower()
    if provider_name == "ollama":
        model_name = settings.ollama_model
        is_configured = True
    else:
        model_name = settings.gemini_model
        is_configured = bool(settings.gemini_api_key)

    return {
        "provider": provider_name,
        "model": model_name,
        "is_configured": is_configured,
        "app_env": settings.app_env,
        "staff_tools_count": len(STAFF_TOOLS),
        "staff_tools": list(STAFF_TOOLS.keys()),
    }


@router.post("/chat", response_model=CopilotChatResponse)
def copilot_chat_endpoint(
    req: CopilotChatRequest,
    current_staff: StaffUser = Depends(get_current_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Gửi câu hỏi từ Web CRM Copilot Drawer tới AI Orchestrator với STAFF_TOOLS."""
    orchestrator = AIOrchestrator()
    res = orchestrator.process_chat(
        db=db,
        message=req.message,
        role="staff",
        history=req.history,
        staff_user_id=current_staff.id,
        staff_username=current_staff.username,
    )
    return {
        "reply": res.get("reply", "Không có nội dung phản hồi."),
        "tools_used": res.get("tools_used", []),
        "provider": res.get("provider", settings.llm_provider),
        "status": res.get("status", "success"),
    }
