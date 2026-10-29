"""Kết nối sàn giao dịch — lưu credentials mã hóa + đọc số dư chỉ đọc (D-056).

Ranh giới:
- Credentials chỉ lưu ciphertext (Fernet) — KHÔNG plaintext, KHÔNG log/response secret.
- Master key qua env (`ADSOS_EXCHANGE_MASTER_KEY`, ít nhất 32 bytes). Chưa cấu hình →
  `ExchangeMasterKeyMissing` — API phải trả 503 kèm hướng dẫn, KHÔNG lưu plaintext.
- Chỉ Binance hỗ trợ verify + lưu trong giai đoạn này; OKX/MEXC từ chối (không connector giả).
- Verify Binance: giữ THẮT_LỢI (bước cuối trước lưu):
  (1) gọi `apiRestrictions` — chỉ tuyên bố "chỉ đọc" khi canRead + !canTrade + !canWithdraw;
      khóa có quyền ghi → từ chối lưu (ExchangeVerificationFailed), KHÔNG tự hạPermissions.
  (2) đọc thử Spot + Funding USDT — 2 endpoint bất kỳ lỗi → verify fail (không lưu).
- Snapshot append-only, USDT-only; một ví lỗi → giữ phần còn lại + báo độ phủ
  (0 đó không tự dán 0 giả — không snapshot cho ví lỗi).
- Chống ghi trùng: unique (connection_id, wallet_type, asset, read_at); chạy lại cùng
  thời điểm → bỏ qua dòng trùng, không cộng dồn.
- Audit log sự kiện EXCHANGE_*; detail KHÔNG chứa api_key/secret (chỉ last4 + status).
"""
from __future__ import annotations

import time  # noqa: F401
from datetime import datetime, timezone, timedelta  # noqa: F401
from decimal import Decimal, InvalidOperation

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.binance import BinanceConnector, BinanceError, BinanceRateLimitError, validate_read_permissions
from app.core.config import settings
from app.models.exchange import (
    EXCH_HISTORY_ERROR,
    EXCH_HISTORY_OK,
    EXCH_HISTORY_PARTIAL,
    EXCH_HISTORY_STARTED,
    EXCH_PROVIDER_BINANCE,
    EXCH_SOURCE_MANUAL,
    EXCH_STATUS_ACTIVE,
    EXCH_STATUS_REMOVED,
    EXCH_WALLET_FUNDING,
    EXCH_WALLET_SPOT,
    ExchangeBalanceSnapshot,
    ExchangeConnection,
    ExchangeCredentials,
    ExchangeSyncHistory,
)
from app.models.finance import AuditLog, utcnow

AUSDT = "USDT"


class ExchangeError(Exception):
    """Lỗi nghiệp vụ exchange (không phải lỗi API)."""


class ExchangeMasterKeyMissing(ExchangeError):
    """Server chưa cấu hình bảo mật — không lưu credentials (chống plaintext fallback)."""


class ExchangeConflict(ExchangeError):
    """Trùng (provider, label) — không ghi đè cấu hình hiện có."""


class ExchangeVerificationFailed(ExchangeError):
    """Verify Binance không đạt — không lưu."""


class ExchangeNotFound(ExchangeError):
    """Connection không tồn tại hoặc đã bị gỡ."""


class ExchangeCredentialsError(ExchangeError):
    """Payload credentials không đủ/thiếu cấu phần bắt buộc."""


# --------------------------------------------------------------------- helpers
def _fernet() -> Fernet:
    """Fernet key từ env; chưa cấu hình/không hợp lệ → lỗi rõ, KHÔNG tự sinh/restart."""
    master_key = (settings.exchange_master_key or "").strip()
    if not master_key:
        raise ExchangeMasterKeyMissing(
            "Chưa cấu hình bảo mật phía máy chủ: đặt env ADSOS_EXCHANGE_MASTER_KEY "
            "(Fernet key ≥32 bytes, vd: python -c \"from cryptography.fernet import "
            "Fernet; print(Fernet.generate_key().decode())\")"
        )
    try:
        return Fernet(master_key.encode("utf-8"))
    except Exception as exc:
        raise ExchangeMasterKeyMissing(
            "ADSOS_EXCHANGE_MASTER_KEY không phải Fernet key hợp lệ — KHÔNG lưu plaintext. "
            f"Lỗi: {exc}"
        ) from exc


