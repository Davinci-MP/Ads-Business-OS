"""Dịch vụ AI Task Dispatcher & Nhận diện Khách hàng tự động từ Telegram.

Phân loại thông minh các yêu cầu:
1. ADD_MAIL_TO_BM (Mời mail vào Business Manager)
2. ADD_AD_ACCOUNT (Thêm/Cấp tài khoản quảng cáo)
3. SETTLE_DEBT (Thanh toán nợ cước tài khoản QC)
4. TOPUP_BUDGET (Nạp ngân sách / gửi biên nhận)
5. CHECK_BALANCE (Tra cứu số dư ví trả trước)
6. GENERAL_SUPPORT (Yêu cầu hỗ trợ kỹ thuật khác)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client_task import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    TASK_STATUS_PENDING,
    TASK_TYPE_ADD_AD_ACCOUNT,
    TASK_TYPE_ADD_MAIL_TO_BM,
    TASK_TYPE_CHECK_BALANCE,
    TASK_TYPE_GENERAL_SUPPORT,
    TASK_TYPE_SETTLE_DEBT,
    TASK_TYPE_TOPUP_BUDGET,
    ClientTask,
)
from app.models.customer import Customer
from app.models.prepaid import ClientBalance

logger = logging.getLogger(__name__)

TASK_TYPE_LABELS = {
    TASK_TYPE_ADD_MAIL_TO_BM: "Mời mail vào Business Manager (BM)",
    TASK_TYPE_ADD_AD_ACCOUNT: "Thêm / Gán tài khoản quảng cáo",
    TASK_TYPE_SETTLE_DEBT: "Thanh toán nợ cước tài khoản QC",
    TASK_TYPE_TOPUP_BUDGET: "Nạp ngân sách / Gửi chứng từ",
    TASK_TYPE_CHECK_BALANCE: "Tra cứu số dư ví",
    TASK_TYPE_GENERAL_SUPPORT: "Hỗ trợ kỹ thuật & Vận hành",
}


def get_verified_customer(
    session: Session,
    chat_id: str,
    username: Optional[str] = None,
) -> Optional[Customer]:
    """Chỉ xác thực danh tính khách hàng dựa trên binding telegram_chat_id hoặc telegram_username đã kiểm chứng."""
    clean_chat_id = str(chat_id).strip()
    clean_user = username.strip().lower().lstrip("@") if username else None

    # 1. Tìm theo telegram_chat_id
    cust = session.scalar(
        select(Customer).where(Customer.telegram_chat_id == clean_chat_id, Customer.is_active.is_(True))
    )
    if cust:
        if clean_user and not cust.telegram_username:
            cust.telegram_username = clean_user
            session.flush()
        return cust

    # 2. Tìm theo telegram_username
    if clean_user:
        cust = session.scalar(
            select(Customer).where(Customer.telegram_username == clean_user, Customer.is_active.is_(True))
        )
        if cust:
            if not cust.telegram_chat_id:
                cust.telegram_chat_id = clean_chat_id
                session.flush()
            return cust

    return None


def scan_mentioned_customer(session: Session, text: str) -> Optional[Customer]:
    """Quét tên khách hàng được nhắc trong nội dung tin nhắn (chỉ dùng để gắn nhãn lead, KHÔNG xác thực danh tính)."""
    if not text or not text.strip():
        return None
    all_customers = session.scalars(select(Customer).where(Customer.is_active.is_(True))).all()
    lower_text = text.lower()
    for c in all_customers:
        c_name = c.name.strip().lower()
        clean_name = re.sub(r"\b(công ty|tnhh|cp|cty|co|ltd|corp)\b", "", c_name).strip()
        clean_name = re.sub(r"\s+", " ", clean_name)
        if (len(c_name) >= 3 and c_name in lower_text) or (len(clean_name) >= 3 and clean_name in lower_text):
            return c
    return None


def match_or_create_customer(
    session: Session,
    chat_id: str,
    username: Optional[str] = None,
    sender_name: Optional[str] = None,
    text: str = "",
    task_type: Optional[str] = None,
) -> Optional[Customer]:
    """Nhận diện khách hàng: ưu tiên xác thực bảo mật qua chat_id/username; cấm match tên khi kiểm tra số dư."""
    verified = get_verified_customer(session, chat_id, username)
    if verified:
        return verified

    # Với các tác vụ nhạy cảm (kiểm tra số dư CHECK_BALANCE), tuyệt đối không nhận diện theo tên nhắc trong text
    if task_type in (TASK_TYPE_CHECK_BALANCE,):
        return None

    # Backward compatibility: hỗ trợ quét tên nếu không phải tác vụ nhạy cảm
    return scan_mentioned_customer(session, text)


def classify_client_message(text: str) -> tuple[str, dict[str, Any], str]:
    """Phân loại nội dung tin nhắn và trích xuất thực thể (email, bm_id, act_id, amount)."""
    raw = text.strip()
    lower = raw.lower()

    extracted: dict[str, Any] = {}
    priority = PRIORITY_NORMAL

    # Regex trích xuất cơ bản
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", raw)
    if email_match:
        extracted["email"] = email_match.group(0)

    # BM ID
    bm_match = re.search(r"(?:bm|business|id\s*bm)[\s:]*([0-9]{10,20})", lower)
    if bm_match:
        extracted["bm_id"] = bm_match.group(1)
    else:
        # Tìm chuỗi số dài nếu có nhắc tới BM
        if "bm" in lower:
            long_digits = re.findall(r"\b[0-9]{12,18}\b", raw)
            if long_digits:
                extracted["bm_id"] = long_digits[0]

    # Ad Account ID
    act_match = re.search(r"(?:act_)?([0-9]{12,18})", raw)
    if act_match and "bm_id" not in extracted:
        extracted["account_id"] = f"act_{act_match.group(1)}"
    elif "act_" in lower:
        act_explicit = re.search(r"act_[0-9]+", raw)
        if act_explicit:
            extracted["account_id"] = act_explicit.group(0)

    # 1. ADD_MAIL_TO_BM
    if any(k in lower for k in ["mời mail", "add mail", "thêm mail", "moi mail", "add email", "mời email", "invite mail"]):
        task_type = TASK_TYPE_ADD_MAIL_TO_BM
        if "admin" in lower or "quản trị" in lower:
            extracted["role"] = "ADMIN"
        else:
            extracted["role"] = "EMPLOYEE"
        return task_type, extracted, PRIORITY_NORMAL

    if "bm" in lower and extracted.get("email"):
        return TASK_TYPE_ADD_MAIL_TO_BM, extracted, PRIORITY_NORMAL

    # 2. SETTLE_DEBT
    if any(k in lower for k in ["thanh toán nợ", "thanh toan no", "trả nợ", "tra no", "nợ cước", "no cuoc", "settle debt", "pay debt", "bị nợ", "bi no", "thanh toán tk"]):
        task_type = TASK_TYPE_SETTLE_DEBT
        priority = PRIORITY_HIGH
        # Trích xuất số tiền nợ nếu có
        amt_match = re.search(r"([0-9]{1,3}(?:[.,][0-9]{3})*|\b[0-9]+\b)\s*(?:k|tr|triệu|vnd|đ|\$|usd)?", lower)
        if amt_match:
            extracted["amount_hint"] = amt_match.group(0)
        return task_type, extracted, priority

    # 3. ADD_AD_ACCOUNT
    if any(k in lower for k in ["thêm tài khoản", "them tai khoan", "add tk", "thêm tk", "cấp tk", "cap tk", "gán tk", "gan tk", "add account"]):
        task_type = TASK_TYPE_ADD_AD_ACCOUNT
        return task_type, extracted, PRIORITY_NORMAL

    # 4. TOPUP_BUDGET
    if any(k in lower for k in ["nạp tiền", "nap tien", "nạp ngân sách", "nap ngan sach", "gửi bill", "gui bill", "chuyển khoản", "chuyen khoan", "đã chuyển", "da chuyen"]):
        task_type = TASK_TYPE_TOPUP_BUDGET
        return task_type, extracted, PRIORITY_NORMAL

    # 5. CHECK_BALANCE
    if any(k in lower for k in ["số dư", "so du", "còn bao nhiêu", "con bao nhieu", "hết tiền", "het tien", "check số dư"]):
        task_type = TASK_TYPE_CHECK_BALANCE
        return task_type, extracted, PRIORITY_LOW

    # 6. Mặc định: GENERAL_SUPPORT
    return TASK_TYPE_GENERAL_SUPPORT, extracted, PRIORITY_NORMAL


def dispatch_client_message(
    session: Session,
    chat_id: str,
    username: Optional[str] = None,
    sender_name: Optional[str] = None,
    message_text: str = "",
    telegram_connector: Optional[Any] = None,
) -> dict[str, Any]:
    """Xử lý tin nhắn khách hàng gửi tới Telegram, phân loại và lưu thành tác vụ có cấu trúc.
    
    Bảo mật: Chỉ xác thực danh tính dựa trên liên kết telegram_chat_id hoặc telegram_username.
    Không bao giờ tiết lộ số dư hoặc tài sản riêng tư cho các chat chưa được xác thực.
    """
    task_type, extracted, priority = classify_client_message(message_text)

    # 1. Chỉ nhận diện khách hàng nếu đã xác thực liên kết Telegram
    customer = get_verified_customer(session, chat_id, username)

    # 2. Nếu chưa liên kết nhưng có nhắc tên công ty/khách hàng, lưu dưới dạng lead chưa xác minh
    if not customer:
        mentioned_cust = scan_mentioned_customer(session, message_text)
        if mentioned_cust:
            extracted["unverified_customer_mention"] = mentioned_cust.name
            extracted["mentioned_customer_id"] = mentioned_cust.id
            extracted["is_identity_verified"] = False

    # Lưu tác vụ vào database
    task = ClientTask(
        customer_id=customer.id if customer else None,
        telegram_chat_id=str(chat_id),
        telegram_username=username,
        sender_name=sender_name,
        task_type=task_type,
        raw_message=message_text,
        extracted_data=json.dumps(extracted, ensure_ascii=False) if extracted else None,
        status=TASK_STATUS_PENDING,
        priority=priority,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    # Multi-BM Auto-Fulfillment & Preference Memory Routing
    fulfillment_note = ""
    if customer and task_type in (TASK_TYPE_ADD_MAIL_TO_BM, TASK_TYPE_ADD_AD_ACCOUNT):
        from app.services.auto_fulfillment import route_and_fulfill_client_task
        fulfillment_res = route_and_fulfill_client_task(
            session=session,
            task=task,
            telegram_connector=telegram_connector,
        )
        if fulfillment_res.get("status") == "AUTO_ROUTED":
            pref_data = fulfillment_res.get("preference", {})
            bm_disp = pref_data.get("bm_name") or pref_data.get("preferred_bm_id")
            fulfillment_note = (
                f"\n\n⚡ <b>Tự động định tuyến:</b> Đã áp dụng {bm_disp} "
                f"({pref_data.get('bm_role')}) theo cấu hình ghi nhớ của bạn."
            )
        elif fulfillment_res.get("status") == "AWAITING_ADMIN_PREFERENCE_SELECTION":
            fulfillment_note = (
                "\n\nℹ️ <i>Yêu cầu cấp quyền BM mới đã được gửi tới Quản trị viên để chọn BM và ghi nhớ cấu hình.</i>"
            )

    type_label = TASK_TYPE_LABELS.get(task_type, task_type)

    # Tạo phản hồi thông minh bằng Tiếng Việt
    details: list[str] = []
    if "email" in extracted:
        details.append(f"• Email: <code>{extracted['email']}</code>")
    if "bm_id" in extracted:
        details.append(f"• BM ID: <code>{extracted['bm_id']}</code>")
    if "account_id" in extracted:
        details.append(f"• TKQC: <code>{extracted['account_id']}</code>")
    if "role" in extracted:
        details.append(f"• Quyền hạn: <b>{extracted['role']}</b>")
    details_str = ("\n" + "\n".join(details)) if details else ""

    if customer:
        # Nếu là hỏi số dư và khách hàng đã có sổ, trả lời trực tiếp số dư
        extra_info = ""
        if task_type == TASK_TYPE_CHECK_BALANCE:
            balances = session.scalars(
                select(ClientBalance).where(ClientBalance.customer_id == customer.id)
            ).all()
            if balances:
                bal_strs = [f"• {b.currency}: <b>{b.amount:,.2f}</b>" for b in balances]
                extra_info = "\n\n💰 <b>Số dư hiện tại của bạn:</b>\n" + "\n".join(bal_strs)

        reply_text = (
            f"🤖 <b>ADSOS AI WORK ASSISTANT</b>\n\n"
            f"✅ Đã ghi nhận yêu cầu cho khách hàng <b>{customer.name}</b>!\n"
            f"📋 <b>Phân loại:</b> {type_label}"
            f"{details_str}\n"
            f"🎫 <b>Mã tác vụ:</b> <code>#{task.id}</code>\n"
            f"⚡ <b>Mức độ ưu tiên:</b> {priority}"
            f"{extra_info}"
            f"{fulfillment_note}\n\n"
            f"<i>Kỹ thuật viên đang tiếp nhận và sẽ phản hồi trong giây lát!</i>"
        )
    else:
        security_note = ""
        if task_type == TASK_TYPE_CHECK_BALANCE:
            security_note = "\n🔒 <i>Vì lý do bảo mật, hệ thống không thể hiển thị số dư ví cho tài khoản chưa liên kết.</i>\n"
        reply_text = (
            f"🤖 <b>ADSOS AI WORK ASSISTANT</b>\n\n"
            f"👋 Xin chào {sender_name or 'bạn'}! Hệ thống đã tiếp nhận yêu cầu của bạn:\n"
            f"📋 <b>Phân loại:</b> {type_label}"
            f"{details_str}\n"
            f"🎫 <b>Mã tác vụ:</b> <code>#{task.id}</code>\n"
            f"{security_note}\n"
            f"💡 <i>Gợi ý: Tài khoản Telegram của bạn chưa liên kết trực tiếp với hồ sơ khách hàng. "
            f"Kỹ thuật viên sẽ kiểm tra và hỗ trợ bạn ngay!</i>"
        )

    return {
        "task_id": task.id,
        "task_type": task_type,
        "customer_id": customer.id if customer else None,
        "customer_name": customer.name if customer else None,
        "extracted_data": extracted,
        "reply_text": reply_text,
    }
