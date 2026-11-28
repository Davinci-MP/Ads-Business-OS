"""Quét tài sản Meta của một VIA kiểu ToolFB — CHỈ qua Graph API chính thức (token OAuth).

Lấy: TKQC cá nhân + TKQC của từng BM (owned/client) với đủ trường (trạng thái, lý do khoá,
limit/ngày, ngưỡng, số dư, đã tiêu, spend cap, thẻ, múi giờ, BM, quyền, ngày tạo, pixel),
danh sách BM (xác minh, ngày tạo, số TK) và Fanpage.

Quy tắc (AGENTS.md):
- Trường Meta không trả → để trống, KHÔNG điền giá trị giả.
- Lỗi API → giữ nguyên dữ liệu cũ, báo lỗi; không xoá bản ghi nào.
- Tiền theo bảng offset của Marketing API (normalize_amount).
- Không log token. Không dùng cookie/proxy (API chính thức không cần).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.customer import utcnow
from app.models.via import SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.via_manager import (
    clean_meta_token,
    fetch_all_graph_pages_with_fallback,
    normalize_amount,
)

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com"

# account_status / disable_reason theo tài liệu Ad Account của Marketing API.
ACCOUNT_STATUS = {
    1: ("ACTIVE", "LIVE"), 2: ("DISABLED", "DIE"), 3: ("UNSETTLED", "DIE"),
    7: ("PENDING_RISK_REVIEW", "WARNING"), 8: ("PENDING_SETTLEMENT", "WARNING"),
    9: ("IN_GRACE_PERIOD", "WARNING"), 100: ("PENDING_CLOSURE", "DIE"), 101: ("CLOSED", "DIE"),
    201: ("ANY_ACTIVE", "LIVE"), 202: ("ANY_CLOSED", "DIE"),
}
DISABLE_REASON = {
    0: "NONE", 1: "ADS_INTEGRITY_POLICY", 2: "ADS_IP_REVIEW", 3: "RISK_PAYMENT",
    4: "GRAY_ACCOUNT_SHUT_DOWN", 5: "ADS_AFC_REVIEW", 6: "BUSINESS_INTEGRITY_RAR",
    7: "PERMANENT_CLOSE", 8: "UNUSED_RESELLER_ACCOUNT", 9: "UNUSED_ACCOUNT",
    10: "UMBRELLA_AD_ACCOUNT", 11: "BUSINESS_MANAGER_INTEGRITY_POLICY",
    12: "MISREPRESENTED_AD_ACCOUNT", 13: "AOAB_DESHARE_LEGAL_ENTITY",
    14: "CTX_THREAD_REVIEW", 15: "COMPROMISED_AD_ACCOUNT",
}

ACCOUNT_FIELDS_FULL = (
    "id,account_id,name,account_status,disable_reason,currency,balance,amount_spent,spend_cap,"
    "adtrust_dsl,timezone_name,created_time,business{id,name},is_prepay_account,user_tasks,"
    "adspaymentcycle{threshold_amount},funding_source_details,"
    "adspixels.limit(50){id,name,last_fired_time,creation_time,is_unavailable}"
)
ACCOUNT_FIELDS_FALLBACK = (
    "id,account_id,name,account_status,disable_reason,currency,balance,amount_spent,spend_cap,"
    "adtrust_dsl,timezone_name,created_time,business{id,name}"
)
ACCOUNT_FIELDS_MINIMAL = "id,account_id,name,account_status,currency,balance,amount_spent"


class ScanAuthError(RuntimeError):
    """Token hết hạn / bị thu hồi (code 190) — dừng quét, giữ dữ liệu cũ."""


def _graph_url(path: str) -> str:
    return f"{GRAPH}/{settings.meta_api_version}/{path.lstrip('/')}"


def _parse_time(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        # Graph trả dạng 2021-05-04T10:22:33+0000
        return datetime.strptime(str(raw), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None


def _error_of(payload: Any) -> dict[str, Any]:
    return payload.get("error", {}) if isinstance(payload, dict) else {}


def _role_from_tasks(tasks: Any) -> str:
    items = {str(t).upper() for t in tasks} if isinstance(tasks, list) else set()
    if "MANAGE" in items:
        return "ADMIN"
    if "ADVERTISE" in items:
        return "ADVERTISER"
    if "ANALYZE" in items:
        return "ANALYST"
    return ""


def parse_account(raw: dict[str, Any], *, bm: Optional[tuple[str, str]] = None) -> Optional[dict[str, Any]]:
    """Graph ad account → dict chỉ gồm giá trị Meta thật trả về."""
    act_num = str(raw.get("account_id") or str(raw.get("id") or "").replace("act_", "")).strip()
    if not act_num:
        return None
    currency = str(raw.get("currency") or "").upper()

    def money(key: str) -> Optional[float]:
        return normalize_amount(raw[key], currency) if raw.get(key) not in (None, "") else None

    try:
        status_code = int(raw.get("account_status"))
    except (TypeError, ValueError):
        status_code = None
    status_name, status_dot = ACCOUNT_STATUS.get(status_code, ("", "WARNING"))

    reason = raw.get("disable_reason")
    try:
        reason_name = DISABLE_REASON.get(int(reason), str(reason))
    except (TypeError, ValueError):
        reason_name = str(reason or "")

    cycle = raw.get("adspaymentcycle") or {}
    cycle_rows = cycle.get("data") if isinstance(cycle, dict) else None
    cycle_row = cycle_rows[0] if isinstance(cycle_rows, list) and cycle_rows else (cycle if isinstance(cycle, dict) else {})
    threshold = cycle_row.get("threshold_amount")

    funding = raw.get("funding_source_details") or {}
    display = str(funding.get("display_string") or "").strip()
    last4_match = re.search(r"(\d{4})\D*$", display)

    biz = raw.get("business") if isinstance(raw.get("business"), dict) else None
    bm_id = str(biz["id"]) if biz and biz.get("id") else (bm[0] if bm else None)
    bm_name = str(biz.get("name") or "") if biz else (bm[1] if bm else None)

    pixels_raw = (raw.get("adspixels") or {}).get("data") if isinstance(raw.get("adspixels"), dict) else None
    pixels = [
        {
            "id": str(px.get("id")),
            "name": px.get("name") or "",
            "last_fired_time": px.get("last_fired_time"),
            "creation_time": px.get("creation_time"),
            "is_unavailable": bool(px.get("is_unavailable", False)),
        }
        for px in (pixels_raw or [])
        if isinstance(px, dict) and px.get("id")
    ]

    return {
        "act_id": act_num,
        "name": str(raw.get("name") or f"act_{act_num}"),
        "account_status": status_code if status_code is not None else 0,
        "status_name": status_name,
        "status_dot": status_dot,
        "disable_reason": reason_name or "NONE",
        "currency": currency,
        "balance": money("balance"),
        "amount_spent": money("amount_spent"),
        "spend_cap": money("spend_cap"),
        "ad_trust_dsl": money("adtrust_dsl"),
        "threshold": normalize_amount(threshold, currency) if threshold not in (None, "") else None,
        "timezone_name": str(raw.get("timezone_name") or ""),
        "created_time": _parse_time(raw.get("created_time")),
        "bm_id": bm_id,
        "business_name": bm_name or None,
        "account_type": "BM" if bm_id else "PERSONAL",
        "is_prepay": raw.get("is_prepay_account") if isinstance(raw.get("is_prepay_account"), bool) else None,
        "user_tasks": ",".join(str(t) for t in raw["user_tasks"]) if isinstance(raw.get("user_tasks"), list) else None,
        "user_role": _role_from_tasks(raw.get("user_tasks")),
        "card_display": display or None,
        "card_last4": last4_match.group(1) if last4_match else None,
        "pixels": pixels if isinstance(pixels_raw, list) else None,
    }


def _fetch_accounts(client: httpx.Client, token: str, path: str, *, bm: Optional[tuple[str, str]] = None,
                    max_pages: int = 20) -> tuple[list[dict[str, Any]], Optional[str]]:
    status, items, payload = fetch_all_graph_pages_with_fallback(
        client=client, url=_graph_url(path), token=token,
        primary_fields=ACCOUNT_FIELDS_FULL, fallback_fields=ACCOUNT_FIELDS_FALLBACK,
        minimal_fields=ACCOUNT_FIELDS_MINIMAL, extra_params={"limit": 100}, max_pages=max_pages,
    )
    if status != 200:
        err = _error_of(payload)
        if err.get("code") == 190:
            raise ScanAuthError(err.get("message") or "Token Meta hết hạn hoặc bị thu hồi")
        return [], f"{path}: HTTP {status} — {err.get('message') or 'Meta từ chối yêu cầu'}"
    parsed = [p for p in (parse_account(item, bm=bm) for item in items if isinstance(item, dict)) if p]
    return parsed, None


def fetch_via_assets(token: str, transport: Optional[httpx.BaseTransport] = None) -> dict[str, Any]:
    """Gọi Graph lấy toàn bộ tài sản của token; không đụng DB."""
    errors: list[str] = []
    accounts: dict[str, dict[str, Any]] = {}
    bms: dict[str, dict[str, Any]] = {}
    pages: list[dict[str, Any]] = []
    ok = {"accounts": True, "bms": True, "pages": True}
    with httpx.Client(timeout=30.0, transport=transport, headers={"User-Agent": "AdsBusinessOS/2.0"}) as client:
        personal, err = _fetch_accounts(client, token, "me/adaccounts")
        if err:
            errors.append(err)
            ok["accounts"] = False
        for acc in personal:
            accounts[acc["act_id"]] = acc

        status, bm_items, payload = fetch_all_graph_pages_with_fallback(
            client=client, url=_graph_url("me/businesses"), token=token,
            primary_fields="id,name,verification_status,created_time", fallback_fields="id,name",
            extra_params={"limit": 100}, max_pages=20,
        )
        if status != 200:
            err_info = _error_of(payload)
            if err_info.get("code") == 190:
                raise ScanAuthError(err_info.get("message") or "Token Meta hết hạn")
            errors.append(f"me/businesses: HTTP {status} — {err_info.get('message') or 'Meta từ chối yêu cầu'}")
            ok["bms"] = False
        for b in bm_items:
            bm_id = str(b.get("id") or "").strip()
            if not bm_id:
                continue
            bm_name = str(b.get("name") or f"BM {bm_id}")
            owned, err_o = _fetch_accounts(client, token, f"{bm_id}/owned_ad_accounts", bm=(bm_id, bm_name))
            client_accs, err_c = _fetch_accounts(client, token, f"{bm_id}/client_ad_accounts", bm=(bm_id, bm_name))
            if err_o or err_c:
                errors.extend(e for e in (err_o, err_c) if e)
                ok["accounts"] = False  # thiếu TK của BM → không ghi đè tổng số TK
            for acc in owned + client_accs:
                # Ưu tiên bản có nhiều trường hơn nếu cùng TK xuất hiện ở nhiều nguồn.
                prev = accounts.get(acc["act_id"])
                if prev is None or sum(v is not None for v in acc.values()) > sum(v is not None for v in prev.values()):
                    accounts[acc["act_id"]] = acc
            created = _parse_time(b.get("created_time"))
            bms[bm_id] = {
                "bm_id": bm_id,
                "name": bm_name,
                "verified_status": str(b.get("verification_status") or ""),
                "created_year": str(created.year) if created else None,
                "ad_account_count": len({a["act_id"] for a in owned + client_accs}),
            }

        status, page_items, payload = fetch_all_graph_pages_with_fallback(
            client=client, url=_graph_url("me/accounts"), token=token,
            primary_fields="id,name,category,fan_count,followers_count", fallback_fields="id,name,category",
            extra_params={"limit": 100}, max_pages=20,
        )
        if status != 200:
            errors.append(f"me/accounts: HTTP {status} — {_error_of(payload).get('message') or 'Meta từ chối yêu cầu'}")
            ok["pages"] = False
        for p in page_items:
            if p.get("id"):
                pages.append({
                    "page_id": str(p["id"]),
                    "name": str(p.get("name") or p["id"]),
                    "category": p.get("category"),
                    "fan_count": p.get("fan_count") if isinstance(p.get("fan_count"), int) else None,
                    "followers_count": p.get("followers_count") if isinstance(p.get("followers_count"), int) else None,
                })
    return {"accounts": list(accounts.values()), "bms": list(bms.values()), "pages": pages, "errors": errors, "ok": ok}


def _apply_account(row: SyncedAdAccount, acc: dict[str, Any], now: datetime) -> None:
    row.name = acc["name"]
    row.account_status = acc["account_status"]
    row.status_dot = acc["status_dot"]
    row.disable_reason = acc["disable_reason"] or "NONE"
    if acc["currency"]:
        row.currency = acc["currency"]
    for col, key in (("balance", "balance"), ("total_spend", "amount_spent"), ("amount_spent", "amount_spent"),
                     ("ad_trust_dsl", "ad_trust_dsl"), ("threshold", "threshold"), ("threshold_amount", "threshold")):
        if acc[key] is not None:
            setattr(row, col, acc[key])
    row.spend_cap = acc["spend_cap"]
    row.timezone_name = acc["timezone_name"] or row.timezone_name
    row.created_time = acc["created_time"] or row.created_time
    row.bm_id = acc["bm_id"]
    row.business_name = acc["business_name"]
    row.account_type = acc["account_type"]
    if acc["is_prepay"] is not None:
        row.is_prepay = acc["is_prepay"]
    if acc["user_tasks"] is not None:
        row.user_tasks = acc["user_tasks"]
        row.user_role = acc["user_role"]
    if acc["card_display"] is not None:
        row.funding_source_summary = acc["card_display"]
        row.funding_source_last_four = acc["card_last4"]
    if acc["pixels"] is not None:
        row.pixel_list = acc["pixels"]
        row.pixel_id = acc["pixels"][0]["id"] if acc["pixels"] else None
    row.last_scanned_at = now


def save_scan(session: Session, via: ViaProfile, result: dict[str, Any], now: Optional[datetime] = None) -> dict[str, int]:
    """Upsert kết quả quét. Không xoá gì; TK đã thuộc VIA khác đang ACTIVE giữ nguyên chủ."""
    now = now or utcnow()
    act_ids = [a["act_id"] for a in result["accounts"]]
    existing = {
        r.act_id: r
        for r in session.scalars(select(SyncedAdAccount).where(SyncedAdAccount.act_id.in_(act_ids))).all()
    } if act_ids else {}
    for acc in result["accounts"]:
        row = existing.get(acc["act_id"])
        if row is None:
            row = SyncedAdAccount(
                via_profile_id=via.id, act_id=acc["act_id"], name=acc["name"],
                user_role="", country_code="", tax_status="", admin_count=0,
                timezone_name=acc["timezone_name"] or "",
            )
            session.add(row)
        elif row.via_profile_id != via.id:
            owner = session.get(ViaProfile, row.via_profile_id)
            if owner is None or owner.token_status != "ACTIVE":
                row.via_profile_id = via.id
        _apply_account(row, acc, now)

    for b in result["bms"]:
        row = session.scalar(
            select(SyncedBM).where(SyncedBM.bm_id == b["bm_id"], SyncedBM.via_profile_id == via.id)
        )
        if row is None:
            row = SyncedBM(bm_id=b["bm_id"], via_profile_id=via.id, name=b["name"])
            session.add(row)
        row.name = b["name"]
        row.status = "ACTIVE"
        if b["verified_status"]:
            row.verified_status = b["verified_status"]
        row.created_year = b["created_year"] or row.created_year
        row.ad_account_count = b["ad_account_count"]

    for p in result["pages"]:
        row = session.scalar(
            select(SyncedPage).where(SyncedPage.page_id == p["page_id"], SyncedPage.via_profile_id == via.id)
        )
        if row is None:
            row = SyncedPage(page_id=p["page_id"], via_profile_id=via.id, name=p["name"])
            session.add(row)
        row.name = p["name"]
        row.category = p["category"]
        if p["fan_count"] is not None:
            row.likes_count = p["fan_count"]
        if p["followers_count"] is not None:
            row.followers_count = p["followers_count"]

    pixel_ids = {px["id"] for a in result["accounts"] for px in (a["pixels"] or [])}
    step_ok = result.get("ok", {"accounts": True, "bms": True, "pages": True})
    # Chỉ cập nhật số đếm của bước quét thành công (lỗi → giữ số cũ, không ghi đè bằng 0).
    if step_ok["accounts"]:
        via.ad_account_count = len(result["accounts"])
    if step_ok["bms"]:
        via.bm_count = len(result["bms"])
    if step_ok["pages"]:
        via.page_count = len(result["pages"])
    via.last_synced_at = now
    return {
        "accounts": len(result["accounts"]),
        "personal_accounts": sum(a["account_type"] == "PERSONAL" for a in result["accounts"]),
        "bm_accounts": sum(a["account_type"] == "BM" for a in result["accounts"]),
        "live": sum(a["status_dot"] == "LIVE" for a in result["accounts"]),
        "die": sum(a["status_dot"] == "DIE" for a in result["accounts"]),
        "bms": len(result["bms"]),
        "pages": len(result["pages"]),
        "pixels": len(pixel_ids),
    }


def scan_via(session: Session, via: ViaProfile, transport: Optional[httpx.BaseTransport] = None) -> dict[str, Any]:
    """Quét một VIA và lưu. Lỗi → giữ dữ liệu cũ (rollback), trả báo cáo lỗi."""
    token = clean_meta_token(via.access_token)
    if not token:
        return {"ok": False, "via_id": via.id, "error": "VIA chưa có token. Hãy bấm Cấp quyền Facebook trước."}
    try:
        result = fetch_via_assets(token, transport=transport)
    except ScanAuthError as exc:
        via.token_status = "EXPIRED"
        session.commit()
        return {"ok": False, "via_id": via.id, "error": f"Token hết hạn hoặc bị thu hồi: {exc}. Hãy cấp quyền lại."}
    except httpx.HTTPError as exc:
        session.rollback()
        return {"ok": False, "via_id": via.id, "error": f"Không kết nối được Meta Graph API ({type(exc).__name__}). Dữ liệu cũ được giữ nguyên."}
    if not any(result["ok"].values()):
        session.rollback()
        detail = result["errors"][0] if result["errors"] else "Meta không phản hồi"
        return {"ok": False, "via_id": via.id, "error": f"Quét thất bại ({detail}). Dữ liệu cũ được giữ nguyên.",
                "warnings": result["errors"]}
    try:
        counts = save_scan(session, via, result)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Lưu kết quả quét VIA %s thất bại", via.id)
        return {"ok": False, "via_id": via.id, "error": "Không lưu được kết quả quét. Dữ liệu cũ được giữ nguyên."}
    return {"ok": True, "via_id": via.id, "counts": counts, "warnings": result["errors"]}


def scan_via_job(session: Session, via_id: int, **_: Any) -> dict[str, Any]:
    """Adapter cho job định kỳ (scheduled_asset_sync)."""
    via = session.get(ViaProfile, via_id)
    if via is None:
        return {"success": False, "status": "VIA_NOT_FOUND"}
    result = scan_via(session, via)
    return {"success": result["ok"], "status": "OK" if result["ok"] else result.get("error", "ERROR")}


def aggregate_pixels(session: Session, via_id: Optional[int] = None, search: Optional[str] = None) -> list[dict[str, Any]]:
    """Gộp pixel từ pixel_list của các TKQC (đã quét qua /act_x/adspixels)."""
    query = select(SyncedAdAccount).where(SyncedAdAccount.pixel_list.is_not(None))
    if via_id:
        query = query.where(SyncedAdAccount.via_profile_id == via_id)
    pixels: dict[str, dict[str, Any]] = {}
    for acc in session.scalars(query).all():
        for px in acc.pixel_list or []:
            if not isinstance(px, dict) or not px.get("id"):
                continue
            item = pixels.setdefault(str(px["id"]), {
                "pixel_id": str(px["id"]), "name": px.get("name") or "",
                "last_fired_time": px.get("last_fired_time"), "creation_time": px.get("creation_time"),
                "is_unavailable": bool(px.get("is_unavailable", False)), "accounts": [],
            })
            if px.get("last_fired_time") and (not item["last_fired_time"] or px["last_fired_time"] > item["last_fired_time"]):
                item["last_fired_time"] = px["last_fired_time"]
            item["accounts"].append({"act_id": acc.act_id, "name": acc.name})
    rows = list(pixels.values())
    if search:
        needle = search.strip().lower()
        rows = [r for r in rows if needle in r["pixel_id"] or needle in r["name"].lower()
                or any(needle in a["act_id"] or needle in (a["name"] or "").lower() for a in r["accounts"])]
    rows.sort(key=lambda r: r["last_fired_time"] or "", reverse=True)
    return rows
