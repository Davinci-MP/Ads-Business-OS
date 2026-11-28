"""API Quản lý Khách hàng & Cấu hình Ghi nhớ Phân quyền Multi-BM (Client BM Preferences)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.local_admin import require_local_admin_or_owner
from app.db import get_db
from app.models.client_bm_preference import (
    ACCESS_TYPE_FULL,
    ACCESS_TYPE_PARTIAL,
    BM_ROLE_ADMIN,
    BM_ROLE_EMPLOYEE,
    DEFAULT_PARTIAL_PERMISSIONS,
    ClientBMPreference,
)
from app.models.customer import Customer
from app.models.via import SyncedBM, ViaProfile
from app.services.auto_fulfillment import (
    ACCESS_TYPE_LABELS,
    AVAILABLE_BMS,
    BM_ROLE_LABELS,
    PERMISSION_LABELS,
    get_available_bms,
    get_client_bm_preference,
    save_or_update_client_bm_preference,
)

router = APIRouter(tags=["clients-multi-bm"], dependencies=[Depends(require_local_admin_or_owner)])


class UpdateBMPreferenceRequest(BaseModel):
    preferred_bm_id: Optional[str] = Field(None, description="BM_01, BM_02, BM_03 hoặc ID BM Meta")
    via_profile_id: Optional[int] = Field(None, description="ID của VIA Profile quản lý BM này")
    bm_role: Optional[str] = Field(None, description="EMPLOYEE hoặc ADMIN")
    ad_account_access_type: Optional[str] = Field(None, description="FULL hoặc PARTIAL")
    partial_permissions: Optional[list[str]] = Field(None, description="Danh sách quyền: MANAGE_CAMPAIGNS, VIEW_PERFORMANCE, CREATIVE_HUB")
    notes: Optional[str] = None
    actor: str = Field("web_ui", min_length=1)


def _serialize_pref(
    client: Customer,
    pref: Optional[ClientBMPreference],
    synced_bms_map: Optional[dict[str, SyncedBM]] = None,
) -> dict[str, Any]:
    bm_id = pref.preferred_bm_id if pref else "BM_01"
    bm_meta = AVAILABLE_BMS.get(bm_id, {})
    synced = synced_bms_map.get(bm_id) if synced_bms_map else None

    bm_name = synced.name if synced else bm_meta.get("name", bm_id)
    bm_full_name = (
        f"{'★ [BM Cho Thuê] ' if synced and synced.is_primary_rental else ''}{synced.name}"
        if synced
        else bm_meta.get("full_name", bm_id)
    )
    is_primary = bool(synced.is_primary_rental) if synced else False

    via_id = pref.via_profile_id if pref and pref.via_profile_id else (synced.via_profile_id if synced else None)
    via_uid = pref.via_profile.uid if pref and pref.via_profile else (synced.via_profile.uid if synced and synced.via_profile else None)
    via_name = pref.via_profile.profile_name if pref and pref.via_profile else (synced.via_profile.profile_name if synced and synced.via_profile else None)

    role = pref.bm_role if pref else BM_ROLE_EMPLOYEE
    access = pref.ad_account_access_type if pref else ACCESS_TYPE_FULL
    perms = pref.get_permissions_list() if pref else list(DEFAULT_PARTIAL_PERMISSIONS)

    return {
        "client_id": client.id,
        "customer_id": client.id,
        "customer_name": client.name,
        "preferred_bm_id": bm_id,
        "bm_name": bm_name,
        "bm_full_name": bm_full_name,
        "is_primary_rental": is_primary,
        "via_profile_id": via_id,
        "via_uid": via_uid,
        "via_profile_name": via_name,
        "bm_role": role,
        "bm_role_label": BM_ROLE_LABELS.get(role, role),
        "ad_account_access_type": access,
        "ad_account_access_label": ACCESS_TYPE_LABELS.get(access, access),
        "partial_permissions": perms,
        "partial_permissions_labels": [PERMISSION_LABELS.get(p, p) for p in perms],
        "is_configured": pref is not None,
        "notes": pref.notes if pref else None,
        "updated_at": pref.updated_at.isoformat() if pref and pref.updated_at else None,
    }


# --- Metadata & Configuration Options ---

@router.get("/clients/bm-options")
@router.get("/customers/bm-options")
def get_bm_routing_options(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Danh mục cấu hình Business Manager, Vai trò và Quyền hạn TKQC khả dụng."""
    return {
        "available_bms": get_available_bms(db),
        "roles": [
            {"value": BM_ROLE_EMPLOYEE, "label": "Nhân viên (EMPLOYEE)", "description": "Quyền tài nguyên được chỉ định, không quản lý nhân sự BM"},
            {"value": BM_ROLE_ADMIN, "label": "Quản trị viên (ADMIN)", "description": "Toàn quyền kiểm soát và gán tài nguyên trong BM"},
        ],
        "access_types": [
            {"value": ACCESS_TYPE_FULL, "label": "Truy cập đầy đủ (FULL)", "description": "Toàn quyền quản lý chiến dịch, ngân sách và báo cáo"},
            {"value": ACCESS_TYPE_PARTIAL, "label": "Truy cập một phần (PARTIAL)", "description": "Chỉ định danh mục quyền giới hạn"},
        ],
        "partial_permissions": [
            {"key": "MANAGE_CAMPAIGNS", "label": "Quản lý chiến dịch", "description": "Tạo, sửa, bật/tắt quảng cáo"},
            {"key": "VIEW_PERFORMANCE", "label": "Xem hiệu quả", "description": "Xem báo cáo số liệu và chi tiêu"},
            {"key": "CREATIVE_HUB", "label": "Creative Hub", "description": "Tạo mockup và kiểm duyệt mẫu quảng cáo"},
        ],
    }


