"""Test đối chiếu Google Sheets ↔ DB (Q-007/D-036 bản cập nhật, chỉ đọc).

Quy tắc: đối chiếu theo Customer + ngày nghiệp vụ (mã ngày trong campaign
name) + Ad Account ID; chi tiêu = TỔNG TÍCH LŨY mỗi campaign (KHÔNG dùng
cum(day)−cum(day-1) theo ngày Meta); tolerance theo đơn vị tiền.
"""

from datetime import date, datetime, timedelta, timezone
from itertools import count

from sqlalchemy import delete, select

from app.models.ad_account import AdAccount
from app.models.campaign import RECOGNITION_CONFIRMED, RECOGNITION_UNRECOGNIZED, Campaign
from app.services.sheets_compare import (
    COMPARE_DIFF,
    COMPARE_MATCH,
    COMPARE_NEEDS_CONFIRMATION,
    COMPARE_NEEDS_MAPPING,
    COMPARE_NEEDS_RATE,
    COMPARE_NO_LIVE_META,
    COMPARE_NO_META,
    COMPARE_SKIPPED,
    compare_sheet_with_db,
    currency_from_header,
    meta_live_configured,
    tolerance_for_currency,
)
from app.services.meta_sync import extract_report_dates
from app.services.sheets_compare import _serial_to_date
from tests.conftest import add_snapshot, datetime_utc

# 46320 (Excel serial) = 25/10/2026 — khớp mã ngày "1025" trong campaign name
DETAIL_ROWS = [
    ["NGÀY (25/10)", "USD", "ID TK", None, "USD", "VND", "Phí", "Tổng"],
    [46320, "USD", None, None, None, None, None, None],
    [None, "USD", "111111111111111", None, 10.0, 271350.0, 1085.4, 272435.4],
    [None, "USD", None, None, 5.0, 135675.0, 542.7, 136217.7],
]

MERGES = [{"start_row": 1, "end_row": 5, "start_col": 0, "end_col": 1}]

_account_seq = count(0)


class DetailConnector:
    """Giả lập connector đọc detail (chỉ GET) — mục đích test đối chiếu."""

    mode = "mock"
    spreadsheet_key = "mock"

    def __init__(self, rows, merges):
        self._rows = rows
        self._merges = merges

    def list_sheets(self):
        return [{"title": "JOKER", "hidden": False}]

    def read_sheet_detail(self, sheet_name):
        return {"sheet_name": sheet_name, "rows": self._rows, "merges": self._merges, "locale": "vi_VN"}


def _seed_mappings(db, connector, spend_header="USD"):
    from app.models.sheets import MAPPING_CONFIRMED, SheetMapping

    db.execute(
        delete(SheetMapping).where(
            SheetMapping.spreadsheet_key == connector.spreadsheet_key,
            SheetMapping.sheet_name == "JOKER",
        )
    )
    roles = {0: "DATE", 2: "ACCOUNT", 4: "SPEND", 5: "SPEND"}
    headers = {0: "NGÀY", 2: "ID TK", 4: spend_header, 5: "VND"}
    letters = {0: "A", 2: "C", 4: "E", 5: "F"}
    for idx, role in roles.items():
        db.add(
            SheetMapping(
                spreadsheet_key=connector.spreadsheet_key,
                sheet_name="JOKER",
                column_index=idx,
                column_letter=letters[idx],
                header=headers[idx],
                role=role,
                status=MAPPING_CONFIRMED,
                confirmed_at=datetime_utc(2026, 10, 27),
            )
        )
    db.commit()


