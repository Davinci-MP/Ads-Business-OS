"""appsecret_proof cho lời gọi Graph API từ server.

Khi app Meta bật "Require App Secret", mọi lời gọi Graph bằng access token phải kèm
``appsecret_proof = HMAC-SHA256(access_token, app_secret)`` dạng hex. Thiếu → Meta trả
code 100 "API calls from the server require an appsecret_proof argument".

Chỉ ký token do chính app này cấp (OAuth). Token ``EAAB...``/``EAAG...`` thuộc app nội bộ
của Facebook (Ads Manager/Business Manager); ký bằng secret của app này sẽ bị Meta từ chối
("Invalid appsecret_proof"), nên bỏ qua. Không bao giờ log token hay proof.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Optional

import httpx

from app.core.config import settings

GRAPH_HOST = "graph.facebook.com"
_FIRST_PARTY_TOKEN_PREFIXES = ("EAAB", "EAAG")


def compute_appsecret_proof(token: Optional[str], app_secret: Optional[str] = None) -> Optional[str]:
    """Trả về proof hex, hoặc None khi không nên/không thể ký."""
    token = (token or "").strip()
    secret = (settings.facebook_app_secret if app_secret is None else app_secret or "").strip()
    if not token or not secret or token.startswith(_FIRST_PARTY_TOKEN_PREFIXES):
        return None
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def with_appsecret_proof(fields: Optional[dict[str, Any]], token: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Bản sao ``fields`` có thêm ``appsecret_proof`` (token lấy từ ``fields['access_token']``
    nếu không truyền). Không ghi đè proof đã có."""
    if fields is None and token is None:
        return fields
    result = dict(fields or {})
    if "appsecret_proof" in result:
        return result
    proof = compute_appsecret_proof(token if token is not None else str(result.get("access_token") or ""))
    if proof:
        result["appsecret_proof"] = proof
    return result


def _token_from_request(request: httpx.Request) -> Optional[str]:
    token = request.url.params.get("access_token")
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def add_proof_to_graph_request(request: httpx.Request) -> None:
    """Hook ``request`` của httpx: ký mọi request tới graph.facebook.com có token trên URL
    hoặc header (kể cả link phân trang ``next`` Meta trả về)."""
    if request.url.host != GRAPH_HOST or "appsecret_proof" in request.url.params:
        return
    proof = compute_appsecret_proof(_token_from_request(request))
    if proof:
        request.url = request.url.copy_add_param("appsecret_proof", proof)


def ensure_graph_proof_hook(client: httpx.Client) -> httpx.Client:
    """Gắn ``add_proof_to_graph_request`` vào client (một lần). Hook ở lại trên client nên
    cả các ``client.get(next_url)`` phân trang sau đó cũng được ký."""
    hooks = client.event_hooks.get("request", [])
    if add_proof_to_graph_request not in hooks:
        client.event_hooks = {**client.event_hooks, "request": [*hooks, add_proof_to_graph_request]}
    return client
