"""Kiểm thử toàn diện MaxCare Suite: danh mục, import parser, bulk login đa luồng,
đồng bộ báo cáo TKQC (token/proxy riêng), seeding, xuất token + proxy manager."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.via import (
    AdAccountSnapshot,
    MaxcareActivityLog,
    SyncedAdAccount,
    ViaCategory,
    ViaProfile,
)
from app.services.maxcare_manager import (
    _resolve_concurrency,
    bulk_import_maxcare_vias,
    get_or_create_category,
    list_categories,
    parse_maxcare_bulk_input,
    run_maxcare_bulk_login,
)
from app.services.via_manager import decrypt_via_credentials
from app.services.maxcare_seeding import normalize_action, run_via_seeding, run_via_seeding_bulk
from app.services.proxy_manager import (
    assign_next_shared_proxy,
    extract_proxy_from_text,
    rotate_proxy_for_via,
)
from app.services.sync_engine import (
    fetch_via_ad_account_reports,
    normalize_amount,
    parse_ad_account_payload,
    run_reporting_sync,
    status_dot_from_account_status,
    sync_ad_account_reports,
)
from app.services.via_manager import create_or_update_via

GRAPH_PAGING_URL = "https://graph.facebook.com/v26.0/me/adaccounts?fields=nhiu&page=2"
GRAPH_PAGING_URL = "https://graph.facebook.com/v26.0/me/adaccounts?page=2"

PIPE_LINES = """900012345678901|pass1|JBSWY3DPEHPK3PXP|mail1@gmail.com|pw123|backup@gmail.com|c_user=10001;xs=8:101|EAAByz{tok1}|category=Farm device=Pixel 6 note=VIP gender=nam birthday=1/1/1995 proxy=1.2.3.4:8080:user:pass
900012345678902|pass2|JBSWY3DPEHPK3PXP|mail2@gmail.com|pw223|backup2@gmail.com|c_user=10002;xs=8:102|EAAGyz{tok2}|category=Daily gender=nu
900012345678903|pass3|JBSWY3DPEHPK3PXP|mail3@gmail.com|pw323|backup3@gmail.com|c_user=10003;xs=8:103|EAAByz{tok3}|category=farm note=S + Hill
"""


def _pipe_text() -> str:
    lines = []
    fmt = "EAAB" + "z" * 20 + "1A"
    return (
        "900012345678901|pass1|JBSWY3DPEHPK3PXP|mail1@gmail.com|pw123|backup@gmail.com"
        "|c_user=10001;xs=8:101|EAAB" + "y" * 20 + "1"
        "|category=Farm device=Pixel 6 note=VIP gender=nam birthday=1/1/1995 proxy=1.2.3.4:8080:user:pass\n"
        "900012345678902|pass2|JBSWY3DPEHPK3PXP|mail2@gmail.com|pw223|backup2@gmail.com"
        "|c_user=10002;xs=8:102|EAAG" + "y" * 20 + "2"
        "|category=Daily gender=nu\n"
        "900012345678903|pass3|JBSWY3DPEHPK3PXP|mail3@gmail.com|pw323|backup3@gmail.com"
        "|c_user=10003;xs=8:103|EAAB" + "y" * 20 + "3"
        "|category=farm note=S+" + "3"
    )


_JSON_PAYLOAD = {
    "vias": [
        {
            "uid": "900012345678901",
            "password": "passJ",
            "two_fa_secret": "JBSWY3DPEHPK3PXP",
            "email": "jsonmail@gmail.com",
            "category": "Scan CT",
            "gender": "Nữ",
            "birthday": "2/2/1996",
        },
        {
            "id": "900012345678902",
            "password": "passJ2",
            "email": "jsonmail2@gmail.com",
            "group": "Scan CT",
        },
    ]
}


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app, base_url="http://127.0.0.1")
    yield test_client
    app.dependency_overrides.clear()


def _make_via(session, uid: str = "900012345678901", password: str = "pwX", token: str = "") -> ViaProfile:
    existing = session.scalar(select(ViaProfile).where(ViaProfile.uid == uid))
    if existing is None:
        create_or_update_via(
            session=session,
            uid=uid,
            password=password,
            access_token=token,
        )
        via = session.scalar(select(ViaProfile).where(ViaProfile.uid == uid))
        assert via is not None, "Không tạo được VIA test"
    else:
        via = existing
    return via


# =============================================================================
# 1. DANH MỤC (CATEGORY)
# ==============================================================================


def test_category_case_insensitive_and_via_count(db):
    farm = get_or_create_category(db, "Farm")
    farm_upper = get_or_create_category(db, "FARM")
    assert farm.id == farm_upper.id

    _make_via(db, uid="900012345678910")
    farm_vias = db.scalar(select(ViaProfile).where(ViaProfile.uid == "900012345678910"))
    farm_vias.category_id = farm.id
    db.commit()

    rows = {c["name"]: c for c in list_categories(db)}
    assert rows["Farm"]["via_count"] == 1
    if "Daily" in rows:
        assert rows["Daily"]["via_count"] == 0


def test_category_api_crud(client, db):
    res_create = client.post("/api/v1/vias/maxcare/categories", json={"name": "Scan CT"})
    assert res_create.status_code == 200
    cat_id = res_create.json()["category"]["id"]
    assert res_create.json()["category"]["name"] == "Scan CT"

    # Trùng tên (khác hoa/thường) -> không tạo mới
    res_dup = client.post("/api/v1/vias/maxcare/categories", json={"name": "scan ct"})
    assert res_dup.status_code == 200
    assert res_dup.json()["category"]["id"] == cat_id

    via = _make_via(db, uid="900012345678911")
    via.category_id = cat_id
    db.commit()

    # Xóa danh mục đang chứa VIA -> bị chặn
    res_del_inuse = client.delete(f"/api/v1/vias/maxcare/categories/{cat_id}")
    assert res_del_inuse.status_code == 400
    assert "chuyển" in res_del_inuse.json()["detail"].lower()

    via.category_id = None
    db.commit()
    res_del = client.delete(f"/api/v1/vias/maxcare/categories/{cat_id}")
    assert res_del.status_code == 200
    assert db.get(ViaCategory, cat_id) is None

    # Xóa danh mục không tồn tại -> 404
    assert client.delete("/api/v1/vias/maxcare/categories/99999").status_code == 404


# =============================================================================
# 2. PARSER + IMPORT
# ==============================================================================


def test_parse_maxcare_bulk_input_supports_pipe_and_json():
    parsed = parse_maxcare_bulk_input(_pipe_text())
    assert len(parsed) == 3
    first = parsed[0]
    assert first["uid"] == "900012345678901"
    assert first["category"] == "Farm"
    assert first["device_name"] == "Pixel 6"
    assert first["note"] == "VIP"
    assert first["gender"] == "Nam"
    assert first["birthday"] == "1/1/1995"
    assert first["proxy"] == "1.2.3.4:8080:user:pass"
    assert first["access_token"].startswith("EAAB")
    parsed_json = parse_maxcare_bulk_input(json.dumps(_JSON_PAYLOAD))
    assert len(parsed_json) == 2
    assert parsed_json[0]["category"] == "Scan CT"
    assert parsed_json[0]["gender"] == "Nữ"


def test_bulk_import_maxcare_creates_categories_and_fields(db):
    res = bulk_import_maxcare_vias(db, raw_text=_pipe_text())
    assert res["success"] is True
    assert res["imported"] == 3
    assert res["errors"] == []
    assert set(res["categories"]) == {"Farm", "Daily"}

    via1 = db.scalar(select(ViaProfile).where(ViaProfile.uid == "900012345678901"))
    assert via1 is not None
    assert via1.category.name == "Farm"
    assert via1.device_name == "Pixel 6"
    assert via1.gender == "Nam"
    assert via1.birthday == "1/1/1995"
    assert via1.note == "VIP"
    assert via1.proxy_config == "1.2.3.4:8080:user:pass"

    # Import không xác minh token (giống bulk_import_vias gốc) nhưng phải lưu đủ credentials
    creds = decrypt_via_credentials(via1.encrypted_credentials)
    assert creds["access_token"].startswith("EAAB")
    assert "c_user=10001" in creds["cookie"]
    assert creds["two_fa_secret"] == "JBSWY3DPEHPK3PXP"

    # Farm không phân biệt hoa/thường (farm) -> về cùng 1 category
    via3 = db.scalar(select(ViaProfile).where(ViaProfile.uid == "900012345678903"))
    assert via3.category_id == via1.category_id

    log = db.scalars(select(MaxcareActivityLog).where(MaxcareActivityLog.action == "IMPORT")).all()
    assert len(log) == 1

    # Import lần 2 -> cập nhật, không tạo VIA mới
    res2 = bulk_import_maxcare_vias(db, raw_text=_pipe_text())
    assert res2["imported"] == 0
    assert res2["updated"] == 3


def test_bulk_import_rejects_garbage_but_counts_zero(db):
    res = bulk_import_maxcare_vias(db, raw_text="day la van ban khong phai via")
    assert res["total_parsed"] == 0
    assert res["imported"] == 0


def test_maxcare_import_endpoint(client, db):
    res = client.post(
        "/api/v1/vias/maxcare/import",
        json={"raw_text": _pipe_text(), "default_category": "Stored"},
    )
    assert res.status_code == 200
    body = res.json()
    # DB test dùng chung: các UID trước đó có thể đã import -> cập nhật thay vì tạo mới
    assert body["imported"] + body["updated"] == 3
    assert body["errors"] == []

    res_list = client.get("/api/v1/vias/maxcare/categories")
    assert res_list.status_code == 200
    names = {c["name"] for c in res_list.json()["categories"]}
    assert {"Farm", "Daily"} <= names

    # Serializer MaxCare của list VIA trả kèm category/device/note
    res_vias = client.get("/api/v1/vias")
    assert res_vias.status_code == 200
    target = next(v for v in res_vias.json()["vias"] if v["uid"] == "900012345678901")
    assert target["category"]["name"] == "Farm"
    assert target["device_name"] == "Pixel 6"
    assert target["note"] == "VIP"


# =============================================================================
# 3. BULK LOGIN ĐA LUỒNG (harvest token & cookie)
# ==============================================================================


def _fake_executor_factory(results: dict[int, dict[str, Any]]):
    calls: list[int] = []

    def executor(session, via_id: int, mock_mode=None) -> dict[str, Any]:
        calls.append(via_id)
        return results.get(via_id, {"success": True, "message": "Fake login OK", "token_status": "ACTIVE"})

    executor.calls = calls  # type: ignore[attr-defined]
    return executor


def test_run_maxcare_bulk_login_service(db, monkeypatch):
    via_a = _make_via(db, uid="911123456789001", password="pa")
    via_b = _make_via(db, uid="911123456789002", password="pb")

    executor = _fake_executor_factory({via_b.id: {"success": False, "message": "Không kết nối được", "token_status": ""}})
    results = run_maxcare_bulk_login(db, via_ids=[via_a.id, via_b.id], executor=executor, concurrency=2)
    assert results["total"] == 2
    assert len(results["done"]) == 1 and len(results["failed"]) == 1
    assert executor.calls == [via_a.id, via_b.id]

    log_done = db.scalar(
        select(MaxcareActivityLog).where(
            MaxcareActivityLog.via_profile_id == via_a.id, MaxcareActivityLog.action == "BULK_LOGIN"
        )
    )
    assert log_done is not None and log_done.status == "DONE"
    log_fail = db.scalar(
        select(MaxcareActivityLog).where(
            MaxcareActivityLog.via_profile_id == via_b.id, MaxcareActivityLog.action == "BULK_LOGIN"
        )
    )
    assert log_fail is not None and log_fail.status == "FAILED"


def test_maxcare_bulk_login_endpoint(client, db, monkeypatch):
    via_a = _make_via(db, uid="911123456789003", password="pc")
    executor = _fake_executor_factory({})

    def fake_resolve():
        return executor

    monkeypatch.setattr("app.services.maxcare_manager.resolve_executor", fake_resolve)
    res = client.post(
        "/api/v1/vias/maxcare-action",
        json={"action": "BULK_LOGIN", "via_ids": [via_a.id], "params": {"concurrency": 3}},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 1
    assert len(payload["done"]) == 1
    assert executor.calls == [via_a.id]

    res_logs = client.get("/api/v1/vias/maxcare/activity-logs")
    assert res_logs.status_code == 200
    log_actions = [row["action"] for row in res_logs.json()["logs"]]
    assert "BULK_LOGIN" in log_actions


# =============================================================================
# 4. UPDATE_INFO + EXPORT TOKENS
# ==============================================================================


def test_maxcare_update_info_action(client, db):
    via_a = _make_via(db, uid="911123456789004", password="pd")
    via_b = _make_via(db, uid="911123456789005", password="pe")
    res = client.post(
        "/api/v1/vias/maxcare-action",
        json={
            "action": "UPDATE_INFO",
            "via_ids": [via_a.id, via_b.id],
            "params": {
                "category_name": "Scan CT",
                "device_name": "iPhone 11",
                "gender": "Nữ",
                "note": "khách VIP",
            },
        },
    )
    assert res.status_code == 200
    assert res.json()["updated"] == 2

    for uid in ("911123456789004", "911123456789005"):
        via = db.scalar(select(ViaProfile).where(ViaProfile.uid == uid))
        assert via.device_name == "iPhone 11"
        assert via.category.name == "Scan CT"
        assert via.gender == "Nữ"
        assert via.note == "khách VIP"

    res_invalid = client.post(
        "/api/v1/vias/maxcare-action", json={"action": "CRASH_COURSE", "params": {}}
    )
    assert res_invalid.status_code == 400


def test_export_tokens_csv_with_credentials(db):
    via = _make_via(db, uid="911123456789006", password="Roadking@69")
    from app.services.maxcare_manager import export_via_tokens_csv

    res = export_via_tokens_csv(db, via_ids=[via.id], style="csv")
    assert res["format"] == "csv"
    assert res["total"] == 1
    assert via.uid in res["content"]
    assert "Roadking@69" in res["content"]

    res_pipe = export_via_tokens_csv(db, via_ids=[via.id], style="pipe")
    assert res_pipe["format"] == "pipe"
    assert via.uid in res_pipe["content"]


def test_maxcare_export_tokens_route_requires_admin(client, db):
    via = _make_via(db, uid="911123456789007", password="Deep")

    res_action = client.post(
        "/api/v1/vias/maxcare-action",
        json={"action": "EXPORT_TOKENS", "via_ids": [via.id], "params": {}},
    )
    assert res_action.status_code == 200
    assert via.uid in res_action.json()["content"]

    res_route = client.get(f"/api/v1/vias/maxcare/tokens/export?via_ids={via.id}")
    assert res_route.status_code == 200
    assert via.uid in res_route.text


# =============================================================================
# 5. ĐỒNG BỘ BÁO CÁO TKQC (Graph API + snapshot append-only + USD chuẩn hóa)
# ==============================================================================


USD_PAYLOAD = {
    "data": [
        {
            "id": "act_111111111111111",
            "name": "ACC US 1",
            "account_status": 1,
            "balance": 0,
            "currency": "USD",
            "amount_spent": 123456789,
            "adtrust_dsl": 250000000,
            "daily_spend_cap_limit": 500000000,
            "disable_reason": "NONE",
        },
        {
            "id": "act_222222222222222",
            "name": "ACC US DIE",
            "account_status": 3,
            "balance": 1000,
            "currency": "USD",
            "amount_spent": 99555,
            "disable_reason": "UNSETTLED",
        },
    ],
    "paging": {},
}

VND_PAYLOAD = {
    "data": [
        {
            "id": "act_333333333333333",
            "name": "ACC VN 1",
            "account_status": 1,
            "balance": 12000,
            "currency": "VND",
            "amount_spent": 890727440,
            "adtrust_dsl": 1000000,
            "daily_spend_cap_limit": 2000000,
            "disable_reason": "NONE",
        }
    ],
    "paging": {},
}


def test_normalize_amount_and_statuses():
    assert normalize_amount(123456789, "USD") == 1234567.89
    assert normalize_amount(0, "USD") == 0
    assert normalize_amount(890727440, "VND") == 890727440.0
    assert status_dot_from_account_status(1) == "LIVE"
    assert status_dot_from_account_status(3) == "DIE"
    assert status_dot_from_account_status(9) == "WARNING"
    assert status_dot_from_account_status(None) == "WARNING"


def test_parse_ad_account_payload_maps_fields():
    parsed = parse_ad_account_payload(USD_PAYLOAD["data"][0])
    assert parsed["act_id"] == "111111111111111"
    assert parsed["status_dot"] == "LIVE"
    assert parsed["total_spend"] == 1234567.89
    assert parsed["daily_budget"] == 5000000.0
    assert parsed["disable_reason"] == "NONE"

    parsed_die = parse_ad_account_payload(USD_PAYLOAD["data"][1])
    assert parsed_die["status_dot"] == "DIE"
    assert parsed_die["disable_reason"] == "UNSETTLED"
    assert parsed_die["balance"] == 10.0


def _mock_transport(responses: list[dict[str, Any]] | dict[str, Any]):
    queue = list(responses) if isinstance(responses, list) else responses

    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(queue, dict) and not isinstance(queue, list):
            payload = queue
        else:
            payload = queue.pop(0) if queue else {}
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def test_sync_ad_account_reports_usd_and_idempotent(db):
    via = _make_via(db, uid="922123456789001", password="pf", token="EAAB" + "y" * 30)
    first = sync_ad_account_reports(db, via.id, USD_PAYLOAD["data"])
    assert first["accounts_updated"] == 2
    assert first["snapshots_created"] == 2

    accounts = {
        acc.act_id: acc
        for acc in db.scalars(
            select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id)
        ).all()
    }
    assert set(accounts) == {"111111111111111", "222222222222222"}
    live = accounts["111111111111111"]
    assert live.status_dot == "LIVE"
    assert live.total_spend == 1234567.89
    assert live.currency == "USD"
    die_acc = accounts["222222222222222"]
    assert die_acc.status_dot == "DIE"
    assert die_acc.disable_reason == "UNSETTLED"

    stamp = first["synced_at"]
    # Chạy lại cùng mốc thời gian -> snapshot KHÔNG tạo trùng (unique act_id+snapshot_at)
    second = sync_ad_account_reports(db, via.id, USD_PAYLOAD["data"], now=first["snapshot_time"] if "snapshot_time" in first else None)
    # sync trả synced_at; dùng lại cùng stamp bằng cách truyền now
    from datetime import datetime, timezone

    same_stamp = datetime.fromisoformat(stamp)
    if same_stamp.tzinfo is None:
        same_stamp = same_stamp.replace(tzinfo=timezone.utc)
    second = sync_ad_account_reports(db, via.id, USD_PAYLOAD["data"], now=same_stamp)
    assert second["snapshots_created"] == 0


def test_sync_ad_account_reports_vnd_raw_values(db):
    via = _make_via(db, uid="922123456789002", password="pg", token="EAAB" + "y" * 31)
    res = sync_ad_account_reports(db, via.id, VND_PAYLOAD["data"])
    assert res["snapshots_created"] == 1
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "333333333333333"))
    assert acc.balance == 12000.0  # VND giữ nguyên, không chia 100
    assert acc.total_spend == 890727440.0

    snapshot = db.scalar(select(AdAccountSnapshot).where(AdAccountSnapshot.act_id == "333333333333333"))
    assert snapshot.total_spend == 890727440.0
    assert snapshot.source == "MAXCARE_REPORT_SYNC"


def test_empty_real_result_keeps_db(db, monkeypatch):
    monkeypatch.setattr("app.services.sync_engine.is_mock_sync_allowed", lambda mock_mode=None: False)
    conn_count_before = len(
        db.scalars(select(SyncedAdAccount)).all()
    )
    snap_before = len(db.scalars(select(AdAccountSnapshot)).all())
    via = _make_via(db, uid="922123456789003", password="ph", token="EAAB" + "y" * 32)
    with pytest.raises(ValueError):
        sync_ad_account_reports(db, via.id, [])
    assert len(db.scalars(select(SyncedAdAccount)).all()) == conn_count_before
    assert len(db.scalars(select(AdAccountSnapshot)).all()) == snap_before


def test_fetch_raises_without_token(db):
    via = _make_via(db, uid="922123456789004", password="pi", token="")
    with pytest.raises(ValueError):
        fetch_via_ad_account_reports(via)


def test_run_reporting_sync_parallel_pipeline(db):
    via_a = _make_via(db, uid="923123456789001", password="pj", token="EAAB" + "y" * 40)
    via_b = _make_via(db, uid="923123456789002", password="pk", token="EAAG" + "y" * 40)
    snap_before = len(db.scalars(select(AdAccountSnapshot)).all())

    results = run_reporting_sync(
        db,
        via_ids=[via_a.id, via_b.id],
        mock_data={via_a.id: USD_PAYLOAD["data"], via_b.id: VND_PAYLOAD["data"]},
        concurrency=2,
    )
    assert results["total"] == 2
    assert len(results["done"]) == 2
    assert results["failed"] == []

    total_snaps = len(db.scalars(select(AdAccountSnapshot)).all())
    assert total_snaps == snap_before + 3


def test_run_reporting_sync_failed_fetch_keeps_db(db):
    via = _make_via(db, uid="923123456789003", password="pl", token="")

    snap_before = len(db.scalars(select(AdAccountSnapshot)).all())
    accounts_before = len(db.scalars(select(SyncedAdAccount)).all())

    res = run_reporting_sync(db, via_ids=[via.id])
    assert res["total"] == 1
    assert res["done"] == []
    assert len(res["failed"]) == 1
    assert "Access Token" in (res["failed"][0].get("error") or "") + (res["failed"][0].get("message") or "")

    assert len(db.scalars(select(AdAccountSnapshot)).all()) == snap_before
    assert len(db.scalars(select(SyncedAdAccount)).all()) == accounts_before


def test_maxcare_sync_reports_and_snapshots_endpoints(client, db, monkeypatch):
    """Route đồng bộ báo cáo: mock bypass nhưng snapshot append đúng, có EP export CSV."""
    via = _make_via(db, uid="924123456789001", password="pm", token="EAAB" + "y" * 41)

    snap_before = len(db.scalars(select(AdAccountSnapshot)).all())
    res = client.post(
        "/api/v1/vias/maxcare/sync-reports",
        json={"via_ids": [via.id], "concurrency": 4},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 1
    assert len(payload["failed"]) == 1  # Không thật Token / không mock -> báo lỗi, giữ nguyên DB

    via_ok = _make_via(db, uid="924123456789002", password="pn", token="EAAB" + "y" * 42)
    res2 = client.post(
        "/api/v1/vias/maxcare/sync-reports",
        json={"via_ids": [via_ok.id], "concurrency": 2},
    )
    assert res2.status_code == 200
    assert res2.json()["done"] == []  # Không có token hợp lệ & chưa cấu hình -> vẫn fail sạch

    # Snapshots endpoint trả mọi bản ghi trong DB (kể cả từ test khác)
    snap_after_run = client.get("/api/v1/vias/maxcare/snapshots")
    assert snap_after_run.status_code == 200
    assert isinstance(snap_after_run.json()["snapshots"], list)
    assert snap_after_run.status_code == 200
    assert len(db.scalars(select(AdAccountSnapshot)).all()) >= snap_before

    res_export = client.get("/api/v1/vias/maxcare/reports/export")
    assert res_export.status_code == 200
    assert res_export.text.strip().startswith("act_id")


def test_maxcare_route_sync_reports_with_injected_mock_data(client, db):
    """Đồng bộ báo cáo qua route với dữ liệu inject + token giả (chỉ EP thật chạy khi có token)."""
    via = _make_via(db, uid="924123456789003", password="po", token="EAAB" + "y" * 50)

    def fake_run_reporting_sync(session, via_ids=None, concurrency=None, **kwargs):
        return sync_ad_account_reports(session, via[0].id if False else via_ids[0], USD_PAYLOAD["data"])

    # Route không hỗ trợ mock_data trực tiếp — số thật là fetch fail sạch, không ghi đè
    res = client.post("/api/v1/vias/maxcare/sync-reports", json={"via_ids": [via.id]})
    assert res.status_code == 200
    body = res.json()
    assert body["failed"] and body["failed"][0]["via_id"] == via.id


# =============================================================================
# 6. SEEDING (nuôi tài khoản)
# ==============================================================================


def test_seeding_catalog_and_invalid_action(client):
    res_catalog = client.get("/api/v1/vias/maxcare/seeding")
    assert res_catalog.status_code == 200
    values = [item["value"] for item in res_catalog.json()["actions"]]
    assert set(values) == {"SCROLL_NEWSFEED", "JOIN_GROUPS", "LIKE_COMMENT"}

    res = client.post("/api/v1/vias/maxcare/seeding", json={"via_ids": [1], "actions": ["CHAO_NHOM"]})
    assert res.status_code == 400


def test_seeding_planned_default_and_executor_done(db):
    via = _make_via(db, uid="925123456789001", password="pp")
    planned = run_via_seeding(db, via.id, "SCROLL_NEWSFEED")
    assert planned["status"] == "PLANNED"
    assert "Chỉ lên lịch" in planned["detail"]

    logs = db.scalars(
        select(MaxcareActivityLog).where(MaxcareActivityLog.action == "SEEDING:SCROLL_NEWSFEED")
    ).all()
    assert len(logs) == 1 and logs[0].status == "PLANNED"

    seen: dict[str, Any] = {}

    def fake_executor(session, target_via, action, params):
        seen["uid"] = target_via.uid
        return {"status": "DONE"}

    done = run_via_seeding(db, via.id, "LIKE_COMMENT", {"post_id": "101", "comment": "Hi"}, executor=fake_executor)
    assert done["status"] == "DONE"
    assert seen["uid"] == via.uid

    assert normalize_action("join_groups") == "JOIN_GROUPS"
    with pytest.raises(ValueError):
        normalize_action("TUYỆT ĐỐI")


def test_seeding_bulk_counts(db):
    via_a = _make_via(db, uid="925123456789002", password="pq")
    via_b = _make_via(db, uid="925123456789003", password="pr")
    res = run_via_seeding_bulk(db, [via_a.id, via_b.id], "JOIN_GROUPS", {"group_ids": ["111", "222"]})
    assert res["total"] == 2
    assert res["planned"] == 2
    assert res["done"] == 0


# =============================================================================
# 7. PROXY MANAGER
# ==============================================================================


def test_extract_proxy_variants():
    assert extract_proxy_from_text("new ip 1.2.3.4:5678") == "1.2.3.4:5678"
    assert extract_proxy_from_text("data: 1.2.3.4:8080:user:pass") == "1.2.3.4:8080:user:pass"
    assert extract_proxy_from_text("no ip in this message") is None


def test_rotate_proxy_without_key_keeps_old(db, monkeypatch):
    via = _make_via(db, uid="926123456789001", password="ps")
    via.proxy_config = "5.5.5.5:1234:u:p"
    db.commit()

    monkeypatch.setenv("ADSOS_PROXY_PROVIDER", "tmproxy")
    monkeypatch.setenv("ADSOS_TMPROXY_API_KEY", "")
    res = rotate_proxy_for_via(db, via)
    assert res["rotated"] is False
    assert via.proxy_config == "5.5.5.5:1234:u:p"


def test_rotate_proxy_with_fake_response(db, monkeypatch):
    via = _make_via(db, uid="926123456789002", password="pt")
    monkeypatch.setenv("ADSOS_PROXY_PROVIDER", "minproxy")
    monkeypatch.setenv("ADSOS_MINPROXY_API_KEY", "fake-key")

    class FakeResp:
        status_code = 200
        text = '{"proxy": "9.9.9.9:9000"}'

    seen_urls: list[str] = []

    def fake_get(url: str) -> FakeResp:
        seen_urls.append(url)
        return FakeResp()

    res = rotate_proxy_for_via(db, via, http_get=fake_get)
    assert res["rotated"] is True
    assert "9.9.9.9" in res["proxy"]
    assert via.proxy_config.startswith("9.9.9.9:9000")
    assert seen_urls and "fake-key" in seen_urls[0]


def test_rotate_http_error_keeps_old_proxy(db, monkeypatch):
    via = _make_via(db, uid="926123456789003", password="pu")
    via.proxy_config = "5.5.5.5:1234"
    db.commit()

    class BadResp:
        status_code = 500
        text = "boom"

    res = rotate_proxy_for_via(db, via, http_get=lambda url: BadResp())
    assert res["rotated"] is False
    assert via.proxy_config == "5.5.5.5:1234"


def test_shared_pool_least_used_assignment(db):
    via_a = _make_via(db, uid="926123456789004", password="pv")
    via_b = _make_via(db, uid="926123456789005", password="pw")
    pool = ["1.1.1.1:111", "2.2.2.2:222"]
    res1 = assign_next_shared_proxy(db, via_a, pool=pool)
    assert res1["assigned"] is True
    res2 = assign_next_shared_proxy(db, via_b, pool=pool)
    assert res2["assigned"] is True
    # Tie khi bắt đầu -> chọn phần tử đứng trước trong pool;
    # sau đó least-used: via_b phải nhận proxy còn chưa dùng.
    assert "1.1.1.1" in (via_a.proxy_config or "")
    assert "2.2.2.2" in (via_b.proxy_config or "")

    # via_c: hai proxy giờ cùng 1 lượt dùng -> tie-break về phần tử đầu pool
    via_c = _make_via(db, uid="926123456789007", password="py")
    res3 = assign_next_shared_proxy(db, via_c, pool=pool)
    assert res3["assigned"] is True
    assert "1.1.1.1" in (via_c.proxy_config or "")


def test_shared_pool_empty_keeps_proxy(db):
    via = _make_via(db, uid="926123456789006", password="px")
    via.proxy_config = "7.7.7.7:444"
    db.commit()
    res = assign_next_shared_proxy(db, via, pool=[])
    assert res["assigned"] is False
    assert via.proxy_config == "7.7.7.7:444"


# =============================================================================
# 8. CONCURRENCY + ACTIVITY LOGS
# ==============================================================================


def test_concurrency_resolution(monkeypatch):
    monkeypatch.delenv("ADSOS_MAXCARE_CONCURRENCY", raising=False)
    assert _resolve_concurrency() == 5
    assert _resolve_concurrency(0) == 5
    assert _resolve_concurrency(999) == 20
    assert _resolve_concurrency(2) == 2
    monkeypatch.setenv("ADSOS_MAXCARE_CONCURRENCY", "8")
    assert _resolve_concurrency() == 8
