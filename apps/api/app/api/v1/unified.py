"""API Tổng hợp Đa nền tảng (Unified Platform Aggregator) & Quản lý Tác vụ Khách hàng."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.local_admin import require_local_admin
from app.db import get_db
from app.models.ad_account import AdAccount
from app.models.campaign import Campaign
from app.models.client_task import (
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PENDING,
    ClientTask,
)
from app.models.customer import Customer, utcnow
from app.models.exchange import (
    EXCH_PROVIDER_BINANCE,
    EXCH_PROVIDER_PINGPONG,
    EXCH_STATUS_ACTIVE,
    ExchangeBalanceSnapshot,
    ExchangeCardSnapshot,
    ExchangeConnection,
)
from app.models.finance import AuditLog
from app.models.meta_risk import MetaAccountRisk
from app.models.sheet_reports import SheetReportSource
from app.models.telegram import AutomationRule, TelegramBotConfig
from app.services.task_dispatcher import TASK_TYPE_LABELS

router = APIRouter(prefix="/unified", tags=["hop-nhat-he-thong"], dependencies=[Depends(require_local_admin)])


# -----------------------------------------------------------------------------
# 1. OVERVIEW & TELEMETRY
# -----------------------------------------------------------------------------


@router.get("/overview")
def get_unified_overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Tổng hợp trạng thái toàn bộ kết nối nền tảng (Meta, Binance, PingPong, TRON, Sheets, Telegram) và các chỉ số vận hành chính."""
    # 1. Meta Ads Status & Health
    if settings.meta_access_token:
        meta_mode = "LIVE"
    elif settings.app_env in ("local", "test"):
        meta_mode = "MOCK"
    else:
        meta_mode = "UNCONFIGURED"

    has_meta_risk_error = db.scalar(
        select(MetaAccountRisk).where(MetaAccountRisk.data_status == "API_ERROR").limit(1)
    ) is not None
    if has_meta_risk_error:
        meta_health = "ERROR"
    elif meta_mode == "UNCONFIGURED":
        meta_health = "DEGRADED"
    else:
        meta_health = "HEALTHY"

    # 2. Exchange Connections (Binance & PingPong)
    binance_conn = db.scalar(
        select(ExchangeConnection).where(
            ExchangeConnection.provider == EXCH_PROVIDER_BINANCE,
            ExchangeConnection.status == EXCH_STATUS_ACTIVE,
        )
    )
    if binance_conn:
        binance_mode = "LIVE"
        if binance_conn.last_error:
            binance_health = "ERROR"
        elif binance_conn.read_only_verified and binance_conn.last_ok_at:
            binance_health = "HEALTHY"
        else:
            binance_health = "DEGRADED"
    else:
        binance_mode = "UNCONFIGURED"
        binance_health = "UNCONFIGURED"

    pingpong_conn = db.scalar(
        select(ExchangeConnection).where(
            ExchangeConnection.provider == EXCH_PROVIDER_PINGPONG,
            ExchangeConnection.status == EXCH_STATUS_ACTIVE,
        )
    )
    if pingpong_conn:
        pingpong_mode = "LIVE"
        if pingpong_conn.last_error:
            pingpong_health = "ERROR"
        elif pingpong_conn.read_only_verified and pingpong_conn.last_ok_at:
            pingpong_health = "HEALTHY"
        else:
            pingpong_health = "DEGRADED"
    else:
        pingpong_mode = "UNCONFIGURED"
        pingpong_health = "UNCONFIGURED"

    # 3. TRON Wallet
    tron_addr = getattr(settings, "tron_wallet_address", None)
    tron_configured = bool(tron_addr)
    tron_mode = "LIVE" if tron_configured else "UNCONFIGURED"
    tron_health = "HEALTHY" if tron_configured else "UNCONFIGURED"

    # 4. Google Sheets Sources
    sheets_count = db.scalar(select(func.count(SheetReportSource.id)).where(SheetReportSource.active.is_(True))) or 0
    sheets_mode = "LIVE" if bool(settings.google_sheets_spreadsheet_id) else ("MOCK" if sheets_count > 0 or settings.app_env in ("local", "test") else "UNCONFIGURED")
    sheets_health = "HEALTHY" if (sheets_count > 0 or bool(settings.google_sheets_spreadsheet_id)) else "UNCONFIGURED"

    # 5. Telegram Bot
    tg_config = db.scalar(select(TelegramBotConfig).order_by(TelegramBotConfig.id.desc()).limit(1))
    tg_configured = bool(tg_config and tg_config.encrypted_bot_token) or bool(settings.telegram_bot_token)
    tg_mode = "LIVE" if tg_configured else ("MOCK" if settings.app_env in ("local", "test") else "UNCONFIGURED")
    tg_health = "HEALTHY" if (tg_configured or tg_mode == "MOCK") else "UNCONFIGURED"
    active_rules_count = db.scalar(select(func.count(AutomationRule.id)).where(AutomationRule.is_enabled.is_(True))) or 0

    # 6. Ad Accounts & Campaigns Count
    total_accounts = db.scalar(select(func.count(AdAccount.id))) or 0
    total_campaigns = db.scalar(select(func.count(Campaign.id))) or 0
    pending_tasks = db.scalar(select(func.count(ClientTask.id)).where(ClientTask.status == TASK_STATUS_PENDING)) or 0

    return {
        "timestamp": utcnow().isoformat(),
        "platform_mode": settings.app_env,
        "connectors": {
            "meta_ads": {
                "name": "Meta Marketing API",
                "version": settings.meta_api_version,
                "mode": meta_mode.lower(),
                "mode_label": meta_mode,
                "status": meta_health,
                "health": meta_health,
            },
            "binance": {
                "name": "Binance Read-Only",
                "connected": binance_conn is not None,
                "mode": binance_mode.lower(),
                "mode_label": binance_mode,
                "status": binance_health,
                "health": binance_health,
                "label": binance_conn.label if binance_conn else None,
                "read_only_verified": bool(binance_conn.read_only_verified) if binance_conn else False,
                "last_ok_at": binance_conn.last_ok_at.isoformat() if binance_conn and binance_conn.last_ok_at else None,
            },
            "pingpong": {
                "name": "PingPong OpenAPI & VCC Cards",
                "connected": pingpong_conn is not None,
                "mode": pingpong_mode.lower(),
                "mode_label": pingpong_mode,
                "status": pingpong_health,
                "health": pingpong_health,
                "label": pingpong_conn.label if pingpong_conn else None,
                "read_only_verified": bool(pingpong_conn.read_only_verified) if pingpong_conn else False,
                "last_ok_at": pingpong_conn.last_ok_at.isoformat() if pingpong_conn and pingpong_conn.last_ok_at else None,
            },
            "tron": {
                "name": "TRON Blockchain USDT-TRC20",
                "configured": tron_configured,
                "mode": tron_mode.lower(),
                "mode_label": tron_mode,
                "status": tron_health,
                "health": tron_health,
                "address": f"{tron_addr[:6]}...{tron_addr[-4:]}" if tron_addr and len(tron_addr) > 10 else tron_addr,
            },
            "sheets": {
                "name": "Google Sheets Financial Reporting",
                "active_sources": sheets_count,
                "mode": sheets_mode.lower(),
                "mode_label": sheets_mode,
                "status": sheets_health,
                "health": sheets_health,
            },
            "telegram": {
                "name": "Telegram AI Assistant & Alert Bot",
                "configured": tg_configured,
                "mode": tg_mode.lower(),
                "mode_label": tg_mode,
                "status": tg_health,
                "health": tg_health,
                "active_rules": active_rules_count,
            },
        },
        "stats": {
            "total_ad_accounts": total_accounts,
            "total_campaigns": total_campaigns,
            "pending_client_tasks": pending_tasks,
        },
    }