def _seed_campaign(
    db,
    account_id,
    name,
    business_date=date(2026, 10, 25),
    recognition=RECOGNITION_CONFIRMED,
    tz_name="Asia/Ho_Chi_Minh",
):
    """Campaign CONFIRMED với kỳ báo cáo theo mã ngày trong tên (D-026)."""
    from app.models.customer import Customer

    customer = db.execute(select(Customer).where(Customer.name == "JOKER")).scalar_one_or_none()
    if customer is None:
        customer = Customer(name="JOKER")
        db.add(customer)
        db.flush()
    account = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == account_id)).scalar_one_or_none()
    if account is None:
        account = AdAccount(meta_ad_account_id=account_id, name="acc", timezone_name=tz_name)
        db.add(account)
        db.flush()
    campaign = Campaign(
        meta_campaign_id=f"cmp_{name}_{account_id}",
        ad_account_id=account.id,
        customer_id=customer.id,
        name=name,
        recognition_status=recognition,
        meta_status="ACTIVE",
        report_period_start=business_date,
        report_period_end=business_date,
    )
    db.add(campaign)
    db.commit()
    return campaign, account.id


def _rows_for_account(result, account_id):
    return [r for r in result["rows"] if r.get("ad_account_id") == account_id]


def _with_account(rows, account_id):
    patched = [list(r) for r in rows]
    patched[2][2] = account_id
    return patched


def test_needs_mapping_when_mapping_missing(db):
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    result = compare_sheet_with_db(db, connector, "JOKER")
    assert result["summary"]["status"] == COMPARE_NEEDS_MAPPING


def test_match_usd_cumulative_sum(db):
    """D-036: Meta = tổng tích lũy snapshot VERIFIED mới nhất (không delta ngày)."""
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    campaign, _ = _seed_campaign(db, "111111111111111", "1025-JOKER")
    # campaign bắt đầu ngày trước (28/09) — tổng tích lũy đến thời điểm kiểm tra
    add_snapshot(db, campaign, datetime_utc(2026, 9, 28, 9), 9.0)
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 9), 10.0)
    result = compare_sheet_with_db(db, connector, "JOKER")
    row = _rows_for_account(result, "111111111111111")[0]
    assert row["status"] == COMPARE_MATCH
    assert row["meta_cumulative_spend"] == 10.0
    assert row["method"] == "cumulative-sum"
    assert row["meta_campaigns"][0]["campaign_id"] == campaign.meta_campaign_id


def test_diff_when_cumulative_mismatch(db):
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    campaign, _ = _seed_campaign(db, "111111111111112", "1025-JOKER")
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 20), 7.5)
    connectors = DetailConnector(_with_account(DETAIL_ROWS, "111111111111112"), MERGES)
    result = compare_sheet_with_db(db, connectors, "JOKER")
    row = _rows_for_account(result, "111111111111112")[0]
    assert row["status"] == COMPARE_DIFF
    assert row["delta"] == 2.5


def test_checkpoint_and_latest_not_double_counted(db):
    """Test yêu cầu #2: checkpoint 09:00=1000.00, latest 20:00=1002.84 → tổng 1002.84 (không cộng trùng)."""
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    account_id = f"11111111111010{next(_account_seq):03d}"
    campaign, _ = _seed_campaign(db, account_id, "1025-JOKER")
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 2), 1000.00, is_checkpoint_9h=True)  # 09:00 VN = 02:00Z
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 13), 1002.84)  # 20:00 VN
    rows = [list(r) for r in DETAIL_ROWS]
    rows[2][2] = account_id
    rows[2][4] = 1002.84
    result = compare_sheet_with_db(db, DetailConnector(rows, MERGES), "JOKER")
    row = _rows_for_account(result, account_id)[0]
    assert row["status"] == COMPARE_MATCH
    assert row["meta_cumulative_spend"] == 1002.84


def test_multiple_campaigns_same_day_accumulated(db):
    """Test yêu cầu #3: nhiều campaign cùng account + cùng ngày nghiệp vụ → cộng tổng tích lũy."""
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    account_id = f"11111111111010{next(_account_seq):03d}"
    c1, _ = _seed_campaign(db, account_id, "1025-JOKER-1")
    c2, _ = _seed_campaign(db, account_id, "1025-JOKER-2")
    c3, _ = _seed_campaign(db, account_id, "1025-JOKER-3")
    add_snapshot(db, c1, datetime_utc(2026, 10, 25, 9), 4.0)
    add_snapshot(db, c2, datetime_utc(2026, 10, 25, 9), 6.0)
    add_snapshot(db, c3, datetime_utc(2026, 10, 25, 9), 100.0)  # có đủ c3 nhưng chỉ c1+c2 → 10
    rows = [list(r) for r in DETAIL_ROWS]
    rows[2][2] = account_id
    result = compare_sheet_with_db(db, DetailConnector(rows, MERGES), "JOKER")
    row = _rows_for_account(result, account_id)[0]
    assert row["status"] == COMPARE_DIFF  # sheet 10 vs tổng c3 có 100 → khác
    assert row["meta_cumulative_spend"] == 110.0
    assert len(row["meta_campaigns"]) == 3


