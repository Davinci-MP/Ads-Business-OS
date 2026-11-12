"""API endpoints cho Telegram Bot Agent quản trị, quy tắc tự động hóa và nhật ký hoạt động."""

from __future__ import annotations

from decimal import Decimal
import hmac
import secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.connectors.meta import decrypt_token_if_encrypted, encrypt_meta_token
from app.connectors.telegram import TelegramAPIError, TelegramBotConnector
from app.core.config import settings
from app.core.local_admin import require_local_admin
from app.db import get_db
from app.models.telegram import AutomationRule, TelegramActivityLog, TelegramBotConfig
from app.services.automation_rules import ensure_default_rules, evaluate_automation_rules
from app.services.telegram_bot import TelegramBotAgent, get_configured_telegram_connector

router = APIRouter(prefix="/telegram", tags=["telegram-bot"])

ADMIN_COMMANDS = {"/khoatkn", "/khoatk", "/set_bm", "/setbm", "/bm_pref"}


def require_telegram_admin(request: Request) -> None:
    """Yêu cầu quyền admin: hỗ trợ local loopback admin hoặc HTTP header x-admin-token."""
    admin_token = request.headers.get("x-admin-token") or request.headers.get("x-adsos-admin-token")
    if admin_token and getattr(settings, "exchange_admin_token", "") and len(settings.exchange_admin_token) >= 16:
        if secrets.compare_digest(admin_token, settings.exchange_admin_token):
            return
    require_local_admin(request)


# --- Schemas ---

class TestSendMessageRequest(BaseModel):
    message: str = Field(..., description="Nội dung tin nhắn cần gửi thử")
    chat_id: str | None = Field(None, description="Chat ID đích (mặc định gửi cho admin)")


class DispatchCommandRequest(BaseModel):
    command: str = Field(..., description="Lệnh cần điều phối (vd: /tk, /baocao, /lencamp...)")
    chat_id: str | int | None = Field(None, description="Chat ID người gửi (phải qua kiểm tra whitelist)")
    actor: str = Field("web_ui", description="Tên tác nhân thực hiện")


class UpdateBotConfigRequest(BaseModel):
    bot_token: Optional[str] = Field(None, description="Telegram Bot Token mới")
    admin_chat_id: Optional[str] = Field(None, description="Chat ID của Admin nhận thông báo")
    allowed_chat_ids: Optional[str] = Field(None, description="Danh sách Chat ID được phân quyền (phân tách bởi dấu phẩy)")
    webhook_url: Optional[str] = Field(None, description="URL Webhook tiếp nhận Telegram update")
    webhook_secret: Optional[str] = Field(None, description="Secret token xác thực Webhook header (X-Telegram-Bot-Api-Secret-Token)")


class CreateAutomationRuleRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=255, description="Tên quy tắc tự động")
    rule_type: str = Field(..., description="AUTO_PAUSE_SPEND_LIMIT, ALERT_LOW_VCC_BALANCE, DAILY_REPORT_SCHEDULE, ALERT_HIGH_DRIFT_SPEND")
    threshold: Decimal = Field(default=Decimal("0"), description="Ngưỡng kích hoạt")
    currency: str = Field("VND", description="Đơn vị tiền tệ (VND, USD)")
    target_entity_id: Optional[str] = Field(None, description="ID chiến dịch/thẻ mục tiêu hoặc để trống áp dụng tất cả")
    action_type: str = Field("TELEGRAM_ALERT", description="AUTO_PAUSE, TELEGRAM_ALERT, DAILY_DIGEST")
    is_enabled: bool = Field(True, description="Trạng thái bật/tắt quy tắc")


class UpdateAutomationRuleRequest(BaseModel):
    name: Optional[str] = None
    threshold: Optional[Decimal] = None
    currency: Optional[str] = None
    target_entity_id: Optional[str] = None
    action_type: Optional[str] = None
    is_enabled: Optional[bool] = None


# --- Endpoints: Trạng thái & Kết nối Bot ---

