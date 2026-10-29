"""Summaries from one saved Sheets snapshot per active source period.

Basis "current": dùng bản đọc thành công mới nhất của nguồn đang hoạt động —
kể cả khi kỳ đã có bản chốt (khi đó gắn closure_note "có bản chốt"). Nếu nguồn
hoạt động không có bản đọc nào mà chính nó có bản chốt → dùng bản chốt của
chính nguồn đó. "Bản chốt luôn thắng" CHỈ áp dụng cho basis "closed": chỉ dùng
bản chốt; kỳ chưa chốt không tự thay bằng bản hiện hành.
"""
from copy import deepcopy
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.sheet_reports import (
    SheetReportClosure, SheetReportCustomerLink, SheetReportSnapshot, SheetReportSource, SheetReportSyncAttempt,
)
from app.services.sheet_report_store import latest_snapshot
from app.services.sheets_report import enrich_sheets_report, exact_decimal_sum


FLOW_FIELDS = ("budget_deposits_vnd", "spend_vnd", "fee", "billing_total", "usdt_received", "usdt_refunded", "usdt_net")


def _last_attempt(session: Session, source: SheetReportSource | None) -> dict | None:
    if source is None:
        return None
    item = session.scalar(
        select(SheetReportSyncAttempt).where(SheetReportSyncAttempt.source_id == source.id)
        .order_by(SheetReportSyncAttempt.id.desc()).limit(1)
    )
    if item is None:
        return None
    return {"status": item.status, "started_at": item.started_at, "error": item.error}


def _month_common(source: SheetReportSource, active: SheetReportSource | None, last_attempt: dict | None) -> dict:
    return {
        "source_id": source.id, "name": source.name,
        "sync_enabled": active.sync_enabled if active else False,
        "last_attempt": last_attempt,
    }


def _month_rows(session: Session, year: int, basis: str) -> list[dict]:
    """Chọn đúng một snapshot mỗi kỳ:
    - basis "current": bản đọc thành công mới nhất của nguồn đang hoạt động; nếu
      nguồn hoạt động chưa có bản đọc nào mà chính nó có bản chốt → dùng bản
      chốt của chính nguồn đó. Bản chốt của nguồn KHÁC (đã thay) không tự dùng
      khi nguồn hiệu lực không đọc được — báo MISSING_SNAPSHOT rõ ràng.
    - basis "closed": chỉ dùng bản chốt (kể cả bản chốt của nguồn đã thay);
      kỳ chưa chốt không tự thay bằng bản hiện hành."""
    if basis not in ("current", "closed"):
        raise ValueError("Basis chỉ nhận 'current' hoặc 'closed'.")
    sources = session.scalars(
        select(SheetReportSource).where(
            SheetReportSource.period >= f"{year:04d}-01",
            SheetReportSource.period <= f"{year:04d}-12",
        )
    ).all()
    by_period: dict[str, list[SheetReportSource]] = {}
    for source in sources:
        by_period.setdefault(source.period, []).append(source)
    closures = session.scalars(
        select(SheetReportClosure).where(SheetReportClosure.source_id.in_([source.id for source in sources]))
    ).all()
    closures_by_source = {closure.source_id: closure for closure in closures}
    rows = []
    for month in range(1, 13):
        period = f"{year:04d}-{month:02d}"
        period_sources = by_period.get(period, [])
        active = next((source for source in period_sources if source.active), None)
        closed = [(source, closures_by_source[source.id]) for source in period_sources if source.id in closures_by_source]
        if len(closed) > 1:
            rows.append({"period": period, "state_kind": "CONFLICTING_CLOSURES", "active": active})
            continue
        last_attempt = _last_attempt(session, active)
        if basis == "closed" and not closed:
            rows.append({
                "period": period,
                "state_kind": "NOT_CLOSED_NO_SOURCE" if active is None else "NOT_CLOSED",
                "active": active,
                "last_attempt": last_attempt,
            })
            continue
        if basis == "current" and active is not None:
            source = active
            closure = closures_by_source.get(active.id)
            active_snapshot = latest_snapshot(session, active.id)
            if active_snapshot is not None:
                snapshot = active_snapshot
            elif closure is not None:
                snapshot = session.get(SheetReportSnapshot, closure.snapshot_id)
                if snapshot is None or snapshot.source_id != source.id:
                    raise RuntimeError(f"Bản chốt nguồn {source.id} không hợp lệ.")
            else:
                snapshot = None
            if snapshot is None:
                rows.append({
                    "period": period, "state_kind": "MISSING_SNAPSHOT", "source": source,
                    "active": active, "closure": closure, "last_attempt": last_attempt,
                })
                continue
            rows.append({
                "period": period, "state_kind": "RESOLVED", "source": source, "active": active,
                "closure": closure, "period_closed": closed[0] if closed else None,
                "last_attempt": last_attempt,
                "snapshot": snapshot, "active_snapshot": active_snapshot,
            })
            continue
        source, closure = closed[0] if closed else (None, None)
        if source is None:
            rows.append({"period": period, "state_kind": "MISSING_SOURCE", "active": active})
            continue
        snapshot = session.get(SheetReportSnapshot, closure.snapshot_id)
        if snapshot is None or snapshot.source_id != source.id:
            raise RuntimeError(f"Bản chốt nguồn {source.id} không hợp lệ.")
        active_snapshot = latest_snapshot(session, active.id) if active else None
        rows.append({
            "period": period, "state_kind": "RESOLVED", "source": source, "active": active,
            "closure": closure, "period_closed": None,
            "last_attempt": last_attempt,
            "snapshot": snapshot, "active_snapshot": active_snapshot,
        })
    return rows


