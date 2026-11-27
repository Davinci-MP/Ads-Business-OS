"""Bộ công cụ STAFF_TOOLS dành riêng cho nhân viên trên Web CRM.

Chỉ được thực thi khi phiên người dùng đã xác thực nhân sự (StaffUser).
Mọi dữ liệu trả về đều phải được lọc qua Data Sanitizer trước khi tới LLM.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.ad_account import AdAccount, AdAccountAssignment
from app.models.campaign import Campaign
from app.models.customer import Customer
from app.models.prepaid import ClientBalance
from app.models.spend import DriftRecord, SpendSnapshot
from app.models.telegram import TelegramActivityLog
from app.models.via import ViaProfile
from app.services.ai.tools.base import ToolContext, ToolDefinition


def staff_get_system_overview(db: Session, context: ToolContext, **kwargs: Any) -> dict[str, Any]:
    """Lấy tổng quan tình hình toàn hệ thống: chi tiêu hôm nay, số chiến dịch, tài khoản và dàn VIA."""
    total_campaigns = db.scalar(select(func.count(Campaign.id))) or 0
    active_campaigns = db.scalar(select(func.count(Campaign.id)).where(Campaign.meta_status == "ACTIVE")) or 0
    total_accounts = db.scalar(select(func.count(AdAccount.id))) or 0
    active_accounts = db.scalar(select(func.count(AdAccount.id)).where(AdAccount.status == "ACTIVE")) or 0
    total_customers = db.scalar(select(func.count(Customer.id)).where(Customer.is_active == True)) or 0

    # Thống kê VIA theo trạng thái (chỉ đếm số lượng, tuyệt đối không đọc mật khẩu/cookie)
    via_stats: dict[str, int] = {}
    try:
        rows = db.execute(select(ViaProfile.status, func.count(ViaProfile.id)).group_by(ViaProfile.status)).all()
        for st, cnt in rows:
            via_stats[str(st or "UNKNOWN")] = cnt
    except Exception:
        via_stats = {"total": 0}

    # Chi tiêu tích lũy mới nhất từ snapshot
    latest_spend_sum = Decimal("0")
    try:
        subq = (
            select(
                SpendSnapshot.campaign_id,
                func.max(SpendSnapshot.snapshot_at).label("max_snap"),
            )
            .group_by(SpendSnapshot.campaign_id)
            .subquery()
        )
        stmt = (
            select(func.sum(SpendSnapshot.spend_amount))
            .join(
                subq,
                (SpendSnapshot.campaign_id == subq.c.campaign_id)
                & (SpendSnapshot.snapshot_at == subq.c.max_snap),
            )
        )
        res = db.scalar(stmt)
        if res is not None:
            latest_spend_sum = Decimal(str(res))
    except Exception:
        pass

    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_campaigns": total_campaigns,
        "active_campaigns": active_campaigns,
        "total_ad_accounts": total_accounts,
        "active_ad_accounts": active_accounts,
        "active_customers": total_customers,
        "total_verified_spend_vnd": float(latest_spend_sum),
        "via_profile_counts": via_stats,
    }


def staff_search_campaigns(
    db: Session,
    context: ToolContext,
    keyword: str = "",
    status: str = "",
    limit: int = 10,
    **kwargs: Any,
) -> dict[str, Any]:
    """Tìm kiếm danh sách chiến dịch theo từ khóa hoặc trạng thái."""
    query = select(Campaign)
    if keyword and keyword.strip():
        query = query.where(Campaign.name.ilike(f"%{keyword.strip()}%"))
    if status and status.strip():
        query = query.where(Campaign.meta_status == status.strip().upper())

    limit_val = min(max(1, limit), 25)
    campaigns = db.scalars(query.order_by(desc(Campaign.id)).limit(limit_val)).all()

    results = []
    for c in campaigns:
        # Lấy snapshot chi tiêu mới nhất
        latest_snap = db.execute(
            select(SpendSnapshot)
            .where(SpendSnapshot.campaign_id == c.id)
            .order_by(desc(SpendSnapshot.snapshot_at))
            .limit(1)
        ).scalar_one_or_none()

        drift_rec = db.execute(
            select(DriftRecord)
            .where(DriftRecord.campaign_id == c.id)
            .order_by(desc(DriftRecord.computed_at))
            .limit(1)
        ).scalar_one_or_none()

        results.append({
            "id": c.id,
            "meta_campaign_id": c.meta_campaign_id,
            "name": c.name,
            "status": c.meta_status,
            "ad_account_id": c.ad_account_id,
            "customer_id": c.customer_id,
            "latest_spend": float(latest_snap.spend_amount) if latest_snap else 0.0,
            "latest_drift": float(drift_rec.drift_amount) if drift_rec else 0.0,
        })

    return {
        "status": "success",
        "count": len(results),
        "campaigns": results,
    }


def staff_get_campaign_details(
    db: Session,
    context: ToolContext,
    campaign_id: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """Xem chi tiết số liệu, ngân sách và lịch sử một chiến dịch cụ thể."""
    c = db.get(Campaign, campaign_id)
    if not c:
        return {"status": "error", "message": f"Không tìm thấy chiến dịch id={campaign_id}"}

    customer_name = None
    if c.customer_id:
        cust = db.get(Customer, c.customer_id)
        if cust:
            customer_name = cust.name

    account_name = None
    act = db.get(AdAccount, c.ad_account_id)
    if act:
        account_name = act.name

    latest_snap = db.execute(
        select(SpendSnapshot)
        .where(SpendSnapshot.campaign_id == c.id)
        .order_by(desc(SpendSnapshot.snapshot_at))
        .limit(1)
    ).scalar_one_or_none()

    drift_rec = db.execute(
        select(DriftRecord)
        .where(DriftRecord.campaign_id == c.id)
        .order_by(desc(DriftRecord.computed_at))
        .limit(1)
    ).scalar_one_or_none()

    return {
        "status": "success",
        "id": c.id,
        "meta_campaign_id": c.meta_campaign_id,
        "name": c.name,
        "meta_status": c.meta_status,
        "recognition_status": c.recognition_status,
        "customer_id": c.customer_id,
        "customer_name": customer_name,
        "ad_account_id": c.ad_account_id,
        "ad_account_name": account_name,
        "latest_spend": float(latest_snap.spend_amount) if latest_snap else 0.0,
        "latest_drift": float(drift_rec.drift_amount) if drift_rec else 0.0,
        "snapshot_at": latest_snap.snapshot_at.isoformat() if latest_snap else None,
    }


def staff_get_customers_summary(
    db: Session,
    context: ToolContext,
    limit: int = 15,
    **kwargs: Any,
) -> dict[str, Any]:
    """Xem danh sách khách hàng, tỷ lệ phí dịch vụ, và số dư ví tạm ứng."""
    limit_val = min(max(1, limit), 50)
    customers = db.scalars(
        select(Customer)
        .where(Customer.is_active == True)
        .order_by(Customer.name)
        .limit(limit_val)
    ).all()

    results = []
    for cust in customers:
        balances = db.scalars(select(ClientBalance).where(ClientBalance.customer_id == cust.id)).all()
        bal_dict = {b.currency: float(b.amount) for b in balances}

        # Đếm số TKQC đang gán
        acc_count = db.scalar(
            select(func.count(AdAccountAssignment.id)).where(
                AdAccountAssignment.customer_id == cust.id,
                AdAccountAssignment.valid_to == None,
            )
        ) or 0

        results.append({
            "id": cust.id,
            "name": cust.name,
            "telegram_username": cust.telegram_username,
            "fee_rate_pct": float(cust.fee_rate * 100),
            "balances": bal_dict,
            "assigned_accounts_count": acc_count,
        })

    return {
        "status": "success",
        "count": len(results),
        "customers": results,
    }


def staff_get_ad_accounts(
    db: Session,
    context: ToolContext,
    status: str = "",
    limit: int = 15,
    **kwargs: Any,
) -> dict[str, Any]:
    """Tra cứu danh sách tài khoản quảng cáo và Business Manager."""
    query = select(AdAccount)
    if status and status.strip():
        query = query.where(AdAccount.status == status.strip().upper())

    limit_val = min(max(1, limit), 50)
    accounts = db.scalars(query.order_by(desc(AdAccount.id)).limit(limit_val)).all()

    return {
        "status": "success",
        "count": len(accounts),
        "ad_accounts": [
            {
                "id": a.id,
                "meta_ad_account_id": a.meta_ad_account_id,
                "name": a.name,
                "business_manager_id": a.business_manager_id,
                "timezone": a.timezone_name,
                "status": a.status,
            }
            for a in accounts
        ],
    }


def staff_get_vias_status(db: Session, context: ToolContext, **kwargs: Any) -> dict[str, Any]:
    """Tra cứu tình trạng dàn VIA Farm (an toàn: KHÔNG lộ mật khẩu, 2FA, token, hay cookie)."""
    try:
        rows = db.execute(select(ViaProfile.status, func.count(ViaProfile.id)).group_by(ViaProfile.status)).all()
        stats = {str(st or "UNKNOWN"): cnt for st, cnt in rows}
        total = sum(stats.values())
        return {
            "status": "success",
            "total_profiles": total,
            "by_status": stats,
            "security_note": "Tất cả credentials, mật khẩu và cookies đã được bảo vệ hoàn toàn.",
        }
    except Exception as exc:
        return {"status": "error", "message": f"Không thể đọc danh sách VIA: {str(exc)}"}


def staff_get_recent_activity_logs(
    db: Session,
    context: ToolContext,
    limit: int = 10,
    **kwargs: Any,
) -> dict[str, Any]:
    """Xem nhật ký tương tác bot và các lệnh gần nhất."""
    limit_val = min(max(1, limit), 20)
    logs = db.scalars(
        select(TelegramActivityLog).order_by(desc(TelegramActivityLog.id)).limit(limit_val)
    ).all()

    return {
        "status": "success",
        "count": len(logs),
        "logs": [
            {
                "id": l.id,
                "chat_id": l.chat_id,
                "username": l.username,
                "command": l.command,
                "status": l.status,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


# Danh mục các công cụ dành riêng cho Nhân viên CRM
STAFF_TOOLS: dict[str, ToolDefinition] = {
    "get_system_overview": ToolDefinition(
        name="get_system_overview",
        description="Lấy báo cáo tổng quan toàn hệ thống gồm chi tiêu hôm nay, số chiến dịch đang chạy, tài khoản và tình trạng dàn VIA.",
        parameters={"type": "object", "properties": {}},
        handler=staff_get_system_overview,
    ),
    "search_campaigns": ToolDefinition(
        name="search_campaigns",
        description="Tìm kiếm danh sách các chiến dịch quảng cáo theo từ khóa tên hoặc trạng thái (ACTIVE, PAUSED).",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Từ khóa tìm kiếm trong tên chiến dịch"},
                "status": {"type": "string", "description": "Trạng thái chiến dịch (ACTIVE, PAUSED)"},
                "limit": {"type": "integer", "description": "Số lượng tối đa cần lấy (mặc định 10)"},
            },
        },
        handler=staff_search_campaigns,
    ),
    "get_campaign_details": ToolDefinition(
        name="get_campaign_details",
        description="Lấy chi tiết chi tiêu, tiền trôi và thông số của một chiến dịch theo ID nội bộ.",
        parameters={
            "type": "object",
            "properties": {
                "campaign_id": {"type": "integer", "description": "ID nội bộ của chiến dịch"},
            },
            "required": ["campaign_id"],
        },
        handler=staff_get_campaign_details,
    ),
    "get_customers_summary": ToolDefinition(
        name="get_customers_summary",
        description="Lấy danh sách khách hàng, tỷ lệ phí dịch vụ, số dư ví nạp trước và số tài khoản QC đang gán.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Số lượng khách hàng tối đa cần xem"},
            },
        },
        handler=staff_get_customers_summary,
    ),
    "get_ad_accounts": ToolDefinition(
        name="get_ad_accounts",
        description="Tra cứu danh sách các tài khoản quảng cáo Meta và Business Manager tương ứng.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Lọc theo trạng thái tài khoản (ACTIVE, RESTRICTED)"},
                "limit": {"type": "integer", "description": "Số lượng tài khoản tối đa"},
            },
        },
        handler=staff_get_ad_accounts,
    ),
    "get_vias_status": ToolDefinition(
        name="get_vias_status",
        description="Xem thống kê tổng quan dàn VIA profiles theo các trạng thái (LIVE, CHECKPOINT, RESTRICTED). Không bao giờ lộ mật khẩu hay cookie.",
        parameters={"type": "object", "properties": {}},
        handler=staff_get_vias_status,
    ),
    "get_recent_activity_logs": ToolDefinition(
        name="get_recent_activity_logs",
        description="Xem nhật ký tương tác và các lệnh gần đây trên hệ thống.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Số dòng nhật ký tối đa (mặc định 10)"},
            },
        },
        handler=staff_get_recent_activity_logs,
    ),
}
