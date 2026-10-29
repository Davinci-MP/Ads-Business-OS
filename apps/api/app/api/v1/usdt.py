"""REST endpoints USDT — cấu hình ví TRC20 + chỉ đọc số dư on-chain.

KHÔNG ký giao dịch, KHÔNG chuyển tiền, KHÔNG lưu key ở frontend; lịch sử số dư
append-only; lỗi đọc KHÔNG biến số dư thành 0. Số dư là giá trị tại thời điểm
đọc, không thuộc tháng/năm báo cáo, không đối chiếu trực tiếp L1/hoàn còn lại.
Giao dịch nạp/match vẫn theo luồng nhập tay riêng (Q-006) — endpoint này không thay thế.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.tron import TronAPIError, TronConnector
from app.core.config import settings
from app.db import get_db
from app.models.finance import (
    USDT_BALANCE_MANUAL,
    AuditLog,
    UsdtWallet,
    UsdtWalletBalance,
)
from app.services.usdt_wallet import (
    WalletConflict,
    WalletError,
    get_wallet,
    read_balance,
    save_wallet,
    set_auto_sync,
    verify_address,
)

router = APIRouter(tags=["usdt"])

DISCLAIMERS = [
    "Số dư là giá trị tại thời điểm đọc; không thuộc tháng/năm đang chọn trong báo cáo.",
    "Không đối chiếu trực tiếp số dư đọc lúc này với L1 hay số dư đến kỳ của tháng cũ.",
    "Không cộng L1 nhiều tháng để tạo 'tổng ngân sách còn lại'.",
    "Đọc được ví chưa đủ làm cơ sở đối soát toàn doanh nghiệp; giao dịch vẫn theo luồng nhập tay riêng (Q-006).",
    "Số dư on-chain của địa chỉ này KHÔNG đại diện số dư tài khoản trên sàn nếu đó là địa chỉ nạp sàn.",
]


class WalletSaveBody(BaseModel):
    wallet_name: str
    address: str

    @field_validator("wallet_name", "address")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class WalletUpdateBody(BaseModel):
    wallet_name: Optional[str] = None
    auto_sync: Optional[bool] = None

    @field_validator("wallet_name")
    @classmethod
    def _strip_name(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else None


class VerifyBody(BaseModel):
    address: str


@router.get("/usdt/wallet")
def vault_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    wallet = get_wallet(db)
    latest_balance = None
    if wallet is not None:
        row = db.scalars(select(UsdtWalletBalance).where(
            UsdtWalletBalance.wallet_id == wallet.id).order_by(
            UsdtWalletBalance.id.desc()).limit(1)).first()
        if row is not None:
            latest_balance = {
                "balance": str(row.balance) if row.balance is not None else None,
                "read_at": row.read_at.isoformat() if row.read_at else None,
                "source": row.source,
                "note": row.note,
            }
    base: dict[str, Any] = {
        "mode_live": True,
        "wallet": None,
        "env_wallet_configured": bool((settings.tron_wallet_address or "").strip()),
        "network": "TRON Mainnet",
        "contract": TronConnector("").contract,
        "disclaimers": DISCLAIMERS,
    }
    if wallet is None:
        return base
    base["wallet"] = {
        "id": wallet.id,
        "wallet_name": wallet.wallet_name,
        "wallet_address": wallet.wallet_address,
        "network": "TRON Mainnet",
        "contract": wallet.contract,
        "auto_sync": wallet.auto_sync,
        "last_checked_at": wallet.last_checked_at.isoformat() if wallet.last_checked_at else None,
        "last_ok_at": wallet.last_ok_at.isoformat() if wallet.last_ok_at else None,
        "last_error": wallet.last_error,
        "latest_balance": latest_balance,
    }
    return base


@router.post("/usdt/wallet/verify")
def wallet_verify(body: VerifyBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = verify_address(body.address)
    current = get_wallet(db)
    result["saved_wallet_address"] = current.wallet_address if current else None
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@router.post("/usdt/wallet")
def wallet_save(body: WalletSaveBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    verified = verify_address(body.address)
    if not verified.get("ok"):
        raise HTTPException(status_code=502,
                            detail=f"Kiểm tra kết nối thất bại — CHƯA lưu cấu hình: {verified.get('error')}")
    try:
        wallet = save_wallet(db, body.wallet_name, body.address)
    except WalletConflict as exc:
        raise HTTPException(status_code=409, detail={
            "error": "Đã có ví khác được theo dõi; KHÔNG ghi đè.",
            "saved_wallet_address": str(exc),
        }) from exc
    except WalletError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(AuditLog(actor="admin", action="USDT_WALLET_SAVED", entity_type="usdt_wallet",
                    entity_id=str(wallet.id), detail={"wallet_address": wallet.wallet_address,
                                                      "network": "tron_mainnet"}))
    db.commit()
    return {"saved": True, "wallet_id": wallet.id, "wallet_address": wallet.wallet_address,
            "network": "TRON Mainnet", "verified": True, "disclaimers": DISCLAIMERS}


@router.put("/usdt/wallet")
def wallet_update(body: WalletUpdateBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        if body.auto_sync is not None:
            wallet = set_auto_sync(db, body.auto_sync)
        else:
            wallet = get_wallet(db)
            if wallet is None:
                raise WalletError("Chưa lưu ví nào.")
            if body.wallet_name is not None:
                if not body.wallet_name:
                    raise WalletError("Tên ví không được để trống.")
                wallet.wallet_name = body.wallet_name
                db.commit()
    except WalletError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(AuditLog(actor="admin", action="USDT_WALLET_UPDATED", entity_type="usdt_wallet",
                    entity_id=str(wallet.id), detail={
                        "auto_sync": wallet.auto_sync, "wallet_name": wallet.wallet_name}))
    db.commit()
    return {"wallet_id": wallet.id, "wallet_name": wallet.wallet_name,
            "auto_sync": wallet.auto_sync, "disclaimers": DISCLAIMERS}


@router.post("/usdt/wallet/read-balance")
def wallet_read_balance(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        wallet, payload = read_balance(db, source=USDT_BALANCE_MANUAL)
    except TronAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if wallet is None:
        raise HTTPException(status_code=400, detail="Chưa lưu ví nào để đọc số dư.")
    db.add(AuditLog(actor="admin", action="USDT_WALLET_BALANCE_READ", entity_type="usdt_wallet",
                    entity_id=str(wallet.id), detail={"source": "MANUAL",
                                                      "balance": payload.get("balance") if payload else None}))
    db.commit()
    return {
        "wallet_id": wallet.id,
        "wallet_address": wallet.wallet_address,
        "balance": payload.get("balance"),
        "read_at": payload.get("read_at"),
        "note": payload.get("note"),
        "disclaimers": DISCLAIMERS,
    }


@router.get("/usdt/wallet/balances")
def vault_balances(limit: int = 20, db: Session = Depends(get_db)) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    wallet = get_wallet(db)
    items: list[dict[str, Any]] = []
    total = 0
    if wallet is not None:
        rows = db.scalars(select(UsdtWalletBalance).where(
            UsdtWalletBalance.wallet_id == wallet.id).order_by(UsdtWalletBalance.id.desc())).all()
        total = len(rows)
        for row in rows[:limit]:
            items.append({
                "balance": str(row.balance) if row.balance is not None else None,
                "read_at": row.read_at.isoformat() if row.read_at else None,
                "source": row.source,
                "note": row.note,
            })
    return {"wallet_address": wallet.wallet_address if wallet else None,
            "total": total, "items": items, "disclaimers": DISCLAIMERS}


@router.get("/usdt/wallet-balance")
def usdt_wallet_balance(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Legacy chỉ-đọc: dùng ví đã lưu (ưu tiên) hoặc env; chưa cấu hình → mode=mock, không giả 0."""
    wallet = get_wallet(db)
    address = (wallet.wallet_address if wallet else (settings.tron_wallet_address or "").strip())
    if wallet is not None and wallet.last_error and wallet.last_ok_at is None:
        address = ""
    connector = TronConnector(address, api_key=settings.tron_api_key)
    try:
        payload = connector.wallet_balance()
    except TronAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Không đọc được số dư ví TRON: {exc}") from exc
    payload["disclaimers"] = DISCLAIMERS
    return payload
