"""Meta Marketing API connector — chuẩn D-027 và mở rộng vận hành bền bỉ.

Nguyên tắc bất biến:
- Kiểm soát ghi (Controlled Write Path): Chỉ cho phép tạo campaign ở trạng thái PAUSED
  và đổi trạng thái (ACTIVE/PAUSED) có guardrail kiểm soát ngân sách.
- Token lấy từ biến môi trường (`ADSOS_META_ACCESS_TOKEN` + `ADSOS_META_TOKEN_MAP`),
  hỗ trợ Fernet decrypt nếu token đã được mã hóa.
- KHÔNG log token / appsecret_proof ra log/exception/repr (redaction tự động).
- Rate limit telemetry: Đọc các headers x-business-use-case-usage, x-ad-account-usage,
  x-app-usage để chủ động giảm tải khi tải vượt 80%.
- Tự động retry khi gặp lỗi tạm thời (5xx, network timeout) và mã rate limit (17, 80004, 613, 4).
- Hỗ trợ auto-pagination (paging.cursors.after) và Batch API.
- Mock mode phục vụ kiểm thử offline trọn vẹn, không gọi mạng thật.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Optional

import httpx

from app.core.meta_proof import with_appsecret_proof

from app.core.config import settings as _settings

logger = logging.getLogger(__name__)

TOKEN_ENV = "ADSOS_META_ACCESS_TOKEN"
TOKEN_MAP_ENV = "ADSOS_META_TOKEN_MAP"

RATE_LIMIT_ERROR_CODES = {4, 17, 613, 80004}
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

AD_ACCOUNT_STATUS_MAP: dict[int, str] = {
    1: "Hoạt động",
    2: "Bị vô hiệu hóa",
    3: "Chưa thanh toán / Nợ cước",
    7: "Đang xét duyệt rủi ro",
    8: "Chờ thanh toán",
    9: "Tạm dừng thanh toán",
    100: "Chờ đóng tài khoản",
    101: "Đã đóng",
}

DISABLE_REASON_MAP: dict[int, str] = {
    0: "Không có vi phạm",
    1: "Chính sách thanh toán không hợp lệ",
    2: "Vi phạm chính sách quảng cáo",
    3: "Hành vi tài khoản bất thường",
    4: "Vi phạm sở hữu trí tuệ",
    5: "Tài khoản kinh doanh bị hạn chế",
}


def _default_api_version() -> str:
    """Phiên bản Marketing API từ cấu hình (ADSOS_META_API_VERSION) — S16: v26.0 là mặc định."""
    return _settings.meta_api_version


def redact_sensitive(text: str) -> str:
    """Loại bỏ access_token và appsecret_proof khỏi chuỗi log/error."""
    if not text:
        return ""
    text = re.sub(r'(access_token=)[^&"\'\s]+', r'\1[REDACTED]', text)
    text = re.sub(r'(appsecret_proof=)[^&"\'\s]+', r'\1[REDACTED]', text)
    text = re.sub(r'("access_token"\s*:\s*")[^"]+(")', r'\1[REDACTED]\2', text)
    return text


def decrypt_token_if_encrypted(token: Optional[str]) -> Optional[str]:
    """Giải mã token nếu được lưu dưới dạng ciphertext Fernet (bắt đầu bằng gAAAAA)."""
    if not token or not token.startswith("gAAAAA"):
        return token
    master_key = _settings.exchange_master_key
    if not master_key:
        return token
    try:
        from cryptography.fernet import Fernet
        f = Fernet(master_key.encode("utf-8"))
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return token


def encrypt_meta_token(token: str) -> str:
    """Mã hóa token bằng Fernet master key."""
    master_key = _settings.exchange_master_key
    if not master_key:
        raise ValueError("Chưa cấu hình ADSOS_EXCHANGE_MASTER_KEY để mã hóa token")
    from cryptography.fernet import Fernet
    f = Fernet(master_key.encode("utf-8"))
    return f.encrypt(token.encode("utf-8")).decode("utf-8")


class MetaAPIError(Exception):
    """Lỗi từ Meta Graph API hoặc cấu hình connector."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, error_code: Optional[int] = None) -> None:
        sanitized = redact_sensitive(message)
        super().__init__(sanitized)
        self.status_code = status_code
        self.error_code = error_code


class MetaAuthError(MetaAPIError):
    """Token hết hạn / không đủ quyền — cần chủ dự án cấp token mới, KHÔNG fallback mock."""


