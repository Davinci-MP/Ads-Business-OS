"""PingPong Issuing 2.7.1: GET-only token, account balances and masked card list.

Official contract: developer.pingpongx.com/apiDocs/main?business=Issuing&version=2.7.1
App ID/Secret retain the internal client_id/client_secret names for stored credentials.
No endpoint for inspecting credential permissions is documented: never fabricate verification.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import logging
import re
import threading
import time
from typing import Any
import urllib.parse

import httpx

DEFAULT_PINGPONG_BASE_URL = "https://gateway.pingpongx.com"
PINGPONG_SANDBOX_BASE_URL = "https://sandbox-gateway.pingpongx.com"
TOKEN_PATH = "/v2/token/get"
BALANCE_PATH = "/v2/vcc/open/account/balance/all"
CARDS_PATH = "/v2/vcc/open/cards"
ISSUING_CARDS_PATH = "/v2/issuing/cards"
TRANSACTIONS_PATH = "/v2/vcc/open/transactions"
CARD_TRANSACTIONS_PATH = "/v2/vcc/open/card/transactions"
_ALLOWED_PATHS = frozenset({
    TOKEN_PATH,
    BALANCE_PATH,
    CARDS_PATH,
    ISSUING_CARDS_PATH,
    TRANSACTIONS_PATH,
    CARD_TRANSACTIONS_PATH,
})

_DEFAULT_TIMEOUT_S = 8.0
_MAX_RETRIES = 2

# Biểu thức tìm số thẻ (13-19 số) và CVV (3-4 số) để che giấu
_PAN_REGEX = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_CVV_REGEX = re.compile(r"""(?i)(["']?(?:cvv|cvc|security_code)["']?\s*[:=]\s*["']?)(\d{3,4})(["']?)""")
_EXCLUDED_SIGN_KEYS = frozenset({"sign", "signature", "pingpong-signature", "pingpong_signature"})


class PingPongError(ValueError):
    """Lỗi PingPong connector — thông báo không chứa secret/PAN/CVV."""

    def __init__(self, message: str, code: str | None = None):
        safe_msg = _redact(message)
        super().__init__(safe_msg)
        self.message = safe_msg
        self.code = code


class PingPongAuthError(PingPongError):
    """Lỗi xác thực hoặc không đủ quyền đọc."""


class PingPongRateLimitError(PingPongError):
    """HTTP 429 — vượt quá hạn mức truy vấn."""

    def __init__(self, message: str, retry_after_s: float | None = None, code: str | None = None):
        super().__init__(message, code=code)
        self.retry_after_s = retry_after_s


class PingPongTransportError(PingPongError):
    """Lỗi kết nối mạng/timeout/5xx."""


def _redact(text: str) -> str:
    """Che giấu triệt để secrets, full card PAN và CVV khỏi chuỗi text/error log."""
    if not text:
        return ""
    out = text

    # Che các tham số bí mật thông dụng
    for key in ("app_secret=", "client_secret=", "secret=", "access_token=", "token=", "Authorization: Bearer "):
        idx = out.find(key)
        while idx != -1:
            end = out.find("&", idx)
            if end == -1:
                end = out.find(" ", idx + len(key))
            if end == -1:
                end = len(out)
            out = out[: idx + len(key)] + "[REDACTED]" + out[end:]
            idx = out.find(key, idx + len(key) + len("[REDACTED]"))

    # Che CVV
    out = _CVV_REGEX.sub(r"\1***\3", out)

    # Che PAN (chỉ giữ 4 số cuối nếu khớp dạng thẻ)
    def _mask_pan(match: re.Match) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19:
            return f"****{digits[-4:]}"
        return raw

    out = _PAN_REGEX.sub(_mask_pan, out)
    return out


def _mask_card_number(raw_number: str | None) -> str:
    """Trích xuất an toàn 4 số cuối thẻ, che toàn bộ phần còn lại."""
    if not raw_number:
        return "—"
    digits = re.sub(r"\D", "", str(raw_number))
    if len(digits) >= 4:
        return digits[-4:]
    return digits


def _format_param_val(val: Any) -> str:
    """Định dạng giá trị tham số ký không khoảng trắng thừa."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (dict, list)):
        return json.dumps(val, separators=(",", ":"), sort_keys=True)
    return str(val)


def build_string_to_sign(
    path: str,
    timestamp: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | str | None = None,
) -> str:
    """Xây dựng chuỗi ký String-to-Sign cho PingPong Issuing 2.7.1.

    Quy tắc:
    - Thu thập body/query parameters (loại trừ sign/signature).
    - Sắp xếp các tham số theo thứ tự bảng chữ cái (A-Z) theo tên tham số (key).
    - Định dạng key=value nối bằng ký tự '&' (không có khoảng trắng thừa).
    - Nối với URI và timestamp:
      - Nếu có tham số: f"{path}?{param_str}&timestamp={timestamp}"
      - Nếu không có tham số: f"{path}?timestamp={timestamp}"
    """
    clean_path = (path or "").strip()
    if "?" in clean_path:
        clean_path, raw_query = clean_path.split("?", 1)
    else:
        raw_query = ""

    clean_ts = str(timestamp).strip()
    merged_params: dict[str, Any] = {}

    if raw_query:
        for k, v in urllib.parse.parse_qsl(raw_query, keep_blank_values=True):
            if k.lower() not in _EXCLUDED_SIGN_KEYS:
                merged_params[k] = v

    if params:
        for k, v in params.items():
            if k.lower() not in _EXCLUDED_SIGN_KEYS and v is not None:
                merged_params[k] = v

    if isinstance(body, dict):
        for k, v in body.items():
            if k.lower() not in _EXCLUDED_SIGN_KEYS and v is not None:
                merged_params[k] = v

    sorted_keys = sorted(merged_params.keys())
    param_pairs = [f"{k}={_format_param_val(merged_params[k])}" for k in sorted_keys]
    param_str = "&".join(param_pairs)

    if param_str:
        return f"{clean_path}?{param_str}&timestamp={clean_ts}"
    return f"{clean_path}?timestamp={clean_ts}"


def generate_signature(secret: str, string_to_sign: str) -> str:
    """Tạo chữ ký HMAC-SHA256 hoặc RSA-SHA256 (nếu secret là RSA private key PEM)."""
    secret = (secret or "").strip()
    if not secret:
        return ""

    # Hỗ trợ RSA Private Key PEM
    if secret.startswith("-----BEGIN"):
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            import base64

            private_key = load_pem_private_key(secret.encode("utf-8"), password=None)
            signature_bytes = private_key.sign(
                string_to_sign.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return base64.b64encode(signature_bytes).decode("ascii")
        except Exception as exc:
            raise PingPongError(f"Không thể tạo chữ ký RSA PingPong: {exc}") from exc

    # Mặc định: HMAC-SHA256 với App Secret
    return hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _is_success(payload: dict[str, Any]) -> bool:
    """Kiểm tra mã trạng thái nghiệp vụ PingPong biểu thị thành công."""
    if payload.get("success") is True:
        return True
    code = payload.get("code")
    if code is not None and str(code).strip() in {"6666", "0", "00000", "200"}:
        return True
    return False


def _extract_business_error(payload: dict[str, Any]) -> tuple[str, str]:
    """Trích xuất mã lỗi và thông điệp lỗi nghiệp vụ cụ thể từ JSON payload PingPong."""
    error_code = (
        payload.get("code")
        if payload.get("code") is not None
        else (
            payload.get("bizCode")
            or payload.get("subCode")
            or payload.get("errorCode")
            or "UNKNOWN"
        )
    )
    error_code_str = str(error_code).strip()

    error_message = (
        payload.get("msg")
        or payload.get("message")
        or payload.get("bizMsg")
        or payload.get("subMsg")
        or payload.get("errorMsg")
        or payload.get("error_msg")
        or payload.get("description")
    )
    if not error_message:
        error_message = f"Mã lỗi {error_code_str}"
    error_msg_str = str(error_message).strip()

    return error_code_str, error_msg_str


class _SafeTransport(httpx.BaseTransport):
    """Strip token-query credentials before httpx logs or formats request errors."""

    def __init__(self, inner: httpx.BaseTransport):
        self.inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return self.inner.handle_request(request)
        finally:
            if request.url.path == TOKEN_PATH:
                request.url = request.url.copy_with(query=b"")

    def close(self) -> None:
        self.inner.close()


class PingPongConnector:
    def __init__(self, *, client_id: str, client_secret: str, account_id: str | None = None,
                 base_url: str = DEFAULT_PINGPONG_BASE_URL, timeout_s: float = _DEFAULT_TIMEOUT_S,
                 transport: httpx.BaseTransport | None = None):
        self._client_id = (client_id or "").strip()
        self._client_secret = (client_secret or "").strip()
        if not self._client_id or not self._client_secret:
            raise PingPongError("App ID/App Secret không được để trống")
        self._account_id = account_id  # Legacy metadata; not an Issuing authentication field.
        self._base_url = (base_url or DEFAULT_PINGPONG_BASE_URL).strip().rstrip("/")
        if self._base_url not in {DEFAULT_PINGPONG_BASE_URL, PINGPONG_SANDBOX_BASE_URL}:
            raise PingPongError(
                "Issuing 2.7.1 chỉ dùng https://gateway.pingpongx.com hoặc "
                "https://sandbox-gateway.pingpongx.com; không dùng website pingpongx.com."
            )
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout_s,
            transport=_SafeTransport(transport if transport is not None else httpx.HTTPTransport()),
            follow_redirects=False, trust_env=False)
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = threading.Lock()
        self._max_retries = _MAX_RETRIES

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _send(
        self,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if path not in _ALLOWED_PATHS:
            raise PingPongError("Đường dẫn không nằm trong whitelist bảo mật")

        timestamp = str(int(time.time() * 1000))
        string_to_sign = build_string_to_sign(
            path=path,
            timestamp=timestamp,
            params=params,
            body=json_data if isinstance(json_data, dict) else None,
        )
        signature = generate_signature(self._client_secret, string_to_sign)

        req_headers = {
            "Content-Type": "application/json",
            "PingPong-Client-Id": self._client_id,
            "PingPong-Timestamp": timestamp,
            "PingPong-Signature": signature,
        }
        if headers:
            req_headers.update(headers)

        for attempt in range(self._max_retries + 1):
            try:
                if method.upper() == "POST":
                    response = self._client.post(path, params=params, json=json_data, headers=req_headers)
                else:
                    response = self._client.get(path, params=params, headers=req_headers)
            except httpx.HTTPError:
                if attempt < self._max_retries:
                    time.sleep(0.1)
                    continue
                raise PingPongTransportError("Không thể kết nối PingPong; kiểm tra mạng/gateway.") from None

            status = response.status_code
            if 300 <= status < 400:
                raise PingPongError(f"PingPong chuyển hướng (HTTP {status}); kiểm tra gateway, không chuyển tiếp khóa.")
            if status in (401, 403):
                raise PingPongAuthError(f"PingPong từ chối xác thực (HTTP {status}); kiểm tra App ID/App Secret, môi trường và IP whitelist.")
            if status == 429:
                try:
                    retry = float(response.headers.get("Retry-After", ""))
                except ValueError:
                    retry = None
                raise PingPongRateLimitError("PingPong giới hạn tần suất (HTTP 429).", retry)
            if status >= 500:
                if attempt < self._max_retries:
                    time.sleep(0.1)
                    continue
                raise PingPongTransportError(f"Máy chủ PingPong lỗi (HTTP {status}).")
            if status != 200:
                raise PingPongError(f"PingPong trả HTTP {status}; kiểm tra Issuing 2.7.1.")

            try:
                payload = response.json(parse_float=Decimal)
            except (ValueError, UnicodeError):
                raise PingPongError("PingPong trả JSON không hợp lệ.") from None

            if not isinstance(payload, dict):
                raise PingPongError("PingPong trả sai cấu trúc phản hồi.")

            if not _is_success(payload):
                err_code, err_msg = _extract_business_error(payload)
                full_error = f"PingPong API Error [{err_code}]: {err_msg}"
                lower_msg = err_msg.lower()
                is_auth_issue = (
                    err_code in {"1004", "1005", "4109", "401", "403"}
                    or any(k in lower_msg for k in ("signature", "whitelist", "ip", "auth", "permission", "unauthorized", "forbidden"))
                )
                if is_auth_issue:
                    raise PingPongAuthError(full_error, code=err_code)
                raise PingPongError(full_error, code=err_code)

            if "data" not in payload:
                raise PingPongError("Phản hồi PingPong thiếu data.")
            return payload["data"]

    def _ensure_access_token(self) -> str:
        with self._token_lock:
            now = time.monotonic()
            if self._access_token and now < self._token_expires_at:
                return self._access_token
            data = self._send(TOKEN_PATH, params={"app_id": self._client_id, "app_secret": self._client_secret})
            if not isinstance(data, dict) or not isinstance(data.get("access_token"), str) or not data["access_token"]:
                raise PingPongAuthError("PingPong không trả access_token hợp lệ.")
            try:
                ttl = int(data["expires_in"])
                if ttl <= 0:
                    raise ValueError
            except (KeyError, ValueError, TypeError, OverflowError):
                raise PingPongAuthError("PingPong không trả thời hạn token hợp lệ.") from None
            self._access_token = data["access_token"]
            self._token_expires_at = now + max(0, ttl - min(60, ttl // 10))
            return self._access_token

    def _request(self, method: str, path: str, *, params=None, json_data=None) -> Any:
        if method != "GET" or path not in _ALLOWED_PATHS:
            raise PingPongError("Chỉ cho phép GET các endpoint chỉ đọc trong whitelist.")
        token = self._ensure_access_token()
        # The official balance example uses Bearer; card-list example uses the raw token.
        authorization = f"Bearer {token}" if path == BALANCE_PATH else token
        return self._send(path, method="GET", params=params, json_data=json_data, headers={"Authorization": authorization})

    @staticmethod
    def _amount(value: Any) -> str:
        if value is None or isinstance(value, bool):
            raise PingPongError("PingPong thiếu số dư; giữ dữ liệu cũ.")
        try:
            number = Decimal(str(value))
            if not number.is_finite():
                raise ValueError
        except (InvalidOperation, ValueError):
            raise PingPongError("Số dư PingPong không hợp lệ; giữ dữ liệu cũ.") from None
        return str(number)

    def funding_balances(self) -> list[dict[str, str]]:
        data = self._request("GET", BALANCE_PATH)
        # Account-balance response is an array of budget balances, or one balance object.
        rows = data if isinstance(data, list) else [data] if isinstance(data, dict) and "currency" in data else None
        if rows is None:
            raise PingPongError("Sai cấu trúc số dư Issuing; giữ dữ liệu cũ.")
        results = []
        currencies = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("currency"), str) or not row["currency"].strip():
                raise PingPongError("Thiếu tiền tệ của số dư PingPong.")
            currency = row["currency"].strip().upper()
            if currency in currencies:
                raise PingPongError("Nhiều budget cùng tiền tệ; chưa hỗ trợ gộp, giữ dữ liệu cũ.")
            currencies.add(currency)
            results.append({"currency": currency, "available_balance": self._amount(row.get("balance")),
                "frozen_balance": self._amount(row.get("pending_balance")),
                "total_balance": self._amount(row.get("total_balance"))})
        return results

    def virtual_cards(self) -> list[dict[str, Any]]:
        results = []
        seen = set()
        for page in range(1, 101):
            data = self._request("GET", CARDS_PATH, params={"start_page": page, "row": 100})
            rows = data.get("list") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise PingPongError("Sai cấu trúc danh sách thẻ Issuing; giữ dữ liệu cũ.")
            for row in rows:
                if not isinstance(row, dict):
                    raise PingPongError("Sai cấu trúc thẻ Issuing.")
                # Official descriptions use snake_case; official Postman tests use camelCase.
                card_id = row.get("pp_card_id", row.get("ppCardId"))
                currency = row.get("billing_currency", row.get("billingCurrency"))
                status = row.get("card_status", row.get("cardStatus"))
                if not card_id or not currency or not status or str(card_id) in seen:
                    raise PingPongError("Thẻ thiếu trường bắt buộc hoặc trang bị lặp; giữ dữ liệu cũ.")
                seen.add(str(card_id))
                results.append({"card_id": str(card_id), "card_name": str(row.get("remark") or ""),
                    "last4": _mask_card_number(row.get("card_number", row.get("cardNumber"))),
                    "currency": str(currency), "status": str(status),
                    "spending_limit": None, "available_balance": None})
            if len(rows) < 100:
                return results
        raise PingPongError("Danh sách thẻ vượt giới hạn phân trang; không lưu dữ liệu chưa đầy đủ.")

    def get_usd_budget_balance(self) -> Decimal:
        """Lấy số dư khả dụng tổng quỹ USD Master Budget từ PingPong."""
        balances = self.funding_balances()
        for b in balances:
            if b.get("currency", "").upper() == "USD":
                val = b.get("available_balance", "0")
                try:
                    return Decimal(str(val))
                except (InvalidOperation, ValueError):
                    return Decimal("0")
        return Decimal("0")

    def get_active_cards(self) -> list[dict[str, Any]]:
        """Lấy danh sách các thẻ VCC đang hoạt động (ACTIVE), bóc tách 4 số cuối, remark và số dư khả dụng."""
        results = []
        seen = set()
        for page in range(1, 101):
            data = self._request("GET", CARDS_PATH, params={"start_page": page, "row": 100})
            rows = data.get("list") if isinstance(data, dict) else (data if isinstance(data, list) else None)
            if not isinstance(rows, list):
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                status = str(row.get("card_status", row.get("cardStatus", row.get("status", "")))).strip().upper()
                if status != "ACTIVE":
                    continue
                card_id = row.get("pp_card_id", row.get("ppCardId", row.get("card_id", row.get("id"))))
                if not card_id or str(card_id) in seen:
                    continue
                seen.add(str(card_id))

                raw_num = str(row.get("card_number", row.get("cardNumber", "")) or "")
                last_four = _mask_card_number(raw_num)
                if len(raw_num) >= 8 and "*" not in raw_num:
                    masked_num = f"{raw_num[:4]} **** **** {last_four}"
                elif raw_num:
                    masked_num = raw_num
                else:
                    masked_num = f"**** **** **** {last_four}"

                remark = str(row.get("remark") or row.get("alias") or row.get("card_name") or row.get("cardName") or "")
                currency = str(row.get("billing_currency", row.get("billingCurrency", row.get("currency", "USD")))).upper()

                # Tính toán available_balance và allocated_balance
                avail_val = row.get("available_balance", row.get("availableBalance", row.get("balance", row.get("spending_limit", 0))))
                try:
                    avail_bal = Decimal(str(avail_val if avail_val is not None else 0))
                except (InvalidOperation, ValueError):
                    avail_bal = Decimal("0")

                alloc_val = row.get("allocated_balance", row.get("allocatedBalance", row.get("spending_limit", avail_bal)))
                try:
                    alloc_bal = Decimal(str(alloc_val if alloc_val is not None else avail_bal))
                except (InvalidOperation, ValueError):
                    alloc_bal = avail_bal

                results.append({
                    "id": str(card_id),
                    "card_number_masked": masked_num,
                    "last_four": last_four,
                    "status": "ACTIVE",
                    "remark": remark,
                    "currency": currency,
                    "allocated_balance": alloc_bal,
                    "available_balance": avail_bal,
                })
            if len(rows) < 100:
                break
        return results

    def get_card_transactions(self, card_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Lấy lịch sử giao dịch/biến động số dư (Authorization / Clearing) cho một thẻ VCC cụ thể."""
        card_id_str = str(card_id).strip()
        try:
            data = self._request("GET", TRANSACTIONS_PATH, params={"card_id": card_id_str, "row": limit})
        except Exception:
            try:
                data = self._request("GET", CARD_TRANSACTIONS_PATH, params={"pp_card_id": card_id_str, "row": limit})
            except Exception:
                return []

        rows = data.get("list") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not isinstance(rows, list):
            return []

        results = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            txn_id = str(row.get("transaction_id") or row.get("txn_id") or row.get("id") or f"txn_{card_id_str}_{idx}")
            try:
                auth_amt = Decimal(str(row.get("auth_amount", row.get("amount", 0))))
            except (InvalidOperation, ValueError):
                auth_amt = Decimal("0")

            try:
                settle_amt = Decimal(str(row.get("settle_amount", row.get("settled_amount", auth_amt))))
            except (InvalidOperation, ValueError):
                settle_amt = auth_amt

            currency = str(row.get("currency") or row.get("billing_currency") or "USD").upper()
            merchant = str(row.get("merchant_name") or row.get("merchantName") or row.get("remark") or "FACEBOOK ADS")
            status = str(row.get("status") or "SETTLED").upper()
            txn_time = row.get("transaction_time") or row.get("transactionTime") or row.get("created_at")

            results.append({
                "id": txn_id,
                "card_id": card_id_str,
                "auth_amount": auth_amt,
                "settle_amount": settle_amt,
                "currency": currency,
                "merchant_name": merchant,
                "status": status,
                "transaction_time": str(txn_time) if txn_time else None,
            })
        return results
