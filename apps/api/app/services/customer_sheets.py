"""Customer balances from explicitly linked, saved Sheets snapshots."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.ad_account import AdAccountAssignment
from app.models.customer import Customer
from app.models.sheet_reports import SheetReportClosure, SheetReportCustomerLink, SheetReportSource, SheetReportSyncAttempt
from app.services.sheet_report_store import latest_snapshot


def customer_sheets_overview(session: Session, source: SheetReportSource) -> dict:
    snapshot = latest_snapshot(session, source.id)
    closure = session.scalar(select(SheetReportClosure).where(SheetReportClosure.source_id == source.id))
    last_attempt = session.scalar(
        select(SheetReportSyncAttempt).where(SheetReportSyncAttempt.source_id == source.id)
        .order_by(SheetReportSyncAttempt.id.desc()).limit(1)
    )
    customers = session.scalars(select(Customer).order_by(Customer.name, Customer.id)).all()
    links = session.scalars(select(SheetReportCustomerLink).where(
        SheetReportCustomerLink.source_id == source.id, SheetReportCustomerLink.active.is_(True),
    )).all()
    links_by_customer = {link.customer_id: link for link in links}
    tabs = snapshot.report.get("customers", []) if snapshot else []
    now = datetime.now(timezone.utc)
    assignments = session.scalars(select(AdAccountAssignment).where(
        AdAccountAssignment.valid_from <= now,
        or_(AdAccountAssignment.valid_to.is_(None), AdAccountAssignment.valid_to > now),
    )).all()
    by_account: dict[int, list[AdAccountAssignment]] = defaultdict(list)
    for assignment in assignments:
        by_account[assignment.ad_account_id].append(assignment)
    account_counts: dict[int, int] = defaultdict(int)
    conflicts: dict[int, int] = defaultdict(int)
    for group in by_account.values():
        if len(group) == 1:
            account_counts[group[0].customer_id] += 1
        else:
            for customer_id in {item.customer_id for item in group}:
                conflicts[customer_id] += 1
    result = []
    for customer in customers:
        link = links_by_customer.get(customer.id)
        matches = [tab for tab in tabs if link and tab.get("sheet_id") == link.sheet_id]
        tab = matches[0] if len(matches) == 1 and matches[0].get("source_sheet") == link.source_title else None
        if not snapshot:
            state = "NO_SNAPSHOT"
        elif not link:
            state = "UNLINKED"
        elif not tab:
            state = "LINK_REVIEW"
        elif tab.get("profile_status") in {"SOURCE_ERROR", "STRUCTURE_ERROR"}:
            state = "SOURCE_ERROR"
        else:
            state = "LINKED"
        totals = tab.get("tab_source_totals", {}) if tab and state == "LINKED" else {}
        def value(field: str) -> str | None:
            return (totals.get(field) or {}).get("value")
        balance = value("current_balance")
        threshold = customer.budget_alert_threshold_vnd
        result.append({
            "customer_id": customer.id, "name": customer.name, "link_status": state,
            "source_sheet": tab.get("source_sheet") if tab else link.source_title if link else None,
            "budget_deposits_vnd": value("budget_deposits_vnd"), "spend_vnd": value("spend_vnd"),
            "fee": value("fee"), "current_balance": balance,
            "budget_alert_threshold_vnd": str(threshold) if threshold is not None else None,
            "low_balance": balance is not None and threshold is not None and Decimal(balance) <= threshold,
            "account_count": account_counts[customer.id], "conflicting_accounts": conflicts[customer.id],
            "data_status": tab.get("completeness_status") if tab else None,
        })
    return {
        "source_id": source.id, "source_name": source.name, "period": source.period,
        "source_active": source.active,
        "snapshot_id": snapshot.id if snapshot else None,
        "read_at": snapshot.read_at if snapshot else None,
        "quality": snapshot.quality if snapshot else None,
        "closed_snapshot_id": closure.snapshot_id if closure else None,
        "last_attempt": {"status": last_attempt.status, "error": last_attempt.error} if last_attempt else None,
        "customers": result,
    }