def test_timezone_independent_business_date(db):
    """Test yêu cầu #4: account UTC-7 / UTC+3 / UTC+7 — ngày nghiệp vụ theo mã ngày tên, KHÔNG theo ngày Meta."""
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    for tz in ("America/Los_Angeles", "Europe/Moscow", "Asia/Ho_Chi_Minh"):
        account_id = f"11111111111{len(tz):02d}{next(_account_seq):03d}1"[:15]
        campaign, _ = _seed_campaign(db, account_id, "1025-JOKER", tz_name=tz)
        # snapshot chậm (12:00Z) vẫn thuộc ngày nghiệp vụ 25/10 theo tên campaign
        add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 12), 10.0)
        rows = [list(r) for r in DETAIL_ROWS]
        rows[2][2] = account_id
        result = compare_sheet_with_db(db, DetailConnector(rows, MERGES), "JOKER")
        row = _rows_for_account(result, account_id)[0]
        assert row["status"] == COMPARE_MATCH, tz
        assert row["sheet_date"] == "2026-10-25"


def test_replaced_account_old_campaign_still_compared(db):
    """Test yêu cầu #5: account bị thay thế (REPLACED) — campaign cũ vẫn được ghép + có tiền trôi."""
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    old_account_id = f"11111111111010{next(_account_seq):03d}"
    campaign, account_row_id = _seed_campaign(db, old_account_id, "1025-JOKER")
    # checkpoint 09:00 đầy đủ + latest cao hơn → tiền trôi 2.00 (D-023), campaign cũ vẫn so khớp theo tích lũy
    checkpoint = add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 2), 8.0, is_checkpoint_9h=True)
    add_snapshot(db, campaign, datetime_utc(2026, 10, 26, 13), 10.0)
    from app.models.spend import DriftRecord

    drift = DriftRecord(
        campaign_id=campaign.id,
        checkpoint_snapshot_id=checkpoint.id,
        latest_snapshot_id=checkpoint.id,
        drift_amount=2.0,
    )
    drift.latest_snapshot_id = checkpoint.id
    db.add(drift)
    db.commit()
    # account cũ bị thay thế
    new_account = AdAccount(meta_ad_account_id=f"2222222222{next(_account_seq):03d}", name="new", timezone_name="Asia/Ho_Chi_Minh")
    db.add(new_account)
    db.flush()
    from app.models import AdAccountAssignment

    db_obj_old = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == old_account_id)).scalar_one()
    db_obj_old.status = "REPLACED"
    db_obj_old.replaced_by_id = new_account.id
    db.commit()
    rows = [list(r) for r in DETAIL_ROWS]
    rows[2][2] = old_account_id
    result = compare_sheet_with_db(db, DetailConnector(rows, MERGES), "JOKER")
    row = _rows_for_account(result, old_account_id)[0]
    assert row["status"] == COMPARE_MATCH
    assert row["meta_cumulative_spend"] == 10.0


def test_rerun_same_data_no_duplication(db):
    """Test yêu cầu #6: chạy lại cùng dữ liệu không cộng trùng (unique key + logic mới)."""
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    account_id = f"11111111111010{next(_account_seq):03d}"
    campaign, _ = _seed_campaign(db, account_id, "1025-JOKER")
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 9), 10.0)
    patched = _with_account(DETAIL_ROWS, account_id)
    first_run = compare_sheet_with_db(db, DetailConnector(patched, MERGES), "JOKER")
    second_run = compare_sheet_with_db(db, DetailConnector(patched, MERGES), "JOKER")
    assert first_run == second_run
    row = _rows_for_account(first_run, account_id)[0]
    assert row["meta_cumulative_spend"] == 10.0
    assert len(row["meta_campaigns"]) == 1  # campaign ID chỉ đếm một lần


