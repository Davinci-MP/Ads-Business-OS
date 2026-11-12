from fastapi.testclient import TestClient

from app.api.v1 import sheets as sheets_api
from app.connectors.sheets import MockSheetsConnector
from app.main import app
from decimal import Decimal
from app.services.sheets_report import (
    _effective_deposit_kind,
    _formula_has_unchecked_dependency,
    build_sheets_source_report,
    enrich_sheets_report,
)
from app.services.sheet_report_store import CONFIRMED_MAPPING_CONFIG, SEPARATOR_MAPPING_CONFIG
from app.services.sheets_report import OWNER_USDT_REFUNDS_WORKBOOK as REFUND_WORKBOOK_GATE


def _cell(value, formula=None, number_format=None):
    result = {"value": value}
    if formula:
        result["formula"] = formula
    if number_format:
        result["nf"] = number_format
    return result


def _report_connector(*, fail_title=None):
    summary = [
        ["Tên", "ĐÃ BANK", "T9/2026", "RUN", "PHÍ", "TỔNG", "CÒN"],
        [
            "JOKER",
            _cell(54270, "=JOKER!K1"),
            _cell(59908004, "=JOKER!J1", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"}),
            _cell(371350, "=JOKER!F1"),
            _cell(14854, "=JOKER!G1"),
            _cell(386204, "=JOKER!H1"),
            _cell(59610150, "=B2+C2-F2", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"}),
        ],
        ["ALL", _cell(0, "=ALL!B1"), None, None, None, None, None],
    ]
    blank_row = [None] * 12
    opening = list(blank_row)
    opening[8] = "T9/2026"
    opening[5] = _cell(371349.999999, "=SUM(F4:F)", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    opening[6] = _cell(14854, "=SUM(G4:G)", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    opening[7] = _cell(386204, "=F1+G1", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    opening[10] = _cell(54270, "=SUM(K4:K)", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    opening[9] = _cell(59908004, number_format={"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    header = [
        "Ngày", "Tên TK", "ID TK", "Tiêu", "USD", "VND", "Phí 4%", "Tổng",
        "", "USDT", "", "Tỷ giá nhận",
    ]
    row4 = list(blank_row)
    row4[0] = _cell(46296, number_format={"type": "DATE", "pattern": "dd/mm/yyyy"})
    row4[1], row4[2] = "USD", "act_001"
    row4[4] = _cell(10, number_format={"type": "NUMBER", "pattern": "0.00"})
    row4[5] = _cell(271350, "=E4*I4", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    row4[6] = _cell(10854, "=F4*4%", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    row4[7] = _cell(282204, "=F4+G4", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    row4[8] = 27135
    row5 = list(blank_row)
    row5[1], row5[2] = "VND", "act_002"
    row5[5], row5[6], row5[7] = 100000, 4000, 104000
    row5[9] = _cell(2, number_format={"type": "NUMBER", "pattern": "0.00"})
    row5[10] = _cell(54270, "=J5*L5", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    row5[11] = 27135
    row6 = list(blank_row)
    row6[1], row6[2] = "USD", "act_003"
    row6[5] = _cell(0, "=E6*I6", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    row6[6] = _cell(0, "=F6*4%", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    row6[7] = _cell(0, "=F6+G6", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    row6[8] = 27135
    joker = [opening, list(blank_row), header, row4, row5, row6]

    class FailingConnector(MockSheetsConnector):
        def read_sheet_detail(self, sheet_title):
            if sheet_title == fail_title:
                from app.connectors.sheets import SheetsAPIError

                raise SheetsAPIError("tab unavailable", status_code=503)
            return super().read_sheet_detail(sheet_title)

    return FailingConnector(
        workbook={"TỔNG T10": summary, "JOKER": joker, "ALL": [["Archive"]]},
        merges={"JOKER": [{"start_row": 3, "end_row": 6, "start_col": 0, "end_col": 1}]},
    )


def _add_hunter_tab(connector):
    connector._workbook["TỔNG T10"].append(
        [
            "HUNTER",
            _cell(27000, "=HUNTER!K4"),
            _cell(0, "=HUNTER!J1"),
            _cell(27000, "=HUNTER!F4"),
            _cell(1080, "=HUNTER!G4"),
            _cell(28080, "=HUNTER!H4"),
            _cell(0, "=B4+C4-F4"),
        ]
    )
    blank_row = [None] * 12
    header = [
        "Ngày", "Tên TK", "ID TK", "Tiêu", "USD", "VND", "Phí 4%", "Tổng",
        "", "USDT", "", "Tỷ giá nhận",
    ]
    detail_row = list(blank_row)
    detail_row[0] = _cell(46296, number_format={"type": "DATE", "pattern": "dd/mm/yyyy"})
    detail_row[1], detail_row[2] = "USD", "hunter-account-001"
    detail_row[4] = 1
    detail_row[5] = _cell(27000, "=E4*I4", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    detail_row[6] = _cell(1080, "=F4*4%", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    detail_row[7] = _cell(28080, "=F4+G4", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    detail_row[8] = 27000
    detail_row[9] = 1
    detail_row[10] = _cell(27000, "=J4*L4", {"type": "CURRENCY", "pattern": "[$đ-42A]#,##0"})
    detail_row[11] = 27000
    connector._workbook["HUNTER"] = [[None] * 12, [None] * 12, header, detail_row]


def _add_confirmed_test_tab(connector, title, *, header=None, detail=None):
    connector._workbook["TỔNG T10"].append(
        [title, _cell(0, f"={title}!K1"), _cell(1000, f"={title}!J1")]
    )
    totals = [None] * 12
    totals[5], totals[6], totals[7] = 0, 0, 0
    totals[9], totals[10], totals[11] = 1000, 0, 1000
    header_row = ["Ngày", "Tên TK", "ID TK", "Tiêu", "USD", "VND", "Phí", "Tổng", "", header, "", "Tỷ giá nhận"]
    connector._workbook[title] = [totals, [None] * 12, header_row] + (detail or [])


def _confirmed_report(connector, period="2026-10"):
    return build_sheets_source_report(
        connector, source_period=period, mapping_config=CONFIRMED_MAPPING_CONFIG,
    )


def test_all_customer_totals_keep_exact_decimals_negative_and_field_coverage():
    def customer(name, opening, spend, usdt, date):
        return {
            "source_sheet": name, "profile_status": "NEEDS_CONFIRMATION",
            "opening_balance": {"value": opening, "source": "J1"},
            "tab_source_totals": {
                "spend_vnd": {"value": spend, "source": "F1"},
                "current_balance": {"value": opening, "source": "L1"},
            },
            "deposits": ([{"included": True, "amount_usdt": usdt, "business_date": date, "source_cells": ["J4"]}] if usdt is not None else []),
            "usdt_receipts_state": "HAS_RECORDS" if usdt is not None else "NO_RECORDED",
        }
    report = {"customers": [
        customer("A", "1.25", "0.49", "2.125", "2026-10-02"),
        customer("B", "-2.50", "0.49", "3", None),
        customer("C", None, None, None, None),
    ]}
    totals = enrich_sheets_report(report, "2026-10")["all_customer_totals"]["metrics"]
    assert totals["opening_balance"]["value"] == "-1.25"
    assert totals["opening_balance"]["complete_customers"] == 2
    assert totals["opening_balance"]["missing_customers"] == ["C"]
    assert totals["spend_vnd"]["value"] == "0.98"
    assert totals["budget_deposits_vnd"]["value"] is None
    assert totals["usdt_received"]["value"] == "2.125"
    assert totals["usdt_received"]["complete_customers"] == 2
    assert totals["usdt_received"]["missing_customers"] == ["B"]


def test_customer_aggregation_keeps_digits_beyond_default_decimal_precision():
    report = {"customers": [
        {"source_sheet": name, "opening_balance": {"value": value}, "usdt_receipts_state": "NO_RECORDED"}
        for name, value in (("A", "1234567890123456789012345678.49"), ("B", "0.49"))
    ]}
    totals = enrich_sheets_report(report, "2026-10")["all_customer_totals"]["metrics"]
    assert totals["opening_balance"]["value"] == "1234567890123456789012345678.98"


def test_usdt_formula_with_blank_result_does_not_hide_partial_coverage():
    connector = _report_connector()
    blank_formula = [None] * 12
    blank_formula[9] = _cell("", "=IF(A7=\"\", \"\", 1)")
    connector._workbook["JOKER"].append(blank_formula)
    metric = build_sheets_source_report(connector, source_period="2026-10")["all_customer_totals"]["metrics"]["usdt_received"]
    assert metric["value"] == "2"
    assert metric["status"] == "PARTIAL"
    assert metric["missing_customers"] == ["JOKER"]


def test_confirmed_separator_with_only_a_date_is_not_a_financial_row():
    connector = _report_connector()
    date_row = [None] * 12
    date_row[0] = _cell(46296, number_format={"type": "DATE", "pattern": "dd/mm/yyyy"})
    _add_confirmed_test_tab(connector, "JACK", header="USDT", detail=[[None] * 12, [None] * 12, date_row])
    customer = next(c for c in build_sheets_source_report(
        connector, source_period="2026-10", mapping_config=SEPARATOR_MAPPING_CONFIG,
    )["customers"] if c["source_sheet"] == "JACK")
    assert not any(row["row_number"] == 6 for row in customer["unclassified_rows"])
    assert not any("Dòng được xác nhận phân cách" in issue["message"] for issue in customer["issues"])


def test_totals_do_not_add_subtotals_or_receipts_from_other_periods():
    connector = _report_connector()
    result = build_sheets_source_report(connector, source_period="2026-11")
    metrics = result["all_customer_totals"]["metrics"]
    assert metrics["usdt_received"]["value"] == "0"
    assert len(result["customers"]) == 1
    assert metrics["opening_balance"]["total_customers"] == 1


def test_enrich_classifies_d051_refunds_in_snapshots_built_before_kind():
    def customer(name, deposits):
        return {
            "source_sheet": name, "profile_status": "NEEDS_CONFIRMATION",
            "deposits": deposits, "usdt_receipts_state": "HAS_RECORDS",
        }
    report = {"spreadsheet_key": None, "customers": [
        customer("PEDRI", [
            {"included": True, "amount_usdt": "1000", "business_date": "2026-09-07", "source_cells": ["J4"]},
            {"included": True, "amount_usdt": "-18", "business_date": "2026-09-07",
             "source_cells": ["J5", "K5", "L5"]},
        ]),
        customer("KING", [
            {"included": True, "amount_usdt": "-117", "business_date": "2026-09-21",
             "source_cells": ["J8", "K8", "L8"]},
        ]),
    ]}
    totals = enrich_sheets_report(report, "2026-09")["all_customer_totals"]["metrics"]
    # Workbook gate: key chưa xác nhận → không phân loại hoàn (giữ nguyên hành vi trước D-051 ở kỳ khác workbook).
    assert totals["usdt_refunded"]["value"] == "0"
    assert totals["usdt_received"]["value"] == "865"
    assert totals["usdt_net"]["value"] == "865"
    report["spreadsheet_key"] = REFUND_WORKBOOK_GATE
    totals = enrich_sheets_report(report, "2026-09")["all_customer_totals"]["metrics"]
    assert totals["usdt_received"]["value"] == "1000"
    refunds = totals["usdt_refunded"]
    assert refunds["value"] == "135"
    assert {(c["customer"], tuple(c["source"])) for c in refunds["contributions"]} == {
        ("PEDRI", ("J5", "K5", "L5")),
        ("KING", ("J8", "K8", "L8")),
    }
    assert all(Decimal(c["value"]) > 0 for c in refunds["contributions"])
    assert totals["usdt_net"]["value"] == "865"


def test_enrich_refund_fallback_is_limited_to_confirmed_cells():
    report = {"spreadsheet_key": REFUND_WORKBOOK_GATE, "customers": [{
        "source_sheet": "PDRI", "profile_status": "NEEDS_CONFIRMATION",
        "deposits": [
            # Ô sai (J9 thay vì J5) hoặc sai kỳ → không được phân loại hoàn.
            {"included": True, "amount_usdt": "-18", "business_date": "2026-09-07",
             "source_cells": ["J9", "K9", "L9"]},
            {"included": True, "amount_usdt": "-117", "business_date": "2026-10-21",
             "source_cells": ["J8", "K8", "L8"]},
        ],
        "usdt_receipts_state": "HAS_RECORDS",
    }]}
    totals = enrich_sheets_report(report, "2026-09")["all_customer_totals"]["metrics"]
    assert totals["usdt_refunded"]["contributions"] == []
    assert _effective_deposit_kind(
        report["customers"][0]["deposits"][0], Decimal("-18"), "PDRI", "2026-09",
        REFUND_WORKBOOK_GATE,
    ) == "RECEIPT"


def test_enrich_refund_fallback_requires_owner_workbook_key():
    deposits = [
        {"included": True, "amount_usdt": "-18", "business_date": "2026-09-07",
         "source_cells": ["J5", "K5", "L5"]},
    ]
    for key in (None, "mock", "14mgYdWuhkF0-1TbXnSwAVnMbqKmTfiiq-oDr7MuOt7k"):
        totals = enrich_sheets_report(
            {"spreadsheet_key": key, "customers": [{
                "source_sheet": "PEDRI", "profile_status": "NEEDS_CONFIRMATION",
                "deposits": deposits, "usdt_receipts_state": "HAS_RECORDS",
            }]},
            "2026-09",
        )["all_customer_totals"]["metrics"]
        assert totals["usdt_refunded"]["value"] == "0", key
        assert _effective_deposit_kind(
            deposits[0], Decimal("-18"), "PEDRI", "2026-09", key,
        ) == "RECEIPT", key


def test_separator_a_with_receipt_preserves_jkl_without_row_conflict():
    connector = _report_connector()
    rows = [[None] * 12 for _ in range(3)]
    rows[2][9] = 7
    rows[2][10] = _cell(175000, "=J6*L6")
    rows[2][11] = 25000
    _add_confirmed_test_tab(connector, "JACK", detail=rows)
    report = build_sheets_source_report(connector, source_period="2026-10", mapping_config=SEPARATOR_MAPPING_CONFIG)
    customer = next(c for c in report["customers"] if c["source_sheet"] == "JACK")
    receipt = customer["deposits"][0]
    assert (receipt["amount_usdt"], receipt["amount_vnd"], receipt["rate"]) == (7, 175000, 25000)
    assert receipt["business_date"] is None
    assert receipt["source_cells"] == ["J6", "K6", "L6"]
    assert not any(row["row_number"] == 6 for row in customer["account_rows"] + customer["unclassified_rows"])
    assert not any("phân cách có nội dung" in issue["message"] for issue in customer["issues"])
    assert report["all_customer_totals"]["metrics"]["usdt_received"]["status"] == "PARTIAL"
    assert report["all_customer_totals"]["metrics"]["usdt_received"]["value"] == "2"


def test_separator_layout_is_structural_and_does_not_ignore_account_rows():
    connector = _report_connector()
    rows = [[None] * 12 for _ in range(5)]
    rows[1][1], rows[1][2], rows[1][5] = "VND", "real-account", 25
    rows[1][9] = 3
    rows[4][9], rows[4][10], rows[4][11] = 8, 200000, 25000
    _add_confirmed_test_tab(connector, "JACK", detail=rows)
    customer = next(c for c in build_sheets_source_report(
        connector, source_period="2026-10", mapping_config=SEPARATOR_MAPPING_CONFIG,
    )["customers"] if c["source_sheet"] == "JACK")
    assert any(row["account_id"] == "real-account" and row["business_date"] is None for row in customer["account_rows"])
    assert any("không có ngày" in issue["message"] for issue in customer["issues"])
    assert [row["amount_usdt"] for row in customer["deposits"]] == [3, 8]
    assert all(row["business_date"] is None for row in customer["deposits"])
    assert not any(row["row_number"] == 8 for row in customer["unclassified_rows"])


def test_separator_viktor_text_note_is_separate_from_financial_rows():
    connector = _report_connector()
    rows = [[None] * 13 for _ in range(3)]
    rows[2][12] = "tk 65$"
    _add_confirmed_test_tab(connector, "VIKTOR", detail=rows)
    customer = next(c for c in build_sheets_source_report(
        connector, source_period="2026-10", mapping_config=SEPARATOR_MAPPING_CONFIG,
    )["customers"] if c["source_sheet"] == "VIKTOR")
    assert not any(row["row_number"] == 6 for row in customer["unclassified_rows"])
    assert any("VIKTOR!M6" in issue["source"] and "ghi chú" in issue["message"].lower() for issue in customer["issues"])
    assert not any("phân cách có nội dung" in issue["message"] for issue in customer["issues"])


def test_receipt_only_blank_a_does_not_inherit_date_from_account_merge():
    connector = _report_connector()
    rows = [[None] * 12 for _ in range(3)]
    rows[0][0] = _cell(46296, number_format={"type": "DATE", "pattern": "dd/mm/yyyy"})
    rows[2][9] = 7
    _add_confirmed_test_tab(connector, "JACK", detail=rows)
    connector._merges["JACK"] = [{"start_row": 3, "end_row": 6, "start_col": 0, "end_col": 1}]
    customer = next(c for c in build_sheets_source_report(
        connector, source_period="2026-10", mapping_config=SEPARATOR_MAPPING_CONFIG,
    )["customers"] if c["source_sheet"] == "JACK")
    assert customer["deposits"][0]["business_date"] is None


def test_original_account_spend_uses_account_currency_not_converted_vnd():
    connector = _report_connector()
    report = build_sheets_source_report(connector, source_period="2026-10")
    rows = report["customers"][0]["account_rows"]
    usd = next(row for row in rows if row["account_id"] == "act_001")
    vnd = next(row for row in rows if row["account_id"] == "act_002")
    missing = next(row for row in rows if row["account_id"] == "act_003")
    assert usd["original_spend"] == {"value": "10", "currency": "USD", "source": "E4"}
    assert vnd["original_spend"] == {"value": "100000", "currency": "VND", "source": "F5"}
    assert missing["original_spend"]["value"] is None


def test_confirmed_blank_j3_is_scoped_and_preserves_balances_without_creating_zero_receipts():
    connector = _report_connector()
    for title in ("JACK", "VKL", "SONA", "VIKTOR", "OTHER"):
        _add_confirmed_test_tab(connector, title)
    report = _confirmed_report(connector)
    customers = {item["source_sheet"]: item for item in report["customers"]}
    for title in ("JACK", "VKL", "SONA", "VIKTOR"):
        customer = customers[title]
        assert customer["profile_status"] != "STRUCTURE_ERROR"
        assert customer["opening_balance"]["value"] == "1000"
        assert customer["tab_source_totals"]["current_balance"]["value"] == "1000"
        assert customer["usdt_receipts_state"] == "NO_RECORDED"
        assert customer["deposits"] == []
        assert not any("header chưa khớp" in issue["message"] for issue in customer["issues"])
    assert customers["JACK"]["activity_status"] is None
    for title in ("VKL", "SONA", "VIKTOR"):
        assert customers[title]["activity_status"] == {
            "period": "2026-10", "status": "OWNER_CONFIRMED_INACTIVE", "conflict": False,
        }
    # Mapping chuẩn: J3 trống hợp lệ cho mọi tab, nhưng trạng thái "chưa hoạt động" không áp ngoài kỳ đã xác nhận.
    assert customers["OTHER"]["profile_status"] != "STRUCTURE_ERROR"
    assert customers["OTHER"]["activity_status"] is None
    future = {item["source_sheet"]: item for item in _confirmed_report(connector, "2026-11")["customers"]}
    assert future["VKL"]["activity_status"] is None
    without_config = {item["source_sheet"]: item for item in build_sheets_source_report(connector)["customers"]}
    assert without_config["VKL"]["profile_status"] != "STRUCTURE_ERROR"
    assert without_config["VKL"]["tab_source_totals"]["current_balance"]["value"] == "1000"
    assert without_config["VKL"]["activity_status"] is None


def test_conflicting_j3_header_isolates_only_j_metrics():
    connector = _report_connector()
    _add_confirmed_test_tab(connector, "VKL", header="EUR")
    report = _confirmed_report(connector)
    customer = next(c for c in report["customers"] if c["source_sheet"] == "VKL")
    assert customer["profile_status"] != "STRUCTURE_ERROR"
    # J3 xung đột không được cô lập J1: opening balance đọc theo ô riêng của nó.
    assert customer["opening_balance"]["value"] == "1000"
    assert customer["opening_balance"]["basis"] == "SOURCE_VALUE"
    assert customer["usdt_receipts_state"] == "NEEDS_REVIEW"
    assert customer["tab_source_totals"]["current_balance"]["value"] == "1000"
    assert any(i["source"] == "VKL!J3" for i in customer["issues"])
    assert any("khoản nhận USDT" in i["message"] and i["source"] == "VKL!J3" for i in customer["issues"])
    metrics = report["all_customer_totals"]["metrics"]
    assert "VKL" not in metrics["opening_balance"]["missing_customers"]
    assert "VKL" not in metrics["current_balance"]["missing_customers"]


def test_owner_blank_opening_zero_requires_owner_workbook():
    connector = _report_connector()
    _add_confirmed_test_tab(connector, "KING", header="USDT")
    connector._workbook["KING"][0][9] = None  # J1 trống
    # connector mock có spreadsheet_key="mock" → xác nhận J1 trống = 0 không áp.
    customer = next(
        c for c in build_sheets_source_report(
            connector, source_period="2026-09", mapping_config=CONFIRMED_MAPPING_CONFIG,
        )["customers"] if c["source_sheet"] == "KING"
    )
    assert customer["opening_balance"]["value"] is None
    assert customer["opening_balance"]["basis"] == "BLANK_UNCONFIRMED"



def test_inactive_tab_new_current_period_data_remains_visible_and_warns():
    connector = _report_connector()
    row = [None] * 12
    row[0] = _cell(46302, number_format={"type": "DATE", "pattern": "dd/mm/yyyy"})
    row[1], row[2], row[5], row[9] = "VND", "synthetic-account", 25, 2
    _add_confirmed_test_tab(connector, "SONA", detail=[row])
    customer = next(c for c in _confirmed_report(connector)["customers"] if c["source_sheet"] == "SONA")
    assert customer["account_rows"][0]["business_date"] == "2026-10-07"
    assert customer["deposits"][0]["amount_usdt"] == 2
    assert customer["activity_status"]["conflict"] is True
    assert any("mâu thuẫn" in issue["message"] and "SONA!J4" in issue["source"] for issue in customer["issues"])


def test_previous_period_detail_does_not_conflict_or_relabel_source_totals():
    connector = _report_connector()
    row = [None] * 12
    row[0] = _cell(46272, number_format={"type": "DATE", "pattern": "dd/mm/yyyy"})
    row[1], row[2], row[5] = "VND", "synthetic-old", 17
    _add_confirmed_test_tab(connector, "VIKTOR", detail=[row])
    customer = next(c for c in _confirmed_report(connector)["customers"] if c["source_sheet"] == "VIKTOR")
    assert customer["account_rows"][0]["business_date"].startswith("2026-09")
    assert customer["activity_status"]["conflict"] is False
    assert "source_totals" not in customer["period_totals"]["2026-09"]
    assert customer["tab_source_totals"]["current_balance"]["value"] == "1000"


def test_inactive_tab_nonzero_period_total_or_undated_spend_is_flagged():
    connector = _report_connector()
    row = [None] * 12
    row[2], row[5] = "synthetic-undated", 12
    _add_confirmed_test_tab(connector, "VKL", detail=[row])
    connector._workbook["VKL"][0][10] = 100
    customer = next(c for c in _confirmed_report(connector)["customers"] if c["source_sheet"] == "VKL")
    assert customer["activity_status"]["conflict"] is True
    warning = next(issue for issue in customer["issues"] if "mâu thuẫn" in issue["message"])
    assert "VKL!K1" in warning["source"] and "VKL!F4" in warning["source"]
    assert customer["tab_source_totals"]["budget_deposits_vnd"]["value"] == "100"


def test_confirmed_tab_non_numeric_usdt_is_reported_without_counting():
    connector = _report_connector()
    row = [None] * 12
    row[9] = "not a number"
    _add_confirmed_test_tab(connector, "JACK", detail=[row])
    customer = next(c for c in _confirmed_report(connector)["customers"] if c["source_sheet"] == "JACK")
    assert customer["deposits"][0]["included"] is False
    assert any(issue["source"] == "JACK!J4" and "không phải số" in issue["message"] for issue in customer["issues"])


def test_confirmed_tab_zero_is_not_blank_and_formula_empty_needs_review():
    connector = _report_connector()
    zero = [None] * 12
    zero[9] = 0
    _add_confirmed_test_tab(connector, "JACK", detail=[zero])
    customer = next(c for c in _confirmed_report(connector)["customers"] if c["source_sheet"] == "JACK")
    assert customer["deposits"][0]["amount_usdt"] == 0
    assert customer["usdt_receipts_state"] == "HAS_RECORDS"
    empty_formula = [None] * 12
    empty_formula[9] = _cell("", '=""')
    _add_confirmed_test_tab(connector, "VKL", detail=[empty_formula])
    customer = next(c for c in _confirmed_report(connector)["customers"] if c["source_sheet"] == "VKL")
    assert customer["usdt_receipts_state"] == "NEEDS_REVIEW"
    assert customer["deposits"] == []


def test_report_counts_only_account_rows_and_keeps_unresolved_zero_or_formula_rows_visible():
    connector = _report_connector()
    _add_hunter_tab(connector)
    hunter_rows = connector._workbook["HUNTER"]
    while len(hunter_rows) < 26:
        hunter_rows.append([None] * 12)
    hunter_rows.append([None] * 12)  # row 27 is a blank separator

    zero_account = [None] * 12
    zero_account[1], zero_account[2], zero_account[4] = "USD", "0", 0
    zero_account[5] = _cell(0, "=E28*I28", {"type": "CURRENCY", "pattern": "[$$-en-US]#,##0.00"})
    hunter_rows.append(zero_account)

    formula_only = [None] * 12
    formula_only[0] = _cell("", '=""')
    hunter_rows.append(formula_only)

    zero_without_id = [None] * 12
    zero_without_id[5] = _cell(0)
    hunter_rows.append(zero_without_id)

    result = build_sheets_source_report(connector)
    hunter = next(customer for customer in result["customers"] if customer["source_sheet"] == "HUNTER")

    undated_accounts = [row for row in hunter["account_rows"] if not row["business_date"]]
    assert [row["row_number"] for row in undated_accounts] == [28]
    assert undated_accounts[0]["account_id"] == "0"
    assert 27 not in {row["row_number"] for row in hunter["source_rows"]}
    assert [row["row_number"] for row in hunter["unclassified_rows"]] == [29, 30]
    assert "công thức" in hunter["unclassified_rows"][0]["reason"]
    assert next(cell for cell in hunter["unclassified_rows"][1]["cells"] if cell["address"] == "F30")["value"] == 0
    assert any(issue["source"] == "HUNTER!A28" for issue in hunter["issues"])


def test_report_preserves_zero_values_and_does_not_extend_a_merged_date_past_its_range():
    connector = _report_connector()
    zero_account = [None] * 12
    zero_account[1], zero_account[2], zero_account[4] = "USD", "0", 0
    zero_account[5] = _cell(0, "=E7*I7", {"type": "CURRENCY", "pattern": "[$$-en-US]#,##0.00"})
    zero_account[9] = _cell(0)
    connector._workbook["JOKER"].append(zero_account)

    result = build_sheets_source_report(connector)
    joker = next(customer for customer in result["customers"] if customer["source_sheet"] == "JOKER")
    row = next(item for item in joker["account_rows"] if item["row_number"] == 7)
    receipt = next(item for item in joker["deposits"] if item["source_row"] == 7)

    assert row["account_id"] == "0"
    assert row["business_date"] is None
    assert row["cells"][5]["value"] == 0
    assert receipt["amount_usdt"] == 0
    assert receipt["business_date"] is None
    assert 7 not in joker["daily"][0]["account_rows"]


def test_report_limited_read_scope_and_unchecked_formula_dependencies_are_explicit():
    connector = _report_connector()
    _add_hunter_tab(connector)
    original_read = connector.read_sheet_detail

    def read_a_to_l(sheet_title):
        detail = original_read(sheet_title)
        if sheet_title == "HUNTER":
            detail["cells"][3][5]["formula"] = "=E4*I4+M4"
            detail["read_scope"] = "A:L"
        return detail

    connector.read_sheet_detail = read_a_to_l
    result = build_sheets_source_report(connector)
    hunter = next(customer for customer in result["customers"] if customer["source_sheet"] == "HUNTER")

    assert result["status"] == "PARTIAL"
    assert hunter["read_scope"] == "A:L"
    assert hunter["completeness_status"] == "NEEDS_REVIEW"
    assert hunter["field_status"]["business_date"]["status"] == "DETECTED"
    assert hunter["field_status"]["business_date"]["source"] == "HUNTER!A"
    assert hunter["source_periods"] == ["2026-10"]
    assert hunter["observed_date_from"] == "2026-10-01"
    assert len(hunter["source_rows"][-1]["cells"]) == 12
    assert hunter["account_rows"][0]["account_id"] == "hunter-account-001"
    assert not hunter["account_rows"][0]["missing_inputs"]
    assert any("chưa kiểm tra phụ thuộc" in issue["message"] for issue in hunter["issues"])
    assert any("Chỉ đọc phạm vi A:L" in note for note in hunter["source_analysis"]["notes"])


def test_unchecked_formula_dependency_uses_l_as_boundary():
    assert not _formula_has_unchecked_dependency("=SUM(A4:L4)")
    assert _formula_has_unchecked_dependency("=SUM(A4:M4)")
    assert _formula_has_unchecked_dependency("=SUM(L:M)")
    assert _formula_has_unchecked_dependency("='Other tab'!A4")


def test_read_scope_alone_does_not_make_report_partial():
    connector = _report_connector()
    connector._workbook["TỔNG T10"] = connector._workbook["TỔNG T10"][:2]
    connector._workbook["JOKER"] = connector._workbook["JOKER"][:5]
    connector._merges["JOKER"] = [{"start_row": 3, "end_row": 5, "start_col": 0, "end_col": 1}]
    original_read = connector.read_sheet_detail

    def read_a_to_l(sheet_title):
        detail = original_read(sheet_title)
        if sheet_title == "JOKER":
            detail["read_scope"] = "A:L"
        return detail

    connector.read_sheet_detail = read_a_to_l
    result = build_sheets_source_report(connector)
    joker = next(customer for customer in result["customers"] if customer["source_sheet"] == "JOKER")
    assert result["status"] == "READY"
    assert joker["completeness_status"] == "SOURCE_ROWS_CLASSIFIED"
    assert not any("chưa kiểm tra phụ thuộc" in issue["message"] for issue in joker["issues"])


def test_unresolved_summary_reference_makes_report_partial():
    connector = _report_connector()
    connector._workbook["TỔNG T10"] = connector._workbook["TỔNG T10"][:2]
    connector._workbook["TỔNG T10"][1].append(_cell(10, "=ALL!M2"))
    connector._workbook["JOKER"] = connector._workbook["JOKER"][:5]
    connector._merges["JOKER"] = [{"start_row": 3, "end_row": 5, "start_col": 0, "end_col": 1}]
    result = build_sheets_source_report(connector)
    assert result["customers"][0]["completeness_status"] == "SOURCE_ROWS_CLASSIFIED"
    assert result["summary_tabs"][0]["rows"][1]["unresolved_references"]
    assert result["status"] == "PARTIAL"


def test_undated_receipt_on_separator_is_preserved_without_assigning_date():
    connector = _report_connector()
    _add_hunter_tab(connector)
    separator = [None] * 12
    separator[9], separator[10], separator[11] = 2, _cell(54000, "=J5*L5"), 27000
    connector._workbook["HUNTER"].append(separator)
    result = build_sheets_source_report(connector)
    hunter = next(customer for customer in result["customers"] if customer["source_sheet"] == "HUNTER")
    receipt = next(item for item in hunter["deposits"] if item["source_row"] == 5)
    assert receipt["business_date"] is None
    assert receipt["source_cells"] == ["J5", "K5", "L5"]
    assert receipt["status"] == "PREVIEW"
    assert hunter["period_totals"]["2026-10"]["usdt_received"] is None
    assert not hunter["unclassified_rows"]
    assert hunter["completeness_status"] == "NEEDS_REVIEW"


def test_sheets_report_keeps_source_totals_separate_and_honors_confirmed_joker_profile():
    result = build_sheets_source_report(_report_connector())

    assert result["status"] == "PARTIAL"
    assert [customer["source_sheet"] for customer in result["customers"]] == ["JOKER"]
    customer = result["customers"][0]
    assert customer["opening_balance"] == {
        "value": "59908004",
        "formatted_value": None,
        "currency": "VND",
        "source": "JOKER!J1",
        "status": "CONFIRMED",
        "basis": "SOURCE_VALUE",
        "source_value": 59908004,
    }
    assert customer["source_periods"] == ["2026-10"]
    assert len(customer["deposits"]) == 1
    assert customer["deposits"][0]["business_date"] == "2026-10-01"
    assert customer["deposits"][0]["amount_usdt"] == 2
    assert customer["deposits"][0]["amount_vnd"] == 54270
    assert customer["daily"][0]["spend_by_currency"] == {"USD": "10", "VND": "100000"}
    assert customer["daily"][0]["spend_vnd"] == "371350"
    assert customer["period_totals"]["2026-10"]["spend_vnd"] == "371350"
    assert customer["period_totals"]["2026-10"]["usdt_received"] == "2"
    assert customer["period_totals"]["2026-10"]["budget_deposits_vnd"] == "54270"
    assert customer["period_totals"]["2026-10"]["source_totals"]["spend_vnd"] == {
        "value": "371349.999999",
        "formatted_value": None,
        "currency": "VND",
        "formula": "=SUM(F4:F)",
        "source": "F1",
        "status": "CONFIRMED",
    }
    assert customer["closing_balances"][0]["formula"] == "=B2+C2-F2"
    assert customer["closing_balances"][0]["value"] == 59610150
    assert customer["closing_balances"][0]["currency"] == "VND"
    assert any("đầu vào trống" in issue["message"] for issue in customer["issues"])
    assert customer["ignored_columns"] == ["D"]
    assert all(row["link_status"] == "NEEDS_CONFIRMATION" for row in result["summary_tabs"][0]["rows"] if row["customer_label"] == "ALL")


def test_sheets_report_applies_standard_mapping_without_confirming_other_fields():
    connector = _report_connector()
    _add_hunter_tab(connector)

    result = build_sheets_source_report(connector)

    hunter = next(customer for customer in result["customers"] if customer["source_sheet"] == "HUNTER")
    assert hunter["profile_status"] == "NEEDS_CONFIRMATION"
    assert hunter["opening_balance"]["status"] == "CONFIRMED"
    assert hunter["field_status"]["usdt_receipts"]["status"] == "CONFIRMED"
    assert hunter["field_status"]["usdt_vnd_rate"]["status"] == "PREVIEW"
    assert hunter["deposits"][0]["status"] == "PREVIEW"
    assert hunter["period_totals"]["2026-10"]["usdt_received"] == "1"


def test_standard_totals_use_exact_cells_and_l1_not_detail_rate():
    connector = _report_connector()
    connector._workbook["JOKER"][0][11] = _cell(-1250.5, "=K1+J1-H1")
    customer = build_sheets_source_report(connector)["customers"][0]
    totals = customer["period_totals"]["2026-10"]["source_totals"]
    assert totals["current_balance"]["value"] == "-1250.5"
    assert totals["current_balance"]["source"] == "L1"
    assert totals["profit_convention"]["value"] == totals["fee"]["value"]
    assert totals["profit_convention"]["source"] == "G1"
    assert totals["budget_deposits_vnd"]["source"] == "K1"
    assert customer["deposits"][0]["rate"] == 27135


def test_invalid_standard_total_is_reported_without_fallback():
    connector = _report_connector()
    connector._workbook["JOKER"][0][5] = "not a monetary value"
    customer = build_sheets_source_report(connector)["customers"][0]
    assert "spend_vnd" not in customer["period_totals"]["2026-10"]["source_totals"]
    assert any(issue["source"] == "JOKER!F1" for issue in customer["issues"])
    connector = _report_connector()
    connector._workbook["JOKER"][0][9] = "invalid opening"
    customer = build_sheets_source_report(connector)["customers"][0]
    assert customer["opening_balance"]["value"] is None
    assert any(issue["source"] == "JOKER!J1" for issue in customer["issues"])


def test_source_detail_difference_preserves_fractional_value():
    customer = build_sheets_source_report(_report_connector())["customers"][0]
    differences = customer["period_totals"]["2026-10"]["source_detail_differences"]
    spend = next(item for item in differences if item["field"] == "spend_vnd")
    assert spend["source_value"] == "371349.999999"
    assert spend["detail_value"] == "371350"
    assert spend["difference"] == "-0.000001"


def test_tab_totals_remain_available_without_identifiable_period():
    connector = _report_connector()
    connector._workbook["JOKER"][3][0] = None
    customer = build_sheets_source_report(connector)["customers"][0]
    assert customer["source_periods"] == []
    assert customer["period_totals"] == {}
    assert customer["tab_source_totals"]["spend_vnd"]["value"] == "371349.999999"
    assert customer["tab_source_totals"]["budget_deposits_vnd"]["source"] == "K1"


def test_incompatible_customer_structure_is_not_mapped_using_other_columns():
    connector = _report_connector()
    connector._workbook["JOKER"][2][5] = "Wrong header"
    customer = build_sheets_source_report(connector)["customers"][0]
    assert customer["profile_status"] == "STRUCTURE_ERROR"
    assert customer["period_totals"] == {}
    assert "F" in customer["issues"][0]["message"]


def test_receipt_subtotals_are_not_double_counted_and_are_traceable():
    connector = _report_connector()
    rows = connector._workbook["JOKER"]
    subtotal = [None] * 12
    subtotal[9] = _cell(2, "=SUM(J4:J6)")
    rows.append(subtotal)
    customer = build_sheets_source_report(connector)["customers"][0]
    excluded = next(item for item in customer["deposits"] if item["source_row"] == 7)
    assert excluded["included"] is False
    assert excluded["status"] == "EXCLUDED"
    assert excluded["source_cells"][0] == "J7"
    assert customer["period_totals"]["2026-10"]["usdt_received"] == "2"


def test_hidden_tab_is_not_read_or_exposed_and_hidden_dependency_warns():
    connector = _report_connector()
    _add_hunter_tab(connector)
    connector._workbook["TỔNG T10"][1].append(_cell(10, "=HUNTER!L1"))
    original_list = connector.list_sheets
    original_read = connector.read_sheet_detail
    read_titles = []

    def list_with_hidden():
        return [{**item, "hidden": item["title"] == "HUNTER"} for item in original_list()]

    def tracked_read(title):
        read_titles.append(title)
        assert title != "HUNTER"
        return original_read(title)

    connector.list_sheets = list_with_hidden
    connector.read_sheet_detail = tracked_read
    result = build_sheets_source_report(connector)
    assert "HUNTER" not in read_titles
    assert all(c["source_sheet"] != "HUNTER" for c in result["customers"])
    assert all(row["customer_label"] != "HUNTER" for tab in result["summary_tabs"] for row in tab["rows"])
    assert any("tab ẩn" in issue["message"] for issue in result["issues"])


def test_refresh_removes_newly_hidden_customer():
    connector = _report_connector()
    _add_hunter_tab(connector)
    original_list = connector.list_sheets
    original_read = connector.read_sheet_detail
    hidden = set()
    read_titles = []

    def list_with_hidden():
        return [{**item, "hidden": item["title"] in hidden} for item in original_list()]

    def tracked_read(title):
        read_titles.append(title)
        return original_read(title)

    connector.list_sheets = list_with_hidden
    connector.read_sheet_detail = tracked_read
    assert any(c["source_sheet"] == "HUNTER" for c in build_sheets_source_report(connector)["customers"])
    hidden.add("HUNTER")
    read_titles.clear()
    refreshed = build_sheets_source_report(connector)
    assert "HUNTER" not in read_titles
    assert all(c["source_sheet"] != "HUNTER" for c in refreshed["customers"])


def test_hidden_tab_is_not_read_by_structure_or_preview(monkeypatch):
    from app.services.sheets_structure import analyze_workbook_detailed

    connector = _report_connector()
    _add_hunter_tab(connector)
    original_list = connector.list_sheets
    original_read = connector.read_sheet_detail
    hidden_id = next(item["sheet_id"] for item in original_list() if item["title"] == "HUNTER")

    def list_with_hidden():
        return [{**item, "hidden": item["title"] == "HUNTER"} for item in original_list()]

    def tracked_read(title):
        assert title != "HUNTER"
        return original_read(title)

    connector.list_sheets = list_with_hidden
    connector.read_sheet_detail = tracked_read
    assert all(sheet["title"] != "HUNTER" for sheet in analyze_workbook_detailed(connector)["sheets"])
    monkeypatch.setattr(sheets_api, "_connector_for", lambda _spreadsheet: connector)
    response = TestClient(app).post("/api/v1/sheets/preview", json={"spreadsheet": "workbook-id", "sheet_id": hidden_id})
    assert response.status_code == 404


def test_sheets_report_partial_read_keeps_successful_customer_tabs():
    connector = _report_connector(fail_title="JOKER")
    _add_hunter_tab(connector)
    result = build_sheets_source_report(connector)

    assert result["status"] == "PARTIAL"
    assert {customer["source_sheet"] for customer in result["customers"]} == {"JOKER", "HUNTER"}
    assert next(customer for customer in result["customers"] if customer["source_sheet"] == "JOKER")["profile_status"] == "SOURCE_ERROR"
    assert next(customer for customer in result["customers"] if customer["source_sheet"] == "HUNTER")["profile_status"] == "NEEDS_CONFIRMATION"
    assert any(issue["severity"] == "error" for issue in result["issues"])


def test_sheets_report_endpoint_uses_read_only_source_without_mapping_confirmation(monkeypatch):
    connector = _report_connector()
    monkeypatch.setattr(sheets_api, "_connector_for", lambda _spreadsheet: connector)
    response = TestClient(app).post(
        "/api/v1/sheets/report",
        json={"spreadsheet": "workbook-id"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mapping_status"] == "PREVIEW_NEEDS_CONFIRMATION"
    assert payload["meta_reconciliation_status"] == "NOT_COMPARED"
    assert payload["customers"][0]["opening_balance"]["source"] == "JOKER!J1"

import pytest


def _company_report(row_number=35, total='120.25'):
    return {
        'customers': [{'source_sheet': 'CLIENT', 'tab_source_totals': {
            'spend_vnd': {'value': '100'}}, 'opening_balance': {}}],
        'summary_tabs': [{'title': 'TỔNG T11', 'header_row': 1, 'rows': [
            {'summary_row': 1, 'cells': [
                {'address': f'{col}1', 'value': value}
                for col, value in zip('ABCDEFG', ['Tên', 'ĐÃ BANK', 'T10/2026', 'RUN', 'PHÍ', 'TỔNG', 'CÒN'])]},
            {'summary_row': row_number, 'customer_label': 'TỔNG', 'cells': [
                {'address': f'{col}{row_number}', 'value': value, 'formula': f'=SUM({col}2:{col}{row_number-1})'}
                for col, value in zip('BCDEFG', ['200', '-10', total, '4', '124.25', '65.75'])]}
        ]}]
    }


@pytest.mark.parametrize('row_number', [30, 35, 40])
def test_company_total_follows_label_when_customer_count_changes(row_number):
    report = enrich_sheets_report(_company_report(row_number), '2026-11')
    total = report['company_totals']
    assert total['source_row'] == row_number
    assert total['metrics']['spend_vnd']['source'] == f'TỔNG T11!D{row_number}'
    assert total['metrics']['spend_vnd']['value'] == '120.25'
    assert total['metrics']['spend_vnd']['difference'] == '20.25'
    assert total['metrics']['opening_balance']['value'] == '-10'
    assert report['all_customer_totals']['metrics']['spend_vnd']['value'] == '100'


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'wrong_month', 'wrong_header'])
def test_company_total_does_not_guess_ambiguous_or_missing_source(case):
    from copy import deepcopy
    report = _company_report()
    tab = report['summary_tabs'][0]
    if case == 'missing':
        tab['rows'].pop()
    elif case == 'duplicate':
        tab['rows'].append(deepcopy(tab['rows'][-1]))
    elif case == 'wrong_month':
        tab['title'] = 'TỔNG T10'
    else:
        tab['rows'][0]['cells'][3]['value'] = 'USD'
    total = enrich_sheets_report(report, '2026-11')['company_totals']
    assert total['status'] == 'NEEDS_CONFIRMATION'
    assert total['metrics']['spend_vnd']['value'] is None


@pytest.mark.parametrize('value', [None, '#REF!', 'NaN', 'Infinity'])
def test_company_total_invalid_cell_never_becomes_zero(value):
    total = enrich_sheets_report(_company_report(total=value), '2026-11')['company_totals']
    assert total['metrics']['spend_vnd']['value'] is None
    assert total['metrics']['spend_vnd']['status'] == 'PARTIAL'
    assert total['metrics']['budget_deposits_vnd']['value'] == '200'
