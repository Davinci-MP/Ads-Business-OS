"""API Quản lý kho tài nguyên quảng cáo (VIA, BM, Fanpage, Proxy) có mã hóa Fernet."""

from __future__ import annotations

from typing import Any, Optional

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.local_admin import require_local_admin_or_owner
from app.db import get_db
from app.models.customer import Customer
from app.models.finance import AuditLog
from app.models.inventory import (
    ITEM_TYPE_BM,
    ITEM_TYPE_PAGE,
    ITEM_TYPE_PROXY,
    ITEM_TYPE_VIA,
    STATUS_AVAILABLE,
    STATUS_ASSIGNED,
    STATUS_DEAD,
    InventoryItem,
)

router = APIRouter(prefix="/inventory", tags=["kho-tai-nguyen"], dependencies=[Depends(require_local_admin_or_owner)])


def _get_fernet() -> Optional[Fernet]:
    master_key = (settings.exchange_master_key or "").strip()
    if master_key:
        try:
            return Fernet(master_key.encode("utf-8"))
        except Exception:
            return None
    return None


def encrypt_credentials(raw_text: str) -> str:
    """Mã hóa thông tin đăng nhập bằng Fernet; cấm fallback plaintext nếu thiếu master key."""
    if not raw_text:
        return ""
    f = _get_fernet()
    if f is None:
        raise RuntimeError("Chưa cấu hình ADSOS_EXCHANGE_MASTER_KEY hợp lệ để mã hóa tài nguyên kho")
    return f.encrypt(raw_text.encode("utf-8")).decode("utf-8")


def decrypt_credentials(encrypted_text: str) -> str:
    """Giải mã an toàn thông tin tài nguyên."""
    if not encrypted_text:
        return ""
    if encrypted_text.startswith("plain::"):
        return encrypted_text[7:]
    f = _get_fernet()
    if f is not None:
        try:
            return f.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
        except Exception:
            return "[Lỗi giải mã: Khóa bảo mật không khớp]"
    return "[Chưa cấu hình ADSOS_EXCHANGE_MASTER_KEY để giải mã]"


class CreateInventoryItemRequest(BaseModel):
    item_type: str = Field(..., description="VIA, BM, PAGE, PROXY")
    name: str = Field(..., min_length=1, max_length=255)
    credentials: str = Field(..., min_length=1, description="UID|Pass|2FA hoặc Link mời BM hoặc IP:Port:User:Pass")
    notes: Optional[str] = None
    assigned_customer_id: Optional[int] = None
    assigned_ad_account_id: Optional[str] = None


class HandoverRequest(BaseModel):
    customer_id: int
    assigned_ad_account_id: Optional[str] = None
    actor: str = Field("web_ui", min_length=1)


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., description="AVAILABLE, ASSIGNED, DEAD")
    notes: Optional[str] = None