def _company_month(row: dict) -> dict:
    period, kind = row["period"], row["state_kind"]
    active = row.get("active")
    if kind == "CONFLICTING_CLOSURES":
        return {"period": period, "state": kind, "active_source_id": active.id if active else None}
    last_attempt = row.get("last_attempt")
    if kind == "NOT_CLOSED_NO_SOURCE":
        return {"period": period, "state": kind, "active_source_id": None, "last_attempt": last_attempt}
    if kind == "NOT_CLOSED":
        active = row["active"]
        return {"period": period, "state": kind, "active_source_id": active.id,
                **_month_common(active, active, last_attempt)}
    if kind == "MISSING_SOURCE":
        return {"period": period, "state": kind}
    if kind == "MISSING_SNAPSHOT":
        active = row.get("active")
        return {
            "period": period, "state": kind,
            **_month_common(row["source"], active, last_attempt),
            "active_source_id": active.id if active else None,
            "latest_read_at": None,
        }
    source, closure, snapshot = row["source"], row["closure"], row["snapshot"]
    active_snapshot = row["active_snapshot"]
    report = enrich_sheets_report(deepcopy(snapshot.report), period, source.spreadsheet_id)
    mismatches = [
        {"customer": customer["source_sheet"], "periods": [item for item in customer.get("source_periods", []) if item != period]}
        for customer in report.get("customers", [])
        if any(item != period for item in customer.get("source_periods", []))
    ]
    snapshot_is_closure = closure is not None and snapshot.id == closure.snapshot_id
    entry: dict = {
        "period": period,
        **_month_common(source, active, last_attempt),
        "snapshot_id": snapshot.id,
        "active_source_id": active.id if active else None,
        "read_at": snapshot.read_at, "quality": snapshot.quality,
        "closure_snapshot_id": closure.snapshot_id if snapshot_is_closure else None,
        "closed_at": closure.closed_at if snapshot_is_closure else None,
        "latest_read_at": active_snapshot.read_at if active_snapshot else None,
        "period_mismatches": mismatches,
        "_report": report,
    }
    if snapshot_is_closure:
        entry["state"] = "CLOSED"
        if active_snapshot is not None and active_snapshot.id != snapshot.id:
            entry["closure_note"] = "Tồn tại bản đọc mới hơn bản chốt; chế độ 'Bản chốt' vẫn dùng bản chốt làm nguồn chính thức."
    else:
        entry["state"] = "PROVISIONAL"
        if row.get("period_closed") is not None:
            entry["closure_note"] = "Kỳ đã có bản chốt; chế độ Hiện hành đang dùng bản đọc mới hơn; bản chốt vẫn là nguồn chính thức ở chế độ 'Bản chốt'."
    return entry


def build_year_summary(session: Session, year: int, basis: str = "current") -> dict:
    months_no_metrics = []
    month_metrics = []
    for row in _month_rows(session, year, basis):
        entry = _company_month(row)
        report = entry.pop("_report", None)
        if report is not None:
            entry["metrics"] = report["all_customer_totals"]["metrics"]
        months_no_metrics.append(entry)
    months = months_no_metrics

    available = [month for month in months if "metrics" in month]
    flows = {}
    for field in FLOW_FIELDS:
        contributions = []
        complete = []
        for month in available:
            metric = month["metrics"][field]
            if metric["value"] is not None:
                contributions.append({"period": month["period"], "value": metric["value"]})
            if metric["status"] == "COMPLETE" and metric["value"] is not None:
                complete.append(month["period"])
        flows[field] = {
            "value": str(exact_decimal_sum([Decimal(item["value"]) for item in contributions])) if contributions else None,
            "months_with_value": len(contributions),
            "complete_months": len(complete),
            "total_months": 12,
            "missing_or_partial_months": [month["period"] for month in months if month["period"] not in complete],
            "status": "COMPLETE" if len(complete) == 12 else "PARTIAL",
            "contributions": contributions,
        }
    january = months[0] if "metrics" in months[0] else None
    latest = available[-1] if available else None
    return {
        "year": year,
        "basis": basis,
        "months": months,
        "months_with_data": len(available),
        "flows": flows,
        "opening_balance": {"period": january["period"], "metric": january["metrics"]["opening_balance"]} if january else None,
        "closing_balance": {"period": latest["period"], "metric": latest["metrics"]["current_balance"]} if latest else None,
    }


