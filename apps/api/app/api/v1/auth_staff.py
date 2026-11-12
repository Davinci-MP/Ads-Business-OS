from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    get_current_staff,
    log_staff_action,
    mask_sensitive_data,
    require_owner,
)
from app.db import get_db
from app.models.customer import Customer
from app.models.staff import StaffAuditLog, StaffUser, hash_password, verify_password

StaffRole = Literal["OWNER", "STAFF_OPS", "STAFF_SUPPORT", "ACCOUNTANT"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class StaffCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(default="", max_length=200)
    password: str = Field(min_length=8, max_length=200)
    role: StaffRole
    assigned_customer_ids: list[int] = Field(default_factory=list)


class StaffUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: StaffRole | None = None
    assigned_customer_ids: list[int] | None = None
    is_active: bool | None = None


def _validate_customer_ids(db: Session, customer_ids: list[int]) -> list[int]:
    cleaned = sorted(set(customer_ids))
    if not cleaned:
        return []
    existing = set(db.scalars(select(Customer.id).where(Customer.id.in_(cleaned))).all())
    missing = [customer_id for customer_id in cleaned if customer_id not in existing]
    if missing:
        raise HTTPException(status_code=422, detail=f"Không tìm thấy khách hàng: {', '.join(map(str, missing))}.")
    return cleaned


auth_router = APIRouter(prefix="/auth", tags=["Xác thực nhân sự"])
staff_router = APIRouter(prefix="/staff", tags=["Quản lý nhân sự"])
router = auth_router


@auth_router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(StaffUser).where(StaffUser.username == payload.username.strip()))
    if user is None or not user.is_active or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng.")
    user.last_login_at = datetime.now(timezone.utc)
    log_staff_action(db, user, "LOGIN", detail="Đăng nhập thành công.")
    db.commit()
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": mask_sensitive_data(user),
    }


@auth_router.get("/me")
def me(current_staff: StaffUser = Depends(get_current_staff)) -> dict:
    return mask_sensitive_data(current_staff)


@auth_router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_staff: StaffUser = Depends(get_current_staff),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not verify_password(current_staff.password_hash, payload.old_password):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng.")
    current_staff.password_hash = hash_password(payload.new_password)
    log_staff_action(db, current_staff, "UPDATE_ACCOUNT", detail="Đã đổi mật khẩu cá nhân.")
    db.commit()
    return {"message": "Đổi mật khẩu thành công."}


@staff_router.get("")
def list_staff(
    _: StaffUser = Depends(require_owner),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [mask_sensitive_data(user) for user in db.scalars(select(StaffUser).order_by(StaffUser.id)).all()]


@staff_router.post("", status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffCreateRequest,
    current_staff: StaffUser = Depends(require_owner),
    db: Session = Depends(get_db),
) -> dict:
    username = payload.username.strip()
    if db.scalar(select(StaffUser).where(StaffUser.username == username)) is not None:
        raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại.")
    assigned_ids = _validate_customer_ids(db, payload.assigned_customer_ids)
    user = StaffUser(
        username=username,
        full_name=payload.full_name.strip(),
        email=payload.email.strip() or None,
        password_hash=hash_password(payload.password),
        role=payload.role,
        assigned_customer_ids=assigned_ids,
        is_active=True,
    )
    db.add(user)
    db.flush()
    log_staff_action(db, current_staff, "STAFF_CRUD", detail=f"Đã tạo nhân sự {username} với vai trò {payload.role}.")
    db.commit()
    db.refresh(user)
    return {**mask_sensitive_data(user), "message": "Tạo nhân viên thành công."}


@staff_router.patch("/{staff_id}")
def update_staff(
    staff_id: int,
    payload: StaffUpdateRequest,
    current_staff: StaffUser = Depends(require_owner),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(StaffUser, staff_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.email is not None:
        user.email = payload.email.strip() or None
    if payload.role is not None:
        if user.role == "OWNER" and payload.role != "OWNER":
            owner_count = db.query(StaffUser).filter(StaffUser.role == "OWNER", StaffUser.is_active.is_(True)).count()
            if owner_count <= 1:
                raise HTTPException(status_code=409, detail="Không thể hạ quyền OWNER đang hoạt động cuối cùng.")
        user.role = payload.role
    if payload.assigned_customer_ids is not None:
        user.assigned_customer_ids = _validate_customer_ids(db, payload.assigned_customer_ids)
    if payload.is_active is not None:
        if user.id == current_staff.id and not payload.is_active:
            raise HTTPException(status_code=409, detail="Bạn không thể tự khóa tài khoản đang đăng nhập.")
        user.is_active = payload.is_active
    if payload.password:
        user.password_hash = hash_password(payload.password)
    log_staff_action(db, current_staff, "STAFF_CRUD", detail=f"Đã cập nhật nhân sự {user.username}.")
    db.commit()
    db.refresh(user)
    return {**mask_sensitive_data(user), "message": "Cập nhật nhân viên thành công."}


@staff_router.delete("/{staff_id}")
def delete_staff(
    staff_id: int,
    current_staff: StaffUser = Depends(require_owner),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = db.get(StaffUser, staff_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")
    if user.id == current_staff.id:
        raise HTTPException(status_code=409, detail="Bạn không thể tự vô hiệu hóa tài khoản đang đăng nhập.")
    if user.role == "OWNER":
        owner_count = db.query(StaffUser).filter(StaffUser.role == "OWNER", StaffUser.is_active.is_(True)).count()
        if owner_count <= 1:
            raise HTTPException(status_code=409, detail="Không thể vô hiệu hóa OWNER cuối cùng.")
    user.is_active = False
    log_staff_action(db, current_staff, "STAFF_CRUD", detail=f"Đã vô hiệu hóa nhân sự {user.username}.")
    db.commit()
    return {"message": "Đã vô hiệu hóa nhân viên và giữ nguyên lịch sử thao tác."}


@staff_router.get("/audit-logs")
def list_audit_logs(
    username: str | None = None,
    role: str | None = None,
    action_type: str | None = None,
    log_status: str | None = None,
    _: StaffUser = Depends(require_owner),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(StaffAuditLog)
    if username:
        query = query.where(StaffAuditLog.username == username)
    if role:
        query = query.where(StaffAuditLog.role == role)
    if action_type:
        query = query.where(StaffAuditLog.action_type == action_type)
    if log_status:
        query = query.where(StaffAuditLog.status == log_status)
    logs = db.scalars(query.order_by(StaffAuditLog.created_at.desc()).limit(500)).all()
    return [
        {
            "id": log.id,
            "staff_id": log.staff_id,
            "username": log.username,
            "role": log.role,
            "action_type": log.action_type,
            "target_bm_id": log.target_bm_id,
            "target_account_ids": log.target_account_ids,
            "recipient_info": log.recipient_info,
            "status": log.status,
            "detail": log.detail,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
