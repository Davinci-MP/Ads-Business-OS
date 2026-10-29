"""Kiểm thử S6+ — phân tích chi tiết bảng Google Sheets thật (mô phỏng qua mock).

Các case theo yêu cầu chủ dự án: ngày 25/10, ID tài khoản số dài, merged cells,
hàng phân cách màu, ô công thức, tiền USD/VND, số nguyên/thập phân theo locale,
mơ hồ → NEEDS_CONFIRMATION (Q-007). Mọi dữ liệu là fixture — KHÔNG đụng bảng thật.
"""

import json
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.connectors.sheets import (
    GoogleSheetsConnector,
    MockSheetsConnector,
    SheetsAPIError,
    parse_spreadsheet_url,
)
from app.main import app
from app.db import get_db
from app.models import AuditLog, SheetMapping
from app.services import sheets_structure

CLEAN_TABLES = (SheetMapping, AuditLog)


@pytest.fixture(autouse=True)
def _clean_tables(db):
    yield
    db.rollback()
    for model in CLEAN_TABLES:
        db.execute(delete(model))
    db.commit()


def _no_token_env(monkeypatch):
    for name in (
        "ADSOS_GOOGLE_SHEETS_ACCESS_TOKEN",
        "ADSOS_GOOGLE_SHEETS_SPREADSHEET_ID",
        "ADSOS_GOOGLE_SERVICE_ACCOUNT_FILE",
        "ADSOS_GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(name, raising=False)


# --- Spreadsheet URL/ID ---


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://docs.google.com/spreadsheets/d/1AbC_def-GHIJKLmnopQRs_tuV/edit#gid=0", "1AbC_def-GHIJKLmnopQRs_tuV"),
        ("https://docs.google.com/spreadsheets/d/1AbC_def-GHIJKLmnopQRs_tuV", "1AbC_def-GHIJKLmnopQRs_tuV"),
        ("1AbC_def-GHIJKLmnopQRs_tuV", "1AbC_def-GHIJKLmnopQRs_tuV"),
    ],
)
def test_parse_spreadsheet_url(raw, expected):
    assert parse_spreadsheet_url(raw) == expected


@pytest.mark.parametrize("bad", ["", "   ", "https://drive.google.com/file/d/xyz", "dões not match"])
def test_parse_spreadsheet_url_invalid(bad):
    with pytest.raises(ValueError):
        parse_spreadsheet_url(bad)


# --- normalize_cell: ngày, ID dài, tiền tệ, số theo locale ---


@pytest.mark.parametrize(
    "raw,kind,value,ambiguous",
    [
        ("25/10", "date", "25/10", False),  # 25>12 → chắc chắn dd/MM (VN)
        ("25/10/2026", "date", "25/10/2026", False),  # 25>12 → chắc chắn dd/MM (VN)
        ("10/25", "date", "10/25", False),  # 25>12 ở vị trí 2 → chắc chắn MM/dd
        ("11/02", "date", "11/02", True),  # đối xứng D-026 — không tự đoán
        ("05/05", "date", "05/05", False),  # giống nhau → cùng ngày
        ("3491929321209045", "id", "3491929321209045", False),  # 16 số → ID, giữ string
        ("1234567890", "number", 1234567890.0, False),
        ("$1,234.56", "number", 1234.56, False),
        ("1.234.567₫", "number", 1234567.0, False),
        ("25.500,75", "number", 25500.75, False),
        ("1,5", "number", 1.5, False),
        ("25,500", "number", 25500.0, True),  # grouping đơn không format → mơ hồ
    ],
)
def test_normalize_cell_s6plus(raw, kind, value, ambiguous):
    result = sheets_structure.normalize_cell(raw)
    assert result["kind"] == kind
    assert result["value"] == value
    assert result["ambiguous"] is ambiguous


# --- fixture bảng khách hàng mô phỏng bảng thật (Q-007) ---

