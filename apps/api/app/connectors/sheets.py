"""Google Sheets API v4 connector — S6, chuẩn D-024/D-028.

Nguyên tắc bất biến:
- CHỈ ĐỌC: connector KHÔNG định nghĩa method ghi nào (values.update/batchUpdate
  vắng mặt chủ ý); test introspection chặn việc thêm method ghi.
- Spreadsheet ID + access token từ biến môi trường; không hardcode, không log token
  (repr không chứa secret).
- Chưa có token hoặc spreadsheet id → mode mock (fixture workbook), phục vụ kiểm thử S6.
- Live gọi REST chính thức Sheets API v4, GET only; access token do service account
  cấp (staging sẽ thiết lập khi chủ dự án cung cấp bảng hiện hành — Q-007/Q-009).
- Cấu trúc bảng đang vận hành là bất biến; module này không sửa/định dạng lại.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import quote

import httpx

SPREADSHEET_ID_ENV = "ADSOS_GOOGLE_SHEETS_SPREADSHEET_ID"
ACCESS_TOKEN_ENV = "ADSOS_GOOGLE_SHEETS_ACCESS_TOKEN"
SERVICE_ACCOUNT_FILE_ENV = "ADSOS_GOOGLE_SERVICE_ACCOUNT_FILE"
SERVICE_ACCOUNT_JSON_ENV = "ADSOS_GOOGLE_SERVICE_ACCOUNT_JSON"
GOOGLE_APP_CREDENTIALS_ENV = "GOOGLE_APPLICATION_CREDENTIALS"  # chuẩn Google (đường dẫn JSON)
SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"

_SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"

_SPREADSHEET_URL_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]{20,})")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")

_GRID_FIELDS = (
    "sheets.properties(title,sheetId,gridProperties(rowCount,columnCount)),"
    "properties(locale),"
    "sheets.data.startRow,sheets.data.startColumn,"
    "sheets.data.rowData.values(userEnteredValue,effectiveValue,formattedValue,"
    "effectiveFormat.numberFormat,effectiveFormat.backgroundColor,"
    "effectiveFormat.backgroundColorStyle,note),"
    "sheets.merges"
)
_A_TO_L_SHEETS = frozenset({"pedri", "lock", "tommy", "hunter"})
_READ_COLUMN_LIMIT = 12


def _read_range(sheet_title: str) -> str:
    if sheet_title.strip().casefold() not in _A_TO_L_SHEETS:
        return sheet_title
    escaped_title = sheet_title.replace("'", "''")
    return f"'{escaped_title}'!A:L"


def _restricted_to_a_to_l(sheet_title: str) -> bool:
    return sheet_title.strip().casefold() in _A_TO_L_SHEETS


def service_account_configured() -> bool:
    """Đã cấu hình service account Google qua env chưa (KHÔNG đọc file tại đây — lazy)."""
    return bool(
        os.environ.get(SERVICE_ACCOUNT_FILE_ENV, "")
        or os.environ.get(SERVICE_ACCOUNT_JSON_ENV, "")
        or os.environ.get(GOOGLE_APP_CREDENTIALS_ENV, "")
    )


class _ServiceAccountTokenProvider:
    """Token bearer từ Google service account (google-auth) — tự làm mới khi hết hạn.

    Scope cố định `spreadsheets.readonly`; service account được share bảng với
    quyền Viewer. KHÔNG log nội dung credentials/token; key JSON nằm ngoài repo.
    """

    def __init__(self) -> None:
        self._credentials: Any = None
        self._last_config: tuple[str, str, str] | None = None
        self._lock = threading.Lock()

    def _current_config(self) -> tuple[str, str, str]:
        return (
            os.environ.get(SERVICE_ACCOUNT_FILE_ENV, ""),
            os.environ.get(SERVICE_ACCOUNT_JSON_ENV, ""),
            os.environ.get(GOOGLE_APP_CREDENTIALS_ENV, ""),
        )

    def _load(self) -> Any:
        from google.oauth2 import service_account

        scopes = [SHEETS_READONLY_SCOPE]
        file_path = os.environ.get(SERVICE_ACCOUNT_FILE_ENV, "")
        json_content = os.environ.get(SERVICE_ACCOUNT_JSON_ENV, "")
        gac_path = os.environ.get(GOOGLE_APP_CREDENTIALS_ENV, "")
        try:
            if file_path:
                return service_account.Credentials.from_service_account_file(file_path, scopes=scopes)
            if json_content:
                return service_account.Credentials.from_service_account_info(json.loads(json_content), scopes=scopes)
            if gac_path:
                return service_account.Credentials.from_service_account_file(gac_path, scopes=scopes)
        except Exception as exc:  # noqa: BLE001 — không lộ nội dung file key
            raise SheetsAuthError(
                f"Service account JSON không đọc được ({type(exc).__name__}) — kiểm tra env "
                f"{SERVICE_ACCOUNT_FILE_ENV}/{SERVICE_ACCOUNT_JSON_ENV} và quyền Viewer"
            ) from None
        raise SheetsAuthError("Chưa cấu hình service account Google qua biến môi trường")

    def bearer_token(self) -> str:
        with self._lock:
            # Env có thể đổi giữa các lần gọi (đổi key ngoài repo / test):
            # cấu hình khác cache cũ → bỏ credentials cache (không log nội dung).
            key = self._current_config()
            if self._credentials is not None and key != self._last_config:
                self._credentials = None
            if self._credentials is None:
                self._credentials = self._load()
                self._last_config = key
            if not self._credentials.valid:
                try:
                    from google.auth.transport.requests import Request

                    self._credentials.refresh(Request())
                except Exception as exc:  # noqa: BLE001 — không log chi tiết token
                    self._credentials = None
                    raise SheetsAuthError(
                        f"Làm mới token service account thất bại ({type(exc).__name__}) — kiểm tra quyền Viewer của service account trên bảng"
                    ) from None
            return str(self._credentials.token)


_SA_PROVIDER = _ServiceAccountTokenProvider()


def parse_spreadsheet_url(value: str) -> str:
    """Nhận Spreadsheet URL hoặc Spreadsheet ID → trả về Spreadsheet ID.

    Hỗ trợ:
    - https://docs.google.com/spreadsheets/d/<ID>/edit#gid=0
    - https://docs.google.com/spreadsheets/d/<ID>
    - Chuỗi ID trần (<ID>).
    """
    text = (value or "").strip()
    if not text:
        raise ValueError("Spreadsheet URL/ID trống")
    match = _SPREADSHEET_URL_RE.search(text)
    if match:
        return match.group(1)
    if _ID_RE.fullmatch(text):
        return text
    raise ValueError("Không đọc được Spreadsheet ID từ URL/ID đã nhập")


def _workbook_locale(payload: dict[str, Any]) -> Optional[str]:
    props = payload.get("properties") or {}
    return props.get("locale")


def _cell_color(cell: dict[str, Any]) -> Optional[dict[str, float]]:
    fmt = cell.get("effectiveFormat") or {}
    color = fmt.get("backgroundColor")
    if color is None:
        style = fmt.get("backgroundColorStyle") or {}
        color = style.get("rgbColor")
    if not isinstance(color, dict):
        return None
    return {k: float(color.get(k) or 0.0) for k in ("red", "green", "blue")}


def _cell_value(cell: dict[str, Any]) -> Any:
    effective = cell.get("effectiveValue") or {}
    for key in ("numberValue", "stringValue", "boolValue"):
        if key in effective:
            return effective[key]
    return None


class SheetsAPIError(Exception):
    """Lỗi từ Google Sheets API hoặc cấu hình connector."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SheetsAuthError(SheetsAPIError):
    """Token hết hạn / không đủ quyền — cần service account/reader mới, KHÔNG fallback mock."""


