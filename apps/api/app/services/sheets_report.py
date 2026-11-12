"""Read-only, source-traceable reporting over summary-linked Google Sheets tabs."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from app.connectors.sheets import GoogleSheetsConnector, SheetsAPIError
from app.services import sheets_structure

_CELL_REF_RE = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)")
_COLUMN_RANGE_RE = re.compile(r"(?<![A-Z0-9_])\$?([A-Z]{1,3}):\$?([A-Z]{1,3})(?![A-Z0-9_])")
_CURRENCY_CODES = {"USD", "VND", "EUR", "GBP", "USDT"}
_JOKER_PROFILE = {
    "title": "JOKER",
    "opening_balance": "J1",
    "ignored_columns": {"D"},
    "confirmed_columns": {"B", "I", "J", "K", "L"},
}

# Xác nhận của chủ dự án theo kỳ/khách/ô nguồn (D-051). Chỉ áp đúng workbook (theo
# spreadsheet key), kỳ, tab và ô được nêu — workbook khác cùng tên tab/ô/số tiền không nhận.
OWNER_USDT_REFUNDS_WORKBOOK = "1scuChvqYJb1vk3FFAqWGwAqpFoCFyQyN2S1Z7Pl5axk"
OWNER_BLANK_OPENING_ZERO: dict[str, frozenset[str]] = {
    "2026-09": frozenset(
        name.casefold() for name in ("NIN", "WIN", "JACK", "WINE", "KING", "SONA", "VIKTOR", "ALEX", "TOMMY")
    ),
}
OWNER_USDT_REFUNDS: dict[str, dict[tuple[str, str], Decimal]] = {
    "2026-09": {("pedri", "J5"): Decimal("-18"), ("king", "J8"): Decimal("-117")},
}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold().strip()


def _col_index(letter: str) -> int:
    result = 0
    for char in letter:
        result = result * 26 + ord(char.upper()) - 64
    return result - 1


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _effective_deposit_kind(
    deposit: dict[str, Any], amount: Decimal | None, owner: str, source_period: str | None,
    workbook_key: str | None = None,
) -> str:
    """Phân loại hiệu dụng cho snapshot đã lưu trước khi có trường `kind` (D-051)."""
    kind = deposit.get("kind")
    if kind in ("RECEIPT", "REFUND", "UNCLASSIFIED_NEGATIVE"):
        return kind
    if amount is None or source_period is None or workbook_key != OWNER_USDT_REFUNDS_WORKBOOK:
        return "RECEIPT"
    if amount < 0:
        refunds = OWNER_USDT_REFUNDS.get(source_period, {})
        j_cells = [
            str(cell).upper()
            for cell in (deposit.get("source_cells") or [])
            if str(cell).upper().startswith("J")
        ]
        if any(refunds.get((owner.casefold(), cell)) == amount for cell in j_cells):
            return "REFUND"
    return "RECEIPT"


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def exact_decimal_sum(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal(0)
    integer_digits = max(0, *(value.adjusted() + 1 for value in values))
    fractional_digits = max(0, *(-value.as_tuple().exponent for value in values))
    with localcontext() as context:
        context.prec = max(28, integer_digits + fractional_digits + len(str(len(values))) + 1)
        return sum(values, Decimal(0))


def _exact_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, list):
        return [_exact_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _exact_json(item) for key, item in value.items()}
    return value


def _date_value(cell: dict[str, Any] | None) -> str | None:
    if not cell:
        return None
    value = cell.get("value")
    if (
        isinstance(value, (int, float, Decimal))
        and not isinstance(value, bool)
        and (cell.get("number_format") or {}).get("type") == "DATE"
    ):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=int(value))).date().isoformat()
        except (OverflowError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            return None
    return None


def _source_cells(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for cell in row.get("cells") or []:
        match = re.match(r"^([A-Z]+)", str(cell.get("address") or ""))
        if match:
            result[match.group(1)] = cell
    return result


def _sheet_references(formula: str | None, titles: list[str]) -> list[str]:
    if not formula:
        return []
    references: list[str] = []
    for title in sorted(titles, key=len, reverse=True):
        escaped = re.escape(title)
        pattern = rf"(?:'{escaped}'|(?<![A-Za-z0-9_]){escaped})!"
        if re.search(pattern, formula, flags=re.IGNORECASE):
            references.append(title)
    return references


def _field_state(status: str, reason: str, source: str | None = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "source": source}


def _formula_has_missing_input(
    detail: dict[str, Any],
    row_index: int,
    column_index: int,
    visited: set[tuple[int, int]] | None = None,
) -> bool:
    rows = detail.get("rows") or []
    cells = detail.get("cells") or []
    if row_index >= len(rows) or column_index >= len(rows[row_index]):
        return True
    key = (row_index, column_index)
    seen = visited or set()
    if key in seen:
        return False
    seen.add(key)
    metadata = cells[row_index][column_index] if row_index < len(cells) and column_index < len(cells[row_index]) else {}
    formula = metadata.get("formula")
    if not formula:
        return False
    for column, row_number in _CELL_REF_RE.findall(formula):
        if int(row_number) != row_index + 1:
            continue
        ref_col = _col_index(column)
        if detail.get("read_scope") == "A:L" and ref_col >= 12:
            continue
        if ref_col >= len(rows[row_index]) or rows[row_index][ref_col] in (None, ""):
            return True
        if _formula_has_missing_input(detail, row_index, ref_col, seen):
            return True
    return False


def _formula_has_unchecked_dependency(formula: str) -> bool:
    if "!" in formula:
        return True
    referenced_columns = [column for column, _ in _CELL_REF_RE.findall(formula)]
    referenced_columns.extend(
        column
        for start, end in _COLUMN_RANGE_RE.findall(formula)
        for column in (start, end)
    )
    return any(_col_index(column) >= 12 for column in referenced_columns)


def _header_columns(analysis: dict[str, Any]) -> dict[str, str]:
    return {
        str(column.get("column_letter")): str(column.get("header") or "")
        for column in analysis.get("columns") or []
        if column.get("column_letter")
    }


def _find_column(headers: dict[str, str], predicate: Any) -> str | None:
    matches = [letter for letter, header in headers.items() if predicate(_norm(header))]
    return matches[0] if len(matches) == 1 else None


def _find_date_column(headers: dict[str, str]) -> str | None:
    return _find_column(headers, lambda header: header in {"ngay", "date"})


def _date_rows(
    detail: dict[str, Any],
    preview: dict[str, Any],
    date_column: str | None,
) -> tuple[dict[int, str], str | None]:
    if not date_column:
        return {}, None
    date_index = _col_index(date_column)
    dates_by_row: dict[int, str] = {}
    source_rows = {row["row_number"]: row for row in preview.get("rows") or []}
    for row_number, row in source_rows.items():
        cell = _source_cells(row).get(date_column)
        parsed = _date_value(cell)
        if not parsed:
            continue
        detail_row = row_number - 1
        merge = next(
            (
                item
                for item in detail.get("merges") or []
                if item.get("start_row", 0) <= detail_row < item.get("end_row", 0)
                and item.get("start_col", 0) <= date_index < item.get("end_col", 0)
            ),
            None,
        )
        first = int(merge["start_row"] + 1) if merge else row_number
        last = int(merge["end_row"]) if merge else row_number
        for target in range(first, last + 1):
            dates_by_row[target] = parsed
    return dates_by_row, date_column


def _profile_valid(title: str, headers: dict[str, str], opening_cell: dict[str, Any] | None) -> bool:
    if title != _JOKER_PROFILE["title"] or opening_cell is None:
        return False
    return _find_date_column(headers) is not None and _find_column(
        headers, lambda value: "id tk" in value or "account id" in value
    ) is not None


def _build_customer_report(
    meta: dict[str, Any],
    detail: dict[str, Any],
    linked_summary_rows: list[dict[str, Any]],
    hidden_titles: list[str] | None = None,
    source_period: str | None = None,
    mapping_config: dict[str, Any] | None = None,
    workbook_key: str | None = None,
) -> dict[str, Any]:
    analysis = sheets_structure.analyze_sheet_detail(detail)
    preview = sheets_structure.build_cell_preview(detail)
    headers = _header_columns(analysis)
    title = str(meta["title"])
    config = mapping_config or {}
    confirmed_tabs = {str(item).casefold() for item in config.get("blank_usdt_header_tabs", [])}
    header_row_is_3 = analysis.get("header_row_index") == 2
    header_row = next((row for row in preview.get("rows") or [] if row.get("row_number") == 3), {})
    j3 = _source_cells(header_row).get("J", {})
    j3_value = _norm(j3.get("value"))
    # Mapping chuẩn cột J đã được chủ dự án xác nhận cho mọi tab khách: J3 trống không phải lỗi cấu trúc.
    confirmed_j3 = title.casefold() in confirmed_tabs or (header_row_is_3 and j3_value == "")
    inactive_tabs = {
        str(item).casefold()
        for item in config.get("inactive_tabs_by_period", {}).get(source_period or "", [])
    }
    confirmed_layout_tabs = {
        name.casefold()
        for name in config.get("separator_rows_by_period", {}).get(source_period or "", {})
    }
    activity_status = (
        {"period": source_period, "status": "OWNER_CONFIRMED_INACTIVE", "conflict": False}
        if title.casefold() in inactive_tabs else None
    )
    expected_headers = {
        "A": lambda value: value in {"ngay", "date"},
        "C": lambda value: "id tk" in value or "account id" in value or "ad account" in value,
        "F": lambda value: value in {"vnd", "chi tieu vnd", "spend vnd"},
        "G": lambda value: value.startswith("phi") or value.startswith("fee"),
        "H": lambda value: value in {"tong", "tong cong", "total"},
        "J": lambda value: value == "usdt",
    }
    incompatible = [
        column for column, matches in expected_headers.items()
        if not (
            confirmed_j3 and column == "J"
            and analysis.get("header_row_index") == 2 and j3_value in {"", "usdt"}
        ) and not matches(_norm(headers.get(column)))
    ]
    if confirmed_j3 and (analysis.get("header_row_index") != 2 or j3_value not in {"", "usdt"}):
        if "J" not in incompatible:
            incompatible.append("J")
    # J3 mang giá trị khác USDT: mâu thuẫn chỉ ảnh hưởng khoản nhận USDT (J4:J); J1 đọc theo ô riêng, F1/G1/H1/K1/L1 vẫn đọc.
    j_conflict = incompatible == ["J"] and header_row_is_3 and j3_value not in {"", "usdt"}
    if j_conflict:
        incompatible = []
    if incompatible:
        issue = {
            "severity": "error",
            "source": f"{meta['title']}!{','.join('J3' if col == 'J' and confirmed_j3 else col for col in incompatible)}",
            "message": "Cấu trúc không phù hợp mapping chuẩn; header chưa khớp tại cột " + ", ".join(incompatible) + ". Không áp dụng mapping cũ hoặc lấy ô khác thay thế.",
        }
        return {
            "display_name": linked_summary_rows[0].get("customer_label") if linked_summary_rows else meta["title"],
            "source_sheet": meta["title"], "sheet_id": meta.get("sheet_id"),
            "read_scope": detail.get("read_scope"), "completeness_status": "NEEDS_REVIEW",
            "profile_status": "STRUCTURE_ERROR", "source_periods": [], "source_rows": preview.get("rows") or [],
            "observed_date_from": None, "observed_date_to": None, "period_coverage_complete": False,
            "period_coverage_note": "Không áp dụng mapping do cấu trúc không phù hợp.",
            "field_status": {}, "period_totals": {}, "account_rows": [], "deposits": [],
            "unclassified_rows": [], "daily": [], "issues": [issue],
            "activity_status": activity_status,
            "linked_summary_rows": linked_summary_rows, "ignored_columns": [],
        }
    date_column = _find_date_column(headers)
    if not date_column and detail.get("read_scope") == "A:L":
        if any(_date_value(_source_cells(row).get("A")) for row in preview.get("rows") or []):
            date_column = "A"
    dates_by_row, _ = _date_rows(detail, preview, date_column)
    observed_dates = sorted(set(dates_by_row.values()))
    opening_cell = next(
        (
            cell
            for row in preview.get("rows") or []
            for cell in row.get("cells") or []
            if cell.get("address") == _JOKER_PROFILE["opening_balance"]
        ),
        None,
    )
    totals_row_cells = _source_cells(
        next(
            (row for row in preview.get("rows") or [] if row.get("row_number") == 1),
            {},
        )
    )
    invalid_totals = [
        column for column in ("F", "G", "H", "J", "K", "L")
        if totals_row_cells.get(column, {}).get("value") not in (None, "")
        and _decimal(totals_row_cells[column]["value"]) is None
    ]
    profile_confirmed = _profile_valid(str(meta["title"]), headers, opening_cell) and any(
        row.get("opening_balance_refers_to_source") for row in linked_summary_rows
    )

    account_id_column = _find_column(
        headers, lambda value: "id tk" in value or "account id" in value or "ad account" in value
    )
    usd_column = _find_column(headers, lambda value: value in {"usd", "chi tieu usd", "spend usd"})
    vnd_column = _find_column(headers, lambda value: value in {"vnd", "chi tieu vnd", "spend vnd"})
    fee_column = _find_column(headers, lambda value: value.startswith("phi") or value.startswith("fee"))
    total_column = _find_column(headers, lambda value: value in {"tong", "tong cong", "total"})
    usdt_column = (
        None if j_conflict
        else "J" if confirmed_j3
        else _find_column(headers, lambda value: value == "usdt")
    )
    if confirmed_j3 and not j3_value:
        analysis["notes"] = [
            note for note in analysis.get("notes", [])
            if note != "cột J không có header — bỏ qua, chờ chủ dự án xác nhận"
        ]
        analysis["notes"].append("J3 trống; mapping cột J được chủ dự án xác nhận cho nguồn này.")
    rate_column = "L" if usdt_column else None
    conversion_column = "K" if usdt_column else None

    fields: dict[str, dict[str, Any]] = {
        "business_date": _field_state(
            "DETECTED" if date_column else "UNIDENTIFIED",
            (
                "Được nhận diện theo header ngày và giá trị DATE."
                if date_column in headers
                else "Ô cột A có numberFormat=DATE; header ngày chưa xác nhận trong phạm vi đọc giới hạn."
            )
            if date_column
            else "Không có cột ngày đủ căn cứ.",
            f"{meta['title']}!{date_column}" if date_column else None,
        ),
        "ad_account_id": _field_state(
            "PREVIEW" if account_id_column else "UNIDENTIFIED",
            "Header nhận diện ID tài khoản; chưa xác nhận mapping chính thức."
            if account_id_column
            else "Không tìm thấy header ID tài khoản duy nhất.",
            f"{meta['title']}!{account_id_column}" if account_id_column else None,
        ),
        "spend_original": _field_state(
            "PREVIEW" if usd_column or vnd_column else "UNIDENTIFIED",
            "Các cột được nhận diện từ header currency; giá trị gốc giữ theo đơn vị trên Sheet."
            if usd_column or vnd_column
            else "Không tìm thấy cột chi tiêu có header tiền tệ duy nhất.",
            ", ".join(f"{meta['title']}!{column}" for column in (usd_column, vnd_column) if column) or None,
        ),
        "spend_vnd": _field_state(
            "PREVIEW" if vnd_column else "UNIDENTIFIED",
            "Cột VND lấy theo header và kết quả Sheet; không quy đổi lại."
            if vnd_column
            else "Không xác định được cột chi tiêu VND.",
            f"{meta['title']}!{vnd_column}" if vnd_column else None,
        ),
        "fee": _field_state(
            "PREVIEW" if fee_column else "UNIDENTIFIED",
            "Phí theo giá trị/header Sheets; chưa khẳng định chính sách phí cho khách."
            if fee_column
            else "Không tìm thấy cột phí duy nhất.",
            f"{meta['title']}!{fee_column}" if fee_column else None,
        ),
        "billing_total": _field_state(
            "PREVIEW" if total_column else "UNIDENTIFIED",
            "Tổng lấy nguyên giá trị/formula Sheets; chưa suy diễn lại."
            if total_column
            else "Không tìm thấy cột tổng duy nhất.",
            f"{meta['title']}!{total_column}" if total_column else None,
        ),
        "usdt_receipts": _field_state(
            "CONFIRMED" if profile_confirmed else ("PREVIEW" if usdt_column else "UNIDENTIFIED"),
            "J/K/L được xác nhận riêng cho JOKER."
            if profile_confirmed
            else (
                "Có header USDT nhưng ý nghĩa chưa được xác nhận cho tab này."
                if usdt_column
                else "Không nhận diện được cột USDT."
            ),
            f"{meta['title']}!{usdt_column}" if usdt_column else None,
        ),
        "opening_balance": _field_state(
            "CONFIRMED" if profile_confirmed else "UNIDENTIFIED",
            "JOKER!J1 được xác nhận là số dư đầu kỳ; không áp dụng profile sang tab khác."
            if profile_confirmed
            else "Chưa có mapping số dư đầu kỳ được xác nhận cho cấu trúc tab này.",
            f"{meta['title']}!{_JOKER_PROFILE['opening_balance']}" if profile_confirmed else None,
        ),
        "usdt_vnd_rate": _field_state(
            "CONFIRMED" if profile_confirmed and rate_column else ("PREVIEW" if rate_column else "UNIDENTIFIED"),
            "Tỷ giá nhận USDT/VND được xác nhận riêng cho JOKER."
            if profile_confirmed and rate_column
            else (
                "Có cột tỷ giá nhưng ý nghĩa/đơn vị chưa xác nhận cho tab này."
                if rate_column
                else "Không nhận diện được cột tỷ giá nhận."
            ),
            f"{meta['title']}!{rate_column}" if rate_column else None,
        ),
        "usdt_receipt_vnd": _field_state(
            "CONFIRMED" if profile_confirmed and conversion_column else ("PREVIEW" if conversion_column else "UNIDENTIFIED"),
            "K là giá trị VND theo Sheet, được xác nhận riêng cho JOKER."
            if profile_confirmed and conversion_column
            else (
                "Cột có formula tham chiếu USDT và tỷ giá; ý nghĩa chưa xác nhận."
                if conversion_column
                else "Không nhận diện được cột VND quy đổi."
            ),
            f"{meta['title']}!{conversion_column}" if conversion_column else None,
        ),
    }
    fields["opening_balance"] = _field_state("CONFIRMED", "Mapping chuẩn theo D-047; giá trị nguồn cấp tab.", f"{meta['title']}!J1")
    fields["usdt_receipts"] = _field_state("CONFIRMED", "Khoản nhận hợp lệ từ J4 trở đi; loại dòng tổng và giá trị chưa đủ căn cứ.", f"{meta['title']}!J4:J")
    if profile_confirmed:
        for column in _JOKER_PROFILE["confirmed_columns"]:
            for field in ("ad_account_id", "spend_original", "spend_vnd", "fee", "billing_total", "usdt_receipts"):
                if fields[field].get("source", "").endswith(f"!{column}"):
                    fields[field]["status"] = "CONFIRMED"
                    fields[field]["reason"] = "Ý nghĩa cột đã được chủ dự án xác nhận cho JOKER."
        fields["spend_usd_vnd_rate"] = _field_state(
            "CONFIRMED", "Ý nghĩa tỷ giá USD/VND đã xác nhận riêng cho JOKER.", "JOKER!I"
        )
        fields["usdt_vnd_rate"] = _field_state(
            "CONFIRMED", "Ý nghĩa tỷ giá nhận USDT/VND đã xác nhận riêng cho JOKER.", "JOKER!L"
        )
        fields["ignored_columns"] = _field_state(
            "CONFIRMED", "Cột D JOKER được xác nhận bỏ qua; không cảnh báo thiếu.", "JOKER!D"
        )

    daily: dict[str, dict[str, Any]] = {}
    deposits: list[dict[str, Any]] = []
    account_rows: list[dict[str, Any]] = []
    unclassified_rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for column in invalid_totals:
        issues.append({
            "severity": "error",
            "source": f"{meta['title']}!{column}1",
            "message": "Ô tổng chuẩn không phải số; không dùng giá trị thay thế.",
        })
    if j_conflict:
        issues.append({
            "severity": "warning",
            "source": f"{meta['title']}!J3",
            "message": "Header J3 không phải USDT; chỉ khoản nhận USDT (J4:J) bị cô lập. J1 đọc theo ô riêng của nó; F1/G1/H1/K1/L1 vẫn đọc nguồn.",
        })
    source_row_numbers: list[int] = []
    read_scope = detail.get("read_scope")
    for source_row in preview.get("rows") or []:
        row_number = int(source_row["row_number"])
        cells = _source_cells(source_row)
        for cell in source_row.get("cells") or []:
            hidden_refs = _sheet_references(cell.get("formula"), hidden_titles or [])
            if hidden_refs:
                issues.append({
                    "severity": "warning",
                    "source": f"{meta['title']}!{cell['address']}",
                    "message": "Công thức phụ thuộc tab ẩn; giữ kết quả nguồn, không đọc tab ẩn và chưa kiểm tra phụ thuộc.",
                    "references": hidden_refs,
                })
        if read_scope:
            for cell in source_row.get("cells") or []:
                formula = cell.get("formula")
                if formula and _formula_has_unchecked_dependency(formula):
                    issues.append(
                        {
                            "severity": "warning",
                            "source": cell.get("address"),
                            "message": "Công thức có tham chiếu ngoài phạm vi đọc; giữ kết quả do Sheets trả về nhưng chưa kiểm tra phụ thuộc.",
                        }
                    )
        if row_number <= (analysis.get("header_row_index") or 0) + 1:
            continue
        account_id_cell = cells.get(account_id_column) if account_id_column else None
        account_id = account_id_cell.get("value") if account_id_cell else None
        if account_id not in (None, ""):
            source_row_numbers.append(row_number)
        source_date = dates_by_row.get(row_number)
        row_index = row_number - 1

        receipt_columns: set[str] = set()
        if usdt_column and row_number >= 4:
            usdt_cell = cells.get(usdt_column)
            if usdt_cell and usdt_cell.get("value") not in (None, ""):
                formula = str(usdt_cell.get("formula") or "")
                labels = " ".join(_norm(cell.get("value")) for column, cell in cells.items() if column in {"A", "B", "C", "D"})
                is_total = bool(re.search(r"\b(tong|total|subtotal)\b", labels)) or bool(
                    re.search(r"\b(?:SUM|SUBTOTAL|SUMIF|SUMIFS)\s*\(", formula, re.IGNORECASE)
                    or re.search(r"(?:^|[^A-Z])\$?J\$?\d+", formula, re.IGNORECASE)
                )
                valid_amount = _decimal(usdt_cell.get("value")) is not None
                if confirmed_j3 and not valid_amount:
                    issues.append({
                        "severity": "warning",
                        "source": f"{title}!{usdt_cell['address']}",
                        "message": "Giá trị tại cột USDT không phải số; giữ ô nguồn và không tính thành khoản nhận.",
                    })
                excluded_reason = (
                    "Dòng tổng hoặc công thức cộng cột J; không cộng trùng."
                    if is_total else
                    "Công thức hoặc giá trị USDT chưa đủ căn cứ xác định là khoản nhận."
                    if formula or not valid_amount else None
                )
                refund_key = (title.casefold(), str(usdt_cell.get("address")))
                usdt_amount = _decimal(usdt_cell.get("value"))
                confirmed_refund = (
                    excluded_reason is None and usdt_amount is not None and source_period is not None
                    and workbook_key == OWNER_USDT_REFUNDS_WORKBOOK
                    and OWNER_USDT_REFUNDS.get(source_period, {}).get(refund_key) == usdt_amount
                )
                if excluded_reason is None and usdt_amount is not None and usdt_amount < 0 and not confirmed_refund:
                    excluded_reason = "Số âm chưa có xác nhận loại khoản; cần rà soát, không tính là nhận hoặc hoàn."
                kind = (
                    "REFUND" if confirmed_refund
                    else "UNCLASSIFIED_NEGATIVE" if usdt_amount is not None and usdt_amount < 0
                    else "RECEIPT"
                )
                receipt_columns = {column for column in (usdt_column, conversion_column, rate_column) if column}
                deposits.append(
                    {
                        "kind": kind,
                        "confirmation": (
                            {"decision": "D-051", "meaning": "Hoàn USDT cho khách", "source": f"{title}!{usdt_cell['address']}"}
                            if confirmed_refund else None
                        ),
                        "business_date": (
                            None if account_id in (None, "") and not _date_value(cells.get(date_column or "A"))
                            else source_date
                        ),
                        "amount_usdt": usdt_cell.get("value"),
                        "amount_vnd": cells.get(conversion_column, {}).get("value") if conversion_column else None,
                        "rate": cells.get(rate_column, {}).get("value") if rate_column else None,
                        "source_cells": [
                            item.get("address")
                            for item in (
                                usdt_cell,
                                cells.get(conversion_column),
                                cells.get(rate_column),
                            )
                            if item and item.get("address")
                        ],
                        "source_row": row_number,
                        "status": "EXCLUDED" if excluded_reason else "PREVIEW",
                        "included": excluded_reason is None,
                        "exclusion_reason": excluded_reason,
                    }
                )

        if not account_id_cell or account_id in (None, ""):
            standalone_notes = {
                column for column, cell in cells.items()
                if title.casefold() in confirmed_layout_tabs
                and column == "M"
                and isinstance(cell.get("value"), str)
                and cell["value"].strip()
                and not cell.get("formula")
                and not any(
                    other.get("value") not in (None, "") or other.get("formula")
                    for other_column, other in cells.items()
                    if other_column in {"B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"}
                )
            }
            for column in standalone_notes:
                issues.append({
                    "severity": "warning",
                    "source": f"{title}!{cells[column]['address']}",
                    "message": "Ghi chú ngoài khối TKQC và nhận tiền được giữ nguyên; chưa phân loại nội dung.",
                })
            row_values = [
                cell
                for column, cell in cells.items()
                if column not in (_JOKER_PROFILE["ignored_columns"] if profile_confirmed else set())
                and column not in receipt_columns
                and column not in standalone_notes
                and (cell.get("value") not in (None, "") or cell.get("formula"))
                and (column != date_column or cell.get("formula"))
            ]
            if row_values:
                formula_only = all(
                    cell.get("value") in (None, "") and cell.get("formula")
                    for cell in row_values
                )
                unclassified_rows.append(
                    {
                        "row_number": row_number,
                        "business_date": source_date,
                        "cells": source_row.get("cells") or [],
                        "status": "UNIDENTIFIED",
                        "reason": (
                            "Dòng có công thức nhưng kết quả ô trống; chưa đủ căn cứ coi là dòng phân cách."
                            if formula_only
                            else "Dòng có dữ liệu nhưng không nhận diện được là dòng tài khoản hoặc khoản nhận."
                        ),
                    }
                )
            continue
        account_currency = str(cells.get("B", {}).get("value") or "").upper()
        missing_inputs = [
            cell.get("address")
            for column in (usd_column, vnd_column, fee_column, total_column)
            if column
            for cell in (cells.get(column),)
            if cell
            and _formula_has_missing_input(detail, row_index, _col_index(column))
        ]
        account_rows.append(
            {
                "row_number": row_number,
                "business_date": source_date,
                "account_id": str(account_id),
                "account_currency": account_currency or None,
                "cells": source_row.get("cells") or [],
                "missing_inputs": missing_inputs,
                "status": "NEEDS_CONFIRMATION" if not profile_confirmed else "PREVIEW",
            }
        )
        if not source_date:
            issues.append(
                {
                    "severity": "warning",
                    "source": f"{meta['title']}!{date_column or 'A'}{row_number}",
                    "message": "Dòng tài khoản có dữ liệu nhưng không có ngày trong ô hoặc vùng merge hợp lệ.",
                }
            )
            continue
        day = daily.setdefault(
            source_date,
            {
                "business_date": source_date,
                "spend_by_currency": {},
                "spend_vnd": None,
                "fee_by_currency": {},
                "billing_by_currency": {},
                "source_cells": [],
                "account_rows": [],
            },
        )
        day["account_rows"].append(row_number)
        currency = account_currency
        if currency and currency not in {"USD", "VND"}:
            issues.append(
                {
                    "severity": "warning",
                    "source": f"{meta['title']}!B{row_number}",
                    "message": f"Currency TK {currency} chưa có cột chi tiêu phù hợp được xác nhận; không cộng vào tổng.",
                }
            )
        for column, target_currency in ((usd_column, "USD"), (vnd_column, "VND")):
            if not column:
                continue
            cell = cells.get(column)
            if not cell:
                continue
            if _formula_has_missing_input(detail, row_index, _col_index(column)):
                issues.append(
                    {
                        "severity": "warning",
                        "source": cell.get("address"),
                        "message": "Formula có đầu vào trống; kết quả không được tính là chi tiêu bằng 0.",
                    }
                )
                continue
            amount = _decimal(cell.get("value"))
            if amount is None:
                continue
            if target_currency == "USD" and currency == "USD":
                current = _decimal(day["spend_by_currency"].get("USD")) or Decimal(0)
                day["spend_by_currency"]["USD"] = _decimal_text(current + amount)
            if target_currency == "VND":
                spend_vnd = _decimal(day["spend_vnd"])
                day["spend_vnd"] = _decimal_text((spend_vnd or Decimal(0)) + amount)
                if currency == "VND":
                    current = _decimal(day["spend_by_currency"].get("VND")) or Decimal(0)
                    day["spend_by_currency"]["VND"] = _decimal_text(current + amount)
            day["source_cells"].append(cell.get("address"))

        for column, target_key in ((fee_column, "fee_by_currency"), (total_column, "billing_by_currency")):
            if not column:
                continue
            cell = cells.get(column)
            if not cell or _formula_has_missing_input(detail, row_index, _col_index(column)):
                continue
            amount = _decimal(cell.get("value"))
            if amount is None:
                continue
            currency_code = _currency_from_cell(cell, headers.get(column, ""), currency)
            if not currency_code:
                issues.append(
                    {
                        "severity": "warning",
                        "source": cell.get("address"),
                        "message": "Không xác định được currency của số tiền; không cộng vào biểu đồ.",
                    }
                )
                continue
            current = _decimal(day[target_key].get(currency_code)) or Decimal(0)
            day[target_key][currency_code] = _decimal_text(current + amount)
            day["source_cells"].append(cell.get("address"))

    dates = sorted(daily)
    periods = sorted({item[:7] for item in [*dates, *observed_dates]})
    for deposit in deposits:
        day = deposit.get("business_date")
        if day:
            deposit["period"], deposit["period_basis"] = day[:7], "DATE"
        elif source_period and periods == [source_period]:
            # Chỉ biết kỳ: mọi ngày quan sát được của tab đều thuộc kỳ nguồn; không gán ngày giả.
            deposit["period"], deposit["period_basis"] = source_period, "SOURCE_PERIOD"
        else:
            deposit["period"], deposit["period_basis"] = None, None
    for day in daily.values():
        day["source_cells"] = sorted(set(day["source_cells"]))
        day["data_state"] = "SOURCE_PREVIEW"

    tab_source_totals: dict[str, dict[str, Any]] = {}
    for field, column in (
        ("spend_vnd", "F"),
        ("fee", "G"),
        ("billing_total", "H"),
        ("budget_deposits_vnd", "K"),
        ("current_balance", "L"),
        ("profit_convention", "G"),
    ):
        cell = totals_row_cells.get(column)
        if not cell or cell.get("value") in (None, "") or _decimal(cell.get("value")) is None:
            continue
        value = cell["value"]
        tab_source_totals[field] = {
            "value": _decimal_text(value) if isinstance(value, Decimal) else str(value),
            "formatted_value": cell.get("formatted_value"),
            "currency": "VND",
            "formula": cell.get("formula"),
            "source": cell.get("address"),
            "status": "CONFIRMED",
        }

    period_totals: dict[str, dict[str, Any]] = {}
    for period in periods:
        period_totals[period] = {
            "spend_original_by_currency": {},
            "spend_vnd": None,
            "fee_by_currency": {},
            "billing_by_currency": {},
            "usdt_received": None,
            "usdt_received_vnd": None,
            "budget_deposits_vnd": None,
            "budget_deposits_status": "NEEDS_CONFIRMATION",
            "budget_deposits_reason": "Nguồn chưa phân biệt rõ phần nhận USDT được phân bổ vào ngân sách quảng cáo.",
        }
        totals = period_totals[period]
        for day in (item for item in daily.values() if item["business_date"].startswith(period)):
            for metric, target in (
                ("spend_by_currency", "spend_original_by_currency"),
                ("fee_by_currency", "fee_by_currency"),
                ("billing_by_currency", "billing_by_currency"),
            ):
                for currency_code, amount in day[metric].items():
                    current = _decimal(totals[target].get(currency_code)) or Decimal(0)
                    totals[target][currency_code] = _decimal_text(current + Decimal(amount))
            if day["spend_vnd"] is not None:
                current_spend = _decimal(totals["spend_vnd"]) or Decimal(0)
                totals["spend_vnd"] = _decimal_text(current_spend + Decimal(day["spend_vnd"]))
        totals["usdt_refunded"] = None
        totals["usdt_net"] = None
        for deposit in deposits:
            if deposit["included"] and deposit.get("period") == period:
                amount_usdt = _decimal(deposit.get("amount_usdt"))
                if deposit["kind"] == "RECEIPT" and amount_usdt is not None:
                    current_usdt = _decimal(totals["usdt_received"]) or Decimal(0)
                    totals["usdt_received"] = _decimal_text(current_usdt + amount_usdt)
                    if deposit.get("amount_vnd") not in (None, ""):
                        current_vnd = _decimal(totals["usdt_received_vnd"]) or Decimal(0)
                        totals["usdt_received_vnd"] = _decimal_text(current_vnd + Decimal(str(deposit["amount_vnd"])))
                elif deposit["kind"] == "REFUND" and amount_usdt is not None:
                    current_refund = _decimal(totals["usdt_refunded"]) or Decimal(0)
                    totals["usdt_refunded"] = _decimal_text(current_refund - amount_usdt)
        if any(
            (deposit["included"] and not deposit.get("period")) or deposit["kind"] == "UNCLASSIFIED_NEGATIVE"
            for deposit in deposits
        ):
            totals["usdt_received"] = None
            totals["usdt_received_vnd"] = None
            totals["usdt_refunded"] = None
        elif totals["usdt_received"] is not None or totals["usdt_refunded"] is not None:
            totals["usdt_net"] = _decimal_text(
                (_decimal(totals["usdt_received"]) or Decimal(0)) - (_decimal(totals["usdt_refunded"]) or Decimal(0))
            )
        if len(periods) == 1 and (not confirmed_j3 or not source_period or periods[0] == source_period):
            source_totals = tab_source_totals
            if source_totals.get("budget_deposits_vnd"):
                totals["budget_deposits_vnd"] = source_totals["budget_deposits_vnd"]["value"]
                totals["budget_deposits_status"] = "CONFIRMED"
                totals["budget_deposits_reason"] = "K1 theo mapping chuẩn; không suy ra từ USDT."
            totals["source_totals"] = source_totals
            comparisons = []
            for field, detail_value in (
                ("spend_vnd", totals["spend_vnd"]),
                ("fee", totals["fee_by_currency"].get("VND")),
                ("billing_total", totals["billing_by_currency"].get("VND")),
            ):
                source_value = _decimal(source_totals.get(field, {}).get("value"))
                detail_amount = _decimal(detail_value)
                if source_value is not None and detail_amount is not None and source_value != detail_amount:
                    comparisons.append({
                        "field": field,
                        "source": source_totals[field]["source"],
                        "source_value": _decimal_text(source_value),
                        "detail_value": _decimal_text(detail_amount),
                        "difference": _decimal_text(source_value - detail_amount),
                        "note": "Chi tiết chỉ gồm dòng đã nhận diện và gán được ngày; không thay thế tổng nguồn.",
                    })
            totals["source_detail_differences"] = comparisons

    account_rows.sort(key=lambda row: (row.get("business_date") or "9999-99-99", row["row_number"]))
    deposits.sort(key=lambda row: (row.get("business_date") or "9999-99-99", row["source_row"]))
    unclassified_rows.sort(key=lambda row: row["row_number"])

    j_detail_cells = [
        cell
        for row in preview.get("rows") or [] if row.get("row_number", 0) >= 4
        for cell in [_source_cells(row).get("J")]
        if cell and (cell.get("value") not in (None, "") or cell.get("formula"))
    ]
    usdt_receipts_state = (
        "NEEDS_REVIEW" if j_conflict
        else "NO_RECORDED" if not j_detail_cells
        else "HAS_RECORDS" if any(item["included"] for item in deposits)
        else "NEEDS_REVIEW"
    )
    if activity_status and source_period:
        conflicting_sources = [
            f"{title}!{column}1" for column in ("F", "G", "H", "K")
            if _decimal(totals_row_cells.get(column, {}).get("value")) not in (None, Decimal(0))
        ]
        conflicting_sources.extend([
            f"{title}!C{row['row_number']}" for row in account_rows
            if (row.get("business_date") or "").startswith(source_period)
        ])
        conflicting_sources.extend(
            f"{title}!J{item['source_row']}" for item in deposits
            if item["included"] and (
                (item.get("business_date") or "").startswith(source_period)
                or (not item.get("business_date") and _decimal(item.get("amount_usdt")) not in (None, Decimal(0)))
            )
        )
        conflicting_sources.extend(
            f"{title}!{cell['address']}"
            for row in account_rows + unclassified_rows
            if not row.get("business_date") or row["business_date"].startswith(source_period)
            for cell in row["cells"]
            if re.match(r"^(?:E|F|G|H|J|K)\d+$", str(cell.get("address") or ""))
            and _decimal(cell.get("value")) not in (None, Decimal(0))
        )
        if conflicting_sources:
            activity_status["conflict"] = True
            issues.append({
                "severity": "warning",
                "source": ", ".join(dict.fromkeys(conflicting_sources)),
                "message": "Có dữ liệu có thể mâu thuẫn với xác nhận chưa hoạt động trong kỳ; cần rà soát, không tự đổi trạng thái.",
            })

    opening_value = opening_cell.get("value") if opening_cell else None
    if opening_value is not None:
        opening_value = _decimal_text(opening_value) if isinstance(opening_value, Decimal) else str(opening_value)
    opening_basis = "SOURCE_VALUE" if opening_value is not None else "BLANK_UNCONFIRMED"
    if "J" in invalid_totals:
        opening_value, opening_basis = None, "INVALID_CELL"
    elif source_period and workbook_key == OWNER_USDT_REFUNDS_WORKBOOK and \
            title.casefold() in OWNER_BLANK_OPENING_ZERO.get(source_period, frozenset()):
        if opening_cell is None or opening_cell.get("value") in (None, ""):
            if not (opening_cell or {}).get("formula"):
                opening_value, opening_basis = "0", "OWNER_CONFIRMED_BLANK_ZERO"
        else:
            issues.append({
                "severity": "warning",
                "source": f"{title}!J1",
                "message": "J1 đã có giá trị nguồn; xác nhận J1 trống = 0 không còn áp dụng, dùng giá trị nguồn và cần rà soát mâu thuẫn.",
            })
    summary_balances = []
    for row in linked_summary_rows:
        source_cell = next(
            (
                cell
                for cell in row.get("cells") or []
                if cell.get("address") == row.get("closing_balance_source")
            ),
            {},
        )
        if row.get("closing_balance_source"):
            summary_balances.append(
                {
                    "summary_sheet": row.get("summary_sheet"),
                    "summary_row": row.get("summary_row"),
                    "value": row.get("closing_balance_value"),
                    "formatted_value": source_cell.get("formatted_value"),
                    "currency": _currency_from_cell(source_cell, "", ""),
                    "formula": row.get("closing_balance_formula"),
                    "source": row.get("closing_balance_source"),
                }
            )

    incomplete = (
        bool(unclassified_rows)
        or any(not row["business_date"] or row["missing_inputs"] for row in account_rows)
        or any(not deposit["business_date"] for deposit in deposits)
        or any(fields[field]["status"] == "UNIDENTIFIED" for field in (
            "business_date", "ad_account_id", "spend_original", "spend_vnd",
            "fee", "billing_total", "usdt_receipts", "usdt_vnd_rate", "usdt_receipt_vnd",
            "opening_balance",
        ))
        or bool(issues)
    )
    return {
        "display_name": linked_summary_rows[0].get("customer_label") if linked_summary_rows else meta["title"],
        "source_sheet": meta["title"],
        "sheet_id": meta.get("sheet_id"),
        "read_scope": read_scope,
        "completeness_status": "NEEDS_REVIEW" if incomplete else "SOURCE_ROWS_CLASSIFIED",
        "profile_status": "CONFIRMED_PARTIAL" if profile_confirmed else "NEEDS_CONFIRMATION",
        "source_periods": periods,
        "observed_date_from": observed_dates[0] if observed_dates else (dates[0] if dates else None),
        "observed_date_to": observed_dates[-1] if observed_dates else (dates[-1] if dates else None),
        "period_coverage_complete": False,
        "period_coverage_note": "Phạm vi ngày có dòng nhận diện được; ngày cuối không chứng minh kỳ đã hoàn tất.",
        "source_config_period": source_period if confirmed_j3 else None,
        "activity_status": activity_status,
        "usdt_receipts_state": usdt_receipts_state,
        "field_status": fields,
        "opening_balance": {
            "value": opening_value if "J" not in invalid_totals else None,
            "formatted_value": opening_cell.get("formatted_value") if opening_cell and "J" not in invalid_totals else None,
            "currency": "VND",
            "source": f"{meta['title']}!J1",
            "source_value": opening_cell.get("value") if opening_cell else None,
            "basis": opening_basis,
            "status": "CONFIRMED",
        },
        "period_totals": period_totals,
        "tab_source_totals": tab_source_totals,
        "closing_balances": summary_balances,
        "deposits": deposits,
        "account_rows": account_rows,
        "unclassified_rows": unclassified_rows,
        "daily": [daily[key] for key in dates],
        "source_rows": preview.get("rows") or [],
        "source_analysis": analysis,
        "account_row_numbers": source_row_numbers,
        "issues": issues,
        "linked_summary_rows": linked_summary_rows,
        "ignored_columns": (
            sorted(_JOKER_PROFILE["ignored_columns"]) if profile_confirmed else []
        ),
    }


def _currency_from_cell(cell: dict[str, Any], header: str, account_currency: str) -> str | None:
    pattern = (cell.get("number_format") or {}).get("pattern") or ""
    currency = sheets_structure._currency_from_pattern(pattern)
    if currency:
        return currency
    normalized_header = _norm(header)
    if normalized_header in _CURRENCY_CODES:
        return normalized_header.upper()
    if account_currency in {"USD", "VND", "EUR", "GBP"}:
        return account_currency
    return None


def _company_summary_totals(report: dict[str, Any], period: str | None) -> dict[str, Any]:
    """Read the labelled company total, never infer a row number or recalculate it."""
    candidates = []
    for tab in report.get("summary_tabs") or []:
        # A workbook can contain several monthly summary tabs.
        title_month = re.search(r"\bt\s*(\d{1,2})(?!\d)", _norm(tab.get("title")))
        if period and title_month and int(title_month[1]) != int(period[-2:]):
            continue
        rows = tab.get("rows") or []
        headers = next((r for r in rows if r.get("summary_row") == tab.get("header_row")), {})
        cells = _source_cells(headers)
        if not (
            _norm(cells.get("B", {}).get("value")) in {"đa bank", "da bank", "đã bank"}
            and _norm(cells.get("D", {}).get("value")) == "run"
            and _norm(cells.get("E", {}).get("value")) == "phi"
            and _norm(cells.get("F", {}).get("value")) == "tong"
            and _norm(cells.get("G", {}).get("value")) == "con"
        ):
            continue
        for row in rows:
            if _norm(row.get("customer_label")) in {"tong", "tong cong"}:
                candidates.append((tab, row))
    selected = candidates[0] if len(candidates) == 1 else None
    metrics = {}
    for field, column in {
        "budget_deposits_vnd": "B", "opening_balance": "C", "spend_vnd": "D",
        "fee": "E", "billing_total": "F", "current_balance": "G",
    }.items():
        cell = _source_cells(selected[1]).get(column, {}) if selected else {}
        amount = _decimal(cell.get("value"))
        if amount is not None and not amount.is_finite():
            amount = None
        source = f"{selected[0]['title']}!{cell['address']}" if selected and cell.get("address") else None
        detail = report["all_customer_totals"]["metrics"][field]
        detail_amount = _decimal(detail.get("value"))
        metrics[field] = {
            "value": _decimal_text(amount) if amount is not None else None,
            "status": "COMPLETE" if amount is not None else "PARTIAL",
            "basis": "SUMMARY_ROW", "source": source, "formula": cell.get("formula"),
            "complete_customers": detail["complete_customers"],
            "total_customers": detail["total_customers"],
            "missing_customers": detail["missing_customers"],
            "contributions": [{"customer": selected[0]["title"], "source": source,
                               "value": _decimal_text(amount)}] if amount is not None else [],
            "detail_value": detail.get("value"),
            "difference": _decimal_text(exact_decimal_sum([amount, -detail_amount]))
            if amount is not None and detail_amount is not None else None,
            "detail_status": detail["status"],
        }
    # USDT remains a separate currency, read from validated customer receipts.
    for field in ("usdt_received", "usdt_refunded", "usdt_net"):
        metrics[field] = report["all_customer_totals"]["metrics"][field]
    return {
        "period": period, "metrics": metrics,
        "status": "READY" if selected else "NEEDS_CONFIRMATION",
        "reason": None if selected else ("MULTIPLE_TOTAL_ROWS" if candidates else "TOTAL_ROW_NOT_FOUND"),
        "source_sheet": selected[0]["title"] if selected else None,
        "source_row": selected[1]["summary_row"] if selected else None,
    }


def enrich_sheets_report(
    report: dict[str, Any], source_period: str | None, workbook_key: str | None = None,
) -> dict[str, Any]:
    # Workbook gate (D-051): key được truyền từ nguồn ĐỌC (nguồn thật hiện hành) — nếu
    # không truyền thì dùng key lưu trong chính snapshot; key khác workbook gốc → không phần loại hoàn.
    effective_workbook_key = workbook_key if workbook_key is not None else report.get("spreadsheet_key")
    customers = report.get("customers") or []
    for customer in customers:
        headers = _header_columns(customer.get("source_analysis") or {})
        columns = {
            "USD": _find_column(headers, lambda value: value in {"usd", "chi tieu usd", "spend usd"}),
            "VND": _find_column(headers, lambda value: value in {"vnd", "chi tieu vnd", "spend vnd"}),
        }
        for row in customer.get("account_rows") or []:
            currency = row.get("account_currency")
            column = columns.get(currency)
            cell = _source_cells(row).get(column) if column else None
            value = _decimal(cell.get("value")) if cell else None
            if value is not None and (not value.is_finite() or cell.get("address") in row.get("missing_inputs", [])):
                value = None
            row["original_spend"] = {
                "value": _decimal_text(value) if value is not None else None,
                "currency": currency,
                "source": cell.get("address") if cell else None,
            }

    fields = {
        "opening_balance": ("opening_balance", None),
        "budget_deposits_vnd": ("tab_source_totals", "budget_deposits_vnd"),
        "spend_vnd": ("tab_source_totals", "spend_vnd"),
        "fee": ("tab_source_totals", "fee"),
        "billing_total": ("tab_source_totals", "billing_total"),
        "current_balance": ("tab_source_totals", "current_balance"),
    }
    metrics: dict[str, Any] = {}
    for field, (container, key) in fields.items():
        amounts: list[Decimal] = []
        contributions = []
        missing = []
        for customer in customers:
            raw = customer.get(container) or {}
            item = raw if key is None else raw.get(key) or {}
            amount = _decimal(item.get("value"))
            if amount is None or not amount.is_finite():
                missing.append(customer["source_sheet"])
            else:
                amounts.append(amount)
                contributions.append({"customer": customer["source_sheet"], "source": item.get("source"), "value": _decimal_text(amount)})
        metrics[field] = {
            "value": _decimal_text(exact_decimal_sum(amounts)) if contributions else None,
            "complete_customers": len(contributions), "total_customers": len(customers),
            "missing_customers": missing, "contributions": contributions,
            "status": "PARTIAL" if missing or not customers else "COMPLETE",
        }

    usdt_amounts: list[Decimal] = []
    usdt_contributions: list[dict[str, Any]] = []
    usdt_refund_amounts: list[Decimal] = []
    usdt_refund_contributions: list[dict[str, Any]] = []
    usdt_net_amounts: list[Decimal] = []
    usdt_missing: list[str] = []
    complete_usdt = 0
    for customer in customers:
        title = customer["source_sheet"]
        valid = []
        uncertain = not source_period or customer.get("profile_status") in {"SOURCE_ERROR", "STRUCTURE_ERROR"}
        deposits = customer.get("deposits") or []
        if any(
            cell and cell.get("formula") and cell.get("value") in (None, "")
            for row in customer.get("source_rows") or [] if row.get("row_number", 0) >= 4
            for cell in [_source_cells(row).get("J")]
        ):
            uncertain = True
        for deposit in deposits:
            if not deposit.get("included"):
                if "Dòng tổng hoặc công thức cộng cột J" not in (deposit.get("exclusion_reason") or ""):
                    uncertain = True
                continue
            amount = _decimal(deposit.get("amount_usdt"))
            day = deposit.get("business_date")
            if amount is None or not amount.is_finite() or not day:
                uncertain = True
            elif source_period and day.startswith(source_period):
                valid.append((deposit, amount))
        if customer.get("usdt_receipts_state") == "NEEDS_REVIEW":
            uncertain = True
        if not deposits and customer.get("usdt_receipts_state") != "NO_RECORDED":
            uncertain = True
        receipt_sum = Decimal(0)
        refund_sum = Decimal(0)
        for deposit, amount in valid:
            if _effective_deposit_kind(deposit, amount, title, source_period, effective_workbook_key) == "REFUND":
                # amount âm (giá nguồn); quy đổi thành magnitude dương để hiển thị.
                refund_sum += -amount
                usdt_refund_amounts.append(-amount)
                usdt_refund_contributions.append({
                    "customer": title, "source": deposit.get("source_cells", []),
                    "date": deposit.get("business_date"), "value": _decimal_text(-amount),
                })
            else:
                receipt_sum += amount
                usdt_amounts.append(amount)
                usdt_contributions.append({
                    "customer": title, "source": deposit.get("source_cells", []),
                    "date": deposit.get("business_date"), "value": _decimal_text(amount),
                })
        if receipt_sum or refund_sum:
            usdt_net_amounts.append(receipt_sum - refund_sum)
        if uncertain:
            usdt_missing.append(title)
        else:
            complete_usdt += 1
    metrics["usdt_received"] = {
        "value": _decimal_text(exact_decimal_sum(usdt_amounts)) if complete_usdt or usdt_contributions else None,
        "complete_customers": complete_usdt, "total_customers": len(customers),
        "missing_customers": usdt_missing, "contributions": usdt_contributions,
        "status": "PARTIAL" if usdt_missing or not customers else "COMPLETE",
    }
    metrics["usdt_refunded"] = {
        "value": _decimal_text(exact_decimal_sum(usdt_refund_amounts)) if complete_usdt or usdt_refund_contributions else None,
        "complete_customers": complete_usdt, "total_customers": len(customers),
        "missing_customers": usdt_missing, "contributions": usdt_refund_contributions,
        "status": "PARTIAL" if usdt_missing or not customers else "COMPLETE",
    }
    metrics["usdt_net"] = {
        "value": _decimal_text(exact_decimal_sum(usdt_net_amounts)) if complete_usdt or usdt_net_amounts else None,
        "complete_customers": complete_usdt, "total_customers": len(customers),
        "missing_customers": usdt_missing, "contributions": [],
        "status": "PARTIAL" if usdt_missing or not customers else "COMPLETE",
    }
    report["all_customer_totals"] = {"period": source_period, "metrics": metrics}
    report["company_totals"] = _company_summary_totals(report, source_period)
    return report


def build_sheets_source_report(
    connector: GoogleSheetsConnector, *, source_period: str | None = None,
    mapping_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read summary tabs and only detail tabs directly linked by source formulas."""
    all_metas = connector.list_sheets()
    hidden_titles = [str(meta["title"]) for meta in all_metas if meta.get("hidden")]
    hidden_keys = {title.casefold() for title in hidden_titles}
    sheet_metas = [meta for meta in all_metas if not meta.get("hidden")]
    titles = [str(meta.get("title") or "") for meta in all_metas]
    meta_by_title = {str(meta.get("title") or "").casefold(): meta for meta in sheet_metas}
    summaries = [
        meta for meta in sheet_metas
        if sheets_structure.classify_sheet(str(meta.get("title") or "")) == sheets_structure.SHEET_SUMMARY
    ]
    issues: list[dict[str, Any]] = []
    summary_payloads: list[dict[str, Any]] = []
    customer_links: dict[str, list[dict[str, Any]]] = defaultdict(list)
    details: dict[str, dict[str, Any]] = {}
    analyses: dict[str, dict[str, Any]] = {}

    for summary_meta in summaries:
        title = str(summary_meta["title"])
        try:
            detail = connector.read_sheet_detail(title)
        except SheetsAPIError as exc:
            issues.append(
                {"severity": "error", "source": title, "message": str(exc), "sheet_id": summary_meta.get("sheet_id")}
            )
            continue
        details[title.casefold()] = detail
        analyses[title.casefold()] = sheets_structure.analyze_sheet_detail(detail)
        preview = sheets_structure.build_cell_preview(detail)
        header_row_number = (analyses[title.casefold()].get("header_row_index") or 0) + 1
        summary_header_cells = _source_cells(
            next(
                (row for row in preview.get("rows") or [] if row["row_number"] == header_row_number),
                {},
            )
        )
        closing_balance_column = next(
            (
                letter
                for letter, cell in summary_header_cells.items()
                if _norm(cell.get("value")) in {"con", "so du cuoi ky", "balance"}
            ),
            None,
        )
        rows: list[dict[str, Any]] = []
        for source_row in preview.get("rows") or []:
            cells = _source_cells(source_row)
            label_value = cells.get("A", {}).get("value")
            label = str(label_value).strip() if label_value not in (None, "") else None
            if not label:
                continue
            if label.casefold() in hidden_keys:
                continue
            formula_cells = [
                cell for cell in source_row.get("cells") or [] if cell.get("formula")
            ]
            refs_with_sources = [
                (cell, referenced_title)
                for cell in formula_cells
                for referenced_title in _sheet_references(cell.get("formula"), titles)
            ]
            refs = sorted({name for _, name in refs_with_sources})
            for cell, referenced_title in refs_with_sources:
                if referenced_title.casefold() in hidden_keys:
                    issues.append({
                        "severity": "warning",
                        "source": f"{title}!{cell['address']}",
                        "message": "Công thức phụ thuộc tab ẩn; giữ kết quả nguồn, không đọc tab ẩn và chưa kiểm tra phụ thuộc.",
                        "references": [referenced_title],
                    })
            candidate_meta = meta_by_title.get(label.casefold())
            directly_linked = bool(
                candidate_meta
                and sheets_structure.classify_sheet(label) == sheets_structure.SHEET_CUSTOMER
                and any(name.casefold() == label.casefold() for name in refs)
            )
            customer_title = str(candidate_meta["title"]) if directly_linked and candidate_meta else None
            linked_row = {
                "summary_sheet": title,
                "summary_row": source_row["row_number"],
                "customer_label": label,
                "customer_sheet": customer_title,
                "link_status": "LINKED_BY_LABEL_AND_FORMULA" if customer_title else "NEEDS_CONFIRMATION",
                "unresolved_references": [
                    {"sheet": name, "cells": sorted({cell.get("address") for cell, ref in refs_with_sources if ref == name})}
                    for name in refs
                    if not customer_title or name.casefold() != customer_title.casefold()
                ],
                "cells": source_row.get("cells") or [],
                "opening_balance_refers_to_source": any(
                    cell.get("address") == "C" + str(source_row["row_number"])
                    and f"{label}!J1".casefold() in str(cell.get("formula") or "").replace("'", "").casefold()
                    for cell in formula_cells
                ) if label == "JOKER" else False,
                "closing_balance_value": cells.get(closing_balance_column, {}).get("value")
                if closing_balance_column
                else None,
                "closing_balance_formula": cells.get(closing_balance_column, {}).get("formula")
                if closing_balance_column
                else None,
                "closing_balance_source": cells.get(closing_balance_column, {}).get("address")
                if closing_balance_column
                else None,
            }
            rows.append(linked_row)
            if customer_title:
                customer_links[customer_title.casefold()].append(linked_row)
            elif refs or label.casefold() in {item.casefold() for item in titles}:
                issues.append(
                    {
                        "severity": "warning",
                        "source": f"{title}!A{source_row['row_number']}",
                        "message": "Dòng summary chưa liên kết được duy nhất với tab khách bằng cả nhãn và công thức; không nhập vào tổng khách.",
                        "references": refs,
                    }
                )
        summary_payloads.append(
            {
                "title": title,
                "sheet_id": summary_meta.get("sheet_id"),
                "header_row": (
                    header_row_number
                ),
                "rows": rows,
                "source_columns": _header_columns(analyses[title.casefold()]),
                "source_analysis": analyses[title.casefold()],
            }
        )

    customers: list[dict[str, Any]] = []
    linked_titles = list(
        dict.fromkeys(
            row["customer_sheet"]
            for rows in customer_links.values()
            for row in rows
            if row.get("customer_sheet")
        )
    )
    for title in linked_titles:
        meta = meta_by_title[title.casefold()]
        try:
            detail = details.get(title.casefold()) or connector.read_sheet_detail(title)
            customers.append(_build_customer_report(
                meta, detail, customer_links[title.casefold()], hidden_titles, source_period, mapping_config,
                workbook_key=connector.spreadsheet_key,
            ))
        except SheetsAPIError as exc:
            issue = {
                "severity": "error",
                "source": title,
                "message": str(exc),
                "sheet_id": meta.get("sheet_id"),
            }
            issues.append(issue)
            customers.append(
                {
                    "display_name": customer_links[title.casefold()][0]["customer_label"],
                    "source_sheet": title,
                    "sheet_id": meta.get("sheet_id"),
                    "profile_status": "SOURCE_ERROR",
                    "source_periods": [],
                    "source_rows": [],
                    "daily": [],
                    "deposits": [],
                    "issues": [issue],
                }
            )

    errors = any(issue["severity"] == "error" for issue in issues)
    incomplete_customers = any(
        customer.get("completeness_status") == "NEEDS_REVIEW"
        for customer in customers
    )
    unresolved_summary_references = any(
        row.get("unresolved_references")
        for summary in summary_payloads
        for row in summary["rows"]
    )
    return _exact_json(enrich_sheets_report({
        "mode": connector.mode,
        "status": "PARTIAL" if errors or incomplete_customers or unresolved_summary_references else ("READY" if customers else "NEEDS_CONFIRMATION"),
        "spreadsheet_key": connector.spreadsheet_key,
        "read_at": datetime.now().astimezone().isoformat(),
        "workbook_tab_count": len(all_metas),
        "summary_tabs": summary_payloads,
        "customers": customers,
        "issues": issues,
        "mapping_status": "PREVIEW_NEEDS_CONFIRMATION",
        "meta_reconciliation_status": "NOT_COMPARED",
        "notes": [
            "Summary và chi tiết hiển thị tách biệt; không cộng summary với các dòng chi tiết.",
            "Chỉ đọc tab khách được summary liên kết trực tiếp bằng nhãn tab và công thức.",
            "Các mapping chưa xác nhận được hiển thị trạng thái; không tự lưu CONFIRMED.",
        ],
    }, source_period))
