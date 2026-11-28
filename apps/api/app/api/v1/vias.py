"""API Quản lý Dàn Multi-VIA Farm, Proxy Riêng, Check Live UID & Đồng Bộ BM."""

from __future__ import annotations

import io
import json
import logging
from decimal import Decimal
from pathlib import Path
import secrets
from typing import Any, Optional
import zipfile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.local_admin import require_local_admin, require_local_admin_or_owner
from app.db import get_db
from app.models.customer import Customer, utcnow
from app.models.extension_remote import (
    CampaignDraft,
    CampaignTemplate,
    ExtensionClientKey,
    ExtensionRemoteTask,
    RemoteViaCommand,
)
from app.models.via import (
    AdAccountSnapshot,
    MaxcareActivityLog,
    SyncedAdAccount,
    SyncedBM,
    SyncedPage,
    ViaCategory,
    ViaProfile,
)
from app.services.chrome_launcher import launch_chrome_for_via
from app.services.maxcare_manager import (
    bulk_import_maxcare_vias,
    bulk_update_vias,
    export_via_tokens_csv,
    get_or_create_category,
    list_categories,
    run_maxcare_bulk_login,
)
from app.services.maxcare_seeding import SEEDING_ACTIONS, run_via_seeding_bulk
from app.services.sync_engine import (
    export_maxcare_report_csv,
    load_recent_snapshots,
    run_reporting_sync,
)
from app.services.remote_commands import claim_oldest_pending, finish_command
from app.api.v1.remote_commands import require_extension_or_local
from app.services.via_manager import (
    assign_ad_account_customer,
    bulk_assign_ad_accounts_customer,
    bulk_import_vias,
    check_bulk_uids_live,
    check_uid_live_status,
    classify_account_type,
    clean_meta_token,
    create_or_update_via,
    decrypt_via_credentials,
    encrypt_via_credentials,
    export_adsos_check_data,
    extended_payment_action,
    extract_tokens_from_cookie,
    fetch_accounts_for_bm_service,
    generate_totp_code,
    get_ads_check_explorer_data,
    harvest_session_from_profile_or_cdp,
    ingest_extension_payload,
    is_real_facebook_cookie,
    login_via_profile,
    normalize_account_status_and_dot,
    normalize_proxy_config,
    remove_hidden_admins_action,
    rename_accounts_action,
    save_synced_browser_cookie,
    serialize_synced_bm,
    serialize_via_profile,
    share_pixel_action,
    super_share_ads_action,
    super_target_action,
    sync_via_all_assets,
    sync_via_bm_assets,
    toggle_synced_bm_primary_rental,
)

router = APIRouter(
    prefix="/vias",
    tags=["vias-farm-management"],
    dependencies=[Depends(require_local_admin_or_owner)],
)


@router.get("/ping")
def ping_bridge() -> dict[str, Any]:
    """Lightweight unauthenticated health check cho AdsOS Extension Bridge tự động dò cổng."""
    return {
        "status": "ok",
        "connected": True,
        "message": "AdsOS Extension Bridge Connected",
        "timestamp": utcnow().isoformat(),
    }


# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================

class CreateSingleViaRequest(BaseModel):
    uid: str = Field(..., min_length=1, description="UID Facebook của VIA")
    password: str = Field(..., min_length=1, description="Mật khẩu VIA")
    profile_name: Optional[str] = Field(None, description="Tên định danh profile (VD: VIA-001)")
    two_fa_secret: Optional[str] = Field(None, description="Khóa 2FA TOTP bí mật (16/32 ký tự)")
    email: Optional[str] = Field(None, description="Email đăng nhập / liên kết")
    email_password: Optional[str] = Field(None, description="Mật khẩu Email")
    backup_email: Optional[str] = Field(None, description="Mail khôi phục (Backup mail)")
    cookie: Optional[str] = Field(None, description="Cookie phiên đăng nhập")
    access_token: Optional[str] = Field(None, description="Access Token Meta")
    proxy_config: Optional[str] = Field(None, description="Proxy riêng (IP:Port:User:Pass hoặc URL)")


class BulkImportViaRequest(BaseModel):
    raw_text: str = Field(
        ...,
        min_length=3,
        description="Danh sách VIA nhiều dòng dạng: UID|PASS|2FA|mail|pass mail|Mail back up",
    )
    default_proxy: Optional[str] = Field(None, description="Proxy mặc định gắn cho các VIA nhập lần này")


class UpdateProxyRequest(BaseModel):
    proxy_config: str = Field(..., description="Proxy riêng dạng IP:Port:User:Pass hoặc URL")


class UpdateViaInfoRequest(BaseModel):
    profile_name: Optional[str] = Field(None, max_length=255, description="Tên định danh profile (VD: VIA-001 - Cầm BM1)")
    note: Optional[str] = Field(None, max_length=2000, description="Ghi chú nội bộ cho VIA")
    proxy_url: Optional[str] = Field(None, description="Proxy riêng dạng IP:Port:User:Pass hoặc URL")


class ViaLoginRequest(BaseModel):
    cookie: Optional[str] = Field(None, description="Cookie cập nhật mới nếu có")
    access_token: Optional[str] = Field(None, description="Token cập nhật mới nếu có")


class SyncBrowserCookieRequest(BaseModel):
    cookie: str = Field(..., min_length=5, description="Chuỗi session cookies c_user=...; xs=... từ Chrome")
    access_token: Optional[str] = Field(None, description="Access Token Meta nếu trích xuất được từ DOM")


class ManualCredentialsRequest(BaseModel):
    cookie: Optional[str] = Field(None, description="Chuỗi session cookie c_user=...; xs=...")
    access_token: Optional[str] = Field(None, description="Access Token Meta EAAB... / EAAG...")



class TogglePrimaryBMRequest(BaseModel):
    is_primary_rental: Optional[bool] = Field(None, description="True/False hoặc để trống để đảo cờ")


class CheckBulkLiveRequest(BaseModel):
    via_ids: Optional[list[int]] = Field(None, description="Danh sách ID các VIA cần check (hoặc để trống để check tất cả)")


class RemoveHiddenAdminsRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list, description="Danh sách ID tài khoản cần gỡ QTV ẩn")
    via_id: Optional[int] = Field(None, description="Lọc theo VIA ID cụ thể")


class RenameAccountsRequest(BaseModel):
    account_ids: list[str] = Field(..., description="Danh sách ID tài khoản cần đổi thông tin")
    prefix: Optional[str] = Field(None, description="Tiền tố tên")
    suffix: Optional[str] = Field(None, description="Hậu tố tên")
    new_name: Optional[str] = Field(None, description="Tên mới cơ sở (hỗ trợ mẫu {index})")
    currency: Optional[str] = Field(None, description="Đơn vị tiền tệ (VND, USD)")
    timezone_name: Optional[str] = Field(None, description="Múi giờ (VD: Asia/Ho_Chi_Minh | GMT+7)")
    country_code: Optional[str] = Field(None, description="Mã quốc gia (VN, US)")
    tax_status: Optional[str] = Field(None, description="Trạng thái thuế (VD: MIỄN THUẾ, ĐÃ KHAI THUẾ)")


class SharePixelRequest(BaseModel):
    pixel_id: str = Field(..., min_length=1, description="Meta Pixel ID")
    target_account_ids: list[str] = Field(..., description="Danh sách ID tài khoản nhận quyền Pixel")
    bm_id: Optional[str] = Field(None, description="Business Manager ID sở hữu Pixel")


class SuperShareAdsRequest(BaseModel):
    client_id: int = Field(..., description="ID khách hàng (customer_id)")
    account_ids: list[str] = Field(..., min_length=1, description="Danh sách ID tài khoản quảng cáo cần chia sẻ")
    bm_id: Optional[str] = Field(None, description="BM phân quyền (ưu tiên BM Chính Cho Thuê)")
    via_profile_id: Optional[int] = Field(None, description="ID hồ sơ VIA thực hiện")
    role: str = Field("EMPLOYEE", description="Vai trò: ADMIN hoặc EMPLOYEE")
    access_type: str = Field("FULL", description="Kiểu quyền: FULL hoặc PARTIAL")
    partial_permissions: Optional[list[str]] = Field(None, description="Danh sách quyền chi tiết nếu PARTIAL")


class AssignCustomerRequest(BaseModel):
    act_id: str = Field(..., min_length=1, description="ID tài khoản quảng cáo (VD: 123456789 hoặc act_123456789)")
    customer_id: Optional[int] = Field(None, description="ID khách hàng gán kết (None hoặc 0 để hủy gán)")


class BulkAssignCustomerRequest(BaseModel):
    account_ids: list[str] = Field(..., min_length=1, description="Danh sách ID tài khoản quảng cáo cần gán")
    customer_id: Optional[int] = Field(None, description="ID khách hàng gán kết (None hoặc 0 để hủy gán)")