def _customer_month_values(
    report: dict, link: SheetReportCustomerLink | None,
) -> tuple[str, dict[str, dict]]:
    """Trích số của một khách từ báo cáo tháng đã enrich; trả về (link_state, values)."""
    tabs = report.get("customers", [])
    matches = [tab for tab in tabs if link and tab.get("sheet_id") == link.sheet_id]
    tab = None
    if link is None:
        state = "UNLINKED"
    elif len(matches) == 1 and matches[0].get("source_sheet") == link.source_title:
        tab = matches[0]
        if tab.get("profile_status") in {"SOURCE_ERROR", "STRUCTURE_ERROR"}:
            state, tab = "SOURCE_ERROR", None
        else:
            state = "LINKED"
    else:
        state = "LINK_REVIEW"
    values: dict[str, dict] = {}
    if tab is None:
        return state, values
    metrics = report.get("all_customer_totals", {}).get("metrics", {})
    title = tab["source_sheet"]

    def metric_for(field: str) -> dict | None:
        metric = metrics.get(field)
        if not metric:
            return None
        contributions = [item for item in metric.get("contributions", []) if item.get("customer") == title]
        if contributions:
            amount = exact_decimal_sum([Decimal(item["value"]) for item in contributions])
            return {
                "value": str(amount),
                "source": ", ".join(str(item.get("source")) for item in contributions if item.get("source")),
                "status": metric.get("status"),
            }
        return None

    for field in ("budget_deposits_vnd", "spend_vnd", "fee", "billing_total", "current_balance"):
        item = (tab.get("tab_source_totals", {}).get(field) or {})
        values[field] = {"value": item.get("value"), "source": item.get("source")} if item.get("value") is not None else {"value": None, "source": None}
    opening = tab.get("opening_balance") or {}
    values["opening_balance"] = {"value": opening.get("value"), "source": opening.get("source")} if opening.get("value") is not None else {"value": None, "source": None}
    for field in ("usdt_received", "usdt_refunded"):
        if (metric := metric_for(field)) is not None:
            values[field] = metric
        else:
            values[field] = {"value": None, "source": None}
    received = values["usdt_received"]["value"]
    refunded = values["usdt_refunded"]["value"]
    if received is not None or refunded is not None:
        net = (Decimal(received or "0") - Decimal(refunded or "0"))
        values["usdt_net"] = {"value": str(net), "source": None}
    else:
        values["usdt_net"] = {"value": None, "source": None}
    return state, values


def _customer_rank_entries(
    session: Session, rows: list[dict], reports: dict[int, dict],
) -> dict[int, dict]:
    """Tổng từng khách theo các phát sinh trong năm (không cộng số dư)."""
    customers = session.scalars(select(Customer).order_by(Customer.name, Customer.id)).all()
    source_ids = [row["source"].id for row in rows if row.get("source")]
    links = session.scalars(select(SheetReportCustomerLink).where(
        SheetReportCustomerLink.source_id.in_(source_ids), SheetReportCustomerLink.active.is_(True))).all()
    links_by_source: dict[int, dict[int, SheetReportCustomerLink]] = {}
    for link in links:
        links_by_source.setdefault(link.source_id, {})[link.customer_id] = link
    result: dict[int, dict] = {}
    for customer in customers:
        result[customer.id] = {
            "customer_id": customer.id, "name": customer.name,
            "months_with_value": {field: 0 for field in FLOW_FIELDS},
            "buckets": {field: [] for field in FLOW_FIELDS},
        }
    for index, row in enumerate(rows):
        if row["state_kind"] != "RESOLVED":
            continue
        report = reports[index]
        for customer in customers:
            link = links_by_source.get(row["source"].id, {}).get(customer.id)
            state, values = _customer_month_values(report, link)
            bucket = result[customer.id]
            for field in FLOW_FIELDS:
                value = values.get(field, {}).get("value")
                if value is not None:
                    bucket["buckets"][field].append(Decimal(value))
                    bucket["months_with_value"][field] += 1
    # Chỉ cộng các phát sinh (balance không tổng hợp qua các tháng — D-052).
    return {
        customer_id: {
            "customer_id": bucket["customer_id"], "name": bucket["name"],
            "months_with_value": bucket["months_with_value"],
            "totals": {
                field: (str(exact_decimal_sum(bucket["buckets"][field])) if bucket["buckets"][field] else None)
                for field in FLOW_FIELDS
            },
        }
        for customer_id, bucket in result.items()
    }


