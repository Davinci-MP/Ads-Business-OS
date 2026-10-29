"""Rà soát liên kết khách Sheets — CHỈ ĐỌC, không tự đổi/xoá liên kết.

Mục đích (theo chỉ đạo chủ dự án): dựng màn danh sách + đề xuất để người vận hành
XÁC NHẬN trước khi đụng liên kết. KHÔNG tựen gán/xoá/gộp hồ sơ; KHÔNG tự sửa
liên kết thật; mỗi dòng đề xuất là gợi ý để rà soát, không phải kết luận.

Phát hiện:
- Tab có dữ liệu nhưng chưa liên kết khách trong nguồn → UNLINKED.
- Tab đang liên kết hồ sơ có dấu hiệu thử nghiệm (tên chứa "TEST") → TEST_PROFILE.
- Cùng sheet_id đang liên kết KHÁC khách ở kỳ khác → LINKED_OTHER_ELSEWHERE
  (bàn giao/moved hoặc nhầm link — cần chủ dự án quyết định).
- Cùng tab liên kết ≥2 khách khác nhau trong cùng nguồn → MULTI_LINKED.
Hồ sơ mơ hồ giữa "thử nghiệm" và "vận hành" KHÔNG tự phán — chỉ gợi ý kèm câu hỏi.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.sheet_reports import (
    SheetReportClosure, SheetReportCustomerLink, SheetReportSnapshot, SheetReportSource,
)

_TEST_HINT_RE = re.compile(r"TEST", re.IGNORECASE)

FLAG_TEXTS = {
    "UNLINKED": "Tab có dữ liệu nhưng chưa liên kết khách nội bộ.",
    "TEST_PROFILE": "Tab liên kết hồ sơ có dấu hiệu thử nghiệm (tên chứa TEST) — cần quyết định giữ/đổi sang hồ sơ vận hành.",
    "LINKED_OTHER_ELSEWHERE": "Cùng tab đã liên kết khách KHÁC ở kỳ khác — bàn giao hoặc nhầm liên kết, cần xác nhận.",
    "MULTI_LINKED": "Cùng tab đang liên kết nhiều khách khác nhau trong cùng kỳ — xung đột phân bổ, cần rà soát.",
}


def _is_test_profile(name: str) -> bool:
    return bool(_TEST_HINT_RE.search(name or ""))


def build_link_review(session: Session) -> dict:
    sources = session.scalars(select(SheetReportSource).order_by(SheetReportSource.period, SheetReportSource.id)).all()
    customers = {customer.id: customer for customer in session.scalars(select(Customer))}
    links = session.scalars(select(SheetReportCustomerLink).where(SheetReportCustomerLink.active.is_(True))).all()
    links_by_sheet: dict[int, list[SheetReportCustomerLink]] = {}
    links_by_source_sheet: dict[tuple[int, int], list[SheetReportCustomerLink]] = {}
    for link in links:
        links_by_sheet.setdefault(link.sheet_id, []).append(link)
        links_by_source_sheet.setdefault((link.source_id, link.sheet_id), []).append(link)
    closures = {closure.source_id: closure for closure in session.scalars(select(SheetReportClosure))}
    snapshots = session.scalars(
        select(SheetReportSnapshot).order_by(SheetReportSnapshot.source_id, SheetReportSnapshot.read_at)
    ).all()
    latest_by_source: dict[int, SheetReportSnapshot] = {}
    for snapshot in snapshots:
        latest_by_source[snapshot.source_id] = snapshot

    source_rows = []
    for source in sources:
        closure = closures.get(source.id)
        snapshot = latest_by_source.get(source.id)
        tabs = []
        if snapshot is not None:
            for tab in snapshot.report.get("customers", []):
                sheet_id = tab.get("sheet_id")
                title = tab.get("source_sheet")
                if not isinstance(sheet_id, int):
                    continue
                link_rows = links_by_source_sheet.get((source.id, sheet_id), [])
                linked_customers = []
                seen_customer_ids = set()
                for link in link_rows:
                    if link.customer_id not in seen_customer_ids:
                        seen_customer_ids.add(link.customer_id)
                        customer = customers.get(link.customer_id)
                        linked_customers.append({
                            "customer_id": link.customer_id,
                            "customer_name": customer.name if customer else None,
                        })
                profile_status = tab.get("profile_status")
                flags: list[str] = []
                link_state = "LINKED"
                if not linked_customers:
                    link_state = "UNLINKED"
                    flags.append("UNLINKED")
                if len(seen_customer_ids) > 1:
                    flags.append("MULTI_LINKED")
                    link_state = "LINK_REVIEW"
                else:
                    linked_name = linked_customers[0]["customer_name"] or "" if linked_customers else ""
                    if _is_test_profile(linked_name):
                        flags.append("TEST_PROFILE")
                        link_state = "LINK_REVIEW" if link_state == "LINKED" else link_state
                if len(seen_customer_ids) == 1:
                    foreign = [
                        link.customer_id for link in links_by_sheet.get(sheet_id, [])
                        if link.source_id != source.id and link.customer_id != linked_customers[0]["customer_id"]
                    ]
                    if foreign:
                        flags.append("LINKED_OTHER_ELSEWHERE")
                flags = list(dict.fromkeys(flags))
                note = None
                if profile_status in {"SOURCE_ERROR", "STRUCTURE_ERROR"}:
                    note = "Tab lỗi dữ liệu/cấu trúc trong snapshot; kiểm tra bản đọc trước khi quyết."
                tabs.append({
                    "sheet_id": sheet_id,
                    "tab": title,
                    "profile_status": profile_status,
                    "link_state": link_state,
                    "linked_customers": linked_customers,
                    "flags": flags,
                    "note": note,
                    "proposals": [FLAG_TEXTS[flag] for flag in flags],
                })
        else:
            tabs = []
        source_rows.append({
            "source_id": source.id, "period": source.period, "name": source.name,
            "active": source.active,
            "closed": closure is not None,
            "closed_at": closure.closed_at.isoformat() if closure else None,
            "snapshot_id": snapshot.id if snapshot else None,
            "snapshot_read_at": snapshot.read_at if snapshot else None,
            "tabs": tabs,
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Danh sách chỉ đọc để rà soát; không tự đổi/xoá liên kết. Chỉ khi được xác nhận mới dùng luồng cấu hình khách (customer-setup) hiện có.",
        "sources": source_rows,
    }
