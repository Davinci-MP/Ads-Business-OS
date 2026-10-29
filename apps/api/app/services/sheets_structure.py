"""Phân tích cấu trúc Google Sheets + mapping đề xuất (S6, D-024/D-028).

Chỉ ĐỌC và PHÂN TÍCH: không có đường ghi nào tới Google Sheets.
- `analyze_workbook`: cấu trúc từng sheet (header, cột, kiểu dữ liệu, tỉ lệ đầy).
- `normalize_cell`: chuẩn hoá ô (rỗng, khoảng trắng, phân cách nghìn/thập phân
  "1,234.56" hoặc "1.234,56", tiền tố/tiền tố đơn vị tiền) — quy tắc parse dữ liệu,
  KHÔNG phải công thức tài chính.
- `propose_mapping`: mapping sheet/cột → vai trò đối soát (PROPOSED) dựa trên từ
  khoá header. Chỉ là đề xuất — cấu trúc thật của bảng đang vận hành chờ chủ dự án
  cung cấp (Q-007); CONFIRMED chỉ khi chủ dự án xác nhận.
- Lưu mapping vào bảng `sheet_mappings` (unique `(spreadsheet_key, sheet_name,
  column_index)` — idempotent); dòng đã CONFIRMED không bị đè.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import utcnow
from app.models.finance import AuditLog
from app.models.sheets import MAPPING_CONFIRMED, MAPPING_PROPOSED, SheetMapping

ROLE_DATE = "DATE"
ROLE_CAMPAIGN = "CAMPAIGN"
ROLE_SPEND = "SPEND"
ROLE_ACCOUNT = "ACCOUNT"
ROLE_CUSTOMER = "CUSTOMER"
ROLE_TELEGRAM = "TELEGRAM"
ROLE_NOTE = "NOTE"
ROLE_DEBT = "DEBT"
ROLE_DEPOSIT = "DEPOSIT"
ROLE_RATE = "RATE"
ROLE_FEE = "FEE"
ROLE_TOTAL = "TOTAL"

# Đích dự kiến cho màn hình preview mapping — chỉ là GỢI Ý hiển thị,
# không phải ràng buộc ghi; mọi ghi vào DB phải qua phê duyệt riêng.
ROLE_TARGETS: dict[str, dict[str, str]] = {
    ROLE_DATE: {"area": "kỳ báo cáo", "field": "ngày kỳ"},
    ROLE_CAMPAIGN: {"area": "campaigns", "field": "meta_campaign_id / name"},
    ROLE_SPEND: {"area": "spend_snapshots", "field": "spend_value (tổng tích lũy)"},
    ROLE_ACCOUNT: {"area": "ad_accounts", "field": "meta_ad_account_id"},
    ROLE_CUSTOMER: {"area": "customers", "field": "name"},
    ROLE_TELEGRAM: {"area": "customers", "field": "telegram_chat_id"},
    ROLE_RATE: {"area": "exchange_rates", "field": "rate (USDT/VND)"},
    ROLE_FEE: {"area": "ledger_entries", "field": "amount (khoản PHÍ DỊCH VỤ riêng — D-021)"},
    ROLE_TOTAL: {"area": "đối soát", "field": "tổng cộng (khoản riêng)"},
    ROLE_DEBT: {"area": "ledger_entries", "field": "amount (khoản CÔNG NỢ riêng)"},
    ROLE_DEPOSIT: {"area": "ledger_entries", "field": "amount (khoản NẠP riêng)"},
    ROLE_NOTE: {"area": "ghi chú", "field": "note"},
}

# Từ khoá header → vai trò. Thứ tự quan trọng: cụm dài/trùng khớp rõ trước.
_HEADER_ROLE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("chi tiêu", "spend", "tổng chi"), ROLE_SPEND),
    (("tỷ giá", "usdt/vnd", "ty gia", "rate"), ROLE_RATE),
    (("tổng cộng", "tổng nợ", "tổng", "thành tiền", "grand total", "total"), ROLE_TOTAL),
    (("phí", "phi", "fee"), ROLE_FEE),
    (("công nợ", "nợ", "debt", "du nợ", "dư nợ"), ROLE_DEBT),
    (("nạp", "deposit", "nap tien"), ROLE_DEPOSIT),
    (("mã campaign", "ma campaign", "campaign"), ROLE_CAMPAIGN),
    (("id tài khoản", "tai khoan", "id account", "account id", "ad account", "account"), ROLE_ACCOUNT),
    (("telegram",), ROLE_TELEGRAM),
    (("khách", "khach hang", "customer"), ROLE_CUSTOMER),
    (("ngày", "ngay", "date"), ROLE_DATE),
    (("ghi chú", "ghi chu", "note"), ROLE_NOTE),
]

_MAX_HEADER_SCAN_ROWS = 10

# Phân loại tab đặc biệt (Q-007, quyết định chủ dự án 2026-10-27):
# SUMMARY = bảng tổng hợp (chỉ đọc + đối chiếu); TEMPLATE = bảng mẫu
# (KHÔNG phải khách hoạt động); UNCLASSIFIED = chưa phân loại
# (KHÔNG tự đồng bộ); CUSTOMER = tab khách (tình trạng hoạt động vẫn cần xác nhận).
SHEET_SUMMARY = "SUMMARY"
SHEET_TEMPLATE = "TEMPLATE"
SHEET_UNCLASSIFIED = "UNCLASSIFIED"
SHEET_CUSTOMER = "CUSTOMER"
_SPECIAL_TABS_UNCLASSIFIED = ("all", "old")
DEFAULT_FEE_RATE = 0.04


def classify_sheet(title: Optional[str]) -> str:
    """Phân loại tab: TỔNG* → SUMMARY; MẪU* → TEMPLATE; ALL/OLD → UNCLASSIFIED; còn lại CUSTOMER."""
    lowered = (title or "").strip().lower()
    if lowered.startswith("tổng") or lowered.startswith("tong "):
        return SHEET_SUMMARY
    if lowered.startswith("mẫu") or lowered.startswith("mau "):
        return SHEET_TEMPLATE
    if lowered in _SPECIAL_TABS_UNCLASSIFIED:
        return SHEET_UNCLASSIFIED
    return SHEET_CUSTOMER


def fee_rate_from_formulas(formulas: list[str]) -> Optional[float]:
    """Bóc tỷ lệ phí từ công thức Sheets dạng `=F4*5%` / `=F4*0.05`. Trả về None nếu không thấy."""
    for formula in formulas:
        match = re.search(r"\*\s*(\d+(?:[.,]\d+)?)\s*%", formula)
        if match:
            return float(match.group(1).replace(",", ".")) / 100.0
        match = re.search(r"\*\s*0(\.\d+)?\b", formula)
        if match:
            return float(match.group(0)[1:])
    return None


def resolve_row_dates(detail: dict[str, Any], date_col: int = 0) -> dict[int, dict[str, Any]]:
    """Gán ngày báo cáo cho từng dòng và ngày tại cột date_col (cột A).

    Ngày được merge qua nhiều dòng → mọi dòng trong vùng merge cùng dùng giá trị
    góc trên-trái (`_merge_anchor`). Trả về {row_index: {"date", "value", "kind",
    "ambiguous"}} chỉ gồm dòng có ngày. KHÔNG tự sửa ngày trong bảng.
    """
    rows = detail.get("rows") or []
    merges = detail.get("merges") or []
    resolved: dict[int, dict[str, Any]] = {}
    for row_index in range(len(rows)):
        anchor_row, anchor_col = _merge_anchor(merges, row_index, date_col)
        if anchor_col != date_col or anchor_row >= len(rows):
            continue
        merged = None
        for m in merges:
            if int(m.get("start_row")) <= row_index < int(m.get("end_row")) and int(m.get("start_col")) <= date_col < int(m.get("end_col")):
                merged = m
                break
        raw = rows[anchor_row][date_col] if date_col < len(rows[anchor_row]) else None
        cell = normalize_cell(raw)
        if cell["kind"] in ("number", "date", "id"):
            resolved[row_index] = {
                "date_raw": cell["raw"],
                "value": cell["value"],
                "kind": cell["kind"],
                "ambiguous": bool(cell["ambiguous"]),
                # khoảng 1-indexed của khối ngày: từ dòng anchor tới cuối merge
                # (bảng thật: 1 ngày merge qua nhiều dòng account + dòng phân cách)
                "merge_span": (
                    [int(merged["start_row"]) + 1, int(merged["end_row"])]
                    if merged
                    else [row_index + 1, row_index + 1]
                ),
            }
    return resolved


def column_letter(index: int) -> str:
    """0 → A, 1 → B, ..., 25 → Z, 26 → AA."""
    letters = ""
    n = index + 1
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _cell_address(row_index: int, column_index: int) -> str:
    return f"{column_letter(column_index)}{row_index + 1}"


def build_cell_preview(detail: dict[str, Any]) -> dict[str, Any]:
    """Return read-only cell values with exact A1 references; preserve blanks and formulas."""
    rows = detail.get("rows") or []
    cells = detail.get("cells") or []
    row_offset = int(detail.get("start_row") or 0)
    column_offset = int(detail.get("start_column") or 0)
    width = max(
        (max(len(row), len(cells[index]) if index < len(cells) else 0) for index, row in enumerate(rows)),
        default=0,
    )
    preview_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        cell_row = cells[row_index] if row_index < len(cells) else []
        preview_cells: list[dict[str, Any]] = []
        has_content = False
        for column_index in range(width):
            value = row[column_index] if column_index < len(row) else None
            metadata = cell_row[column_index] if column_index < len(cell_row) else {}
            formula = metadata.get("formula")
            formatted = metadata.get("formatted")
            if value is not None or formula or formatted:
                has_content = True
            number_format = None
            if metadata.get("nf_type") or metadata.get("nf_pattern"):
                number_format = {
                    "type": metadata.get("nf_type"),
                    "pattern": metadata.get("nf_pattern"),
                }
            preview_cells.append(
                {
                    "address": _cell_address(row_index + row_offset, column_index + column_offset),
                    "value": value,
                    "formula": formula,
                    "formatted_value": formatted,
                    "number_format": number_format,
                    "note": metadata.get("note"),
                }
            )
        if has_content:
            preview_rows.append(
                {
                    "row_number": row_index + row_offset + 1,
                    "cells": preview_cells,
                }
            )

    return {
        "title": detail.get("title"),
        "locale": detail.get("locale"),
        "grid_rows": detail.get("grid_rows"),
        "grid_columns": detail.get("grid_columns"),
        "read_scope": detail.get("read_scope"),
        "merges": [
            {
                "range": (
                    f"{_cell_address(merge['start_row'], merge['start_col'])}:"
                    f"{_cell_address(merge['end_row'] - 1, merge['end_col'] - 1)}"
                ),
                **merge,
            }
            for merge in detail.get("merges", [])
        ],
        "rows": preview_rows,
    }


def _strip_currency(text: str) -> tuple[str, Optional[str]]:
    """Bóc token tiền tệ khỏi chuỗi số. Trả về (chuỗi_số, token_tiền_tệ)."""
    token = None
    for tok in ("VND", "USD", "USDT", "₫", "đ", "Đ", "$"):
        if tok in text:
            token = tok
            text = text.replace(tok, "")
    return text.strip(), token


def _parse_number_details(clean: str) -> tuple[Optional[float], bool]:
    """Parse số kiểu VN/quốc tế. Trả về (giá_trị, mơ_hồ).

    Heuristic (quy ước dữ liệu kế toán VN, cần xác minh với numberFormat bảng
    thật — Q-007; ô có numberValue từ Google Sheets thì KHÔNG dùng hàm này):
    - Có cả "," và "." → dấu sau cùng là thập phân, dấu còn lại là nhóm nghìn.
    - Chỉ một loại dấu, lặp lại ≥2 lần → nhóm nghìn, bỏ hết.
    - Chỉ một loại dấu, xuất hiện 1 lần + theo sau đúng 3 chữ số → NHÓM NGHÌN
      nhưng MƠ HỒ (có thể là thập phân) → ambiguous=True → NEEDS_CONFIRMATION.
    - Còn lại → dấu phân cách là thập phân, không mơ hồ.
    """
    comma = clean.count(",")
    dot = clean.count(".")
    ambiguous = False
    if comma and dot:
        decimal_sep = "," if clean.rfind(",") > clean.rfind(".") else "."
        thousand_sep = "." if decimal_sep == "," else ","
        clean = clean.replace(thousand_sep, "").replace(decimal_sep, ".")
    elif comma > 1 or dot > 1:
        clean = clean.replace(",", "").replace(".", "")
    else:
        sep = "," if comma else "."
        if comma or dot:
            head, _, tail = clean.partition(sep)
            if len(tail) == 3 and head.replace("-", "").isdigit():
                clean = clean.replace(",", "").replace(".", "")
                ambiguous = True
            else:
                clean = clean.replace(",", ".")
    try:
        return float(clean), ambiguous
    except ValueError:
        return None, False


def _parse_number(clean: str) -> Optional[float]:
    value, _ambiguous = _parse_number_details(clean)
    return value


_DATE_TEXT_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")
_ID_MIN_DIGITS = 13  # Meta ad account ~15-16 số, campaign ID ~19 số → không parse float


def _classify_text(cleaned: str) -> Optional[dict[str, Any]]:
    """Phân loại text thuần: số / ngày / ID dài. Trả None nếu là text thường."""
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)*", cleaned):
        digits_only = re.sub(r"[^\d]", "", cleaned)
        if cleaned.lstrip("+-").isdigit() and len(digits_only) >= _ID_MIN_DIGITS:
            return {"kind": "id", "value": cleaned, "ambiguous": False}
        value, ambiguous = _parse_number_details(cleaned)
        if value is not None:
            return {"kind": "number", "value": value, "ambiguous": ambiguous}
        return None
    date_match = _DATE_TEXT_RE.match(cleaned)
    if date_match:
        first, second = int(date_match.group(1)), int(date_match.group(2))
        if first > 12 and second <= 31:
            ambiguous = False  # chắc chắn thứ tự dd/MM (VN)
        elif second > 12 and first <= 31:
            ambiguous = False  # chắc chắn thứ tự MM/dd
        elif first == second:
            ambiguous = False
        else:
            ambiguous = True  # cả hai ≤12 → không phân định dd/MM vs MM/dd
        return {"kind": "date", "value": cleaned, "ambiguous": ambiguous}
    return None


def normalize_cell(raw: Any) -> dict[str, Any]:
    """Chuẩn hoá 1 ô: `kind` = empty | number | date | id | text; `value` tương ứng.

    - Số hỗ trợ kiểu en ("1,234.56") lẫn vn ("1.234,56") + token tiền tệ
      (VND/USD/USDT/$/₫/đ). "25,500" hiểu là nghìn grouping → 25500 nhưng MƠ HỒ
      (ambiguous=True) khi không có numberFormat — chờ xác nhận (Q-007).
    - Chuỗi chữ số dài (≥13) là ID tài khoản/campaign → giữ nguyên string (kind
      "id"), KHÔNG parse float (mất chính xác).
    - "25/10" là ngày; nếu cả 2 phần ≤12 (vd "11/02") → ambiguous=True chờ xác
      nhận thứ tự dd/MM vs MM/dd (đối xứng D-026).
    """
    if raw is None:
        return {"raw": None, "kind": "empty", "value": None, "ambiguous": False}
    if not isinstance(raw, str):
        if isinstance(raw, (int, float, Decimal)):
            return {"raw": raw, "kind": "number", "value": float(raw), "ambiguous": False}
        text = str(raw)
    else:
        text = raw
    cleaned = text.replace("\xa0", " ").strip()
    if not cleaned:
        return {"raw": raw, "kind": "empty", "value": None, "ambiguous": False}
    number_candidate, _token = _strip_currency(cleaned)
    classified = _classify_text(number_candidate) if number_candidate else None
    if classified:
        return {"raw": raw, "kind": classified["kind"], "value": classified["value"], "ambiguous": classified["ambiguous"]}
    return {"raw": raw, "kind": "text", "value": cleaned, "ambiguous": False}


def _slug_field(header: str) -> str:
    """Header → tên field ASCII snake_case: "Chi tiêu (USD)" → "chi_tieu_usd"."""
    decomposed = unicodedata.normalize("NFD", header)
    ascii_text = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    return slug or "cot"


def _role_for_header(header: str) -> Optional[str]:
    lowered = header.lower()
    for keywords, role in _HEADER_ROLE_RULES:
        if any(keyword in lowered for keyword in keywords):
            return role
    return None


def analyze_workbook(connector: Any) -> dict[str, Any]:
    """Phân tích cấu trúc toàn workbook (đọc mock/live). Không ghi gì."""
    sheets: list[dict[str, Any]] = []
    for meta in connector.list_sheets():
        if meta.get("hidden"):
            continue
        grid = connector.read_grid(meta["title"])
        analyzed = analyze_grid(grid)
        analyzed["sheet_id"] = meta["sheet_id"]
        analyzed["grid_rows"] = meta["grid_rows"]
        analyzed["grid_columns"] = meta["grid_columns"]
        sheets.append(analyzed)
    return {"spreadsheet_key": connector.spreadsheet_key, "mode": connector.mode, "sheets": sheets}


def analyze_grid(grid: dict[str, Any]) -> dict[str, Any]:
    """Phân tích 1 sheet từ kết quả `read_grid`."""
    rows = grid.get("rows") or []
    header_row_index: Optional[int] = None
    for index, row in enumerate(rows[:_MAX_HEADER_SCAN_ROWS]):
        if any(normalize_cell(cell)["kind"] != "empty" for cell in row):
            header_row_index = index
            break
    result: dict[str, Any] = {
        "title": grid.get("title"),
        "row_count": len(rows),
        "header_row_index": header_row_index,
        "columns": [],
        "notes": [],
    }
    if grid.get("read_scope"):
        result["notes"].append(
            f"Chỉ đọc phạm vi {grid['read_scope']}; các cột ngoài phạm vi chưa được phân tích."
        )
    if header_row_index is None:
        result["notes"].append("không tìm thấy hàng header trong 10 hàng đầu — cần chủ dự án xác nhận")
        return result
    header_row = rows[header_row_index]
    data_rows = rows[header_row_index + 1 :]
    width = max((len(row) for row in rows), default=0)
    for col in range(width):
        header_cell = normalize_cell(header_row[col]) if col < len(header_row) else {"kind": "empty", "value": None}
        if header_cell["kind"] == "empty":
            result["notes"].append(f"cột {column_letter(col)} không có header — bỏ qua")
            continue
        values = [normalize_cell(row[col]) for row in data_rows if col < len(row)]
        non_empty = [v for v in values if v["kind"] != "empty"]
        kinds = {v["kind"] for v in non_empty}
        kind_majority = next(iter(kinds)) if len(kinds) == 1 and kinds else ("mixed" if len(kinds) > 1 else None)
        result["columns"].append(
            {
                "column_index": col,
                "column_letter": column_letter(col),
                "header": str(header_cell["value"]),
                "kind_majority": kind_majority,
                "non_empty_ratio": round(len(non_empty) / len(values), 2) if values else 0.0,
                "samples": [v["value"] for v in non_empty[:3]],
            }
        )
    return result


# --- Phân tích chi tiết có metadata (merged/formula/numberFormat/màu/locale) ---


def _merge_mask(merges: list[dict[str, int]], row_count: int, col_count: int) -> set[tuple[int, int]]:
    """Tập ô bị merge che (không tính ô góc trên-trái giữ giá trị)."""
    covered: set[tuple[int, int]] = set()
    for merge in merges:
        r0, r1 = int(merge.get("start_row", 0)), int(merge.get("end_row", 0))
        c0, c1 = int(merge.get("start_col", 0)), int(merge.get("end_col", 0))
        for row in range(r0, min(r1, row_count)):
            for col in range(c0, min(c1, col_count)):
                if (row, col) != (r0, c0):
                    covered.add((row, col))
    return covered


def _merge_anchor(merges: list[dict[str, int]], row: int, col: int) -> tuple[int, int]:
    """Ô góc trên-trái của vùng merge chứa (row, col); trả chính nó nếu không bị che."""
    for merge in merges:
        r0, r1 = int(merge.get("start_row", 0)), int(merge.get("end_row", 0))
        c0, c1 = int(merge.get("start_col", 0)), int(merge.get("end_col", 0))
        if r0 <= row < r1 and c0 <= col < c1:
            return r0, c0
    return row, col


def _is_separator_color(bg: Any) -> bool:
    """Màu nền khác trắng/gần trắng → tô màu (tiêu đề nhóm / dòng phân cách).

    bg là dict {red,green,blue} (live) hoặc tuple (r,g,b) 0..1 (mock).
    """
    if bg is None:
        return False
    if isinstance(bg, dict):
        red, green, blue = bg.get("red", 1), bg.get("green", 1), bg.get("blue", 1)
    else:
        values = tuple(bg) + (1.0, 1.0, 1.0)
        red, green, blue = values[0], values[1], values[2]
    return not (red >= 0.97 and green >= 0.97 and blue >= 0.97)


def _currency_from_pattern(pattern: Optional[str]) -> Optional[str]:
    if not pattern:
        return None
    lowered = pattern.casefold()
    if "₫" in pattern or "đ" in lowered or "vnd" in lowered:
        return "VND"
    if "usd" in lowered or "us$" in lowered:
        return "USD"
    return None


def _nf_majority(entries: list[Optional[dict[str, Any]]]) -> Optional[dict[str, Any]]:
    """Định dạng numberFormat phổ biến trong cột (type + pattern + currency)."""
    counts: dict[tuple[str, str], int] = {}
    for entry in entries:
        if entry and entry.get("nf_type"):
            key = (str(entry["nf_type"]), str(entry.get("nf_pattern") or ""))
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    (nf_type, nf_pattern), _count = max(counts.items(), key=lambda kv: kv[1])
    return {"type": nf_type, "pattern": nf_pattern or None, "currency": _currency_from_pattern(nf_pattern)}


def analyze_sheet_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """Phân tích 1 sheet từ `read_sheet_detail` — có merge/màu/công thức/numberFormat.

    Nguyên tắc (D-028 + yêu cầu chủ dự án):
    - Ưu tiên numberValue chuẩn từ Google Sheets (không mơ hồ); text-số mới dùng heuristic.
    - numberFormat CURRENCY/DATE/NUMBER → format_source="number_format" (chắc chắn).
    - Text-số không có numberFormat, grouping đơn (1 dấu + đuôi 3 số) → MƠ HỒ →
      needs_confirmation=True (NEEDS_CONFIRMATION — Q-007).
    - Hàng phân cách màu + hàng banner: loại khỏi thống kê, ghi note.
    - Ô bị merge che: không tính vào thống kê cột.
    """
    rows = detail.get("rows") or []
    cells = detail.get("cells") or []
    merges = detail.get("merges") or []
    locale = detail.get("locale")
    notes: list[str] = []
    if detail.get("read_scope"):
        notes.append(
            f"Chỉ đọc phạm vi {detail['read_scope']}; các cột ngoài phạm vi chưa được phân tích."
        )
    if merges:
        notes.append(f"có {len(merges)} vùng merge — ô bị che không tính vào thống kê cột")
    covered = _merge_mask(merges, len(rows), max((len(row) for row in rows), default=0))

    separator_rows: set[int] = set()
    for row_index, row in enumerate(rows):
        cell_meta = cells[row_index] if row_index < len(cells) else []
        colored = any(_is_separator_color(meta.get("bg")) for meta in cell_meta)
        if not colored:
            continue
        non_empty = [
            col
            for col in range(len(row))
            if (row_index, col) not in covered and normalize_cell(row[col])["kind"] != "empty"
        ]
        if len(non_empty) <= 2:
            separator_rows.add(row_index)
            notes.append(f"dòng {row_index + 1}: hàng phân cách màu/tiêu đề nhóm — loại khỏi thống kê cột (xác nhận nếu sai)")

    def _row_info(row_index: int) -> tuple[list[int], list[str]]:
        """(cột non-empty không bị che, text thuần không phải số/ngày/ID)."""
        row = rows[row_index]
        cols = [
            col for col in range(len(row)) if (row_index, col) not in covered and normalize_cell(row[col])["kind"] != "empty"
        ]
        texts = [col for col in cols if normalize_cell(row[col])["kind"] == "text"]
        return cols, texts

    header_row_index: Optional[int] = None
    header_notes: list[int] = []
    for row_index in range(min(len(rows), _MAX_HEADER_SCAN_ROWS)):
        if row_index in separator_rows:
            continue
        cols, texts = _row_info(row_index)
        if len(texts) >= 3:
            header_row_index = row_index
            break
        if cols:
            header_notes.append(row_index)
    if header_row_index is None:
        # Fallback: hàng đầu tiên có ≥2 ô non-empty (không bị merge che).
        for row_index in header_notes:
            header_row_index = row_index
            notes.append("header fallback theo ô đầu tiên non-empty — xác nhận nếu sai (Q-007)")
            break
    if header_row_index is not None and header_row_index > 0:
        notes.append(f"header thực tế ở dòng {header_row_index + 1} (có summary/banner phía trên — KHÔNG phải tất cả tab đều giống)")

    formula_cells: list[str] = []
    for row_index, cell_row in enumerate(cells):
        for col, meta in enumerate(cell_row):
            if meta.get("formula"):
                formula_cells.append(f"{column_letter(col)}{row_index + 1}")
    if formula_cells:
        notes.append(
            f"có {len(formula_cells)} ô chứa công thức ({', '.join(formula_cells[:5])}"
            + ("…" if len(formula_cells) > 5 else "")
            + ") — đọc giá trị tính được (effectiveValue), KHÔNG sửa công thức"
        )

    result: dict[str, Any] = {
        "title": detail.get("title"),
        "sheet_type": classify_sheet(detail.get("title")),
        "row_count": len(rows),
        "header_row_index": header_row_index,
        "locale": locale,
        "merges": merges,
        "separator_rows": sorted(separator_rows),
        "formula_cells": formula_cells,
        "columns": [],
        "notes": notes,
    }
    if header_row_index is None:
        return result

    headers = rows[header_row_index]
    col_count = max((len(row) for row in rows), default=0)
    for col in range(col_count):
        anchor_row, anchor_col = _merge_anchor(merges, header_row_index, col)
        header_cell = normalize_cell(rows[anchor_row][anchor_col]) if anchor_col < len(rows[anchor_row]) else {"kind": "empty", "value": None}
        if header_cell["kind"] == "empty":
            notes.append(f"cột {column_letter(col)} không có header — bỏ qua, chờ chủ dự án xác nhận")
            continue

        number_entries: list[Optional[dict[str, Any]]] = []
        kinds: set[str] = set()
        samples: list[Any] = []
        samples_formatted: list[str] = []
        needs_confirmation = False
        confirm_reasons: set[str] = set()
        ambiguous_dates = 0
        ambiguous_numbers = 0
        non_empty = 0
        total = 0
        for row_index in range(header_row_index + 1, len(rows)):
            if row_index in separator_rows or (row_index, col) in covered:
                continue
            row = rows[row_index]
            if col >= len(row):
                total += 1
                continue
            meta = cells[row_index][col] if row_index < len(cells) and col < len(cells[row_index]) else {}
            value = row[col]
            nf_entry = (
                {"nf_type": meta.get("nf_type"), "nf_pattern": meta.get("nf_pattern")}
                if isinstance(meta, dict)
                else None
            )
            formatted = meta.get("formatted") if isinstance(meta, dict) else None
            total += 1
            if value is None and not (formatted or "").strip():
                continue
            non_empty += 1
            number_entries.append(nf_entry)
            if isinstance(value, (int, float, Decimal)):
                kinds.add("number")
            elif isinstance(value, str):
                stripped, _token = _strip_currency(value)
                classified = _classify_text(stripped) if stripped else None
                if classified:
                    kinds.add(classified["kind"])
                    if classified["kind"] == "date":
                        ambiguous_dates += classified["ambiguous"]
                    elif classified["kind"] == "number":
                        ambiguous_numbers += classified["ambiguous"]
                else:
                    kinds.add("text")
            else:
                kinds.add("text")
            if len(samples) < 3:
                samples.append(value)
                samples_formatted.append(str(formatted) if formatted else str(value))
            if nf_entry and nf_entry.get("nf_type"):
                pass

        kind_majority = next(iter(kinds)) if len(kinds) == 1 and kinds else ("mixed" if len(kinds) > 1 else None)
        number_format = _nf_majority(number_entries)
        has_nf = number_format is not None
        if ambiguous_numbers:
            needs_confirmation = True
            confirm_reasons.add("số dạng text, phân cách nghìn/thập phân mơ hồ — NEEDS_CONFIRMATION (Q-007)")
        if ambiguous_dates:
            needs_confirmation = True
            confirm_reasons.add(
                "ngày dạng text, không phân định được thứ tự dd/MM vs MM/dd (đối xứng D-026) — NEEDS_CONFIRMATION (Q-007)"
            )
        if kinds and not has_nf and "number" in kinds:
            notes.append(
                f"cột {column_letter(col)}: số dạng text KHÔNG có numberFormat — cần xác minh quy ước với chủ dự án (Q-007)"
            )
        if "mixed" in kinds or (len(kinds) > 1 and has_nf):
            notes.append(f"cột {column_letter(col)}: kiểu dữ liệu trộn lẫn ({', '.join(sorted(kinds))}) — kiểm tra thêm")

        result["columns"].append(
            {
                "column_index": col,
                "column_letter": column_letter(col),
                "header": str(header_cell["value"]),
                "field": _slug_field(str(header_cell["value"])),
                "kind_majority": kind_majority,
                "non_empty_ratio": round(non_empty / total, 2) if total else 0.0,
                "samples": samples,
                "samples_formatted": samples_formatted,
                "number_format": number_format,
                "format_source": "number_format" if has_nf else ("heuristic" if kinds else None),
                "has_formula": any(
                    (cells[r][col].get("formula") if r < len(cells) and col < len(cells[r]) else None)
                    for r in range(header_row_index + 1, len(rows))
                ),
                "merge_count": sum(1 for r in range(len(rows)) if (r, col) in covered),
                "needs_confirmation": needs_confirmation,
                "confirm_reasons": sorted(confirm_reasons),
            }
        )

    # Tỷ lệ phí theo công thức thực tế của cột Phí (Q-007 tiếp tục):
    # công thức Sheets là nguồn sự thật; nếu ≠ mặc định 4% (D-021) → NEEDS_CONFIRMATION
    # riêng — KHÔNG tự kích hoạt mức phí khác tự động.
    for entry in result["columns"]:
        lowered_header = str(entry["header"]).lower()
        if not any(token in lowered_header for token in ("phí", "phi", "fee")):
            continue
        col = entry["column_index"]
        formulas = [
            cells[r][col].get("formula")
            for r in range(header_row_index + 1, len(rows))
            if r < len(cells) and col < len(cells[r]) and cells[r][col].get("formula")
        ]
        rate = fee_rate_from_formulas(formulas)
        if rate is None:
            continue
        entry["fee_rate_from_formula"] = rate
        entry["fee_confirmed"] = abs(rate - DEFAULT_FEE_RATE) < 1e-9
        if not entry["fee_confirmed"]:
            entry["needs_confirmation"] = True
            percent = round(rate * 100, 2)
            entry["confirm_reasons"] = sorted(
                set(entry["confirm_reasons"]) | {
                    f"phí công thức Sheets {percent}% ≠ mặc định 4% (D-021) — cần xác nhận riêng trước khi kích hoạt (Q-007)"
                }
            )
    return result


def analyze_workbook_detailed(connector: Any) -> dict[str, Any]:
    """Phân tích workbook dùng metadata chi tiết (merged/formula/numberFormat/màu/locale)."""
    sheets: list[dict[str, Any]] = []
    for meta in connector.list_sheets():
        if meta.get("hidden"):
            continue
        detail = connector.read_sheet_detail(meta["title"])
        analyzed = analyze_sheet_detail(detail)
        analyzed["sheet_id"] = meta["sheet_id"]
        sheets.append(analyzed)
    return {"spreadsheet_key": connector.spreadsheet_key, "mode": connector.mode, "sheets": sheets}


def propose_mapping(structure: dict[str, Any]) -> list[dict[str, Any]]:
    """Từ cấu trúc đã phân tích → đề xuất mapping (PROPOSED). Chỉ đề xuất, không tự xác nhận.

    Mỗi dòng có `source` (ô nguồn: sheet/cột/header/samples/format) và `target`
    (đích dự kiến — chỉ là gợi ý hiển thị cho màn preview, không phải ghi thật).
    Tab TEMPLATE/UNCLASSIFIED KHÔNG sinh đề xuất tự đồng bộ (chờ chủ dự án phân
    loại — Q-007); tab SUMMARY chỉ để đối soát chỉ đọc.
    """
    proposals: list[dict[str, Any]] = []
    for sheet in structure.get("sheets", []):
        sheet_type = sheet.get("sheet_type") or classify_sheet(sheet.get("title"))
        if sheet_type in (SHEET_TEMPLATE, SHEET_UNCLASSIFIED, SHEET_SUMMARY):
            note_summary = (
                "bảng tổng hợp — chỉ đọc và đối soát, KHÔNG tự đồng bộ cột khách (Q-007)"
                if sheet_type == SHEET_SUMMARY
                else (
                    "tab đặc biệt (TEMPLATE/UNCLASSIFIED) — KHÔNG tự đồng bộ, "
                    "chờ chủ dự án phân loại (Q-007)"
                )
            )
            if not sheet.get("columns"):
                proposals.append(
                    {
                        "sheet_name": sheet["title"],
                        "sheet_type": sheet_type,
                        "column_index": -1,
                        "column_letter": "",
                        "header": None,
                        "role": None,
                        "field": None,
                        "confidence": "none",
                        "note": note_summary,
                        "source": {"sheet": sheet["title"], "needs_confirmation": True},
                        "target": None,
                    }
                )
                continue;
        for column in sheet.get("columns", []):
            header = column["header"]
            role = _role_for_header(header)
            needs_confirmation = bool(column.get("needs_confirmation"))
            target = ROLE_TARGETS.get(role) if role else None
            note_parts = []
            if not role:
                note_parts.append("chưa xác định vai trò — chờ chủ dự án (Q-007)")
            for reason in column.get("confirm_reasons", []):
                note_parts.append(reason)
            nf = column.get("number_format")
            nf_label = f'{nf["type"]}' + (f' {nf["pattern"]}' if nf.get("pattern") else "") if nf else None
            if nf and nf.get("currency"):
                nf_label = f'{nf_label} [{nf["currency"]}]'
            proposals.append(
                {
                    "sheet_name": sheet["title"],
                    "sheet_type": sheet_type,
                    "column_index": column["column_index"],
                    "column_letter": column["column_letter"],
                    "header": header,
                    "role": role,
                    "field": _slug_field(header),
                    "confidence": "high" if role and not needs_confirmation else ("low" if role else None),
                    "note": "; ".join(note_parts) if note_parts else None,
                    "source": {
                        "sheet": sheet["title"],
                        "column_letter": column["column_letter"],
                        "header": header,
                        "samples": column.get("samples", []),
                        "samples_formatted": column.get("samples_formatted", []),
                        "number_format": nf_label,
                        "format_source": column.get("format_source"),
                        "locale": sheet.get("locale"),
                        "merge_count": column.get("merge_count", 0),
                        "has_formula": column.get("has_formula", False),
                        "needs_confirmation": needs_confirmation,
                    },
                    "target": target,
                }
            )
    return proposals


def persist_proposals(
    db: Session,
    spreadsheet_key: str,
    proposals: list[dict[str, Any]],
    actor: str = "agent:sheets-s6",
) -> dict[str, int]:
    """Lưu đề xuất mapping (idempotent theo unique key). Dòng CONFIRMED không bị đè."""
    created = updated = unchanged = skipped_confirmed = 0
    for item in proposals:
        if item.get("column_index", -1) < 0 or not item.get("column_letter"):
            continue  # đề xuất tab đặc biệt — không lưu mapping cột
        existing = db.execute(
            select(SheetMapping).where(
                SheetMapping.spreadsheet_key == spreadsheet_key,
                SheetMapping.sheet_name == item["sheet_name"],
                SheetMapping.column_index == item["column_index"],
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                SheetMapping(
                    spreadsheet_key=spreadsheet_key,
                    sheet_name=item["sheet_name"],
                    column_index=item["column_index"],
                    column_letter=item["column_letter"],
                    header=item["header"],
                    role=item["role"],
                    field=item["field"],
                    status=MAPPING_PROPOSED,
                    note=item["note"],
                )
            )
            created += 1
        elif existing.status == MAPPING_CONFIRMED:
            skipped_confirmed += 1
        elif (
            existing.header == item["header"]
            and existing.role == item["role"]
            and existing.field == item["field"]
        ):
            unchanged += 1
        else:
            existing.column_letter = item["column_letter"]
            existing.header = item["header"]
            existing.role = item["role"]
            existing.field = item["field"]
            existing.note = item["note"]
            updated += 1
    db.add(
        AuditLog(
            actor=actor,
            action="SHEET_MAPPING_PROPOSED",
            entity_type="sheet_mapping",
            entity_id=spreadsheet_key,
            detail={"created": created, "updated": updated, "unchanged": unchanged, "skipped_confirmed": skipped_confirmed},
        )
    )
    db.commit()
    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "skipped_confirmed": skipped_confirmed,
    }


def confirm_sheet_mappings(db: Session, spreadsheet_key: str, sheet_name: str, actor: str) -> dict[str, Any]:
    """Chủ dự án xác nhận mapping của 1 sheet: PROPOSED → CONFIRMED (+ audit log)."""
    rows = db.execute(
        select(SheetMapping).where(
            SheetMapping.spreadsheet_key == spreadsheet_key,
            SheetMapping.sheet_name == sheet_name,
            SheetMapping.status == MAPPING_PROPOSED,
        )
    ).scalars().all()
    confirmed_at = utcnow()
    for row in rows:
        row.status = MAPPING_CONFIRMED
        row.confirmed_at = confirmed_at
    db.add(
        AuditLog(
            actor=actor,
            action="SHEET_MAPPING_CONFIRMED",
            entity_type="sheet_mapping",
            entity_id=f"{spreadsheet_key}:{sheet_name}",
            detail={"confirmed": len(rows)},
        )
    )
    db.commit()
    return {"confirmed": len(rows)}
