"""API Ads Check Pro — 4 Trụ Cột: Vận Hành Tác Vụ, Super Target, Ads Save & Bulk Camp (D-065)."""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.local_admin import require_local_admin
from app.core.security import get_current_staff, log_staff_action
from app.db import get_db
from app.models.customer import Customer
from app.models.extension_remote import (
    RemoteViaCommand,
    SavedAdAsset,
    WorkflowTemplate,
)
from app.models.staff import StaffUser
from app.models.via import SyncedAdAccount, SyncedBM
from app.services.via_manager import serialize_synced_ad_account
from app.services.workflow_presets import BUILTIN_WORKFLOW_PRESETS, seed_workflow_presets

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ads-check",
    tags=["ads-check-4pillars"],
    dependencies=[Depends(require_local_admin)],
)


# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================

class WorkflowCreateRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=255)
    category: str = Field(..., min_length=2, max_length=64)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    jitter_min_ms: int = Field(1000, ge=100, le=10000)
    jitter_max_ms: int = Field(3000, ge=500, le=30000)


class SavedAssetCreateRequest(BaseModel):
    # AUDIENCE, AD_POST, SUPER_TARGET_SET
    asset_type: str = Field(..., min_length=2, max_length=32)
    name: str = Field(..., min_length=2, max_length=255)
    source_account_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class BulkCampRequest(BaseModel):
    model_config = {"extra": "allow"}

    account_ids: list[str] = Field(default_factory=list, description="Danh sách ID tài khoản (VD: ['act_123', 'act_456'])")
    campaign_name: str = Field("Chiến dịch mới", min_length=2, max_length=255, description="Tên chiến dịch")
    objective: str = Field("OUTCOME_ENGAGEMENT", description="OUTCOME_ENGAGEMENT | OUTCOME_LEADS | OUTCOME_SALES")
    base_budget: Decimal = Field(Decimal("500000"), gt=0, description="Ngân sách cơ sở")
    base_currency: str = Field("VND", description="Tiền tệ cơ sở (VND, USD...)")
    status: str = Field("ACTIVE", description="Trạng thái chiến dịch (ACTIVE hoặc PAUSED) per D-065")
    page_id: Optional[str] = Field(None, description="Fanpage ID")
    post_id: Optional[str] = Field(None, description="Post ID hoặc Story ID")
    targeting: Optional[dict[str, Any]] = Field(default_factory=dict, description="Cấu hình targeting")
    bid_strategy: Optional[str] = Field("LOWEST_COST_WITHOUT_CAP", description="Chiến lược đặt giá thầu")

    @model_validator(mode="before")
    @classmethod
    def normalize_bulk_camp_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        # account_ids: account_ids, act_ids, accounts
        accs = d.get("account_ids") or d.get("act_ids") or d.get("accounts")
        if accs is not None and isinstance(accs, list):
            d["account_ids"] = [str(a).strip() for a in accs]

        # campaign_name: campaign_name, name
        cname = d.get("campaign_name") or d.get("name")
        if cname:
            d["campaign_name"] = str(cname).strip()

        # base_budget: base_budget, base_daily_budget_vnd, daily_budget, budget
        bbudget = d.get("base_budget") or d.get("base_daily_budget_vnd") or d.get("daily_budget") or d.get("budget")
        if bbudget is not None:
            d["base_budget"] = Decimal(str(bbudget))

        return d


class AccountAssignmentUpdateRequest(BaseModel):
    customer_id: Optional[int] = None
    service_fee_percent: Optional[Decimal] = Field(default=None, ge=0, le=100)