class RateLimitTelemetry:
    """Thu thập thông số giới hạn cuộc gọi từ Meta response headers."""

    def __init__(self) -> None:
        self.business_use_case: dict[str, Any] = {}
        self.ad_account_usage: dict[str, Any] = {}
        self.app_usage: dict[str, Any] = {}
        self.max_util_pct: float = 0.0
        self.last_updated: Optional[float] = None

    def update_from_headers(self, headers: httpx.Headers) -> None:
        self.last_updated = time.time()
        # Header x-business-use-case-usage
        b_hdr = headers.get("x-business-use-case-usage")
        if b_hdr:
            try:
                self.business_use_case = json.loads(b_hdr)
                for _act, usages in self.business_use_case.items():
                    for u in usages:
                        self.max_util_pct = max(
                            self.max_util_pct,
                            float(u.get("call_count", 0)),
                            float(u.get("total_cputime", 0)),
                            float(u.get("total_time", 0)),
                        )
            except Exception:
                pass

        # Header x-ad-account-usage
        acc_hdr = headers.get("x-ad-account-usage")
        if acc_hdr:
            try:
                self.ad_account_usage = json.loads(acc_hdr)
                util = float(self.ad_account_usage.get("acc_id_util_pct", 0.0))
                self.max_util_pct = max(self.max_util_pct, util)
            except Exception:
                pass

        # Header x-app-usage
        app_hdr = headers.get("x-app-usage")
        if app_hdr:
            try:
                self.app_usage = json.loads(app_hdr)
                self.max_util_pct = max(
                    self.max_util_pct,
                    float(self.app_usage.get("call_count", 0)),
                    float(self.app_usage.get("total_cputime", 0)),
                    float(self.app_usage.get("total_time", 0)),
                )
            except Exception:
                pass

    @property
    def should_throttle(self) -> bool:
        return self.max_util_pct >= 80.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_util_pct": round(self.max_util_pct, 2),
            "should_throttle": self.should_throttle,
            "business_use_case": self.business_use_case,
            "ad_account_usage": self.ad_account_usage,
            "app_usage": self.app_usage,
            "last_updated": self.last_updated,
        }


