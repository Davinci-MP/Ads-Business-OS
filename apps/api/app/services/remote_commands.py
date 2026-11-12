"""Nghiệp vụ hàng đợi lệnh Meta do Chrome Extension thực thi."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import case, or_, select, update
from sqlalchemy.orm import Session

from app.models.customer import Customer, utcnow
from app.models.extension_remote import CampaignDraft, CampaignTemplate, RemoteViaCommand
from app.models.via import SyncedAdAccount, ViaProfile


TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}


def normalize_act_id(value: str) -> str:
    clean = str(value or "").strip()
    if clean.startswith("act_"):
        clean = clean[4:]
    if not clean.isdigit():
        raise ValueError("Mã tài khoản quảng cáo không hợp lệ.")
    return f"act_{clean}"


def enqueue_set_camp(
    db: Session,
    *,
    chat_id: str,
    act_id: str,
    campaign_name: str,
) -> RemoteViaCommand:
    customer = db.scalar(select(Customer).where(Customer.telegram_chat_id == str(chat_id)))
    if customer is None:
        raise PermissionError("TELEGRAM_NOT_LINKED")

    normalized = normalize_act_id(act_id)
    raw_id = normalized[4:]
    owned_filter = (
        or_(SyncedAdAccount.act_id == normalized, SyncedAdAccount.act_id == raw_id),
        SyncedAdAccount.customer_id == customer.id,
    )
    if db.scalar(select(SyncedAdAccount.id).where(*owned_filter).limit(1)) is None:
        raise PermissionError("ACCOUNT_NOT_OWNED")
    account = db.scalar(
        select(SyncedAdAccount)
        .join(ViaProfile, ViaProfile.id == SyncedAdAccount.via_profile_id)
        .where(*owned_filter, ViaProfile.token_status == "ACTIVE")
        .order_by(SyncedAdAccount.id.desc())
    )
    if account is None:
        raise ValueError("Chưa có VIA đang hoạt động và có quyền truy cập tài khoản này.")
    via = db.get(ViaProfile, account.via_profile_id)

    requested_name = campaign_name.strip()
    if not requested_name:
        raise ValueError("Tên chiến dịch không được để trống.")

    draft = db.scalar(
        select(CampaignDraft)
        .where(
            or_(
                CampaignDraft.draft_code.ilike(requested_name),
                CampaignDraft.draft_name.ilike(requested_name),
            )
        )
        .order_by(CampaignDraft.id.desc())
    )
    template = None
    if draft is None:
        template = db.scalar(
            select(CampaignTemplate)
            .where(CampaignTemplate.name.ilike(requested_name))
            .order_by(CampaignTemplate.id.desc())
        )

    payload: dict[str, Any] = {
        "campaign_name": draft.draft_name if draft else template.name if template else requested_name,
        "objective": draft.objective if draft else template.objective if template else "OUTCOME_ENGAGEMENT",
        "special_ad_categories": [],
        "status": "PAUSED",
    }
    if draft:
        payload.update(
            {
                "draft_code": draft.draft_code,
                "daily_budget": str(draft.daily_budget),
                "targeting": draft.targeting_json,
                "page_id": draft.page_id,
                "post_id": draft.post_id,
            }
        )
    elif template:
        payload.update(
            {
                "daily_budget": template.daily_budget,
                "targeting": template.targeting_json,
                "page_id": template.page_id,
                "post_id": template.post_id_or_creative_json,
            }
        )

    command = RemoteViaCommand(
        via_id=via.id,
        via_uid=via.uid,
        act_id=normalized,
        ad_account_id=normalized,
        customer_id=customer.id,
        draft_id=draft.id if draft else None,
        draft_name=payload["campaign_name"],
        command_type="SET_CAMP",
        payload=payload,
        payload_json=json.dumps(payload, ensure_ascii=False),
        status="PENDING",
        requested_by_telegram=str(chat_id),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(command)
    db.commit()
    db.refresh(command)
    return command


def enqueue_extension_command(
    db: Session,
    *,
    act_id: str,
    command_type: str,
    payload: dict[str, Any],
    customer_id: int | None = None,
    requested_by: str | None = None,
) -> RemoteViaCommand:
    """Xếp lệnh quản trị; mọi giá trị trạng thái tạo mới đều bị ép PAUSED."""
    normalized = normalize_act_id(act_id)
    raw_id = normalized[4:]
    account = db.scalar(
        select(SyncedAdAccount)
        .join(ViaProfile, ViaProfile.id == SyncedAdAccount.via_profile_id)
        .where(
            or_(SyncedAdAccount.act_id == normalized, SyncedAdAccount.act_id == raw_id),
            ViaProfile.token_status == "ACTIVE",
        )
        .order_by(SyncedAdAccount.id.desc())
    )
    via = db.get(ViaProfile, account.via_profile_id) if account else None
    safe_payload = dict(payload)
    if command_type == "SET_CAMP":
        safe_payload["status"] = "PAUSED"
    command = RemoteViaCommand(
        via_id=via.id if via else None,
        via_uid=via.uid if via else "",
        act_id=normalized,
        ad_account_id=normalized,
        customer_id=customer_id if customer_id is not None else account.customer_id if account else None,
        draft_name=str(safe_payload.get("campaign_name") or "") or None,
        command_type=command_type,
        payload=safe_payload,
        payload_json=json.dumps(safe_payload, ensure_ascii=False),
        status="PENDING",
        requested_by_telegram=requested_by,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(command)
    db.commit()
    db.refresh(command)
    return command


def serialize_command(command: RemoteViaCommand) -> dict[str, Any]:
    payload = command.payload
    if payload is None:
        try:
            payload = json.loads(command.payload_json or "{}")
        except (TypeError, ValueError):
            payload = {}
    public_id = command.public_id or str(command.id)
    return {
        "id": public_id,
        "legacy_id": command.id,
        "via_id": command.via_id,
        "via_uid": command.via_uid,
        "ad_account_id": command.ad_account_id or command.act_id,
        "act_id": command.act_id,
        "customer_id": command.customer_id,
        "customer_name": command.customer.name if command.customer else None,
        "campaign_name": command.draft_name or payload.get("campaign_name"),
        "command_type": command.command_type,
        "payload": payload,
        "status": command.status,
        "result_log": command.result_log or command.error_message or command.result_json,
        "created_at": command.created_at.isoformat() if command.created_at else None,
        "updated_at": command.updated_at.isoformat() if command.updated_at else None,
    }


def claim_oldest_pending(
    db: Session,
    via_uid: str | None,
    *,
    customer_id: int | None = None,
) -> RemoteViaCommand | None:
    query = select(RemoteViaCommand.id).where(RemoteViaCommand.status == "PENDING")
    if customer_id is not None:
        query = query.where(RemoteViaCommand.customer_id == customer_id)
    if via_uid:
        query = query.where(
            or_(RemoteViaCommand.via_uid == via_uid.strip(), RemoteViaCommand.via_id.is_(None))
        )

    while True:
        ordering = []
        if via_uid:
            ordering.append(case((RemoteViaCommand.via_uid == via_uid.strip(), 0), else_=1))
        command_id = db.scalar(
            query.order_by(*ordering, RemoteViaCommand.created_at.asc(), RemoteViaCommand.id.asc()).limit(1)
        )
        if command_id is None:
            return None
        claimed_at = utcnow()
        result = db.execute(
            update(RemoteViaCommand)
            .where(
                RemoteViaCommand.id == command_id,
                RemoteViaCommand.status == "PENDING",
            )
            .values(status="PROCESSING", updated_at=claimed_at)
        )
        db.commit()
        if result.rowcount == 1:
            return db.get(RemoteViaCommand, command_id)
        db.expire_all()


def find_command(db: Session, command_id: str) -> RemoteViaCommand | None:
    command = db.scalar(
        select(RemoteViaCommand).where(RemoteViaCommand.public_id == command_id)
    )
    if command is None and command_id.isdigit():
        command = db.get(RemoteViaCommand, int(command_id))
    return command


def cancel_pending(db: Session, command_id: str) -> RemoteViaCommand:
    command = find_command(db, command_id)
    if command is None:
        raise LookupError("Không tìm thấy lệnh từ xa.")
    if command.status != "PENDING":
        raise ValueError("Chỉ có thể hủy lệnh đang chờ xử lý.")
    command.status = "CANCELLED"
    command.result_log = "Lệnh đã được hủy bởi quản trị viên."
    command.updated_at = utcnow()
    command.completed_at = utcnow()
    db.commit()
    db.refresh(command)
    return command


def finish_command(
    db: Session,
    command_id: str,
    *,
    status: str,
    result: dict[str, Any] | None,
    result_log: str | None,
) -> RemoteViaCommand:
    command = find_command(db, command_id)
    if command is None:
        raise LookupError("Không tìm thấy lệnh từ xa.")
    normalized_status = status.upper()
    if normalized_status not in {"COMPLETED", "FAILED"}:
        raise ValueError("Trạng thái báo cáo chỉ được là COMPLETED hoặc FAILED.")
    if command.status in TERMINAL_STATUSES:
        if command.status == normalized_status:
            return command
        raise ValueError("Lệnh đã kết thúc và không thể đổi trạng thái.")
    if command.status != "PROCESSING":
        raise ValueError("Lệnh chưa được Extension nhận xử lý.")

    safe_log = (result_log or "").strip()[:4000] or None
    command.status = normalized_status
    command.result_json = json.dumps(result or {}, ensure_ascii=False)
    command.result_log = safe_log
    command.error_message = safe_log if normalized_status == "FAILED" else None
    command.updated_at = utcnow()
    command.completed_at = utcnow()
    db.commit()
    db.refresh(command)
    return command