# --- List All Preferences ---

@router.get("/clients/preferences")
@router.get("/customers/preferences")
def list_all_client_bm_preferences(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Lấy danh sách cấu hình phân quyền BM của tất cả khách hàng."""
    clients = db.scalars(select(Customer).order_by(Customer.id)).all()
    prefs_map = {p.client_id: p for p in db.scalars(select(ClientBMPreference)).all()}
    synced_bms_map = {b.bm_id: b for b in db.scalars(select(SyncedBM)).all()}

    return [_serialize_pref(c, prefs_map.get(c.id), synced_bms_map=synced_bms_map) for c in clients]


# --- Single Client Preference Read & Override ---

@router.get("/clients/{client_id}/bm-preferences")
@router.get("/customers/{client_id}/bm-preferences")
def get_client_bm_preference_endpoint(client_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Đọc cấu hình BM ưu tiên của một khách hàng cụ thể."""
    client = db.get(Customer, client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy khách hàng với ID {client_id}")

    pref = get_client_bm_preference(db, client_id)
    synced_bms_map = {b.bm_id: b for b in db.scalars(select(SyncedBM)).all()}
    return _serialize_pref(client, pref, synced_bms_map=synced_bms_map)


@router.patch("/clients/{client_id}/bm-preferences")
@router.patch("/customers/{client_id}/bm-preferences")
def update_client_bm_preference_endpoint(
    client_id: int,
    req: UpdateBMPreferenceRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật hoặc ghi đè cấu hình phân quyền BM ưu tiên cho khách hàng (Auto-Remember & Override)."""
    client = db.get(Customer, client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy khách hàng với ID {client_id}")

    if req.bm_role and req.bm_role.upper() not in (BM_ROLE_EMPLOYEE, BM_ROLE_ADMIN):
        raise HTTPException(status_code=400, detail="bm_role phải là EMPLOYEE hoặc ADMIN")

    if req.ad_account_access_type and req.ad_account_access_type.upper() not in (ACCESS_TYPE_FULL, ACCESS_TYPE_PARTIAL):
        raise HTTPException(status_code=400, detail="ad_account_access_type phải là FULL hoặc PARTIAL")

    pref = save_or_update_client_bm_preference(
        session=db,
        client_id=client_id,
        preferred_bm_id=req.preferred_bm_id,
        via_profile_id=req.via_profile_id,
        bm_role=req.bm_role,
        ad_account_access_type=req.ad_account_access_type,
        partial_permissions=req.partial_permissions,
        notes=req.notes,
        actor=req.actor,
    )

    synced_bms_map = {b.bm_id: b for b in db.scalars(select(SyncedBM)).all()}
    serialized = _serialize_pref(client, pref, synced_bms_map=synced_bms_map)
    return {
        "success": True,
        "message": f"Đã lưu và ghi nhớ cấu hình BM ưu tiên cho khách hàng {client.name}!",
        "preference": serialized,
    }
    return {
        "success": True,
        "message": f"Đã lưu và ghi nhớ cấu hình BM ưu tiên cho khách hàng {client.name}!",
        "preference": serialized,
    }
