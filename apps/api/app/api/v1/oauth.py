"""OAuth 2.0 chính thức của Meta cho hồ sơ VIA."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.local_admin import require_local_admin_or_owner
from app.core.meta_proof import with_appsecret_proof
from app.db import get_db
from app.models.customer import utcnow
from app.models.via import ViaProfile

router = APIRouter(prefix="/oauth", tags=["meta-oauth"])
logger = logging.getLogger(__name__)

_OAUTH_SCOPES = ("ads_read", "business_management", "pages_show_list")
_STATE_MAX_AGE_SECONDS = 600


async def get_oauth_http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        yield client


def _require_oauth_config() -> None:
    if not all(
        value.strip()
        for value in (
            settings.facebook_app_id,
            settings.facebook_app_secret,
            settings.facebook_redirect_uri,
        )
    ):
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình đầy đủ OAuth Meta ở máy chủ.",
        )


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _allowed_frontend_origins() -> set[str]:
    candidates = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        *(origin.strip().rstrip("/") for origin in settings.exchange_ui_origins.split(",")),
    }
    return {
        origin
        for origin in candidates
        if origin and urlsplit(origin).scheme in {"http", "https"} and urlsplit(origin).netloc
    }


def _frontend_origin(request: Request) -> str:
    allowed = _allowed_frontend_origins()
    requested = (request.headers.get("origin") or "").strip().rstrip("/")
    if requested in allowed:
        return requested
    if "http://localhost:3000" in allowed:
        return "http://localhost:3000"
    return sorted(allowed)[0]


def _create_state(via_id: int, frontend_origin: str) -> str:
    payload = {
        "via_id": via_id,
        "iat": int(time.time()),
        "nonce": secrets.token_urlsafe(16),
        "frontend_origin": frontend_origin,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.facebook_app_secret.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded}.{_b64encode(signature)}"


def _read_state(state: str) -> dict[str, Any]:
    try:
        encoded, supplied_signature = state.split(".", 1)
        expected_signature = hmac.new(
            settings.facebook_app_secret.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64decode(supplied_signature), expected_signature):
            raise ValueError("Chữ ký không hợp lệ")
        payload = json.loads(_b64decode(encoded))
        issued_at = int(payload["iat"])
        via_id = int(payload["via_id"])
        frontend_origin = str(payload["frontend_origin"]).rstrip("/")
        age = int(time.time()) - issued_at
        if age < -60 or age > _STATE_MAX_AGE_SECONDS:
            raise ValueError("State đã hết hạn")
        if via_id <= 0 or frontend_origin not in _allowed_frontend_origins():
            raise ValueError("Nội dung state không hợp lệ")
        return {"via_id": via_id, "frontend_origin": frontend_origin}
    except (binascii.Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Yêu cầu OAuth không hợp lệ hoặc đã hết hạn.",
        ) from exc


def _callback_redirect(frontend_origin: str, *, success: bool, reason: str = "") -> RedirectResponse:
    query: dict[str, str] = {"success": "true" if success else "false"}
    if reason:
        query["oauth_error"] = reason
    return RedirectResponse(f"{frontend_origin}/vias?{urlencode(query)}", status_code=303)


async def _get_meta_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = await client.get(url, params=params, headers=headers)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Meta trả về phản hồi không hợp lệ") from exc
    if response.is_error or not isinstance(payload, dict) or payload.get("error"):
        # Chỉ log nội dung lỗi Meta trả về (không log params vì chứa client_secret).
        meta_error = payload.get("error") if isinstance(payload, dict) else payload
        logger.error("Meta OAuth bị từ chối: status=%s error=%s", response.status_code, meta_error)
        raise RuntimeError("Meta từ chối yêu cầu OAuth")
    return payload


@router.get("/facebook/login", dependencies=[Depends(require_local_admin_or_owner)])
def facebook_login(
    request: Request,
    via_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Tạo URL cấp quyền chính thức, không lấy token từ cookie hoặc DOM."""
    _require_oauth_config()
    if db.get(ViaProfile, via_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy VIA cần cấp quyền.")

    state = _create_state(via_id, _frontend_origin(request))
    query = urlencode(
        {
            "client_id": settings.facebook_app_id,
            "redirect_uri": settings.facebook_redirect_uri,
            "scope": ",".join(_OAUTH_SCOPES),
            "response_type": "code",
            "state": state,
        }
    )
    return {
        "authorization_url": (
            f"https://www.facebook.com/{settings.meta_api_version}/dialog/oauth?{query}"
        )
    }


@router.get("/facebook/callback")
async def facebook_callback(
    state: str = Query(..., min_length=1),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_oauth_http_client),
) -> RedirectResponse:
    """Đổi authorization code lấy long-lived token và lưu ở dạng mã hóa."""
    _require_oauth_config()
    context = _read_state(state)
    frontend_origin = context["frontend_origin"]

    if error:
        reason = "access_denied" if error == "access_denied" else "meta_error"
        return _callback_redirect(frontend_origin, success=False, reason=reason)
    if not code:
        return _callback_redirect(frontend_origin, success=False, reason="missing_code")

    via = db.get(ViaProfile, context["via_id"])
    if via is None:
        return _callback_redirect(frontend_origin, success=False, reason="via_not_found")

    token_url = f"https://graph.facebook.com/{settings.meta_api_version}/oauth/access_token"
    try:
        short_lived = await _get_meta_json(
            client,
            token_url,
            params={
                "client_id": settings.facebook_app_id,
                "client_secret": settings.facebook_app_secret,
                "redirect_uri": settings.facebook_redirect_uri,
                "code": code,
            },
        )
        short_token = str(short_lived.get("access_token") or "").strip()
        if not short_token:
            raise RuntimeError("Meta không trả về access token ngắn hạn")

        long_lived = await _get_meta_json(
            client,
            token_url,
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.facebook_app_id,
                "client_secret": settings.facebook_app_secret,
                "fb_exchange_token": short_token,
            },
        )
        long_token = str(long_lived.get("access_token") or "").strip()
        if not long_token:
            raise RuntimeError("Meta không trả về access token dài hạn")

        identity = await _get_meta_json(
            client,
            f"https://graph.facebook.com/{settings.meta_api_version}/me",
            params=with_appsecret_proof({"fields": "id,name"}, long_token),
            headers={"Authorization": f"Bearer {long_token}"},
        )
        # /me (Graph v2.0+) trả app-scoped user ID, KHÔNG phải UID thật của VIA, nên không so
        # với via.uid được. Lần đầu: liên kết ID này vào VIA; các lần sau phải trùng ID đã liên kết.
        meta_user_id = str(identity.get("id") or "").strip()
        if not meta_user_id:
            raise RuntimeError("Meta không trả về id người dùng")
        if via.meta_app_user_id and via.meta_app_user_id != meta_user_id:
            return _callback_redirect(frontend_origin, success=False, reason="uid_mismatch")
        linked_elsewhere = db.scalar(
            select(ViaProfile.id).where(
                ViaProfile.meta_app_user_id == meta_user_id, ViaProfile.id != via.id
            )
        )
        if linked_elsewhere is not None:
            return _callback_redirect(frontend_origin, success=False, reason="account_linked_elsewhere")

        via.meta_app_user_id = meta_user_id
        meta_user_name = str(identity.get("name") or "").strip()
        if meta_user_name:
            via.meta_user_name = meta_user_name[:255]

        refreshed_at = utcnow()
        via.access_token = long_token
        via.token_status = "ACTIVE"
        via.last_token_refresh = refreshed_at
        try:
            expires_in = int(long_lived.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        via.token_expires_at = refreshed_at + timedelta(seconds=expires_in) if expires_in > 0 else None
        db.commit()
    except (httpx.HTTPError, RuntimeError):
        db.rollback()
        return _callback_redirect(frontend_origin, success=False, reason="token_exchange_failed")
    except Exception:
        db.rollback()
        return _callback_redirect(frontend_origin, success=False, reason="secure_storage_failed")

    return _callback_redirect(frontend_origin, success=True)