_CUSTOMER_SHEET = "Chi tiêu KH A"
_CUSTOMER_ROWS = [
    # banner có màu, sẽ bị loại khỏi header search (1 ô non-empty + màu)
    [{"value": "BẢNG CHI TIÊU THÁNG 10 — KH A", "bg": (0.85, 0.85, 1.0)}],
    ["Ngày", "ID tài khoản", "Chi tiêu (USD)", "Tỷ giá", "Phí dịch vụ", "Tổng VND"],
    # 0-based data row 2 (dòng sheet thứ 3)
    [
        {"value": 45124, "nf": {"type": "DATE", "pattern": "d/M/yyyy"}, "formatted": "25/10/2026"},
        "3491929321209045",
        {"value": 1234.56, "nf": {"type": "CURRENCY", "pattern": '"US$"#,##0.00'}, "formatted": "US$1,234.56"},
        {"value": 25500, "nf": {"type": "NUMBER", "pattern": "#,##0"}, "formatted": "25.500"},
        {"value": 49.38, "nf": {"type": "NUMBER", "pattern": "0.00"}, "formatted": "49,38"},
        {"value": 62983920.0, "formula": "=C3*D3+E3", "nf": {"type": "NUMBER", "pattern": "#,##0"}, "formatted": "62.983.920"},
    ],
    # hàng phân cách màu giữa bảng
    [{"value": "Tổng tháng 10", "bg": (1.0, 0.9, 0.7)}],
    [
        {"value": 45125, "nf": {"type": "DATE", "pattern": "d/M/yyyy"}, "formatted": "26/10/2026"},
        "3491929321209045",
        {"value": 888.11, "nf": {"type": "CURRENCY", "pattern": '"US$"#,##0.00'}, "formatted": "US$888.11"},
        {"value": 25500, "nf": {"type": "NUMBER", "pattern": "#,##0"}, "formatted": "25.500"},
        {"value": 35.52, "nf": {"type": "NUMBER", "pattern": "0.00"}, "formatted": "35,52"},
        {"value": 22646811.52, "formula": "=C5*D5+E5", "nf": {"type": "NUMBER", "pattern": "#,##0"}, "formatted": "22.646.812"},
    ],
]


def _customer_connector():
    return MockSheetsConnector(
        workbook={_CUSTOMER_SHEET: _CUSTOMER_ROWS},
        locale="vi_VN",
        merges={_CUSTOMER_SHEET: [{"start_row": 0, "end_row": 1, "start_col": 0, "end_col": 6}]},
    )


def _customer_detail_analysis():
    connector = _customer_connector()
    return sheets_structure.analyze_sheet_detail(connector.read_sheet_detail(_CUSTOMER_SHEET))


# --- analyze_sheet_detail: banner/merged/màu/formula/nf ---


def test_detail_header_after_banner_and_merge():
    result = _customer_detail_analysis()
    assert result["header_row_index"] == 1
    assert result["locale"] == "vi_VN"
    assert result["merges"] == [{"start_row": 0, "end_row": 1, "start_col": 0, "end_col": 6}]
    assert any("merge" in note for note in result["notes"])
    # banner row 0 có màu + 1 ô non-empty → bị phân loại hàng phân cách màu (loại khỏi header search)
    assert any(("banner" in note) or ("phân cách màu" in note) for note in result["notes"])


def test_detail_separator_color_row_excluded():
    result = _customer_detail_analysis()
    # banner row 0 (màu, 1 ô) và hàng phân cách dòng 4 đều bị loại khỏi thống kê
    assert set(result["separator_rows"]) == {0, 3}
    assert any("phân cách màu" in note for note in result["notes"])
    # cột dữ liệu phải bỏ qua các hàng này khi thống kê
    spend_col = result["columns"][2]
    assert spend_col["samples"][0] == 1234.56


def test_detail_formula_cells_detected():
    result = _customer_detail_analysis()
    assert result["formula_cells"] == ["F3", "F5"]
    total_col = result["columns"][5]
    assert total_col["has_formula"] is True
    assert any("công thức" in note for note in result["notes"])


