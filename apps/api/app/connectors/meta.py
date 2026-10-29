"""Meta Marketing API connector — chuẩn D-027.

Nguyên tắc bất biến:
- CHỈ ĐỌC: mọi method chỉ GET, không có mutation API nào được expose.
- Token lấy từ biến môi trường (`ADSOS_META_ACCESS_TOKEN` + `ADSOS_META_TOKEN_MAP`
  theo nguồn BM/ad account); KHÔNG hardcode, KHÔNG log/token vào output (repr được
  thiết kế để không chứa token).
- KHÔNG dùng cookie/token trích từ phiên Facebook, KHÔNG dùng cơ chế vượt quyền.
- Chưa có token → mode mock (dữ liệu giả lập), phục vụ kiểm thử S3.
- Trả lỗi chuẩn qua MetaAPIError; không chia mạng logic ngoài connector.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx

from app.core.config import settings as _settings

TOKEN_ENV = "ADSOS_META_ACCESS_TOKEN"
TOKEN_MAP_ENV = "ADSOS_META_TOKEN_MAP"


def _default_api_version() -> str:
    """Phiên bản Marketing API từ cấu hình (ADSOS_META_API_VERSION) — S16: v26.0 là mặc định."""
    return _settings.meta_api_version


class MetaAPIError(Exception):
    """Lỗi từ Meta Graph API hoặc cấu hình connector."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MetaAuthError(MetaAPIError):
    """Token hết hạn / không đủ quyền — cần chủ dự án cấp token mới, KHÔNG fallback mock."""


def load_token_map(raw: Optional[str] = None) -> dict[str, str]:
    """Đọc token map JSON: {"<bm_id|act_id>": "token"}. Lỗi parse → bỏ qua, không raise secrets."""
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
    """Đọc-only Meta Marketing API. Dùng mock khi không có token (D-027)."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        token_map: Optional[dict[str, str]] = None,
        api_version: Optional[str] = None,
        timeout: float = 30.0,
        use_mock: Optional[bool] = None,
        mock_connector: Optional[MockMetaConnector] = None,
    ) -> None:
        self.api_version = api_version or os.environ.get("ADSOS_META_API_VERSION", "") or _default_api_version()
        self._token_map: dict[str, str] = dict(token_map or load_token_map())
        self._default_token = access_token or os.environ.get(TOKEN_ENV, "")
        self._timeout = timeout
        # use_mock=True: ép mock (test); use_mock=None: tự mock khi chưa có token (D-027)
        self._use_mock = not (access_token or self._default_token or self._token_map) if use_mock is None else use_mock
        if self._use_mock:
            self._mock = mock_connector or MockMetaConnector()
        else:
            self._mock = None

    # --- token phân quyền theo nguồn (BM/ad account) ---

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
        return f"MetaAdsConnector(mode={self.mode})"

    # --- read-only endpoints ---

    def check_access(self) -> dict[str, Any]:
        """S16: kiểm tra token còn hiệu lực + quyền ads_read + account truy cập được.

        KHÔNG fallback mock (mock mode → lỗi rõ). Chỉ GET; không lộ token trong kết quả.
        """
        if self._use_mock:
            raise MetaAPIError("mock: chưa có token thật — kiểm tra LIVE cần token (env ADSOS_META_ACCESS_TOKEN / ADSOS_META_TOKEN_MAP)")
        accounts = self.get_ad_accounts()  # 401/403 → MetaAuthError; lỗi khác → MetaAPIError
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
        sources: list[Optional[str]] = bm_ids if bm_ids else [None]
        for bm_id in sources:
            token = self.token_for_source(bm_id)
            if not token:
                raise MetaAPIError(f"Không tìm thấy token cho nguồn {bm_id or 'default'}")
            path = f"act_{bm_id}/owned_ad_accounts" if bm_id else "me/adaccounts"
            page = self._graph_get(path, {"fields": fields, "access_token": token})
            for row in page:
                account_id = row.get("id") or (f"act_{row.get('account_id')}" if row.get("account_id") else None)
                if not account_id or account_id in seen:
                    continue
                seen.add(account_id)
                accounts.append(
                    {
                        "meta_ad_account_id": account_id,
                        "name": row.get("name") or account_id,
                        "business_manager_id": row.get("business") or bm_id,
                        "timezone_name": row.get("timezone_name") or "UTC",
                        "currency": row.get("currency") or "USD",
                    }
                )
            if not bm_ids:
                break
        return accounts

    def get_account_campaigns(self, meta_ad_account_id: str) -> list[dict[str, Any]]:
        """Danh sách campaign của account: chỉ read."""
        if self._use_mock:
            return self._mock.get_account_campaigns(meta_ad_account_id)
        token = self.token_for_source(meta_ad_account_id)
        if not token:
            raise MetaAPIError(f"Không tìm thấy token cho nguồn {meta_ad_account_id}")
        fields = "id,name,status,effective_status,objective,created_time"
        page = self._graph_get(
            f"{meta_ad_account_id}/campaigns",
            {"fields": fields, "limit": "500", "access_token": token},
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
        """Chi tiêu tích lũy của campaign. time_range bỏ trống = lifetime (total spend theo campaign)."""
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

    def _graph_get(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        url = f"https://graph.facebook.com/{self.api_version}/{path.lstrip('/')}"
        try:
            response = httpx.get(url, params=params, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise MetaAPIError(f"Meta Graph API không kết nối được: {type(exc).__name__}") from exc
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
            raise MetaAPIError("Meta Graph API trả lỗi")
        data = payload.get("data", [])
        return data if isinstance(data, list) else []


class MockMetaConnector:
    """Dữ liệu giả lập S3: 2 ad account (khác múi giờ), campaign nhận diện/UNRECOGNIZED,
    insights chi tiêu tích lũy. Chỉ phục vụ kiểm thử, không gọi mạng."""

    def __init__(self) -> None:
        self._insights = {row["meta_campaign_id"]: dict(row) for row in MOCK_INSIGHTS}
        self._insight_error: dict[str, bool] = {}
        self._accounts_error = False
        self._accounts_error_kind = "server"
        self._campaigns_error: set[str] = set()
        self.calls = {"accounts": 0, "campaigns": 0, "insights": 0}

    # -- điều khiển giả lập cho test --

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

    # -- read-only surface (trùng interface MetaAdsConnector) --

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
        return [dict(c) for c in campaigns]

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
            # Mã 4 số lưỡng nan (1102 = 02/11 MMDD = 11/02 DDMM) → UNRECOGNIZED (D-026)
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
