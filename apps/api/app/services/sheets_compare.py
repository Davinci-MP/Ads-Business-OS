"""Báo cáo đối chiếu Google Sheets ↔ chi tiêu Meta trong DB (Q-007, chỉ đọc).

Quy tắc D-036 (bản cập nhật 2026-10-27 — chủ dự án duyệt):
- KHÔNG dùng công thức `cum(day) − cum(day−1)` theo ngày Meta làm mặc định.
- Đối chiếu theo **Customer + ngày nghiệp vụ + Ad Account ID**:
  - ngày nghiệp vụ của campaign lấy từ **mã ngày trong tên campaign** (MMDD/DDMM, D-026),
    KHÔNG lấy ngày Meta làm căn cứ duy nhất;
  - chi tiêu = **tổng tích lũy từ khi campaign bắt đầu** (snapshot VERIFIED mới nhất,
    D-008); nhiều campaign hợp lệ cùng account + cùng ngày nghiệp vụ → cộng tổng
    tích lũy (mỗi Campaign ID chỉ đếm một lần — unique `meta_campaign_id`);
- VND (Sheets) vs USD (Meta) → NEEDS_CONFIRMATION (chờ tỷ giá Q-005), KHÔNG tự
  đổi tiền; chỉ quy đổi khi có tỷ giá đã được phê duyệt truyền vào.
- Tolerance cấu hình theo đơn vị tiền (env `ADSOS_COMPARE_TOLERANCE_USD` mặc định
  0.01; `ADSOS_COMPARE_TOLERANCE_VND` mặc định 1 đ) — KHÔNG chia sẻ một giá trị.
- Mapping phải CONFIRMED đủ DATE + ACCOUNT + SPEND → thiếu → NEEDS_MAPPING.
- Meta API lỗi / checkpoint trễ: theo meta_sync (không đè số đã xác nhận, không
  giả checkpoint) — ở đây chỉ ĐỌC snapshot VERIFIED, không tự tạo số.
- KHÔNG ghi gì vào Google Sheets; chỉ đọc + so khớp với DB nội bộ.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ad_account import AdAccount
from app.models.campaign import RECOGNITION_CONFIRMED, Campaign
from app.models.sheets import MAPPING_CONFIRMED, SheetMapping
from app.models.spend import DATA_VERIFIED, SpendSnapshot
from app.services.sheets_structure import classify_sheet, resolve_row_dates

COMPARE_MATCH = "MATCH"
COMPARE_DIFF = "DIFF"
COMPARE_NO_META = "NO_META_SNAPSHOTS"
COMPARE_NO_LIVE_META = "NO_LIVE_META_DATA"
COMPARE_NEEDS_MAPPING = "NEEDS_MAPPING"
COMPARE_NEEDS_RATE = "NEEDS_CONFIRMATION_RATE"
COMPARE_NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
COMPARE_UNRECOGNIZED_CURRENCY = "NEEDS_CONFIRMATION"
COMPARE_SKIPPED = "SKIPPED"

_TOLERANCE_USD_ENV = "ADSOS_COMPARE_TOLERANCE_USD"
_TOLERANCE_VND_ENV = "ADSOS_COMPARE_TOLERANCE_VND"

_DEFAULT_TOLERANCE = {"USD": 0.01, "VND": 1.0}

_CURRENCY_TOKENS = {
    "usd": "USD",
    "$": "USD",
    "vnd": "VND",
    "đ": "VND",
    "gbp": "GBP",
    "£": "GBP",
    "eur": "EUR",
    "€": "EUR",
}


def currency_from_header(header: Optional[str]) -> Optional[str]:
    """Đơn vị tiền từ header cột — USD/VND/GBP/EUR; không nhận ra → None (chờ xác nhận)."""
    text = str(header or "").strip().lower()
    if not text:
        return None
    for token, currency in _CURRENCY_TOKENS.items():
        if token in text:
            return currency
    return None


def tolerance_for_currency(currency: str) -> float:
    """Tolerance theo đơn vị tiền — cấu hình qua env, mặc định USD 0.01 / VND 1 đ.

    GBP/EUR chưa được duyệt cấu hình tolerance riêng → dùng default USD (0.01)
    và gắn NEEDS_CONFIRMATION ở mức dòng nếu nguồn không cùng đơn vị.
    """
    env_name = _TOLERANCE_USD_ENV if currency != "VND" else _TOLERANCE_VND_ENV
    raw = os.environ.get(env_name, "").strip()
    if raw:
        try:
            return max(float(raw), 0.0)
        except ValueError:
            pass
    return _DEFAULT_TOLERANCE.get(currency, 0.01)


def meta_live_configured() -> bool:
    """Có Meta access token hợp lệ trong env không (Q-009) — chỉ kiểm tra sự tồn tại."""
    if os.environ.get("ADSOS_META_ACCESS_TOKEN", "").strip():
        return True
    token_map = os.environ.get("ADSOS_META_TOKEN_MAP", "").strip()
    return bool(token_map)


def _confirmed_columns(db: Session, spreadsheet_key: str, sheet_name: str) -> dict[int, dict[str, Any]]:
    rows = db.execute(
        select(SheetMapping).where(
            SheetMapping.spreadsheet_key == spreadsheet_key,
            SheetMapping.sheet_name == sheet_name,
            SheetMapping.status == MAPPING_CONFIRMED,
        )
    ).scalars().all()
    return {row.column_index: {"role": row.role, "header": row.header} for row in rows}


def _serial_to_date(serial: Any) -> Optional[date]:
    """Serial ngày Excel (origin 1899-12-30) → date."""
    try:
        return date(1899, 12, 30) + timedelta(days=int(serial))
    except (ValueError, TypeError, OverflowError):
        return None


def _latest_verified_cumulative(db: Session, campaign_id: int) -> Optional[float]:
    """Tổng chi tiêu tích lũy của campaign = snapshot VERIFIED mới nhất (D-008/D-011)."""
    latest = db.execute(
        select(SpendSnapshot)
        .where(
            SpendSnapshot.campaign_id == campaign_id,
            SpendSnapshot.data_status == DATA_VERIFIED,
        )
        .order_by(SpendSnapshot.snapshot_at.desc(), SpendSnapshot.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return None if latest is None else float(latest.spend_amount)


def _meta_cumulative_by_account_business_day(
    db: Session, meta_ad_account_id: str, business_day: date
) -> dict[str, Any]:
    """Tổng chi tiêu tích lũy của các campaign (account, ngày nghiệp vụ) — D-036.

    Lọc: account khớp ID (chuẩn hoá act_/số), campaign **CONFIRMED**, ngày
    nghiệp vụ theo `report_period_*` (mã ngày trong tên — D-026, KHÔNG phải
    ngày Meta). Mỗi Campaign ID chỉ cộng một lần (unique meta_campaign_id).
    """
    account = db.execute(
        select(AdAccount).where(AdAccount.meta_ad_account_id.isnot(None)).where(
            AdAccount.meta_ad_account_id.in_(
                [meta_ad_account_id, f"act_{meta_ad_account_id}", meta_ad_account_id.replace("act_", "")]
            )
        )
    ).scalar_one_or_none()
    if account is None:
        return {"campaigns": [], "total": None}
    campaigns = db.execute(
        select(Campaign).where(
            Campaign.ad_account_id == account.id,
            Campaign.recognition_status == RECOGNITION_CONFIRMED,
            Campaign.report_period_start == business_day,
            Campaign.report_period_end == business_day,
        )
    ).scalars().all()
    matched: list[dict[str, Any]] = []
    total = 0.0
    for campaign in campaigns:
        cumulative = _latest_verified_cumulative(db, campaign.id)
        if cumulative is None:
            continue  # chưa có snapshot VERIFIED → không cộng 0 giả (D-011)
        matched.append({
            "campaign_id": campaign.meta_campaign_id,
            "campaign_name": campaign.name,
            "customer_id": campaign.customer_id,
            "business_date": business_day.isoformat(),
            "cumulative_spend": round(cumulative, 2),
        })
        total += cumulative
    if not matched:
        return {"campaigns": [], "total": None}
    return {"campaigns": matched, "total": round(total, 2)}


def compare_sheet_with_db(
    db: Session,
    connector: Any,
    sheet_name: str,
    confirmed_rate: Optional[float] = None,
) -> dict[str, Any]:
    """Đối chiếu các dòng account/ngày nghiệp vụ của 1 tab khách với DB.

    `confirmed_rate`: tỷ giá USD→VND **đã được phê duyệt** (Q-005 còn mở — chỉ
    truyền vào sau khi chủ dự án xác nhận nguồn tỷ giá). KHÔNG tự đổi tiền.

    Trả {sheet_name, summary, rows}. CHỈ ĐỌC — không ghi Sheets, không ghi DB.
    """
    spreadsheet_key = connector.spreadsheet_key
    result_base = {
        "sheet_name": sheet_name,
        "sheet_type": classify_sheet(sheet_name),
        "spreadsheet_key": spreadsheet_key,
    }
    sheet_type = classify_sheet(sheet_name)
    if sheet_type != "CUSTOMER":
        result_base["summary"] = {"status": COMPARE_SKIPPED, "rows": 0}
        result_base["rows"] = []
        result_base["note"] = f"tab loại {sheet_type} — không tự đồng bộ/đối chiếu dòng khách (Q-007/D-035)"
        return result_base
    mapping = _confirmed_columns(db, spreadsheet_key, sheet_name)
    date_col = next((idx for idx, m in sorted(mapping.items()) if m["role"] == "DATE"), None)
    account_col = next((idx for idx, m in sorted(mapping.items()) if m["role"] == "ACCOUNT"), None)
    spend_cols = [idx for idx, m in sorted(mapping.items()) if m["role"] == "SPEND"]

    if date_col is None or account_col is None or not spend_cols:
        result_base["summary"] = {"status": COMPARE_NEEDS_MAPPING, "rows": 0}
        result_base["rows"] = []
        result_base["note"] = (
            "mapping chưa CONFIRMED đủ DATE + ACCOUNT + SPEND — không đối chiếu; "
            "chủ dự án xác nhận mapping trên /sheets trước"
        )
        return result_base

    if any(item.get("hidden") and item["title"].casefold() == sheet_name.casefold() for item in connector.list_sheets()):
        result_base["summary"] = {"status": COMPARE_SKIPPED, "rows": 0}
        result_base["rows"] = []
        result_base["note"] = "Tab ẩn không được đọc dữ liệu hoặc đối chiếu."
        return result_base
    detail = connector.read_sheet_detail(sheet_name)
    dates_by_row = resolve_row_dates(detail, date_col=date_col)
    live_required = spreadsheet_key != "mock"
    meta_live = meta_live_configured()

    rows = detail.get("rows") or []
    merges = detail.get("merges") or []
    sep_rows = {m["start_row"] - 1 for m in merges if "start_row" in m}

    # Pass 1: thu thập dòng hồ sơ (account 15 số + ngày serial + spend)
    entries: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        if row_index in sep_rows:
            continue
        if account_col >= len(row):
            continue
        sheet_date_info = dates_by_row.get(row_index)
        raw_id = row[account_col]
        if sheet_date_info is None or raw_id is None or str(raw_id).strip() == "":
            continue
        account_id = str(raw_id).strip()
        if not account_id.isdigit() or len(account_id) < 13:
            continue  # nhãn text / không phải ad account ID
        spend_col = next((idx for idx in spend_cols if idx < len(row) and isinstance(row[idx], (int, float))), None)
        if spend_col is None:
            skipped_rows.append({
                "sheet_row": row_index + 1,
                "ad_account_id": account_id,
                "status": COMPARE_SKIPPED,
                "note": "dòng không có giá trị chi tiêu (dòng trống)",
            })
            continue
        sheet_currency = currency_from_header(mapping[spend_col]["header"])
        day = _serial_to_date(sheet_date_info["value"]) if sheet_date_info["kind"] == "number" else None
        if day is None:
            skipped_rows.append({
                "sheet_row": row_index + 1,
                "ad_account_id": account_id,
                "status": COMPARE_SKIPPED,
                "note": "ngày dạng text/mơ hồ — không tự phán dd/MM (D-026)",
            })
            continue
        entries.append({
            "row_index": row_index,
            "sheet_row": row_index + 1,
            "account_id": account_id,
            "day": day,
            "spend_col": spend_col,
            "sheet_value": float(row[spend_col]),
            "sheet_currency": sheet_currency,
        })

    # Dùng trùng (account ID, ngày nghiệp vụ) mà chưa rõ quy tắc phân bổ → NEEDS_CONFIRMATION
    dup_keys: set[tuple[str, date]] = set()
    seen: set[tuple[str, date]] = set()
    for e in entries:
        key = (e["account_id"], e["day"])
        if key in seen:
            dup_keys.add(key)
        seen.add(key)

    # Pass 2: đối chiếu từng dòng
    row_reports: list[dict[str, Any]] = list(skipped_rows)
    matched = diff = no_meta = needs_rate = needs_confirmation = needs_live = 0
    for e in entries:
        account_id, day = e["account_id"], e["day"]
        report: dict[str, Any] = {
            "sheet_row": e["sheet_row"],
            "sheet_date": day.isoformat(),
            "sheet_value": round(e["sheet_value"], 2),
            "sheet_column": mapping[e["spend_col"]]["header"],
            "ad_account_id": account_id,
        }
        if e["sheet_currency"] is None:
            report["status"] = COMPARE_UNRECOGNIZED_CURRENCY
            report["note"] = (
                f"đơn vị tiền cột '{mapping[e['spend_col']]['header']}' không nhận ra "
                "(USD/VND/GBP/EUR) — không tự mặc định VND; chờ xác nhận"
            )
            needs_confirmation += 1
            row_reports.append(report)
            continue
        report["sheet_currency"] = e["sheet_currency"]
        if (account_id, day) in dup_keys:
            report["status"] = COMPARE_NEEDS_CONFIRMATION
            report["note"] = "cùng ID tài khoản xuất hiện nhiều lần trong cùng ngày — quy tắc phân bổ chưa rõ, chờ chủ dự án"
            needs_confirmation += 1
            row_reports.append(report)
            continue
        if live_required and not meta_live:
            # Live sheets nhưng chưa có Meta token hợp lệ → KHÔNG dùng mock/dữ liệu cũ
            # trong DB để khẳng định MATCH (dữ liệu Meta thật chưa có)
            report["status"] = COMPARE_NO_LIVE_META
            report["note"] = (
                "chưa có Meta Access Token hợp lệ (env ADSOS_META_ACCESS_TOKEN / "
                "ADSOS_META_TOKEN_MAP — Q-009): không có dữ liệu Meta thật, không dùng mock/khẳng định MATCH"
            )
            needs_live += 1
            row_reports.append(report)
            continue
        meta = _meta_cumulative_by_account_business_day(db, account_id, day)
        if meta["total"] is None:
            report["status"] = COMPARE_NO_META
            report["note"] = "không có campaign CONFIRMED + snapshot VERIFIED cho (account, ngày nghiệp vụ)"
            no_meta += 1
            row_reports.append(report)
            continue
        report["meta_campaigns"] = meta["campaigns"]
        report["meta_cumulative_spend"] = meta["total"]
        owners = {c.get("customer_id") for c in meta["campaigns"]}
        if len(owners) > 1:
            # Tài khoản từng chuyển giao giữa các khách / campaign cùng account khác khách
            # mà thiếu căn cứ kỳ sử dụng → không tự gán số tiền
            report["status"] = COMPARE_NEEDS_CONFIRMATION
            report["note"] = (
                f"campaign của account + ngày nghiệp vụ này thuộc {len(owners)} khách khác nhau "
                "(tài khoản từng chuyển giao?) — không tự gán số tiền khi thiếu căn cứ kỳ sử dụng"
            )
            needs_confirmation += 1
            row_reports.append(report)
            continue
        tol = tolerance_for_currency(e["sheet_currency"])
        report["method"] = "cumulative-sum"
        if e["sheet_currency"] == "USD":
            # USD ↔ USD so trực tiếp (brief #4: account USD so cột USD trực tiếp,
            # không cần tỷ giá); Meta snapshot luôn USD
            delta = round(abs(e["sheet_value"] - meta["total"]), 2)
            report["delta"] = delta
            report["tolerance"] = tol
            report["status"] = COMPARE_MATCH if delta <= tol else COMPARE_DIFF
            if report["status"] == COMPARE_MATCH:
                matched += 1
            else:
                diff += 1
        elif e["sheet_currency"] in ("GBP", "EUR"):
            # đơn vị chưa duyệt tolerance riêng + Meta USD khác đơn vị → chờ xác nhận
            report["status"] = COMPARE_NEEDS_RATE
            report["note"] = (
                f"chi tiêu {e['sheet_currency']} so với Meta USD — cần tỷ giá đã xác nhận "
                "(Q-005) trước khi so số, không tự mặc định USD"
            )
            needs_rate += 1
        elif confirmed_rate is None or confirmed_rate <= 0:
            # VND: chỉ quy đổi khi có tỷ giá ĐÃ PHÊ DUYỆT (Q-005 còn mở)
            report["meta_cumulative_spend_usd"] = meta["total"]
            report["status"] = COMPARE_NEEDS_RATE
            report["note"] = "chi tiêu VND so với Meta USD — cần tỷ giá đã xác nhận (Q-005) trước khi so số"
            needs_rate += 1
        else:
            meta_vnd = round(meta["total"] * confirmed_rate, 2)
            report["confirmed_rate"] = confirmed_rate
            report["meta_cumulative_spend_usd"] = meta["total"]
            report["meta_cumulative_spend_vnd"] = meta_vnd
            delta = round(abs(e["sheet_value"] - meta_vnd), 2)
            report["delta"] = delta
            report["tolerance_vnd"] = tol
            report["status"] = COMPARE_MATCH if delta <= tol else COMPARE_DIFF
            if report["status"] == COMPARE_MATCH:
                matched += 1
            else:
                diff += 1
        row_reports.append(report)

    row_reports.sort(key=lambda r: (r.get("sheet_row") or 0, r.get("sheet_date") or ""))
    return {
        **result_base,
        "summary": {
            "rows_mapped": len(row_reports),
            "match": matched,
            "diff": diff,
            "no_meta_snapshots": no_meta,
            "no_live_meta_data": needs_live,
            "needs_rate": needs_rate,
            "needs_confirmation": needs_confirmation,
        },
        "meta_live": meta_live if live_required else None,
        "tolerance": {"USD": tolerance_for_currency("USD"), "VND": tolerance_for_currency("VND")},
        "rows": row_reports,
        "note": (
            "chi tiêu Meta = TỔNG TÍCH LŨY snapshot VERIFIED mới nhất của campaign CONFIRMED "
            "khớp ngày nghiệp vụ (mã ngày trong tên campaign — D-026); KHÔNG dùng "
            "cum(day)−cum(day−1) theo ngày Meta (D-036 bản cập nhật); đối chiếu theo "
            "Customer + ngày + Ad Account ID; tài khoản chuyển giao không tự gán khi thiếu "
            "căn cứ; fee 4% theo Sheets (D-021), khách lệch phí chờ xác nhận (D-037); chỉ đọc"
        ),
    }