def test_detail_number_format_and_currency():
    result = _customer_detail_analysis()
    spend_col = result["columns"][2]
    assert spend_col["number_format"] == {"type": "CURRENCY", "pattern": '"US$"#,##0.00', "currency": "USD"}
    assert spend_col["format_source"] == "number_format"
    assert spend_col["needs_confirmation"] is False
    rate_col = result["columns"][3]
    assert rate_col["number_format"]["currency"] is None
    assert rate_col["number_format"]["type"] == "NUMBER"


@pytest.mark.parametrize(
    "pattern,expected",
    [
        ('#,##0 [$đ-42A]', "VND"),
        ('"US$"#,##0.00', "USD"),
        ('"$"#,##0.00', None),
    ],
)
def test_currency_format_does_not_assume_bare_dollar_is_usd(pattern, expected):
    connector = MockSheetsConnector(
        workbook={
            "Currency": [
                ["Amount"],
                [{"value": 1234, "nf": {"type": "CURRENCY", "pattern": pattern}, "formatted": "1.234"}],
            ]
        }
    )
    result = sheets_structure.analyze_sheet_detail(connector.read_sheet_detail("Currency"))
    assert result["columns"][0]["number_format"]["currency"] == expected


def test_detail_kinds_long_id_and_date():
    result = _customer_detail_analysis()
    id_col = result["columns"][1]
    assert id_col["kind_majority"] == "id"
    date_col = result["columns"][0]
    assert date_col["kind_majority"] == "number"  # numberValue chuẩn từ Google (serial ngày)
    assert date_col["number_format"]["type"] == "DATE"


def test_detail_ambiguous_text_numbers_flagged():
    """Cột text-số KHÔNG có numberFormat, grouping đơn → NEEDS_CONFIRMATION."""
    connector = MockSheetsConnector(
        workbook={
            "Nhập tay": [
                ["Số tiền / Ngày", "Ghi chú"],
                ["25,500", "chưa rõ định dạng"],
                ["11/02", "ghi chú thường"],
            ]
        }
    )
    result = sheets_structure.analyze_sheet_detail(connector.read_sheet_detail("Nhập tay"))
    amount_col = result["columns"][0]
    assert amount_col["needs_confirmation"] is True
    reasons = " ".join(amount_col["confirm_reasons"])
    assert "Q-007" in reasons
    assert "dd/MM" in reasons  # ngày 11/02 mơ hồ cũng nằm trong cột này
    note_col = result["columns"][1]
    assert note_col["kind_majority"] == "text"
    assert note_col["needs_confirmation"] is False  # text thường → không mơ hồ


def test_detail_vnd_currency_pattern():
    connector = MockSheetsConnector(
        workbook={
            "VND": [
                ["Ngày", "Chi tiêu (VND)"],
                ["25/10/2026", {"value": 1500000, "nf": {"type": "CURRENCY", "pattern": '#,##0 "₫"'}, "formatted": "1.500.000 ₫"}],
            ]
        }
    )
    result = sheets_structure.analyze_sheet_detail(connector.read_sheet_detail("VND"))
    col = result["columns"][1]
    assert col["number_format"]["currency"] == "VND"
    assert col["kind_majority"] == "number"


# --- propose_mapping: role mới + preview nguồn→đích ---


def test_propose_roles_fee_total_rate_account():
    structure = sheets_structure.analyze_workbook_detailed(_customer_connector())
    proposals = sheets_structure.propose_mapping(structure)
    by_letter = {p["column_letter"]: p for p in proposals}
    assert by_letter["A"]["role"] == sheets_structure.ROLE_DATE
    assert by_letter["B"]["role"] == sheets_structure.ROLE_ACCOUNT
    assert by_letter["C"]["role"] == sheets_structure.ROLE_SPEND
    assert by_letter["D"]["role"] == sheets_structure.ROLE_RATE
    assert by_letter["E"]["role"] == sheets_structure.ROLE_FEE
    assert by_letter["F"]["role"] == sheets_structure.ROLE_TOTAL


