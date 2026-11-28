"""API endpoints cho quản lý tài khoản Meta Ads và Controlled Campaign Pipeline."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.connectors.meta import MetaAPIError, MetaAdsConnector
from app.db import get_db
from app.core.local_admin import require_local_admin_or_owner
from app.services.meta_account_policy import set_violation_override, validate_account_policy
from app.services.meta_risk import assert_account_unlocked
from app.models.meta_tasks import MetaCampaignTask
from app.models.ad_account import AdAccount
from app.models.campaign import Campaign
from app.models.meta_risk import MetaAccountRisk
from app.services.meta_campaign_builder import CampaignCreationRequest, validate_budget_cap
from app.services.remote_commands import enqueue_extension_command, serialize_command

router = APIRouter(prefix="/meta", tags=["meta-ads"], dependencies=[Depends(require_local_admin_or_owner)])


class ToggleStatusRequest(BaseModel):
    status: str = Field(..., description="Trạng thái mới: ACTIVE hoặc PAUSED")
    actor: str = Field("web_ui", description="Tác nhân thực hiện")


@router.get("/accounts/billing")
def get_accounts_billing_health(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Lấy danh sách tất cả tài khoản quảng cáo cùng thông số thanh toán, hạn mức và nhãn Tiếng Việt."""
    connector = MetaAdsConnector()
    try:
        accounts = connector.get_ad_accounts()
        results = []
        for acc in accounts:
            act_id = acc["meta_ad_account_id"]
            health = connector.get_ad_account_billing_health(act_id)
            db_acc = db.scalar(select(AdAccount).where(AdAccount.meta_ad_account_id == act_id))
            db_risk = db.get(MetaAccountRisk, act_id)
            health["allow_violated_accounts"] = bool(db_acc.allow_violated_accounts) if db_acc else False
            health["locked"] = bool(db_risk.locked) if db_risk else False
            health["risk_code"] = db_risk.risk_code if db_risk else "UNKNOWN"
            results.append(health)
        return results
    except MetaAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Lỗi kết nối Meta Marketing API: {str(exc)}")


@router.get("/accounts/{account_id}/insights")
def get_account_insights(
    account_id: str,
    db: Session = Depends(get_db),
    date_preset: str = Query("today", description="today, yesterday, last_7d, this_month"),
) -> list[dict[str, Any]]:
    """Lấy báo cáo hiệu suất chi tiết của tài khoản."""
    connector = MetaAdsConnector()
    try:
        act_id = account_id if account_id.startswith("act_") else f"act_{account_id}"
        validate_account_policy(db, connector, act_id)
        return connector.get_performance_insights(act_id, date_preset=date_preset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except MetaAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Lỗi khi lấy chỉ số hiệu suất: {str(exc)}")


@router.get("/telemetry")
def get_meta_telemetry() -> dict[str, Any]:
    """Lấy thông số telemetry giới hạn cuộc gọi (Rate-limit) hiện thời."""
    connector = MetaAdsConnector()
    return connector.telemetry.to_dict()


@router.post("/campaigns/create")
def create_campaign_endpoint(
    req: CampaignCreationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Chỉ xếp lệnh tạo campaign PAUSED; backend không gọi Meta write API."""
    try:
        validate_budget_cap(req.daily_budget)
        assert_account_unlocked(db, req.ad_account_id)
        with MetaAdsConnector() as connector:
            validate_account_policy(db, connector, req.ad_account_id)
        payload = req.model_dump(mode="json")
        payload["status"] = "PAUSED"
        command = enqueue_extension_command(
            db,
            act_id=req.ad_account_id,
            command_type="SET_CAMP",
            payload=payload,
            requested_by=req.created_by,
        )
        return {
            "success": True,
            "status": "PENDING",
            "message": "Đã xếp lệnh tạo chiến dịch PAUSED để Chrome Extension xử lý.",
            "command": serialize_command(command),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/campaigns/{campaign_id}/status")
def toggle_campaign_endpoint(
    campaign_id: str,
    body: ToggleStatusRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Chỉ xếp lệnh đổi trạng thái; backend không gọi Meta write API."""
    target_status = body.status.upper()
    if target_status not in {"ACTIVE", "PAUSED"}:
        raise HTTPException(status_code=400, detail="Trạng thái chỉ được là ACTIVE hoặc PAUSED.")
    campaign = db.scalar(select(Campaign).where(Campaign.meta_campaign_id == campaign_id))
    account = db.get(AdAccount, campaign.ad_account_id) if campaign else None
    if account is None:
        raise HTTPException(status_code=409, detail="Không xác định được tài khoản quảng cáo của chiến dịch.")
    if target_status == "ACTIVE":
        try:
            assert_account_unlocked(db, account.meta_ad_account_id)
            with MetaAdsConnector() as connector:
                validate_account_policy(db, connector, account.meta_ad_account_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    command = enqueue_extension_command(
        db,
        act_id=account.meta_ad_account_id,
        command_type="SET_CAMPAIGN_STATUS",
        payload={"campaign_id": campaign_id, "status": target_status},
        customer_id=campaign.customer_id,
        requested_by=body.actor,
    )
    return {
        "success": True,
        "status": "PENDING",
        "message": "Đã xếp lệnh đổi trạng thái để Chrome Extension xử lý.",
        "command": serialize_command(command),
    }


@router.get("/campaigns/tasks")
def list_campaign_tasks(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lấy lịch sử các tác vụ tạo chiến dịch tự động."""
    stmt = select(MetaCampaignTask).order_by(desc(MetaCampaignTask.id)).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": r.id,
            "ad_account_id": r.ad_account_id,
            "campaign_name": r.campaign_name,
            "objective": r.objective,
            "daily_budget": float(r.daily_budget),
            "status": r.status,
            "meta_campaign_id": r.meta_campaign_id,
            "meta_adset_id": r.meta_adset_id,
            "meta_ad_id": r.meta_ad_id,
            "error_message": r.error_message,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


class ViolationOverrideRequest(BaseModel):
    enabled: bool

@router.post("/accounts/{account_id}/violation-override")
def update_violation_override(account_id: str, body: ViolationOverrideRequest, db: Session = Depends(get_db)):
    try:
        account = set_violation_override(db, account_id, body.enabled)
        db.commit()
        return {"meta_ad_account_id": account.meta_ad_account_id, "allow_violated_accounts": account.allow_violated_accounts}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
