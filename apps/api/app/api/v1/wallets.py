"""Router Cấu hình sàn & nguồn tiền (D-056, PingPong VCC) — chỉ listen on localhost.

Loopback-only: request từ host lạ → 404 (không tiết lộ endpoint tồn tại);
Origin sơ khai → 403. KHÔNG tin X-Forwarded-For.
"""
from __future__ import annotations

import re
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.services import exchange_connections as service
from app.services.exchange_connections import (
    ExchangeConflict,
    ExchangeCredentialsError,
    ExchangeError,
    ExchangeMasterKeyMissing,
    ExchangeNotFound,
    ExchangeVerificationFailed,
)

router = APIRouter()

_LOCAL_HOSTS = {"127.0.0.1", "::1", "testclient", "localhost"}
_DEV_ORIGIN_REGEX = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$")

_DISCLAIMERS = [
    "Số dư sàn & nguồn tiền PingPong TÁCH BIỆT với số dư ví blockchain TRC20 — không cộng trộn.",
    "Chỉ đọc Spot + Funding (Binance USDT) & Nguồn tiền/Thẻ ảo (PingPong) — ngoài phạm vi không can thiệp.",
    "Credentials lưu mã hóa phía server bằng Fernet; không hiển thị/log secret.",
    "Khóa API cần quyền chỉ đọc (Read-Only); khóa có quyền ghi/chuyển tiền/tạo thẻ sẽ bị từ chối lưu.",
    "Thẻ ảo VCC chỉ hiển thị và lưu 4 số cuối (last4); tuyệt đối không lưu full PAN hay mã CVV.",
]

_PROVIDER_LABELS = {
    "binance": "Binance (Spot + Funding, USDT)",
    "pingpong": "PingPong (Nguồn tiền đa tệ & Thẻ VCC)",
    "okx": "OKX — Chưa hỗ trợ",
    "mexc": "MEXC — Chưa hỗ trợ",
}


def _guard_local(request: Request) -> None:
    if getattr(request, "method", "GET") == "OPTIONS":
        return
    client = request.client
    host = client.host if client else None
    if host not in _LOCAL_HOSTS:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên")
    origin = request.headers.get("origin")
    if origin:
        origin_clean = origin.rstrip("/")
        allowed_origins = {o.strip().rstrip("/") for o in settings.exchange_ui_origins.split(",") if o.strip()}
        allowed_origins.update({"http://localhost:3000", "http://127.0.0.1:3000"})
        if origin_clean not in allowed_origins and not _DEV_ORIGIN_REGEX.match(origin_clean):
            raise HTTPException(status_code=403, detail="Origin không được phép")
    if len(settings.exchange_admin_token) < 32:
        raise HTTPException(status_code=503, detail="Chưa cấu hình mã quản trị kết nối ví ở máy chủ")
    supplied = request.headers.get("x-adsos-wallet-token", "")
    if not secrets.compare_digest(supplied, settings.exchange_admin_token):
        raise HTTPException(status_code=401, detail="Mã quản trị kết nối ví không hợp lệ")


def _translate(exc: Exception) -> HTTPException:
    text = str(getattr(exc, "message", None) or exc)
    if isinstance(exc, ExchangeMasterKeyMissing):
        return HTTPException(
            status_code=503,
            detail={"error": text, "action": "Đặt ADSOS_EXCHANGE_MASTER_KEY trên server rồi khởi động lại."},
        )
    if isinstance(exc, ExchangeConflict):
        return HTTPException(status_code=409, detail={"error": text})
    if isinstance(exc, ExchangeNotFound):
        return HTTPException(status_code=404, detail={"error": text})
    if isinstance(exc, (ExchangeCredentialsError, ExchangeVerificationFailed)):
        return HTTPException(status_code=400, detail={"error": text})
    if isinstance(exc, ExchangeError):
        return HTTPException(status_code=400, detail={"error": text})
    return HTTPException(status_code=500, detail={"error": "Lỗi hệ thống — chưa xác định"})


class VerifyPayload(BaseModel):
    provider: str = Field(default="binance")
    api_key: str = Field(..., min_length=8)
    api_secret: str = Field(..., min_length=8)
    account_id: str | None = None
    base_url: str | None = None


class SaveConnectionPayload(VerifyPayload):
    label: str = Field(..., min_length=1, max_length=64)


class UpdateConnectionPayload(BaseModel):
    label: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    account_id: str | None = None
    base_url: str | None = None
    auto_sync: bool | None = None


@router.get("/exchange/disclaimers")
def disclaimers(request: Request) -> dict:
    _guard_local(request)
    return {"disclaimers": _DISCLAIMERS, "providers": _PROVIDER_LABELS}


