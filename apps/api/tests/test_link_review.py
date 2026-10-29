"""Link review — danh sách + đề xuất LIÊN KẾT CHỈ ĐỌC (không tự đổi liên kết).

- Tab có dữ liệu chưa liên kết → UNLINKED, không tự gán số.
- Tab liên kết hồ sơ có dấu hiệu thử nghiệm (tên chứa TEST) → TEST_PROFILE.
- Cùng sheet_id liên kết khách khác ở kỳ khác → LINKED_OTHER_ELSEWHERE.
- Snapshot lỗi cấu trúc → note rõ; tab lỗi không tự gán.
"""
from datetime import datetime, timezone

import alembic.command
import alembic.config
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app
from app.models.customer import Customer
from app.models.sheet_reports import SheetReportCustomerLink, SheetReportSnapshot
from app.services import sheet_report_store as store
from app.services.link_review import _is_test_profile


@pytest.fixture
def db(tmp_path):
    database = tmp_path / "link-review-test.db"
    cfg = alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    alembic.command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _source(db, period="2026-10", name="first"):
    from app.models.sheet_reports import SheetReportSource
    source = SheetReportSource(period=period, spreadsheet_id=name, name=name,
                               mapping_version=store.MAPPING_VERSION, mapping_config=store.MAPPING_CONFIG.copy(),
                               active=True, sync_enabled=True)
    db.add(source)
    db.commit()
    return source


def _report(value="10", sheet_id=7, title="SYNTHETIC"):
    return {
        "read_at": datetime.now(timezone.utc).isoformat(), "status": "PARTIAL", "mode": "live",
        "customers": [{"source_sheet": title, "sheet_id": sheet_id, "profile_status": "NEEDS_CONFIRMATION",
                       "tab_source_totals": {"current_balance": {"value": value}},
                       "opening_balance": {"value": value}}],
    }


def _save_snapshot(db, owner, report):
    db.add(SheetReportSnapshot(source_id=owner.id, read_at=datetime.now(timezone.utc),
                               mapping_version=owner.mapping_version, mapping_config=owner.mapping_config,
                               quality="PARTIAL", report=report))


def test_link_review_flags(db):
    customer = Customer(name="JOKER")
    test_profile = Customer(name="S17.1-TEST")
    db.add_all([customer, test_profile])
    db.commit()
    source = _source(db, "2026-10", "oct")
    other = _source(db, "2026-09", "sep")
    db.add_all([
        SheetReportCustomerLink(source_id=source.id, sheet_id=7, source_title="SYNTHETIC",
                                customer_id=test_profile.id, active=True),
        SheetReportCustomerLink(source_id=other.id, sheet_id=7, source_title="SYNTHETIC",
                                customer_id=customer.id, active=True),
    ])
    db.commit()

    combined = _report("10")
    error_tab = _report("0", sheet_id=8, title="ERR TAB")["customers"][0]
    error_tab["profile_status"] = "STRUCTURE_ERROR"
    combined["customers"].append(error_tab)
    _save_snapshot(db, source, combined)
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/api/v1/sheets/sources/link-review")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    rows = {item["source_id"]: item for item in payload["sources"]}
    assert rows[source.id]["closed"] is False
    by_sheet = {tab["sheet_id"]: tab for tab in rows[source.id]["tabs"]}
    unlinked = by_sheet[8]
    assert unlinked["link_state"] == "UNLINKED"
    assert any(flag == "UNLINKED" for flag in unlinked["flags"])
    linked_tab = by_sheet[7]
    assert linked_tab["linked_customers"][0]["customer_name"] == "S17.1-TEST"
    assert any(flag == "TEST_PROFILE" for flag in linked_tab["flags"])
    assert any(flag == "LINKED_OTHER_ELSEWHERE" for flag in linked_tab["flags"])
    assert any("customer-setup" in proposal or "thử nghiệm" in proposal for proposal in linked_tab["proposals"])


def test_link_review_test_hint(db):
    assert _is_test_profile("s17.1-test") is True
    assert _is_test_profile("JOKER") is False
    assert _is_test_profile("qc test profile 2") is True