def _conn_or_raised(session: Session, connection_id: int) -> ExchangeConnection:
    row = session.get(ExchangeConnection, connection_id)
    if row is None or row.status != EXCH_STATUS_ACTIVE:
        raise ExchangeNotFound(f"Connection #{connection_id} không tồn tại hoặc đã gỡ")
    return row


def _connection_view(connection: ExchangeConnection, credentials: ExchangeCredentials | None = None) -> dict:
    view = {
        "id": connection.id,
        "provider": connection.provider,
        "label": connection.label,
        "status": connection.status,
        "wallet_types": list(connection.wallet_types or []),
        "read_only_verified": bool(connection.read_only_verified),
        "auto_sync": bool(connection.auto_sync),
        "last_checked_at": connection.last_checked_at.isoformat() if connection.last_checked_at else None,
        "last_ok_at": connection.last_ok_at.isoformat() if connection.last_ok_at else None,
        "last_error": connection.last_error,
        "created_at": connection.created_at.isoformat() if connection.created_at else None,
    }
    if credentials is not None:
        view["api_key_last4"] = credentials.api_key_last4
    return view


def _wallet_types() -> list[str]:
    return [EXCH_WALLET_SPOT, EXCH_WALLET_FUNDING]


def _audit(session: Session, action: str, entity_id: int, detail: dict, actor: str = "admin") -> None:
    session.add(AuditLog(
        actor=actor,
        action=action,
        entity_type="exchange_connection",
        entity_id=str(entity_id),
        detail=detail,
    ))


# ------------------------------------------------------------------ lifecycle
def list_connections(session: Session, include_removed: bool = False) -> list[dict]:
    """Danh sách kết nối — không trả api_key/encrypted payload, chỉ last4."""
    query = select(ExchangeConnection).order_by(ExchangeConnection.id)
    if not include_removed:
        query = query.where(ExchangeConnection.status == EXCH_STATUS_ACTIVE)
    rows = session.scalars(query).all()
    credential_rows = {
        row.connection_id: row
        for row in session.scalars(select(ExchangeCredentials)).all()
    }
    return [
        {**_connection_view(connection, credential_rows.get(connection.id)), "wallet_errors": _latest_wallet_errors(session, connection.id)}
        for connection in rows
    ]


def get_connection_view(session: Session, connection_id: int) -> dict:
    row = session.get(ExchangeConnection, connection_id)
    if row is None:
        raise ExchangeNotFound(f"Connection #{connection_id} không tồn tại")
    credential = session.scalars(
        select(ExchangeCredentials).where(ExchangeCredentials.connection_id == connection_id)
    ).first()
    return {**_connection_view(row, credential), "wallet_errors": _latest_wallet_errors(session, connection_id)}


def _latest_wallet_errors(session: Session, connection_id: int) -> dict:
    latest = session.scalars(select(ExchangeSyncHistory).where(
        ExchangeSyncHistory.connection_id == connection_id
    ).order_by(ExchangeSyncHistory.id.desc()).limit(1)).first()
    if not latest or latest.status not in (EXCH_HISTORY_ERROR, EXCH_HISTORY_PARTIAL):
        return {}
    wallets = (latest.detail or {}).get("wallets", {})
    return {name: wallets.get(name, {}).get("error", latest.error_message or "Chưa đọc được")
            for name in _wallet_types() if wallets.get(name, {}).get("ok") is not True}


def _validate_credentials_payload(api_key: str, api_secret: str) -> tuple[str, str]:
    """Không kết nối cho provider khác giai đoạn này (R2-T2); binance bắt buộc đủ 2 trường."""
    api_key = (api_key or "").strip()
    api_secret = (api_secret or "").strip()
    if not api_key or not api_secret:
        raise ExchangeCredentialsError("Binance apiKey/apiSecret không được để trống")
    if len(api_key) < 8 or len(api_secret) < 8:
        raise ExchangeCredentialsError("apiKey/apiSecret quá ngắn")
    return api_key, api_secret


