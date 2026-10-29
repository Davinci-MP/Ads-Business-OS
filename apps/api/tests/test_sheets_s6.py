"""Kiểm thử S6 — Google Sheets connector + phân tích cấu trúc + mapping (D-024/D-028)."""

import pytest
from sqlalchemy import delete, func, select

from app.connectors.sheets import (
    GoogleSheetsConnector,
    MockSheetsConnector,
    SheetsAPIError,
    SheetsAuthError,
    build_connector,
)
from app.main import app
from app.db import get_db
from app.models import AuditLog, SheetMapping
from app.services import sheets_structure


# --- fixture dọn dẹp bảng mapping/audit ---

CLEAN_TABLES = (SheetMapping, AuditLog)


def _clean(db):
    for model in CLEAN_TABLES:
        db.execute(delete(model))
    db.commit()


@pytest.fixture(autouse=True)
def _clean_tables(db):
    yield
    db.rollback()
    _clean(db)


# --- connector: mock/live, bảo mật, chỉ đọc ---


def test_no_config_defaults_to_mock_mode():
    connector = build_connector()
    assert connector.mode == "mock"
    assert connector.spreadsheet_key == "mock"
    assert "token" not in repr(connector).lower()
    assert "Bearer" not in repr(connector)


def test_live_mode_when_spreadsheet_and_token_configured():
    connector = GoogleSheetsConnector(spreadsheet_id="sheet_live_1", access_token="tok", use_mock=False)
    assert connector.mode == "live"
    assert connector.spreadsheet_key == "sheet_live_1"
    assert connector.auth_method == "access_token"
    assert "secret-token" not in repr(connector)  # không lộ token qua repr/log
def test_mock_list_and_read_grid():
    connector = build_connector()
    titles = [s["title"] for s in connector.list_sheets()]
    assert "Chi tiêu" in titles and "Công nợ" in titles
    grid = connector.read_grid("Chi tiêu")
    assert grid["rows"][0][0] == "Ngày"
    with pytest.raises(SheetsAPIError):
        connector.read_grid("Sheet Không Tồn Tại")


def test_connector_has_no_write_methods():
    """D-024/D-028: connector chỉ đọc — introspection chặn surface ghi."""
    forbidden_prefixes = ("write", "update", "delete", "append", "clear", "set_", "batch", "patch")
    for cls in (GoogleSheetsConnector, MockSheetsConnector):
        for name in dir(cls):
            if name.startswith("_"):
                continue
            assert not any(name.startswith(prefix) for prefix in forbidden_prefixes), f"{cls.__name__}.{name}"


def test_live_api_errors(monkeypatch):
    connector = GoogleSheetsConnector(spreadsheet_id="sheet_x", access_token="tok", use_mock=False)

    class FakeResp:
        def __init__(self, status_code):
            self.status_code = status_code

        def json(self):
            return {}

    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResp(status)

    monkeypatch.setattr("app.connectors.sheets.httpx.get", fake_get)

    status = 401
    with pytest.raises(SheetsAuthError):
        connector.list_sheets()

    status = 500
    with pytest.raises(SheetsAPIError):
        connector.list_sheets()

    status = 200
    monkeypatch.setattr(
        "app.connectors.sheets.httpx.get",
        lambda url, params=None, headers=None, timeout=None: type(
            "R", (), {"status_code": 200, "json": staticmethod(lambda: {"sheets": [{"properties": {"sheetId": 1, "title": "S1", "gridProperties": {"rowCount": 5, "columnCount": 3}}}]})},
        )(),
    )
    sheets = connector.list_sheets()
    assert sheets == [{"sheet_id": 1, "title": "S1", "grid_rows": 5, "grid_columns": 3, "hidden": False}]


