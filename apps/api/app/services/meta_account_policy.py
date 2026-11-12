"""Đặc cách chỉ áp dụng cho đúng tài khoản đã được quản trị viên cấu hình."""
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.ad_account import AdAccount
from app.models.finance import AuditLog
from app.core.config import settings

def find_account(session: Session, account_id: str):
    raw = account_id.removeprefix("act_")
    return session.execute(select(AdAccount).where(AdAccount.meta_ad_account_id.in_([raw, f"act_{raw}"]))).scalar_one_or_none()

def set_violation_override(session: Session, account_id: str, enabled: bool, actor: str = "web_ui"):
    if settings.app_env == "staging":
        raise ValueError("Môi trường staging chỉ cho phép đọc.")
    account = find_account(session, account_id)
    if account is None:
        raise ValueError("Tài khoản chưa được quản lý; hãy thêm tài khoản trước khi cấu hình đặc cách.")
    old = account.allow_violated_accounts
    account.allow_violated_accounts = enabled
    session.add(AuditLog(actor=actor, action="SET_ACCOUNT_VIOLATION_OVERRIDE", entity_type="ad_account", entity_id=str(account.id), detail={"previous": old, "enabled": enabled}))
    session.flush()
    return account

def validate_account_policy(session: Session, connector, account_id: str):
    account = find_account(session, account_id)
    health = connector.get_ad_account_billing_health(account_id)
    try:
        status = int(health["account_status"])
        balance = Decimal(str(health.get("balance", "0")))
        threshold = health.get("billing_threshold")
        debt_exceeded = threshold is not None and balance >= Decimal(str(threshold)) and balance > 0
        if not balance.is_finite() or (threshold is not None and not Decimal(str(threshold)).is_finite()):
            raise ValueError()
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise ValueError("Chưa xác minh được trạng thái tài khoản; vui lòng thử lại.")
    local_blocked = account is not None and account.status != "ACTIVE"
    if (status != 1 or debt_exceeded or local_blocked) and not (account and account.allow_violated_accounts):
        raise ValueError("Tài khoản bị hạn chế, vô hiệu hóa hoặc vượt ngưỡng nợ; cần bật Đặc cách cho đúng tài khoản trước khi tiếp tục.")
    return health
