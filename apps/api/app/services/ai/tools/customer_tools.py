"""Bộ công cụ CUSTOMER_TOOLS dành riêng cho Khách hàng trên Telegram.

QUY TẮC BẢO MẬT BẮT BUỘC (REQ-3):
- Khóa cứng tuyệt đối theo telegram_chat_id / customer_id của người gửi.
- Khách hàng KHÔNG THỂ xem hoặc can thiệp vào tài khoản, chiến dịch, hay số dư của khách khác.
- Lọc bỏ triệt để mọi thông tin nhạy cảm.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ad_account import AdAccount, AdAccountAssignment
from app.models.campaign import Campaign
from app.models.client_task import ClientTask, TASK_STATUS_PENDING
from app.models.customer import Customer
from app.models.prepaid import ClientBalance
from app.models.spend import DriftRecord, SpendSnapshot
from app.services.ai.tools.base import ToolContext, ToolDefinition


def _assert_verified_customer(context: ToolContext) -> int:
    """Kiểm tra và trả về customer_id đã được xác thực an toàn. Ngăn chặn tuyệt đối truy cập chéo."""
    if not context.customer_id:
        raise PermissionError(
            "Tài khoản Telegram của bạn chưa được liên kết với khách hàng nào trong hệ thống. "
            "Vui lòng liên hệ Admin để hoàn tất cấu hình."
        )
    return context.customer_id


def customer_get_my_balance(db: Session, context: ToolContext, **kwargs: Any) -> dict[str, Any]:
    """Tra cứu số dư ví nạp trước của chính khách hàng hiện tại."""
    try:
        cust_id = _assert_verified_customer(context)
    except PermissionError as exc:
        return {"status": "unauthorized", "message": str(exc)}

    balances = db.scalars(select(ClientBalance).where(ClientBalance.customer_id == cust_id)).all()
    if not balances:
        return {
            "status": "success",
            "customer_name": context.customer_name,
            "balances": [],
            "message": "Bạn chưa có số dư ví tạm ứng trong hệ thống.",
        }

    bal_list = [
        {
            "currency": b.currency,
            "amount": float(b.amount),
            "deposit_info": b.deposit_info or "",
        }
        for b in balances
    ]

    return {
        "status": "success",
        "customer_name": context.customer_name,
        "balances": bal_list,
    }


def customer_get_my_campaigns(
    db: Session,
    context: ToolContext,
    status: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Xem danh sách các chiến dịch quảng cáo thuộc về khách hàng hiện tại."""
    try:
        cust_id = _assert_verified_customer(context)
    except PermissionError as exc:
        return {"status": "unauthorized", "message": str(exc)}

    # Lấy các TKQC mà khách hàng đang được gán
    assigned_acc_ids = db.scalars(
        select(AdAccountAssignment.ad_account_id).where(
            AdAccountAssignment.customer_id == cust_id,
            AdAccountAssignment.valid_to == None,
        )
    ).all()

    query = select(Campaign).where(
        (Campaign.customer_id == cust_id) | (Campaign.ad_account_id.in_(assigned_acc_ids))
    )
    if status and status.strip():
        query = query.where(Campaign.meta_status == status.strip().upper())

    campaigns = db.scalars(query.order_by(desc(Campaign.id)).limit(20)).all()

    camp_list = []
    for c in campaigns:
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

        camp_list.append({
            "campaign_id": c.id,
            "name": c.name,
            "status": c.meta_status,
            "spend": float(latest_snap.spend_amount) if latest_snap else 0.0,
            "drift": float(drift_rec.drift_amount) if drift_rec else 0.0,
        })

    return {
        "status": "success",
        "customer_name": context.customer_name,
        "total_campaigns": len(camp_list),
        "campaigns": camp_list,
    }


def customer_get_my_ad_accounts(db: Session, context: ToolContext, **kwargs: Any) -> dict[str, Any]:
    """Xem các tài khoản quảng cáo Meta được phân bổ cho khách hàng này."""
    try:
        cust_id = _assert_verified_customer(context)
    except PermissionError as exc:
        return {"status": "unauthorized", "message": str(exc)}

    assignments = db.scalars(
        select(AdAccountAssignment).where(
            AdAccountAssignment.customer_id == cust_id,
            AdAccountAssignment.valid_to == None,
        )
    ).all()

    acc_list = []
    for asgn in assignments:
        acc = db.get(AdAccount, asgn.ad_account_id)
        if acc:
            acc_list.append({
                "account_id": acc.id,
                "meta_ad_account_id": acc.meta_ad_account_id,
                "name": acc.name,
                "status": acc.status,
            })

    return {
        "status": "success",
        "customer_name": context.customer_name,
        "total_accounts": len(acc_list),
        "accounts": acc_list,
    }


