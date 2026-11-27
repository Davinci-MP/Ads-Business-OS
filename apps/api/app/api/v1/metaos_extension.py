"""API tương thích cho Chrome extension metaOs chạy trên Ads Business OS."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.extension_remote import ExtensionReportShare, ExtensionReportSnapshot
from app.services.metaos_extension import (
    MetaOsIntegrationUnavailable,
    append_snapshot,
    claim_pending_edits,
    create_edit,
    create_share,
    find_active_client_key,
    finish_edit,
    generate_ai_comments,
    heartbeat_shares,
    list_shares,
    send_zalo_notification,
    serialize_share,
    set_share_status,
)


router = APIRouter(tags=["metaOs Extension"])
STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "metaos"


def _is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    origin = request.headers.get("origin") or ""
    if host in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return True
    if origin:
        parsed = urlsplit(origin)
        return parsed.scheme == "chrome-extension" or parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    return False


def _base_url(request: Request) -> str:
    configured = settings.extension_public_base_url.strip().rstrip("/")
    return configured or str(request.base_url).rstrip("/")


def _require_client_key(request: Request, db: Session, supplied: str | None):
    key = find_active_client_key(db, supplied or request.headers.get("x-adsos-client-key"))
    if supplied and key is None:
        raise HTTPException(status_code=403, detail="Client Key của extension không hợp lệ.")
    if key is None and not _is_local(request):
        raise HTTPException(status_code=403, detail="Extension cần Client Key hợp lệ.")
    return key


class ShareCreateRequest(BaseModel):
    model_config = {"populate_by_name": True}

    key: str | None = None
    account_id: str = Field(alias="accountId", min_length=1, max_length=64)
    account_name: str = Field(default="", alias="accountName", max_length=255)
    currency: str = Field(default="", max_length=16)
    scope_type: Literal["account", "campaigns"] = Field(default="account", alias="scopeType")
    campaign_ids: list[str] = Field(default_factory=list, alias="campaignIds", max_length=500)


class KeyRequest(BaseModel):
    key: str | None = None


class SnapshotRequest(KeyRequest):
    id: str
    snapshot: dict[str, Any]


class EditCreateRequest(BaseModel):
    model_config = {"populate_by_name": True}

    key: str | None = None
    target_id: str = Field(alias="targetId", min_length=1, max_length=64)
    account_id: str = Field(alias="accountId", min_length=1, max_length=64)
    currency: str = Field(default="", max_length=16)
    action: Literal["toggle", "budget", "rename"]
    params: dict[str, Any] = Field(default_factory=dict)


class EditResultRequest(KeyRequest):
    editId: str
    ok: bool
    message: str = ""


class AiSeedingRequest(BaseModel):
    licenseKey: str | None = None
    mode: Literal["share", "comments"] = "comments"
    caption: str = Field(default="", max_length=1500)
    count: int = Field(default=1, ge=1, le=10)


class NotifyRequest(BaseModel):
    key: str | None = None
    message: str = Field(min_length=1, max_length=4000)


@router.get("/metaos")
def metaos_home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/popup")
def metaos_account_popup() -> FileResponse:
    return FileResponse(STATIC_DIR / "popup.html")


@router.get("/bm-popup.html")
def metaos_bm_popup() -> FileResponse:
    return FileResponse(STATIC_DIR / "bm-popup.html")


@router.get("/ext-runner")
def metaos_extension_runner() -> FileResponse:
    return FileResponse(STATIC_DIR / "ext-runner.html")


@router.get("/api/tenant-status")
def tenant_status(
    request: Request,
    key: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client_key = find_active_client_key(db, key)
    active = client_key is not None or (not key and _is_local(request))
    return {"active": active, "apiBase": _base_url(request), "brand": "metaOs"}


@router.get("/api/ext-shield")
def extension_shield() -> dict[str, Any]:
    return {
        "v": 1,
        "syncMin": 20,
        "graphVer": settings.meta_api_version,
        "graphVerPage": settings.meta_api_version,
    }


@router.post("/api/share")
def create_report_share(
    body: ShareCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    key = _require_client_key(request, db, body.key)
    row = create_share(
        db,
        client_key=key,
        account_id=body.account_id.strip().removeprefix("act_"),
        account_name=body.account_name.strip(),
        currency=body.currency.strip().upper(),
        scope_type=body.scope_type,
        campaign_ids=[str(item).strip() for item in body.campaign_ids if str(item).strip()],
    )
    return {"success": True, "item": serialize_share(row)}


@router.post("/api/share/{share_id}/status")
def update_report_share_status(
    share_id: str,
    status: Literal["active", "paused", "revoked"],
    request: Request,
    key: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client_key = _require_client_key(request, db, key)
    try:
        row = set_share_status(db, share_id, status, client_key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "item": serialize_share(row)}


@router.get("/api/share/list")
def report_share_list(
    request: Request,
    key: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client_key = _require_client_key(request, db, key)
    return {"success": True, "items": [serialize_share(row) for row in list_shares(db, client_key)]}


@router.post("/api/share/heartbeat")
def report_share_heartbeat(
    body: KeyRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client_key = _require_client_key(request, db, body.key)
    return {"success": True, "updated": heartbeat_shares(db, client_key)}


@router.post("/api/share/snapshot")
def report_share_snapshot(
    body: SnapshotRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client_key = _require_client_key(request, db, body.key)
    try:
        row, created = append_snapshot(
            db,
            share_public_id=body.id,
            snapshot=body.snapshot,
            client_key=client_key,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "snapshotId": row.id, "created": created}


@router.get("/api/share/pending")
def report_share_pending(
    request: Request,
    key: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client_key = _require_client_key(request, db, key)
    rows = claim_pending_edits(db, client_key)
    return {
        "success": True,
        "edits": [
            {
                "editId": row.public_id,
                "targetId": row.target_id,
                "accountId": row.account_id,
                "currency": row.currency,
                "action": row.action,
                "params": row.params or {},
            }
            for row in rows
        ],
    }


@router.post("/api/share/{share_id}/edits")
def queue_report_share_edit(
    share_id: str,
    body: EditCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not settings.meta_writes_enabled:
        raise HTTPException(status_code=403, detail="Meta writes đang tắt; chưa xếp lệnh chỉnh sửa.")
    client_key = _require_client_key(request, db, body.key)
    try:
        row = create_edit(
            db,
            share_public_id=share_id,
            target_id=body.target_id,
            account_id=body.account_id.removeprefix("act_"),
            currency=body.currency.upper(),
            action=body.action,
            params=body.params,
            client_key=client_key,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "editId": row.public_id, "status": row.status}


@router.post("/api/share/edit-result")
def report_share_edit_result(
    body: EditResultRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client_key = _require_client_key(request, db, body.key)
    try:
        row = finish_edit(
            db,
            public_id=body.editId,
            ok=body.ok,
            message=body.message,
            client_key=client_key,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "status": row.status}


@router.get("/api/share/{share_id}")
def public_report_share(share_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    share = db.scalar(select(ExtensionReportShare).where(ExtensionReportShare.public_id == share_id))
    if share is None or share.status == "revoked":
        raise HTTPException(status_code=404, detail="Không tìm thấy báo cáo.")
    snapshot = db.scalar(
        select(ExtensionReportSnapshot)
        .where(ExtensionReportSnapshot.share_id == share.id)
        .order_by(desc(ExtensionReportSnapshot.id))
    )
    return {"success": True, "item": serialize_share(share), "snapshot": snapshot.payload if snapshot else None}


@router.post("/api/ai/seeding")
async def ai_seeding(
    body: AiSeedingRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_client_key(request, db, body.licenseKey)
    try:
        comments = await generate_ai_comments(body.mode, body.caption, body.count)
    except MetaOsIntegrationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Nhà cung cấp AI không phản hồi.") from exc
    return {"ok": True, "comments": comments}


@router.post("/api/zalo/notify")
async def zalo_notify(
    body: NotifyRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_client_key(request, db, body.key)
    try:
        await send_zalo_notification(body.message)
    except MetaOsIntegrationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Webhook Zalo không phản hồi.") from exc
    return {"success": True}
