"""Ví USDT TRC20 — chỉ đọc on-chain, không ký giao dịch, không ghi sổ.

- Lưu tối đa MỘT địa chỉ được theo dõi; địa chỉ đã lưu là bất biến: yêu cầu lưu
  địa chỉ khác khi đã có → xung đột (không ghi đè, không tự xoá lịch sử).
- Địa chỉ hợp lệ: T + base58 (34 ký tự, bỏ qua 0/O/I/l); mạng cố định TRON Mainnet.
- Kiểm tra kết nối = đọc thử qua TrongGrid (GET duy nhất); thành công mới ghi cấu hình.
- Số dư là giá trị tại thời điểm đọc; lịch sử append-only; lỗi KHÔNG ghi 0.
- Không trả/log API key; nếu có `ADSOS_TRON_API_KEY` chỉ dùng header server-side.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.tron import TronAPIError, TronConnector
from app.core.config import settings
from app.models.finance import (
    USDT_BALANCE_AUTO,
    USDT_BALANCE_MANUAL,
    USDT_NETWORK_TRON_MAINNET,
    UsdtWallet,
    UsdtWalletBalance,
    utcnow,
)

TRON_ADDRESS_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")


class WalletError(Exception):
    """Lỗi nghiệp vụ ví (không phải lỗi API)."""


class WalletConflict(WalletError):
    """Địa chỉ khác đã được theo dõi — không tự ghi đè."""


def validate_address(address: str) -> str:
    candidate = (address or "").strip()
    if not TRON_ADDRESS_RE.match(candidate):
        raise WalletError("Địa chỉ TRON không đúng định dạng (phải là T + 33 ký tự base58, không chứa 0/O/I/l).")
    return candidate


def get_wallet(session: Session) -> UsdtWallet | None:
    return session.scalars(select(UsdtWallet).order_by(UsdtWallet.id)).first()


def _connector(address: str, transport=None) -> TronConnector:
    connector = TronConnector(address)
    if settings.tron_api_key:
        connector = TronConnector(address, api_key=settings.tron_api_key)
    if transport is not None:
        connector._transport = transport
    return connector


def verify_address(address: str, transport=None) -> dict:
    """Kiểm tra kết nối: đọc thử on-chain qua TrongGrid (không lưu gì)."""
    candidate = validate_address(address)
    connector = _connector(candidate, transport=transport)
    try:
        payload = connector.wallet_balance()
    except TronAPIError as exc:
        return {"ok": False, "error": str(exc), "address": candidate, "network": "TRON Mainnet"}
    return {
        "ok": True,
        "address": candidate,
        "network": "TRON Mainnet",
        "balance": payload.get("balance"),
        "contract": payload.get("contract"),
        "note": payload.get("note"),
        "read_at": payload.get("read_at"),
        "mode": payload.get("mode"),
    }


def save_wallet(session: Session, wallet_name: str, address: str) -> UsdtWallet:
    full_name = (wallet_name or "").strip()
    if not full_name:
        raise WalletError("Tên ví không được để trống.")
    candidate = validate_address(address)
    existing = get_wallet(session)
    if existing is not None and existing.wallet_address != candidate:
        raise WalletConflict(existing.wallet_address)
    if existing is None:
        existing = UsdtWallet(
            wallet_name=full_name,
            wallet_address=candidate,
            network=USDT_NETWORK_TRON_MAINNET,
            contract=TronConnector(candidate).contract,
        )
        session.add(existing)
    else:
        existing.wallet_name = full_name
        existing.updated_at = utcnow()
    session.add(existing)
    session.commit()
    return existing


def set_auto_sync(session: Session, enabled: bool) -> UsdtWallet:
    wallet = get_wallet(session)
    if wallet is None:
        raise WalletError("Chưa lưu ví nào để bật/tắt tự đồng bộ.")
    wallet.auto_sync = bool(enabled)
    wallet.updated_at = utcnow()
    session.commit()
    return wallet


def _record_error(session: Session, wallet: UsdtWallet, message: str) -> None:
    wallet.last_checked_at = utcnow()
    wallet.last_error = message
    session.commit()


def read_balance(session: Session, source: str = USDT_BALANCE_MANUAL, transport=None,
                 now: datetime | None = None) -> tuple[UsdtWallet | None, dict | None]:
    """Đọc số dư hiện tại: thành công → lưu lịch sử + cập nhật trạng thái; lỗi → last_error (không ghi 0)."""
    wallet = get_wallet(session)
    if wallet is None:
        return None, None
    connector = _connector(wallet.wallet_address, transport=transport)
    try:
        payload = connector.wallet_balance()
    except TronAPIError as exc:
        _record_error(session, wallet, f"Không đọc được số dư ví TRON: {exc}")
        raise
    read_at = payload.get("read_at")
    balance_raw = payload.get("balance")
    balance = None
    if balance_raw is not None:
        from decimal import Decimal
        try:
            balance = Decimal(str(balance_raw))
        except Exception:
            balance = None
    session.add(UsdtWalletBalance(
        wallet_id=wallet.id,
        wallet_address=wallet.wallet_address,
        balance=balance,
        note=payload.get("note"),
        source=source,
        read_at=now or utcnow(),
    ))
    wallet.last_checked_at = utcnow()
    wallet.last_ok_at = utcnow()
    wallet.last_error = None
    session.commit()
    return wallet, payload
