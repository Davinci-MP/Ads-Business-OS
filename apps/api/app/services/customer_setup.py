"""Thiết lập khách nội bộ từ tab Sheets: đề xuất và xác nhận hàng loạt, không ghi tiền hay phân công."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Customer
from app.models.sheet_reports import SheetReportCustomerLink, SheetReportSource, SheetReportTabDismissal
from app.services import accounts as account_service
from app.services.sheet_report_store import latest_snapshot

ERROR_PROFILES = {"SOURCE_ERROR", "STRUCTURE_ERROR"}
ACTIONS = {"link", "create", "dismiss", "restore"}


class SetupError(Exception):
    pass


def _active_links(session: Session, source_id: int) -> dict[int, SheetReportCustomerLink]:
    return {item.sheet_id: item for item in session.scalars(select(SheetReportCustomerLink).where(
        SheetReportCustomerLink.source_id == source_id, SheetReportCustomerLink.active.is_(True)))}


def _dismissals(session: Session, source_id: int) -> dict[int, SheetReportTabDismissal]:
    return {item.sheet_id: item for item in session.scalars(select(SheetReportTabDismissal).where(
        SheetReportTabDismissal.source_id == source_id, SheetReportTabDismissal.active.is_(True)))}


def setup_proposals(session: Session, source: SheetReportSource) -> dict:
    snapshot = latest_snapshot(session, source.id)
    tabs = snapshot.report.get("customers", []) if snapshot else []
    links, dismissals = _active_links(session, source.id), _dismissals(session, source.id)
    customers = session.scalars(select(Customer).order_by(Customer.name, Customer.id)).all()
    linked_customers = {link.customer_id for link in links.values()}
    title_counts: dict[str, int] = {}
    for tab in tabs:
        key = str(tab.get("source_sheet", "")).strip().casefold()
        title_counts[key] = title_counts.get(key, 0) + 1
    rows = []
    for tab in tabs:
        sheet_id, title = tab.get("sheet_id"), str(tab.get("source_sheet", "")).strip()
        link, dismissal = links.get(sheet_id), dismissals.get(sheet_id)
        warnings = []
        if tab.get("profile_status") in ERROR_PROFILES:
            warnings.append("Tab lỗi nguồn/cấu trúc; chưa thể liên kết hoặc tạo hồ sơ.")
        if title_counts.get(title.casefold(), 0) > 1:
            warnings.append("Có nhiều tab cùng tên; chỉ định danh theo sheet ID.")
        if link and link.source_title != tab.get("source_sheet"):
            warnings.append("Tab đã đổi tên so với lúc liên kết; cần xác nhận lại ở màn hình liên kết.")
        exact = [c for c in customers if c.name.strip().casefold() == title.casefold()]
        if not link and exact:
            warnings.append("Đã có hồ sơ cùng tên; cần chọn liên kết rõ ràng, hệ thống không tự liên kết.")
        status = "DISMISSED" if dismissal else "LINKED" if link and link.source_title == tab.get("source_sheet") \
            else "LINK_REVIEW" if link else "UNLINKED"
        rows.append({
            "sheet_id": sheet_id, "spreadsheet_id": source.spreadsheet_id, "source_sheet": tab.get("source_sheet"),
            "suggested_name": title, "status": status, "profile_status": tab.get("profile_status"),
            "customer_id": link.customer_id if link else None, "warnings": warnings,
            "name_exists": bool(exact),
        })
    return {
        "source_id": source.id, "period": source.period, "snapshot_id": snapshot.id if snapshot else None,
        "rows": rows,
        "customers": [{"id": c.id, "name": c.name, "linked_in_source": c.id in linked_customers} for c in customers],
        "create_defaults": "Hồ sơ mới chỉ có tên. Các trường khác dùng mặc định hệ thống (phí 4%, đối soát SIMPLE_FEE); "
                           "không có tỷ giá, email hay ngân sách; không ghi có tiền.",
    }


def apply_setup(session: Session, source: SheetReportSource, items: list[dict], actor: str = "admin") -> dict:
    snapshot = latest_snapshot(session, source.id)
    tabs = {tab.get("sheet_id"): tab for tab in (snapshot.report.get("customers", []) if snapshot else [])}
    links, dismissals = _active_links(session, source.id), _dismissals(session, source.id)
    seen_tabs: set[int] = set()
    seen_customers: set[int] = set()
    plan = []
    for item in items:
        action, sheet_id = item.get("action"), item.get("sheet_id")
        if action not in ACTIONS:
            raise SetupError("Hành động không hợp lệ.")
        tab = tabs.get(sheet_id)
        if tab is None:
            raise SetupError(f"Không tìm thấy tab sheet ID {sheet_id} trong bản lưu hiện hành.")
        if sheet_id in seen_tabs:
            raise SetupError(f"Tab sheet ID {sheet_id} xuất hiện nhiều lần.")
        seen_tabs.add(sheet_id)
        if item.get("expected_source_sheet") != tab.get("source_sheet"):
            raise SetupError(f"Tên tab {tab.get('source_sheet')!r} đã thay đổi; tải lại danh sách trước khi xác nhận.")
        link, dismissal = links.get(sheet_id), dismissals.get(sheet_id)
        if action in {"link", "create"}:
            if tab.get("profile_status") in ERROR_PROFILES:
                raise SetupError(f"Tab {tab.get('source_sheet')!r} lỗi nguồn/cấu trúc.")
            if dismissal:
                raise SetupError(f"Tab {tab.get('source_sheet')!r} đang được bỏ qua; khôi phục trước.")
        if action == "link":
            customer_id = item.get("customer_id")
            if session.get(Customer, customer_id) is None:
                raise SetupError("Không tìm thấy hồ sơ khách để liên kết.")
            if link and link.customer_id != customer_id:
                raise SetupError(f"Tab {tab.get('source_sheet')!r} đã liên kết với hồ sơ khác.")
            if customer_id in seen_customers:
                raise SetupError("Một hồ sơ khách không được liên kết với hai tab trong cùng lần xác nhận.")
            seen_customers.add(customer_id)
        elif action == "create":
            name = str(item.get("name") or "").strip()
            if link:
                pass  # lần thử lại: liên kết đã có thì giữ nguyên, không tạo hồ sơ thứ hai
            elif not name:
                raise SetupError("Tên hồ sơ không được rỗng.")
        elif action == "dismiss" and link:
            raise SetupError(f"Tab {tab.get('source_sheet')!r} đang liên kết; không thể bỏ qua.")
        plan.append((action, item, tab, link, dismissal))
    results = []
    try:
        for action, item, tab, link, dismissal in plan:
            sheet_id, title = tab["sheet_id"], tab["source_sheet"]
            if action == "dismiss":
                if dismissal is None:
                    session.add(SheetReportTabDismissal(source_id=source.id, sheet_id=sheet_id, source_title=title, actor=actor))
                    account_service._audit(session, actor, "sheet_tab_dismissed", "sheet_tab",
                                           f"{source.spreadsheet_id}:{sheet_id}", {"source_id": source.id, "title": title})
                results.append({"sheet_id": sheet_id, "result": "unchanged" if dismissal else "dismissed"})
            elif action == "restore":
                if dismissal:
                    dismissal.active = False
                    account_service._audit(session, actor, "sheet_tab_restored", "sheet_tab",
                                           f"{source.spreadsheet_id}:{sheet_id}", {"source_id": source.id, "title": title})
                results.append({"sheet_id": sheet_id, "result": "restored" if dismissal else "unchanged"})
            elif link:
                results.append({"sheet_id": sheet_id, "customer_id": link.customer_id, "result": "unchanged"})
            else:
                if action == "create":
                    customer = account_service.create_customer(session, str(item["name"]).strip(), actor=actor)
                    customer_id, outcome = customer.id, "created_and_linked"
                else:
                    customer_id, outcome = item["customer_id"], "linked"
                session.add(SheetReportCustomerLink(source_id=source.id, sheet_id=sheet_id, source_title=title,
                                                    customer_id=customer_id, active=True))
                account_service._audit(session, actor, "sheet_tab_linked", "sheet_tab",
                                       f"{source.spreadsheet_id}:{sheet_id}",
                                       {"source_id": source.id, "title": title, "customer_id": customer_id, "mode": outcome})
                session.flush()
                results.append({"sheet_id": sheet_id, "customer_id": customer_id, "result": outcome})
        session.commit()
    except (IntegrityError, account_service.AccountError) as exc:
        session.rollback()
        raise SetupError(f"Không thể ghi: {exc.orig if isinstance(exc, IntegrityError) else exc}") from exc
    return {"results": results}
