"""Quản lý ad account (S5/D-032): gắn account với khách, thay thế account, chi phí mua.

- CHỈ THÊM lịch sử (append) — không xoá assignment/account cũ.
- Thay account bị hạn chế: account cũ → status REPLACED + replaced_by, gán khách
  sang account mới; lịch sử giữ nguyên.
- Mọi thay đổi ghi audit log.
- KHÔNG ghi Google Sheets; đây là tác vụ ghi DB nội bộ, không phải giao dịch tiền thật
  (chi phí mua chỉ là tham số lưu trữ).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models import AuditLog, AdAccount, AdAccountAssignment, Customer
from app.models.ad_account import ACCOUNT_ACTIVE, ACCOUNT_REPLACED
from app.models.customer import utcnow


class AccountError(Exception):
    pass


def _audit(session: Session, actor: str, action: str, entity_type: str, entity_id: str, detail: dict) -> None:
    session.add(AuditLog(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id, detail=detail))


def set_budget_alert_threshold(session: Session, customer_id: int, value: Decimal | None,
                               actor: str = "admin") -> Customer:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise AccountError("Không tìm thấy khách hàng")
    previous = customer.budget_alert_threshold_vnd
    customer.budget_alert_threshold_vnd = value
    _audit(session, actor, "customer_budget_alert_threshold_set", "customer", str(customer_id), {
        "previous": str(previous) if previous is not None else None,
        "value": str(value) if value is not None else None,
        "currency": "VND",
    })
    session.flush()
    return customer


def assign_account(
    session: Session,
    customer_id: int,
    ad_account_id: int,
    valid_from: Optional[datetime] = None,
    actor: str = "admin",
) -> AdAccountAssignment:
    customer = session.get(Customer, customer_id)
    account = session.scalar(select(AdAccount).where(AdAccount.id == ad_account_id).with_for_update())
    if customer is None or account is None:
        raise AccountError("Không tìm thấy khách hoặc ad account")
    now = utcnow()
    if valid_from is not None:
        if valid_from.tzinfo is None:
            raise AccountError("Thời điểm hiệu lực phải có múi giờ")
        valid_from = valid_from.astimezone(timezone.utc)
        if valid_from > now:
            raise AccountError("Chưa hỗ trợ gán tài khoản có hiệu lực trong tương lai")
    existing_rows = session.execute(
        select(AdAccountAssignment).where(
            AdAccountAssignment.customer_id == customer_id,
            AdAccountAssignment.ad_account_id == ad_account_id,
            AdAccountAssignment.valid_to.is_(None),
        )
    ).scalars().all()
    if len(existing_rows) > 1:
        raise AccountError("Phân công đang mở bị trùng; cần rà soát trước khi gán")
    if existing_rows:
        existing = existing_rows[0]
        if valid_from is not None and existing.valid_from != valid_from:
            raise AccountError("Phân công đang mở có thời điểm hiệu lực khác; không tự sửa lịch sử")
        return existing
    if account.status != ACCOUNT_ACTIVE:
        raise AccountError(f"Chỉ gán được account trạng thái ACTIVE (hiện tại: {account.status})")
    other_open = session.execute(
        select(AdAccountAssignment).where(
            AdAccountAssignment.ad_account_id == ad_account_id,
            AdAccountAssignment.valid_to.is_(None),
            AdAccountAssignment.customer_id != customer_id,
        ).limit(1)
    ).scalar_one_or_none()
    if other_open is not None:
        raise AccountError(
            f"Account đang được gán cho khách #{other_open.customer_id} — một account chỉ phục vụ một khách tại một thời điểm"
        )
    valid_from = valid_from or now
    overlap = session.scalar(select(AdAccountAssignment.id).where(
        AdAccountAssignment.ad_account_id == ad_account_id,
        or_(AdAccountAssignment.valid_to.is_(None), AdAccountAssignment.valid_to > valid_from),
    ).limit(1))
    if overlap is not None:
        raise AccountError("Thời điểm hiệu lực chồng lấn lịch sử phân công")
    assignment = AdAccountAssignment(
        customer_id=customer_id, ad_account_id=ad_account_id, valid_from=valid_from
    )
    session.add(assignment)
    _audit(session, actor, "account_assigned", "ad_account", str(ad_account_id), {"customer_id": customer_id})
    session.flush()
    return assignment


def transfer_account(session: Session, ad_account_id: int, customer_id: int,
                     expected_assignment_id: int, actor: str = "admin") -> AdAccountAssignment:
    account = session.scalar(select(AdAccount).where(AdAccount.id == ad_account_id).with_for_update())
    customer = session.get(Customer, customer_id)
    if account is None or customer is None:
        raise AccountError("Không tìm thấy khách hoặc ad account")
    if account.status != ACCOUNT_ACTIVE:
        raise AccountError("Chỉ chuyển account ở trạng thái ACTIVE")
    now = utcnow()
    assignments = session.scalars(select(AdAccountAssignment).where(
        AdAccountAssignment.ad_account_id == ad_account_id,
        or_(AdAccountAssignment.valid_to.is_(None), AdAccountAssignment.valid_to > now),
    )).all()
    if (len(assignments) != 1 or assignments[0].valid_to is not None
            or assignments[0].valid_from >= now):
        raise AccountError("Phân công hiện tại không rõ ràng; cần rà soát trước khi chuyển")
    previous = assignments[0]
    if previous.id != expected_assignment_id:
        raise AccountError("Phân công đã thay đổi; tải lại trước khi chuyển")
    if previous.customer_id == customer_id:
        raise AccountError("Account đã được phân công cho khách này")
    result = session.execute(update(AdAccountAssignment).where(
        AdAccountAssignment.id == previous.id, AdAccountAssignment.valid_to.is_(None),
    ).values(valid_to=now))
    if result.rowcount != 1:
        raise AccountError("Phân công đã thay đổi; tải lại trước khi chuyển")
    assignment = AdAccountAssignment(customer_id=customer_id, ad_account_id=ad_account_id, valid_from=now)
    session.add(assignment)
    _audit(session, actor, "account_transferred", "ad_account", str(ad_account_id), {
        "previous_assignment_id": previous.id, "previous_customer_id": previous.customer_id,
        "customer_id": customer_id, "effective_at": now.isoformat(),
    })
    session.flush()
    return assignment


def replace_account(
    session: Session,
    old_account_id: int,
    new_meta_ad_account_id: str,
    new_name: str = "",
    new_timezone_name: str = "UTC",
    new_business_manager_id: Optional[str] = None,
    actor: str = "admin",
) -> AdAccount:
    """Account cũ bị hạn chế → REPLACED; khách đang dùng chuyển sang account mới."""
    old = session.scalar(select(AdAccount).where(AdAccount.id == old_account_id).with_for_update())
    if old is None:
        raise AccountError("Không tìm thấy account cũ")
    if old.status == ACCOUNT_REPLACED:
        raise AccountError("Account cũ đã được thay thế")
    now = utcnow()
    active_assignments = session.execute(
        select(AdAccountAssignment).where(
            AdAccountAssignment.ad_account_id == old.id,
            AdAccountAssignment.valid_to.is_(None),
        )
    ).scalars().all()
    if len(active_assignments) > 1 or any(item.valid_from > now for item in active_assignments):
        raise AccountError("Phân công account cũ mơ hồ; cần rà soát trước khi thay")
    existing = session.execute(
        select(AdAccount).where(AdAccount.meta_ad_account_id == new_meta_ad_account_id).with_for_update()
    ).scalar_one_or_none()
    if existing is not None:
        if existing.id == old.id:
            raise AccountError("Account mới phải khác account cũ")
        if existing.status != ACCOUNT_ACTIVE:
            raise AccountError("Account mới không ở trạng thái ACTIVE")
        occupied = session.scalar(select(AdAccountAssignment.id).where(
            AdAccountAssignment.ad_account_id == existing.id,
            or_(AdAccountAssignment.valid_to.is_(None), AdAccountAssignment.valid_to > now),
        ).limit(1))
        if occupied is not None:
            raise AccountError("Account mới đã được phân công; cần rà soát trước khi thay")
        new_account = existing
    else:
        new_account = AdAccount(
            meta_ad_account_id=new_meta_ad_account_id,
            name=new_name or new_meta_ad_account_id,
            timezone_name=new_timezone_name,
            status=ACCOUNT_ACTIVE,
            business_manager_id=new_business_manager_id,
        )
        session.add(new_account)
        session.flush()
    old.status = ACCOUNT_REPLACED
    old.replaced_by_id = new_account.id
    # chuyển khách đang dùng account cũ sang account mới; lịch sử cũ giữ nguyên
    moved_customer_ids: set[int] = set()
    for assignment in active_assignments:
        assignment.valid_to = now
        if assignment.customer_id in moved_customer_ids:
            continue  # phòng hờ dữ liệu cũ có 2 assignment mở — mỗi khách chỉ chuyển 1 lần
        moved_customer_ids.add(assignment.customer_id)
        session.add(
            AdAccountAssignment(
                customer_id=assignment.customer_id,
                ad_account_id=new_account.id,
                valid_from=now,
            )
        )
    _audit(
        session,
        actor,
        "account_replaced",
        "ad_account",
        str(old.id),
        {"new_account_id": new_account.id, "customers_moved": len(active_assignments)},
    )
    session.flush()
    return new_account


def set_purchase_cost(
    session: Session,
    ad_account_id: int,
    cost: Decimal,
    actor: str = "admin",
) -> AdAccount:
    account = session.get(AdAccount, ad_account_id)
    if account is None:
        raise AccountError("Không tìm thấy ad account")
    account.purchase_cost = cost
    _audit(session, actor, "purchase_cost_set", "ad_account", str(ad_account_id), {"cost": str(cost)})
    session.flush()
    return account


def restrict_account(
    session: Session,
    ad_account_id: int,
    actor: str = "admin",
) -> AdAccount:
    """Đánh dấu account bị hạn chế (RESTRICTED) — thay thế bằng replace_account."""
    from app.models.ad_account import ACCOUNT_RESTRICTED

    account = session.get(AdAccount, ad_account_id)
    if account is None:
        raise AccountError("Không tìm thấy ad account")
    account.status = ACCOUNT_RESTRICTED
    account.restricted_at = utcnow()
    _audit(session, actor, "account_restricted", "ad_account", str(ad_account_id), {})
    session.flush()
    return account


def create_customer(
    session: Session,
    name: str,
    telegram_chat_id: Optional[str] = None,
    actor: str = "admin",
) -> Customer:
    """Tạo khách mới (chỉ thêm; không có DELETE — D-002 giữ lịch sử)."""
    name = (name or "").strip()
    if not name:
        raise AccountError("Tên khách không được rỗng")
    duplicate = session.execute(
        select(Customer).where(Customer.name == name)
    ).scalar_one_or_none()
    if duplicate is not None:
        raise AccountError(f"Khách '{name}' đã tồn tại")
    customer = Customer(name=name, telegram_chat_id=telegram_chat_id)
    session.add(customer)
    _audit(session, actor, "customer_created", "customer", name, {"telegram_chat_id": telegram_chat_id})
    session.flush()
    return customer


def create_ad_account(
    session: Session,
    meta_ad_account_id: str,
    name: str = "",
    business_manager_id: Optional[str] = None,
    timezone_name: str = "UTC",
    actor: str = "admin",
) -> AdAccount:
    """Nhập ad account mới vào hệ thống (ACTIVE mặc định). Trùng Act ID bị chặn."""
    meta_ad_account_id = (meta_ad_account_id or "").strip()
    if not meta_ad_account_id:
        raise AccountError("Act ID không được rỗng")
    existing = session.execute(
        select(AdAccount).where(AdAccount.meta_ad_account_id == meta_ad_account_id)
    ).scalar_one_or_none()
    if existing is not None:
        raise AccountError(f"Ad account {meta_ad_account_id} đã tồn tại")
    account = AdAccount(
        meta_ad_account_id=meta_ad_account_id,
        name=name or meta_ad_account_id,
        business_manager_id=business_manager_id,
        timezone_name=timezone_name or "UTC",
        status=ACCOUNT_ACTIVE,
    )
    session.add(account)
    _audit(session, actor, "account_created", "ad_account", meta_ad_account_id, {})
    session.flush()
    return account
