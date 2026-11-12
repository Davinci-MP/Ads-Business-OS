"""Kết nối sàn giao dịch & nguồn tiền (D-056, Binance, PingPong VCC) — lưu credentials mã hóa + đọc chỉ đọc.

Ranh giới & Bảo mật:
- Credentials chỉ lưu ciphertext (Fernet) — KHÔNG plaintext, KHÔNG log/response secret.
- Master key qua env (`ADSOS_EXCHANGE_MASTER_KEY`, ít nhất 32 bytes). Chưa cấu hình →
  `ExchangeMasterKeyMissing` — API phải trả 503 kèm hướng dẫn, KHÔNG lưu plaintext.
- Hỗ trợ Binance và PingPong (OpenAPI & Commercial Card VCC); OKX/MEXC từ chối.
- Verify Read-Only:
  (1) Binance: gọi `apiRestrictions` — chỉ chấp nhận khi canRead + !canTrade + !canWithdraw.
  (2) PingPong Issuing: chỉ gọi GET token/balances/cards; API không cung cấp endpoint
      xác minh quyền khóa. Giữ read_only_verified=False, không suy từ việc đọc thành công.
- Snapshot append-only; một ví/nguồn lỗi → giữ phần còn lại + báo độ phủ.
- Chống ghi trùng: unique read_at; chạy lại cùng thời điểm → bỏ qua dòng trùng.
- Audit log sự kiện EXCHANGE_*; detail KHÔNG chứa credentials/secret (chỉ last4 + status).
"""
from __future__ import annotations

import json
import time  # noqa: F401
from datetime import datetime, timezone, timedelta  # noqa: F401
from decimal import Decimal, InvalidOperation

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.binance import (
    BinanceConnector,
    BinanceError,
    BinanceRateLimitError,
    validate_read_permissions as validate_binance_permissions,
)
from app.connectors.pingpong import (
    DEFAULT_PINGPONG_BASE_URL,
    PingPongConnector,
    PingPongError,
    PingPongRateLimitError,
)
from app.core.config import settings
from app.models.exchange import (
    EXCH_HISTORY_ERROR,
    EXCH_HISTORY_OK,
    EXCH_HISTORY_PARTIAL,
    EXCH_HISTORY_STARTED,
    EXCH_PROVIDER_BINANCE,
    EXCH_PROVIDER_PINGPONG,
    EXCH_SOURCE_MANUAL,
    EXCH_STATUS_ACTIVE,
    EXCH_STATUS_REMOVED,
    EXCH_WALLET_CARDS,
    EXCH_WALLET_FUNDING,
    EXCH_WALLET_SPOT,
    ExchangeBalanceSnapshot,
    ExchangeCardSnapshot,
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
    """Verify tài khoản sàn/nguồn tiền không đạt — không lưu."""


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
        "read_only_verified": bool(connection.read_only_verified) if connection.provider != EXCH_PROVIDER_PINGPONG else False,
        "auto_sync": bool(connection.auto_sync),
        "last_checked_at": connection.last_checked_at.isoformat() if connection.last_checked_at else None,
        "last_ok_at": connection.last_ok_at.isoformat() if connection.last_ok_at else None,
        "last_error": connection.last_error,
        "created_at": connection.created_at.isoformat() if connection.created_at else None,
    }
    if credentials is not None:
        view["api_key_last4"] = credentials.api_key_last4
        if credentials.encrypted_extra:
            try:
                fernet = _fernet()
                raw_extra = fernet.decrypt(credentials.encrypted_extra.encode("utf-8")).decode("utf-8")
                extra = json.loads(raw_extra)
                if extra.get("account_id"):
                    view["account_id"] = extra["account_id"]
                if extra.get("base_url"):
                    view["base_url"] = extra["base_url"]
            except Exception:
                pass
    return view


def _wallet_types(provider: str = EXCH_PROVIDER_BINANCE) -> list[str]:
    if provider == EXCH_PROVIDER_PINGPONG:
        return [EXCH_WALLET_FUNDING, EXCH_WALLET_CARDS]
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
        {
            **_connection_view(connection, credential_rows.get(connection.id)),
            "wallet_errors": _latest_wallet_errors(session, connection.id, connection.provider),
        }
        for connection in rows
    ]


def get_connection_view(session: Session, connection_id: int) -> dict:
    row = session.get(ExchangeConnection, connection_id)
    if row is None:
        raise ExchangeNotFound(f"Connection #{connection_id} không tồn tại")
    credential = session.scalars(
        select(ExchangeCredentials).where(ExchangeCredentials.connection_id == connection_id)
    ).first()
    return {
        **_connection_view(row, credential),
        "wallet_errors": _latest_wallet_errors(session, connection_id, row.provider),
    }