# -----------------------------------------------------------------------------
# 2. UNIFIED TREASURY (SUB-50MS CACHED SNAPSHOT READ)
# -----------------------------------------------------------------------------


@router.get("/treasury")
def get_unified_treasury(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Tổng hợp số dư thanh khoản đa nguồn (Binance Spot/Funding, PingPong Multi-currency, VCC Cards, TRON USDT)."""
    # Lấy các connection sàn
    connections = db.scalars(select(ExchangeConnection).where(ExchangeConnection.status == EXCH_STATUS_ACTIVE)).all()

    treasury_sources: list[dict[str, Any]] = []
    total_usdt_estimate = Decimal("0")

    for conn in connections:
        # Tìm snapshot gần nhất
        latest_read_at = db.scalar(
            select(func.max(ExchangeBalanceSnapshot.read_at)).where(
                ExchangeBalanceSnapshot.connection_id == conn.id
            )
        )
        balances_list = []
        if latest_read_at:
            rows = db.scalars(
                select(ExchangeBalanceSnapshot).where(
                    ExchangeBalanceSnapshot.connection_id == conn.id,
                    ExchangeBalanceSnapshot.read_at == latest_read_at,
                )
            ).all()
            for r in rows:
                balances_list.append(
                    {
                        "wallet_type": r.wallet_type,
                        "asset": r.asset,
                        "free": str(r.free),
                        "locked": str(r.locked),
                        "total": str(r.free + r.locked),
                    }
                )
                if r.asset in ("USDT", "USD"):
                    total_usdt_estimate += (r.free + r.locked)

        # Lấy virtual cards nếu là PingPong
        cards_list = []
        if conn.provider == EXCH_PROVIDER_PINGPONG:
            latest_card_read_at = db.scalar(
                select(func.max(ExchangeCardSnapshot.read_at)).where(
                    ExchangeCardSnapshot.connection_id == conn.id
                )
            )
            if latest_card_read_at:
                card_rows = db.scalars(
                    select(ExchangeCardSnapshot).where(
                        ExchangeCardSnapshot.connection_id == conn.id,
                        ExchangeCardSnapshot.read_at == latest_card_read_at,
                    )
                ).all()
                for cr in card_rows:
                    cards_list.append(
                        {
                            "card_id": cr.card_id,
                            "card_label": cr.card_label,
                            "card_last4": cr.card_last4,
                            "currency": cr.currency,
                            "status": cr.status,
                            "spending_limit": str(cr.spending_limit) if cr.spending_limit else None,
                            "balance": str(cr.balance) if cr.balance else "0",
                        }
                    )
                    if cr.balance and cr.currency in ("USD", "USDT"):
                        total_usdt_estimate += cr.balance

        treasury_sources.append(
            {
                "id": conn.id,
                "provider": conn.provider,
                "label": conn.label,
                "last_checked_at": conn.last_checked_at.isoformat() if conn.last_checked_at else None,
                "balances": balances_list,
                "cards": cards_list,
            }
        )

    return {
        "total_liquid_usd_estimate": str(total_usdt_estimate),
        "sources": treasury_sources,
        "note": "Số liệu tổng hợp tức thời từ snapshot cơ sở dữ liệu (đáp ứng <50ms).",
    }


# -----------------------------------------------------------------------------
# 3. UNIFIED AD ACCOUNTS & HEALTH
# -----------------------------------------------------------------------------


@router.get("/accounts")
def get_unified_accounts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Tổng hợp danh sách tài khoản quảng cáo kèm trạng thái đặc cách, khóa khẩn cấp và nợ cước."""
    accounts = db.scalars(select(AdAccount).order_by(AdAccount.id)).all()
    results = []

    for acc in accounts:
        risk = db.get(MetaAccountRisk, acc.meta_ad_account_id)
        results.append(
            {
                "id": acc.id,
                "meta_ad_account_id": acc.meta_ad_account_id,
                "name": acc.name,
                "business_manager_id": acc.business_manager_id,
                "timezone_name": acc.timezone_name,
                "status": acc.status,
                "allow_violated_accounts": acc.allow_violated_accounts,
                "locked": bool(risk.locked) if risk else False,
                "risk_code": risk.risk_code if risk else "UNKNOWN",
                "debt": str(risk.debt) if risk and risk.debt is not None else "0",
                "currency": risk.currency if risk and risk.currency else "USD",
                "checked_at": risk.checked_at.isoformat() if risk and risk.checked_at else None,
            }
        )
    return results


# -----------------------------------------------------------------------------
# 4. CLIENT TASKS MANAGEMENT (KANBAN / TABLE)
# -----------------------------------------------------------------------------


class UpdateTaskStatusRequest(BaseModel):
    status: str = Field(..., description="PENDING, IN_PROGRESS, COMPLETED, CANCELLED")
    notes: Optional[str] = None
    assigned_to: Optional[str] = None
    actor: str = Field("web_ui", min_length=1)


class CreateTaskManualRequest(BaseModel):
    customer_id: Optional[int] = None
    telegram_chat_id: str = Field("manual", description="ID chat hoặc nguồn thủ công")
    sender_name: Optional[str] = None
    task_type: str = Field(..., description="ADD_MAIL_TO_BM, ADD_AD_ACCOUNT, SETTLE_DEBT, TOPUP_BUDGET, GENERAL_SUPPORT")
    raw_message: str = Field(..., min_length=1)
    extracted_data: Optional[dict[str, Any]] = None
    priority: str = Field(PRIORITY_NORMAL, description="LOW, NORMAL, HIGH, URGENT")
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


@router.get("/tasks")
def list_client_tasks(
    status: Optional[str] = Query(None, description="Lọc theo trạng thái: PENDING, IN_PROGRESS, COMPLETED, CANCELLED"),
    task_type: Optional[str] = Query(None, description="Lọc theo loại tác vụ"),
    customer_id: Optional[int] = Query(None, description="Lọc theo khách hàng"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lấy danh sách các tác vụ khách hàng gửi qua Telegram để hiển thị trên bảng điều khiển Kanban/Table."""
    stmt = select(ClientTask).order_by(desc(ClientTask.id))
    if status:
        stmt = stmt.where(ClientTask.status == status.upper())
    if task_type:
        stmt = stmt.where(ClientTask.task_type == task_type.upper())
    if customer_id:
        stmt = stmt.where(ClientTask.customer_id == customer_id)

    tasks = db.scalars(stmt).all()
    customers_map = {c.id: c.name for c in db.scalars(select(Customer)).all()}

    output = []
    for t in tasks:
        parsed_data = {}
        if t.extracted_data:
            try:
                parsed_data = json.loads(t.extracted_data)
            except Exception:
                parsed_data = {"raw": t.extracted_data}

        output.append(
            {
                "id": t.id,
                "customer_id": t.customer_id,
                "customer_name": customers_map.get(t.customer_id) if t.customer_id else None,
                "telegram_chat_id": t.telegram_chat_id,
                "telegram_username": t.telegram_username,
                "sender_name": t.sender_name,
                "task_type": t.task_type,
                "task_type_label": TASK_TYPE_LABELS.get(t.task_type, t.task_type),
                "raw_message": t.raw_message,
                "extracted_data": parsed_data,
                "status": t.status,
                "priority": t.priority,
                "assigned_to": t.assigned_to,
                "notes": t.notes,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
        )
    return output


@router.post("/tasks/{task_id}/status")
def update_client_task_status(
    task_id: int,
    req: UpdateTaskStatusRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật tiến độ hoặc hoàn tất tác vụ khách hàng."""
    task = db.get(ClientTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ.")

    valid_statuses = {TASK_STATUS_PENDING, TASK_STATUS_IN_PROGRESS, TASK_STATUS_COMPLETED, TASK_STATUS_CANCELLED}
    upper_status = req.status.upper()
    if upper_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Trạng thái không hợp lệ. Cho phép: {', '.join(valid_statuses)}")

    old_status = task.status
    task.status = upper_status
    if req.notes is not None:
        task.notes = req.notes.strip()
    if req.assigned_to is not None:
        task.assigned_to = req.assigned_to.strip()

    db.add(
        AuditLog(
            actor=req.actor,
            action="UPDATE_CLIENT_TASK_STATUS",
            entity_type="client_task",
            entity_id=str(task.id),
            detail={"old_status": old_status, "new_status": task.status, "assigned_to": task.assigned_to},
        )
    )
    db.commit()
    db.refresh(task)

    return {
        "id": task.id,
        "status": task.status,
        "assigned_to": task.assigned_to,
        "notes": task.notes,
        "message": f"Đã chuyển tác vụ #{task.id} sang trạng thái {task.status}.",
    }


@router.post("/tasks/create")
def create_client_task_manual(
    req: CreateTaskManualRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tạo tác vụ mới từ giao diện quản trị hoặc webhook ngoài."""
    if req.customer_id:
        cust = db.get(Customer, req.customer_id)
        if not cust:
            raise HTTPException(status_code=400, detail="Không tìm thấy khách hàng được chỉ định.")

    task = ClientTask(
        customer_id=req.customer_id,
        telegram_chat_id=req.telegram_chat_id,
        sender_name=req.sender_name,
        task_type=req.task_type.upper(),
        raw_message=req.raw_message.strip(),
        extracted_data=json.dumps(req.extracted_data or {}, ensure_ascii=False),
        status=TASK_STATUS_PENDING,
        priority=req.priority.upper(),
        assigned_to=req.assigned_to,
        notes=req.notes,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return {"id": task.id, "status": task.status, "message": f"Đã tạo tác vụ #{task.id} thành công."}
