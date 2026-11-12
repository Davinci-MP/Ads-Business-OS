"""Giám sát sức khỏe; khóa nội bộ độc lập với cờ đặc cách vi phạm."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape

from sqlalchemy import select

from app.connectors.meta import MetaAPIError
from app.connectors.telegram import TelegramAPIError
from app.core.config import settings
from app.models.ad_account import AdAccount
from app.models.campaign import Campaign
from app.models.finance import AuditLog, TelegramOutbox
from app.models.meta_risk import MetaAccountRisk
from app.services.remote_commands import enqueue_extension_command


def normalize(account_id):
    value = str(account_id).strip()
    if value.startswith("act_"):
        value = value[4:]
    if not value or not value.isdigit():
        raise ValueError("Mã tài khoản phải là chữ số, có thể bắt đầu bằng act_.")
    return "act_" + value


def get_risk(db, account_id, allow_mock=False):
    account_id = str(account_id) if allow_mock else normalize(account_id)
    row = db.get(MetaAccountRisk, account_id)
    if row is None:
        row = MetaAccountRisk(account_id=account_id)
        db.add(row)
        db.flush()
    return row


def assert_account_unlocked(db, account_id):
    value = str(account_id).strip()
    row = db.get(MetaAccountRisk, value if value.startswith("act_") else "act_" + value)
    if row and row.locked:
        raise ValueError("Tài khoản đang bị khóa an toàn; không thể tạo hoặc bật chiến dịch dù đã đặc cách.")


def _notify(db, notifier, message):
    try:
        notifier.send_admin_message(message)
    except Exception:
        db.add(TelegramOutbox(message=message, last_error="Không gửi được cảnh báo rủi ro Telegram."))


def scan_account_risks(db, connector, notifier):
    if settings.app_env == "production" and connector.mode == "mock":
        return {"checked": 0, "errors": 0, "message": "Không dùng dữ liệu giả lập trong môi trường sản xuất."}
    try:
        accounts = connector.get_ad_accounts()
    except MetaAPIError:
        rows = db.scalars(select(MetaAccountRisk)).all()
        for row in rows:
            row.data_status = "UNVERIFIED"
            row.last_error = "Không đọc được danh sách Meta; giữ nguyên dữ liệu đã có."
        _notify(db, notifier, "⚠️ Không đọc được danh sách tài khoản Meta; giữ nguyên dữ liệu cũ và đánh dấu chưa xác minh.")
        db.flush()
        return {"checked": 0, "errors": len(rows) or 1}
    checked = errors = 0
    for account in accounts:
        row = get_risk(db, account["meta_ad_account_id"], allow_mock=connector.mode == "mock")
        try:
            health = connector.get_ad_account_billing_health(row.account_id)
            status = int(health["account_status"])
            currency = str(health["currency"])
            debt = Decimal(str(health["balance"]))
            if not debt.is_finite() or debt < 0 or not currency:
                raise ValueError("Dữ liệu nợ cước chưa xác minh.")
            risk = "DISABLED" if status == 2 else "UNSETTLED" if status == 3 else "HEALTHY" if status == 1 else "RESTRICTED"
            if row.currency is not None and row.currency != currency:
                row.debt_threshold = None
            if risk == "HEALTHY" and row.debt_threshold is not None and row.currency == currency and debt > row.debt_threshold:
                risk = "HIGH_DEBT"
            previous = row.risk_code
            row.account_status, row.debt, row.currency = status, debt, currency
            row.risk_code, row.data_status = risk, "VERIFIED"
            row.checked_at, row.last_error = datetime.now(timezone.utc), None
            if risk != "HEALTHY" and risk != previous:
                labels = {"DISABLED": "bị vô hiệu hóa", "UNSETTLED": "có vấn đề thanh toán", "HIGH_DEBT": "nợ cước vượt ngưỡng", "RESTRICTED": "bị hạn chế"}
                _notify(db, notifier, f"🚨 Tài khoản <code>{escape(row.account_id)}</code> {labels[risk]}. Nợ cước: {debt} {escape(currency)}. Dùng /khoatkn {escape(row.account_id)} để khóa an toàn.")
            checked += 1
        except (MetaAPIError, ValueError, KeyError, TypeError, InvalidOperation):
            row.data_status = "UNVERIFIED"
            row.last_error = "Không xác minh được trạng thái Meta; giữ nguyên dữ liệu đã có."
            errors += 1
    db.flush()
    return {"checked": checked, "errors": errors}


def lock_account(db, connector, account_id, actor="web_ui"):
    if settings.app_env == "staging":
        raise ValueError("Môi trường thử nghiệm chỉ đọc, không được khóa hoặc dừng chiến dịch.")
    row = get_risk(db, account_id, allow_mock=connector.mode == "mock" and str(account_id).startswith("act_"))
    row.locked = True
    db.add(AuditLog(actor=actor, action="LOCK_META_ACCOUNT", entity_type="ad_account", entity_id=row.account_id, detail={"locked": True}))
    db.commit()  # Khóa phải tồn tại ngay cả khi Meta từ chối lệnh dừng.
    campaigns = connector.get_account_campaigns(row.account_id)
    queued, failed = [], []
    for campaign in campaigns:
        campaign_id = campaign.get("meta_campaign_id") or campaign.get("id")
        if not campaign_id:
            continue
        try:
            local = db.scalar(select(Campaign).where(Campaign.meta_campaign_id == campaign_id))
            enqueue_extension_command(
                db,
                act_id=row.account_id,
                command_type="SET_CAMPAIGN_STATUS",
                payload={"campaign_id": campaign_id, "status": "PAUSED"},
                customer_id=local.customer_id if local else None,
                requested_by=actor,
            )
            queued.append(campaign_id)
        except (MetaAPIError, ValueError):
            failed.append(campaign_id)
    db.add(AuditLog(actor=actor, action="QUEUE_PAUSE_ACCOUNT_CAMPAIGNS", entity_type="ad_account", entity_id=row.account_id, detail={"queued": queued, "failed": failed, "mode": connector.mode}))
    db.commit()
    return {"account_id": row.account_id, "locked": True, "paused": [], "queued": queued, "failed": failed, "mode": connector.mode, "message": "Đã khóa nội bộ. " + ("Một số chiến dịch chưa xếp được lệnh tạm dừng." if failed else "Đã xếp lệnh tạm dừng cho Chrome Extension.")}


def unlock_account(db, account_id, actor="web_ui"):
    if settings.app_env == "staging":
        raise ValueError("Môi trường thử nghiệm chỉ đọc, không được mở khóa.")
    row = get_risk(db, account_id, allow_mock=True)
    row.locked = False
    db.add(AuditLog(actor=actor, action="UNLOCK_META_ACCOUNT", entity_type="ad_account", entity_id=row.account_id, detail={"locked": False}))
    db.commit()
    return {"account_id": row.account_id, "locked": False, "message": "Đã mở khóa an toàn tài khoản nội bộ."}