@router.get("/exchange/connections")
def list_connections(request: Request, session: Session = Depends(get_db)) -> dict:
    _guard_local(request)
    return {
        "connections": service.list_connections(session),
        "disclaimers": _DISCLAIMERS,
        "scheduler_enabled": settings.exchange_scheduler_enabled,
        "secure_storage_ready": bool(settings.exchange_master_key),
    }


@router.post("/exchange/verify")
def verify_connection(request: Request, payload: VerifyPayload) -> dict:
    _guard_local(request)
    try:
        service._fernet()
        return service.verify_connection(
            payload.api_key,
            payload.api_secret,
            provider=payload.provider,
            account_id=payload.account_id,
            base_url=payload.base_url,
        )
    except ExchangeError as exc:
        raise _translate(exc) from exc


@router.post("/exchange/connections")
def save_connection(
    request: Request,
    payload: SaveConnectionPayload,
    session: Session = Depends(get_db),
) -> dict:
    _guard_local(request)
    try:
        row = service.save_connection(
            session,
            label=payload.label,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            provider=payload.provider,
            account_id=payload.account_id,
            base_url=payload.base_url,
        )
    except ExchangeError as exc:
        raise _translate(exc) from exc
    return {
        "saved": True,
        "connection": service.get_connection_view(session, row.id),
    }


@router.put("/exchange/connections/{connection_id}")
def update_connection(
    request: Request,
    connection_id: int,
    payload: UpdateConnectionPayload,
    session: Session = Depends(get_db),
) -> dict:
    _guard_local(request)
    if payload.auto_sync is not None and any(
        v is not None for v in (payload.label, payload.api_key, payload.api_secret, payload.account_id, payload.base_url)
    ):
        raise HTTPException(status_code=400, detail="Cập nhật đồng bộ và khóa bằng hai thao tác riêng")
    try:
        if payload.auto_sync is not None:
            service.set_auto_sync(session, connection_id, payload.auto_sync)
        if any(v is not None for v in (payload.label, payload.api_key, payload.api_secret, payload.account_id, payload.base_url)):
            service.update_credentials(
                session,
                connection_id,
                payload.api_key,
                payload.api_secret,
                account_id=payload.account_id,
                base_url=payload.base_url,
                label=payload.label,
            )
        view = service.get_connection_view(session, connection_id)
    except ExchangeError as exc:
        raise _translate(exc) from exc
    return {"connection": view}


@router.delete("/exchange/connections/{connection_id}")
def disconnect_connection(
    request: Request,
    connection_id: int,
    session: Session = Depends(get_db),
) -> dict:
    _guard_local(request)
    try:
        row = service.disconnect_connection(session, connection_id)
    except ExchangeError as exc:
        raise _translate(exc) from exc
    return {"disconnected": True, "connection": service.get_connection_view(session, row.id)}


@router.post("/exchange/connections/{connection_id}/read-balances")
def read_balances(
    request: Request,
    connection_id: int,
    session: Session = Depends(get_db),
) -> dict:
    _guard_local(request)
    try:
        row, result = service.read_balances(session, connection_id)
        cards = service.list_cards(session, connection_id) if row.provider == "pingpong" else []
    except ExchangeError as exc:
        raise _translate(exc) from exc
    return {
        "connection": service.get_connection_view(session, row.id),
        "result": result,
        "cards": cards,
    }


@router.get("/exchange/connections/{connection_id}/snapshots")
def list_snapshots(
    request: Request,
    connection_id: int,
    limit: int = 50,
    session: Session = Depends(get_db),
) -> dict:
    _guard_local(request)
    try:
        items = service.list_snapshots(session, connection_id, limit=limit)
    except ExchangeError as exc:
        raise _translate(exc) from exc
    return {"snapshots": items}


@router.get("/exchange/connections/{connection_id}/cards")
def list_cards(
    request: Request,
    connection_id: int,
    limit: int = 50,
    session: Session = Depends(get_db),
) -> dict:
    _guard_local(request)
    try:
        items = service.list_cards(session, connection_id, limit=limit)
    except ExchangeError as exc:
        raise _translate(exc) from exc
    return {"cards": items}


@router.get("/exchange/connections/{connection_id}/history")
def list_history(
    request: Request,
    connection_id: int,
    limit: int = 20,
    session: Session = Depends(get_db),
) -> dict:
    _guard_local(request)
    try:
        items = service.list_history(session, connection_id, limit=limit)
    except ExchangeError as exc:
        raise _translate(exc) from exc
    return {"history": items}