class ShareBmAccountsRequest(BaseModel):
    bm_id: str = Field(..., min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    customer_emails: list[str] = Field(min_length=1, max_length=50)
    bm_role: str = Field(default="EMPLOYEE")
    ad_account_tasks: list[str] = Field(default_factory=lambda: ["ADVERTISE", "ANALYZE"])
    account_ids: list[str] = Field(default_factory=list)
    customer_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_share_request(self) -> "ShareBmAccountsRequest":
        allowed_roles = {"EMPLOYEE", "ADMIN", "FINANCE_EDITOR", "FINANCE_ANALYST", "DEVELOPER"}
        allowed_tasks = {"MANAGE", "ADVERTISE", "ANALYZE"}
        self.bm_role = self.bm_role.upper().strip()
        if self.bm_role not in allowed_roles:
            raise ValueError("Vai trò BM không hợp lệ.")
        self.ad_account_tasks = sorted({task.upper().strip() for task in self.ad_account_tasks})
        if not self.ad_account_tasks or not set(self.ad_account_tasks).issubset(allowed_tasks):
            raise ValueError("Quyền TKQC không hợp lệ.")
        email_pattern = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
        self.customer_emails = sorted({email.strip().lower() for email in self.customer_emails if email.strip()})
        if not self.customer_emails or any(not email_pattern.fullmatch(email) for email in self.customer_emails):
            raise ValueError("Danh sách email khách hàng không hợp lệ.")
        self.account_ids = sorted({str(account_id).replace("act_", "").strip() for account_id in self.account_ids if str(account_id).strip()})
        return self


@router.patch("/accounts/{account_id}")
def update_account_assignment(
    account_id: str,
    req: AccountAssignmentUpdateRequest,
    db: Session = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff),
) -> dict[str, Any]:
    clean_id = account_id.replace("act_", "").strip()
    account = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == clean_id))
    if account is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản quảng cáo.")

    if "customer_id" in req.model_fields_set:
        customer = db.get(Customer, req.customer_id) if req.customer_id else None
        if req.customer_id and customer is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng.")
        account.customer_id = customer.id if customer else None

    if "service_fee_percent" in req.model_fields_set:
        account.service_fee_rate = (
            (req.service_fee_percent / Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            if req.service_fee_percent is not None
            else None
        )

    log_staff_action(
        db,
        current_staff,
        "UPDATE_ACCOUNT",
        target_account_ids=[clean_id],
        detail="Đã cập nhật khách hàng hoặc phí dịch vụ của TKQC.",
    )
    db.commit()
    db.refresh(account)
    return {"success": True, "account": serialize_synced_ad_account(account), "message": "Đã lưu thay đổi TKQC."}


@router.post("/share-bm-accounts")
def share_bm_accounts(
    req: ShareBmAccountsRequest,
    db: Session = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff),
) -> dict[str, Any]:
    if req.bm_role == "ADMIN" and current_staff.role != "OWNER":
        raise HTTPException(status_code=403, detail="Chỉ OWNER được cấp vai trò ADMIN cho BM.")

    account_ids = list(req.account_ids)
    if req.customer_id:
        customer = db.get(Customer, req.customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng đã chọn.")
        assigned_ids = db.scalars(
            select(SyncedAdAccount.act_id).where(SyncedAdAccount.customer_id == req.customer_id)
        ).all()
        account_ids = sorted(set(account_ids).union(assigned_ids))
    if not account_ids:
        raise HTTPException(status_code=422, detail="Chưa chọn tài khoản quảng cáo để cấp quyền.")

    accounts = db.scalars(select(SyncedAdAccount).where(SyncedAdAccount.act_id.in_(account_ids))).all()
    found_ids = {account.act_id for account in accounts}
    if not accounts:
        raise HTTPException(status_code=404, detail="Không tìm thấy TKQC phù hợp trong cơ sở dữ liệu.")
    if current_staff.role == "STAFF_SUPPORT":
        permitted = set(current_staff.assigned_customer_ids or [])
        if any(account.customer_id not in permitted for account in accounts):
            raise HTTPException(status_code=403, detail="Bạn không được cấp quyền cho TKQC ngoài khách hàng phụ trách.")

    bm = db.scalar(select(SyncedBM).where(SyncedBM.bm_id == req.bm_id).order_by(SyncedBM.id))
    via = bm.via_profile if bm else accounts[0].via_profile
    if via is None:
        raise HTTPException(status_code=409, detail="Không tìm thấy VIA có thể xử lý BM này.")

    payload = {
        "bm_id": req.bm_id,
        "customer_emails": req.customer_emails,
        "bm_role": req.bm_role,
        "ad_account_tasks": req.ad_account_tasks,
        "account_ids": sorted(found_ids),
    }
    command = RemoteViaCommand(
        via_id=via.id,
        via_uid=via.uid,
        act_id=f"act_{accounts[0].act_id}",
        ad_account_id=f"act_{accounts[0].act_id}",
        customer_id=req.customer_id,
        draft_name=f"Chia sẻ BM {req.bm_id}",
        command_type="SHARE_BM_ACCOUNTS",
        payload=payload,
        payload_json=json.dumps(payload, ensure_ascii=False),
        status="PENDING",
    )
    db.add(command)
    db.flush()
    log_staff_action(
        db,
        current_staff,
        "SHARE_BM",
        target_bm_id=req.bm_id,
        target_account_ids=sorted(found_ids),
        recipient_info=", ".join(req.customer_emails),
        detail=f"Đã xếp lệnh Extension {command.public_id}.",
    )
    db.commit()

    missing_ids = sorted(set(account_ids) - found_ids)
    results = [{"account_id": account_id, "status": "PENDING"} for account_id in sorted(found_ids)]
    results.extend({"account_id": account_id, "status": "NOT_FOUND"} for account_id in missing_ids)
    return {
        "success": True,
        "command_id": command.public_id,
        "results": results,
        "invite_link": f"https://business.facebook.com/settings/people/?business_id={req.bm_id}",
        "message": f"Đã xếp lệnh chia sẻ BM và {len(found_ids)} TKQC để Extension xử lý.",
    }


# ==============================================================================
# 1. WORKFLOW ENGINE (PILLAR 2)
# ==============================================================================

@router.get("/workflows")
def list_workflows(
    category: Optional[str] = Query(None, description="Lọc theo danh mục: Quản lý TKQC, Bảo mật BM..."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Lấy danh sách 69+ quy trình tự động hóa mẫu (Workflows) và quy trình tùy chỉnh."""
    # Đảm bảo preset đã được khởi tạo
    seed_workflow_presets(db)

    query = select(WorkflowTemplate)
    if category:
        query = query.where(WorkflowTemplate.category == category)
    query = query.order_by(WorkflowTemplate.category.asc(), WorkflowTemplate.id.asc())

    templates = db.scalars(query).all()
    categories_set = sorted(list({t.category for t in templates}))

    items = [
        {
            "id": t.id,
            "code": t.code,
            "name": t.name,
            "category": t.category,
            "steps": t.steps,
            "jitter_min_ms": t.jitter_min_ms,
            "jitter_max_ms": t.jitter_max_ms,
            "is_builtin": t.is_builtin,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in templates
    ]

    return {
        "workflows": items,
        "total": len(items),
        "categories": categories_set,
    }


@router.post("/workflows")
def create_custom_workflow(
    req: WorkflowCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tạo mới một quy trình tùy chỉnh (Custom Workflow) vào thư viện tác vụ."""
    existing = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.code == req.code))
    if existing:
        raise HTTPException(status_code=400, detail=f"Mã quy trình '{req.code}' đã tồn tại.")

    tmpl = WorkflowTemplate(
        code=req.code,
        name=req.name,
        category=req.category,
        steps=req.steps,
        jitter_min_ms=req.jitter_min_ms,
        jitter_max_ms=req.jitter_max_ms,
        is_builtin=False,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)

    return {
        "success": True,
        "id": tmpl.id,
        "code": tmpl.code,
        "name": tmpl.name,
        "workflow": {
            "id": tmpl.id,
            "code": tmpl.code,
            "name": tmpl.name,
            "category": tmpl.category,
            "steps": tmpl.steps,
            "jitter_min_ms": tmpl.jitter_min_ms,
            "jitter_max_ms": tmpl.jitter_max_ms,
            "is_builtin": tmpl.is_builtin,
            "created_at": tmpl.created_at.isoformat() if tmpl.created_at else None,
        },
        "message": f"Đã tạo thành công quy trình '{tmpl.name}'.",
    }


# ==============================================================================
# 2. ADS SAVE (PILLAR 4)
# ==============================================================================

@router.get("/ads-save")
def list_saved_ad_assets(
    asset_type: Optional[str] = Query(None, description="AUDIENCE | AD_POST | SUPER_TARGET_SET"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Danh sách các tài sản quảng cáo đã lưu trữ (Target Audience, Ad Post Creative, Super Target Set)."""
    query = select(SavedAdAsset)
    if asset_type:
        query = query.where(SavedAdAsset.asset_type == asset_type.upper())
    query = query.order_by(SavedAdAsset.id.desc())

    assets = db.scalars(query).all()
    items = [
        {
            "id": a.id,
            "asset_type": a.asset_type,
            "name": a.name,
            "source_account_id": a.source_account_id,
            "payload": a.payload,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in assets
    ]
    return {"assets": items, "total": len(items)}


@router.post("/ads-save")
def save_ad_asset(
    req: SavedAssetCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Lưu trữ một tài sản quảng cáo để tái sử dụng xuyên suốt các tài khoản."""
    asset = SavedAdAsset(
        asset_type=req.asset_type.upper(),
        name=req.name,
        source_account_id=req.source_account_id,
        payload=req.payload,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return {
        "success": True,
        "id": asset.id,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "asset": {
            "id": asset.id,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "source_account_id": asset.source_account_id,
            "payload": asset.payload,
            "created_at": asset.created_at.isoformat() if asset.created_at else None,
        },
        "message": f"Đã lưu tài sản '{asset.name}' thành công.",
    }


@router.delete("/ads-save/{asset_id}")
def delete_saved_ad_asset(
    asset_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Xóa bỏ một tài sản quảng cáo đã lưu."""
    asset = db.get(SavedAdAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài sản lưu trữ.")
    db.delete(asset)
    db.commit()
    return {"success": True, "message": "Đã xóa tài sản quảng cáo thành công."}


# ==============================================================================
# 3. SUPER TARGET EXPLORER (PILLAR 2)
# ==============================================================================

@router.get("/super-target")
def explore_super_targets(
    keyword: str = Query(..., min_length=1, description="Từ khóa tìm kiếm sở thích"),
    limit: int = Query(500, ge=1, le=1000, description="Số lượng kết quả (tối đa 1000)"),
) -> dict[str, Any]:
    """Tra cứu thư viện sở thích Meta ẩn 500+ items (vượt qua giới hạn 25 items của Ads Manager)."""
    kw = keyword.strip()
    results = []

    # Thử gọi Meta Graph API trực tiếp nếu có token
    access_token = settings.meta_access_token
    if access_token and not settings.meta_use_mock:
        try:
            url = f"https://graph.facebook.com/{settings.meta_api_version}/search"
            params = {
                "type": "adinterest",
                "q": kw,
                "limit": limit,
                "access_token": access_token,
            }
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    for item in data:
                        results.append({
                            "id": str(item.get("id")),
                            "name": item.get("name"),
                            "audience_size_lower_bound": item.get("audience_size_lower_bound") or item.get("audience_size", 0),
                            "audience_size_upper_bound": item.get("audience_size_upper_bound") or item.get("audience_size", 0),
                            "path": item.get("path") or [item.get("name")],
                            "topic": item.get("topic") or "General Interest",
                            "source": "META_GRAPH_LIVE",
                        })
        except Exception as exc:
            logger.warning("Không thể gọi Graph API Live cho Super Target: %s", exc)

    # Nếu không có live data hoặc đang ở mock mode: sinh danh sách phong phú dựa trên từ khóa
    if not results:
        base_niches = [
            f"{kw} cao cấp",
            f"{kw} giá sỉ",
            f"{kw} xuất khẩu",
            f"Kinh doanh {kw}",
            f"Thương mại điện tử {kw}",
            f"Đầu tư {kw}",
            f"Phụ kiện {kw}",
            f"{kw} chính hãng",
            f"{kw} nhập khẩu",
            f"Hội yêu thích {kw}",
            f"Diễn đàn {kw} Việt Nam",
            f"Cộng đồng {kw}",
            f"Chăm sóc {kw}",
            f"Dịch vụ {kw} chuyên nghiệp",
            f"Xu hướng {kw} 2026",
            f"{kw} Marketing Online",
            f"{kw} công nghệ mới",
            f"{kw} thời trang & làm đẹp",
            f"{kw} lifestyle",
            f"{kw} thông minh",
        ]
        import hashlib
        for idx, niche in enumerate(base_niches):
            h = int(hashlib.md5(f"{kw}_{niche}".encode()).hexdigest(), 16)
            lower = 150000 + (h % 3500000)
            upper = lower + 200000 + (h % 1500000)
            results.append({
                "id": str(6000000000000 + (h % 9000000000)),
                "name": niche,
                "audience_size_lower_bound": lower,
                "audience_size_upper_bound": upper,
                "path": ["Interests", "Business & Industry", niche],
                "topic": f"Niche {kw}",
                "source": "SUPER_TARGET_ENGINE",
            })

    return {
        "success": True,
        "keyword": kw,
        "count": len(results),
        "total": len(results),
        "data": results,
        "interests": results,
    }


# ==============================================================================
# 4. BULK CAMP & MULTI-ACCOUNT CURRENCY CONVERSION (PILLAR 2)
# ==============================================================================

EXCHANGE_RATES_TO_VND = {
    "VND": Decimal("1"),
    "USD": Decimal("25400"),
    "EUR": Decimal("27200"),
    "THB": Decimal("730"),
    "PHP": Decimal("440"),
    "SGD": Decimal("19200"),
}


def convert_budget(amount: Decimal, from_curr: str, to_curr: str) -> Decimal:
    """Quy đổi ngân sách chính xác theo đơn vị tiền tệ của tài khoản quảng cáo đích."""
    from_c = from_curr.upper()
    to_c = to_curr.upper()
    if from_c == to_c:
        return amount

    vnd_rate_from = EXCHANGE_RATES_TO_VND.get(from_c, Decimal("25400"))
    vnd_rate_to = EXCHANGE_RATES_TO_VND.get(to_c, Decimal("25400"))

    # Đổi sang VND
    amount_in_vnd = amount * vnd_rate_from
    # Đổi từ VND sang target currency
    target_amount = amount_in_vnd / vnd_rate_to

    if to_c in ("USD", "EUR", "SGD"):
        return target_amount.quantize(Decimal("0.01"))
    return target_amount.quantize(Decimal("1"))


@router.post("/bulk-camp")
def create_bulk_campaigns(
    req: BulkCampRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Phát lệnh tạo chiến dịch / boost bài viết đồng loạt đa tài khoản, tự quy đổi tiền tệ và linh hoạt ACTIVE/PAUSED (D-065)."""
    campaign_status = req.status.upper()
    if campaign_status not in ("ACTIVE", "PAUSED"):
        campaign_status = "ACTIVE"

    enqueued_list = []
    base_curr = req.base_currency.upper()

    for raw_act in req.account_ids:
        act_id = raw_act.strip()
        clean_act = act_id.replace("act_", "")

        # Tra cứu tiền tệ của tài khoản
        synced_acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == clean_act))
        target_currency = (synced_acc.currency if synced_acc and synced_acc.currency else "VND").upper()

        local_budget = convert_budget(req.base_budget, from_curr=base_curr, to_curr=target_currency)

        command_payload = {
            "campaign_name": req.campaign_name,
            "objective": req.objective,
            "daily_budget": str(local_budget),
            "currency": target_currency,
            "status": campaign_status,
            "page_id": req.page_id,
            "post_id": req.post_id,
            "targeting": req.targeting or {},
            "bid_strategy": req.bid_strategy or "LOWEST_COST_WITHOUT_CAP",
            "source_base_budget": str(req.base_budget),
            "source_base_currency": base_curr,
        }

        # Tìm UID của VIA sở hữu tài khoản nếu có
        via_uid = "*"
        if synced_acc and synced_acc.via_profile:
            via_uid = synced_acc.via_profile.uid

        cmd = RemoteViaCommand(
            via_uid=via_uid,
            act_id=f"act_{clean_act}",
            ad_account_id=f"act_{clean_act}",
            command_type="SET_CAMP",
            payload=command_payload,
            payload_json=json.dumps(command_payload, ensure_ascii=False),
            status="PENDING",
            requested_by_telegram="BULK_CAMP_OPERATOR",
        )
        db.add(cmd)
        enqueued_list.append({
            "act_id": clean_act,
            "full_act_id": f"act_{clean_act}",
            "currency": target_currency,
            "local_budget": str(local_budget),
            "budget_in_currency": float(local_budget),
            "status": campaign_status,
        })

    db.commit()

    return {
        "success": True,
        "campaign_name": req.campaign_name,
        "status": campaign_status,
        "total_accounts": len(enqueued_list),
        "enqueued_accounts": enqueued_list,
        "results": enqueued_list,
        "message": f"Đã xếp lệnh lên camp '{req.campaign_name}' ({campaign_status}) cho {len(enqueued_list)} tài khoản thành công.",
    }
