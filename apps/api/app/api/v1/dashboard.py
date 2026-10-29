"""Dashboard + quản lý khách/ad account (S5, D-032). Chỉ đọc cho dashboard;
ghi tài khoản (assign/replace/cost) qua service accounts.py, có audit log.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AdAccount, Customer
from app.services import accounts as account_service
from app.services import dashboard as dashboard_service
from app.services import operations_overview as operations_service

router = APIRouter()


def _lock_sqlite_assignments(db: Session) -> None:
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


# --- dashboard (read-only) ---


@router.get("/dashboard/overview")
def dashboard_overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    return dashboard_service.overview(db)


@router.get("/dashboard/operations-overview")
def dashboard_operations_overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    return operations_service.operations_overview(db)


@router.get("/dashboard/operations-overview/{metric}")
def dashboard_operations_list(metric: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return operations_service.operations_list(db, metric)
    except KeyError:
        raise HTTPException(404, "Chỉ số không tồn tại")


@router.get("/dashboard/campaigns")
def dashboard_campaigns(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return dashboard_service.campaign_rows(db)


@router.get("/dashboard/accounts")
def dashboard_accounts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return dashboard_service.account_rows(db)


@router.get("/dashboard/system")
def dashboard_system(db: Session = Depends(get_db)) -> dict[str, Any]:
    return dashboard_service.system_rows(db)


# --- danh sách tham chiếu cho form gắn account ---


@router.get("/customers")
def list_customers(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [
        {"id": c.id, "name": c.name, "recon_mode": c.recon_mode}
        for c in db.execute(select(Customer).order_by(Customer.name)).scalars().all()
    ]


@router.get("/ad-accounts")
def list_ad_accounts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [
        {
            "id": a.id,
            "meta_ad_account_id": a.meta_ad_account_id,
            "name": a.name,
            "status": a.status,
        }
        for a in db.execute(select(AdAccount).order_by(AdAccount.id)).scalars().all()
    ]


# --- quản lý tài khoản (ghi DB nội bộ, có audit) ---


class CustomerCreate(BaseModel):
    name: str
    telegram_chat_id: Optional[str] = None


class BudgetAlertThresholdUpdate(BaseModel):
    threshold_vnd: Optional[Decimal] = Field(..., ge=0, max_digits=18, decimal_places=2)


@router.patch("/customers/{customer_id}/budget-alert")
def update_budget_alert(customer_id: int, payload: BudgetAlertThresholdUpdate,
                        db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        customer = account_service.set_budget_alert_threshold(db, customer_id, payload.threshold_vnd)
        db.commit()
    except account_service.AccountError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"customer_id": customer.id, "threshold_vnd": str(customer.budget_alert_threshold_vnd)
            if customer.budget_alert_threshold_vnd is not None else None}


class AdAccountCreate(BaseModel):
    meta_ad_account_id: str
    name: str = ""
    timezone_name: str = "UTC"
    business_manager_id: Optional[str] = None


@router.post("/customers")
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        customer = account_service.create_customer(
            db, payload.name, telegram_chat_id=payload.telegram_chat_id
        )
        db.commit()
    except account_service.AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "CREATED", "customer_id": customer.id, "name": customer.name}


@router.post("/ad-accounts")
def create_ad_account(payload: AdAccountCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        account = account_service.create_ad_account(
            db,
            payload.meta_ad_account_id,
            name=payload.name,
            business_manager_id=payload.business_manager_id,
            timezone_name=payload.timezone_name,
        )
        db.commit()
    except account_service.AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "CREATED",
        "account_id": account.id,
        "meta_ad_account_id": account.meta_ad_account_id,
        "account_status": account.status,
    }


class AssignRequest(BaseModel):
    customer_id: int
    ad_account_id: int
    valid_from: Optional[datetime] = None


@router.post("/accounts/assign")
def assign_account(payload: AssignRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        _lock_sqlite_assignments(db)
        assignment = account_service.assign_account(
            db, payload.customer_id, payload.ad_account_id, valid_from=payload.valid_from
        )
        db.commit()
    except account_service.AccountError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account đã được phân công; tải lại trước khi thử.") from exc
    except OperationalError as exc:
        db.rollback()
        if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
            raise
        raise HTTPException(status_code=409, detail="Tài khoản đang được cập nhật; tải lại và thử lại.") from exc
    return {"status": "ASSIGNED", "assignment_id": assignment.id}


class TransferRequest(BaseModel):
    ad_account_id: int
    customer_id: int
    expected_assignment_id: int


@router.post("/accounts/transfer")
def transfer_account(payload: TransferRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        _lock_sqlite_assignments(db)
        assignment = account_service.transfer_account(
            db, payload.ad_account_id, payload.customer_id, payload.expected_assignment_id)
        db.commit()
    except account_service.AccountError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Phân công xung đột; tải lại trước khi chuyển.") from exc
    except OperationalError as exc:
        db.rollback()
        if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
            raise
        raise HTTPException(status_code=409, detail="Tài khoản đang được cập nhật; tải lại và thử lại.") from exc
    return {"status": "TRANSFERRED", "assignment_id": assignment.id,
            "valid_from": assignment.valid_from.isoformat()}


class ReplaceRequest(BaseModel):
    old_account_id: int
    new_meta_ad_account_id: str
    new_name: str = ""
    new_timezone_name: str = "UTC"
    new_business_manager_id: Optional[str] = None


@router.post("/accounts/replace")
def replace_restricted_account(payload: ReplaceRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        _lock_sqlite_assignments(db)
        new_account = account_service.replace_account(
            db,
            payload.old_account_id,
            payload.new_meta_ad_account_id,
            new_name=payload.new_name,
            new_timezone_name=payload.new_timezone_name,
            new_business_manager_id=payload.new_business_manager_id,
        )
        db.commit()
    except account_service.AccountError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account mới đã được phân công; tải lại và rà soát.") from exc
    except OperationalError as exc:
        db.rollback()
        if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
            raise
        raise HTTPException(status_code=409, detail="Tài khoản đang được cập nhật; tải lại và thử lại.") from exc
    return {"status": "REPLACED", "new_account_id": new_account.id}


class PurchaseCostRequest(BaseModel):
    cost: Decimal = Field(gt=-1, description="Chi phí mua tài khoản")


@router.post("/accounts/{account_id}/purchase-cost")
def set_purchase_cost(account_id: int, payload: PurchaseCostRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        account = account_service.set_purchase_cost(db, account_id, payload.cost)
        db.commit()
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Chi phí mua không hợp lệ")
    except account_service.AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "OK", "account_id": account.id, "purchase_cost": str(account.purchase_cost)}


class RestrictedRequest(BaseModel):
    note: Optional[str] = None


@router.post("/accounts/{account_id}/restrict")
def restrict_account(account_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        account = account_service.restrict_account(db, account_id)
        db.commit()
    except account_service.AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "RESTRICTED", "account_id": account.id}