class LoadModeRequest(BaseModel):
    mode: str = Field("LOAD_ALL", description="LOAD_ALL, LOAD_BY_ACT_IDS, LOAD_BY_BM_ID, LOAD_BY_VIA_ID")
    account_ids: Optional[list[str]] = Field(None, description="Danh sách act_id khi mode=LOAD_BY_ACT_IDS")
    bm_id: Optional[str] = Field(None, description="ID BM khi mode=LOAD_BY_BM_ID")
    via_id: Optional[int] = Field(None, description="ID VIA khi mode=LOAD_BY_VIA_ID")
    status: Optional[str] = Field(None, description="Bộ lọc trạng thái (ACTIVE, DISABLED, UNSETTLED)")
    via_profile_id: Optional[int] = Field(None, description="Hồ sơ VIA sở hữu BM")
    role: str = Field("EMPLOYEE", description="Vai trò: EMPLOYEE hoặc ADMIN")
    access_type: str = Field("FULL", description="Loại quyền: FULL hoặc PARTIAL")
    partial_permissions: Optional[list[str]] = Field(None, description="Danh sách quyền chi tiết nếu PARTIAL")
    access_token: Optional[str] = Field(None, description="Access Token Meta EAAB/EAAG")
    cookie: Optional[str] = Field(None, description="Session cookie")


class LaunchBrowserRequest(BaseModel):
    target_type: str = Field("FB_HOME", description="Loại điều hướng: ADS_MANAGER, BILLING, BM_SETTINGS, PAGE, FB_HOME")
    act_id: Optional[str] = Field(None, description="ID Tài khoản quảng cáo nếu có")
    bm_id: Optional[str] = Field(None, description="ID BM nếu có")
    page_id: Optional[str] = Field(None, description="ID Page nếu có")
    custom_url: Optional[str] = Field(None, description="URL đích tùy chỉnh")


class OpenInViaRequest(BaseModel):
    act_id: Optional[str] = Field(None, description="ID Tài khoản quảng cáo cần mở")
    bm_id: Optional[str] = Field(None, description="ID BM cần mở")
    page_id: Optional[str] = Field(None, description="ID Page cần mở")
    via_id: Optional[int] = Field(None, description="ID VIA cụ thể nếu biết trước")
    target_type: str = Field("ADS_MANAGER", description="Loại điều hướng: ADS_MANAGER, BILLING, BM_SETTINGS, PAGE, FB_HOME")
    custom_url: Optional[str] = Field(None, description="URL đích tùy chỉnh")


class ExtendedPaymentRequest(BaseModel):
    account_ids: list[str] = Field(..., min_length=1, description="Danh sách ID tài khoản áp dụng")
    action: str = Field("PAY_NOW", description="PAY_NOW, SET_PRIMARY_CARD, ADD_BACKUP_CARD, REMOVE_CARD, FETCH_INVOICES")
    card_brand: Optional[str] = Field(None, description="Thương hiệu thẻ: VISA, MASTERCARD")
    card_last4: Optional[str] = Field(None, description="4 số cuối thẻ")
    amount: Optional[float] = Field(None, description="Số tiền thanh toán nợ (để trống nếu trả hết dư nợ)")


class SuperTargetRequest(BaseModel):
    keyword: Optional[str] = Field(None, description="Từ khóa tìm kiếm sở thích ẩn Meta")
    action: str = Field("SEARCH_INTERESTS", description="SEARCH_INTERESTS hoặc APPEAL_ACCOUNT")
    account_ids: Optional[list[str]] = Field(None, description="Danh sách ID tài khoản kháng nghị")
    appeal_reason: Optional[str] = Field(None, description="Lý do kháng nghị gửi Meta")


class MaxcareCategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80, description="Tên nhóm VIA MaxCare")
    description: Optional[str] = Field(None, max_length=255, description="Mô tả nhóm")


class MaxcareCategoryUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80, description="Tên mới của nhóm")


class MaxcareBulkImportRequest(BaseModel):
    raw_text: str = Field(
        ...,
        min_length=3,
        description="Danh sách VIA nhiều nhiều dòng (UTF-8, 1000+ dòng). Mỗi dòng: UID|PASS|2FA|mail|pass mail|mail backup|cookie|token",
    )
    default_category: Optional[str] = Field(None, description="Nhóm gán mặc định khi không khai /category= trên dòng")


class MaxcareActionRequest(BaseModel):
    action: str = Field(
        ...,
        description="BULK_LOGIN, CHECK_LIVE, UPDATE_INFO hoặc EXPORT_TOKENS",
    )
    via_ids: Optional[list[int]] = Field(None, description="ID VIA áp dụng (để trống = tất cả)")
    params: Optional[dict[str, Any]] = Field(None, description="Tùy chọn bổ sung cho hành động")


class MaxcareSeedingRequest(BaseModel):
    via_ids: list[int] = Field(..., min_length=1, description="Danh sách VIA chạy nuôi tài khoản")
    actions: list[str] = Field(..., min_length=1, description="Danh sách hành động nuôi tài khoản")
    scroll_count: int = Field(20, ge=1, le=100, description="Số lần lướt newsfeed")
    like_count: int = Field(3, ge=0, le=50, description="Số lượt like/comment mỗi phiên")
    join_group_count: int = Field(1, ge=0, le=10, description="Số group tham gia mỗi phiên")


