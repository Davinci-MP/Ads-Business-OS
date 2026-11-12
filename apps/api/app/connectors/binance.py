"""Binance connector — CHỈ ĐỌC (D-056).

Ranh giới:
- Base URL cố định `https://api.binance.com`; chỉ gọi các path trong whitelist
  (spot account, funding wallet, apiRestrictions, server time). Không nhận URL tùy ý.
- KHÔNG có method đặt lệnh / rút tiền / chuyển nội bộ. Mọi ghi = ngoài phạm vi.
- Signature: HMAC-SHA256 trên toàn bộ query string (SIGNED endpoints), hex; tham số
  nhúng vào query string cho cả GET và POST để payload ký luôn là query string theo
  tài liệu chính thức; `recvWindow` ≤ 60000ms (mặc định 5000).
- Timestamp theo giờ server Binance: đọc offset từ GET /api/v3/time, cache TTL ngắn;
  khi Binance trả code -1021 (timestamp outside recvWindow) → re-sync 1 lần rồi thử lại.
- Rate limit: HTTP 429/418 → `BinanceRateLimitError` (chữ Retry-After nếu Meta gửi);
  không tự retry vòng lặp vì có thể khiến IP bị cấm lâu hơn.
- Lỗi transport (timeout/mạng/5xx) → retry có giới hạn; HTTP 401/403 và code
  -2014/-2015/-1022 → `BinanceAuthError`. Lỗi → connector ném exception, KHÔNG trả 0 giả
  (D-011); caller giữ dữ liệu cũ.
- Không log/inlude secret: exception message chỉ chứa path + code + msg; apiKey và
  signature trong URL bị che nếu success debug cần.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import threading
import time
import urllib.parse
from typing import Any

import httpx

base_url = "https://api.binance.com"

spot_account_path = "/api/v3/account"
funding_wallet_path = "/sapi/v1/asset/get-funding-asset"
api_restrictions_path = "/sapi/v1/account/apiRestrictions"
server_time_path = "/api/v3/time"

_ALLOWED_PATHS = frozenset({
    spot_account_path,
    funding_wallet_path,
    api_restrictions_path,
    server_time_path,
})

_DEFAULT_TIMEOUT_S = 15.0
_MAX_RETRIES = 2
_RECV_WINDOW_MS = 5000
_SERVER_OFFSET_TTL_S = 60.0

_CODE_TIMESTAMP_OUTSIDE_RECV_WINDOW = -1021
_CODE_SIGNATURE_INVALID = -1022
_CODE_INVALID_API_KEY = -2014
_CODE_NO_PERMISSION = -2015


class BinanceError(Exception):
    """Lỗi Binance — message không chứa secret."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BinanceAuthError(BinanceError):
    """Lỗi xác thực/thiếu quyền đọc — không nên tự retry."""