def test_hidden_metadata_blocks_direct_read_after_listing(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params))
        payload = {"sheets": [
            {"properties": {"sheetId": 1, "title": "VISIBLE", "hidden": False}},
            {"properties": {"sheetId": 2, "title": "HIDDEN", "hidden": True}},
        ]}
        return type("R", (), {"status_code": 200, "json": staticmethod(lambda **kwargs: payload)})()

    monkeypatch.setattr("app.connectors.sheets.httpx.get", fake_get)
    connector = GoogleSheetsConnector(spreadsheet_id="sheet_x", access_token="tok", use_mock=False)
    metas = connector.list_sheets()
    assert metas[1]["hidden"] is True
    assert "hidden" in calls[0][1]["fields"]
    with pytest.raises(SheetsAPIError):
        connector.read_grid("HIDDEN")
    with pytest.raises(SheetsAPIError):
        connector.read_sheet_detail("HIDDEN")
    assert len(calls) == 1


# --- normalize_cell ---


@pytest.mark.parametrize(
    "raw,kind,value",
    [
        (None, "empty", None),
        ("   ", "empty", None),
        ("", "empty", None),
        ("1,234.56", "number", 1234.56),
        ("1.234,56", "number", 1234.56),
        ("5.000.000", "number", 5000000.0),
        ("2,000,000", "number", 2000000.0),
        ("25,500", "number", 25500.0),
        ("25600", "number", 25600.0),
        (" VND 2.500.000 ", "number", 2500000.0),
        ("42", "number", 42.0),
        (42, "number", 42.0),
        ("đã đối soát", "text", "đã đối soát"),
        ("1025-KH Alpha", "text", "1025-KH Alpha"),
    ],
)
def test_normalize_cell(raw, kind, value):
    result = sheets_structure.normalize_cell(raw)
    assert result["kind"] == kind
    assert result["value"] == value


# --- phân tích cấu trúc + proposal ---


def test_analyze_workbook_mock_structure():
    connector = build_connector()
    structure = sheets_structure.analyze_workbook(connector)
    assert structure["spreadsheet_key"] == "mock"
    titles = {s["title"] for s in structure["sheets"]}
    assert titles == {"Chi tiêu", "Công nợ", "Khách hàng", "Tỷ giá"}
    spend_sheet = next(s for s in structure["sheets"] if s["title"] == "Chi tiêu")
    assert spend_sheet["header_row_index"] == 0
    col_spend = next(c for c in spend_sheet["columns"] if c["header"] == "Chi tiêu (USD)")
    assert col_spend["column_letter"] == "C"
    assert col_spend["kind_majority"] == "number"
    assert col_spend["non_empty_ratio"] == 1.0


def test_analyze_grid_skips_empty_header_column():
    grid = {"title": "S", "rows": [["", "X"], ["a", "1"]]}
    result = sheets_structure.analyze_grid(grid)
    assert [c["column_index"] for c in result["columns"]] == [1]
    assert any("A" in note for note in result["notes"])


def test_analyze_grid_no_header():
    grid = {"title": "S", "rows": [["", ""], ["", ""]]}
    result = sheets_structure.analyze_grid(grid)
    assert result["columns"] == []
    assert any("header" in note for note in result["notes"])


def test_propose_mapping_roles_on_mock():
    connector = build_connector()
    structure = sheets_structure.analyze_workbook(connector)
    proposals = sheets_structure.propose_mapping(structure)
    by_key = {(p["sheet_name"], p["column_index"]): p for p in proposals}
    assert by_key[("Chi tiêu", 2)]["role"] == sheets_structure.ROLE_SPEND
    assert by_key[("Chi tiêu", 1)]["role"] == sheets_structure.ROLE_CAMPAIGN
    assert by_key[("Công nợ", 1)]["role"] == sheets_structure.ROLE_DEBT
    assert by_key[("Công nợ", 2)]["role"] == sheets_structure.ROLE_DEPOSIT
    assert by_key[("Công nợ", 4)]["role"] == sheets_structure.ROLE_DEBT
    assert by_key[("Khách hàng", 1)]["role"] == sheets_structure.ROLE_TELEGRAM
    assert by_key[("Tỷ giá", 1)]["role"] == sheets_structure.ROLE_RATE
    assert by_key[("Tỷ giá", 1)]["confidence"] == "high"
    assert all(p["field"] for p in proposals)


