"""Nghiệp vụ backend tương thích extension metaOs; không gọi Meta hoặc ghi tài chính."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.customer import utcnow
from app.models.extension_remote import (
    ExtensionClientKey,
    ExtensionReportEdit,
    ExtensionReportShare,
    ExtensionReportSnapshot,
)


class MetaOsIntegrationUnavailable(RuntimeError):
    pass


def find_active_client_key(db: Session, supplied: str | None) -> ExtensionClientKey | None:
    key = (supplied or "").strip()
    if not key:
        return None
    rows = db.scalars(select(ExtensionClientKey).where(ExtensionClientKey.is_active.is_(True))).all()
    return next((row for row in rows if secrets.compare_digest(key, row.api_key)), None)


def serialize_share(row: ExtensionReportShare) -> dict[str, Any]:
    return {
        "id": row.public_id,
        "accountId": row.account_id,
        "accountName": row.account_name,
        "currency": row.currency,
        "scopeType": row.scope_type,
        "campaignIds": row.campaign_ids or [],
        "status": row.status,
        "lastHeartbeatAt": row.last_heartbeat_at.isoformat() if row.last_heartbeat_at else None,
    }


def list_shares(db: Session, client_key: ExtensionClientKey | None) -> list[ExtensionReportShare]:
    query = select(ExtensionReportShare)
    query = query.where(
        ExtensionReportShare.client_key_id == (client_key.id if client_key else None)
    )
    return db.scalars(query.order_by(ExtensionReportShare.id.asc())).all()


def create_share(
    db: Session,
    *,
    client_key: ExtensionClientKey | None,
    account_id: str,
    account_name: str,
    currency: str,
    scope_type: str,
    campaign_ids: list[str],
) -> ExtensionReportShare:
    row = ExtensionReportShare(
        client_key_id=client_key.id if client_key else None,
        account_id=account_id,
        account_name=account_name,
        currency=currency,
        scope_type=scope_type,
        campaign_ids=campaign_ids,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_share_status(
    db: Session,
    public_id: str,
    status: str,
    client_key: ExtensionClientKey | None,
) -> ExtensionReportShare:
    row = db.scalar(
        select(ExtensionReportShare).where(
            ExtensionReportShare.public_id == public_id,
            ExtensionReportShare.client_key_id == (client_key.id if client_key else None),
        )
    )
    if row is None:
        raise LookupError("Không tìm thấy liên kết báo cáo.")
    row.status = status
    row.updated_at = utcnow()
    db.commit()
    return row


def heartbeat_shares(db: Session, client_key: ExtensionClientKey | None) -> int:
    rows = list_shares(db, client_key)
    now = utcnow()
    for row in rows:
        row.last_heartbeat_at = now
        row.updated_at = now
    db.commit()
    return len(rows)


def append_snapshot(
    db: Session,
    *,
    share_public_id: str,
    snapshot: dict[str, Any],
    client_key: ExtensionClientKey | None,
) -> tuple[ExtensionReportSnapshot, bool]:
    share = db.scalar(
        select(ExtensionReportShare).where(
            ExtensionReportShare.public_id == share_public_id,
            ExtensionReportShare.client_key_id == (client_key.id if client_key else None),
        )
    )
    if share is None:
        raise LookupError("Không tìm thấy liên kết báo cáo.")
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = db.scalar(
        select(ExtensionReportSnapshot).where(
            ExtensionReportSnapshot.share_id == share.id,
            ExtensionReportSnapshot.content_hash == content_hash,
        )
    )
    if existing:
        return existing, False
    row = ExtensionReportSnapshot(
        share_id=share.id,
        content_hash=content_hash,
        payload=snapshot,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, True


def create_edit(
    db: Session,
    *,
    share_public_id: str,
    target_id: str,
    account_id: str,
    currency: str,
    action: str,
    params: dict[str, Any],
    client_key: ExtensionClientKey | None,
) -> ExtensionReportEdit:
    share = db.scalar(
        select(ExtensionReportShare).where(
            ExtensionReportShare.public_id == share_public_id,
            ExtensionReportShare.client_key_id == (client_key.id if client_key else None),
        )
    )
    if share is None:
        raise LookupError("Không tìm thấy liên kết báo cáo.")
    row = ExtensionReportEdit(
        share_id=share.id,
        target_id=target_id,
        account_id=account_id,
        currency=currency,
        action=action,
        params=params,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def claim_pending_edits(
    db: Session, client_key: ExtensionClientKey | None, limit: int = 20
) -> list[ExtensionReportEdit]:
    share_ids = select(ExtensionReportShare.id).where(
        ExtensionReportShare.client_key_id == (client_key.id if client_key else None)
    )
    stale_before = utcnow() - timedelta(minutes=10)
    rows = db.scalars(
        select(ExtensionReportEdit)
        .where(
            ExtensionReportEdit.share_id.in_(share_ids),
            or_(
                ExtensionReportEdit.status == "PENDING",
                (ExtensionReportEdit.status == "PROCESSING")
                & (ExtensionReportEdit.claimed_at < stale_before),
            ),
        )
        .order_by(ExtensionReportEdit.id.asc())
        .limit(limit)
    ).all()
    now = utcnow()
    for row in rows:
        row.status = "PROCESSING"
        row.claimed_at = now
    db.commit()
    return rows


def finish_edit(
    db: Session,
    *,
    public_id: str,
    ok: bool,
    message: str,
    client_key: ExtensionClientKey | None,
) -> ExtensionReportEdit:
    row = db.scalar(
        select(ExtensionReportEdit)
        .join(ExtensionReportShare, ExtensionReportShare.id == ExtensionReportEdit.share_id)
        .where(
            ExtensionReportEdit.public_id == public_id,
            ExtensionReportShare.client_key_id == (client_key.id if client_key else None),
        )
    )
    if row is None:
        raise LookupError("Không tìm thấy lệnh chỉnh sửa.")
    target_status = "COMPLETED" if ok else "FAILED"
    if row.status in {"COMPLETED", "FAILED"}:
        if row.status != target_status:
            raise ValueError("Lệnh đã có kết quả cuối khác với báo cáo mới.")
        return row
    row.status = target_status
    row.result_message = message[:2000]
    row.completed_at = utcnow()
    db.commit()
    return row


async def generate_ai_comments(mode: str, caption: str, count: int) -> list[str]:
    if not settings.ai_api_url or not settings.ai_api_key or not settings.ai_model:
        raise MetaOsIntegrationUnavailable("Chưa cấu hình AI cho metaOs.")
    prompt = (
        "Viết nội dung Facebook ngắn, tự nhiên, không spam. "
        f"Chế độ: {mode}. Số lượng: {count}. Ngữ cảnh: {caption}"
    )
    headers = {"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": settings.ai_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(settings.ai_api_url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    text = str((((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")).strip()
    comments = [line.strip(" -•\t") for line in text.splitlines() if line.strip()]
    return comments[:count]


async def send_zalo_notification(message: str) -> None:
    if not settings.zalo_notify_url:
        raise MetaOsIntegrationUnavailable("Chưa cấu hình webhook thông báo Zalo.")
    headers = {"Content-Type": "application/json"}
    if settings.zalo_notify_token:
        headers["Authorization"] = f"Bearer {settings.zalo_notify_token}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(settings.zalo_notify_url, headers=headers, json={"message": message})
    response.raise_for_status()