class BinanceRateLimitError(BinanceError):
    """HTTP 429/418 — caller phải honor Retry-After, không retry ngay."""

    def __init__(self, message: str, retry_after_s: float | None = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s


class BinanceTransportError(BinanceError):
    """Lỗi mạng/timeout/5xx."""


def _redact(text: str) -> str:
    """Che apiKey/signature nếu vô tình lọt vào chuỗi lỗi."""
    out = text
    for token in ("apiKey=", "signature=", "X-MBX-APIKEY"):
        idx = out.find(token)
        while idx != -1:
            end = out.find("&", idx)
            if end == -1:
                end = len(out)
            out = out[: idx + len(token)] + "[REDACTED]" + out[end:]
            idx = out.find(token, idx + len(token) + len("[REDACTED]"))
    return out


class BinanceConnector:
    """Connector read-only cho Binance Spot + Funding."""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        recv_window_ms: int = _RECV_WINDOW_MS,
        server_offset_ttl_s: float = _SERVER_OFFSET_TTL_S,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key or not api_secret:
            raise BinanceError("Binance apiKey/apiSecret không được để trống")
        if not (0 < recv_window_ms <= 60000):
            raise BinanceError("recvWindow phải trong khoảng (0, 60000] ms")
        self._api_secret = api_secret.encode("utf-8")
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_s,
            transport=transport,
            headers={"X-MBX-APIKEY": api_key},
        )
        self._max_retries = 2
        self._recv_window_ms = recv_window_ms
        self._server_offset_ttl_s = server_offset_ttl_s
        self._server_offset_ms = 0
        self._server_offset_at = 0.0
        self._offset_lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BinanceConnector":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ---------------------------------------------------------------- public
    def spot_balances(self) -> list[dict[str, str]]:
        """GET /api/v3/account (USER_DATA, weight 20) — list {'asset','free','locked'} chuỗi gốc."""
        body = self._signed_request("GET", spot_account_path, {})
        rows = body.get("balances") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise BinanceError("spot: response thiếu 'balances' dạng list")
        return _parse_rows(rows, funding=False)

    def funding_balances(self, *, asset: str = "USDT") -> list[dict[str, str]]:
        body = self._signed_request("POST", funding_wallet_path, {"asset": asset})
        if not isinstance(body, list):
            raise BinanceError("Funding: response không phải danh sách")
        return _parse_rows(body, funding=True)

    def api_restrictions(self) -> dict[str, bool]:
        body = self._signed_request("GET", api_restrictions_path, {})
        if not isinstance(body, dict):
            raise BinanceError("Không đọc được quyền API")
        return {key: value for key, value in body.items() if isinstance(value, bool)}

    # -------------------------------------------------------------- internal
    def _server_time_offset_ms(self, *, force: bool = False) -> int:
        now_monotonic = time.monotonic()
        with self._offset_lock:
            if not force and now_monotonic - self._server_offset_at < self._server_offset_ttl_s:
                return self._server_offset_ms
            response = self._send_with_retries("GET", server_time_path, signed_qs="")
            if response.status_code == 429 or response.status_code == 418:
                raise BinanceRateLimitError(
                    f"{server_time_path}: HTTP {response.status_code}",
                    _retry_after_s(response),
                )
            if response.status_code >= 500:
                raise BinanceTransportError(f"{server_time_path}: HTTP {response.status_code}")
            try:
                server_time_ms = int(response.json()["serverTime"])
            except Exception as exc:
                raise BinanceError(f"GET {server_time_path}: response không đọc được — {_redact(str(exc))}") from exc
            self._server_offset_ms = server_time_ms - int(time.time() * 1000)
            self._server_offset_at = now_monotonic
            return self._server_offset_ms

    def _signed_request(self, method: str, path: str, params: dict[str, str]) -> dict | list:
        """SIGNED GET/POST: signature = HMAC-SHA256(query string) — mã hex."""
        if not isinstance(params, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in params.items()):
            raise BinanceError("params phải là dict[str, str]")
        force_sync = False
        last_message = ""
        for attempt in range(self._max_retries + 1):
            offset = self._server_time_offset_ms(force=force_sync)
            timestamp_ms = int(time.time() * 1000) + offset
            pieces: list[str] = []
            base_qs = urllib.parse.urlencode(params)
            if base_qs:
                pieces.append(base_qs)
            pieces.append(f"recvWindow={self._recv_window_ms}")
            pieces.append(f"timestamp={timestamp_ms}")
            total = "&".join(pieces)
            signature = hmac.new(self._api_secret, total.encode("utf-8"), hashlib.sha256).hexdigest()
            signed_qs = f"{total}&signature={signature}"
            response = self._send_with_retries(method, path, signed_qs=signed_qs)
            if response.status_code == 200:
                try:
                    return response.json()
                except Exception as exc:
                    raise BinanceError(f"{path}: JSON không đọc được — {_redact(str(exc))}") from exc
            try:
                payload: Any = response.json()
            except Exception:
                payload = None
            code = payload.get("code") if isinstance(payload, dict) else None
            last_message = _error_message(path, response.status_code, code, payload)
            if code == _CODE_TIMESTAMP_OUTSIDE_RECV_WINDOW and attempt < self._max_retries:
                force_sync = True
                continue
            if resp_is_auth_failure(response.status_code, code):
                raise BinanceAuthError(last_message)
            if response.status_code == 429 or response.status_code == 418:
                raise BinanceRateLimitError(last_message, _retry_after_s(response))
            if response.status_code >= 500:
                raise BinanceTransportError(last_message)
            raise BinanceError(last_message)
        raise BinanceError(last_message or f"{path}: hết số lượt retry cho phép")

    def _send_with_retries(self, method: str, path: str, *, signed_qs: str) -> httpx.Response:
        if path not in _ALLOWED_PATHS:
            raise BinanceError(f"path không nằm trong whitelist: {path}")
        target = f"{path}?{signed_qs}" if signed_qs else path
        last_exc: BinanceError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._client.request(method, target)
            except httpx.HTTPError as exc:
                last_exc = BinanceTransportError(f"{path}: lỗi kết nối ({type(exc).__name__})")
                if attempt < self._max_retries:
                    continue
        raise last_exc if last_exc else BinanceError(f"{path}: transport lỗi không xác định")


