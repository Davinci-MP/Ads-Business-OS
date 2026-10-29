"""Kiểm thử mapping/cấu trúc theo dữ liệu thật phát hiện ở phiên Live Read-only Q-007:

- Header thực tế ở dòng 3 (index 2) cho tab khách có summary banner phía trên;
  KHÔNG mặc định mọi tab đều header dòng 3.
- Ngày merge qua nhiều dòng gắn đúng từng dòng dữ liệu (resolve_row_dates).
- Phí theo công thức Sheets: 4% mặc định; LUNA 5% → NEEDS_CONFIRMATION riêng,
  KHÔNG tự kích hoạt; KHÔNG sửa công thức bảng gốc.
- Phân loại tab: TỔNG* = SUMMARY (chỉ đối soát), MẪU* = TEMPLATE,
  ALL/OLD = UNCLASSIFIED (KHÔNG tự đồng bộ), còn lại CUSTOMER.
- Mọi fixture chỉ mô phỏng cấu trúc đã đối chiếu — không phải dữ liệu thật.
"""

import pytest

from app.services.sheets_structure import (
    DEFAULT_FEE_RATE,
    SHEET_CUSTOMER,
    SHEET_SUMMARY,
    SHEET_TEMPLATE,
    SHEET_UNCLASSIFIED,
    analyze_sheet_detail,
    classify_sheet,
    fee_rate_from_formulas,
    propose_mapping,
    resolve_row_dates,
)


def _cell(cell: dict) -> dict:
    base = {"formula": None, "nf_type": None, "nf_pattern": None, "bg": (1, 1, 1), "formatted": None}
    base.update(cell)
    return base


def _plain_row(n: int = 12) -> list:
    return [_cell({}) for _ in range(n)]


def _sep_row(n: int = 12) -> list:
    return [_cell({"bg": (0.9, 0.92, 0.97)}) for _ in range(n)]


def _fee_row(row_number: int, fee: str) -> list:
    return [_cell({"formula": f"=F{row_number}{fee}", "nf_type": "CURRENCY", "nf_pattern": "#,##0 [$đ]"})]


def _customer_tab_like(title: str = "JOKER", fee_percent: int = 4) -> dict:
    """Fixture mô phỏng cấu trúc tab khách: r0 summary, r1 nhãn phụ,
    r2 header thật, 2 khối ngày 5 dòng (4 account + 1 dòng phân cách màu)."""
    fee = f"*{fee_percent}%"
    return {
        "title": title,
        "locale": "vi_VN",
        "rows": [
            [title, None, None, None, None, 860087038.1, 34403481.52, 894490519.6, "T9/2026", 59908004, 794416627, -40165888.6],
            [None, None, None, None, None, None, None, None, None, None, "NS NHẬN", "CÒN"],
            ["NGÀY", "TÊN TK", "ID TK", "Tiêu", "USD", "VND", "Phí 4%", "Tổng", None, "USDT", None, "Tỉ giá"],
            [46296, "VND", "423573538237358", None, None, 12777832, None, 13288945.28, 27135, 3000, None, 26030],
            [None, "VND", "3295570687437341", None, None, 5318823, None, 5531575.92, 27135, 4000, None, 25990],
            [None, "USD", "1355087928516855", None, 72.5, None, None, None, 27135, None, None, None],
            [None, "USD", "351719144239227", None, None, None, None, None, 27135, None, None, None],
            [None] * 12,
            [46297, "VND", "423573538237358", None, None, 7737425, None, 8046922, 27135, None, None, None],
            [None, "USD", "787974509864195", None, 104.64, None, None, None, 27135, None, None, None],
        ],
        "cells": [
            _plain_row(),
            _plain_row(),
            _plain_row(),
            [
                _cell({"nf_type": "DATE", "nf_pattern": "d/m", "formatted": "1/10"}),
                _cell({"formatted": "VND"}),
                _cell({"formatted": "423573538237358"}),
                _cell({}),
                _cell({}),
                _cell({"nf_type": "CURRENCY", "nf_pattern": "#,##0 [$đ]", "formatted": "12.777.832 đ"}),
                _fee_row(4, fee)[0],
                _cell({"nf_type": "CURRENCY", "nf_pattern": "#,##0 [$đ]"}),
            ],
            [_fee_row(5, fee)[0]] + [_cell({}) for _ in range(11)],
            [_fee_row(6, fee)[0], _cell({"formula": "=E6*I6"})] + [_cell({}) for _ in range(10)],
            [_fee_row(7, fee)[0], _cell({"formula": "=E7*I7"})] + [_cell({}) for _ in range(10)],
            _sep_row(),
            [_fee_row(9, fee)[0]] + [_cell({}) for _ in range(11)],
            [_fee_row(10, fee)[0], _cell({"formula": "=E10*I10"})] + [_cell({}) for _ in range(10)],
        ],
        "merges": [
            {"start_row": 3, "end_row": 8, "start_col": 0, "end_col": 1},
            {"start_row": 7, "end_row": 8, "start_col": 0, "end_col": 9},
        ],
    }