def verify_connection(api_key: str, api_secret: str, *, transport=None) -> dict:
    """Chỉ kiểm tra quyền đọc (canRead + !canTrade + !canWithdraw) và đọc thử Spot/F.
    Không lưu credentials; không ghi snapshot/history.
    """
    api_key, api_secret = _validate_credentials_payload(api_key, api_secret)
    connector = BinanceConnector(api_key=api_key, api_secret=api_secret, transport=transport)
    try:
        restrictions = connector.api_restrictions()
        warnings: list[str] = []
        try:
            validate_read_permissions(restrictions)
        except BinanceError as exc:
            raise ExchangeVerificationFailed(str(exc)) from exc
        try:
            spot = connector.spot_balances()
        except BinanceError as exc:
            raise ExchangeVerificationFailed(f"Không đọc được Spot: {exc}") from exc
        try:
            funding = connector.funding_balances(asset=AUSDT)
        except BinanceError as exc:
            raise ExchangeVerificationFailed(f"Không đọc được Funding: {exc}") from exc
        spot_usdt = [_row for _row in spot if _row["asset"] == AUSDT]
        funding_usdt = [_row for _row in funding if _row["asset"] == AUSDT]
        return {
            "ok": True,
            "read_only_verified": True,
            "permissions": restrictions,
            "spot_preview": spot_usdt,
            "funding_preview": funding_usdt,
            "warnings": warnings,
        }
    finally:
        connector.close()


def save_connection(
    session: Session,
    label: str,
    api_key: str,
    api_secret: str,
    *,
    actor: str = "admin",
    transport=None,
) -> ExchangeConnection:
    """Verify → encrypt credentials → tạo connection; unique (provider, label)."""
    label_clean = (label or "").strip()
    if not label_clean:
        raise ExchangeCredentialsError("Tên kết nối không được để trống")
    api_key, api_secret = _validate_credentials_payload(api_key, api_secret)

    fernet = _fernet()  # Chưa cấu hình → không lưu plaintext (ExchangeMasterKeyMissing)
    duplicate = session.scalars(
        select(ExchangeConnection).where(
            ExchangeConnection.provider == EXCH_PROVIDER_BINANCE,
            ExchangeConnection.label == label_clean,
            ExchangeConnection.status == EXCH_STATUS_ACTIVE,
        )
    ).first()
    if duplicate is not None:
        raise ExchangeConflict(f"Đã có kết nối Binance tên '{label_clean}' — chọn tên khác")

    verify_connection(api_key, api_secret, transport=transport)
    encrypted_api_key = fernet.encrypt(api_key.encode("utf-8")).decode("utf-8")
    encrypted_api_secret = fernet.encrypt(api_secret.encode("utf-8")).decode("utf-8")

    connection = ExchangeConnection(
        provider=EXCH_PROVIDER_BINANCE,
        label=label_clean,
        status=EXCH_STATUS_ACTIVE,
        wallet_types=_wallet_types(),
        read_only_verified=True,
    )
    session.add(connection)
    session.flush()
    session.add(ExchangeCredentials(
        connection_id=connection.id,
        provider=EXCH_PROVIDER_BINANCE,
        encrypted_api_key=encrypted_api_key,
        encrypted_api_secret=encrypted_api_secret,
        api_key_last4=api_key[-4:],
    ))
    _audit(session, "EXCHANGE_CONNECTION_SAVED", connection.id, {
        "provider": EXCH_PROVIDER_BINANCE,
        "label": label_clean,
        "api_key_last4": api_key[-4:],
        "read_only_verified": True,
    }, actor=actor)
    session.commit()
    session.refresh(connection)
    return connection