def resp_is_auth_failure(status: int, code: Any) -> bool:
    if status in (401, 403):
        return True
    return code in (
        _CODE_SIGNATURE_INVALID,
        _CODE_INVALID_API_KEY,
        _CODE_NO_PERMISSION,
    )


def _error_message(path: str, status: int, code: Any, payload: Any) -> str:
    binance_msg = payload.get("msg") if isinstance(payload, dict) and payload.get("msg") else None
    brief = binance_msg or "Yêu cầu bị Binance từ chối; kiểm tra quyền, IP và thời gian máy chủ."
    return f"{path}: HTTP {status}, code={code}, msg={_redact(str(brief))}"


def _retry_after_s(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


WRITE_PERMISSIONS = (
    "enableWithdrawals", "enableInternalTransfer", "enableMargin", "enableFutures",
    "permitsUniversalTransfer", "enableVanillaOptions", "enableSpotAndMarginTrading",
    "enablePortfolioMarginTrading", "enableFixApiTrade",
)
REQUIRED_PERMISSIONS = ("enableReading", "enableWithdrawals", "enableInternalTransfer",
                        "enableSpotAndMarginTrading", "permitsUniversalTransfer")

def validate_read_permissions(permissions: dict) -> None:
    if any(type(permissions.get(key)) is not bool for key in REQUIRED_PERMISSIONS):
        raise BinanceError("Thiếu thông tin quyền API; chưa xác minh được khóa chỉ đọc")
    if permissions["enableReading"] is not True or any(permissions.get(key) is True for key in WRITE_PERMISSIONS):
        raise BinanceError("Chỉ chấp nhận khóa có quyền đọc, không có quyền giao dịch/rút/chuyển tiền")

def _parse_rows(rows: list, *, funding: bool) -> list[dict[str, str]]:
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("asset"), str):
            raise BinanceError("Dòng tài sản không hợp lệ")
        if row["asset"] != "USDT":
            continue
        if row["asset"] in seen:
            raise BinanceError("Response có tài sản USDT trùng")
        seen.add(row["asset"])
        out = {"asset": "USDT"}
        for key in ("free", "locked", "freeze", "withdrawing"):
            value = row.get(key) if funding or key in ("free", "locked") else "0"
            try:
                number = Decimal(value) if isinstance(value, str) else None
                if number is None or not number.is_finite() or number < 0:
                    raise ValueError()
            except (InvalidOperation, ValueError):
                raise BinanceError(f"USDT thiếu hoặc sai trường {key}") from None
            out[key] = str(number)
        result.append(out)
    # A valid complete asset list with no USDT means a determined zero balance.
    return result or [{"asset": "USDT", "free": "0", "locked": "0", "freeze": "0", "withdrawing": "0"}]