def _format_item(item: InventoryItem, customer_name: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "name": item.name,
        "status": item.status,
        "assigned_customer_id": item.assigned_customer_id,
        "customer_name": customer_name,
        "assigned_ad_account_id": item.assigned_ad_account_id,
        "notes": item.notes,
        "has_credentials": bool(item.encrypted_credentials),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("")
def list_inventory_items(
    item_type: Optional[str] = Query(None, description="Lọc theo loại: VIA, BM, PAGE, PROXY"),
    status: Optional[str] = Query(None, description="Lọc theo trạng thái: AVAILABLE, ASSIGNED, DEAD"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lấy danh sách tài nguyên trong kho kèm thông tin khách hàng bàn giao (ẩn mật khẩu)."""
    stmt = select(InventoryItem).order_by(desc(InventoryItem.id))
    if item_type:
        stmt = stmt.where(InventoryItem.item_type == item_type.upper())
    if status:
        stmt = stmt.where(InventoryItem.status == status.upper())

    items = db.scalars(stmt).all()
    customers_map = {c.id: c.name for c in db.scalars(select(Customer)).all()}

    return [_format_item(item, customers_map.get(item.assigned_customer_id)) for item in items]


@router.post("")
def create_inventory_item(
    req: CreateInventoryItemRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Thêm tài nguyên mới vào kho với thông tin đăng nhập được mã hóa an toàn."""
    valid_types = {ITEM_TYPE_VIA, ITEM_TYPE_BM, ITEM_TYPE_PAGE, ITEM_TYPE_PROXY}
    upper_type = req.item_type.upper()
    if upper_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Loại tài nguyên không hợp lệ. Phải là một trong các loại: {', '.join(valid_types)}",
        )

    if req.assigned_customer_id:
        cust = db.get(Customer, req.assigned_customer_id)
        if not cust:
            raise HTTPException(status_code=400, detail="Không tìm thấy khách hàng được chỉ định.")

    enc = encrypt_credentials(req.credentials.strip())
    initial_status = STATUS_ASSIGNED if req.assigned_customer_id else STATUS_AVAILABLE

    item = InventoryItem(
        item_type=upper_type,
        name=req.name.strip(),
        encrypted_credentials=enc,
        status=initial_status,
        assigned_customer_id=req.assigned_customer_id,
        assigned_ad_account_id=req.assigned_ad_account_id.strip() if req.assigned_ad_account_id else None,
        notes=req.notes.strip() if req.notes else None,
    )
    db.add(item)
    db.flush()

    db.add(
        AuditLog(
            actor="web_ui",
            action="CREATE_INVENTORY_ITEM",
            entity_type="inventory_item",
            entity_id=str(item.id),
            detail={"item_type": item.item_type, "name": item.name, "status": item.status},
        )
    )
    db.commit()
    db.refresh(item)

    customer_name = item.customer.name if item.customer else None
    return _format_item(item, customer_name)


@router.get("/{item_id}/credentials")
def get_inventory_credentials(
    item_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Giải mã và hiển thị thông tin đăng nhập của tài nguyên (yêu cầu quản trị local)."""
    item = db.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên trong kho.")

    raw_credentials = decrypt_credentials(item.encrypted_credentials)
    return {
        "id": item.id,
        "name": item.name,
        "item_type": item.item_type,
        "credentials": raw_credentials,
    }


@router.post("/{item_id}/handover")
def handover_inventory_item(
    item_id: int,
    req: HandoverRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Bàn giao tài nguyên cho khách hàng và tài khoản quảng cáo."""
    item = db.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên trong kho.")

    customer = db.get(Customer, req.customer_id)
    if not customer:
        raise HTTPException(status_code=400, detail="Không tìm thấy khách hàng để bàn giao.")

    item.assigned_customer_id = req.customer_id
    if req.assigned_ad_account_id:
        item.assigned_ad_account_id = req.assigned_ad_account_id.strip()
    item.status = STATUS_ASSIGNED

    db.add(
        AuditLog(
            actor=req.actor,
            action="INVENTORY_HANDOVER",
            entity_type="inventory_item",
            entity_id=str(item.id),
            detail={
                "customer_id": req.customer_id,
                "customer_name": customer.name,
                "ad_account_id": item.assigned_ad_account_id,
            },
        )
    )
    db.commit()
    db.refresh(item)

    raw_credentials = decrypt_credentials(item.encrypted_credentials)
    formatted = _format_item(item, customer.name)
    formatted["credentials"] = raw_credentials
    return formatted


@router.patch("/{item_id}/status")
def update_inventory_status(
    item_id: int,
    req: UpdateStatusRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật trạng thái tài nguyên (AVAILABLE, ASSIGNED, DEAD)."""
    item = db.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên trong kho.")

    valid_statuses = {STATUS_AVAILABLE, STATUS_ASSIGNED, STATUS_DEAD}
    upper_status = req.status.upper()
    if upper_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Trạng thái không hợp lệ. Phải là một trong: {', '.join(valid_statuses)}",
        )

    old_status = item.status
    item.status = upper_status
    if req.notes is not None:
        item.notes = req.notes.strip()

    db.add(
        AuditLog(
            actor="web_ui",
            action="UPDATE_INVENTORY_STATUS",
            entity_type="inventory_item",
            entity_id=str(item.id),
            detail={"old_status": old_status, "new_status": item.status},
        )
    )
    db.commit()
    db.refresh(item)

    cust_name = item.customer.name if item.customer else None
    return _format_item(item, cust_name)


@router.delete("/{item_id}")
def delete_inventory_item(
    item_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Xóa tài nguyên khỏi kho."""
    item = db.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên trong kho.")

    db.add(
        AuditLog(
            actor="web_ui",
            action="DELETE_INVENTORY_ITEM",
            entity_type="inventory_item",
            entity_id=str(item.id),
            detail={"name": item.name, "item_type": item.item_type},
        )
    )
    db.delete(item)
    db.commit()
    return {"message": f"Đã xóa tài nguyên #{item_id} ({item.name}) khỏi kho."}