@router.get("/status")
def get_telegram_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Kiểm tra cấu hình, trạng thái kết nối bot và thông tin Webhook."""
    connector = get_configured_telegram_connector(db)
    rules_count = db.execute(select(AutomationRule).where(AutomationRule.is_enabled == True)).scalars().all()

    webhook_info = {}
    bot_info = None
    connection_ok = False
    try:
        me = connector.get_me()
        bot_info = me.get("result")
        connection_ok = bool(bot_info)
        wh = connector.get_webhook_info()
        webhook_info = wh.get("result", {})
    except Exception:
        connection_ok = False

    return {
        "mode": connector.mode,
        "is_configured": bool(connector._use_mock is False),
        "admin_chat_id": connector.admin_chat_id,
        "admin_chat_id_configured": bool(connector.admin_chat_id),
        "allowed_chat_ids_count": len(connector.allowed_chat_ids),
        "allowed_chat_ids": list(connector.allowed_chat_ids),
        "bot_info": bot_info,
        "connection_ok": connection_ok,
        "webhook_info": webhook_info,
        "active_rules_count": len(rules_count),
    }


@router.post("/test-connection", dependencies=[Depends(require_telegram_admin)])
def test_bot_connection(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Kiểm tra kết nối trực tiếp tới Telegram Bot API (getMe)."""
    connector = get_configured_telegram_connector(db)
    try:
        res = connector.get_me()
        bot_data = res.get("result", {})
        username = bot_data.get("username", "UnknownBot")
        first_name = bot_data.get("first_name", "Bot")
        return {
            "success": True,
            "message": f"Kết nối thành công tới Bot @{username} ({first_name})!",
            "bot": bot_data,
        }
    except TelegramAPIError as exc:
        raise HTTPException(status_code=400, detail=f"Không thể kết nối Telegram Bot: {str(exc)}")


@router.get("/config", dependencies=[Depends(require_telegram_admin)])
def get_bot_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Lấy thông tin cấu hình Telegram Bot hiện hành (Token được che giấu an toàn)."""
    cfg = db.execute(select(TelegramBotConfig).order_by(desc(TelegramBotConfig.id)).limit(1)).scalar_one_or_none()
    admin_id = cfg.admin_chat_id if cfg else settings.telegram_admin_chat_id
    allowed = cfg.allowed_chat_ids if cfg else settings.telegram_allowed_chat_ids
    webhook_url = cfg.webhook_url if cfg else ""
    has_token = bool((cfg and cfg.encrypted_bot_token) or settings.telegram_bot_token)
    has_webhook_secret = bool((cfg and cfg.encrypted_webhook_secret) or settings.telegram_webhook_secret)

    return {
        "has_token": has_token,
        "has_webhook_secret": has_webhook_secret,
        "admin_chat_id": admin_id or "",
        "allowed_chat_ids": allowed or "",
        "webhook_url": webhook_url or "",
    }


@router.post("/config", dependencies=[Depends(require_telegram_admin)])
@router.put("/config", dependencies=[Depends(require_telegram_admin)])
def update_bot_config(
    req: UpdateBotConfigRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật cấu hình bot (bắt buộc mã hóa Fernet cho Token & Webhook Secret) và thiết lập Webhook."""
    cfg = db.execute(select(TelegramBotConfig).order_by(desc(TelegramBotConfig.id)).limit(1)).scalar_one_or_none()
    if not cfg:
        cfg = TelegramBotConfig()
        db.add(cfg)

    if req.bot_token is not None and req.bot_token.strip():
        token_clean = req.bot_token.strip()
        try:
            cfg.encrypted_bot_token = encrypt_meta_token(token_clean)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Từ chối lưu Telegram Bot Token dạng plaintext: Lỗi mã hóa Fernet ({str(exc)})",
            )

    if req.webhook_secret is not None and req.webhook_secret.strip():
        secret_clean = req.webhook_secret.strip()
        try:
            cfg.encrypted_webhook_secret = encrypt_meta_token(secret_clean)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Từ chối lưu Webhook Secret dạng plaintext: Lỗi mã hóa Fernet ({str(exc)})",
            )

    if req.admin_chat_id is not None:
        cfg.admin_chat_id = req.admin_chat_id.strip()

    if req.allowed_chat_ids is not None:
        cfg.allowed_chat_ids = req.allowed_chat_ids.strip()

    if req.webhook_url is not None:
        cfg.webhook_url = req.webhook_url.strip()

    db.commit()
    db.refresh(cfg)

    # Nếu cấu hình webhook URL, tự động gọi API Telegram kèm secret token
    connector = get_configured_telegram_connector(db)
    webhook_msg = ""
    if cfg.webhook_url:
        secret_raw = None
        if cfg.encrypted_webhook_secret:
            secret_raw = decrypt_token_if_encrypted(cfg.encrypted_webhook_secret) or cfg.encrypted_webhook_secret
        elif settings.telegram_webhook_secret:
            secret_raw = settings.telegram_webhook_secret
        try:
            connector.set_webhook(cfg.webhook_url, secret_token=secret_raw)
            webhook_msg = f" Đã thiết lập Webhook tới {cfg.webhook_url}."
        except Exception as exc:
            webhook_msg = f" (Cảnh báo: Không thể set webhook trên Telegram: {str(exc)})"

    return {
        "success": True,
        "message": f"Cập nhật cấu hình Telegram Bot thành công!{webhook_msg}",
    }


