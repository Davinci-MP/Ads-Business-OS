"""Biên tương thích cho campaign write: chỉ xếp lệnh, không gọi Meta từ backend."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.meta import MetaAdsConnector
from app.core.config import settings
from app.models.ad_account import AdAccount
from app.models.campaign import Campaign
from app.models.finance import AuditLog
from app.models.meta_tasks import MetaCampaignTask
from app.services.meta_risk import assert_account_unlocked
from app.services.meta_account_policy import validate_account_policy
from app.services.remote_commands import enqueue_extension_command, serialize_command


class CampaignCreationRequest(BaseModel):
    ad_account_id: str = Field(..., description="ID tài khoản quảng cáo (dạng act_xxxx hoặc xxxx)")
    campaign_name: str = Field(..., min_length=3, max_length=255, description="Tên chiến dịch")
    objective: str = Field("OUTCOME_LEADS", description="Mục tiêu chiến dịch")
    daily_budget: Decimal = Field(..., gt=0, description="Ngân sách ngày")
    page_id: Optional[str] = None
    post_id: Optional[str] = None
    object_story_id: Optional[str] = None
    adset_name: Optional[str] = None
    ad_name: Optional[str] = None
    optimization_goal: Optional[str] = None
    target_countries: list[str] = Field(default_factory=lambda: ["VN"])
    age_min: int = Field(18, ge=18, le=65)
    age_max: int = Field(65, ge=18, le=65)
    created_by: str = Field("telegram_bot")
    status: Optional[str] = Field("PAUSED", description="Trạng thái chiến dịch (ACTIVE hoặc PAUSED per D-065)")


def normalize_ad_account_id(account_id: str) -> str:
    value = account_id.strip()
    return value if value.startswith("act_") else f"act_{value}"


def validate_budget_cap(daily_budget: Decimal) -> None:
    max_budget = Decimal(str(settings.meta_max_daily_budget))
    if daily_budget > max_budget:
        raise ValueError(
            f"Ngân sách ngày {daily_budget:,.0f} vượt quá hạn mức an toàn tối đa "
            f"({max_budget:,.0f})."
        )


def build_and_create_campaign(
    session: Session,
    connector: MetaAdsConnector,
    req: CampaignCreationRequest,
) -> dict[str, Any]:
    """Tên hàm cũ được giữ để tương thích; hành vi mới chỉ enqueue cho Extension."""
    validate_budget_cap(req.daily_budget)
    act_id = normalize_ad_account_id(req.ad_account_id)
    assert_account_unlocked(session, act_id)
    validate_account_policy(session, connector, act_id)
    target_status = (getattr(req, "status", None) or "PAUSED").upper()
    if target_status not in ("ACTIVE", "PAUSED"):
        target_status = "PAUSED"
    payload = req.model_dump(mode="json")
    payload["status"] = target_status
    command = enqueue_extension_command(
        session,
        act_id=act_id,
        command_type="SET_CAMP",
        payload=payload,
        requested_by=req.created_by,
    )
    session.add(
        AuditLog(
            actor=req.created_by,
            action="QUEUE_META_CAMPAIGN_CREATE",
            entity_type="remote_via_command",
            entity_id=command.public_id or str(command.id),
            detail={"ad_account_id": act_id, "campaign_name": req.campaign_name, "status": target_status},
        )
    )
    session.commit()
    return {
        "success": True,
        "task_id": command.id,
        "command": serialize_command(command),
        "ad_account_id": act_id,
        "campaign_name": req.campaign_name,
        "status": "PENDING",
        "target_status": target_status,
        "message": f"Đã xếp lệnh tạo chiến dịch {target_status} để Chrome Extension xử lý.",
    }


def toggle_campaign_status(
    session: Session,
    connector: MetaAdsConnector,
    meta_campaign_id: str,
    new_status: str,
    actor: str = "telegram_bot",
) -> dict[str, Any]:
    """Xếp lệnh đổi trạng thái cho Extension; backend tuyệt đối không POST Meta."""
    status = new_status.upper()
    if status not in {"ACTIVE", "PAUSED"}:
        raise ValueError("Trạng thái chỉ có thể là ACTIVE hoặc PAUSED.")

    campaign = session.scalar(select(Campaign).where(Campaign.meta_campaign_id == meta_campaign_id))
    account = session.get(AdAccount, campaign.ad_account_id) if campaign else None
    account_id = account.meta_ad_account_id if account else None
    if account_id is None:
        prior_task = session.scalar(
            select(MetaCampaignTask).where(MetaCampaignTask.meta_campaign_id == meta_campaign_id)
        )
        account_id = prior_task.ad_account_id if prior_task else None
    if account_id is None:
        for candidate in connector.get_ad_accounts():
            candidate_id = candidate.get("meta_ad_account_id")
            if not candidate_id:
                continue
            campaigns = connector.get_account_campaigns(candidate_id)
            if any(
                (item.get("meta_campaign_id") or item.get("id")) == meta_campaign_id
                for item in campaigns
            ):
                account_id = candidate_id
                break
    if not account_id:
        raise ValueError("Chưa xác minh được tài khoản sở hữu chiến dịch; không thể xếp lệnh.")
    if status == "ACTIVE":
        assert_account_unlocked(session, account_id)
        validate_account_policy(session, connector, account_id)

    command = enqueue_extension_command(
        session,
        act_id=account_id,
        command_type="SET_CAMPAIGN_STATUS",
        payload={"campaign_id": meta_campaign_id, "status": status},
        customer_id=campaign.customer_id if campaign else None,
        requested_by=actor,
    )
    session.add(
        AuditLog(
            actor=actor,
            action=f"QUEUE_CAMPAIGN_{status}",
            entity_type="remote_via_command",
            entity_id=command.public_id or str(command.id),
            detail={"campaign_id": meta_campaign_id, "target_status": status},
        )
    )
    session.commit()
    return {
        "success": True,
        "meta_campaign_id": meta_campaign_id,
        "status": "PENDING",
        "target_status": status,
        "command": serialize_command(command),
        "message": "Đã xếp lệnh đổi trạng thái để Chrome Extension xử lý.",
    }