class GoogleSheetsConnector:
    """Đọc-only Google Sheets API v4. Dùng mock khi chưa có token/spreadsheet id (D-028)."""

    def __init__(
        self,
        spreadsheet_id: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: float = 30.0,
        deadline: Optional[float] = None,
        use_mock: Optional[bool] = None,
        mock_connector: Optional[MockSheetsConnector] = None,
    ) -> None:
        self._spreadsheet_id = spreadsheet_id or os.environ.get(SPREADSHEET_ID_ENV, "")
        self._access_token = access_token or os.environ.get(ACCESS_TOKEN_ENV, "")
        self._timeout = timeout
        self._deadline = deadline
        self._hidden_titles: set[str] = set()
        # use_mock=True: ép mock (test); use_mock=None: tự mock khi chưa đủ cấu hình (D-028)
        # Cấu hình đủ = spreadsheet id + (access token HOẶC service account google-auth)
        auth_available = bool(self._access_token) or service_account_configured()
        self._use_mock = not (self._spreadsheet_id and auth_available) if use_mock is None else use_mock
        if self._use_mock:
            self._mock = mock_connector or MockSheetsConnector()
        else:
            self._mock = None

    @property
    def mode(self) -> str:
        return "mock" if self._use_mock else "live"

    @property
    def auth_method(self) -> str:
        """Cách xác thực đang dùng: access_token | service_account | none (không lộ secret)."""
        if self._use_mock:
            return "none"
        return "access_token" if self._access_token else "service_account"

    @property
    def mock(self) -> Optional["MockSheetsConnector"]:
        return self._mock

    @property
    def spreadsheet_key(self) -> str:
        """Định danh workbook dùng cho mapping trong DB (live = spreadsheet id; mock = 'mock')."""
        return self._spreadsheet_id if not self._use_mock else "mock"

    def __repr__(self) -> str:  # phòng thủ: không bao giờ lộ token qua repr/log
        return f"GoogleSheetsConnector(mode={self.mode}, auth={self.auth_method})"

    def _bearer_token(self) -> str:
        """Token cho header Authorization: access token tĩnh hoặc service account (tự refresh)."""
        if self._access_token:
            return self._access_token
        return _SA_PROVIDER.bearer_token()

    # --- read-only surface (KHÔNG có method ghi — test introspection chặn thêm) ---

    def list_sheets(self) -> list[dict[str, Any]]:
        """Danh sách sheet: title, grid size. KHÔNG sửa workbook."""
        if self._use_mock:
            return self._mock.list_sheets()
        payload = self._api_get(
            f"/{self._spreadsheet_id}",
            {"fields": "sheets.properties(sheetId,title,hidden,gridProperties(rowCount,columnCount))"},
        )
        sheets = payload.get("sheets") or []
        result = []
        for sheet in sheets:
            props = (sheet.get("properties") or {})
            grid = props.get("gridProperties") or {}
            if props.get("title"):
                result.append(
                    {
                        "sheet_id": props.get("sheetId"),
                        "title": props["title"],
                        "grid_rows": grid.get("rowCount"),
                        "grid_columns": grid.get("columnCount"),
                        "hidden": bool(props.get("hidden", False)),
                    }
                )
        self._hidden_titles = {item["title"].casefold() for item in result if item["hidden"]}
        return result

    def read_grid(self, sheet_title: str) -> dict[str, Any]:
        """Đọc toàn bộ giá trị một sheet (GET values). KHÔNG sửa workbook."""
        if sheet_title.casefold() in self._hidden_titles:
            raise SheetsAPIError("Tab ẩn không được đọc dữ liệu", status_code=403)
        if self._use_mock:
            return self._mock.read_grid(sheet_title)
        read_range = _read_range(sheet_title)
        encoded_range = quote(read_range, safe="!:$'")
        payload = self._api_get(
            f"/{self._spreadsheet_id}/values/{encoded_range}",
            {},
        )
        rows = payload.get("values") or []
        if _restricted_to_a_to_l(sheet_title):
            rows = [row[:_READ_COLUMN_LIMIT] for row in rows]
        result = {"title": sheet_title, "rows": [list(row) for row in rows]}
        if _restricted_to_a_to_l(sheet_title):
            result["read_scope"] = "A:L"
        return result

    def read_sheet_detail(self, sheet_title: str) -> dict[str, Any]:
        """Đọc metadata chi tiết 1 sheet (GET spreadsheets.get, includeGridData).

        Trả về: giá trị ô + công thức + numberFormat + màu nền + note + vùng merge
        + locale workbook. CHỈ ĐỌC — dùng cho phân tích cấu trúc (D-028).
        """
        if sheet_title.casefold() in self._hidden_titles:
            raise SheetsAPIError("Tab ẩn không được đọc dữ liệu", status_code=403)
        if self._use_mock:
            return self._mock.read_sheet_detail(sheet_title)
        restricted = _restricted_to_a_to_l(sheet_title)
        payload = self._api_get(
            f"/{self._spreadsheet_id}",
            {
                "includeGridData": "true",
                "fields": _GRID_FIELDS,
                "ranges": _read_range(sheet_title),
            },
            parse_decimal_numbers=True,
        )
        sheets = payload.get("sheets") or []
        if not sheets:
            raise SheetsAPIError("Google Sheets API không trả dữ liệu sheet", status_code=404)
        sheet = sheets[0]
        props = sheet.get("properties") or {}
        grid = props.get("gridProperties") or {}
        data = (sheet.get("data") or [{}])[0]
        merges = [
            {
                "start_row": m.get("startRowIndex", 0),
                "end_row": m.get("endRowIndex", 0),
                "start_col": m.get("startColumnIndex", 0),
                "end_col": m.get("endColumnIndex", 0),
            }
            for m in (sheet.get("merges") or [])
            if not restricted
            or (
                m.get("startColumnIndex", 0) < _READ_COLUMN_LIMIT
                and m.get("endColumnIndex", 0) > 0
            )
        ]
        rows: list[list[Any]] = []
        cells: list[list[dict[str, Any]]] = []
        for row_data in data.get("rowData") or []:
            value_row: list[Any] = []
            cell_row: list[dict[str, Any]] = []
            row_cells = row_data.get("values") or []
            if restricted:
                available_columns = max(0, _READ_COLUMN_LIMIT - int(data.get("startColumn", 0)))
                row_cells = row_cells[:available_columns]
            for cell in row_cells:
                entered = cell.get("userEnteredValue") or {}
                nf = (cell.get("effectiveFormat") or {}).get("numberFormat") or {}
                cell_row.append(
                    {
                        "formula": entered.get("formulaValue"),
                        "nf_type": nf.get("type"),
                        "nf_pattern": nf.get("pattern"),
                        "bg": _cell_color(cell),
                        "note": cell.get("note"),
                        "formatted": cell.get("formattedValue"),
                    }
                )
                value_row.append(_cell_value(cell))
            cells.append(cell_row)
            rows.append(value_row)
        result = {
            "title": props.get("title", sheet_title),
            "locale": _workbook_locale(payload),
            "grid_rows": grid.get("rowCount"),
            "grid_columns": grid.get("columnCount"),
            "start_row": data.get("startRow", 0),
            "start_column": data.get("startColumn", 0),
            "rows": rows,
            "cells": cells,
            "merges": merges,
        }
        if restricted:
            result["read_scope"] = "A:L"
        return result

    def _api_get(
        self,
        path: str,
        params: dict[str, str],
        *,
        parse_decimal_numbers: bool = False,
    ) -> dict[str, Any]:
        url = f"{_SHEETS_API_BASE}{path}"
        headers = {"Authorization": f"Bearer {self._bearer_token()}"}
        remaining = self._deadline - time.monotonic() if self._deadline is not None else self._timeout
        if remaining <= 0:
            raise SheetsAPIError("Đã hết thời gian đọc báo cáo Sheets")
        try:
            response = httpx.get(url, params=params, headers=headers, timeout=min(self._timeout, remaining))
        except httpx.HTTPError as exc:
            raise SheetsAPIError(f"Google Sheets API không kết nối được: {type(exc).__name__}") from exc
        if response.status_code in (401, 403):
            raise SheetsAuthError(
                "Google Sheets API xác thực lỗi: token hết hạn hoặc service account thiếu quyền reader",
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise SheetsAPIError("Google Sheets API trả lỗi", status_code=response.status_code)
        try:
            return response.json(parse_float=Decimal) if parse_decimal_numbers else response.json()
        except ValueError as exc:
            raise SheetsAPIError("Google Sheets API trả body không hợp lệ") from exc


class MockSheetsConnector:
    """Workbook giả lập S6 (Q-007: cấu trúc thật chưa có). Chỉ phục vụ kiểm thử, không gọi mạng.

    Ô có thể là giá trị thường (str/int/float/None) hoặc dict giàu metadata:
    {"value": ..., "formula": "=SUM(A2:A5)", "nf": {"type": "CURRENCY", "pattern": "#,##0.00"},
     "bg": (r, g, b) 0..1, "note": "..."} — dùng để tái lập merged cells/công thức/
    định dạng số locale/màu phân cách trong kiểm thử cấu trúc bảng thật.
    """

    def __init__(
        self,
        workbook: Optional[dict[str, list[list[Any]]]] = None,
        locale: str = "vi_VN",
        merges: Optional[dict[str, list[dict[str, int]]]] = None,
    ) -> None:
        self.spreadsheet_key = "mock"
        self.locale = locale
        self._merges = {k: [dict(m) for m in v] for k, v in (merges or {}).items()}
        self._workbook = dict(workbook) if workbook else {k: [list(r) for r in v] for k, v in MOCK_WORKBOOK.items()}
        self.calls = {"list_sheets": 0, "read_grid": 0, "read_sheet_detail": 0}

    @property
    def mode(self) -> str:
        return "mock"

    def list_sheets(self) -> list[dict[str, Any]]:
        self.calls["list_sheets"] += 1
        return [
            {"sheet_id": index, "title": title, "grid_rows": len(rows), "grid_columns": max((len(r) for r in rows), default=0)}
            for index, (title, rows) in enumerate(sorted(self._workbook.items()))
        ]

    @staticmethod
    def _plain(value: Any) -> Any:
        if isinstance(value, dict):
            return value.get("value")
        return value

    def read_grid(self, sheet_title: str) -> dict[str, Any]:
        self.calls["read_grid"] += 1
        if sheet_title not in self._workbook:
            raise SheetsAPIError("mock: sheet không tồn tại", status_code=400)
        rows = self._workbook[sheet_title]
        return {"title": sheet_title, "rows": [[self._plain(cell) for cell in row] for row in rows]}

    def read_sheet_detail(self, sheet_title: str) -> dict[str, Any]:
        self.calls["read_sheet_detail"] += 1
        if sheet_title not in self._workbook:
            raise SheetsAPIError("mock: sheet không tồn tại", status_code=400)
        rows = self._workbook[sheet_title]
        width = max((len(r) for r in rows), default=0)
        value_rows: list[list[Any]] = []
        cell_rows: list[list[dict[str, Any]]] = []
        for row in rows:
            value_row: list[Any] = []
            cell_row: list[dict[str, Any]] = []
            for cell in row:
                if isinstance(cell, dict):
                    value = cell.get("value")
                    cell_row.append(
                        {
                            "formula": cell.get("formula"),
                            "nf_type": (cell.get("nf") or {}).get("type"),
                            "nf_pattern": (cell.get("nf") or {}).get("pattern"),
                            "bg": tuple(cell["bg"]) if cell.get("bg") else None,
                            "note": cell.get("note"),
                            "formatted": cell.get("formatted"),
                        }
                    )
                else:
                    value = cell
                    cell_row.append({"formula": None, "nf_type": None, "nf_pattern": None, "bg": None, "note": None, "formatted": None})
                value_row.append(value)
            while len(value_row) < width:
                value_row.append(None)
                cell_row.append({"formula": None, "nf_type": None, "nf_pattern": None, "bg": None, "note": None, "formatted": None})
            value_rows.append(value_row)
            cell_rows.append(cell_row)
        return {
            "title": sheet_title,
            "locale": self.locale,
            "grid_rows": len(rows),
            "grid_columns": width,
            "rows": value_rows,
            "cells": cell_rows,
            "merges": [dict(m) for m in self._merges.get(sheet_title, [])],
        }


# Fixture giả lập — NHÃN RÕ là mock, không phải cấu trúc bảng thật (Q-007 đang chờ).
MOCK_WORKBOOK: dict[str, list[list[Any]]] = {
    "Chi tiêu": [
        ["Ngày", "Mã campaign", "Chi tiêu (USD)", "Ad Account", "Ghi chú"],
        ["25/10/2026", "1025-KH Alpha", "1,234.56", "act_1", ""],
        ["25/10/2026", "1025-KH Beta", "888.11", "act_1", "đã đối soát"],
        ["26/10/2026", "2510-KH Alpha", "1.234,56", "act_2", None],
    ],
    "Công nợ": [
        ["Khách", "Nợ đầu kỳ", "Nạp", "Chi tiêu", "Nợ cuối kỳ"],
        ["KH Alpha", "5.000.000", "2,000,000", "1.500.000", "5.700.000"],
        ["KH Beta", " VND 2.500.000 ", "", "0", ""],
    ],
    "Khách hàng": [
        ["Tên khách", "Telegram", "Ghi chú"],
        ["KH Alpha", "@alpha_user", "phí 4%"],
        ["KH Beta", "@beta_user", ""],
    ],
    "Tỷ giá": [
        ["Ngày", "USDT/VND"],
        ["25/10/2026", "25,500"],
        ["26/10/2026", "25600"],
    ],
}


def build_connector(
    spreadsheet_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> GoogleSheetsConnector:
    """Factory chuẩn: cấu hình từ env/kho, không truyền tay rải rác."""
    return GoogleSheetsConnector(spreadsheet_id=spreadsheet_id, access_token=access_token)
