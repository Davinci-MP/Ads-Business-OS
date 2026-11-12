"""Dịch vụ Multi-BM Auto-Fulfillment & Phân luồng Ghi nhớ Phân quyền Khách hàng.

Chức năng:
1. Lookup Preference: Kiểm tra cấu hình ưu tiên `client_bm_preferences` của khách hàng.
2. Auto-Fulfillment: Tự động áp dụng BM, vai trò BM và quyền hạn TKQC nếu đã có cấu hình.
3. Interactive Prompt: Nếu khách hàng mới chưa có cấu hình, gửi Telegram Prompt tương tác
   yêu cầu Quản trị viên lựa chọn:
   - BM lưu trữ (BM 1, BM 2, BM 3)
   - Vai trò BM (Nhân viên / Quản trị viên)
   - Cấp độ quyền TKQC (Truy cập đầy đủ / Truy cập một phần: Quản lý chiến dịch, Xem hiệu quả, Creative Hub)
4. Auto-Remember: Lưu lại lựa chọn vào `client_bm_preferences` để ghi nhớ cho tất cả các yêu cầu sau.
5. Manual Admin Override: Cho phép quản trị viên xem và ghi đè cấu hình qua API PATCH.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.telegram import TelegramBotConnector
from app.models.client_bm_preference import (
    ACCESS_TYPE_FULL,
    ACCESS_TYPE_PARTIAL,
    BM_ROLE_ADMIN,
    BM_ROLE_EMPLOYEE,
    DEFAULT_PARTIAL_PERMISSIONS,
    ClientBMPreference,
)
from app.models.client_task import (
    TASK_TYPE_ADD_AD_ACCOUNT,
    TASK_TYPE_ADD_MAIL_TO_BM,
    ClientTask,
)
from app.models.customer import Customer
from app.models.finance import AuditLog
from app.models.via import SyncedBM, ViaProfile

logger = logging.getLogger(__name__)

# Danh mục Business Manager khả dụng trong hệ thống
AVAILABLE_BMS = {
    "BM_01": {
        "id": "BM_01",
        "name": "BM 1",
        "full_name": "BM 1 (Chính - Ads Holding 01)",
        "description": "Kho tài khoản chính ngạch, độ uy tín cao, ưu tiên khách hàng chạy ngân sách lớn.",
    },
    "BM_02": {
        "id": "BM_02",
        "name": "BM 2",
        "full_name": "BM 2 (Dự phòng - Ads Holding 02)",
        "description": "Kho tài khoản dự phòng luân chuyển, kháng nghị sẵn.",
    },
    "BM_03": {
        "id": "BM_03",
        "name": "BM 3",
        "full_name": "BM 3 (Kháng nghị - Ads Holding 03)",
        "description": "Chuyên dùng cho tài khoản thử nghiệm hoặc ngành hàng đặc thù.",
    },
}


def get_available_bms(session: Optional[Session] = None) -> list[dict[str, Any]]:
    """Lấy danh sách BM khả dụng, ưu tiên BM Chính Cho Thuê (★) từ dàn VIA đã đồng bộ."""
    if session is not None:
        try:
            synced = session.scalars(
                select(SyncedBM).order_by(SyncedBM.is_primary_rental.desc(), SyncedBM.id.desc())
            ).all()
            if synced:
                result = []
                for b in synced:
                    via_uid = b.via_profile.uid if b.via_profile else ""
                    via_name = b.via_profile.profile_name if b.via_profile else ""
                    star_prefix = "★ [BM Cho Thuê] " if b.is_primary_rental else ""
                    result.append({
                        "id": b.bm_id,
                        "name": f"{star_prefix}{b.name}",
                        "full_name": f"{star_prefix}{b.name} (VIA: {via_uid or 'N/A'})",
                        "description": f"VIA: {via_name or via_uid or 'Chưa gán'} · {b.ad_account_count} TKQC · {b.page_count} Page",
                        "is_primary_rental": bool(b.is_primary_rental),
                        "via_profile_id": b.via_profile_id,
                        "via_uid": via_uid,
                    })
                return result
        except Exception as exc:
            logger.warning("Không thể lấy synced BMs, fallback về danh mục mặc định: %s", exc)

    return list(AVAILABLE_BMS.values())

BM_ROLE_LABELS = {
    BM_ROLE_EMPLOYEE: "Nhân viên (EMPLOYEE)",
    BM_ROLE_ADMIN: "Quản trị viên (ADMIN)",
}

ACCESS_TYPE_LABELS = {
    ACCESS_TYPE_FULL: "Truy cập đầy đủ (FULL)",
    ACCESS_TYPE_PARTIAL: "Truy cập một phần (PARTIAL)",
}

PERMISSION_LABELS = {
    "MANAGE_CAMPAIGNS": "Quản lý chiến dịch",
    "VIEW_PERFORMANCE": "Xem hiệu quả",
    "CREATIVE_HUB": "Creative Hub",
}


def get_client_bm_preference(session: Session, client_id: int) -> Optional[ClientBMPreference]:
    """Tìm cấu hình BM ưu tiên đã ghi nhớ của khách hàng."""
    return session.scalar(select(ClientBMPreference).where(ClientBMPreference.client_id == client_id))


def save_or_update_client_bm_preference(
    session: Session,
    client_id: int,
    preferred_bm_id: Optional[str] = None,
    via_profile_id: Optional[int] = None,
    bm_role: Optional[str] = None,
    ad_account_access_type: Optional[str] = None,
    partial_permissions: Optional[list[str]] = None,
    notes: Optional[str] = None,
    actor: str = "system",
) -> ClientBMPreference:
    """Tạo mới hoặc cập nhật cấu hình ghi nhớ BM cho khách hàng."""
    pref = get_client_bm_preference(session, client_id)
    is_new = pref is None

    if is_new:
        pref = ClientBMPreference(client_id=client_id)
        session.add(pref)

    if preferred_bm_id:
        clean_bm = preferred_bm_id.strip()
        pref.preferred_bm_id = clean_bm
        # Nếu chưa truyền via_profile_id, tự động liên kết từ SyncedBM nếu có
        if via_profile_id is None:
            synced_bm = session.scalar(select(SyncedBM).where(SyncedBM.bm_id == clean_bm))
            if synced_bm and synced_bm.via_profile_id:
                pref.via_profile_id = synced_bm.via_profile_id

    if via_profile_id is not None:
        pref.via_profile_id = via_profile_id

    if bm_role:
        clean_role = bm_role.strip().upper()
        if clean_role in (BM_ROLE_EMPLOYEE, BM_ROLE_ADMIN):
            pref.bm_role = clean_role

    if ad_account_access_type:
        clean_access = ad_account_access_type.strip().upper()
        if clean_access in (ACCESS_TYPE_FULL, ACCESS_TYPE_PARTIAL):
            pref.ad_account_access_type = clean_access

    if partial_permissions is not None:
        pref.set_permissions_list(partial_permissions)

    if notes is not None:
        pref.notes = notes.strip()

    session.flush()

    # Ghi audit log
    try:
        session.add(
            AuditLog(
                actor=actor,
                action="UPDATE_CLIENT_BM_PREFERENCE" if not is_new else "CREATE_CLIENT_BM_PREFERENCE",
                entity_type="client_bm_preference",
                entity_id=str(client_id),
                detail={
                    "client_id": client_id,
                    "preferred_bm_id": pref.preferred_bm_id,
                    "via_profile_id": pref.via_profile_id,
                    "bm_role": pref.bm_role,
                    "ad_account_access_type": pref.ad_account_access_type,
                    "partial_permissions": pref.get_permissions_list(),
                },
            )
        )
        session.commit()
        session.refresh(pref)
    except Exception as exc:
        logger.warning("Lỗi ghi audit log client_bm_preference: %s", exc)
        session.commit()

    return pref


def format_interactive_telegram_prompt(client: Customer, task: ClientTask) -> str:
    """Tạo nội dung tin nhắn Telegram tương tác yêu cầu Admin phân luồng BM lần đầu."""
    extracted = {}
    if task.extracted_data:
        try:
            extracted = json.loads(task.extracted_data)
        except Exception:
            extracted = {}

    target_email = extracted.get("email", "Chưa rõ")
    target_act = extracted.get("account_id", "Chưa rõ")

    return (
        f"🤖 <b>ADSOS AUTO-FULFILLMENT: YÊU CẦU CẤU HÌNH PHÂN QUYỀN BM</b>\n\n"
        f"Khách hàng: <b>{client.name}</b> (ID: <code>{client.id}</code>)\n"
        f"Tác vụ: <b>#{task.id}</b> ({task.task_type})\n"
        f"Nội dung yêu cầu: <i>{task.raw_message}</i>\n"
        f"Chi tiết bóc tách: Email: <code>{target_email}</code> | TKQC: <code>{target_act}</code>\n\n"
        f"⚠️ <b>Khách hàng này chưa có cấu hình BM ưu tiên.</b> Vui lòng chọn thiết lập để hệ thống tự động ghi nhớ:\n\n"
        f"1️⃣ <b>Business Manager (BM):</b>\n"
        f"   • <code>BM_01</code>: BM 1 (Chính - Ads Holding 01)\n"
        f"   • <code>BM_02</code>: BM 2 (Dự phòng - Ads Holding 02)\n"
        f"   • <code>BM_03</code>: BM 3 (Kháng nghị - Ads Holding 03)\n\n"
        f"2️⃣ <b>Vai trò trên BM:</b>\n"
        f"   • <code>EMPLOYEE</code>: Nhân viên (khuyên dùng cho khách hàng)\n"
        f"   • <code>ADMIN</code>: Quản trị viên\n\n"
        f"3️⃣ <b>Quyền hạn Tài khoản Quảng cáo:</b>\n"
        f"   • <code>FULL</code>: Toàn quyền truy cập\n"
        f"   • <code>PARTIAL</code>: Quyền một phần (Quản lý chiến dịch, Xem hiệu quả, Creative Hub)\n\n"
        f"👉 <b>Phản hồi trực tiếp bằng lệnh:</b>\n"
        f"<code>/set_bm {client.id} BM_01 EMPLOYEE FULL</code>\n"
        f"<i>(Hệ thống sẽ tự động lưu cấu hình và định tuyến các tác vụ tiếp theo không cần hỏi lại)</i>"
    )


def format_auto_routed_notification(client: Customer, task: ClientTask, pref: ClientBMPreference) -> str:
    """Tạo tin nhắn thông báo đã tự động ghi nhớ và định tuyến thành công."""
    bm_info = AVAILABLE_BMS.get(pref.preferred_bm_id, {})
    bm_name = bm_info.get("full_name", pref.preferred_bm_id)
    role_name = BM_ROLE_LABELS.get(pref.bm_role, pref.bm_role)
    access_name = ACCESS_TYPE_LABELS.get(pref.ad_account_access_type, pref.ad_account_access_type)

    perms_list = pref.get_permissions_list()
    perms_str = ", ".join(PERMISSION_LABELS.get(p, p) for p in perms_list)

    return (
        f"⚡ <b>TỰ ĐỘNG ĐỊNH TUYẾN PHÂN QUYỀN (PREFERENCE MEMORY ROUTING)</b>\n\n"
        f"Khách hàng: <b>{client.name}</b> (ID: <code>{client.id}</code>)\n"
        f"Tác vụ: <b>#{task.id}</b> ({task.task_type})\n\n"
        f"✅ <b>Đã áp dụng cấu hình đã ghi nhớ:</b>\n"
        f"• <b>BM tiếp nhận:</b> {bm_name}\n"
        f"• <b>Vai trò BM:</b> {role_name}\n"
        f"• <b>Quyền TKQC:</b> {access_name} ({perms_str})\n\n"
        f"<i>Tác vụ đã được phân luồng tự động và lưu vết vào hệ thống!</i>"
    )


def route_and_fulfill_client_task(
    session: Session,
    task: ClientTask,
    telegram_connector: Optional[TelegramBotConnector] = None,
) -> dict[str, Any]:
    """Kiểm tra cấu hình ưu tiên và thực hiện phân luồng tự động cho tác vụ BM/TKQC."""
    if task.task_type not in (TASK_TYPE_ADD_MAIL_TO_BM, TASK_TYPE_ADD_AD_ACCOUNT):
        return {"status": "SKIPPED", "reason": "Tác vụ không yêu cầu phân quyền BM."}

    if not task.customer_id:
        return {"status": "UNIDENTIFIED_CUSTOMER", "reason": "Tác vụ chưa gắn với khách hàng cụ thể."}

    client = session.get(Customer, task.customer_id)
    if not client:
        return {"status": "CLIENT_NOT_FOUND", "reason": "Không tìm thấy hồ sơ khách hàng."}

    pref = get_client_bm_preference(session, client.id)

    # 1. Trường hợp: ĐÃ CÓ CẤU HÌNH GHI NHỚ
    if pref:
        bm_info = AVAILABLE_BMS.get(pref.preferred_bm_id, {})
        bm_name = bm_info.get("name", pref.preferred_bm_id)
        synced_bm = session.scalar(select(SyncedBM).where(SyncedBM.bm_id == pref.preferred_bm_id))
        if synced_bm:
            bm_name = synced_bm.name

        # Tra cứu VIA Profile quản lý BM này
        managing_via = None
        if pref.via_profile_id:
            managing_via = session.get(ViaProfile, pref.via_profile_id)
        elif synced_bm and synced_bm.via_profile_id:
            managing_via = session.get(ViaProfile, synced_bm.via_profile_id)

        # Cập nhật thông tin định tuyến vào extracted_data của task
        extracted = {}
        if task.extracted_data:
            try:
                extracted = json.loads(task.extracted_data)
            except Exception:
                extracted = {}

        fulfillment_info = {
            "status": "AUTO_ROUTED",
            "preferred_bm_id": pref.preferred_bm_id,
            "bm_name": bm_name,
            "is_primary_rental": bool(synced_bm.is_primary_rental) if synced_bm else False,
            "via_profile_id": managing_via.id if managing_via else pref.via_profile_id,
            "via_uid": managing_via.uid if managing_via else None,
            "via_profile_dir": managing_via.profile_dir if managing_via else None,
            "proxy_routing": managing_via.proxy_config if managing_via else None,
            "bm_role": pref.bm_role,
            "ad_account_access_type": pref.ad_account_access_type,
            "partial_permissions": pref.get_permissions_list(),
            "auto_remembered": True,
        }
        extracted["fulfillment"] = fulfillment_info
        task.extracted_data = json.dumps(extracted, ensure_ascii=False)
        via_desc = f" (qua VIA {managing_via.uid})" if managing_via else ""
        task.notes = (
            f"Tự động định tuyến tới {bm_name}{via_desc} ({pref.bm_role}) - Quyền: {pref.ad_account_access_type} theo cấu hình đã lưu."
        )
        session.commit()

        # Gửi thông báo cho Admin qua Telegram nếu có kết nối
        if telegram_connector:
            try:
                notify_text = format_auto_routed_notification(client, task, pref)
                telegram_connector.send_admin_message(notify_text)
            except Exception as exc:
                logger.warning("Không thể gửi thông báo Telegram auto-routed: %s", exc)

        return {
            "status": "AUTO_ROUTED",
            "client_id": client.id,
            "client_name": client.name,
            "preference": {
                "preferred_bm_id": pref.preferred_bm_id,
                "bm_name": bm_name,
                "bm_role": pref.bm_role,
                "ad_account_access_type": pref.ad_account_access_type,
                "partial_permissions": pref.get_permissions_list(),
            },
        }

    # 2. Trường hợp: CHƯA CÓ CẤU HÌNH (Khách hàng mới cần prompt admin)
    prompt_text = format_interactive_telegram_prompt(client, task)

    # Ghi nhận trạng thái chờ Admin thiết lập vào task
    extracted = {}
    if task.extracted_data:
        try:
            extracted = json.loads(task.extracted_data)
        except Exception:
            extracted = {}

    extracted["fulfillment"] = {
        "status": "AWAITING_ADMIN_PREFERENCE_SELECTION",
        "prompt_sent": True,
        "available_bms": list(AVAILABLE_BMS.keys()),
    }
    task.extracted_data = json.dumps(extracted, ensure_ascii=False)
    session.commit()

    if telegram_connector:
        try:
            telegram_connector.send_admin_message(prompt_text)
        except Exception as exc:
            logger.warning("Không thể gửi interactive Telegram prompt: %s", exc)

    return {
        "status": "AWAITING_ADMIN_PREFERENCE_SELECTION",
        "client_id": client.id,
        "client_name": client.name,
        "prompt_text": prompt_text,
    }


def apply_admin_bm_selection(
    session: Session,
    client_id: int,
    preferred_bm_id: str,
    via_profile_id: Optional[int] = None,
    bm_role: str = BM_ROLE_EMPLOYEE,
    ad_account_access_type: str = ACCESS_TYPE_FULL,
    partial_permissions: Optional[list[str]] = None,
    task_id: Optional[int] = None,
    actor: str = "admin",
) -> dict[str, Any]:
    """Lưu lựa chọn của Admin vào cấu hình ưu tiên và áp dụng ngay cho tác vụ liên quan."""
    client = session.get(Customer, client_id)
    if not client:
        raise ValueError(f"Không tìm thấy khách hàng với ID {client_id}")

    # Chuẩn hoá permissions
    perms = partial_permissions if partial_permissions is not None else list(DEFAULT_PARTIAL_PERMISSIONS)

    pref = save_or_update_client_bm_preference(
        session=session,
        client_id=client.id,
        preferred_bm_id=preferred_bm_id,
        via_profile_id=via_profile_id,
        bm_role=bm_role,
        ad_account_access_type=ad_account_access_type,
        partial_permissions=perms,
        notes=f"Được thiết lập bởi {actor}",
        actor=actor,
    )

    # Nếu có task_id hoặc tìm các task đang chờ cấu hình của client này
    tasks_to_update = []
    if task_id:
        t = session.get(ClientTask, task_id)
        if t:
            tasks_to_update.append(t)
    else:
        pending_tasks = session.scalars(
            select(ClientTask).where(
                ClientTask.customer_id == client.id,
                ClientTask.task_type.in_([TASK_TYPE_ADD_MAIL_TO_BM, TASK_TYPE_ADD_AD_ACCOUNT]),
            )
        ).all()
        tasks_to_update.extend(pending_tasks)

    updated_count = 0
    for t in tasks_to_update:
        extracted = {}
        if t.extracted_data:
            try:
                extracted = json.loads(t.extracted_data)
            except Exception:
                extracted = {}
        extracted["fulfillment"] = {
            "status": "AUTO_ROUTED",
            "preferred_bm_id": pref.preferred_bm_id,
            "bm_name": AVAILABLE_BMS.get(pref.preferred_bm_id, {}).get("name", pref.preferred_bm_id),
            "bm_role": pref.bm_role,
            "ad_account_access_type": pref.ad_account_access_type,
            "partial_permissions": pref.get_permissions_list(),
            "applied_via_admin_selection": True,
        }
        t.extracted_data = json.dumps(extracted, ensure_ascii=False)
        t.notes = f"Đã áp dụng BM {pref.preferred_bm_id} ({pref.bm_role}) theo lựa chọn của Admin."
        updated_count += 1

    session.commit()

    return {
        "success": True,
        "client_id": client.id,
        "client_name": client.name,
        "preferred_bm_id": pref.preferred_bm_id,
        "via_profile_id": pref.via_profile_id,
        "bm_role": pref.bm_role,
        "ad_account_access_type": pref.ad_account_access_type,
        "partial_permissions": pref.get_permissions_list(),
        "updated_tasks_count": updated_count,
        "message": f"Đã ghi nhớ cấu hình phân quyền cho {client.name} và tự động cập nhật {updated_count} tác vụ liên quan.",
    }
