"""API hàng đợi lệnh dành cho Chrome Extension và màn hình quản trị."""

from __future__ import annotations

import secrets
from html import escape
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.telegram import TelegramAPIError
from app.db import get_db
from app.models.extension_remote import ExtensionClientKey, RemoteViaCommand
from app.models.finance import TelegramOutbox
from app.services.remote_commands import (
    cancel_pending,
    claim_oldest_pending,
    find_command,
    finish_command,
    serialize_command,
)
from app.services.telegram_bot import get_configured_telegram_connector

router = APIRouter(prefix="/remote-commands", tags=["remote-commands"])


class CommandStatusRequest(BaseModel):
    status: str = Field(..., description="COMPLETED hoặc FAILED")
    result: dict[str, Any] | None = None
    result_log: str | None = Field(default=None, max_length=4000)


def _is_local(request: Request) -> bool:
    if not request.client or request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return False
    origin = request.headers.get("origin")
    if not origin:
        return True
    parsed = urlsplit(origin)
    return parsed.scheme == "chrome-extension" or parsed.hostname in {"127.0.0.1", "::1", "localhost"}


def require_local_queue_admin(request: Request) -> None:
    if not _is_local(request):
        raise HTTPException(status_code=403, detail="Hàng đợi lệnh chỉ được quản trị từ máy local.")


def require_extension_or_local(
    request: Request,
    db: Session = Depends(get_db),
) -> ExtensionClientKey | None:
    if _is_local(request):
        return None
    supplied = (request.headers.get("x-adsos-client-key") or "").strip()
    if supplied:
        active_keys = db.scalars(
            select(ExtensionClientKey).where(ExtensionClientKey.is_active.is_(True))
        ).all()
        for client_key in active_keys:
            if secrets.compare_digest(supplied, client_key.api_key):
                return client_key
    raise HTTPException(status_code=403, detail="Client Key của Extension không hợp lệ.")


@router.get("", dependencies=[Depends(require_local_queue_admin)])
def list_remote_commands(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = select(RemoteViaCommand)
    if status:
        query = query.where(RemoteViaCommand.status == status.upper())
    rows = db.scalars(
        query.order_by(RemoteViaCommand.created_at.desc(), RemoteViaCommand.id.desc()).limit(limit)
    ).all()
    return [serialize_command(row) for row in rows]


@router.get("/pending")
def take_pending_command(
    via_uid: str | None = Query(default=None),
    c_user: str | None = Query(default=None),
    db: Session = Depends(get_db),
    extension_key: ExtensionClientKey | None = Depends(require_extension_or_local),
) -> dict[str, Any] | None:
    """Claim nguyên tử đúng một lệnh cũ nhất để tránh Extension chạy trùng."""
    command = claim_oldest_pending(
        db,
        via_uid or c_user,
        customer_id=extension_key.client_id if extension_key else None,
    )
    return serialize_command(command) if command else None


@router.post("/{command_id}/status")
def report_command_status(
    command_id: str,
    body: CommandStatusRequest,
    db: Session = Depends(get_db),
    extension_key: ExtensionClientKey | None = Depends(require_extension_or_local),
) -> dict[str, Any]:
    existing = find_command(db, command_id)
    if (
        extension_key is not None
        and extension_key.client_id is not None
        and (existing is None or existing.customer_id != extension_key.client_id)
    ):
        raise HTTPException(status_code=403, detail="Extension không có quyền cập nhật lệnh này.")
    was_terminal = existing is not None and existing.status in {"COMPLETED", "FAILED", "CANCELLED"}
    try:
        command = finish_command(
            db,
            command_id,
            status=body.status,
            result=body.result,
            result_log=body.result_log,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    customer = command.customer
    if not was_terminal and customer and customer.telegram_chat_id:
        campaign_name = escape(command.draft_name or "không rõ tên")
        act_id = escape(command.act_id)
        if command.status == "COMPLETED":
            if command.command_type in {"SET_CAMP", "SET_CAMP_FROM_DRAFT"}:
                message = (
                    f"🚀 Báo cáo: Đã lên thành công camp {campaign_name} trên tài khoản "
                    f"{act_id}. Trạng thái: TẠM DỪNG (PAUSED)."
                )
            else:
                payload = serialize_command(command)["payload"]
                target_status = escape(str(payload.get("status") or "đã hoàn tất"))
                campaign_id = escape(str(payload.get("campaign_id") or campaign_name))
                message = (
                    f"✅ Báo cáo: Extension đã xử lý lệnh {escape(command.command_type)} "
                    f"cho chiến dịch {campaign_id}. Trạng thái đích: {target_status}."
                )
        else:
            message = (
                f"❌ Báo cáo: Lệnh {escape(command.command_type)} {campaign_name} trên tài khoản {act_id} "
                f"thất bại. Lỗi: {escape(command.result_log or 'Extension không cung cấp chi tiết.')}"
            )
        try:
            get_configured_telegram_connector(db).send_message(customer.telegram_chat_id, message)
        except TelegramAPIError as exc:
            db.add(
                TelegramOutbox(
                    chat_id=str(customer.telegram_chat_id),
                    message=message,
                    last_error=f"Không gửi được kết quả lệnh Extension: {type(exc).__name__}",
                )
            )
            db.commit()

    return {"success": True, "command": serialize_command(command)}


@router.post("/{command_id}/cancel", dependencies=[Depends(require_local_queue_admin)])
def cancel_remote_command(command_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        command = cancel_pending(db, command_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "message": "Đã hủy lệnh đang chờ xử lý.", "command": serialize_command(command)}