def _latest_wallet_errors(session: Session, connection_id: int, provider: str = EXCH_PROVIDER_BINANCE) -> dict:
    latest = session.scalars(select(ExchangeSyncHistory).where(
        ExchangeSyncHistory.connection_id == connection_id
    ).order_by(ExchangeSyncHistory.id.desc()).limit(1)).first()
    if not latest or latest.status not in (EXCH_HISTORY_ERROR, EXCH_HISTORY_PARTIAL):
        return {}
    wallets = (latest.detail or {}).get("wallets", {})
    return {
        name: wallets.get(name, {}).get("error", latest.error_message or "Chưa đọc được")
        for name in _wallet_types(provider) if wallets.get(name, {}).get("ok") is not True
    }


def _validate_credentials_payload(
    api_key: str, api_secret: str, provider: str = EXCH_PROVIDER_BINANCE
) -> tuple[str, str]:
    api_key = (api_key or "").strip()
    api_secret = (api_secret or "").strip()
    prefix = "PingPong App ID / App Secret" if provider == EXCH_PROVIDER_PINGPONG else "Binance apiKey/apiSecret"
    if not api_key or not api_secret:
        raise ExchangeCredentialsError(f"{prefix} không được để trống")
    if provider != EXCH_PROVIDER_PINGPONG and (len(api_key) < 8 or len(api_secret) < 8):
        raise ExchangeCredentialsError(f"{prefix} quá ngắn (ít nhất 8 ký tự)")
    return api_key, api_secret


def verify_pingpong_connection(
    client_id: str,
    client_secret: str,
    account_id: str | None = None,
    base_url: str | None = None,
    *,
    transport=None,
) -> dict:
    """Đọc thử Issuing; không suy quyền khóa từ việc đọc thành công."""
    client_id, client_secret = _validate_credentials_payload(client_id, client_secret, EXCH_PROVIDER_PINGPONG)
    connector = None
    try:
        connector = PingPongConnector(
            client_id=client_id,
            client_secret=client_secret,
            account_id=account_id,
            base_url=base_url or DEFAULT_PINGPONG_BASE_URL,
            transport=transport,
        )
        balances = connector.funding_balances()
        cards = connector.virtual_cards()
        return {
            "ok": True,
            "read_only_verified": False,
            "permissions": None,
            "funding_preview": balances,
            "cards_preview": cards[:5],
            "warnings": ["Issuing không cung cấp API kiểm tra quyền khóa; ứng dụng chỉ gọi GET token/số dư/thẻ, chưa xác minh khóa chỉ đọc."],
        }
    except PingPongError as exc:
        raise ExchangeVerificationFailed(str(exc)) from exc
    finally:
        if connector is not None:
            connector.close()