def test_unrecognized_campaign_not_included(db):
    """Test yêu cầu #7: campaign UNRECOGNIZED không tự ghép vào đối soát."""
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    account_id = f"11111111111010{next(_account_seq):03d}"
    campaign, _ = _seed_campaign(db, account_id, "no-date-code-campaign", recognition=RECOGNITION_UNRECOGNIZED, business_date=None)
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 9), 10.0)
    rows = [list(r) for r in DETAIL_ROWS]
    rows[2][2] = account_id
    result = compare_sheet_with_db(db, DetailConnector(rows, MERGES), "JOKER")
    row = _rows_for_account(result, account_id)[0]
    assert row["status"] == COMPARE_NO_META


def test_usd_vnd_with_confirmed_rate(db):
    """Test yêu cầu #8: VND chỉ quy đổi khi có tỷ giá ĐÃ XÁC NHẬN truyền vào; KHÔNG có → NEEDS_RATE."""
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    account_id = f"11111111111010{next(_account_seq):03d}"
    campaign, _ = _seed_campaign(db, account_id, "1025-JOKER")
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 9), 10.0)  # USD
    # 1) chưa có tỷ giá duyệt → NEEDS_CONFIRMATION_RATE
    rows = [list(r) for r in DETAIL_ROWS]
    rows[2][2] = account_id
    rows[2][4] = None
    result_no_rate = compare_sheet_with_db(db, DetailConnector(rows, MERGES), "JOKER")
    row_no_rate = _rows_for_account(result_no_rate, account_id)[0]
    assert row_no_rate["status"] == COMPARE_NEEDS_RATE
    # 2) có tỷ giá duyệt (27135) → sheet VND 271350 vs meta 10 USD × 27135 = 271350 → MATCH
    result_with_rate = compare_sheet_with_db(db, DetailConnector(rows, MERGES), "JOKER", confirmed_rate=27135.0)
    row_rate = _rows_for_account(result_with_rate, account_id)[0]
    assert row_rate["status"] == COMPARE_MATCH
    assert row_rate["meta_cumulative_spend_vnd"] == 271350.0


def test_special_tab_skipped(db):
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    result = compare_sheet_with_db(db, connector, "TỔNG T10")
    assert result["summary"]["status"] == COMPARE_SKIPPED
    assert result["sheet_type"] == "SUMMARY"


def test_skip_rows_without_account_id(db):
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    account_id = f"11111111111010{next(_account_seq):03d}"
    campaign, _ = _seed_campaign(db, account_id, "1025-JOKER")
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 9), 10.0)
    patched = _with_account(DETAIL_ROWS, account_id)
    result = compare_sheet_with_db(db, DetailConnector(patched, MERGES), "JOKER")
    # chỉ 1 dòng có account (dòng 4 không có ID) — không tạo row rác
    assert len(result["rows"]) == 1


def test_tolerance_by_currency_configurable(db, monkeypatch):
    monkeypatch.delenv("ADSOS_COMPARE_TOLERANCE_USD", raising=False)
    monkeypatch.delenv("ADSOS_COMPARE_TOLERANCE_VND", raising=False)
    assert tolerance_for_currency("USD") == 0.01
    assert tolerance_for_currency("VND") == 1.0
    monkeypatch.setenv("ADSOS_COMPARE_TOLERANCE_VND", "1000")
    assert tolerance_for_currency("VND") == 1000.0


# --- Phiên #15: kiểm tra chuyển đổi serial Google Sheets (brief #1) ---


def test_serial_to_date_no_off_by_one(db):
    """Brief #1: 46296 = 01/10/2026, 46320 = 25/10/2026, 46321 = 26/10/2026 (KHÔNG 25/10)."""
    assert _serial_to_date(46296) == date(2026, 10, 1)
    assert _serial_to_date(46320) == date(2026, 10, 25)
    assert _serial_to_date(46321) == date(2026, 10, 26)
    # đổi chữ: 46319 = 24/10, 46322 = 27/10 — lệch một ngày bị tách đúng biên
    assert _serial_to_date(46319) == date(2026, 10, 24)
    assert _serial_to_date(46322) == date(2026, 10, 27)
    assert _serial_to_date("abc") is None
    assert _serial_to_date(None) is None