def test_classify_special_tabs():
    assert classify_sheet("TỔNG T10") == SHEET_SUMMARY
    assert classify_sheet("MẪU RP") == SHEET_TEMPLATE
    assert classify_sheet("ALL") == SHEET_UNCLASSIFIED
    assert classify_sheet("OLD") == SHEET_UNCLASSIFIED
    assert classify_sheet("JOKER") == SHEET_CUSTOMER


def test_customer_tab_header_at_row3_not_row1():
    result = analyze_sheet_detail(_customer_tab_like("JOKER"))
    assert result["sheet_type"] == SHEET_CUSTOMER
    assert result["header_row_index"] == 2  # dòng 3 (1-indexed)
    assert any("dòng 3" in note for note in result["notes"])
    headers = [c["header"] for c in result["columns"]]
    assert "NGÀY" in headers and "ID TK" in headers and "Phí 4%" in headers


def test_fee_from_formula_4pct_confirmed_5pct_needs_confirmation():
    result = analyze_sheet_detail(_customer_tab_like("JOKER", fee_percent=4))
    fee_col = next(c for c in result["columns"] if "phí" in c["header"].lower())
    assert fee_col.get("fee_rate_from_formula") == pytest.approx(DEFAULT_FEE_RATE)
    assert fee_col["fee_confirmed"] is True
    assert fee_col["needs_confirmation"] is False

    luna = analyze_sheet_detail(_customer_tab_like("LUNA", fee_percent=5))
    fee_col_luna = next(c for c in luna["columns"] if "phí" in c["header"].lower())
    assert fee_col_luna["fee_rate_from_formula"] == pytest.approx(0.05)
    assert fee_col_luna["needs_confirmation"] is True
    assert any("D-021" in reason and "kích hoạt" in reason for reason in fee_col_luna["confirm_reasons"])
    # Đảm bảo KHÔNG tự kích hoạt: fee_confirmed phải là False
    assert fee_col_luna["fee_confirmed"] is False


def test_fee_rate_from_formulas_variants():
    assert fee_rate_from_formulas(["=F4*4%"]) == pytest.approx(0.04)
    assert fee_rate_from_formulas(["=F4*0.05"]) == pytest.approx(0.05)
    assert fee_rate_from_formulas(["=F4+G4"]) is None


def test_propose_mapping_special_tabs_not_synced():
    sheets = [
        analyze_sheet_detail(_customer_tab_like("ALPHA")),
        {"title": "MẪU RP", "sheet_type": SHEET_TEMPLATE, "row_count": 2, "header_row_index": None, "locale": "vi_VN", "merges": [], "separator_rows": [], "formula_cells": [], "columns": [], "notes": []},
        {"title": "OLD", "sheet_type": SHEET_UNCLASSIFIED, "row_count": 2, "header_row_index": None, "locale": "vi_VN", "merges": [], "separator_rows": [], "formula_cells": [], "columns": [], "notes": []},
        {"title": "TỔNG T10", "sheet_type": SHEET_SUMMARY, "row_count": 2, "header_row_index": None, "locale": "vi_VN", "merges": [], "separator_rows": [], "formula_cells": [], "columns": [], "notes": []},
    ]
    proposals = propose_mapping({"spreadsheet_key": "k", "sheets": sheets})
    assert any(p["sheet_name"] == "ALPHA" and p["role"] for p in proposals)
    for name in ("MẪU RP", "OLD", "TỔNG T10"):
        entry = next(p for p in proposals if p["sheet_name"] == name)
        assert entry["column_index"] < 0
        assert entry["role"] is None
        assert "KHÔNG tự đồng bộ" in entry["note"]
    assert {p["sheet_name"] for p in proposals} == {"ALPHA", "MẪU RP", "OLD", "TỔNG T10"}


def test_resolve_row_dates_merge_across_rows():
    detail = _customer_tab_like("JOKER")
    resolved = resolve_row_dates(detail)
    # r3..r6 (index 3..6) cùng một ngày 46296 nhờ merge cột A
    for row_index in (3, 4, 5, 6):
        assert resolved[row_index]["value"] == 46296
    assert resolved[3]["merge_span"] == [4, 8]
    # r7 là dòng phân cách (không có ngày riêng);
    # r8 được gán ngày 46297 (merge anchor vẫn r3->8 cột A? không — r8 chưa merge)
    assert 7 not in resolved or resolved[7]["value"] in (46296, 46297)
    assert resolved[8]["value"] == 46297
    assert not resolved[3]["ambiguous"]


def test_resolve_row_dates_ambiguous_date_flagged():
    detail = _customer_tab_like("X")
    detail["rows"][3][0] = "11/02"  # ngày dạng text mơ hồ dd/MM vs MM/dd
    resolved = resolve_row_dates(detail)
    assert resolved[3]["ambiguous"] is True