def verify_connection(
    api_key: str,
    api_secret: str,
    *,
    provider: str = EXCH_PROVIDER_BINANCE,
    account_id: str | None = None,
    base_url: str | None = None,
    transport=None,
) -> dict:
    """Kiểm tra quyền đọc và đọc thử dữ liệu. Không lưu credentials."""
    if provider == EXCH_PROVIDER_PINGPONG:
        return verify_pingpong_connection(
            api_key, api_secret, account_id=account_id, base_url=base_url, transport=transport
        )
    if provider != EXCH_PROVIDER_BINANCE:
        raise ExchangeCredentialsError(f"Nhà cung cấp '{provider}' chưa được hỗ trợ")

    api_key, api_secret = _validate_credentials_payload(api_key, api_secret, EXCH_PROVIDER_BINANCE)
    connector = BinanceConnector(api_key=api_key, api_secret=api_secret, transport=transport)
    try:
        restrictions = connector.api_restrictions()
        warnings: list[str] = []
        try:
            validate_binance_permissions(restrictions)
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
    provider: str = EXCH_PROVIDER_BINANCE,
    account_id: str | None = None,
    base_url: str | None = None,
    actor: str = "admin",
    transport=None,
) -> ExchangeConnection:
    """Verify → encrypt credentials → tạo connection; unique (provider, label)."""
    label_clean = (label or "").strip()
    if not label_clean:
        raise ExchangeCredentialsError("Tên kết nối không được để trống")
    if provider not in (EXCH_PROVIDER_BINANCE, EXCH_PROVIDER_PINGPONG):
        raise ExchangeCredentialsError(f"Nhà cung cấp '{provider}' chưa được hỗ trợ")

    api_key, api_secret = _validate_credentials_payload(api_key, api_secret, provider)

    fernet = _fernet()  # Chưa cấu hình → không lưu plaintext (ExchangeMasterKeyMissing)
    duplicate = session.scalars(
        select(ExchangeConnection).where(
            ExchangeConnection.provider == provider,
            ExchangeConnection.label == label_clean,
            ExchangeConnection.status == EXCH_STATUS_ACTIVE,
        )
    ).first()
    if duplicate is not None:
        prov_name = "PingPong" if provider == EXCH_PROVIDER_PINGPONG else "Binance"
        raise ExchangeConflict(f"Đã có kết nối {prov_name} tên '{label_clean}' — chọn tên khác")

    verification = verify_connection(
        api_key, api_secret, provider=provider, account_id=account_id, base_url=base_url, transport=transport
    )
    encrypted_api_key = fernet.encrypt(api_key.encode("utf-8")).decode("utf-8")
    encrypted_api_secret = fernet.encrypt(api_secret.encode("utf-8")).decode("utf-8")

    encrypted_extra = None
    if account_id or base_url:
        extra_json = json.dumps({"account_id": account_id or "", "base_url": base_url or ""})
        encrypted_extra = fernet.encrypt(extra_json.encode("utf-8")).decode("utf-8")

    connection = ExchangeConnection(
        provider=provider,
        label=label_clean,
        status=EXCH_STATUS_ACTIVE,
        wallet_types=_wallet_types(provider),
        read_only_verified=verification["read_only_verified"],
    )
    session.add(connection)
    session.flush()
    session.add(ExchangeCredentials(
        connection_id=connection.id,
        provider=provider,
        encrypted_api_key=encrypted_api_key,
        encrypted_api_secret=encrypted_api_secret,
        encrypted_extra=encrypted_extra,
        api_key_last4=api_key[-4:],
    ))
    _audit(session, "EXCHANGE_CONNECTION_SAVED", connection.id, {
        "provider": provider,
        "label": label_clean,
        "api_key_last4": api_key[-4:],
        "read_only_verified": verification["read_only_verified"],
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
    account_id: str | None = None,
    base_url: str | None = None,
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
    keys_changed = bool(provided_key or provided_secret)
    extra_changed = connection.provider == EXCH_PROVIDER_PINGPONG and (account_id is not None or base_url is not None)
    if keys_changed or extra_changed:
        if keys_changed and not (provided_key and provided_secret):
            raise ExchangeCredentialsError(
                "Đổi khóa phải cung cấp đủ API Key/Client ID và Secret Key cùng lúc — giữ nguyên chỉ khi cả hai trống"
            )
        fernet = _fernet()
        previous_extra = {}
        try:
            if credential.encrypted_extra:
                previous_extra = json.loads(fernet.decrypt(credential.encrypted_extra.encode()).decode())
            if not keys_changed:
                provided_key = fernet.decrypt(credential.encrypted_api_key.encode()).decode()
                provided_secret = fernet.decrypt(credential.encrypted_api_secret.encode()).decode()
        except (InvalidToken, ValueError):
            raise ExchangeMasterKeyMissing("Không giải mã được credentials hiện tại.") from None
        effective_account_id = account_id if account_id is not None else previous_extra.get("account_id")
        effective_base_url = base_url if base_url is not None else previous_extra.get("base_url")
        verification = verify_connection(
            provided_key,
            provided_secret,
            provider=connection.provider,
            account_id=effective_account_id,
            base_url=effective_base_url,
            transport=transport,
        )
        connection.read_only_verified = verification["read_only_verified"]
        credential.encrypted_api_key = fernet.encrypt(provided_key.encode("utf-8")).decode("utf-8")
        credential.encrypted_api_secret = fernet.encrypt(provided_secret.encode("utf-8")).decode("utf-8")
        credential.api_key_last4 = provided_key[-4:]
        if account_id is not None or base_url is not None:
            extra_dict = {"account_id": effective_account_id or "", "base_url": effective_base_url or ""}
            credential.encrypted_extra = fernet.encrypt(json.dumps(extra_dict).encode("utf-8")).decode("utf-8")
        credential.updated_at = utcnow()

    if new_label:
        connection.label = new_label
    connection.updated_at = utcnow()
    _audit(session, "EXCHANGE_CONNECTION_UPDATED", connection.id, {
        "label": connection.label,
        "api_key_changed": keys_changed,
    }, actor=actor)
    session.commit()
    session.refresh(connection)
    return connection


def set_auto_sync(
    session: Session, connection_id: int, enabled: bool, *, actor: str = "admin"
) -> ExchangeConnection:
    connection = _conn_or_raised(session, connection_id)
    if enabled and not settings.exchange_scheduler_enabled:
        raise ExchangeError("Scheduler chưa được bật ở máy chủ")
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


# -------------------------------------------------------------------- reading
def _parse_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
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
    """Đọc số dư & thẻ ảo theo provider: append snapshot; lịch sử + audit KHÔNG chứa secret."""
    connection = _conn_or_raised(session, connection_id)
    latest_attempt = session.scalars(select(ExchangeSyncHistory).where(
        ExchangeSyncHistory.connection_id == connection_id
    ).order_by(ExchangeSyncHistory.id.desc()).limit(1)).first()
    if latest_attempt and latest_attempt.detail:
        until = latest_attempt.detail.get("retry_not_before")
        if until and datetime.fromisoformat(until) > utcnow():
            raise ExchangeConflict("Dịch vụ đang giới hạn truy cập; vui lòng chờ tới " + until)

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

    started_at = now or utcnow()

    # ======================== XỬ LÝ PINGPONG ========================
    if connection.provider == EXCH_PROVIDER_PINGPONG:
        account_id = None
        base_url = DEFAULT_PINGPONG_BASE_URL
        if credential.encrypted_extra:
            try:
                raw_extra = fernet.decrypt(credential.encrypted_extra.encode("utf-8")).decode("utf-8")
                extra_data = json.loads(raw_extra)
                account_id = extra_data.get("account_id") or None
                base_url = extra_data.get("base_url") or DEFAULT_PINGPONG_BASE_URL
            except Exception:
                pass

        try:
            pp_connector = PingPongConnector(
                client_id=api_key,
                client_secret=api_secret,
                account_id=account_id,
                base_url=base_url,
                transport=transport,
            )
        except PingPongError as exc:
            connection.last_checked_at = utcnow()
            connection.last_error = str(exc)
            session.add(ExchangeSyncHistory(connection_id=connection.id, started_at=started_at,
                finished_at=utcnow(), completed=False, status=EXCH_HISTORY_ERROR,
                triggered_by=source, error_message=str(exc)))
            session.commit()
            raise ExchangeVerificationFailed(str(exc)) from exc
        connection.read_only_verified = False

        history = ExchangeSyncHistory(
            connection_id=connection.id,
            started_at=started_at,
            status=EXCH_HISTORY_STARTED,
            triggered_by=source,
        )
        session.add(history)
        session.commit()

        per_wallet: dict[str, dict] = {}
        snapshots_to_add: list[ExchangeBalanceSnapshot] = []
        cards_to_add: list[ExchangeCardSnapshot] = []

        # 1. Đọc funding balances
        try:
            balances = pp_connector.funding_balances()
            per_wallet[EXCH_WALLET_FUNDING] = {"ok": True, "asset_count": len(balances)}
            for item in balances:
                snapshots_to_add.append(ExchangeBalanceSnapshot(
                    connection_id=connection.id,
                    wallet_type=EXCH_WALLET_FUNDING,
                    asset=item["currency"],
                    free=_parse_amount(item["available_balance"]),
                    locked=_parse_amount(item["frozen_balance"]),
                    freeze=None,
                    withdrawing=None,
                    source=source,
                    read_at=started_at,
                ))
        except (PingPongError, ExchangeError) as exc:
            per_wallet[EXCH_WALLET_FUNDING] = {"ok": False, "error": str(exc)}

        # 2. Đọc virtual cards
        try:
            cards = pp_connector.virtual_cards()
            per_wallet[EXCH_WALLET_CARDS] = {"ok": True, "card_count": len(cards)}
            for card in cards:
                cards_to_add.append(ExchangeCardSnapshot(
                    connection_id=connection.id,
                    card_id=card["card_id"],
                    card_name=card.get("card_name", ""),
                    last4=card["last4"],
                    currency=card["currency"],
                    status=card.get("status", "ACTIVE"),
                    spending_limit=_parse_amount(card["spending_limit"]) if card.get("spending_limit") is not None else None,
                    available_balance=_parse_amount(card["available_balance"]) if card.get("available_balance") is not None else None,
                    source=source,
                    read_at=started_at,
                ))
        except (PingPongError, ExchangeError) as exc:
            per_wallet[EXCH_WALLET_CARDS] = {"ok": False, "error": str(exc)}

        pp_connector.close()

        final_status = EXCH_HISTORY_OK
        if not any(info.get("ok") for info in per_wallet.values()):
            final_status = EXCH_HISTORY_ERROR
        elif not all(info.get("ok") for info in per_wallet.values()):
            final_status = EXCH_HISTORY_PARTIAL

        for snap in snapshots_to_add:
            try:
                session.add(snap)
                session.commit()
            except IntegrityError:
                session.rollback()

        for card_snap in cards_to_add:
            try:
                session.add(card_snap)
                session.commit()
            except IntegrityError:
                session.rollback()

        history.status = final_status
        history.detail = {"wallets": per_wallet}
        history.finished_at = utcnow()
        history.completed = final_status == EXCH_HISTORY_OK
        if final_status in (EXCH_HISTORY_ERROR, EXCH_HISTORY_PARTIAL):
            history.error_message = "; ".join(
                f"{k}: {v.get('error')}" for k, v in per_wallet.items() if v.get("ok") is False
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
            "provider": EXCH_PROVIDER_PINGPONG,
            "status": final_status,
            "source": source,
            "snapshots_written": len(snapshots_to_add),
            "cards_written": len(cards_to_add),
        }, actor=actor)
        session.commit()
        session.refresh(connection)

        result = {
            "status": final_status,
            "started_at": started_at.isoformat(),
            "wallets": per_wallet,
            "snapshots": len(snapshots_to_add),
            "cards": len(cards_to_add),
            "history_id": history.id,
        }
        return connection, result

    # ======================== XỬ LÝ BINANCE ========================
    connector = BinanceConnector(api_key=api_key, api_secret=api_secret, transport=transport)
    try:
        validate_binance_permissions(connector.api_restrictions())
    except BinanceError as exc:
        connector.close()
        connection.last_checked_at = utcnow()
        connection.last_error = str(exc)
        cooldown = (utcnow() + timedelta(seconds=max(60, exc.retry_after_s or 900))).isoformat() if isinstance(exc, BinanceRateLimitError) else None
        session.add(ExchangeSyncHistory(
            connection_id=connection.id,
            started_at=utcnow(),
            finished_at=utcnow(),
            completed=False,
            status=EXCH_HISTORY_ERROR,
            triggered_by=source,
            error_message=str(exc),
            detail={"retry_not_before": cooldown},
        ))
        session.commit()
        raise ExchangeVerificationFailed(str(exc)) from exc

    history = ExchangeSyncHistory(
        connection_id=connection.id,
        started_at=started_at,
        status=EXCH_HISTORY_STARTED,
        triggered_by=source,
    )
    session.add(history)
    session.commit()

    retry_not_before = None
    per_wallet = {}
    snapshots_to_add = []
    for wallet_type in _wallet_types(connection.provider):
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
            per_wallet[wallet_type] = {"ok": False, "error": str(exc)}
            if isinstance(exc, BinanceRateLimitError):
                retry_not_before = utcnow() + timedelta(seconds=max(60, exc.retry_after_s or 900))
                for remaining in _wallet_types(connection.provider):
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
        "provider": EXCH_PROVIDER_BINANCE,
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


def list_cards(
    session: Session, connection_id: int, *, limit: int = 50
) -> list[dict]:
    """Danh sách snapshot thẻ ảo VCC mới nhất theo từng card_id."""
    if session.get(ExchangeConnection, connection_id) is None:
        raise ExchangeNotFound("Không tìm thấy kết nối")
    rows = session.scalars(
        select(ExchangeCardSnapshot)
        .where(ExchangeCardSnapshot.connection_id == connection_id)
        .order_by(ExchangeCardSnapshot.read_at.desc(), ExchangeCardSnapshot.id.desc())
        .limit(min(max(1, limit), 200))
    ).all()

    # Nhóm để lấy snapshot mới nhất cho mỗi card_id
    latest_cards: dict[str, ExchangeCardSnapshot] = {}
    for r in rows:
        if r.card_id not in latest_cards:
            latest_cards[r.card_id] = r

    return [
        {
            "id": card.id,
            "card_id": card.card_id,
            "card_name": card.card_name,
            "last4": card.last4,
            "currency": card.currency,
            "status": card.status,
            "spending_limit": format(card.spending_limit, "f") if card.spending_limit is not None else None,
            "available_balance": format(card.available_balance, "f") if card.available_balance is not None else None,
            "source": card.source,
            "read_at": card.read_at.isoformat(),
        }
        for card in latest_cards.values()
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
            raise ExchangeConflict("Đang cập nhật số dư sàn/nguồn tiền; vui lòng thử lại sau") from None
        return _read_balances_unlocked(session, connection_id, **kwargs)
    finally:
        lock.close()
