"""MaxCare Manager — mô hình vận hành dàn VIA kiểu MaxCare.

Chức năng:
1. Parser nhập linh hoạt: pipe `uid|pass|2FA|mail|pass mail|backup|cookie|token`
   kèm token khóa `category=`, `device=`, `note=`, `gender=`, `birthday=`, `proxy=`; và JSON
   [{uid, password, two_fa_secret, ...}] hàng loạt.
2. Danh mục VIA (Farm, Daily, Sto, Scan ctv, Scan kh, CK...) gán tự động trước khi chạy luồng chính.
3. Bulk login đa luồng (asyncio Semaphore 5-10) harvest Token EAAB/EAAG + Cookie c_user/xs vào
   Fernet credentials, cập nhật token_status.
4. Nhật ký hoạt động MaxcareActivityLog append-only cho mọi hành động.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from typing import Any, Callable, Optional

from sqlalchemy import func, select

from app.models.customer import utcnow
from app.models.via import MaxcareActivityLog, ViaCategory, ViaProfile
from app.services.via_manager import (
    create_or_update_via,
    get_isolated_profile_dir,
    parse_via_string_line,
)

logger = logging.getLogger(__name__)

_DB_WRITE_LOCK = threading.Lock()

KEY_NAMES = r"category|device|note|gender|birthday|proxy"

CUSTOM_KEY_PATTERN = re.compile(
    rf"\b({KEY_NAMES})\s*[=:]\s*(.*?)\s*(?=\||\b(?:{KEY_NAMES})\s*[=:]|$)",
    re.IGNORECASE,
)
GENDER_TOKENS = {
    "nam": "Nam",
    "nu": "Nữ",
    "male": "Nam",
    "female": "Nữ",
    "m": "Nam",
    "f": "Nữ",
}


def _resolve_concurrency(concurrency: Optional[int] = None) -> int:
    if concurrency is not None and int(concurrency) > 0:
        return max(1, min(int(concurrency), 20))
    env_value = (os_value := __import__("os").getenv("ADSOS_MAXCARE_CONCURRENCY", "")).strip()
    if env_value.isdigit():
        return max(1, min(int(env_value), 20))
    return 5


# =============================================================================
# 1. DANH MỤC (CATEGORY)
# =============================================================================


def get_or_create_category(session, name: str, color: Optional[str] = None) -> ViaCategory:
    """Lấy hoặc tạo danh mục VIA theo tên (không phân biệt hoa/thường)."""
    clean = (name or "").strip()
    if not clean:
        raise ValueError("Tên danh mục không được để trống.")
    existing = session.scalar(select(ViaCategory).where(func.lower(ViaCategory.name) == clean.lower()))
    if existing:
        if color and color != existing.color:
            existing.color = color
            session.flush()
        return existing
    category = ViaCategory(name=clean, color=color)
    session.add(category)
    session.flush()
    return category


def list_categories(session) -> list[dict[str, Any]]:
    """Danh sách category kèm số VIA trong từng mục."""
    rows = session.scalars(select(ViaCategory).order_by(ViaCategory.id)).all()
    counts: dict[int, int] = {
        row[0]: row[1]
        for row in session.execute(
            select(ViaProfile.category_id, func.count(ViaProfile.id))
            .where(ViaProfile.category_id.isnot(None))
            .group_by(ViaProfile.category_id)
        ).all()
    }
    return [{"id": c.id, "name": c.name, "color": c.color, "via_count": counts.get(c.id, 0)} for c in rows]


# =============================================================================
# 2. PARSER ĐA ĐỊNH DẠNG
# =============================================================================


def parse_maxcare_json_input(raw_text: str) -> list[dict[str, Any]]:
    """Parse JSON dạng list hoặc {"vias": [...]}: bóc key maxcare của từng VIA."""
    raw_payload = json.loads(raw_text)
    items: list[Any] = []
    if isinstance(raw_payload, dict):
        items = raw_payload.get("vias") or raw_payload.get("results") or []
    elif isinstance(raw_payload, list):
        items = raw_payload
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not (item.get("uid") or item.get("id")):
            continue
        token = item.get("access_token") or item.get("token") or item.get("2fa_token") or ""
        two_fa = item.get("two_fa_secret") or item.get("totp_secret") or item.get("2fa") or item.get("2fa_secret") or ""
        two_fa = str(two_fa).strip()
        if isinstance(token, str) and token.startswith(("EAAB", "EAAG")):
            parsed_token = token.strip()
        elif isinstance(token, str) and token:
            parsed_token = ""
            if not two_fa:
                two_fa = token.strip()
        else:
            parsed_token = str(token or "").strip()
        entry = {
            "uid": str(item.get("uid") or item.get("id") or "").strip(),
            "password": str(item.get("password") or item.get("passwords") or item.get("account_password") or "").strip(),
            "two_fa_secret": two_fa,
            "email": str(item.get("email") or "").strip(),
            "email_password": str(item.get("email_password") or item.get("mail_password") or "").strip(),
            "backup_email": str(item.get("backup_email") or item.get("mail_backup") or "").strip(),
            "cookie": str(item.get("cookie") or item.get("cookies") or item.get("cookie_raw") or "").strip(),
            "access_token": parsed_token,
            "gender": str(item.get("gender") or "").strip(),
            "birthday": str(item.get("birthday") or item.get("days") or "").strip(),
            "device_name": str(item.get("device_name") or item.get("device") or "").strip(),
            "note": str(item.get("note") or item.get("notes") or item.get("comment") or "").strip(),
            "category": str(item.get("category") or item.get("group") or item.get("category_name") or "").strip(),
            "proxy": str(item.get("proxy") or item.get("proxy_raw") or "").strip(),
        }
        if not entry["uid"]:
            continue
        results.append(entry)
    return results


def parse_maxcare_string_line(line: str) -> Optional[dict[str, Any]]:
    """Parse 1 dòng pipe linh hoạt MaxCare, bóc thêm category/device/gender/birthday/note/proxy."""
    base = parse_via_string_line(line)
    if not base:
        return None
    entry = {
        "uid": base["uid"],
        "password": base["password"],
        "two_fa_secret": base["two_fa_secret"],
        "email": base["email"],
        "email_password": base["email_password"],
        "backup_email": base["backup_email"],
        "cookie": base["cookie"],
        "access_token": base["access_token"],
        "gender": "",
        "birthday": "",
        "device_name": "",
        "note": "",
        "category": "",
        "proxy": "",
    }
    # Bóc key=value tự định nghĩa bất kỳ đâu trong dòng
    for key_match in CUSTOM_KEY_PATTERN.finditer(line):
        key = key_match.group(1).lower()
        value = key_match.group(2).strip()
        if key == "category":
            entry["category"] = value
        elif key == "device":
            entry["device_name"] = value
        elif key == "note":
            entry["note"] = value
        elif key == "gender":
            lowered = value.lower()
            entry["gender"] = GENDER_TOKENS.get(lowered, value)
        elif key == "birthday":
            entry["birthday"] = value
        elif key == "proxy":
            entry["proxy"] = value
    return entry


def parse_maxcare_bulk_input(raw_text: str) -> list[dict[str, Any]]:
    """Parser tổng: JSON trước, pipe-lines sau; lọc dòng trống/comment (#, //)."""
    text = (raw_text or "").strip()
    if not text:
        return []
    if text.startswith("[") or text.startswith("{"):
        return parse_maxcare_json_input(text)
    results: list[dict[str, Any]] = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or clean.startswith("//"):
            continue
        entry = parse_maxcare_string_line(clean)
        if entry and entry.get("uid"):
            results.append(entry)
    return results


# =============================================================================
# 3. NHẬP HÀNG LOẠT + TỰ GÁN DANH MỤC
# =============================================================================


def bulk_import_maxcare_vias(
    session,
    raw_text: str,
    default_category: Optional[str] = None,
    default_proxy: Optional[str] = None,
) -> dict[str, Any]:
    """Nhập 1..100+ VIA kiểu MaxCare: parser linh hoạt, tự tạo category, gán device/birthday."""
    entries = parse_maxcare_bulk_input(raw_text)
    imported = updated = 0
    errors: list[str] = []
    category_map: dict[str, ViaCategory] = {}

    for idx, entry in enumerate(entries, 1):
        try:
            existing = session.scalar(select(ViaProfile).where(ViaProfile.uid == entry["uid"]))
            create_or_update_via(
                session=session,
                uid=entry["uid"],
                password=entry["password"],
                two_fa_secret=entry["two_fa_secret"],
                email=entry["email"],
                email_password=entry["email_password"],
                backup_email=entry["backup_email"],
                cookie=entry["cookie"],
                access_token=entry["access_token"],
                proxy_config=entry.get("proxy", "") or default_proxy,
            )
            fresh = session.scalar(select(ViaProfile).where(ViaProfile.uid == entry["uid"]))
            assert fresh is not None
            category_name = entry.get("category") or default_category
            if category_name:
                cat_key = category_name.lower()
                if cat_key not in category_map:
                    category_map[cat_key] = get_or_create_category(session, category_name)
                fresh.category_id = category_map[cat_key].id
            if entry.get("gender"):
                fresh.gender = entry["gender"]
            if entry.get("birthday"):
                fresh.birthday = entry["birthday"]
            if entry.get("device_name"):
                fresh.device_name = entry["device_name"]
            if entry.get("note"):
                fresh.note = entry["note"]
            fresh.profile_dir = get_isolated_profile_dir(entry["uid"])
            session.flush()
            if existing:
                updated += 1
            else:
                imported += 1
        except Exception as exc:
            errors.append(f"Lỗi nhập dòng #{idx} (UID {entry.get('uid')}): {exc}")

    session.add(
        MaxcareActivityLog(
            action="IMPORT",
            detail=f"Import {imported} VIA mới, cập nhật {updated}, lỗi {len(errors)}.",
            status="DONE" if not errors else "PARTIAL",
        )
    )
    session.commit()

    return {
        "success": True,
        "total_parsed": len(entries),
        "imported": imported,
        "updated": updated,
        "errors": errors,
        "categories": [c.name for c in category_map.values()],
    }


# =============================================================================
# 4. CẬP NHẬT THÔNG TIN HÀNG LOẠT (⚙️ nút 6)
# ==============================================================================


def bulk_update_vias(
    session,
    via_ids: Optional[list[int]] = None,
    category_name: Optional[str] = None,
    category_id: Optional[int] = None,
    device_name: Optional[str] = None,
    gender: Optional[str] = None,
    birthday: Optional[str] = None,
    note: Optional[str] = None,
    as_note_append: bool = False,
) -> dict[str, Any]:
    """⚙️ Cập nhật info hàng loạt cho dàn VIA (category, device, gender, birthday, note)."""
    query = select(ViaProfile).order_by(ViaProfile.id)
    if via_ids:
        query = query.where(ViaProfile.id.in_(via_ids))
    vias = session.scalars(query).all()
    if not vias:
        return {"total": 0, "updated": 0, "message": "Chưa chọn VIA nào."}

    category = None
    if category_id:
        category = session.get(ViaCategory, category_id)
        if not category:
            raise ValueError(f"Không tìm thấy danh mục #{category_id}")
    elif category_name:
        category = get_or_create_category(session, category_name)

    clean_device = (device_name or "").strip()
    clean_gender = (gender or "").strip()
    clean_birthday = (birthday or "").strip()
    clean_note = (note or "").strip()

    updated = 0
    for via in vias:
        if category is not None:
            via.category_id = category.id
        if clean_device:
            via.device_name = clean_device
        if clean_gender:
            via.gender = clean_gender
        if clean_birthday:
            via.birthday = clean_birthday
        if clean_note:
            if as_note_append:
                via.note = ((via.note or "") + " " + clean_note).strip()
            else:
                via.note = clean_note
        updated += 1
        session.add(
            MaxcareActivityLog(
                via_profile_id=via.id,
                action="UPDATE_INFO",
                detail=f"category={category.name if category else '-'} device={clean_device or '-'} gender={clean_gender or '-'}",
                status="DONE",
            )
        )
    session.commit()
    return {
        "total": len(vias),
        "updated": updated,
        "category": category.name if category is not None else None,
        "message": f"Đã cập nhật {updated} VIA.",
    }


# =============================================================================
# 5. BULK LOGIN ĐA LUỒNG (🚀 nút 2) — HARVEST TOKEN & COOKIE
# ==============================================================================


def save_maxcare_log(
    session,
    via_id: Optional[int],
    action: str,
    status: str,
    detail: str = "",
) -> MaxcareActivityLog:
    """Ghi 1 dòng nhật ký hoạt động MaxCare vào bảng append-only."""
    entry = MaxcareActivityLog(via_profile_id=via_id, action=action, status=status, detail=detail)
    session.add(entry)
    session.flush()
    return entry


def resolve_executor() -> Callable[..., dict[str, Any]]:
    """Executor mặc định: Silent Headless Login (headless_login_and_extract)."""
    from app.services.via_manager import headless_login_and_extract

    return headless_login_and_extract


def run_maxcare_bulk_login(
    session,
    session_factory: Optional[Callable[[], Any]] = None,
    via_ids: Optional[list[int]] = None,
    concurrency: Optional[int] = None,
    executor: Optional[Callable[..., dict[str, Any]]] = None,
    mock_mode: Optional[bool] = None,
    delay_between: float = 0.0,
) -> dict[str, Any]:
    """🚀 1-Click Bulk Login nhiều VIA đồng thời (asyncio Semaphore 5-10 luồng).

    - executor: hàm (session, via_id, mock_mode=...) -> dict; mặc định headless_login_and_extract.
    - session_factory: nếu cung cấp, mỗi luồng mở Session riêng; không có thì dùng chung `session`
      (an toàn với SQLite vì toàn bộ thao tác ghi DB được _DB_WRITE_LOCK serialize).
    - Trả thông báo tiếng Việt chi tiết từng VIA.
    """
    query = select(ViaProfile).order_by(ViaProfile.id)
    if via_ids:
        query = query.where(ViaProfile.id.in_(via_ids))
    vias = session.scalars(query).all()
    ids = [v.id for v in vias]
    if not ids:
        return {"total": 0, "done": [], "failed": [], "message": "Chưa chọn VIA nào."}

    limit = _resolve_concurrency(concurrency)
    worker_fn = executor or resolve_executor()

    def _login_one_sync(via_id: int) -> dict[str, Any]:
        local_session = session_factory() if session_factory is not None else session
        try:
            with _DB_WRITE_LOCK:
                result = worker_fn(local_session, via_id, mock_mode=mock_mode)
                status = "DONE" if result.get("success") else "FAILED"
                message = str(result.get("message") or "")
                save_maxcare_log(local_session, via_id, "BULK_LOGIN", status, message)
                if local_session is session:
                    session.commit()
                else:
                    local_session.commit()
                return {
                    "via_id": via_id,
                    "uid": result.get("uid"),
                    "ok": bool(result.get("success")),
                    "token_status": result.get("token_status"),
                    "message": message,
                }
        except Exception as exc:
            try:
                local_session.rollback()
                save_maxcare_log(local_session, via_id, "BULK_LOGIN", "FAILED", str(exc))
                local_session.commit()
            except Exception:
                pass
            return {"via_id": via_id, "ok": False, "message": str(exc)}

    async def _main() -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(limit)

        async def _go(via_id: int) -> dict[str, Any]:
            await asyncio.sleep(delay_between)
            async with semaphore:
                return await asyncio.to_thread(_login_one_sync, via_id)

        return list(await asyncio.gather(*[_go(vid) for vid in ids]))

    results = list(asyncio.run(_main()))
    done = [r for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok")]
    return {
        "total": len(ids),
        "done": done,
        "failed": failed,
        "concurrency": limit,
        "timestamp": utcnow().isoformat(),
        "message": f"Đã chạy Bulk Login đa luồng cho {len(ids)} VIA ({limit} luồng đồng thời).",
    }


# =============================================================================
# 6. XUẤT TOKEN / COOKIE CHO TOOL NGOÀI (📋 nút 4)
# ==============================================================================


def export_via_tokens_csv(
    session,
    via_ids: Optional[list[int]] = None,
    style: str = "csv",
) -> dict[str, Any]:
    """📋 Xuất token + cookie hàng loạt cho tool ngoài (chỉ chạy qua route quản trị local)."""
    from app.services.via_manager import decrypt_via_credentials

    query = select(ViaProfile).order_by(ViaProfile.id)
    if via_ids:
        query = query.where(ViaProfile.id.in_(via_ids))
    vias = session.scalars(query).all()

    if (style or "csv").strip().lower() == "pipe":
        lines = ["uid|password|two_fa|cookie|token"]
        for via in vias:
            creds = decrypt_via_credentials(via.encrypted_credentials)
            lines.append(
                "|".join(
                    [
                        via.uid,
                        str(creds.get("password", "")),
                        str(creds.get("two_fa_secret", "")),
                        str(creds.get("cookie", "")),
                        str(creds.get("access_token", "")),
                    ]
                )
            )
        return {
            "format": "pipe",
            "filename": "maxcare_tokens_pipe.txt",
            "content": "\n".join(lines),
            "total": len(vias),
        }

    lines = ["uid,profile_name,category,uid_live_status,token_status,password,two_fa,cookie,access_token"]
    for via in vias:
        category = session.get(ViaCategory, via.category_id) if via.category_id else None
        creds = decrypt_via_credentials(via.encrypted_credentials)
        row = [
            via.uid,
            via.profile_name,
            category.name if category else "",
            via.uid_live_status or "",
            via.token_status or "",
            str(creds.get("password", "")),
            str(creds.get("two_fa_secret", "")),
            str(creds.get("cookie", "")),
            str(creds.get("access_token", "")),
        ]
        safe_row = []
        for cell in row:
            text = str(cell)
            if "," in text or '"' in text:
                text = '"' + text.replace('"', '""') + '"'
            safe_row.append(text)
        lines.append(",".join(safe_row))
    return {
        "format": "csv",
        "filename": "maxcare_tokens.csv",
        "content": "\n".join(lines),
        "total": len(vias),
    }