class MaxcareSyncReportsRequest(BaseModel):
    via_ids: Optional[list[int]] = Field(None, description="ID VIA cần đồng bộ báo cáo (để trống = tất cả)")
    concurrency: int = Field(5, ge=1, le=20, description="Số luồng đồng bộ song song")


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.get("")
def list_vias(
    search: Optional[str] = None,
    uid_status: Optional[str] = None,
    token_status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000, description="Số lượng VIA trên một trang"),
    offset: int = Query(0, ge=0, description="Độ lệch phân trang"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Lấy danh sách dàn VIA kèm thống kê tổng quan (Live/Die/Token/BM) bằng SQL aggregation và phân trang."""
    # 1. Thống kê KPI tổng thể bằng 1 câu truy vấn SQL Aggregation duy nhất
    stats_row = db.execute(
        select(
            func.count(ViaProfile.id).label("total_vias"),
            func.sum(case((ViaProfile.uid_live_status == "LIVE", 1), else_=0)).label("live_count"),
            func.sum(case((ViaProfile.uid_live_status == "DIE", 1), else_=0)).label("die_count"),
            func.sum(case((ViaProfile.token_status == "ACTIVE", 1), else_=0)).label("active_tokens"),
            func.sum(case((ViaProfile.token_status == "CHECKPOINT", 1), else_=0)).label("checkpoint_tokens"),
            func.coalesce(func.sum(ViaProfile.ad_account_count), 0).label("total_ad_accounts"),
            func.coalesce(func.sum(ViaProfile.page_count), 0).label("total_pages"),
        )
    ).one()

    bm_stats = db.execute(
        select(
            func.count(SyncedBM.id).label("total_bms"),
            func.sum(case((SyncedBM.is_primary_rental.is_(True), 1), else_=0)).label("primary_bms"),
        )
    ).one()

    total_vias = int(stats_row.total_vias or 0)
    live_count = int(stats_row.live_count or 0)
    die_count = int(stats_row.die_count or 0)
    unknown_count = total_vias - live_count - die_count
    active_tokens = int(stats_row.active_tokens or 0)
    checkpoint_tokens = int(stats_row.checkpoint_tokens or 0)
    total_ad_accounts = int(stats_row.total_ad_accounts or 0)
    total_pages = int(stats_row.total_pages or 0)
    total_bms = int(bm_stats.total_bms or 0)
    primary_bms = int(bm_stats.primary_bms or 0)

    # 2. Truy vấn danh sách kèm bộ lọc và phân trang tại tầng cơ sở dữ liệu
    query = select(ViaProfile)

    if uid_status:
        query = query.where(ViaProfile.uid_live_status == uid_status.upper())
    if token_status:
        query = query.where(ViaProfile.token_status == token_status.upper())

    if search and search.strip():
        q = search.strip()
        query = query.where(
            or_(
                ViaProfile.uid.ilike(f"%{q}%"),
                ViaProfile.profile_name.ilike(f"%{q}%"),
            )
        )

    vias = db.scalars(query.order_by(ViaProfile.id).offset(offset).limit(limit)).all()

    return {
        "vias": [serialize_via_profile(v) for v in vias],
        "stats": {
            "total_vias": total_vias,
            "live_count": live_count,
            "die_count": die_count,
            "unknown_count": unknown_count,
            "active_tokens": active_tokens,
            "checkpoint_tokens": checkpoint_tokens,
            "total_bms": total_bms,
            "primary_bms": primary_bms,
            "total_ad_accounts": total_ad_accounts,
            "total_pages": total_pages,
        },
    }


@router.post("")
def create_via(
    req: CreateSingleViaRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tạo mới hoặc cập nhật 1 VIA Profile độc lập."""
    via = create_or_update_via(
        session=db,
        uid=req.uid,
        password=req.password,
        profile_name=req.profile_name,
        two_fa_secret=req.two_fa_secret,
        email=req.email,
        email_password=req.email_password,
        backup_email=req.backup_email,
        cookie=req.cookie,
        access_token=req.access_token,
        proxy_config=req.proxy_config,
    )
    db.commit()
    db.refresh(via)
    return {
        "success": True,
        "message": f"Đã lưu thành công hồ sơ VIA #{via.id} ({via.uid})",
        "via": serialize_via_profile(via),
    }


@router.post("/bulk")
def bulk_import_vias_endpoint(
    req: BulkImportViaRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Nhập hàng loạt 1 hoặc 100+ VIA từ văn bản theo định dạng UID|PASS|2FA|mail|pass mail|Mail back up."""
    result = bulk_import_vias(
        session=db,
        raw_text=req.raw_text,
        default_proxy=req.default_proxy,
    )
    return result


# ==============================================================================
# MAXCARE SUITE (Danh mục, Import, Bulk Login, Seeding, Đồng bộ báo cáo, Xuất)
# ==============================================================================

@router.get("/maxcare/categories")
def maxcare_list_categories(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Danh sách có thứ tự danh mục VIA MaxCare (Farm, Daily, Scan ctv...) kèm số VIA."""
    return {"categories": list_categories(db)}


@router.post("/maxcare/categories")
def maxcare_create_category(
    req: MaxcareCategoryCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tạo danh mục VIA mới (hoặc lấy lại nếu đã tồn tại, không phân biệt hoa/thường)."""
    try:
        category = get_or_create_category(db, req.name, color=req.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if req.description:
        category.color = req.description
        db.commit()
    return {"success": True, "category": {"id": category.id, "name": category.name, "color": category.color}}


@router.patch("/maxcare/categories/{category_id}")
def maxcare_rename_category(
    category_id: int,
    req: MaxcareCategoryUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Đổi tên danh mục VIA MaxCare."""
    category = db.get(ViaCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy danh mục #{category_id}")
    category.name = (req.name or "").strip()
    if not category.name:
        raise HTTPException(status_code=400, detail="Tên danh mục không được để trống.")
    db.commit()
    return {"success": True, "category": {"id": category.id, "name": category.name, "color": category.color}}


@router.delete("/maxcare/categories/{category_id}")
def maxcare_delete_category(
    category_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Xóa danh mục trống (chỉ cho phép khi không còn VIA nào thuộc danh mục)."""
    category = db.get(ViaCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy danh mục #{category_id}")
    in_use = (
        db.query(func.count(ViaProfile.id)).filter(ViaProfile.category_id == category_id).scalar()
    )
    if int(in_use or 0) > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Danh mục đang chứa {in_use} VIA. Hãy chuyển các VIA sang danh mục khác trước khi xóa.",
        )
    db.delete(category)
    db.commit()
    return {"success": True, "message": f"Đã xóa danh mục {category.name}."}


@router.post("/maxcare/import")
def maxcare_import_endpoint(
    req: MaxcareBulkImportRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Nhập hàng loạt 1..1000+ VIA MaxCare: parser linh hoạt, tự tạo danh mục, gán device/birthday."""
    try:
        return bulk_import_maxcare_vias(
            session=db,
            raw_text=req.raw_text,
            default_category=req.default_category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/maxcare-action")
def maxcare_action_endpoint(
    req: MaxcareActionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Bộ hành động MaxCare: BULK_LOGIN (huverst token/cookie), CHECK_LIVE, UPDATE_INFO, EXPORT_TOKENS."""
    params = req.params or {}
    action = (req.action or "").strip().upper()
    try:
        if action == "BULK_LOGIN":
            return run_maxcare_bulk_login(
                db,
                via_ids=req.via_ids,
                concurrency=params.get("concurrency"),
                delay_between=float(params.get("delay_between") or 0),
            )
        if action == "CHECK_LIVE":
            res = check_bulk_uids_live(db, via_ids=req.via_ids)
            return {"action": action, **res}
        if action == "UPDATE_INFO":
            return bulk_update_vias(
                db,
                via_ids=req.via_ids,
                category_name=params.get("category_name"),
                category_id=params.get("category_id"),
                device_name=params.get("device_name"),
                gender=params.get("gender"),
                birthday=params.get("birthday"),
                note=params.get("note"),
                as_note_append=bool(params.get("as_note_append")),
            )
        if action == "EXPORT_TOKENS":
            return export_via_tokens_csv(
                db,
                via_ids=req.via_ids,
                style=params.get("style") or "csv",
            )
        raise ValueError(
            "Hành động không hợp lệ. Chọn một trong: BULK_LOGIN, CHECK_LIVE, UPDATE_INFO, EXPORT_TOKENS."
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/maxcare/seeding")
def maxcare_seeding_catalog() -> dict[str, Any]:
    """Danh mục hành động nuôi tài khoản (Tạo tương tác tự nhiên) cho MaxCare."""
    labels = {
        "SCROLL_NEWSFEED": "Lướt newsfeed (giả lập người thật)",
        "JOIN_GROUPS": "Tham gia nhóm theo từ khóa (chỉ group Public)",
        "LIKE_COMMENT": "Like / Comment bài viết từ danh sách URL",
    }
    return {
        "actions": [
            {
                "value": key,
                "label": labels[key],
                "description": SEEDING_ACTIONS[key],
            }
            for key in SEEDING_ACTIONS
        ]
    }


@router.post("/maxcare/seeding")
def maxcare_seeding_endpoint(
    req: MaxcareSeedingRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Chạy đồng loạt luồng nuôi tài khoản (Scroll / Join group / Like - Comment)."""
    # Kiểm tra tính hợp lệ TRƯỚC khi chạy: action sai phải trả 400, không nuốt lỗi.
    from app.services.maxcare_seeding import normalize_action

    for action in req.actions:
        try:
            normalize_action(action)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    results = []
    for action in req.actions:
        try:
            result = run_via_seeding_bulk(
                session=db,
                via_ids=req.via_ids,
                action=action,
                params={
                    "scroll_count": req.scroll_count,
                    "like_count": req.like_count,
                    "join_group_count": req.join_group_count,
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Lỗi seeding {action}: {exc}")
        results.append(result)
    return {"success": True, "results": results}


@router.post("/maxcare/sync-reports")
def maxcare_sync_reports_endpoint(
    req: MaxcareSyncReportsRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Đồng bộ song song báo cáo TKQC (USD) của các VIA vào DB + snapshot báo cáo."""
    return run_reporting_sync(db, via_ids=req.via_ids, concurrency=req.concurrency)


@router.get("/maxcare/activity-logs")
def maxcare_activity_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    via_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Nhật ký hoạt động MaxCare (append-only): Bulk login, Import, Update info, Seeding..."""
    query = select(MaxcareActivityLog)
    if via_id:
        query = query.where(MaxcareActivityLog.via_profile_id == via_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    logs = db.scalars(query.order_by(MaxcareActivityLog.id.desc()).offset(offset).limit(limit)).all()
    return {
        "total": int(total),
        "logs": [
            {
                "id": log.id,
                "via_id": log.via_profile_id,
                "action": log.action,
                "status": log.status,
                "detail": log.detail,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


@router.get("/maxcare/snapshots")
def maxcare_snapshots(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Snapshot báo cáo TKQC gần nhất (đồng bộ từ Graph API) cho bảng MaxCare Reports."""
    return {"snapshots": load_recent_snapshots(db, limit=limit)}


@router.get("/maxcare/reports/export")
def maxcare_reports_export(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Xuất file CSV báo cáo TKQC MaxCare (UTF-8, tải trực tiếp về máy)."""
    res = export_maxcare_report_csv(db, limit=limit)
    return Response(
        content=res["content"],
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{res["filename"]}"'},
    )


@router.get("/maxcare/tokens/export")
def maxcare_tokens_export(
    style: str = Query("csv", description="Định dạng xuất: csv hoặc pipe"),
    via_ids: Optional[str] = Query(None, description="Danh sách ID VIA phân tách bởi dấu phẩy"),
    db: Session = Depends(get_db),
):
    """📋 Xuất Token + Cookie hàng loạt cho tool ngoài (chỉ admin local có thể truy cập)."""
    ids: Optional[list[int]] = None
    if (via_ids or "").strip():
        try:
            ids = [int(x.strip()) for x in via_ids.split(",") if x.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Danh sách via_ids phải là số nguyên phân tách bởi dấu phẩy.")
    res = export_via_tokens_csv(db, via_ids=ids, style=style)
    media = "text/csv; charset=utf-8" if res["format"] == "csv" else "text/plain; charset=utf-8"
    return Response(
        content=res["content"],
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{res["filename"]}"'},
    )


# ==============================================================================
# SMIT ADS CHECK EXPLORER & QUICK ACTIONS
# ==============================================================================

@router.get("/ads-check")
def ads_check_explorer_endpoint(
    tab: str = Query("personal", description="Tab tài sản: personal, bm, group, page, accounts"),
    via_id: Optional[int] = Query(None, description="Lọc theo VIA ID"),
    currency_display: str = Query("ORIGINAL", description="Đơn vị hiển thị: ORIGINAL, VND, USD"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên hoặc ID"),
    q: Optional[str] = Query(None, description="Tìm kiếm nhanh (alias q)"),
    status: Optional[str] = Query(None, description="Lọc theo trạng thái TK (ACTIVE, DISABLED, UNSETTLED)"),
    status_filter: Optional[str] = Query(None, description="Lọc theo trạng thái TK (alias status_filter)"),
    assignment_status: Optional[str] = Query(None, description="Lọc gắn khách (ASSIGNED, UNASSIGNED)"),
    customer_id: Optional[int] = Query(None, description="Lọc theo khách hàng"),
    bm_id: Optional[str] = Query(None, description="Lọc theo BM ID"),
    account_ids: Optional[str] = Query(None, description="Lọc theo danh sách ID tài khoản (phân cách dấu phẩy)"),
    card_status: Optional[str] = Query(None, description="Lọc theo thẻ (HAS_CARD, NO_CARD)"),
    account_type: Optional[str] = Query(None, description="Lọc loại TK (PERSONAL, BM, BUSINESS, ALL)"),
    currency: Optional[str] = Query(None, description="Lọc theo loại tiền tệ (USD, VND, EUR...)"),
    mode: Optional[str] = Query(None, description="Chế độ tải SMIT (LOAD_ALL, LOAD_BY_ACT_IDS, LOAD_BY_BM_ID, LOAD_BY_VIA_ID)"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(50, ge=1, le=500, description="Số dòng mỗi trang"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Truy vấn bảng SMIT Ads Check Explorer kèm thống kê tổng dòng footer."""
    effective_search = search or q
    effective_status = status or status_filter
    if (mode == "LOAD_BY_BM_ID" or bm_id) and bm_id:
        if tab == "personal":
            tab = "accounts"
        acc_cnt = db.scalar(select(func.count(SyncedAdAccount.id)).where(SyncedAdAccount.bm_id == bm_id)) or 0
        if acc_cnt == 0:
            try:
                fetch_accounts_for_bm_service(session=db, bm_id=bm_id, via_id=via_id)
            except Exception as bm_sc_err:
                logger.debug("Notice ads-check fetch BM %s: %s", bm_id, bm_sc_err)

    return get_ads_check_explorer_data(
        session=db,
        tab=tab,
        via_id=via_id,
        currency_display=currency_display,
        search=effective_search,
        page=page,
        page_size=page_size,
        status=effective_status,
        assignment_status=assignment_status,
        customer_id=customer_id,
        bm_id=bm_id,
        account_ids=account_ids,
        card_status=card_status,
        account_type=account_type,
        currency=currency,
        mode=mode,
    )


@router.post("/ads-check/assign-customer")
def assign_customer_endpoint(
    req: AssignCustomerRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """1-Click gán hoặc đổi khách hàng cho tài khoản quảng cáo."""
    try:
        updated = assign_ad_account_customer(
            session=db,
            act_id=req.act_id,
            customer_id=req.customer_id,
        )
        return {
            "success": True,
            "account": updated,
            "message": f"Đã gắn TKQC {req.act_id} cho khách hàng thành công.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ads-check/bulk-assign-customer")
def bulk_assign_customer_endpoint(
    req: BulkAssignCustomerRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Gán hàng loạt tài khoản quảng cáo cho khách hàng."""
    try:
        return bulk_assign_ad_accounts_customer(
            session=db,
            account_ids=req.account_ids,
            customer_id=req.customer_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ads-check/load-mode")
def load_mode_endpoint(
    req: LoadModeRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Kích hoạt và nạp tài khoản theo 4 chế độ tải SMIT."""
    if (req.mode == "LOAD_BY_BM_ID" or req.bm_id) and req.bm_id:
        try:
            fetch_accounts_for_bm_service(
                session=db,
                bm_id=req.bm_id,
                via_id=req.via_id or req.via_profile_id,
                token=req.access_token,
                cookie=req.cookie,
            )
        except Exception as bm_err:
            logger.warning("Notice load_mode_endpoint fetch BM %s: %s", req.bm_id, bm_err)

    return get_ads_check_explorer_data(
        session=db,
        tab="accounts",
        via_id=req.via_id,
        bm_id=req.bm_id,
        account_ids=req.account_ids,
        status=req.status,
        mode=req.mode,
        page=1,
        page_size=500,
    )


@router.post("/ads-check/remove-hidden-admins")
def remove_hidden_admins_endpoint(
    req: RemoveHiddenAdminsRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Gỡ bỏ toàn bộ Quản trị viên ẩn trên các tài khoản quảng cáo đã chọn."""
    return remove_hidden_admins_action(
        session=db,
        account_ids=req.account_ids,
        via_id=req.via_id,
    )


@router.post("/ads-check/rename-accounts")
def rename_accounts_endpoint(
    req: RenameAccountsRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Đổi thông tin hàng loạt tài khoản quảng cáo (Tên, Tiền tệ, Múi giờ, Thuế)."""
    return rename_accounts_action(
        session=db,
        account_ids=req.account_ids,
        prefix=req.prefix,
        suffix=req.suffix,
        new_name=req.new_name,
        currency=req.currency,
        timezone_name=req.timezone_name,
        country_code=req.country_code,
        tax_status=req.tax_status,
    )


@router.post("/ads-check/open-in-via")
def open_in_via_browser_endpoint(
    req: OpenInViaRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Khởi chạy Chrome VIA độc lập, tự động nạp Cookie/2FA và mở Trình quản lý QC / Billing / BM."""
    try:
        return launch_chrome_for_via(
            session=db,
            via_id=req.via_id,
            act_id=req.act_id,
            bm_id=req.bm_id,
            page_id=req.page_id,
            target_type=req.target_type,
            custom_url=req.custom_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/ads-check/extended-payment")
def extended_payment_endpoint(
    req: ExtendedPaymentRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Hành động thanh toán mở rộng (Thanh toán nợ, đổi thẻ chính/phụ, gỡ thẻ, tải hóa đơn)."""
    try:
        return extended_payment_action(
            session=db,
            account_ids=req.account_ids,
            action=req.action,
            card_brand=req.card_brand,
            card_last4=req.card_last4,
            amount=req.amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/ads-check/super-target")
def super_target_endpoint(
    req: SuperTargetRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tìm sở thích ẩn Meta hoặc gửi đơn kháng nghị tài khoản die."""
    try:
        return super_target_action(
            session=db,
            keyword=req.keyword,
            action=req.action,
            account_ids=req.account_ids,
            appeal_reason=req.appeal_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/ads-check/export")
def export_ads_check_endpoint(
    tab: str = Query("personal", description="Tab tài sản: personal, bm, group, page"),
    via_id: Optional[int] = Query(None, description="Lọc theo VIA ID"),
    format_type: str = Query("csv", description="Định dạng xuất: csv hoặc txt"),
    db: Session = Depends(get_db),
):
    """Xuất file báo cáo tài sản ADSOS CHECK (CSV hoặc TXT)."""
    res = export_adsos_check_data(
        session=db,
        tab=tab,
        via_id=via_id,
        format_type=format_type,
    )
    return Response(
        content=res["content"],
        media_type=res["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{res["filename"]}"'},
    )


@router.post("/ads-check/share-pixel")
def share_pixel_endpoint(
    req: SharePixelRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Chia sẻ Meta Pixel tới các tài khoản quảng cáo."""
    try:
        return share_pixel_action(
            session=db,
            pixel_id=req.pixel_id,
            target_account_ids=req.target_account_ids,
            bm_id=req.bm_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/ads-check/super-share-ads")
def super_share_ads_endpoint(
    req: SuperShareAdsRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Super Share Ads: Cấp quyền tài khoản QC và tự động ghi nhớ cấu hình cho khách hàng."""
    try:
        return super_share_ads_action(
            session=db,
            client_id=req.client_id,
            account_ids=req.account_ids,
            bm_id=req.bm_id,
            via_profile_id=req.via_profile_id,
            role=req.role,
            access_type=req.access_type,
            partial_permissions=req.partial_permissions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ==============================================================================
# ADSOS CHECK PRO EXTENSION ENDPOINTS: INGEST, DOWNLOAD, KEYS, TEMPLATES & TASKS
# ==============================================================================

class ExtensionIngestRequest(BaseModel):
    model_config = {"extra": "allow"}

    fb_uid: Optional[str] = Field(None, description="UID Facebook của VIA")
    client_key: Optional[str] = Field(None, description="Mã Client Key (VD: ADSOS-CLI-XXXX)")
    profile_name: Optional[str] = Field(None, description="Tên định danh profile")
    cookie: Optional[str] = Field(None, description="Cookie Facebook")
    access_token: Optional[str] = Field(None, description="Access Token Meta EAAB/EAAG")
    eaag_token: Optional[str] = Field(None, description="Access Token Meta EAAG")
    eaab_token: Optional[str] = Field(None, description="Access Token Meta EAAB")
    fb_dtsg: Optional[str] = Field(None, description="Token fb_dtsg trích xuất từ session Facebook")
    tokens: Optional[Any] = Field(None, description="Cấu trúc token hoặc danh sách token")
    ad_accounts: Optional[list[dict[str, Any]]] = Field(default=None, description="Danh sách TKQC quét từ browser")
    business_managers: Optional[list[dict[str, Any]]] = Field(default=None, description="Danh sách BM")
    fanpages: Optional[list[dict[str, Any]]] = Field(default=None, description="Danh sách Fanpage")
    pixels: Optional[list[dict[str, Any]]] = Field(default=None, description="Danh sách Pixels")
    device_name: Optional[str] = Field(None, description="Tên thiết bị / User-Agent")

    @model_validator(mode="before")
    @classmethod
    def normalize_extension_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        # fb_uid: fb_uid, c_user, uid, via_uid
        uid_val = d.get("fb_uid") or d.get("c_user") or d.get("uid") or d.get("via_uid")
        if uid_val is not None:
            d["fb_uid"] = str(uid_val).strip()

        # eaag_token / eaab_token
        eaag_val = d.get("eaag_token") or d.get("eaagToken")
        if eaag_val is not None:
            d["eaag_token"] = str(eaag_val).strip()

        eaab_val = d.get("eaab_token") or d.get("eaabToken")
        if eaab_val is not None:
            d["eaab_token"] = str(eaab_val).strip()

        # access_token: access_token, token, tokens
        tok_val = d.get("access_token") or d.get("token") or d.get("tokens") or eaag_val or eaab_val
        if isinstance(tok_val, dict):
            sub_eaag = tok_val.get("eaag") or tok_val.get("eaag_token")
            sub_eaab = tok_val.get("eaab") or tok_val.get("eaab_token")
            sub_tok = tok_val.get("access_token") or tok_val.get("token")
            if sub_eaag and not d.get("eaag_token"):
                d["eaag_token"] = str(sub_eaag).strip()
            if sub_eaab and not d.get("eaab_token"):
                d["eaab_token"] = str(sub_eaab).strip()
            tok_val = sub_eaag or sub_eaab or sub_tok

        if tok_val is not None and not isinstance(tok_val, (dict, list)):
            d["access_token"] = str(tok_val).strip()

        # cookie: cookie, cookies
        cookie_val = d.get("cookie") or d.get("cookies") or d.get("raw_cookie")
        if cookie_val is not None:
            if isinstance(cookie_val, dict):
                d["cookie"] = "; ".join(f"{k}={v}" for k, v in cookie_val.items())
            else:
                d["cookie"] = str(cookie_val).strip()

        # ad_accounts: ad_accounts, accounts, items
        accs_val = d.get("ad_accounts") if d.get("ad_accounts") is not None else (d.get("accounts") if d.get("accounts") is not None else d.get("items"))
        if accs_val is not None and isinstance(accs_val, list):
            d["ad_accounts"] = accs_val

        # business_managers: business_managers, bms, businesses
        bms_val = d.get("business_managers") if d.get("business_managers") is not None else (d.get("bms") if d.get("bms") is not None else d.get("businesses"))
        if bms_val is not None and isinstance(bms_val, list):
            d["business_managers"] = bms_val

        # fanpages: fanpages, pages
        pgs_val = d.get("fanpages") if d.get("fanpages") is not None else d.get("pages")
        if pgs_val is not None and isinstance(pgs_val, list):
            d["fanpages"] = pgs_val

        # fb_dtsg: fb_dtsg, dtsg
        dtsg_val = d.get("fb_dtsg") or d.get("dtsg")
        if dtsg_val is not None:
            d["fb_dtsg"] = str(dtsg_val).strip()

        # pixels: pixels, pixel_list
        pix_val = d.get("pixels") or d.get("pixel_list")
        if pix_val is not None and isinstance(pix_val, list):
            d["pixels"] = pix_val

        # profile_name: profile_name, user_name, name
        pname_val = d.get("profile_name") or d.get("user_name") or d.get("name")
        if pname_val is not None and "profile_name" not in d:
            d["profile_name"] = str(pname_val).strip()

        # client_key: client_key, api_key
        key_val = d.get("client_key") or d.get("api_key")
        if key_val is not None and "client_key" not in d:
            d["client_key"] = str(key_val).strip()

        # device_name: device_name, user_agent
        dev_val = d.get("device_name") or d.get("user_agent")
        if dev_val is not None and "device_name" not in d:
            d["device_name"] = str(dev_val).strip()

        return d


@router.post("/extension-ingest")
def extension_ingest_endpoint(
    req: ExtensionIngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tiếp nhận toàn bộ session cookie, access token và tài nguyên TKQC/BM/Page gửi từ Extension ADSOS PRO.
    Lưu tức thì VIA, token, cookie vào DB và trả về ngay kết quả để Extension không bị treo ở Bước 3.
    Tiến trình quét sâu toàn bộ BMs và TKQC được đẩy vào BackgroundTasks chạy nền."""
    raw_uid = (req.fb_uid or "").strip()
    if not raw_uid or raw_uid.lower() in ("0", "undefined", "null", "none"):
        return {
            "success": False,
            "message": "Chưa chọn phiên Facebook hợp lệ",
            "accounts": [],
            "bms": [],
        }

    try:
        res = ingest_extension_payload(session=db, payload=req, run_deep_sync=False)
        via_id = res.get("via_id")
        token_active = res.get("token_status") == "ACTIVE"
        if via_id and token_active and not req.ad_accounts:
            def _bg_sync_via(v_id: int) -> None:
                from app.db import SessionLocal
                with SessionLocal() as bg_db:
                    try:
                        sync_via_all_assets(session=bg_db, via_id=v_id)
                    except Exception as bg_err:
                        logging.getLogger(__name__).warning("Background sync error for VIA #%s: %s", v_id, bg_err)

            background_tasks.add_task(_bg_sync_via, v_id=via_id)
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/download-extension")
def download_extension_zip() -> Response:
    """Đóng gói và tải về toàn bộ tiện ích Chrome Extension metaOs (.zip)."""
    ext_dir = None
    for candidate in [
        Path("extensions/adsos-check-bridge").resolve(),
        Path.cwd() / "extensions" / "adsos-check-bridge",
        Path.cwd().parent / "extensions" / "adsos-check-bridge",
        Path.cwd().parent.parent / "extensions" / "adsos-check-bridge",
        Path(__file__).resolve().parents[4] / "extensions" / "adsos-check-bridge",
        Path(__file__).resolve().parents[3] / "extensions" / "adsos-check-bridge",
    ]:
        if candidate.is_dir():
            ext_dir = candidate
            break

    if not ext_dir or not ext_dir.is_dir():
        raise HTTPException(status_code=404, detail="Không tìm thấy thư mục nguồn của Extension.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in ext_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(ext_dir)
                zf.write(file_path, arcname)
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="metaos-extension.zip"',
        },
    )


# --- Client Key Management ---
class CreateClientKeyRequest(BaseModel):
    client_id: Optional[int] = None
    client_name: str = Field(..., min_length=1)
    api_key: Optional[str] = None


@router.get("/extension-client-keys")
def list_extension_client_keys(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Lấy danh sách các mã Binding Key Extension của khách hàng."""
    keys = db.scalars(select(ExtensionClientKey).order_by(ExtensionClientKey.id.desc())).all()
    return [
        {
            "id": k.id,
            "client_id": k.client_id,
            "client_name": k.client_name,
            "api_key": k.api_key,
            "is_active": k.is_active,
            "last_seen_at": k.last_seen_at.isoformat() if k.last_seen_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in keys
    ]


@router.post("/extension-client-keys")
def create_extension_client_key(
    req: CreateClientKeyRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tạo mới mã Binding Key Extension (VD: ADSOS-CLI-A1B2C3D4) để giao cho khách hàng."""
    key_str = req.api_key.strip() if req.api_key else f"ADSOS-CLI-{secrets.token_hex(4).upper()}"
    new_key = ExtensionClientKey(
        client_id=req.client_id,
        client_name=req.client_name.strip(),
        api_key=key_str,
        is_active=True,
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    return {
        "id": new_key.id,
        "client_id": new_key.client_id,
        "client_name": new_key.client_name,
        "api_key": new_key.api_key,
        "is_active": new_key.is_active,
        "created_at": new_key.created_at.isoformat() if new_key.created_at else None,
    }


@router.delete("/extension-client-keys/{key_id}")
def delete_extension_client_key(key_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Xóa hoặc vô hiệu hóa mã Binding Key Extension."""
    key = db.get(ExtensionClientKey, key_id)
    if not key:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã key.")
    db.delete(key)
    db.commit()
    return {"success": True, "message": f"Đã xóa mã key #{key_id}"}


# --- Campaign Templates ---
class CampaignTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    client_id: Optional[int] = None
    objective: str = "OUTCOME_ENGAGEMENT"
    daily_budget: str = "500000"
    currency: str = "VND"
    targeting_json: str = "{}"
    page_id: Optional[str] = None
    post_id_or_creative_json: Optional[str] = None
    status_on_create: str = "PAUSED"


@router.get("/campaign-templates")
def list_campaign_templates(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Lấy danh sách các mẫu Set Camp cấu hình sẵn."""
    templates = db.scalars(select(CampaignTemplate).order_by(CampaignTemplate.id.desc())).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "client_id": t.client_id,
            "objective": t.objective,
            "daily_budget": t.daily_budget,
            "currency": t.currency,
            "targeting_json": t.targeting_json,
            "page_id": t.page_id,
            "post_id_or_creative_json": t.post_id_or_creative_json,
            "status_on_create": t.status_on_create,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in templates
    ]


@router.post("/campaign-templates")
def create_campaign_template(
    req: CampaignTemplateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tạo mới mẫu chiến dịch Auto Set Camp."""
    t = CampaignTemplate(
        name=req.name.strip(),
        client_id=req.client_id,
        objective=req.objective,
        daily_budget=req.daily_budget,
        currency=req.currency,
        targeting_json=req.targeting_json,
        page_id=req.page_id,
        post_id_or_creative_json=req.post_id_or_creative_json,
        status_on_create="PAUSED",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {
        "id": t.id,
        "name": t.name,
        "objective": t.objective,
        "daily_budget": t.daily_budget,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.delete("/campaign-templates/{template_id}")
def delete_campaign_template(template_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Xóa mẫu chiến dịch."""
    t = db.get(CampaignTemplate, template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẫu chiến dịch.")
    db.delete(t)
    db.commit()
    return {"success": True, "message": f"Đã xóa mẫu #{template_id}"}


# --- Remote Task Dispatcher & Polling ---
class QueueRemoteTaskRequest(BaseModel):
    via_id: Optional[int] = None
    fb_uid: Optional[str] = None
    client_id: Optional[int] = None
    task_type: str = "CREATE_CAMPAIGN"
    target_act_id: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    requested_by: str = "WEB_ADMIN"
    telegram_chat_id: Optional[str] = None


@router.post("/extension-tasks")
def queue_extension_task(
    req: QueueRemoteTaskRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Đẩy một lệnh điều phối từ xa (Set Camp, Share TKQC, Pause Camp...) vào hàng đợi Extension."""
    fb_uid = req.fb_uid
    if not fb_uid and req.via_id:
        v = db.get(ViaProfile, req.via_id)
        if v:
            fb_uid = v.uid
    if not fb_uid:
        active_via = db.scalar(select(ViaProfile).where(ViaProfile.token_status == "ACTIVE").order_by(ViaProfile.id.desc()))
        if active_via:
            fb_uid = active_via.uid
            req.via_id = active_via.id
        else:
            first_via = db.scalar(select(ViaProfile).order_by(ViaProfile.id.desc()))
            if first_via:
                fb_uid = first_via.uid
                req.via_id = first_via.id
            else:
                fb_uid = "system"

    task = ExtensionRemoteTask(
        via_id=req.via_id,
        fb_uid=fb_uid,
        client_id=req.client_id,
        task_type=req.task_type,
        target_act_id=req.target_act_id,
        payload_json=json.dumps(req.payload or {}),
        status="PENDING",
        requested_by=req.requested_by,
        telegram_chat_id=req.telegram_chat_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return {
        "success": True,
        "task_id": task.id,
        "task_type": task.task_type,
        "fb_uid": task.fb_uid,
        "target_act_id": task.target_act_id,
        "status": task.status,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


@router.get("/extension-tasks/poll")
def poll_extension_tasks(
    fb_uid: Optional[str] = None,
    client_key: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Extension gọi định kỳ để lấy các lệnh PENDING cần thực thi trên trình duyệt."""
    query = select(ExtensionRemoteTask).where(ExtensionRemoteTask.status == "PENDING")

    if client_key:
        ck = db.scalar(select(ExtensionClientKey).where(ExtensionClientKey.api_key == client_key))
        if ck and ck.client_id:
            query = query.where(
                or_(
                    ExtensionRemoteTask.client_id == ck.client_id,
                    ExtensionRemoteTask.fb_uid == fb_uid if fb_uid else False,
                )
            )
        elif fb_uid:
            query = query.where(ExtensionRemoteTask.fb_uid == fb_uid)
    elif fb_uid:
        query = query.where(ExtensionRemoteTask.fb_uid == fb_uid)

    tasks = db.scalars(query.order_by(ExtensionRemoteTask.id.asc()).limit(limit)).all()

    for t in tasks:
        t.status = "RUNNING"
    db.commit()

    return {
        "tasks": [
            {
                "id": t.id,
                "via_id": t.via_id,
                "fb_uid": t.fb_uid,
                "task_type": t.task_type,
                "target_act_id": t.target_act_id,
                "payload_json": t.payload_json,
                "status": t.status,
                "requested_by": t.requested_by,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ]
    }


class ReportTaskResultRequest(BaseModel):
    status: str = Field(..., description="COMPLETED hoặc FAILED")
    result: Optional[dict[str, Any]] = None
    result_json: Optional[str] = None
    error_message: Optional[str] = None


@router.post("/extension-tasks/{task_id}/report")
def report_extension_task_result(
    task_id: int,
    req: ReportTaskResultRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Extension báo cáo kết quả thực thi lệnh về server."""
    task = db.get(ExtensionRemoteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ.")

    task.status = req.status.upper()
    if req.result is not None:
        task.result_json = json.dumps(req.result)
    elif req.result_json is not None:
        task.result_json = req.result_json
    task.error_message = req.error_message
    task.completed_at = utcnow()
    db.commit()

    if task.telegram_chat_id:
        try:
            from app.api.v1.telegram_bot import get_configured_telegram_connector
            from app.services.telegram_bot import TelegramBotAgent
            connector = get_configured_telegram_connector(db)
            agent = TelegramBotAgent(telegram_connector=connector)
            if task.status == "COMPLETED":
                msg = f"✅ Tác vụ {task.task_type} (Mã #{task.id}) trên VIA {task.fb_uid} (TKQC: act_{task.target_act_id or ''}) đã hoàn thành thành công!"
            else:
                msg = f"❌ Tác vụ {task.task_type} (Mã #{task.id}) thất bại: {task.error_message or 'Không rõ lỗi'}"
            agent.send_message_safe(chat_id=task.telegram_chat_id, text=msg)
        except Exception:
            pass

    return {
        "success": True,
        "task_id": task.id,
        "status": task.status,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


# ==============================================================================
# CAMPAIGN DRAFTS & REMOTE VIA COMMANDS (AUTO SET CAMP)
# ==============================================================================

class CreateCampaignDraftRequest(BaseModel):
    draft_name: str = Field(..., min_length=1, description="Tên định danh bản nháp chiến dịch")
    draft_code: Optional[str] = Field(None, description="Mã bản nháp (VD: CAMP-DRAFT-01)")
    source_via_uid: Optional[str] = None
    source_act_id: Optional[str] = None
    source_campaign_id: Optional[str] = None
    objective: str = Field(default="OUTCOME_ENGAGEMENT", description="Mục tiêu chiến dịch Meta")
    buying_type: str = Field(default="AUCTION", description="Loại hình mua")
    daily_budget: float = Field(default=500000.0, ge=0, description="Ngân sách hàng ngày")
    lifetime_budget: Optional[float] = Field(None, ge=0, description="Ngân sách trọn đời")
    bid_strategy: str = Field(default="LOWEST_COST_WITHOUT_CAP", description="Chiến lược giá thầu")
    targeting_json: str = Field(default="{}", description="JSON cấu hình target vị trí, độ tuổi, sở thích")
    page_id: Optional[str] = Field(None, description="ID Fanpage chạy quảng cáo")
    pixel_id: Optional[str] = Field(None, description="ID Meta Pixel")
    post_id: Optional[str] = Field(None, description="ID bài viết Fanpage gắn vào Ad")
    ad_creative_json: str = Field(default="{}", description="JSON cấu hình bài viết / media creative")
    initial_status: str = Field(default="PAUSED", description="Trạng thái khi vừa tạo, luôn là PAUSED")


class CaptureDraftFromActRequest(BaseModel):
    via_uid: str = Field(..., description="UID VIA đang cầm tài khoản")
    act_id: str = Field(..., description="ID tài khoản quảng cáo (VD: act_123456 hoặc 123456)")
    campaign_id: Optional[str] = Field(None, description="ID chiến dịch nguồn để clone")
    draft_name: str = Field(..., min_length=1, description="Tên bản nháp muốn lưu")


class CompleteRemoteCommandRequest(BaseModel):
    status: str = Field(..., description="Trạng thái hoàn thành: COMPLETED hoặc FAILED")
    result_json: Optional[str] = Field(None, description="Dữ liệu kết quả trả về từ Meta API")
    error_message: Optional[str] = Field(None, description="Nội dung lỗi nếu thất bại")


@router.get("/campaign-drafts")
def list_campaign_drafts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Lấy danh sách các Bản Nháp Chiến Dịch (Campaign Drafts) đã lưu trữ."""
    drafts = db.scalars(select(CampaignDraft).order_by(CampaignDraft.id.desc())).all()
    return [
        {
            "id": d.id,
            "draft_code": d.draft_code,
            "draft_name": d.draft_name,
            "source_via_uid": d.source_via_uid,
            "source_act_id": d.source_act_id,
            "source_campaign_id": d.source_campaign_id,
            "objective": d.objective,
            "buying_type": d.buying_type,
            "daily_budget": d.daily_budget,
            "lifetime_budget": d.lifetime_budget,
            "bid_strategy": d.bid_strategy,
            "targeting_json": d.targeting_json,
            "page_id": d.page_id,
            "pixel_id": d.pixel_id,
            "post_id": d.post_id,
            "ad_creative_json": d.ad_creative_json,
            "initial_status": d.initial_status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }
        for d in drafts
    ]


@router.post("/campaign-drafts")
def create_campaign_draft(
    req: CreateCampaignDraftRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tạo mới một Bản Nháp Chiến Dịch để sẵn sàng Auto Set Camp."""
    code = req.draft_code.strip() if req.draft_code else f"DRAFT-{secrets.token_hex(4).upper()}"
    existing = db.scalars(select(CampaignDraft).where(CampaignDraft.draft_code == code)).first()
    if existing:
        code = f"{code}-{secrets.token_hex(2).upper()}"

    draft = CampaignDraft(
        draft_code=code,
        draft_name=req.draft_name.strip(),
        source_via_uid=req.source_via_uid,
        source_act_id=req.source_act_id,
        source_campaign_id=req.source_campaign_id,
        objective=req.objective,
        buying_type=req.buying_type,
        daily_budget=req.daily_budget,
        lifetime_budget=req.lifetime_budget,
        bid_strategy=req.bid_strategy,
        targeting_json=req.targeting_json,
        page_id=req.page_id,
        pixel_id=req.pixel_id,
        post_id=req.post_id,
        ad_creative_json=req.ad_creative_json,
        initial_status="PAUSED",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return {
        "success": True,
        "message": f"Đã tạo bản nháp chiến dịch '{draft.draft_name}' ({draft.draft_code}) thành công.",
        "draft_id": draft.id,
        "draft_code": draft.draft_code,
    }


@router.post("/campaign-drafts/capture-from-act")
def capture_draft_from_ad_account(
    req: CaptureDraftFromActRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Hút cấu hình từ một chiến dịch mẫu của TKQC hoặc tạo bản nháp cơ sở từ tài khoản."""
    clean_act = req.act_id.replace("act_", "").strip()
    code = f"DRAFT-{clean_act[:6]}-{secrets.token_hex(3).upper()}"

    draft = CampaignDraft(
        draft_code=code,
        draft_name=req.draft_name.strip(),
        source_via_uid=req.via_uid.strip(),
        source_act_id=f"act_{clean_act}",
        source_campaign_id=req.campaign_id,
        objective="OUTCOME_ENGAGEMENT",
        buying_type="AUCTION",
        daily_budget=500000.0,
        bid_strategy="LOWEST_COST_WITHOUT_CAP",
        targeting_json=json.dumps({"geo_locations": {"countries": ["VN"]}, "age_min": 18, "age_max": 65}),
        ad_creative_json=json.dumps({"name": f"Creative {req.draft_name}"}),
        initial_status="PAUSED",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return {
        "success": True,
        "message": f"Đã hút và lưu thành công bản nháp chiến dịch '{draft.draft_name}' ({draft.draft_code}).",
        "draft": {
            "id": draft.id,
            "draft_code": draft.draft_code,
            "draft_name": draft.draft_name,
            "source_act_id": draft.source_act_id,
        },
    }


@router.get("/remote-commands/pending", dependencies=[Depends(require_extension_or_local)])
def list_pending_remote_commands(
    c_user: Optional[str] = Query(None, description="UID Facebook phiên đang chạy extension"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Extension Chrome định kỳ thăm dò (poll) các lệnh từ xa đang chờ thực thi."""
    claimed = claim_oldest_pending(db, c_user)
    commands = [claimed] if claimed else []
    results = []
    for cmd in commands:
        draft_info = None
        if cmd.draft:
            draft_info = {
                "id": cmd.draft.id,
                "draft_code": cmd.draft.draft_code,
                "draft_name": cmd.draft.draft_name,
                "objective": cmd.draft.objective,
                "buying_type": cmd.draft.buying_type,
                "daily_budget": cmd.draft.daily_budget,
                "lifetime_budget": cmd.draft.lifetime_budget,
                "bid_strategy": cmd.draft.bid_strategy,
                "targeting_json": cmd.draft.targeting_json,
                "page_id": cmd.draft.page_id,
                "pixel_id": cmd.draft.pixel_id,
                "post_id": cmd.draft.post_id,
                "ad_creative_json": cmd.draft.ad_creative_json,
                "initial_status": cmd.draft.initial_status,
            }
        results.append({
            "id": cmd.id,
            "via_id": cmd.via_id,
            "via_uid": cmd.via_uid,
            "act_id": cmd.act_id,
            "customer_id": cmd.customer_id,
            "draft_id": cmd.draft_id,
            "draft_name": cmd.draft_name,
            "command_type": cmd.command_type,
            "payload_json": cmd.payload_json,
            "status": cmd.status,
            "requested_by_telegram": cmd.requested_by_telegram,
            "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
            "draft": draft_info,
        })
    return results


@router.post("/remote-commands/{command_id}/complete", dependencies=[Depends(require_extension_or_local)])
def complete_remote_command(
    command_id: int,
    req: CompleteRemoteCommandRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Extension Chrome báo cáo kết quả hoàn thành hoặc thất bại của lệnh từ xa."""
    try:
        result = json.loads(req.result_json) if req.result_json else None
    except (TypeError, ValueError):
        result = {"raw": req.result_json}
    try:
        cmd = finish_command(
            db,
            str(command_id),
            status=req.status,
            result=result,
            result_log=req.error_message or req.result_json,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "success": True,
        "command_id": cmd.id,
        "status": cmd.status,
        "message": f"Đã cập nhật trạng thái lệnh #{cmd.id} thành {cmd.status}",
    }


# ==============================================================================
# BÁO CÁO CHI TIÊU KHÁCH HÀNG (4% PHÍ THUÊ)
# ==============================================================================

@router.get("/customer-spend-summary")
def get_customer_spend_summary(
    customer_id: Optional[int] = Query(None, description="Lọc theo mã khách hàng cụ thể"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tính toán bảng kê đối soát chi tiêu cho từng khách hàng theo quy tắc 4% phí dịch vụ.
    Tổng phải thanh toán = Chi tiêu Meta + Phí dịch vụ (4% hoặc theo tỷ lệ riêng của khách)."""
    customers_query = select(Customer).order_by(Customer.id.asc())
    if customer_id:
        customers_query = customers_query.where(Customer.id == customer_id)

    customers = db.scalars(customers_query).all()
    summaries = []
    grand_raw_spend = 0.0
    grand_fee_amount = 0.0
    grand_total_payable = 0.0

    for cust in customers:
        accounts = db.scalars(
            select(SyncedAdAccount).where(SyncedAdAccount.customer_id == cust.id)
        ).all()

        cust_raw_spend = 0.0
        cust_balance = 0.0
        cust_threshold = 0.0
        acc_details = []

        for acc in accounts:
            spent = float(acc.amount_spent or acc.total_spend or 0.0)
            bal = float(acc.balance or 0.0)
            thresh = float(acc.threshold_amount or acc.threshold or 0.0)
            cust_raw_spend += spent
            cust_balance += bal
            cust_threshold += thresh

            via_uid_val = acc.via_profile.uid if acc.via_profile else None

            acc_details.append({
                "account_id": acc.act_id,
                "name": acc.name,
                "amount_spent": spent,
                "balance": bal,
                "threshold_amount": thresh,
                "currency": acc.currency or "VND",
                "account_status": "LIVE" if acc.account_status == 1 else "DIE",
                "via_uid": via_uid_val,
                "bm_id": acc.bm_id,
            })

        # Mức phí dịch vụ mặc định 4% theo DECISIONS.md và rule dự án
        fee_raw = float(cust.fee_rate) if cust.fee_rate is not None else 0.04
        fee_rate = round(fee_raw * 100.0 if fee_raw <= 1.0 else fee_raw, 2)
        fee_amount = round(cust_raw_spend * (fee_rate / 100.0), 2)
        total_payable = round(cust_raw_spend + fee_amount, 2)

        grand_raw_spend += cust_raw_spend
        grand_fee_amount += fee_amount
        grand_total_payable += total_payable

        summaries.append({
            "customer_id": cust.id,
            "customer_name": cust.name,
            "telegram_username": cust.telegram_username,
            "telegram_chat_id": cust.telegram_chat_id,
            "fee_rate_percent": fee_rate,
            "account_count": len(accounts),
            "raw_spend": cust_raw_spend,
            "fee_amount": fee_amount,
            "total_payable": total_payable,
            "total_balance": cust_balance,
            "total_threshold": cust_threshold,
            "accounts": acc_details,
        })

    return {
        "success": True,
        "customers": summaries,
        "grand_totals": {
            "total_customers": len(summaries),
            "grand_raw_spend": grand_raw_spend,
            "grand_fee_amount": grand_fee_amount,
            "grand_total_payable": grand_total_payable,
        },
    }


@router.get("/{via_id}")
def get_via_detail(
    via_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Lấy chi tiết 1 hồ sơ VIA."""
    via = db.get(ViaProfile, via_id)
    if not via:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy VIA với ID #{via_id}")
    return serialize_via_profile(via)


@router.get("/{via_id}/2fa")
@router.get("/{via_id}/totp")
def get_via_live_2fa(
    via_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Lấy mã 2FA TOTP thời gian thực và số giây đếm ngược còn lại."""
    via = db.get(ViaProfile, via_id)
    if not via:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy VIA với ID #{via_id}")

    creds = decrypt_via_credentials(via.encrypted_credentials)
    secret = creds.get("two_fa_secret", "")
    if not secret:
        return {
            "via_id": via.id,
            "uid": via.uid,
            "code": "",
            "remaining_seconds": 0,
            "has_2fa": False,
            "message": "VIA này chưa cấu hình khóa 2FA Secret.",
        }

    code, rem = generate_totp_code(secret)
    return {
        "via_id": via.id,
        "uid": via.uid,
        "code": code,
        "remaining_seconds": rem,
        "has_2fa": True,
        "message": "Mã 2FA OTP đang có hiệu lực.",
    }


class TotpPreviewRequest(BaseModel):
    secret: str


@router.post("/totp-preview")
def preview_totp_code(req: TotpPreviewRequest) -> dict[str, Any]:
    """Tạo trước mã 2FA OTP từ chuỗi secret bất kỳ (hỗ trợ xem thử live)."""
    code, rem = generate_totp_code(req.secret)
    return {
        "success": bool(code),
        "code": code,
        "remaining_seconds": rem,
        "secret": req.secret.replace(" ", "").upper(),
        "message": "Đã tạo mã 2FA TOTP thành công." if code else "Khóa 2FA Base32 không hợp lệ.",
    }



@router.patch("/{via_id}")
@router.put("/{via_id}")
def update_via_info(
    via_id: int,
    req: UpdateViaInfoRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật nhanh Tên Profile/UID, Ghi chú và Proxy của VIA (inline editor)."""
    via = db.get(ViaProfile, via_id)
    if not via:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy VIA với ID #{via_id}")

    if req.profile_name is None and req.note is None and req.proxy_url is None:
        raise HTTPException(status_code=400, detail="Cần cung cấp ít nhất Tên Profile, Ghi chú hoặc Proxy để cập nhật.")

    if req.profile_name is not None:
        clean_name = req.profile_name.strip()
        if not clean_name:
            raise HTTPException(status_code=400, detail="Tên Profile không được để trống.")
        via.profile_name = clean_name

    if req.note is not None:
        clean_note = req.note.strip()
        via.note = clean_note if clean_note else None

    if req.proxy_url is not None:
        clean_proxy = req.proxy_url.strip()
        if clean_proxy:
            norm = normalize_proxy_config(clean_proxy)
            via.proxy_config = norm["raw"] if norm else clean_proxy
            via.proxy_status = "UNKNOWN"
        else:
            via.proxy_config = None
            via.proxy_status = "NONE"

    db.commit()
    db.refresh(via)

    return {
        "success": True,
        "message": f"Đã cập nhật thông tin VIA {via.uid}.",
        "via": serialize_via_profile(via),
    }


@router.patch("/{via_id}/proxy")
def update_via_proxy(
    via_id: int,
    req: UpdateProxyRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Gắn hoặc thay đổi Proxy riêng (IP:Port:User:Pass) cho VIA Profile."""
    via = db.get(ViaProfile, via_id)
    if not via:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy VIA với ID #{via_id}")

    norm = normalize_proxy_config(req.proxy_config)
    if not norm:
        raise HTTPException(status_code=400, detail="Định dạng Proxy không hợp lệ. Vui lòng dùng IP:Port:User:Pass hoặc URL.")

    via.proxy_config = norm["raw"]
    via.proxy_status = "UNKNOWN"
    db.commit()
    db.refresh(via)

    return {
        "success": True,
        "message": f"Đã gắn Proxy {norm['display']} thành công cho VIA {via.uid}.",
        "via": serialize_via_profile(via),
    }


@router.post("/{via_id}/check-live")
def check_single_via_live(
    via_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Kiểm tra tức thì trạng thái LIVE / DIE của UID qua Facebook Graph."""
    via = db.get(ViaProfile, via_id)
    if not via:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy VIA với ID #{via_id}")

    status = check_uid_live_status(db, via)
    return {
        "via_id": via.id,
        "uid": via.uid,
        "uid_live_status": status,
        "last_live_check_at": via.last_live_check_at.isoformat() if via.last_live_check_at else None,
        "message": f"UID {via.uid} hiện đang: {status}",
    }


@router.post("/check-live-bulk")
def check_bulk_vias_live_endpoint(
    req: CheckBulkLiveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Quét trạng thái Live/Die cho hàng loạt VIA trong hệ thống."""
    res = check_bulk_uids_live(db, via_ids=req.via_ids)
    return res


@router.post("/{via_id}/login")
def login_via_endpoint(
    via_id: int,
    req: ViaLoginRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Đăng nhập 1-Click ngay trên bảng quản lý hoặc cập nhật Cookie/Token."""
    try:
        res = login_via_profile(
            session=db,
            via_id=via_id,
            cookie=req.cookie,
            access_token=req.access_token,
        )
        return res
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{via_id}/sync-browser-cookie")
def sync_browser_cookie_endpoint(
    via_id: int,
    req: SyncBrowserCookieRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Đồng bộ session cookie thật thu thập từ trình duyệt Chrome về Backend AdsOS."""
    via = db.get(ViaProfile, via_id)
    if not via:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy VIA với ID #{via_id}")
    try:
        return save_synced_browser_cookie(session=db, via=via, raw_cookie=req.cookie, access_token=req.access_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{via_id}/harvest-session")
def harvest_via_session_endpoint(
    via_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Thu hoạch Cookie & Meta Token thời gian thực từ Chrome qua CDP hoặc Profile Vault."""
    via = db.get(ViaProfile, via_id)
    if not via:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy VIA với ID #{via_id}")
    try:
        res = harvest_session_from_profile_or_cdp(session=db, via_id=via.id)
        db.refresh(via)
        return {
            "success": res.get("success", False),
            "via_id": via.id,
            "token_status": via.token_status,
            "uid_live_status": via.uid_live_status,
            "ad_account_count": via.ad_account_count,
            "bm_count": via.bm_count,
            "page_count": via.page_count,
            "source": res.get("source"),
            "message": res.get("message", "Đã xử lý thu hoạch session."),
            "via": serialize_via_profile(via),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{via_id}/manual-credentials")
def update_manual_credentials_endpoint(
    via_id: int,
    req: ManualCredentialsRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật Cookie hoặc Access Token thủ công cho VIA và tự động kích hoạt đồng bộ tài sản."""
    via = db.get(ViaProfile, via_id)
    if not via:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy VIA với ID #{via_id}")

    cookie = req.cookie.strip() if req.cookie else None
    token = clean_meta_token(req.access_token) if req.access_token else None

    if not cookie and not token:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp ít nhất Cookie hoặc Access Token.")

    if cookie and not token:
        try:
            extracted_token, _, _ = extract_tokens_from_cookie(
                raw_cookie=cookie,
                proxy_config=via.proxy_config,
                user_agent=via.user_agent,
            )
            if extracted_token:
                token = extracted_token
        except Exception:
            pass

    creds = decrypt_via_credentials(via.encrypted_credentials)
    if cookie:
        creds["cookie"] = cookie
    if token:
        creds["access_token"] = token

    via.encrypted_credentials = encrypt_via_credentials(creds)
    via.token_status = "ACTIVE"
    via.uid_live_status = "LIVE"
    if token:
        via.last_token_refresh = utcnow()
    via.last_synced_at = utcnow()
    db.flush()

    try:
        sync_via_all_assets(db, via_id=via.id)
    except Exception as exc:
        logger.warning("Lỗi kích hoạt đồng bộ tài sản sau khi nạp credentials cho VIA %s: %s", via.uid, exc)

    db.commit()
    db.refresh(via)
    return {
        "success": True,
        "via_id": via.id,
        "token_status": via.token_status,
        "uid_live_status": via.uid_live_status,
        "ad_account_count": via.ad_account_count,
        "bm_count": via.bm_count,
        "page_count": via.page_count,
        "message": f"Đã lưu thông tin đăng nhập và đồng bộ tài sản thành công cho VIA {via.profile_name} ({via.uid}).",
        "via": serialize_via_profile(via),
    }



@router.post("/{via_id}/sync-assets")
def sync_via_assets_endpoint(
    via_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Đồng bộ tài sản BM, TKQC và Page của VIA vào hệ thống."""
    try:
        res = sync_via_all_assets(session=db, via_id=via_id)
        return res
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/sync-assets-all")
def force_sync_all_assets_endpoint(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Xếp lịch đồng bộ nền cho toàn bộ VIA đang có token ACTIVE."""
    from app.jobs.asset_sync import scheduled_asset_sync

    background_tasks.add_task(scheduled_asset_sync)
    return {
        "accepted": True,
        "message": "Đã xếp lịch đồng bộ tài sản cho toàn bộ VIA đang hoạt động.",
    }


@router.post("/{via_id}/launch-browser")
def launch_via_browser_endpoint(
    via_id: int,
    req: LaunchBrowserRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Khởi chạy Chrome profile riêng biệt cho 1 VIA cụ thể."""
    via = db.get(ViaProfile, via_id)
    if not via:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy VIA với ID #{via_id}")
    try:
        return launch_chrome_for_via(
            session=db,
            via_id=via.id,
            act_id=req.act_id,
            bm_id=req.bm_id,
            page_id=req.page_id,
            target_type=req.target_type,
            custom_url=req.custom_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{via_id}")
def delete_via(
    via_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Xóa bỏ 1 hồ sơ VIA khỏi hệ thống."""
    via = db.get(ViaProfile, via_id)
    if not via:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy VIA với ID #{via_id}")

    uid = via.uid
    db.delete(via)
    db.commit()
    return {"success": True, "message": f"Đã xóa thành công VIA #{via_id} ({uid})."}


# ==============================================================================
# SYNCED BMS ENDPOINTS
# ==============================================================================

@router.get("/bms/synced")
def list_synced_bms(
    only_primary: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Lấy danh sách tất cả BM đã đồng bộ từ các VIA (ưu tiên BM Chính Cho Thuê)."""
    query = select(SyncedBM)
    if only_primary:
        query = query.where(SyncedBM.is_primary_rental.is_(True))

    # Sắp xếp: BM chính cho thuê lên trước, sau đó theo ID
    bms = db.scalars(
        query.order_by(SyncedBM.is_primary_rental.desc(), SyncedBM.id.desc())
    ).all()

    return {
        "bms": [serialize_synced_bm(b) for b in bms],
        "total": len(bms),
        "primary_rental_count": sum(1 for b in bms if b.is_primary_rental),
    }


@router.patch("/bms/{bm_id}/primary")
def toggle_bm_primary(
    bm_id: str,
    req: TogglePrimaryBMRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Gắn hoặc gỡ cờ BM Chính Cho Thuê (★ BM Cho Thuê)."""
    bm = toggle_synced_bm_primary_rental(
        session=db,
        bm_id=bm_id,
        is_primary=req.is_primary_rental,
    )
    status_label = "Chính Cho Thuê ★" if bm.is_primary_rental else "Thường"
    return {
        "success": True,
        "message": f"Đã cập nhật trạng thái BM {bm.bm_id} thành: {status_label}",
        "bm": serialize_synced_bm(bm),
    }
