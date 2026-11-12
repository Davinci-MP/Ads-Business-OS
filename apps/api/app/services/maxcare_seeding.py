"""MaxCare Social & Seeding Controller — nuôi seed TikTok/Instagram/Facebook (cột tốc hành 4-5).

Nguyên tắc:
- Tất cả hành động chỉ chạy khi qua route quản trị local (require_local_admin).
- LIKE_COMMENT / JOIN_GROUPS thực thi thật (Graph API / CDP) chỉ khi executor được inject HOẶC env
  ADSOS_META_WRITES_ENABLED=true; mặc định trả status=PLANNED (chỉ lên lịch, không bắn API).
- SCROLL_NEWSFEED là hành vi trình duyệt (CDP) — mặc định PLANNED; executor (test) có thể mô phỏng.
- Mọi lần chạy đều append MaxcareActivityLog (action=SEEDING:<ACTION>).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

import httpx

from app.models.customer import utcnow
from app.models.via import MaxcareActivityLog, ViaProfile
from app.services.via_manager import decrypt_via_credentials

logger = logging.getLogger(__name__)

SEEDING_ACTIONS = {
    "SCROLL_NEWSFEED": "Cuộn đọc newsfeed để nuôi tài khoản (CDP trình duyệt).",
    "JOIN_GROUPS": "Tham gia nhóm Facebook theo ID nhóm (Graph API / browser).",
    "LIKE_COMMENT": "Like hoặc comment bài viết theo post_id (Graph API).",
}


def _writes_enabled() -> bool:
    return os.getenv("ADSOS_META_WRITES_ENABLED", "").strip().lower() in ("true", "1", "yes")


def normalize_action(action: str) -> str:
    clean = (action or "").strip().upper()
    if clean not in SEEDING_ACTIONS:
        raise ValueError(
            f"Hành động seeding không hợp lệ: {action!r}. Hỗ trợ: "
            + ", ".join(sorted(SEEDING_ACTIONS.keys()))
        )
    return clean


def build_seeding_plan(via: ViaProfile, action: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Mô tả kế hoạch seeding cho 1 VIA (VN), không phát sinh hành động thật."""
    action = normalize_action(action)
    params = dict(params or {})
    if action == "JOIN_GROUPS":
        group_ids = [str(g).strip() for g in (params.get("group_ids") or []) if str(g).strip()]
        return {
            "via_id": via.id,
            "uid": via.uid,
            "action": action,
            "description": f"VIA {via.uid} tham gia {len(group_ids)} nhóm: " + (", ".join(group_ids) or "—"),
            "group_ids": group_ids,
        }
    if action == "LIKE_COMMENT":
        post_id = str(params.get("post_id") or "").strip()
        comment = str(params.get("comment") or "").strip()
        like = bool(params.get("like", True))
        return {
            "via_id": via.id,
            "uid": via.uid,
            "action": action,
            "description": f"VIA {via.uid} {'like' if like else 'bình luận'} bài {post_id or '—'}"
            + (f" nội dung: {comment}" if comment and like is False else ""),
            "post_id": post_id,
            "comment": comment,
            "like": like,
        }
    minutes = int(params.get("minutes") or 10)
    return {
        "via_id": via.id,
        "uid": via.uid,
        "action": action,
        "description": f"VIA {via.uid} cuộn newsfeed ~{minutes} phút (nuôi slot tương tác).",
        "minutes": minutes,
    }


def _graph_post(
    token: str,
    path: str,
    fields: dict[str, Any],
    transport: Optional[httpx.BaseTransport] = None,
) -> dict[str, Any]:
    api_version = (os.getenv("ADSOS_META_API_VERSION", "v26.0")).strip()
    with httpx.Client(timeout=15.0, transport=transport) as client:
        resp = client.post(
            f"https://graph.facebook.com/{api_version}/{path}",
            params={"access_token": token, **fields},
        )
        resp.raise_for_status()
        return resp.json()


def run_via_seeding(
    session,
    via_id: int,
    action: str,
    params: Optional[dict[str, Any]] = None,
    executor: Optional[Callable[..., dict[str, Any]]] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> dict[str, Any]:
    """Thực thi / lập kế hoạch seeding cho 1 VIA. Executor inject KHÔNG phụ thuộc env write-guard."""
    via = session.get(ViaProfile, via_id)
    if not via:
        raise ValueError(f"Không tìm thấy VIA #{via_id}")
    action = normalize_action(action)
    params = dict(params or {})
    plan = build_seeding_plan(via, action, params)

    strategy: str

    if executor is not None:
        strategy = "EXECUTOR"
        try:
            result = executor(session, via, action, params) or {}
            status = str(result.get("status") or "DONE")
        except Exception as exc:
            result = {"error": str(exc)}
            status = "FAILED"
        detail = plan["description"] + (f" | kết quả: {result}" if result else "")
    elif action == "LIKE_COMMENT":
        creds = decrypt_via_credentials(via.encrypted_credentials)
        token = creds.get("access_token") or ""
        post_id = plan.get("post_id") or ""
        if not (token.startswith("EAAB") or token.startswith("EAAG")) or not post_id:
            status = "PLANNED"
            detail = plan["description"] + " | VIA cần Access Token / post_id để thực thi Graph API."
        elif _writes_enabled():
            strategy = "GRAPH_API"
            try:
                if plan.get("like", False):
                    _graph_post(token, f"{post_id}/likes", {}, transport=transport)
                comment = plan.get("comment") or ""
                if comment:
                    _graph_post(token, f"{post_id}/comments", {"message": comment}, transport=transport)
                status = "DONE"
                detail = plan["description"] + " | Đã lan tỏa qua Graph API (write guard bật)."
            except Exception as exc:
                status = "FAILED"
                detail = plan["description"] + f" | Graph API lỗi: {exc}"
        else:
            status = "PLANNED"
            detail = plan["description"] + " | Chỉ lên lịch (ADSOS_META_WRITES_ENABLED chưa bật)."
    else:
        status = "PLANNED"
        detail = plan["description"] + " | Chỉ lên lịch; cần executor trình duyệt (CDP) để chạy thật."

    session.add(
        MaxcareActivityLog(via_profile_id=via.id, action=f"SEEDING:{action}", detail=detail, status=status)
    )
    session.commit()
    return {
        "via_id": via.id,
        "uid": via.uid,
        "action": action,
        "status": status,
        "description": plan["description"],
        "detail": detail,
        "executed_at": utcnow().isoformat(),
    }


def run_via_seeding_bulk(
    session,
    via_ids: Optional[list[int]],
    action: str,
    params: Optional[dict[str, Any]] = None,
    executor: Optional[Callable[..., dict[str, Any]]] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> dict[str, Any]:
    """Chạy bulk seeding cho toàn bộ VIA được chọn."""
    from sqlalchemy import select

    query = select(ViaProfile).order_by(ViaProfile.id)
    if via_ids:
        query = query.where(ViaProfile.id.in_(via_ids))
    vias = session.scalars(query).all()

    results = []
    done = planned = failed = 0
    for via in vias:
        try:
            result = run_via_seeding(session, via.id, action, params, executor=executor, transport=transport)
        except Exception as exc:
            result = {"via_id": via.id, "uid": via.uid, "status": "FAILED", "detail": str(exc)}
        results.append(result)
        status = result.get("status")
        if status == "DONE":
            done += 1
        elif status == "PLANNED":
            planned += 1
        else:
            failed += 1

    return {
        "action": action,
        "total": len(vias),
        "done": done,
        "planned": planned,
        "failed": failed,
        "results": results,
        "timestamp": utcnow().isoformat(),
    }
