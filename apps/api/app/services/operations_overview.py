"""Tổng quan vận hành từ bản lưu Sheets hiện hành; không đọc lại workbook và không ghi sổ."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import AdAccount, Campaign, Customer
from app.models.ad_account import AdAccountAssignment
from app.models.sheet_reports import (
    SheetReportClosure, SheetReportCustomerLink, SheetReportSettings, SheetReportSource,
    SheetReportSyncAttempt, SheetReportTabDismissal,
)
from app.services.sheet_report_store import latest_snapshot
from app.services.sheets_report import enrich_sheets_report

ERROR_PROFILES = {"SOURCE_ERROR", "STRUCTURE_ERROR"}
METRICS = ("customers", "accounts", "accounts_spending", "negative_balance", "needs_topup",
           "unlinked", "accounts_unassigned", "review")


def _dec(value) -> Decimal | None:
    try:
        number = Decimal(str(value)) if value not in (None, "") else None
    except InvalidOperation:
        return None
    return number if number is not None and number.is_finite() else None


def normalize_account_id(value: str) -> str:
    text = str(value or "").strip().casefold()
    return text[4:] if text.startswith("act_") else text


def _balance(tab: dict) -> Decimal | None:
    if tab.get("profile_status") in ERROR_PROFILES:
        return None
    return _dec(((tab.get("tab_source_totals") or {}).get("current_balance") or {}).get("value"))


def _scope(session: Session) -> tuple[SheetReportSource | None, str]:
    settings = session.get(SheetReportSettings, 1)
    source = session.get(SheetReportSource, settings.default_source_id) if settings and settings.default_source_id else None
    return source, "default" if source else "none"


def _build(session: Session) -> dict:
    source, _ = _scope(session)
    if source is None:
        return {"source": None}
    snapshot = latest_snapshot(session, source.id)
    closure = session.scalar(select(SheetReportClosure).where(SheetReportClosure.source_id == source.id))
    attempt = session.scalar(select(SheetReportSyncAttempt).where(SheetReportSyncAttempt.source_id == source.id)
                             .order_by(SheetReportSyncAttempt.id.desc()).limit(1))
    head = {
        "id": source.id, "name": source.name, "period": source.period, "sync_enabled": source.sync_enabled,
        "snapshot_id": snapshot.id if snapshot else None, "read_at": snapshot.read_at if snapshot else None,
        "quality": snapshot.quality if snapshot else None, "closed": closure is not None,
        "last_attempt": {"status": attempt.status, "error": attempt.error, "started_at": attempt.started_at} if attempt else None,
    }
    if snapshot is None:
        return {"source": head, "rows": {metric: [] for metric in METRICS}, "tabs": []}
    report = enrich_sheets_report(deepcopy(snapshot.report), source.period, source.spreadsheet_id)
    tabs = report.get("customers") or []
    links = {item.sheet_id: item for item in session.scalars(select(SheetReportCustomerLink).where(
        SheetReportCustomerLink.source_id == source.id, SheetReportCustomerLink.active.is_(True)))}
    dismissed = {item.sheet_id for item in session.scalars(select(SheetReportTabDismissal).where(
        SheetReportTabDismissal.source_id == source.id, SheetReportTabDismissal.active.is_(True)))}
    customers = {item.id: item for item in session.scalars(select(Customer))}
    now = datetime.now(timezone.utc)
    assigned = {
        normalize_account_id(meta_id)
        for meta_id in session.scalars(
            select(AdAccount.meta_ad_account_id).join(AdAccountAssignment, AdAccountAssignment.ad_account_id == AdAccount.id)
            .where(AdAccountAssignment.valid_from <= now,
                   or_(AdAccountAssignment.valid_to.is_(None), AdAccountAssignment.valid_to > now)))
    }
    rows: dict[str, list[dict]] = {metric: [] for metric in METRICS}
    accounts: dict[str, dict] = {}
    for tab in tabs:
        sheet_id = tab.get("sheet_id")
        if sheet_id in dismissed:
            continue
        link = links.get(sheet_id)
        customer = customers.get(link.customer_id) if link else None
        linked = bool(link and customer and link.source_title == tab.get("source_sheet"))
        balance = _balance(tab)
        base = {"sheet_id": sheet_id, "source_sheet": tab.get("source_sheet"), "profile_status": tab.get("profile_status"),
                "customer_id": customer.id if linked else None, "customer_name": customer.name if linked else None,
                "link_status": "LINKED" if linked else "LINK_REVIEW" if link else "UNLINKED",
                "balance_vnd": str(balance) if balance is not None else None}
        rows["customers"].append(base)
        if not linked:
            rows["unlinked"].append(base)
        if balance is not None and balance < 0:
            rows["negative_balance"].append(base)
        elif balance is not None and linked and customer.budget_alert_threshold_vnd is not None \
                and balance <= customer.budget_alert_threshold_vnd:
            rows["needs_topup"].append({**base, "threshold_vnd": str(customer.budget_alert_threshold_vnd)})
        if tab.get("profile_status") in ERROR_PROFILES:
            continue
        for row in tab.get("account_rows") or []:
            key = normalize_account_id(row.get("account_id"))
            if not key:
                continue
            item = accounts.setdefault(key, {"account_id": str(row.get("account_id")).strip(), "tabs": set(),
                                             "spending": False, "spend_unknown": False, "rows": 0})
            item["tabs"].add(tab.get("source_sheet"))
            item["rows"] += 1
            spend = _dec((row.get("original_spend") or {}).get("value"))
            if spend is None:
                item["spend_unknown"] = True
            elif spend > 0:
                item["spending"] = True
    for key, item in sorted(accounts.items()):
        entry = {"account_id": item["account_id"], "tabs": sorted(item["tabs"]), "day_rows": item["rows"],
                 "spend_known": item["spending"] or not item["spend_unknown"], "has_spend": item["spending"],
                 "assignment_known": key in assigned}
        rows["accounts"].append(entry)
        if item["spending"]:
            rows["accounts_spending"].append(entry)
        if key not in assigned:
            rows["accounts_unassigned"].append(entry)
    for issue in report.get("issues") or []:
        rows["review"].append({"severity": issue.get("severity"), "source": issue.get("source"), "message": issue.get("message")})
    return {"source": head, "rows": rows, "tabs": tabs, "dismissed": len(dismissed),
            "thresholds_missing": sum(1 for row in rows["customers"] if row["customer_id"]
                                      and customers[row["customer_id"]].budget_alert_threshold_vnd is None),
            "balance_missing": sum(1 for row in rows["customers"] if row["balance_vnd"] is None),
            "error_tabs": sum(1 for row in rows["customers"] if row["profile_status"] in ERROR_PROFILES)}


def operations_overview(session: Session) -> dict:
    built = _build(session)
    source = built["source"]
    internal = {
        "label": "Dữ liệu nội bộ (không phải nguồn Sheets, có thể gồm dữ liệu thử nghiệm)",
        "customers": len(session.scalars(select(Customer.id)).all()),
        "ad_accounts": len(session.scalars(select(AdAccount.id)).all()),
        "campaigns": len(session.scalars(select(Campaign.id)).all()),
        "manual_status": defaultdict(int),
    }
    for status in session.scalars(select(AdAccount.status)):
        internal["manual_status"][
            "not_updated" if status == "ACTIVE" else "updated"
        ] += 1
    internal["manual_status"] = {"updated": internal["manual_status"]["updated"],
                                 "not_updated": internal["manual_status"]["not_updated"]}
    if source is None:
        return {"source": None, "metrics": None, "internal": internal,
                "message": "Chưa chọn nguồn Sheets mặc định."}
    if source["snapshot_id"] is None:
        return {"source": source, "metrics": None, "internal": internal, "message": "Nguồn chưa có bản lưu."}
    rows = built["rows"]
    unlinked = rows["unlinked"]
    def count(metric: str) -> int:
        return len(rows[metric])
    tasks = [
        {"key": "unlinked", "label": "Tab khách chưa liên kết", "count": count("unlinked"), "href": "/sheets#customer-setup"},
        {"key": "accounts_unassigned", "label": "TKQC chưa xác nhận phân công", "count": count("accounts_unassigned"), "href": "/accounts"},
        {"key": "review", "label": "Cảnh báo dữ liệu cần rà soát", "count": count("review"), "href": "/reports"},
    ]
    attempt = source["last_attempt"]
    if attempt and attempt["status"] in {"ERROR", "INTERRUPTED"}:
        tasks.append({"key": "sync_error", "label": "Lần đồng bộ gần nhất lỗi", "count": 1, "href": "/sheets#saved-sources"})
    return {
        "source": source, "internal": internal,
        "metrics": {
            "customers": {"count": count("customers"), "excluded_hidden_or_summary": True,
                          "dismissed": built["dismissed"], "error_tabs": built["error_tabs"], "linked": count("customers") - len(unlinked)},
            "accounts": {"count": count("accounts"), "spending": count("accounts_spending"),
                         "spend_unknown": sum(1 for row in rows["accounts"] if not row["spend_known"])},
            "negative_balance": {"count": count("negative_balance"), "balance_missing": built["balance_missing"]},
            "needs_topup": {"count": count("needs_topup"), "thresholds_missing": built["thresholds_missing"],
                            "balance_missing": built["balance_missing"]},
        },
        "tasks": tasks,
    }


def operations_list(session: Session, metric: str) -> dict:
    if metric not in METRICS:
        raise KeyError(metric)
    built = _build(session)
    return {"source": built["source"], "metric": metric, "rows": built.get("rows", {}).get(metric, [])}