# --- Endpoints: Nhật ký hoạt động (Activity Logs) ---

@router.get("/activity-logs")
def get_activity_logs(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lấy danh sách nhật ký tương tác bot gần nhất."""
    logs = db.execute(select(TelegramActivityLog).order_by(desc(TelegramActivityLog.id)).limit(limit)).scalars().all()
    return [
        {
            "id": l.id,
            "chat_id": l.chat_id,
            "username": l.username or "Ẩn danh",
            "command": l.command,
            "response_summary": l.response_summary,
            "status": l.status,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


# --- Endpoints: Quy tắc Tự động hóa (Automation Rules) ---

@router.get("/rules")
def list_automation_rules(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Lấy danh sách các quy tắc tự động hóa."""
    rules = ensure_default_rules(db)
    return [
        {
            "id": r.id,
            "name": r.name,
            "rule_type": r.rule_type,
            "threshold": float(r.threshold),
            "currency": r.currency,
            "target_entity_id": r.target_entity_id,
            "action_type": r.action_type,
            "is_enabled": r.is_enabled,
            "last_triggered_at": r.last_triggered_at.isoformat() if r.last_triggered_at else None,
            "trigger_count": r.trigger_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rules
    ]


@router.post("/rules", dependencies=[Depends(require_telegram_admin)])
def create_automation_rule(
    req: CreateAutomationRuleRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tạo một quy tắc tự động hóa mới."""
    rule = AutomationRule(
        name=req.name,
        rule_type=req.rule_type,
        threshold=req.threshold,
        currency=req.currency,
        target_entity_id=req.target_entity_id,
        action_type=req.action_type,
        is_enabled=req.is_enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {
        "success": True,
        "rule_id": rule.id,
        "message": f"Đã tạo quy tắc '{rule.name}' thành công.",
    }


@router.patch("/rules/{rule_id}", dependencies=[Depends(require_telegram_admin)])
def update_automation_rule(
    rule_id: int,
    req: UpdateAutomationRuleRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật hoặc Bật/Tắt một quy tắc tự động hóa."""
    rule = db.execute(select(AutomationRule).where(AutomationRule.id == rule_id)).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Không tìm thấy quy tắc tự động hóa")

    if req.name is not None:
        rule.name = req.name
    if req.threshold is not None:
        rule.threshold = req.threshold
    if req.currency is not None:
        rule.currency = req.currency
    if req.target_entity_id is not None:
        rule.target_entity_id = req.target_entity_id
    if req.action_type is not None:
        rule.action_type = req.action_type
    if req.is_enabled is not None:
        rule.is_enabled = req.is_enabled

    db.commit()
    return {
        "success": True,
        "rule_id": rule.id,
        "is_enabled": rule.is_enabled,
        "message": f"Đã cập nhật quy tắc '{rule.name}'.",
    }


@router.delete("/rules/{rule_id}", dependencies=[Depends(require_telegram_admin)])
def delete_automation_rule(
    rule_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Xoá một quy tắc tự động hóa."""
    rule = db.execute(select(AutomationRule).where(AutomationRule.id == rule_id)).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Không tìm thấy quy tắc tự động hóa")
    db.delete(rule)
    db.commit()
    return {"success": True, "message": f"Đã xoá quy tắc '{rule.name}'."}


@router.post("/rules/run-check", dependencies=[Depends(require_telegram_admin)])
def trigger_rules_evaluation(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Kích hoạt kiểm tra thủ công toàn bộ các quy tắc tự động hoá."""
    res = evaluate_automation_rules(db)
    return {
        "success": True,
        "summary": res,
        "message": f"Đã quét {res['rules_checked']} quy tắc. Kích hoạt {res['triggered_count']} hành động.",
    }


# --- Existing Webhook & Dispatch ---

@router.post("/webhook")
async def telegram_webhook_endpoint(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tiếp nhận Telegram Update từ Webhook chính thức của Telegram có xác thực Secret Token."""
    # 1. Xác thực header X-Telegram-Bot-Api-Secret-Token bằng hmac.compare_digest trước khi đọc payload
    header_secret = (
        request.headers.get("x-telegram-bot-api-secret-token")
        or request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        or ""
    )

    cfg = db.execute(
        select(TelegramBotConfig)
        .where(TelegramBotConfig.is_active == True)
        .order_by(desc(TelegramBotConfig.id))
        .limit(1)
    ).scalar_one_or_none()

    expected_secret = None
    if cfg and cfg.encrypted_webhook_secret:
        expected_secret = decrypt_token_if_encrypted(cfg.encrypted_webhook_secret) or cfg.encrypted_webhook_secret
    if not expected_secret and settings.telegram_webhook_secret:
        expected_secret = settings.telegram_webhook_secret

    if not expected_secret or not header_secret or not hmac.compare_digest(header_secret, expected_secret):
        raise HTTPException(
            status_code=403,
            detail="Xác thực Telegram Webhook Secret thất bại: Secret token không hợp lệ hoặc bị thiếu.",
        )

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload JSON không hợp lệ")

    connector = get_configured_telegram_connector(db)
    agent = TelegramBotAgent(telegram_connector=connector)
    result = agent.process_update(db, body)
    return {"status": "ok", "result": result}


@router.post("/dispatch")
def dispatch_command_endpoint(
    req: DispatchCommandRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Kích hoạt và điều phối lệnh bot qua API (bắt buộc Chat ID thuộc Whitelist hoặc phiên Admin)."""
    connector = get_configured_telegram_connector(db)
    agent = TelegramBotAgent(telegram_connector=connector)

    is_admin_session = False
    try:
        require_telegram_admin(request)
        is_admin_session = True
    except HTTPException:
        is_admin_session = False

    raw_chat_id = str(req.chat_id).strip() if req.chat_id is not None else ""
    if not raw_chat_id:
        if not is_admin_session:
            raise HTTPException(
                status_code=403,
                detail="Từ chối điều phối: Yêu cầu cung cấp chat_id hợp lệ hoặc phiên quản trị được xác thực.",
            )
        chat_id_to_use = str(agent.telegram.admin_chat_id or "console")
    else:
        if not agent.telegram.is_chat_allowed(raw_chat_id):
            raise HTTPException(
                status_code=403,
                detail=f"Chat ID {raw_chat_id} không có trong danh sách phân quyền (ADSOS_TELEGRAM_ALLOWED_CHAT_IDS)",
            )
        chat_id_to_use = raw_chat_id

    # Kiểm tra quyền Admin cho các lệnh nhạy cảm / BM routing / khóa tài khoản
    cmd_first = req.command.strip().split()[0].lower().split("@")[0]
    if cmd_first in ADMIN_COMMANDS:
        is_chat_admin = bool(agent.telegram.admin_chat_id and str(chat_id_to_use) == str(agent.telegram.admin_chat_id))
        if not is_admin_session and not is_chat_admin:
            raise HTTPException(
                status_code=403,
                detail=f"⛔ Lệnh {cmd_first} chỉ dành riêng cho Quản trị viên (Admin).",
            )

    response_text = agent.dispatch_command(db, req.command, actor=req.actor)
    # Ghi nhật ký
    try:
        log = TelegramActivityLog(
            chat_id=chat_id_to_use,
            username=req.actor,
            command=req.command,
            response_summary=response_text[:250],
            status="SUCCESS",
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()

    return {
        "command": req.command,
        "actor": req.actor,
        "response_text": response_text,
    }


@router.post("/test-send", dependencies=[Depends(require_telegram_admin)])
def send_test_message_endpoint(
    req: TestSendMessageRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Gửi tin nhắn thử nghiệm tới admin hoặc chat ID chỉ định."""
    connector = get_configured_telegram_connector(db)
    try:
        if req.chat_id:
            res = connector.send_message(req.chat_id, req.message)
        else:
            res = connector.send_admin_message(req.message)
        return {"status": "ok", "detail": res}
    except TelegramAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Lỗi gửi tin nhắn Telegram: {str(exc)}")