# --- Phiên #15: nhận diện campaign 4 dạng mã ngày (brief #2) ---


def test_extract_report_dates_slash_and_safety():
    """MMDD/DDMM (4 số liền) + MM/DD, DD/MM (2/2 dấu /); không nhận chuỗi trong mã khác; mơ hồ → None."""
    d25 = date(2026, 10, 25)
    # cả 4 cách đặt tên → 25/10
    assert extract_report_dates("1025-JOKER") == d25
    assert extract_report_dates("2510 JOKER") == d25
    assert extract_report_dates("10/25 JOKER") == d25
    assert extract_report_dates("25/10 JOKER") == d25
    assert extract_report_dates("PH1025-JOKER-ABC") == d25
    # mơ hồ 4 số liền: 1102 (02/11 MMDD hoặc 11/02 DDMM — khác nhau) → không tự ghép
    assert extract_report_dates("1102-JOKER") is None
    # mơ hồ có dấu: 11/02 (02/11 MM/DD hay 11/02 DD/MM — khác nhau) → không tự ghép
    assert extract_report_dates("11/02 JOKER") is None
    # không nhận 4 chữ số nằm giữa chuỗi số khác (mã TK/KH 6 chữ số...)
    assert extract_report_dates("TK678910") is None
    assert extract_report_dates("10250-JOKER") is None
    assert extract_report_dates("102550-JOKER") is None
    # không nhận 2/2 cạnh số khác
    assert extract_report_dates("110/25-JOKER") is None
    assert extract_report_dates("10/251-JOKER") is None
    # không có mã → None
    assert extract_report_dates("JOKER-khong-ma-ngay") is None


def test_currency_recognition_gbp_eur_not_vnd_default():
    """Brief #4: GBP/EUR nhận diện riêng, không mặc định USD/VND; header lạ → None chờ xác nhận."""
    assert currency_from_header("USD") == "USD"
    assert currency_from_header("£ spend") == "GBP"
    assert currency_from_header("EUR total") == "EUR"
    assert currency_from_header("VND") == "VND"
    assert currency_from_header("Tiêu") is None


def test_gbp_sheet_vs_meta_usd_needs_rate_no_vnd_default(db):
    """Brief #4: tab GBP — KHÔNG tự coi là USD hay VND; Meta USD ≠ GBP → chờ tỷ giá duyệt."""
    from app.models.sheets import MAPPING_CONFIRMED, SheetMapping

    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    # tab GBP: mapping cột F (index 5) SPEND với header GBP — currency_from_header nhận diện riêng
    db.execute(
        delete(SheetMapping).where(
            SheetMapping.spreadsheet_key == connector.spreadsheet_key,
            SheetMapping.sheet_name == "JOKER",
        )
    )
    for idx, role, header in ((0, "DATE", "NGÀY"), (2, "ACCOUNT", "ID TK"), (5, "SPEND", "GBP")):
        db.add(
            SheetMapping(
                spreadsheet_key=connector.spreadsheet_key,
                sheet_name="JOKER",
                column_index=idx,
                column_letter={0: "A", 2: "C", 5: "F"}[idx],
                header=header,
                role=role,
                status=MAPPING_CONFIRMED,
                confirmed_at=datetime_utc(2026, 10, 27),
            )
        )
    db.commit()
    account_id = f"11111111111010{next(_account_seq):03d}"
    campaign, _ = _seed_campaign(db, account_id, "1025-JOKER")
    add_snapshot(db, campaign, datetime_utc(2026, 10, 25, 9), 10.0)  # Meta USD
    rows = [list(r) for r in DETAIL_ROWS]
    rows[2][2] = account_id
    result = compare_sheet_with_db(db, DetailConnector(rows, MERGES), "JOKER")
    row = _rows_for_account(result, account_id)[0]
    assert row["sheet_currency"] == "GBP"
    assert row["status"] == COMPARE_NEEDS_RATE
    assert result["summary"]["needs_rate"] == 1