def build_customer_year_summary(
    session: Session, year: int, basis: str, customer_id: int, rank_by: str | None = None,
) -> dict:
    if rank_by is not None and rank_by not in FLOW_FIELDS:
        raise ValueError("Rank_by chỉ nhận một trong: " + ", ".join(FLOW_FIELDS) + ".")
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise LookupError("Không tìm thấy khách nội bộ.")
    rows = _month_rows(session, year, basis)
    months = []
    months_with_value = {field: 0 for field in FLOW_FIELDS}
    report_cache: dict[int, dict] = {}
    for index, row in enumerate(rows):
        period, state_kind = row["period"], row["state_kind"]
        active = row.get("active")
        entries: dict = {"period": period, "state": state_kind}
        if row.get("source"):
            entries["source_id"] = row["source"].id
            entries["source_name"] = row["source"].name
        if active:
            entries["active_source_id"] = active.id
        if row.get("last_attempt"):
            entries["last_attempt"] = row["last_attempt"]
        if state_kind != "RESOLVED":
            months.append({**entries, "link_state": None, "values": {}})
            continue
        snapshot_is_closure = row["closure"] is not None and row["snapshot"].id == row["closure"].snapshot_id
        closure = row["closure"]
        entry = {
            **entries, "snapshot_id": row["snapshot"].id, "read_at": row["snapshot"].read_at,
            "quality": row["snapshot"].quality,
            "closure_snapshot_id": closure.snapshot_id if snapshot_is_closure else None,
            "closed_at": closure.closed_at if snapshot_is_closure else None,
        }
        if snapshot_is_closure:
            entry["state"] = "CLOSED"
            active_snapshot = row.get("active_snapshot")
            if active_snapshot is not None and active_snapshot.id != row["snapshot"].id:
                entry["closure_note"] = "Tồn tại bản đọc mới hơn bản chốt; chế độ 'Bản chốt' vẫn dùng bản chốt làm nguồn chính thức."
        else:
            entry["state"] = "PROVISIONAL"
            if row.get("period_closed") is not None:
                entry["closure_note"] = "Kỳ đã có bản chốt; chế độ Hiện hành đang dùng bản đọc mới hơn; bản chốt vẫn là nguồn chính thức ở chế độ 'Bản chốt'."
        link = None
        if row.get("source"):
            link = session.scalar(select(SheetReportCustomerLink).where(
                SheetReportCustomerLink.source_id == row["source"].id,
                SheetReportCustomerLink.customer_id == customer_id,
                SheetReportCustomerLink.active.is_(True),
            ))
        report = enrich_sheets_report(deepcopy(row["snapshot"].report), period, row["source"].spreadsheet_id)
        report_cache[index] = report
        link_state, values = _customer_month_values(report, link)
        entry["link_state"] = link_state
        entry["values"] = values
        for field in FLOW_FIELDS:
            if values.get(field, {}).get("value") is not None:
                months_with_value[field] += 1
        months.append(entry)
    totals = {
        field: {"value": None, "months_with_value": months_with_value[field], "total_months": 12}
        for field in FLOW_FIELDS
    }
    for month in months:
        values = month["values"]
        for field in FLOW_FIELDS:
            value = values.get(field, {}).get("value")
            if value is not None:
                totals[field]["value"] = str(Decimal(value) if totals[field]["value"] is None else Decimal(totals[field]["value"]) + Decimal(value))
    opening_month = months[0] if months else None
    opening_value = (opening_month["values"].get("opening_balance") or {}).get("value") if opening_month else None
    opening = {"period": opening_month["period"], "value": None, "source": None}
    if opening_month and opening_value is not None:
        opening = {
            "period": opening_month["period"], "value": opening_value,
            "source": opening_month["values"]["opening_balance"].get("source"),
        }
    closing_month = next(
        (month for month in reversed(months) if month["values"].get("current_balance", {}).get("value") is not None),
        None,
    )
    closing = None
    if closing_month:
        closing_value = closing_month["values"]["current_balance"]
        closing = {"period": closing_month["period"], "value": closing_value["value"], "source": closing_value.get("source")}
    ranking = _customer_rank_entries(session, rows, report_cache)
    ranking_list = list(ranking.values())
    if rank_by:
        ranking_list.sort(
            key=lambda item: Decimal(item["totals"][rank_by]) if item["totals"][rank_by] is not None else Decimal(0),
            reverse=True,
        )
    return {
        "year": year, "basis": basis,
        "customer_id": customer_id, "customer_name": customer.name,
        "months": months,
        "months_with_value": months_with_value,
        "totals": totals,
        "opening_balance": opening,
        "closing_balance": closing,
        "ranking": ranking_list,
        "rank_by": rank_by,
    }