def test_propose_preview_source_and_target():
    structure = sheets_structure.analyze_workbook_detailed(_customer_connector())
    proposals = sheets_structure.propose_mapping(structure)
    spend = next(p for p in proposals if p["column_letter"] == "C")
    assert spend["source"]["sheet"] == _CUSTOMER_SHEET
    assert spend["source"]["column_letter"] == "C"
    assert spend["source"]["header"] == "Chi tiêu (USD)"
    assert spend["source"]["samples_formatted"][0] == "US$1,234.56"
    assert spend["source"]["number_format"].endswith("[USD]")
    assert spend["target"] == {"area": "spend_snapshots", "field": "spend_value (tổng tích lũy)"}
    total = next(p for p in proposals if p["column_letter"] == "F")
    assert total["target"]["area"] == "đối soát"
    assert total["source"]["has_formula"] is True
    assert total["confidence"] == "high"


# --- live read_sheet_detail (mock httpx) ---


def _live_grid_payload():
    return {
        "properties": {"locale": "vi_VN"},
        "sheets": [
            {
                "properties": {"title": "Chi tiêu", "sheetId": 0, "gridProperties": {"rowCount": 2, "columnCount": 3}},
                "merges": [{"startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 3}],
                "data": [
                    {
                        "startRow": 0,
                        "startColumn": 0,
                        "rowData": [
                            {
                                "values": [
                                    {
                                        "userEnteredValue": {"stringValue": "Tiêu đề"},
                                        "effectiveValue": {"stringValue": "Tiêu đề"},
                                        "formattedValue": "Tiêu đề",
                                    },
                                    {
                                        "userEnteredValue": {"formulaValue": "=A1"},
                                        "effectiveValue": {"stringValue": "Tiêu đề"},
                                        "formattedValue": "Tiêu đề",
                                    },
                                    {
                                        "userEnteredValue": {"numberValue": 25500.25},
                                        "effectiveValue": {"numberValue": 25500.25},
                                        "formattedValue": "25.500,25",
                                        "effectiveFormat": {
                                            "numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"},
                                            "backgroundColor": {"red": 1, "green": 0.9, "blue": 0.7},
                                        },
                                    },
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_live_read_sheet_detail(monkeypatch):
    payload = _live_grid_payload()

    def fake_get(url, params=None, headers=None, timeout=None):
        assert "includeGridData" in params
        captured = {"url": url, "params": params, "headers": headers}
        return type(
            "R",
            (),
            {
                "status_code": 200,
                "json": staticmethod(lambda **kwargs: json.loads(json.dumps(payload), **kwargs)),
            },
        )()

    monkeypatch.setattr("app.connectors.sheets.httpx.get", fake_get)
    connector = GoogleSheetsConnector(spreadsheet_id="sheet_live_2", access_token="tok", use_mock=False)
    detail = connector.read_sheet_detail("Chi tiêu")
    assert detail["locale"] == "vi_VN"
    assert detail["rows"] == [["Tiêu đề", "Tiêu đề", Decimal("25500.25")]]
    assert detail["cells"][0][1]["formula"] == "=A1"
    assert detail["cells"][0][2]["nf_type"] == "NUMBER"
    assert detail["cells"][0][2]["nf_pattern"] == "#,##0.00"
    assert detail["merges"] == [{"start_row": 0, "end_row": 1, "start_col": 0, "end_col": 3}]
    result = sheets_structure.analyze_sheet_detail(detail)
    assert result["header_row_index"] is None  # hàng đầu chỉ 1 ô non-empty hiệu dụng (còn bị merge che)
    assert any(("banner" in note) or ("phân cách màu" in note) for note in result["notes"])


@pytest.mark.parametrize("title", ["PEDRI", "LOCK", "TOMMY", "HUNTER"])
def test_live_reads_restrict_confirmed_tabs_to_columns_a_through_l(title, monkeypatch):
    detail_payload = _live_grid_payload()
    values = detail_payload["sheets"][0]["data"][0]["rowData"][0]["values"]
    values.extend({"effectiveValue": {"stringValue": f"column-{index}"}} for index in range(3, 13))
    detail_payload["sheets"][0]["merges"].append(
        {"startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 1, "endColumnIndex": 3}
    )
    detail_payload["sheets"][0]["merges"].append(
        {"startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 12, "endColumnIndex": 14}
    )
    detail_payload["sheets"][0]["merges"].append(
        {"startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 11, "endColumnIndex": 13}
    )
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params))
        if "includeGridData" in (params or {}):
            payload = detail_payload
        else:
            payload = {"values": [[f"column-{index}" for index in range(13)]]}
        return type(
            "R",
            (),
            {
                "status_code": 200,
                "json": staticmethod(lambda **kwargs: json.loads(json.dumps(payload), **kwargs)),
            },
        )()

    monkeypatch.setattr("app.connectors.sheets.httpx.get", fake_get)
    connector = GoogleSheetsConnector(spreadsheet_id="sheet_live_4", access_token="tok", use_mock=False)

    grid = connector.read_grid(title)
    detail = connector.read_sheet_detail(title)

    assert calls[0][0].endswith(f"/values/'{title}'!A:L")
    assert grid["rows"] == [[f"column-{index}" for index in range(12)]]
    assert grid["read_scope"] == "A:L"
    assert calls[1][1]["ranges"] == f"'{title}'!A:L"
    assert len(detail["rows"][0]) == len(detail["cells"][0]) == 12
    assert detail["rows"][0][1] == "Tiêu đề"
    assert detail["rows"][0][11] == "column-11"
    assert detail["read_scope"] == "A:L"
    assert detail["merges"] == [
        {"start_row": 0, "end_row": 1, "start_col": 0, "end_col": 3},
        {"start_row": 0, "end_row": 1, "start_col": 1, "end_col": 3},
        {"start_row": 1, "end_row": 2, "start_col": 11, "end_col": 13},
    ]


def test_live_reads_leave_other_tabs_unrestricted(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return type(
            "R",
            (),
            {
                "status_code": 200,
                "json": staticmethod(lambda **kwargs: json.loads(json.dumps(_live_grid_payload()), **kwargs)),
            },
        )()

    monkeypatch.setattr("app.connectors.sheets.httpx.get", fake_get)
    connector = GoogleSheetsConnector(spreadsheet_id="sheet_live_5", access_token="tok", use_mock=False)
    detail = connector.read_sheet_detail("JOKER")

    assert captured["params"]["ranges"] == "JOKER"
    assert detail.get("read_scope") is None
    assert detail["rows"] == [["Tiêu đề", "Tiêu đề", Decimal("25500.25")]]


def test_live_read_sheet_detail_missing_sheet(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return type(
            "R",
            (),
            {"status_code": 200, "json": staticmethod(lambda **kwargs: {"sheets": []})},
        )()

    monkeypatch.setattr("app.connectors.sheets.httpx.get", fake_get)
    connector = GoogleSheetsConnector(spreadsheet_id="sheet_live_3", access_token="tok", use_mock=False)
    with pytest.raises(SheetsAPIError):
        connector.read_sheet_detail("Không Có")


def test_build_cell_preview_keeps_exact_references_blank_values_and_formulas():
    preview = sheets_structure.build_cell_preview(
        {
            "title": "Source",
            "locale": "vi_VN",
            "start_row": 2,
            "start_column": 1,
            "grid_rows": 1,
            "grid_columns": 4,
            "rows": [["Client", None, 25.5]],
            "cells": [[
                {"formatted": "Client"},
                {"formula": "=SUM(D3:D4)", "formatted": "25,5"},
                {"nf_type": "NUMBER", "nf_pattern": "0.0", "formatted": "25,5"},
            ]],
            "merges": [{"start_row": 2, "end_row": 3, "start_col": 1, "end_col": 3}],
        }
    )

    assert preview["rows"][0]["row_number"] == 3
    cells = preview["rows"][0]["cells"]
    assert cells[0]["address"] == "B3"
    assert cells[1]["address"] == "C3"
    assert cells[1]["value"] is None
    assert cells[1]["formula"] == "=SUM(D3:D4)"
    assert cells[2]["address"] == "D3"
    assert cells[2]["value"] == 25.5
    assert preview["merges"][0]["range"] == "B3:C3"


# --- endpoints: nhập URL/ID + preview ---


def test_endpoint_analyze_mock_and_missing_token(db, monkeypatch):
    _no_token_env(monkeypatch)
    app.dependency_overrides[get_db] = lambda: iter([db])
    try:
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # không truyền spreadsheet → mock mặc định
        response = client.post("/api/v1/sheets/analyze", json={"spreadsheet": ""})
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "mock"
        assert data["spreadsheet_key"] == "mock"
        assert data["structure"]["sheets"]
        assert data["proposals"]

        # URL hợp lệ nhưng thiếu token → 400 + hướng dẫn, KHÔNG fallback mock
        response = client.post("/api/v1/sheets/analyze", json={"spreadsheet": "https://docs.google.com/spreadsheets/d/1AbC_def-GHIJKLmnopQRs_tuV/edit"})
        assert response.status_code == 400
        assert "ADSOS_GOOGLE_SHEETS_ACCESS_TOKEN" in response.json()["detail"]

        # URL sai → 400
        response = client.post("/api/v1/sheets/analyze", json={"spreadsheet": "không phải url"})
        assert response.status_code == 400

        # response không lộ secret
        mode = client.get("/api/v1/sheets/mode").json()
        assert set(mode.keys()) == {"mode", "spreadsheet_id_configured", "auth"}
        assert mode["auth"] in {"none", "access_token", "service_account"}
    finally:
        app.dependency_overrides.clear()


def test_endpoint_read_only_preview_selects_sheet_id_without_persisting(monkeypatch):
    connector = MockSheetsConnector(
        workbook={
            "Chi tiêu KH A": [
                ["Ngày", "Chi tiêu", "Tổng"],
                ["25/10/2026", 100, {"value": 104, "formula": "=B2*1.04", "formatted": "104"}],
            ]
        }
    )
    monkeypatch.setattr("app.api.v1.sheets._connector_for", lambda spreadsheet: connector)

    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.post(
        "/api/v1/sheets/preview",
        json={"spreadsheet": "read-only-test", "sheet_id": 0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["preview_status"] == "PREVIEW"
    assert data["mapping_status"] == "NEEDS_CONFIRMATION"
    assert data["source"]["title"] == "Chi tiêu KH A"
    assert data["source"]["rows"][1]["cells"][2]["address"] == "C2"
    assert data["source"]["rows"][1]["cells"][2]["formula"] == "=B2*1.04"
    assert connector.calls["read_sheet_detail"] == 1

    missing = client.post(
        "/api/v1/sheets/preview",
        json={"spreadsheet": "read-only-test", "sheet_id": 999},
    )
    assert missing.status_code == 404


def test_endpoint_persist_confirm_with_custom_key(db):
    connector = _customer_connector()
    structure = sheets_structure.analyze_workbook_detailed(connector)
    proposals = sheets_structure.propose_mapping(structure)
    sheets_structure.persist_proposals(db, "sheet_live_4", proposals, actor="owner")
    result = sheets_structure.confirm_sheet_mappings(db, "sheet_live_4", _CUSTOMER_SHEET, actor="owner")
    assert result["confirmed"] == 6
    rows = db.execute(
        select(SheetMapping).where(SheetMapping.spreadsheet_key == "sheet_live_4", SheetMapping.sheet_name == _CUSTOMER_SHEET)
    ).scalars().all()
    assert all(r.status == "CONFIRMED" for r in rows)
    audit = db.query(AuditLog).filter(AuditLog.action == "SHEET_MAPPING_CONFIRMED").all()
    assert len(audit) == 1