def test_propose_mapping_unknown_role_marks_needs_confirmation():
    connector = MockSheetsConnector(workbook={"Miếng dán": [["Mystery"], ["x"]]})
    structure = sheets_structure.analyze_workbook(connector)
    proposals = sheets_structure.propose_mapping(structure)
    assert proposals[0]["role"] is None
    assert proposals[0]["confidence"] is None
    assert "Q-007" in proposals[0]["note"]


# --- persist + confirm (idempotent, CONFIRMED không bị đè, audit) ---


def _proposals_from_mock():
    connector = build_connector()
    structure = sheets_structure.analyze_workbook(connector)
    return sheets_structure.propose_mapping(structure)


def test_persist_proposals_idempotent(db):
    proposals = _proposals_from_mock()
    first = sheets_structure.persist_proposals(db, "mock", proposals)
    assert first["created"] == len(proposals)
    second = sheets_structure.persist_proposals(db, "mock", proposals)
    assert second["created"] == 0
    assert second["unchanged"] == len(proposals)
    count = db.execute(select(func.count()).select_from(SheetMapping)).scalar_one()
    assert count == len(proposals)


def test_persist_never_overwrites_confirmed(db):
    sheets_structure.persist_proposals(db, "mock", _proposals_from_mock())
    sheets_structure.confirm_sheet_mappings(db, "mock", "Chi tiêu", actor="owner")

    modified = _proposals_from_mock()
    for item in modified:
        if item["sheet_name"] == "Chi tiêu":
            item["role"] = "NOTE"
            item["field"] = "ghi_chu"
    result = sheets_structure.persist_proposals(db, "mock", modified)
    assert result["skipped_confirmed"] > 0
    assert result["updated"] == 0
    row = db.execute(
        select(SheetMapping).where(SheetMapping.sheet_name == "Chi tiêu", SheetMapping.column_index == 2)
    ).scalar_one()
    assert row.status == "CONFIRMED"
    assert row.role == "SPEND"


def test_confirm_mappings_and_audit(db):
    sheets_structure.persist_proposals(db, "mock", _proposals_from_mock())
    result = sheets_structure.confirm_sheet_mappings(db, "mock", "Chi tiêu", actor="owner")
    assert result["confirmed"] > 0
    rows = db.execute(
        select(SheetMapping).where(SheetMapping.sheet_name == "Chi tiêu")
    ).scalars().all()
    assert all(r.status == "CONFIRMED" and r.confirmed_at is not None for r in rows)
    audit = db.execute(
        select(AuditLog).where(AuditLog.action == "SHEET_MAPPING_CONFIRMED")
    ).scalars().all()
    assert len(audit) == 1
    assert audit[0].actor == "owner"


# --- endpoints ---


def test_endpoints_sheets_flow(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        from fastapi.testclient import TestClient

        client = TestClient(app)

        mode = client.get("/api/v1/sheets/mode").json()
        assert mode == {"mode": "mock", "spreadsheet_id_configured": False, "auth": "none"}
        structure = client.get("/api/v1/sheets/structure").json()
        assert structure["mode"] == "mock"
        assert len(structure["sheets"]) == 4

        proposal = client.get("/api/v1/sheets/structure/proposal").json()
        assert len(proposal) > 0

        saved = client.post("/api/v1/sheets/mappings/proposal?actor=owner").json()
        assert saved["created"] == len(proposal)
        saved_again = client.post("/api/v1/sheets/mappings/proposal?actor=owner").json()
        assert saved_again["created"] == 0 and saved_again["unchanged"] == len(proposal)

        confirmed = client.post("/api/v1/sheets/mappings/confirm?sheet_name=Tỷ%20giá&actor=owner")
        assert confirmed.status_code == 200

        mappings = client.get("/api/v1/sheets/mappings?sheet_name=Tỷ giá").json()
        assert mappings and all(m["status"] == "CONFIRMED" for m in mappings)

        text = "".join(
            client.get(path).text
            for path in ("/api/v1/sheets/mode", "/api/v1/sheets/structure", "/api/v1/sheets/mappings")
        ).lower()
        assert "bearer" not in text
        assert "access_token" not in text

        miss = client.post("/api/v1/sheets/mappings/confirm?sheet_name=Sheet%20Trống")
        assert miss.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