def update_credentials(
    session: Session,
    connection_id: int,
    api_key: str | None = None,
    api_secret: str | None = None,
    *,
    actor: str = "admin",
    transport=None,
    label: str | None = None,
) -> ExchangeConnection:
    """Đổi credentials/label: secret trống = giữ cũ; đổi khóa phải đủ 2 trường + verify lại."""
    connection = _conn_or_raised(session, connection_id)
    credential = session.scalars(
        select(ExchangeCredentials).where(ExchangeCredentials.connection_id == connection_id)
    ).first()
    if credential is None:
        raise ExchangeNotFound(f"Connection #{connection_id} không có credentials")

    new_label = (label or "").strip() if label is not None else None
    if new_label:
        duplicate = session.scalars(
            select(ExchangeConnection).where(
                ExchangeConnection.provider == connection.provider,
                ExchangeConnection.label == new_label,
                ExchangeConnection.id != connection_id,
            )
        ).first()
        if duplicate is not None:
            raise ExchangeConflict(f"Trùng tên kết nối hiện có: '{new_label}'")

    provided_key = (api_key or "").strip()
    provided_secret = (api_secret or "").strip()
    if provided_key or provided_secret:
        if not (provided_key and provided_secret):
            raise ExchangeCredentialsError(
                "Đổi khóa phải cung cấp đủ apiKey và apiSecret cùng lúc — giữ nguyên chỉ khi cả hai trống"
            )
        fernet = _fernet()
        verify_connection(provided_key, provided_secret, transport=transport)
        credential.encrypted_api_key = fernet.encrypt(provided_key.encode("utf-8")).decode("utf-8")
        credential.encrypted_api_secret = fernet.encrypt(provided_secret.encode("utf-8")).decode("utf-8")
        credential.api_key_last4 = provided_key[-4:]
        credential.updated_at = utcnow()
    else:
        provided_key = credential.api_key_last4  # giữ nguyên — chỉ đổi label
    if new_label:
        connection.label = new_label
    connection.updated_at = utcnow()
    _audit(session, "EXCHANGE_CONNECTION_UPDATED", connection.id, {
        "label": connection.label,
        "api_key_changed": bool((api_key or "").strip()),
    }, actor=actor)
    session.commit()
    session.refresh(connection)
    return connection


def set_auto_sync(
    session: Session, connection_id: int, enabled: bool, *, actor: str = "admin"
) -> ExchangeConnection:
    connection = _conn_or_raised(session, connection_id)
    if enabled and not settings.exchange_scheduler_enabled:
        raise ExchangeError("Scheduler sàn chưa được bật ở máy chủ")
    connection.auto_sync = bool(enabled)
    connection.updated_at = utcnow()
    _audit(session, "EXCHANGE_AUTO_SYNC_TOGGLED", connection.id, {"enabled": bool(enabled)}, actor=actor)
    session.commit()
    session.refresh(connection)
    return connection


def disconnect_connection(
    session: Session, connection_id: int, *, actor: str = "admin"
) -> ExchangeConnection:
    """Ngắt kết nối = đổi status REMOVED — KHÔNG xoá snapshot/history."""
    connection = _conn_or_raised(session, connection_id)
    connection.status = EXCH_STATUS_REMOVED
    connection.auto_sync = False
    connection.updated_at = utcnow()
    _audit(session, "EXCHANGE_CONNECTION_DISCONNECTED", connection.id, {}, actor=actor)
    session.commit()
    session.refresh(connection)
    return connection


# -------------------------------------------------------------------- lectura
def _parse_amount(value: str) -> Decimal | None:
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError()
        return number
    except (InvalidOperation, ValueError) as exc:
        raise ExchangeError(f"Giá trị số không đọc được: {value!r}") from exc


def _read_wallet(
    wallet_type: str,
    connector: BinanceConnector,
) -> list[dict[str, str]]:
    """Đọc ví Spot/Funding — giữ nguyên chuỗi gốc decimal (chỉ lọc USDT)."""
    if wallet_type == EXCH_WALLET_SPOT:
        rows = [
            row for row in connector.spot_balances()
            if row["asset"] == AUSDT
        ]
    else:
        rows = [
            row for row in connector.funding_balances(asset=AUSDT)
        ]
    return rows


