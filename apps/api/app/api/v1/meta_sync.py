"""REST endpoints cho Meta sync (S3, D-027).

Guard cứng:
- KHÔNG bao giờ trả token/secret trong response — chỉ trả `mode` (mock/live).
- Sync chỉ đọc Meta; không có hành động ghi Google Sheets ở đây (D-024/D-028).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.meta import MetaAPIError, build_connector
from app.db import get_db
from app.models import Campaign, SpendSnapshot
from app.models.campaign import RECOGNITION_CONFIRMED, RECOGNITION_UNRECOGNIZED
from app.models.spend import DriftRecord
from app.services.meta_sync import run_meta_sync

router = APIRouter(prefix="/meta-sync", tags=["meta-sync"])


@router.post("/run")
def run_sync(
    force_checkpoint_9h: bool = Query(False, description="Ghi snapshot đánh dấu mốc 09:00 (thường job hằng giờ tự phát hiện giờ VN)"),
    now: Optional[str] = Query(None, description="ISO datetime mô phỏng thời điểm chạy — CHỈ khi connector ở mock mode (kiểm thử checkpoint/tiền trôi deterministic); live sẽ bị chặn"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Chạy 1 lượt đồng bộ (idempotent). Connector tự mock khi chưa có token (D-027)."""
    connector = build_connector()
    run_now: Optional[datetime] = None
    if now:
        if connector.mode != "mock":
            raise HTTPException(status_code=400, detail="Tham số `now` chỉ cho phép khi connector ở mock mode")
        try:
            run_now = datetime.fromisoformat(now)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="`now` phải là ISO datetime (VD: 2026-10-26T02:00:00+00:00)") from exc
    try:
        summary = run_meta_sync(db, connector, now=run_now, force_checkpoint_9h=force_checkpoint_9h)
        db.commit()
    except MetaAPIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": connector.mode, "checkpoint_9h_run": force_checkpoint_9h, **summary}


@router.get("/mode")
def connector_mode() -> dict[str, str]:
    connector = build_connector()
    return {"mode": connector.mode}


@router.get("/check")
def check_access() -> dict[str, Any]:
    """S16: kiểm tra Meta token (hiệu lực + quyền ads_read + account truy cập được) — GET-only, không fallback mock."""
    connector = build_connector()
    if connector.mode == "mock":
        raise HTTPException(
            status_code=400,
            detail=(
                "Chưa cấu hình Meta token (env ADSOS_META_ACCESS_TOKEN hoặc ADSOS_META_TOKEN_MAP) — "
                "xem hướng dẫn setup token trong docs; KHÔNG dán token vào chat"
            ),
        )
    try:
        return connector.check_access()
    except MetaAPIError as exc:
        status = 502
        if exc.status_code in (401, 403):
            status = 502  # giữ 502 tướng lỗi upstream; detail nêu rõ xác thực
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/campaigns")
def list_campaigns(
    status: Optional[str] = Query(None, description="CONFIRMED | UNRECOGNIZED"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = select(Campaign)
    if status == RECOGNITION_CONFIRMED:
        query = query.where(Campaign.recognition_status == RECOGNITION_CONFIRMED)
    elif status == RECOGNITION_UNRECOGNIZED:
        query = query.where(Campaign.recognition_status == RECOGNITION_UNRECOGNIZED)
    campaigns = db.execute(query.order_by(Campaign.id)).scalars().all()
    return [
        {
            "id": c.id,
            "meta_campaign_id": c.meta_campaign_id,
            "name": c.name,
            "ad_account_id": c.ad_account_id,
            "customer_id": c.customer_id,
            "recognition_status": c.recognition_status,
            "report_period_start": c.report_period_start.isoformat() if c.report_period_start else None,
            "report_period_end": c.report_period_end.isoformat() if c.report_period_end else None,
            "meta_status": c.meta_status,
        }
        for c in campaigns
    ]


@router.get("/snapshots")
def list_snapshots(
    meta_campaign_id: Optional[str] = None,
    latest_only: bool = Query(True, description="true = chỉ snapshot mới nhất VERIFIED của từng campaign"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    campaign_ids: dict[int, str] = {
        c.id: c.meta_campaign_id for c in db.execute(select(Campaign)).scalars().all()
    }
    query = select(SpendSnapshot).order_by(SpendSnapshot.snapshot_at.desc(), SpendSnapshot.id.desc())
    if meta_campaign_id:
        campaign = next((cid for cid, mid in campaign_ids.items() if mid == meta_campaign_id), None)
        if campaign is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy campaign")
        query = query.where(SpendSnapshot.campaign_id == campaign)
    rows = db.execute(query).scalars().all()
    if latest_only:
        seen: dict[int, SpendSnapshot] = {}
        for row in rows:  # đã sort desc theo thời gian rồi
            seen.setdefault(row.campaign_id, row)
        rows = list(seen.values())
    return [
        {
            "campaign_id": row.campaign_id,
            "meta_campaign_id": campaign_ids.get(row.campaign_id, str(row.campaign_id)),
            "snapshot_at": row.snapshot_at.isoformat(),
            "spend_amount": str(row.spend_amount),
            "currency": row.currency,
            "is_checkpoint_9h": row.is_checkpoint_9h,
            "data_status": row.data_status,
        }
        for row in rows
    ]


@router.get("/drift")
def list_drift(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Tiền trôi = chi tiêu hiện tại − chi tiêu mốc 09:00 (D-023)."""
    rows = db.execute(select(DriftRecord).order_by(DriftRecord.computed_at.desc())).scalars().all()
    return [
        {
            "campaign_id": row.campaign_id,
            "checkpoint_snapshot_id": row.checkpoint_snapshot_id,
            "latest_snapshot_id": row.latest_snapshot_id,
            "drift_amount": str(row.drift_amount),
            "currency": row.currency,
            "computed_at": row.computed_at.isoformat(),
        }
        for row in rows
    ]