def load_token_map(raw: Optional[str] = None) -> dict[str, str]:
    """Đọc token map JSON: {"<bm_id|act_id>": "token"}."""
    if raw is None:
        raw = os.environ.get(TOKEN_MAP_ENV, "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items() if v}


class MetaAdsConnector:
    """Meta Marketing API connector: tối ưu hoá throughput, batching, rate-limits & controlled write."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        token_map: Optional[dict[str, str]] = None,
        api_version: Optional[str] = None,
        timeout: float = 30.0,
        use_mock: Optional[bool] = None,
        mock_connector: Optional[MockMetaConnector] = None,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        discovery_tokens: Optional[list[str]] = None,
    ) -> None:
        self.api_version = api_version or os.environ.get("ADSOS_META_API_VERSION", "") or _default_api_version()
        raw_token_map = dict(token_map or load_token_map())
        self._token_map: dict[str, str] = {k: decrypt_token_if_encrypted(v) or v for k, v in raw_token_map.items()}
        raw_default = access_token or os.environ.get(TOKEN_ENV, "")
        self._default_token = decrypt_token_if_encrypted(raw_default) or ""
        # Token của từng VIA đã cấp quyền OAuth: mỗi token tự liệt kê /me/adaccounts của nó
        # (server không dùng env token như khi chạy local).
        self._discovery_tokens: list[str] = [t for t in dict.fromkeys(discovery_tokens or []) if t]
        self._timeout = timeout
        self._transport = transport
        self._client: Optional[httpx.Client] = client
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.telemetry = RateLimitTelemetry()

        # use_mock=True: ép mock (test); use_mock=None: tự mock khi chưa có token (D-027)
        has_token = bool(self._default_token or self._token_map or self._discovery_tokens)
        self._use_mock = not has_token if use_mock is None else use_mock
        if self._use_mock:
            self._mock = mock_connector or MockMetaConnector()
        else:
            self._mock = None

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                timeout=self._timeout,
                transport=self._transport,
                headers={"User-Agent": "AdsBusinessOS/2.0"},
            )
        return self._client

    def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            self._client.close()
            self._client = None

    def __enter__(self) -> "MetaAdsConnector":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def token_for_source(self, source_id: Optional[str]) -> Optional[str]:
        """Token cho một nguồn cụ thể (BM id hoặc act_id), fallback token mặc định."""
        if self._use_mock:
            return None
        if source_id is not None and source_id in self._token_map:
            return self._token_map[source_id]
        return self._default_token or next(iter(self._token_map.values()), None)

    @property
    def mode(self) -> str:
        return "mock" if self._use_mock else "live"

    @property
    def mock(self) -> Optional["MockMetaConnector"]:
        return self._mock

    def __repr__(self) -> str:  # phòng thủ: không bao giờ lộ token qua repr/log
        return f"MetaAdsConnector(mode={self.mode}, api_version={self.api_version})"

    # --- HTTP Helpers với retry & rate-limit handling ---

    def _execute_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Thực thi HTTP request có retry backoff và phân tích rate limit headers."""
        client = self._get_client()
        attempts = 0
        last_exc: Optional[Exception] = None

        while attempts < self.max_retries:
            attempts += 1
            if self.telemetry.should_throttle:
                logger.warning(
                    "Meta rate limit vượt ngưỡng 80%% (%s%%). Tạm dừng chủ động 500ms...",
                    self.telemetry.max_util_pct,
                )
                time.sleep(0.5)

            try:
                for key in ("params", "data"):
                    if isinstance(kwargs.get(key), dict):
                        kwargs[key] = with_appsecret_proof(kwargs[key])
                response = client.request(method, url, **kwargs)
                self.telemetry.update_from_headers(response.headers)

                # Kiểm tra HTTP status lỗi có thể retry
                if response.status_code in TRANSIENT_STATUS_CODES:
                    if attempts < self.max_retries:
                        time.sleep(self.retry_delay * attempts)
                        continue

                # Parse JSON nếu có lỗi rate limit từ body
                if response.status_code != 200:
                    try:
                        err_payload = response.json().get("error", {})
                        err_code = err_payload.get("code")
                        if err_code in RATE_LIMIT_ERROR_CODES and attempts < self.max_retries:
                            time.sleep(self.retry_delay * attempts * 2)
                            continue
                    except Exception:
                        pass

                return response

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempts < self.max_retries:
                    time.sleep(self.retry_delay * attempts)
                    continue
                raise MetaAPIError(f"Meta Graph API không kết nối được sau {attempts} lần thử: {type(exc).__name__}") from exc
            except httpx.HTTPError as exc:
                raise MetaAPIError(f"Meta Graph API gặp lỗi HTTP: {type(exc).__name__}") from exc

        if last_exc:
            raise MetaAPIError(f"Meta Graph API lỗi kết nối: {type(last_exc).__name__}") from last_exc
        raise MetaAPIError("Meta Graph API không thể hoàn thành yêu cầu")

    def _graph_get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """GET request chuẩn Meta Graph API, trả về mảng records trong payload['data']."""
        url = f"https://graph.facebook.com/{self.api_version}/{path.lstrip('/')}"
        response = self._execute_with_retry("GET", url, params=params)

        if response.status_code != 200:
            if response.status_code in (401, 403):
                raise MetaAuthError(
                    "Meta API xác thực lỗi: token hết hạn hoặc thiếu quyền ads_read",
                    status_code=response.status_code,
                )
            raise MetaAPIError("Meta Graph API trả lỗi", status_code=response.status_code)

        try:
            payload = response.json()
        except ValueError as exc:
            raise MetaAPIError("Meta Graph API trả body không hợp lệ") from exc

        if "error" in payload:
            err = payload["error"]
            raise MetaAPIError(
                err.get("message", "Meta Graph API trả lỗi"),
                status_code=response.status_code,
                error_code=err.get("code"),
            )

        data = payload.get("data", [])
        return data if isinstance(data, list) else []

    def _graph_get_object(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """GET request trả về đối tượng đơn (object)."""
        url = f"https://graph.facebook.com/{self.api_version}/{path.lstrip('/')}"
        response = self._execute_with_retry("GET", url, params=params)

        if response.status_code != 200:
            if response.status_code in (401, 403):
                raise MetaAuthError(
                    "Meta API xác thực lỗi: token hết hạn hoặc thiếu quyền",
                    status_code=response.status_code,
                )
            raise MetaAPIError("Meta Graph API trả lỗi", status_code=response.status_code)

        try:
            payload = response.json()
        except ValueError as exc:
            raise MetaAPIError("Meta Graph API trả body không hợp lệ") from exc

        if "error" in payload:
            err = payload["error"]
            raise MetaAPIError(
                err.get("message", "Meta Graph API trả lỗi"),
                status_code=response.status_code,
                error_code=err.get("code"),
            )
        return payload

    def _graph_get_paginated(
        self,
        path: str,
        params: dict[str, Any],
        limit_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """GET với auto-pagination bằng cursor `paging.cursors.after`."""
        all_records: list[dict[str, Any]] = []
        cur_params = dict(params)
        pages = 0

        while pages < limit_pages:
            pages += 1
            url = f"https://graph.facebook.com/{self.api_version}/{path.lstrip('/')}"
            response = self._execute_with_retry("GET", url, params=cur_params)
            if response.status_code != 200:
                break
            try:
                payload = response.json()
            except Exception:
                break

            data = payload.get("data", [])
            if isinstance(data, list):
                all_records.extend(data)

            # Kiểm tra cursor trang tiếp theo
            paging = payload.get("paging", {})
            cursors = paging.get("cursors", {})
            after_cursor = cursors.get("after")
            if not after_cursor or not data:
                break
            cur_params["after"] = after_cursor

        return all_records

    def _graph_post(self, path: str, payload: dict[str, Any], token: str) -> dict[str, Any]:
        """POST mutation có kiểm soát (Campaign, AdSet, Creative, Ad)."""
        if _settings.app_env == "staging" or not _settings.meta_writes_enabled:
            raise MetaAPIError("Ghi Meta thật chưa được bật hoặc môi trường chỉ đọc.")
        url = f"https://graph.facebook.com/{self.api_version}/{path.lstrip('/')}"
        data = dict(payload)
        data["access_token"] = token
        response = self._execute_with_retry("POST", url, data=data)

        if response.status_code not in (200, 201):
            if response.status_code in (401, 403):
                raise MetaAuthError(
                    "Meta API xác thực lỗi khi ghi: token hết hạn hoặc thiếu quyền ads_management",
                    status_code=response.status_code,
                )
            err_msg = "Meta Graph API POST trả lỗi"
            try:
                body = response.json()
                if "error" in body:
                    err_msg = body["error"].get("message", err_msg)
            except Exception:
                pass
            raise MetaAPIError(err_msg, status_code=response.status_code)

        try:
            return response.json()
        except ValueError as exc:
            raise MetaAPIError("Meta Graph API trả body JSON không hợp lệ sau khi ghi") from exc

    def batch_request(
        self,
        requests: list[dict[str, Any]],
        source_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Gửi nhiều truy vấn qua Graph Batch API trong 1 HTTP request duy nhất."""
        if any(str(request.get("method", "GET")).upper() != "GET" for request in requests):
            if _settings.app_env == "staging" or not _settings.meta_writes_enabled:
                raise MetaAPIError("Lô truy vấn chỉ được đọc khi chưa bật quyền ghi Meta.")
        if self._use_mock:
            return self._mock.batch_request(requests, source_id)

        token = self.token_for_source(source_id)
        if not token:
            raise MetaAPIError("Không có access token hợp lệ để thực thi Batch API")

        url = f"https://graph.facebook.com/{self.api_version}/"
        payload = {
            "access_token": token,
            "batch": json.dumps(requests),
        }
        response = self._execute_with_retry("POST", url, data=payload)
        if response.status_code != 200:
            raise MetaAPIError("Batch request không thành công", status_code=response.status_code)

        try:
            results = response.json()
        except ValueError as exc:
            raise MetaAPIError("Batch response JSON không hợp lệ") from exc

        parsed: list[dict[str, Any]] = []
        for item in results:
            code = item.get("code", 500)
            body_str = item.get("body", "{}")
            try:
                body_json = json.loads(body_str) if isinstance(body_str, str) else body_str
            except Exception:
                body_json = {"raw": body_str}
            parsed.append({"code": code, "body": body_json})

        return parsed

    # --- Read Methods ---

    def check_access(self) -> dict[str, Any]:
        """S16: kiểm tra token còn hiệu lực + quyền ads_read + account truy cập được."""
        if self._use_mock:
            raise MetaAPIError("mock: chưa có token thật — kiểm tra LIVE cần token (env ADSOS_META_ACCESS_TOKEN / ADSOS_META_TOKEN_MAP)")
        accounts = self.get_ad_accounts()
        return {
            "mode": self.mode,
            "api_version": self.api_version,
            "accounts_accessible": [
                {
                    "meta_ad_account_id": a["meta_ad_account_id"],
                    "name": a["name"],
                    "timezone_name": a["timezone_name"],
                    "currency": a["currency"],
                }
                for a in accounts
            ],
            "telemetry": self.telemetry.to_dict(),
        }

    def get_ad_accounts(self) -> list[dict[str, Any]]:
        """Danh sách ad account: meta_ad_account_id, name, business_manager_id, timezone_name, currency."""
        if self._use_mock:
            return self._mock.get_ad_accounts()
        return self._fetch_owned_accounts()

    def _fetch_owned_accounts(self) -> list[dict[str, Any]]:
        accounts: list[dict[str, Any]] = []
        seen: set[str] = set()
        fields = "id,account_id,name,timezone_name,currency,business"
        bm_ids = [k for k in self._token_map if not k.startswith("act_")]
        # (nguồn, token): BM trong token map → /{business_id}/owned_ad_accounts;
        # token VIA → /me/adaccounts của từng token; còn lại → /me/adaccounts token mặc định.
        sources: list[tuple[Optional[str], Optional[str]]]
        if bm_ids:
            sources = [(bm_id, self.token_for_source(bm_id)) for bm_id in bm_ids]
        elif self._discovery_tokens:
            sources = [(None, token) for token in self._discovery_tokens]
        else:
            sources = [(None, self.token_for_source(None))]
        for bm_id, token in sources:
            if not token:
                raise MetaAPIError(f"Không tìm thấy token cho nguồn {bm_id or 'default'}")
            # Graph API: /{business_id}/owned_ad_accounts (KHÔNG có tiền tố act_ cho BM).
            path = f"{bm_id}/owned_ad_accounts" if bm_id else "me/adaccounts"
            page = self._graph_get(path, {"fields": fields, "access_token": token})
            for row in page:
                account_id = row.get("id") or (f"act_{row.get('account_id')}" if row.get("account_id") else None)
                if not account_id or account_id in seen:
                    continue
                seen.add(account_id)
                # Gọi campaign/insights của account này bằng đúng token đã thấy nó.
                self._token_map.setdefault(account_id, token)
                accounts.append(
                    {
                        "meta_ad_account_id": account_id,
                        "name": row.get("name") or account_id,
                        "business_manager_id": row.get("business") or bm_id,
                        "timezone_name": row.get("timezone_name") or "UTC",
                        "currency": row.get("currency") or "USD",
                    }
                )
        return accounts

    def get_account_campaigns(self, meta_ad_account_id: str) -> list[dict[str, Any]]:
        """Danh sách campaign của account."""
        if self._use_mock:
            return self._mock.get_account_campaigns(meta_ad_account_id)
        token = self.token_for_source(meta_ad_account_id)
        if not token:
            raise MetaAPIError(f"Không tìm thấy token cho nguồn {meta_ad_account_id}")
        fields = "id,name,status,effective_status,objective,created_time"
        page = self._graph_get_paginated(
            f"{meta_ad_account_id}/campaigns",
            {"fields": fields, "limit": "500", "access_token": token},
            limit_pages=3,
        )
        return [
            {
                "meta_campaign_id": row.get("id"),
                "name": row.get("name") or "",
                "status": row.get("status") or "ACTIVE",
                "effective_status": row.get("effective_status") or [],
            }
            for row in page
            if row.get("id")
        ]

    def get_campaign_insights(
        self,
        meta_ad_account_id: str,
        meta_campaign_id: str,
        time_range: Optional[dict[str, str]] = None,
    ) -> Optional[dict[str, Any]]:
        """Chi tiêu tích lũy của campaign."""
        if self._use_mock:
            return self._mock.get_campaign_insights(meta_ad_account_id, meta_campaign_id, time_range)
        token = self.token_for_source(meta_ad_account_id)
        if not token:
            raise MetaAPIError(f"Không tìm thấy token cho nguồn {meta_ad_account_id}")
        params = {
            "fields": "campaign_id,spend,date_start,date_stop",
            "access_token": token,
        }
        if time_range is not None:
            params["time_range"] = json.dumps(time_range)
        page = self._graph_get(f"{meta_campaign_id}/insights", params)
        if not page:
            return None
        row = page[0]
        return {
            "meta_campaign_id": row.get("campaign_id") or meta_campaign_id,
            "spend": row.get("spend") or "0",
            "date_start": row.get("date_start"),
            "date_stop": row.get("date_stop"),
        }

    def get_ad_account_billing_health(self, meta_ad_account_id: str) -> dict[str, Any]:
        """Lấy thông tin sức khoẻ và thanh toán của tài khoản quảng cáo với nhãn Tiếng Việt."""
        if self._use_mock:
            return self._mock.get_ad_account_billing_health(meta_ad_account_id)

        token = self.token_for_source(meta_ad_account_id)
        if not token:
            raise MetaAPIError(f"Không tìm thấy token cho nguồn {meta_ad_account_id}")

        fields = "id,account_id,name,account_status,disable_reason,currency,amount_spent,balance,spend_cap,adspaymentcycle"
        path = meta_ad_account_id.lstrip("/")
        payload = self._graph_get_object(path, {"fields": fields, "access_token": token})

        status_code = int(payload.get("account_status", 1))
        disable_reason_code = int(payload.get("disable_reason", 0))

        # Meta trả amount_spent và balance theo đơn vị cent (tiền nhỏ nhất) tùy loại tiền tệ
        raw_spent = float(payload.get("amount_spent", 0)) / 100.0
        raw_balance = float(payload.get("balance", 0)) / 100.0
        spend_cap_val = payload.get("spend_cap")
        spend_cap = float(spend_cap_val) / 100.0 if spend_cap_val else None

        threshold_data = payload.get("adspaymentcycle", {})
        threshold_amount = None
        if isinstance(threshold_data, dict) and "data" in threshold_data:
            cycles = threshold_data["data"]
            if cycles and isinstance(cycles, list):
                threshold_amount = float(cycles[0].get("threshold_amount", 0)) / 100.0

        return {
            "meta_ad_account_id": payload.get("id") or meta_ad_account_id,
            "account_id": payload.get("account_id") or meta_ad_account_id.replace("act_", ""),
            "name": payload.get("name") or meta_ad_account_id,
            "account_status": status_code,
            "account_status_label": AD_ACCOUNT_STATUS_MAP.get(status_code, "Không xác định"),
            "disable_reason": disable_reason_code,
            "disable_reason_label": DISABLE_REASON_MAP.get(disable_reason_code, "Khác"),
            "currency": payload.get("currency", "USD"),
            "amount_spent": round(raw_spent, 2),
            "balance": round(raw_balance, 2),
            "spend_cap": round(spend_cap, 2) if spend_cap is not None else None,
            "billing_threshold": round(threshold_amount, 2) if threshold_amount is not None else None,
        }

    def get_performance_insights(
        self,
        meta_ad_account_id: str,
        date_preset: str = "today",
        time_range: Optional[dict[str, str]] = None,
    ) -> list[dict[str, Any]]:
        """Lấy báo cáo hiệu suất (spend, impressions, clicks, cpc, cpm...) theo preset hoặc time_range."""
        if self._use_mock:
            return self._mock.get_performance_insights(meta_ad_account_id, date_preset, time_range)

        token = self.token_for_source(meta_ad_account_id)
        if not token:
            raise MetaAPIError(f"Không tìm thấy token cho nguồn {meta_ad_account_id}")

        fields = "campaign_id,campaign_name,spend,impressions,reach,clicks,cpc,cpm,ctr,actions"
        params: dict[str, Any] = {
            "fields": fields,
            "level": "campaign",
            "access_token": token,
        }
        if time_range:
            params["time_range"] = json.dumps(time_range)
        else:
            params["date_preset"] = date_preset

        raw_data = self._graph_get(f"{meta_ad_account_id}/insights", params)
        results: list[dict[str, Any]] = []

        for row in raw_data:
            # Rút gọn actions (ví dụ link_click, lead, messaging_conversation_started_7d)
            actions_list = row.get("actions", [])
            action_map: dict[str, int] = {}
            if isinstance(actions_list, list):
                for act in actions_list:
                    action_type = act.get("action_type")
                    if action_type:
                        action_map[action_type] = int(act.get("value", 0))

            results.append(
                {
                    "campaign_id": row.get("campaign_id"),
                    "campaign_name": row.get("campaign_name", ""),
                    "spend": float(row.get("spend", 0.0)),
                    "impressions": int(row.get("impressions", 0)),
                    "reach": int(row.get("reach", 0)),
                    "clicks": int(row.get("clicks", 0)),
                    "ctr": float(row.get("ctr", 0.0)),
                    "cpc": float(row.get("cpc", 0.0)),
                    "cpm": float(row.get("cpm", 0.0)),
                    "conversions": action_map.get("lead", 0) + action_map.get("purchase", 0),
                    "messages": action_map.get("onsite_conversion.messaging_conversation_started_7d", 0),
                }
            )

        return results

    # --- Controlled Write Methods ---

    def create_campaign(self, meta_ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Tạo Campaign mới trên Meta Graph API."""
        if self._use_mock:
            return self._mock.create_campaign(meta_ad_account_id, payload)
        token = self.token_for_source(meta_ad_account_id)
        if not token:
            raise MetaAPIError(f"Không tìm thấy token cho {meta_ad_account_id}")
        return self._graph_post(f"{meta_ad_account_id}/campaigns", payload, token)

    def create_adset(self, meta_ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Tạo AdSet mới trên Meta Graph API."""
        if self._use_mock:
            return self._mock.create_adset(meta_ad_account_id, payload)
        token = self.token_for_source(meta_ad_account_id)
        if not token:
            raise MetaAPIError(f"Không tìm thấy token cho {meta_ad_account_id}")
        return self._graph_post(f"{meta_ad_account_id}/adsets", payload, token)

    def create_adcreative(self, meta_ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Tạo AdCreative mới trên Meta Graph API."""
        if self._use_mock:
            return self._mock.create_adcreative(meta_ad_account_id, payload)
        token = self.token_for_source(meta_ad_account_id)
        if not token:
            raise MetaAPIError(f"Không tìm thấy token cho {meta_ad_account_id}")
        return self._graph_post(f"{meta_ad_account_id}/adcreatives", payload, token)

    def create_ad(self, meta_ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Tạo Ad mới trên Meta Graph API."""
        if self._use_mock:
            return self._mock.create_ad(meta_ad_account_id, payload)
        token = self.token_for_source(meta_ad_account_id)
        if not token:
            raise MetaAPIError(f"Không tìm thấy token cho {meta_ad_account_id}")
        return self._graph_post(f"{meta_ad_account_id}/ads", payload, token)

    def update_campaign_status(self, meta_campaign_id: str, status: str) -> dict[str, Any]:
        """Cập nhật trạng thái chiến dịch (ACTIVE / PAUSED)."""
        if self._use_mock:
            return self._mock.update_campaign_status(meta_campaign_id, status)
        token = self.token_for_source(meta_campaign_id)
        if not token:
            raise MetaAPIError(f"Không tìm thấy token cho {meta_campaign_id}")
        return self._graph_post(meta_campaign_id, {"status": status}, token)


class MockMetaConnector:
    """Dữ liệu giả lập S3 & Write Simulation cho kiểm thử offline toàn diện."""

    def __init__(self) -> None:
        self._insights = {row["meta_campaign_id"]: dict(row) for row in MOCK_INSIGHTS}
        self._insight_error: dict[str, bool] = {}
        self._accounts_error = False
        self._accounts_error_kind = "server"
        self._campaigns_error: set[str] = set()
        self.calls = {"accounts": 0, "campaigns": 0, "insights": 0, "writes": 0}
        self.created_campaigns: list[dict[str, Any]] = []
        self.created_adsets: list[dict[str, Any]] = []
        self.created_adcreatives: list[dict[str, Any]] = []
        self.created_ads: list[dict[str, Any]] = []
        self.campaign_statuses: dict[str, str] = {}

    def set_insight_spend(self, meta_campaign_id: str, spend: float) -> None:
        row = self._insights[meta_campaign_id]
        row["spend"] = str(spend)

    def rename_campaign(self, meta_campaign_id: str, new_name: str) -> None:
        for campaigns in MOCK_CAMPAIGNS.values():
            for c in campaigns:
                if c["meta_campaign_id"] == meta_campaign_id:
                    c["name"] = new_name

    def fail_insights(self, meta_campaign_id: str) -> None:
        self._insight_error[meta_campaign_id] = True

    def fail_accounts(self) -> None:
        self._accounts_error = True

    def fail_accounts_auth(self) -> None:
        self._accounts_error = True
        self._accounts_error_kind = "auth"

    def fail_campaigns(self, meta_ad_account_id: str) -> None:
        self._campaigns_error.add(meta_ad_account_id)

    # -- Read Surface --

    def get_ad_accounts(self) -> list[dict[str, Any]]:
        if self._accounts_error:
            if self._accounts_error_kind == "auth":
                raise MetaAuthError("mock: token hết hạn/thiếu quyền", status_code=401)
            raise MetaAPIError("mock: accounts API lỗi", status_code=500)
        self.calls["accounts"] += 1
        return [dict(acc) for acc in MOCK_ACCOUNTS]

    def get_account_campaigns(self, meta_ad_account_id: str) -> list[dict[str, Any]]:
        if meta_ad_account_id in self._campaigns_error:
            raise MetaAPIError("mock: campaigns API lỗi", status_code=500)
        self.calls["campaigns"] += 1
        campaigns = MOCK_CAMPAIGNS.get(meta_ad_account_id, [])
        res = []
        for c in campaigns:
            item = dict(c)
            # Nếu có trạng thái cập nhật gần đây
            if item["meta_campaign_id"] in self.campaign_statuses:
                item["status"] = self.campaign_statuses[item["meta_campaign_id"]]
            res.append(item)
        return res

    def get_campaign_insights(
        self,
        meta_ad_account_id: str,
        meta_campaign_id: str,
        time_range: Optional[dict[str, str]] = None,
    ) -> Optional[dict[str, Any]]:
        if self._insight_error.get(meta_campaign_id):
            raise MetaAPIError("mock: insights API lỗi", status_code=500)
        self.calls["insights"] += 1
        row = self._insights.get(meta_campaign_id)
        if row is None:
            return None
        return dict(row)

    def get_ad_account_billing_health(self, meta_ad_account_id: str) -> dict[str, Any]:
        return {
            "meta_ad_account_id": meta_ad_account_id,
            "account_id": meta_ad_account_id.replace("act_", ""),
            "name": f"Mock Account {meta_ad_account_id}",
            "account_status": 1,
            "account_status_label": "Hoạt động",
            "disable_reason": 0,
            "disable_reason_label": "Không có vi phạm",
            "currency": "VND",
            "amount_spent": 1250000.0,
            "balance": 250000.0,
            "spend_cap": 50000000.0,
            "billing_threshold": 5000000.0,
        }

    def get_performance_insights(
        self,
        meta_ad_account_id: str,
        date_preset: str = "today",
        time_range: Optional[dict[str, str]] = None,
    ) -> list[dict[str, Any]]:
        return [
            {
                "campaign_id": "cmp_1001",
                "campaign_name": "Chiến dịch Mock 1",
                "spend": 350000.0,
                "impressions": 12450,
                "reach": 9800,
                "clicks": 420,
                "ctr": 3.37,
                "cpc": 833.33,
                "cpm": 28112.45,
                "conversions": 18,
                "messages": 24,
            }
        ]

    # -- Write Surface --

    def create_campaign(self, meta_ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls["writes"] += 1
        cid = f"cmp_mock_{len(self.created_campaigns) + 5001}"
        record = {"id": cid, "meta_ad_account_id": meta_ad_account_id, **payload}
        self.created_campaigns.append(record)
        return {"id": cid, "success": True}

    def create_adset(self, meta_ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls["writes"] += 1
        asid = f"adset_mock_{len(self.created_adsets) + 6001}"
        record = {"id": asid, "meta_ad_account_id": meta_ad_account_id, **payload}
        self.created_adsets.append(record)
        return {"id": asid, "success": True}

    def create_adcreative(self, meta_ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls["writes"] += 1
        crid = f"creative_mock_{len(self.created_adcreatives) + 7001}"
        record = {"id": crid, "meta_ad_account_id": meta_ad_account_id, **payload}
        self.created_adcreatives.append(record)
        return {"id": crid, "success": True}

    def create_ad(self, meta_ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls["writes"] += 1
        adid = f"ad_mock_{len(self.created_ads) + 8001}"
        record = {"id": adid, "meta_ad_account_id": meta_ad_account_id, **payload}
        self.created_ads.append(record)
        return {"id": adid, "success": True}

    def update_campaign_status(self, meta_campaign_id: str, status: str) -> dict[str, Any]:
        self.calls["writes"] += 1
        self.campaign_statuses[meta_campaign_id] = status
        return {"id": meta_campaign_id, "success": True, "status": status}

    def batch_request(
        self,
        requests: list[dict[str, Any]],
        source_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        self.calls["writes"] += 1
        return [{"code": 200, "body": {"id": f"batch_mock_{i}", "success": True}} for i, _ in enumerate(requests)]


MOCK_ACCOUNTS: list[dict[str, Any]] = [
    {
        "meta_ad_account_id": "act_mock_1",
        "name": "BM-A / account 1",
        "business_manager_id": "bm_mock_a",
        "timezone_name": "Asia/Ho_Chi_Minh",
        "currency": "USD",
    },
    {
        "meta_ad_account_id": "act_mock_2",
        "name": "BM-B / account 2",
        "business_manager_id": "bm_mock_b",
        "timezone_name": "America/Los_Angeles",
        "currency": "USD",
    },
]

MOCK_CAMPAIGNS: dict[str, list[dict[str, Any]]] = {
    "act_mock_1": [
        {
            "meta_campaign_id": "cmp_1001",
            "name": "KH Alpha 1025",
            "status": "ACTIVE",
            "effective_status": ["ACTIVE"],
        },
        {
            "meta_campaign_id": "cmp_1002",
            "name": "KH Beta 2510",
            "status": "ACTIVE",
            "effective_status": ["ACTIVE"],
        },
        {
            "meta_campaign_id": "cmp_1003",
            "name": "KH Alpha 1102",
            "status": "ACTIVE",
            "effective_status": ["ACTIVE"],
        },
        {
            "meta_campaign_id": "cmp_1004",
            "name": "KH Alpha 1025 retired",
            "status": "PAUSED",
            "effective_status": ["PAUSED"],
        },
    ],
    "act_mock_2": [
        {
            "meta_campaign_id": "cmp_2001",
            "name": "KH Gamma 1026",
            "status": "ENDED",
            "effective_status": ["CAMPAIGN_ENDED"],
        },
    ],
}

MOCK_INSIGHTS: list[dict[str, Any]] = [
    {"meta_campaign_id": "cmp_1001", "spend": "1234.56", "date_start": "2026-10-01", "date_stop": "2026-10-26"},
    {"meta_campaign_id": "cmp_1002", "spend": "888.11", "date_start": "2026-10-01", "date_stop": "2026-10-26"},
    {"meta_campaign_id": "cmp_1003", "spend": "50.00", "date_start": "2026-10-01", "date_stop": "2026-10-26"},
    {"meta_campaign_id": "cmp_1004", "spend": "1400.00", "date_start": "2026-10-01", "date_stop": "2026-10-26"},
    {"meta_campaign_id": "cmp_2001", "spend": "990.90", "date_start": "2026-10-01", "date_stop": "2026-10-26"},
]


def build_connector(access_token: Optional[str] = None, token_map: Optional[dict[str, str]] = None) -> MetaAdsConnector:
    """Factory chuẩn: mọi caller đi qua đây để token luôn lấy từ env/kho, không truyền tay rải rác."""
    return MetaAdsConnector(access_token=access_token, token_map=token_map)