def customer_get_my_support_tasks(
    db: Session,
    context: ToolContext,
    limit: int = 5,
    **kwargs: Any,
) -> dict[str, Any]:
    """Xem các yêu cầu hỗ trợ hoặc nạp tiền gần nhất mà khách hàng đã gửi."""
    try:
        cust_id = _assert_verified_customer(context)
    except PermissionError as exc:
        return {"status": "unauthorized", "message": str(exc)}

    limit_val = min(max(1, limit), 10)
    tasks = db.scalars(
        select(ClientTask)
        .where(ClientTask.customer_id == cust_id)
        .order_by(desc(ClientTask.id))
        .limit(limit_val)
    ).all()

    return {
        "status": "success",
        "customer_name": context.customer_name,
        "tasks": [
            {
                "task_id": t.id,
                "type": t.task_type,
                "status": t.status,
                "priority": t.priority,
                "raw_message": t.raw_message,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
    }


def customer_create_support_request(
    db: Session,
    context: ToolContext,
    task_type: str = "GENERAL_SUPPORT",
    details: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Tạo một yêu cầu hỗ trợ mới (nạp ngân sách, cấp tài khoản QC, mời mail vào BM)."""
    try:
        cust_id = _assert_verified_customer(context)
    except PermissionError as exc:
        return {"status": "unauthorized", "message": str(exc)}

    clean_type = task_type.strip().upper() if task_type else "GENERAL_SUPPORT"
    clean_details = details.strip() if details else "Yêu cầu hỗ trợ từ khách hàng qua AI Copilot"

    new_task = ClientTask(
        customer_id=cust_id,
        telegram_chat_id=context.telegram_chat_id or "",
        sender_name=context.customer_name,
        task_type=clean_type,
        raw_message=clean_details,
        extracted_data=json.dumps({"source": "ai_copilot_customer"}, ensure_ascii=False),
        status=TASK_STATUS_PENDING,
        priority="NORMAL",
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return {
        "status": "success",
        "task_id": new_task.id,
        "task_type": new_task.task_type,
        "message": f"Đã tạo thành công phiếu yêu cầu #{new_task.id}. Đội ngũ hỗ trợ sẽ xử lý ngay!",
    }


def customer_get_deposit_instructions(db: Session, context: ToolContext, **kwargs: Any) -> dict[str, Any]:
    """Lấy thông tin tài khoản chuyển khoản nạp ngân sách hoặc địa chỉ ví USDT."""
    try:
        _assert_verified_customer(context)
    except PermissionError as exc:
        return {"status": "unauthorized", "message": str(exc)}

    tron_wallet = getattr(settings, "tron_wallet_address", "")
    cust_ref = f"NAP ADS {context.customer_id or ''}".strip()

    return {
        "status": "success",
        "customer_name": context.customer_name,
        "transfer_syntax": cust_ref,
        "usdt_trc20_address": tron_wallet or "Liên hệ admin để nhận ví USDT riêng",
        "instructions": (
            f"Vui lòng ghi nội dung chuyển khoản là '{cust_ref}' để hệ thống tự động cộng số dư "
            "hoặc gửi ảnh biên lai giao dịch vào đây để được xử lý nhanh nhất."
        ),
    }


# Danh mục các công cụ dành cho Khách hàng trên Telegram
CUSTOMER_TOOLS: dict[str, ToolDefinition] = {
    "get_my_balance": ToolDefinition(
        name="get_my_balance",
        description="Tra cứu số dư ví nạp trước (VND, USDT) của chính khách hàng hiện tại.",
        parameters={"type": "object", "properties": {}},
        handler=customer_get_my_balance,
    ),
    "get_my_campaigns": ToolDefinition(
        name="get_my_campaigns",
        description="Xem danh sách chiến dịch quảng cáo và chi tiêu thuộc về các tài khoản của khách hàng này.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Lọc theo trạng thái chiến dịch (ACTIVE, PAUSED)"},
            },
        },
        handler=customer_get_my_campaigns,
    ),
    "get_my_ad_accounts": ToolDefinition(
        name="get_my_ad_accounts",
        description="Xem danh sách tài khoản quảng cáo được cấp cho khách hàng.",
        parameters={"type": "object", "properties": {}},
        handler=customer_get_my_ad_accounts,
    ),
    "get_my_support_tasks": ToolDefinition(
        name="get_my_support_tasks",
        description="Tra cứu tiến độ và trạng thái các phiếu yêu cầu hỗ trợ mà khách hàng đã gửi.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Số lượng phiếu hỗ trợ cần xem (mặc định 5)"},
            },
        },
        handler=customer_get_my_support_tasks,
    ),
    "create_support_request": ToolDefinition(
        name="create_support_request",
        description="Tạo một yêu cầu hỗ trợ mới gửi cho đội ngũ vận hành (nạp ngân sách, cấp tài khoản, kỹ thuật).",
        parameters={
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "description": "Loại tác vụ: TOPUP_BUDGET, ADD_AD_ACCOUNT, ADD_MAIL_TO_BM, GENERAL_SUPPORT",
                },
                "details": {"type": "string", "description": "Nội dung chi tiết yêu cầu"},
            },
            "required": ["details"],
        },
        handler=customer_create_support_request,
    ),
    "get_deposit_instructions": ToolDefinition(
        name="get_deposit_instructions",
        description="Lấy thông tin chuyển khoản ngân hàng và địa chỉ ví USDT kèm cú pháp nạp tiền chính xác.",
        parameters={"type": "object", "properties": {}},
        handler=customer_get_deposit_instructions,
    ),
}