def _read_balances_unlocked(
    session: Session,
    connection_id: int,
    *,
    source: str = EXCH_SOURCE_MANUAL,
    transport=None,
    now: datetime | None = None,
    actor: str = "admin",
) -> tuple[ExchangeConnection, dict]:
    """Đọc Spot + Funding USDT: append snapshot per (wallet_type, asset, read_at); lỗi từng ví
    không đè ví còn lại; lịch sử + audit KHÔNG chứa secret.
    """
    connection = _conn_or_raised(session, connection_id)
    latest_attempt = session.scalars(select(ExchangeSyncHistory).where(
        ExchangeSyncHistory.connection_id == connection_id
    ).order_by(ExchangeSyncHistory.id.desc()).limit(1)).first()
    if latest_attempt and latest_attempt.detail:
        until = latest_attempt.detail.get("retry_not_before")
        if until and datetime.fromisoformat(until) > utcnow():
            raise ExchangeConflict("Binance đang giới hạn truy cập; vui lòng chờ tới " + until)
    credential = session.scalars(
        select(ExchangeCredentials).where(ExchangeCredentials.connection_id == connection_id)
    ).first()
    if credential is None:
        raise ExchangeNotFound(f"Connection #{connection_id} không có credentials")
    fernet = _fernet()
    try:
        api_key = fernet.decrypt(credential.encrypted_api_key.encode("utf-8")).decode("utf-8")
        api_secret = fernet.decrypt(credential.encrypted_api_secret.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ExchangeMasterKeyMissing(
            "Không giải mã được credentials — master key hiện tại không khớp lúc lưu"
        ) from exc

    connector = BinanceConnector(api_key=api_key, api_secret=api_secret, transport=transport)
    try:
        validate_read_permissions(connector.api_restrictions())
    except BinanceError as exc:
        connector.close()
        connection.last_checked_at = utcnow()
        connection.last_error = str(exc)
        cooldown = (utcnow() + timedelta(seconds=max(60, exc.retry_after_s or 900))).isoformat() if isinstance(exc, BinanceRateLimitError) else None
        session.add(ExchangeSyncHistory(connection_id=connection.id, started_at=utcnow(), finished_at=utcnow(), completed=False, status=EXCH_HISTORY_ERROR, triggered_by=source, error_message=str(exc), detail={"retry_not_before": cooldown}))
        session.commit()
        raise ExchangeVerificationFailed(str(exc)) from exc
    started_at = now or utcnow()
    history = ExchangeSyncHistory(
        connection_id=connection.id,
        started_at=started_at,
        status=EXCH_HISTORY_STARTED,
        triggered_by=source,
    )
    session.add(history)
    session.commit()

    retry_not_before = None
    per_wallet: dict[str, dict] = {}
    snapshots_to_add = []
    for wallet_type in _wallet_types():
        try:
            rows = _read_wallet(wallet_type, connector)
            per_wallet[wallet_type] = {"ok": True, "asset_count": len(rows)}
            for row in rows:
                snapshots_to_add.append(ExchangeBalanceSnapshot(
                    connection_id=connection.id,
                    wallet_type=wallet_type,
                    asset=row["asset"],
                    free=_parse_amount(row["free"]),
                    locked=_parse_amount(row["locked"]),
                    freeze=_parse_amount(row["freeze"]),
                    withdrawing=_parse_amount(row["withdrawing"]),
                    source=source,
                    read_at=started_at,
                ))
        except (BinanceError, ExchangeError) as exc:
            # Per-wallet thất bại — giữ phần thành công, KHÔNG 0 giả cho ví này.
            per_wallet[wallet_type] = {"ok": False, "error": str(exc)}
            if isinstance(exc, BinanceRateLimitError):
                retry_not_before = utcnow() + timedelta(seconds=max(60, exc.retry_after_s or 900))
                for remaining in _wallet_types():
                    per_wallet.setdefault(remaining, {"ok": False, "error": "Tạm dừng do giới hạn Binance"})
                break
    connector.close()

    final_status = EXCH_HISTORY_OK
    if not any(info.get("ok") for info in per_wallet.values()):
        final_status = EXCH_HISTORY_ERROR
    elif not all(info.get("ok") for info in per_wallet.values()):
        final_status = EXCH_HISTORY_PARTIAL

    for snapshot in snapshots_to_add:
        try:
            session.add(snapshot)
            session.commit()
        except IntegrityError:
            # Idempotent: cùng (connection, wallet, asset, read_at) — bỏ qua dòng trùng.
            session.rollback()

    history.status = final_status
    history.detail = {"wallets": per_wallet, "retry_not_before": retry_not_before.isoformat() if retry_not_before else None}
    history.finished_at = utcnow()
    history.completed = final_status == EXCH_HISTORY_OK
    if final_status in (EXCH_HISTORY_ERROR, EXCH_HISTORY_PARTIAL):
        history.error_message = "; ".join(
            f"{wallet_type}: {info.get('error')}"
            for wallet_type, info in per_wallet.items() if info.get("ok") is False
        ) or "Đồng bộ độ phủ một phần"
    session.add(history)

    connection.last_checked_at = utcnow()
    if final_status != EXCH_HISTORY_ERROR:
        connection.last_ok_at = utcnow()
        connection.last_error = None
    if final_status in (EXCH_HISTORY_ERROR, EXCH_HISTORY_PARTIAL):
        connection.last_error = history.error_message
    connection.updated_at = utcnow()

    _audit(session, "EXCHANGE_BALANCES_READ", connection.id, {
        "status": final_status,
        "source": source,
        "snapshots_written": len(snapshots_to_add),
    }, actor=actor)
    session.commit()
    session.refresh(connection)

    result = {
        "status": final_status,
        "started_at": started_at.isoformat(),
        "wallets": per_wallet,
        "snapshots": len(snapshots_to_add),
        "history_id": history.id,
    }
    return connection, result


def list_snapshots(
    session: Session, connection_id: int, *, limit: int = 50
) -> list[dict]:
    if session.get(ExchangeConnection, connection_id) is None:
        raise ExchangeNotFound("Không tìm thấy kết nối")
    rows = session.scalars(
        select(ExchangeBalanceSnapshot)
        .where(ExchangeBalanceSnapshot.connection_id == connection_id)
        .order_by(ExchangeBalanceSnapshot.id.desc())
        .limit(min(max(1, limit), 200))
    ).all()
    return [
        {
            "id": row.id,
            "wallet_type": row.wallet_type,
            "asset": row.asset,
            "free": format(row.free, "f") if row.free is not None else None,
            "locked": format(row.locked, "f") if row.locked is not None else None,
            "freeze": format(row.freeze, "f") if row.freeze is not None else None,
            "withdrawing": format(row.withdrawing, "f") if row.withdrawing is not None else None,
            "source": row.source,
            "read_at": row.read_at.isoformat(),
        }
        for row in rows
    ]


def list_history(
    session: Session, connection_id: int, *, limit: int = 20
) -> list[dict]:
    if session.get(ExchangeConnection, connection_id) is None:
        raise ExchangeNotFound("Không tìm thấy kết nối")
    rows = session.scalars(
        select(ExchangeSyncHistory)
        .where(ExchangeSyncHistory.connection_id == connection_id)
        .order_by(ExchangeSyncHistory.id.desc())
        .limit(min(max(1, limit), 200))
    ).all()
    return [
        {
            "id": row.id,
            "started_at": row.started_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "status": row.status,
            "detail": row.detail,
            "error_message": row.error_message,
            "triggered_by": row.triggered_by,
        }
        for row in rows
    ]


def read_balances(session, connection_id, **kwargs):
    import socket
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        try:
            lock.bind(("127.0.0.1", 8913))
        except OSError:
            raise ExchangeConflict("Đang cập nhật số dư sàn; vui lòng thử lại sau") from None
        return _read_balances_unlocked(session, connection_id, **kwargs)
    finally:
        lock.close()