# --- Phiên #15: account ID trùng cùng ngày (brief #5 mapping) ---


def test_duplicate_account_same_day_needs_confirmation(db):
    """Brief #5: cùng ID tài khoản xuất hiện nhiều lần trong cùng ngày mà chưa rõ quy tắc phân bổ → NEEDS_CONFIRMATION, không tự cộng."""
    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    account_id = "11111111111010999"
    rows = [list(r) for r in DETAIL_ROWS]
    rows[2][2] = account_id
    rows[2][4] = 10.0
    # dòng 4 (index 3) cùng ngày (46320) cùng account — NEEDS_CONFIRMATION
    rows[3][2] = account_id
    rows[3][4] = 5.0
    result = compare_sheet_with_db(db, DetailConnector(rows, MERGES), "JOKER")
    dup_rows = _rows_for_account(result, account_id)
    assert len(dup_rows) == 2
    assert all(r["status"] == COMPARE_NEEDS_CONFIRMATION for r in dup_rows)
    assert all("phân bổ" in r["note"] for r in dup_rows)


# --- Phiên #15: tài khoản chuyển giao giữa các khách (brief #3) ---


def test_transferred_account_multi_owner_needs_confirmation(db):
    """Brief #3: account từng dùng cho 2 khách, cùng account + ngày nghiệp vụ có campaign thuộc 2 khách → không tự gán số tiền."""
    from app.models.customer import Customer

    connector = DetailConnector(DETAIL_ROWS, MERGES)
    _seed_mappings(db, connector)
    account_id = "11111111111010888"
    c1, _ = _seed_campaign(db, account_id, "1025-JOKER")  # JOKER — CONFIRMED
    other = Customer(name="LUNA")
    db.add(other)
    db.flush()
    account = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == account_id)).scalar_one()
    c2 = Campaign(
        meta_campaign_id="cmp_1025-LUNA_moved",
        ad_account_id=account.id,
        customer_id=other.id,
        name="1025-LUNA",
        recognition_status=RECOGNITION_CONFIRMED,
        meta_status="ACTIVE",
        report_period_start=date(2026, 10, 25),
        report_period_end=date(2026, 10, 25),
    )
    db.add(c2)
    add_snapshot(db, c1, datetime_utc(2026, 10, 25, 9), 10.0)
    add_snapshot(db, c2, datetime_utc(2026, 10, 25, 9), 5.0)
    db.commit()
    rows = [list(r) for r in DETAIL_ROWS]
    rows[2][2] = account_id
    result = compare_sheet_with_db(db, DetailConnector(rows, MERGES), "JOKER")
    row = _rows_for_account(result, account_id)[0]
    assert row["status"] == COMPARE_NEEDS_CONFIRMATION
    assert "chuyển giao" in row["note"]


# --- Phiên #15: live sheets không có Meta token → NO_LIVE_META_DATA (brief #6) ---


def test_no_live_meta_data_when_real_spreadsheet_without_meta_token(db, monkeypatch):
    """Brief #6: spreadsheet THẬT + chưa có Meta token hợp lệ → NO_LIVE_META_DATA; KHÔNG dùng mock khẳng định MATCH."""
    monkeypatch.delenv("ADSOS_META_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ADSOS_META_TOKEN_MAP", raising=False)

    class LiveKeyConnector(DetailConnector):
        spreadsheet_key = "real-spreadsheet-key"

    _seed_mappings(db, LiveKeyConnector(DETAIL_ROWS, MERGES))
    assert meta_live_configured() is False
    result = compare_sheet_with_db(db, LiveKeyConnector(DETAIL_ROWS, MERGES), "JOKER")
    assert result["meta_live"] is False
    rows = _rows_for_account(result, "111111111111111")
    assert len(rows) == 1
    assert rows[0]["status"] == COMPARE_NO_LIVE_META
    assert result["summary"]["no_live_meta_data"] == 1
