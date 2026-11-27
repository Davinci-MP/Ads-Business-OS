"""Tests cho SMIT Synced Ad Accounts, Customer Assignment (1-Click & Bulk) và 4 SMIT Load Modes."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.models.customer import Customer
from app.models.via import SyncedAdAccount, SyncedBM, ViaProfile
from app.services.via_manager import (
    assign_ad_account_customer,
    bulk_assign_ad_accounts_customer,
    get_ads_check_explorer_data,
)


from app.models.extension_remote import CampaignDraft, RemoteViaCommand


@pytest.fixture(autouse=True)
def clean_smit_tables(db: Session):
    db.query(RemoteViaCommand).delete()
    db.query(CampaignDraft).delete()
    db.query(SyncedAdAccount).delete()
    db.query(SyncedBM).delete()
    db.query(ViaProfile).delete()
    db.query(Customer).delete()
    db.commit()
    yield
    db.query(RemoteViaCommand).delete()
    db.query(CampaignDraft).delete()
    db.query(SyncedAdAccount).delete()
    db.query(SyncedBM).delete()
    db.query(ViaProfile).delete()
    db.query(Customer).delete()
    db.commit()


@pytest.fixture
def test_data(db: Session):
    # Tạo 2 khách hàng
    cust1 = Customer(name="Khách Hàng Alpha", telegram_chat_id="111222")
    cust2 = Customer(name="Khách Hàng Beta", telegram_chat_id="333444")
    db.add_all([cust1, cust2])
    db.flush()

    # Tạo 2 VIA
    via1 = ViaProfile(
        uid="10001",
        profile_name="VIA-01",
        profile_dir="profiles/via_10001",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
        encrypted_credentials="enc_creds_1",
    )
    via2 = ViaProfile(
        uid="10002",
        profile_name="VIA-02",
        profile_dir="profiles/via_10002",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
        encrypted_credentials="enc_creds_2",
    )
    db.add_all([via1, via2])
    db.flush()

    # Tạo 2 BM
    bm1 = SyncedBM(bm_id="bm_9001", via_profile_id=via1.id, name="BM Alpha Agency")
    bm2 = SyncedBM(bm_id="bm_9002", via_profile_id=via2.id, name="BM Beta Holding")
    db.add_all([bm1, bm2])
    db.flush()

    # Tạo các TKQC với trạng thái và thuộc tính khác nhau
    # Acc 1: LIVE, BM 9001, VIA 1, có thẻ, chưa gán khách
    acc1 = SyncedAdAccount(
        via_profile_id=via1.id,
        bm_id="bm_9001",
        account_type="BM",
        act_id="101",
        name="TK Alpha 1",
        status_dot="LIVE",
        account_status=1,
        balance=0.0,
        threshold=50.0,
        ad_trust_dsl=250.0,
        total_spend=1200.0,
        currency="USD",
        payment_card_brand="VISA",
        payment_card_last4="1111",
        customer_id=None,
    )
    # Acc 2: DIE / DISABLED, BM 9001, VIA 1, đã gán cust1
    acc2 = SyncedAdAccount(
        via_profile_id=via1.id,
        bm_id="bm_9001",
        account_type="BM",
        act_id="102",
        name="TK Alpha 2 Disabled",
        status_dot="DIE",
        account_status=2,
        balance=15.0,
        threshold=25.0,
        ad_trust_dsl=50.0,
        total_spend=500.0,
        currency="USD",
        payment_card_brand="MASTERCARD",
        payment_card_last4="2222",
        customer_id=cust1.id,
    )
    # Acc 3: UNSETTLED / WARNING / NỢ, BM 9002, VIA 2, chưa gán khách
    acc3 = SyncedAdAccount(
        via_profile_id=via2.id,
        bm_id="bm_9002",
        account_type="BM",
        act_id="103",
        name="TK Beta 1 Debt",
        status_dot="WARNING",
        account_status=3,
        balance=120.0,
        threshold=100.0,
        ad_trust_dsl=500.0,
        total_spend=3400.0,
        currency="USD",
        payment_card_brand=None,
        payment_card_last4=None,
        customer_id=None,
    )
    # Acc 4: PERSONAL, VIA 2, LIVE, chưa gán khách
    acc4 = SyncedAdAccount(
        via_profile_id=via2.id,
        bm_id=None,
        account_type="PERSONAL",
        act_id="104",
        name="TK Cá Nhân VIA 2",
        status_dot="LIVE",
        account_status=1,
        balance=0.0,
        threshold=20.0,
        ad_trust_dsl=50.0,
        total_spend=150.0,
        currency="VND",
        payment_card_brand="VISA",
        payment_card_last4="4444",
        customer_id=None,
    )

    db.add_all([acc1, acc2, acc3, acc4])
    db.commit()

    return {
        "cust1": cust1,
        "cust2": cust2,
        "via1": via1,
        "via2": via2,
        "bm1": bm1,
        "bm2": bm2,
        "acc1": acc1,
        "acc2": acc2,
        "acc3": acc3,
        "acc4": acc4,
    }


def test_list_synced_accounts_status_and_filters(db: Session, test_data):
    """Kiểm tra liệt kê tài khoản với các bộ lọc trạng thái (ACTIVE, DISABLED, UNSETTLED), bm_id và account_ids."""
    # 1. Lọc ACTIVE
    res_active = get_ads_check_explorer_data(session=db, tab="accounts", status="ACTIVE")
    act_ids_active = [item["act_id"] for item in res_active["items"]]
    assert "101" in act_ids_active
    assert "104" in act_ids_active
    assert "102" not in act_ids_active

    # 2. Lọc DISABLED / DIE
    res_disabled = get_ads_check_explorer_data(session=db, tab="accounts", status="DISABLED")
    act_ids_disabled = [item["act_id"] for item in res_disabled["items"]]
    assert act_ids_disabled == ["102"]

    # 3. Lọc UNSETTLED / NỢ
    res_debt = get_ads_check_explorer_data(session=db, tab="accounts", status="UNSETTLED")
    act_ids_debt = [item["act_id"] for item in res_debt["items"]]
    assert "103" in act_ids_debt
    assert "101" not in act_ids_debt

    # 4. Lọc theo BM ID
    res_bm = get_ads_check_explorer_data(session=db, tab="accounts", bm_id="bm_9001")
    act_ids_bm = [item["act_id"] for item in res_bm["items"]]
    assert set(act_ids_bm) == {"101", "102"}

    # 5. Lọc theo danh sách account_ids cụ thể
    res_ids = get_ads_check_explorer_data(session=db, tab="accounts", account_ids=["102", "103"])
    act_ids_filtered = [item["act_id"] for item in res_ids["items"]]
    assert set(act_ids_filtered) == {"102", "103"}

    # 6. Lọc phân công (ASSIGNED vs UNASSIGNED)
    res_assigned = get_ads_check_explorer_data(session=db, tab="accounts", assignment_status="ASSIGNED")
    assert [i["act_id"] for i in res_assigned["items"]] == ["102"]

    res_unassigned = get_ads_check_explorer_data(session=db, tab="accounts", assignment_status="UNASSIGNED")
    assert "101" in [i["act_id"] for i in res_unassigned["items"]]
    assert "103" in [i["act_id"] for i in res_unassigned["items"]]
    assert "102" not in [i["act_id"] for i in res_unassigned["items"]]


def test_assign_single_customer_persists(db: Session, test_data):
    """Kiểm tra gán 1 tài khoản cho khách hàng và xác minh liên kết tồn tại bền vững trong DB."""
    cust2 = test_data["cust2"]
    res = assign_ad_account_customer(session=db, act_id="101", customer_id=cust2.id)

    assert res["customer_id"] == cust2.id
    assert res["customer_name"] == cust2.name
    assert res["is_assigned"] is True

    # Truy vấn lại trực tiếp từ DB
    db_acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "101"))
    assert db_acc is not None
    assert db_acc.customer_id == cust2.id

    # Hủy gán (customer_id = None)
    res_unassign = assign_ad_account_customer(session=db, act_id="101", customer_id=None)
    assert res_unassign["customer_id"] is None
    assert res_unassign["is_assigned"] is False


def test_bulk_assign_customer(db: Session, test_data):
    """Kiểm tra gán hàng loạt tài khoản quảng cáo cho khách hàng."""
    cust2 = test_data["cust2"]
    res = bulk_assign_ad_accounts_customer(
        session=db,
        account_ids=["101", "103", "104"],
        customer_id=cust2.id,
    )

    assert res["success"] is True
    assert res["updated_count"] == 3
    assert res["customer_id"] == cust2.id

    # Kiểm tra tất cả 3 tài khoản trong DB đều có customer_id == cust2.id
    synced_items = db.scalars(
        select(SyncedAdAccount).where(SyncedAdAccount.act_id.in_(["101", "103", "104"]))
    ).all()
    for acc in synced_items:
        assert acc.customer_id == cust2.id


def test_smit_load_modes(db: Session, test_data):
    """Kiểm tra 4 chế độ tải SMIT (LOAD_ALL, LOAD_BY_ACT_IDS, LOAD_BY_BM_ID, LOAD_BY_VIA_ID)."""
    # Mode 1: LOAD_ALL
    mode_all = get_ads_check_explorer_data(session=db, tab="accounts", mode="LOAD_ALL")
    assert mode_all["mode"] == "LOAD_ALL"
    assert mode_all["total_count"] == 4

    # Mode 2: LOAD_BY_ACT_IDS
    mode_act_ids = get_ads_check_explorer_data(
        session=db,
        tab="accounts",
        mode="LOAD_BY_ACT_IDS",
        account_ids=["act_101", "act_104"],
    )
    assert mode_act_ids["mode"] == "LOAD_BY_ACT_IDS"
    assert set(i["act_id"] for i in mode_act_ids["items"]) == {"101", "104"}

    # Mode 3: LOAD_BY_BM_ID
    mode_bm = get_ads_check_explorer_data(
        session=db,
        tab="accounts",
        mode="LOAD_BY_BM_ID",
        bm_id="bm_9002",
    )
    assert mode_bm["mode"] == "LOAD_BY_BM_ID"
    assert [i["act_id"] for i in mode_bm["items"]] == ["103"]

    # Mode 4: LOAD_BY_VIA_ID
    via1 = test_data["via1"]
    mode_via = get_ads_check_explorer_data(
        session=db,
        tab="accounts",
        mode="LOAD_BY_VIA_ID",
        via_id=via1.id,
    )
    assert mode_via["mode"] == "LOAD_BY_VIA_ID"
    assert set(i["act_id"] for i in mode_via["items"]) == {"101", "102"}


def test_api_endpoints_assign_and_load_mode(db: Session, test_data):
    """Kiểm tra các endpoint REST API /vias/ads-check/assign-customer, bulk và load-mode."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    headers = {"X-Admin-Key": "test-admin"}

    cust1 = test_data["cust1"]

    # 1. POST /api/v1/vias/ads-check/assign-customer
    res = client.post(
        "/api/v1/vias/ads-check/assign-customer",
        headers=headers,
        json={"act_id": "104", "customer_id": cust1.id},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["account"]["customer_id"] == cust1.id

    # 2. POST /api/v1/vias/ads-check/bulk-assign-customer
    res_bulk = client.post(
        "/api/v1/vias/ads-check/bulk-assign-customer",
        headers=headers,
        json={"account_ids": ["101", "103"], "customer_id": cust1.id},
    )
    assert res_bulk.status_code == 200
    data_bulk = res_bulk.json()
    assert data_bulk["success"] is True
    assert data_bulk["updated_count"] == 2

    # 3. POST /api/v1/vias/ads-check/load-mode
    res_mode = client.post(
        "/api/v1/vias/ads-check/load-mode",
        headers=headers,
        json={"mode": "LOAD_BY_BM_ID", "bm_id": "bm_9001"},
    )
    assert res_mode.status_code == 200
    data_mode = res_mode.json()
    assert len(data_mode["items"]) == 2
    assert set(i["act_id"] for i in data_mode["items"]) == {"101", "102"}

    app.dependency_overrides.clear()


def test_extension_ingest_returns_full_assets_list(db: Session):
    """Kiểm tra POST /api/v1/vias/extension-ingest trả về đầy đủ accounts, bms, pages để Extension cập nhật."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    ingest_payload = {
        "fb_uid": "999888777666",
        "profile_name": "VIA Multi-Stage Test",
        "cookie": "c_user=999888777666; xs=testxs;",
        "access_token": "EAABtesttoken1234567890abcdef",
        "ad_accounts": [
            {
                "act_id": "555111",
                "name": "TKQC Đã Quét",
                "account_status": "LIVE",
                "currency": "USD",
                "amount_spent": "100.5",
                "balance": "25.0",
                "threshold": "50.0",
                "spend_cap": "200.0",
                "card_last4": "8888",
                "card_type": "VISA",
            }
        ],
        "business_managers": [
            {
                "bm_id": "bm_555",
                "name": "BM Test SMIT",
                "verification_status": "verified",
                "owned_ad_accounts": {
                    "data": [{"account_id": "555111", "name": "TKQC Sở Hữu"}]
                },
                "client_ad_accounts": [
                    {
                        "account_id": "555222",
                        "name": "TKQC Đối Tác Chia Sẻ",
                        "account_status": 1,
                        "currency": "USD",
                        "balance": "30.0",
                    }
                ],
            }
        ],
        "fanpages": [
            {
                "page_id": "page_555",
                "name": "Fanpage Test SMIT",
                "fan_count": 1200,
            }
        ],
    }

    res = client.post("/api/v1/vias/extension-ingest", json=ingest_payload)
    assert res.status_code == 200
    data = res.json()

    assert data["success"] is True
    assert "accounts" in data
    assert "bms" in data
    assert "pages" in data

    assert len(data["accounts"]) >= 2
    assert any(a["act_id"] == "555111" and a["card_last4"] == "8888" for a in data["accounts"])
    assert any(a["act_id"] == "555222" and a["bm_id"] == "bm_555" for a in data["accounts"])

    owned = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "555111"))
    shared = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "555222"))
    assert owned is not None and owned.bm_id == "bm_555"
    assert shared is not None and shared.bm_id == "bm_555"

    assert len(data["bms"]) >= 1
    assert any(b["bm_id"] == "bm_555" for b in data["bms"])

    assert len(data["pages"]) >= 1
    assert any(p["page_id"] == "page_555" for p in data["pages"])

    app.dependency_overrides.clear()


def test_extension_ingest_flexible_keys_and_status_normalization(db: Session):
    """Kiểm tra POST /api/v1/vias/extension-ingest chấp nhận flexible key names (c_user, accounts, bms, pages, tokens, cookies)
    và chuẩn hóa chính xác account_status số (1=LIVE, 2=DIE, 3/7=WARNING) & account_type (BM nếu có bm_id/business/is_agency)."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    flexible_payload = {
        "c_user": "88812345",
        "user_name": "VIA Flexible Keys Test",
        "cookies": "c_user=88812345; xs=testflex;",
        "token": "EAABtestflexibletoken1234567890",
        "accounts": [
            {
                "id": "act_88801",
                "name": "TK 1 Live Personal",
                "account_status": 1,
                "amount_spent": "150.0",
                "card_last4": "1234",
                "card_type": "VISA",
                "currency": "USD",
            },
            {
                "id": "act_88802",
                "name": "TK 2 Die Personal",
                "account_status": 2,
                "card_last4": "5678",
                "currency": "USD",
            },
            {
                "id": "act_88803",
                "name": "TK 3 Debt BM",
                "account_status": 3,
                "business_id": "bm_777",
                "balance": "45.0",
                "card_last4": "9999",
                "currency": "VND",
            },
            {
                "id": "act_88804",
                "name": "TK 4 In Review BM",
                "account_status": 7,
                "is_agency": True,
                "card_last4": "0000",
                "currency": "USD",
            },
        ],
        "bms": [
            {"bm_id": "bm_777", "name": "BM Flex 777"}
        ],
        "pages": [
            {"page_id": "page_777", "name": "Page Flex 777", "likes_count": 500}
        ],
    }

    res = client.post("/api/v1/vias/extension-ingest", json=flexible_payload)
    assert res.status_code == 200
    data = res.json()

    assert data["success"] is True
    assert data["fb_uid"] == "88812345"
    assert len(data["accounts"]) == 4

    # Kiểm tra trong DB
    via = db.scalar(select(ViaProfile).where(ViaProfile.uid == "88812345"))
    assert via is not None

    acc1 = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "88801"))
    assert acc1.account_status == 1
    assert acc1.status_dot == "LIVE"
    assert acc1.account_type == "PERSONAL"
    assert acc1.payment_card_last4 == "1234"

    acc2 = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "88802"))
    assert acc2.account_status == 2
    assert acc2.status_dot == "DIE"
    assert acc2.account_type == "PERSONAL"

    acc3 = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "88803"))
    assert acc3.account_status == 3
    assert acc3.status_dot == "WARNING"
    assert acc3.account_type == "BM"
    assert acc3.bm_id == "bm_777"

    acc4 = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "88804"))
    assert acc4.account_status == 7
    assert acc4.status_dot == "WARNING"
    assert acc4.account_type == "BM"

    # Kiểm tra explorer filter với account_type & status & currency
    res_pers = client.get("/api/v1/vias/ads-check?tab=accounts&account_type=PERSONAL")
    assert res_pers.status_code == 200
    items_pers = res_pers.json()["items"]
    assert all(i["account_type"] == "PERSONAL" for i in items_pers)

    res_bm = client.get("/api/v1/vias/ads-check?tab=accounts&account_type=BUSINESS")
    assert res_bm.status_code == 200
    items_bm = res_bm.json()["items"]
    assert all(i["account_type"] == "BM" for i in items_bm)

    res_live = client.get("/api/v1/vias/ads-check?tab=accounts&status=ACTIVE")
    assert res_live.status_code == 200
    items_live = res_live.json()["items"]
    assert all(i["status_dot"] == "LIVE" for i in items_live)

    res_die = client.get("/api/v1/vias/ads-check?tab=accounts&status=DISABLED")
    assert res_die.status_code == 200
    items_die = res_die.json()["items"]
    assert all(i["status_dot"] == "DIE" for i in items_die)

    res_curr_vnd = client.get("/api/v1/vias/ads-check?tab=accounts&currency=VND")
    assert res_curr_vnd.status_code == 200
    items_vnd = res_curr_vnd.json()["items"]
    assert all(i["currency"] == "VND" for i in items_vnd)

    res_search_card = client.get("/api/v1/vias/ads-check?tab=accounts&search=9999")
    assert res_search_card.status_code == 200
    items_sc = res_search_card.json()["items"]
    assert len(items_sc) == 1
    assert items_sc[0]["act_id"] == "88803"

    app.dependency_overrides.clear()


def test_multi_bm_discovery_preserves_40_bms_without_truncation(db: Session):
    """Kiểm tra VIA có 40 BMs: Khi đồng bộ tiếp theo chỉ trả về 11 BMs, toàn bộ 40 BMs vẫn được bảo tồn trọn vẹn."""
    via = ViaProfile(
        uid="10040",
        profile_name="VIA-40-BMs",
        profile_dir="profiles/via_10040",
        user_agent="Mozilla/5.0 Chrome/133.0.0.0",
        encrypted_credentials="enc_creds_40",
    )
    db.add(via)
    db.flush()

    # Tạo trước 40 BMs trong Database
    initial_bms = [
        SyncedBM(
            via_profile_id=via.id,
            bm_id=f"BM_MULTI_{i:02d}",
            name=f"Holding BM #{i:02d}",
            status="ACTIVE",
            ad_account_count=2,
        )
        for i in range(1, 41)
    ]
    db.add_all(initial_bms)
    db.commit()

    total_bms_before = db.scalar(select(func.count(SyncedBM.id)).where(SyncedBM.via_profile_id == via.id))
    assert total_bms_before == 40

    # Giả lập đồng bộ mới (ví dụ do Graph API phân trang ban đầu hoặc subquery cũ chỉ trả về 11 BMs)
    partial_11_bms = [
        {"bm_id": f"BM_MULTI_{i:02d}", "name": f"Holding BM #{i:02d} (Updated)", "status": "ACTIVE"}
        for i in range(1, 12)
    ]

    client = TestClient(app)
    app.dependency_overrides[get_db] = lambda: db

    # Gửi qua extension-ingest chỉ với 11 BMs
    resp = client.post(
        "/api/v1/vias/extension-ingest",
        json={
            "fb_uid": "10040",
            "profile_name": "VIA-40-BMs",
            "business_managers": partial_11_bms,
            "ad_accounts": [],
            "fanpages": [],
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    # Kiểm tra: 40 BMs trong DB tuyệt đối không bị cắt giảm về 11
    total_bms_after = db.scalar(select(func.count(SyncedBM.id)).where(SyncedBM.via_profile_id == via.id))
    assert total_bms_after == 40

    # Phản hồi từ server cũng phải trả về đầy đủ toàn bộ 40 BMs
    assert len(data.get("bms", [])) == 40

    app.dependency_overrides.clear()


def test_fetch_accounts_for_bm_service_and_load_by_bm_id(db: Session):
    """Kiểm tra chế độ 'Tải Theo ID BM' (LOAD_BY_BM_ID) với BM ID 439477786474451 không bị trả về 0 tài khoản."""
    via = ViaProfile(
        uid="10099",
        profile_name="VIA-BM-Scanner",
        profile_dir="profiles/via_10099",
        user_agent="Mozilla/5.0 Chrome/133.0.0.0",
        encrypted_credentials="enc_creds_99",
    )
    db.add(via)
    db.flush()

    target_bm_id = "439477786474451"

    client = TestClient(app)
    app.dependency_overrides[get_db] = lambda: db

    # Gọi API LOAD_BY_BM_ID (trong môi trường mock/test dev)
    resp = client.post(
        "/api/v1/vias/ads-check/load-mode",
        json={
            "mode": "LOAD_BY_BM_ID",
            "bm_id": target_bm_id,
            "via_id": via.id,
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    # Phải trả về danh sách tài khoản thuộc BM 439477786474451, không được bằng 0!
    items = data.get("items", [])
    assert len(items) > 0, "Không được trả về 0 TKQC cho Business Manager 439477786474451"
    assert all(item["bm_id"] == target_bm_id for item in items)
    assert all(item["account_type"] == "BM" for item in items)

    # SyncedBM trong DB phải được cập nhật ad_account_count
    bm_db = db.scalar(select(SyncedBM).where(SyncedBM.bm_id == target_bm_id))
    assert bm_db is not None
    assert bm_db.ad_account_count == len(items)

    # Kiểm tra truy vấn GET /ads-check với mode=LOAD_BY_BM_ID và bm_id
    get_res = client.get(f"/api/v1/vias/ads-check?mode=LOAD_BY_BM_ID&bm_id={target_bm_id}")
    assert get_res.status_code == 200
    get_items = get_res.json()["items"]
    assert len(get_items) == len(items)

    app.dependency_overrides.clear()


def test_concurrent_deep_bm_sweep_in_sync_assets(db: Session):
    """Kiểm tra sync_via_all_assets tự động quét sâu tài khoản quảng cáo của tất cả BMs và bảo toàn dữ liệu."""
    from app.services.via_manager import sync_via_all_assets

    via = ViaProfile(
        uid="10055",
        profile_name="VIA-Concurrency-Test",
        profile_dir="profiles/via_10055",
        user_agent="Mozilla/5.0 Chrome/133.0.0.0",
        encrypted_credentials="enc_creds_55",
    )
    db.add(via)
    db.flush()

    # Mock sync với nhiều BMs
    mock_payload = {
        "bms": [
            {"bm_id": "BM_TEST_01", "name": "BM Test 01", "ad_account_count": 3, "status": "ACTIVE"},
            {"bm_id": "BM_TEST_02", "name": "BM Test 02", "ad_account_count": 5, "status": "ACTIVE"},
            {"bm_id": "BM_TEST_03", "name": "BM Test 03", "ad_account_count": 2, "status": "ACTIVE"},
        ],
        "personal_accounts": [
            {"act_id": "999001", "name": "TK Cá Nhân 01", "account_status": 1, "balance": 100000.0, "total_spend": 500000.0, "currency": "VND"}
        ],
        "bm_accounts": [
            {"act_id": "999101", "bm_id": "BM_TEST_01", "name": "TK BM 01-1", "account_status": 1, "balance": 200000.0, "total_spend": 1000000.0, "currency": "VND"},
            {"act_id": "999102", "bm_id": "BM_TEST_01", "name": "TK BM 01-2", "account_status": 1, "balance": 0.0, "total_spend": 2000000.0, "currency": "VND"},
            {"act_id": "999201", "bm_id": "BM_TEST_02", "name": "TK BM 02-1", "account_status": 1, "balance": 500000.0, "total_spend": 3000000.0, "currency": "VND"},
        ],
        "pages": [],
    }

    result = sync_via_all_assets(session=db, via_id=via.id, mock_data=mock_payload, mock_mode=True)
    assert result["success"] is True
    assert result["bms_synced"] == 3
    assert result["ad_account_count"] == 10

    bms_in_db = db.scalars(select(SyncedBM).where(SyncedBM.via_profile_id == via.id)).all()
    assert len(bms_in_db) == 3

    accs_in_db = db.scalars(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id)).all()
    assert len(accs_in_db) == 4
    pers_accs = [a for a in accs_in_db if a.account_type == "PERSONAL"]
    bm_accs = [a for a in accs_in_db if a.account_type == "BM"]
    assert len(pers_accs) == 1
    assert len(bm_accs) == 3


def test_auto_provisioned_via_from_extension_ingest_has_active_token_and_populated_assets(db: Session):
    """Kiểm tra VIA tự động tạo từ Extension Ingest (chưa từng nhập thủ công) luôn có TRẠNG THÁI TOKEN = ACTIVE,
    lưu đầy đủ access_token (EAAG/EAAB), cookies và quét đầy đủ BMs + TKQC."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    new_uid = "100005100850747"
    # Đảm bảo UID chưa tồn tại trong DB
    existing = db.scalar(select(ViaProfile).where(ViaProfile.uid == new_uid))
    assert existing is None

    payload = {
        "c_user": new_uid,
        "profile_name": "Trần Văn Auto Ingest",
        "cookies": f"c_user={new_uid}; xs=2%3Alive_session_xs_hash%3A0%3A0; datr=datr_sample_hash;",
        "eaag_token": "EAAG_TEST_TOKEN_BUSINESS_MOCK_12345678",
        "eaab_token": "EAAB_TEST_TOKEN_ADS_MOCK_12345678",
        "business_managers": [
            {"bm_id": "439477786474451", "name": "BM Agency Pro", "verification_status": "verified", "ad_account_count": 5},
            {"bm_id": "555888999111222", "name": "BM Retail Store", "verification_status": "not_verified", "ad_account_count": 2},
        ],
        "ad_accounts": [
            {
                "act_id": "111222333",
                "name": "TKQC Số 1 Agency",
                "account_status": 1,
                "amount_spent": "5000000",
                "balance": "150000",
                "threshold": "20000000",
                "spend_cap": "0",
                "currency": "VND",
                "card_last4": "1234",
                "card_type": "VISA",
            },
            {
                "act_id": "444555666",
                "name": "TKQC Số 2 Retail",
                "account_status": 1,
                "amount_spent": "12000000",
                "balance": "0",
                "threshold": "50000000",
                "spend_cap": "50000000",
                "currency": "VND",
                "card_last4": "5678",
                "card_type": "MASTERCARD",
                "bm_id": "439477786474451",
            },
        ],
        "fanpages": [
            {"page_id": "page_999888", "name": "Fanpage Official Store", "fan_count": 5500}
        ],
    }

    resp = client.post("/api/v1/vias/extension-ingest", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    assert data["token_status"] == "ACTIVE"
    assert data["uid_live_status"] == "LIVE"
    assert len(data["bms"]) == 2
    assert len(data["accounts"]) == 2

    # Kiểm tra bản ghi trong Cơ sở Dữ liệu
    via_db = db.scalar(select(ViaProfile).where(ViaProfile.uid == new_uid))
    assert via_db is not None
    assert via_db.token_status == "ACTIVE"
    assert via_db.status == "LIVE"
    assert via_db.access_token is not None
    assert via_db.access_token.startswith("EAAG") or via_db.access_token.startswith("EAAB")
    assert f"c_user={new_uid}" in via_db.cookies
    assert via_db.ad_account_count >= 2
    assert via_db.bm_count >= 2
    assert via_db.page_count >= 1

    # Cookie-only vẫn lưu phiên LIVE nhưng không được tự chế access token.
    cookie_uid = "100009999999999"
    cookie_only_payload = {
        "c_user": cookie_uid,
        "profile_name": "Cookie Only Provisioning",
        "cookies": f"c_user={cookie_uid}; xs=2%3Alive_cookie_xs%3A0%3A0; datr=datr_sample_hash;",
        "business_managers": [
            {"bm_id": "bm_cookie_01", "name": "BM Cookie Auto", "verification_status": "verified"}
        ],
    }
    resp_cook = client.post("/api/v1/vias/extension-ingest", json=cookie_only_payload)
    assert resp_cook.status_code == 200
    data_cook = resp_cook.json()
    assert data_cook["success"] is True
    assert data_cook["token_status"] == "NONE"

    via_cook = db.scalar(select(ViaProfile).where(ViaProfile.uid == cookie_uid))
    assert via_cook is not None
    assert via_cook.token_status == "NONE"
    assert via_cook.status == "LIVE"
    assert not via_cook.access_token
    assert f"c_user={cookie_uid}" in via_cook.cookies
    assert via_cook.bm_count >= 1

    app.dependency_overrides.clear()


def test_extension_ingest_early_exit_on_invalid_or_missing_uid(db: Session):
    """Kiểm tra POST /api/v1/vias/extension-ingest xử lý an toàn khi c_user/uid không hợp lệ:
    Trả về ngay HTTP 200 success=False với message tiếng Việt rõ ràng, không làm treo Extension UI."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    invalid_payloads = [
        {},
        {"c_user": ""},
        {"fb_uid": "0"},
        {"uid": "undefined"},
        {"c_user": "null"},
        {"fb_uid": "none"},
    ]

    for p in invalid_payloads:
        resp = client.post("/api/v1/vias/extension-ingest", json=p)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["message"] == "Chưa chọn phiên Facebook hợp lệ"
        assert data["accounts"] == []
        assert data["bms"] == []

    app.dependency_overrides.clear()


def test_cross_via_bm_and_account_isolation(db: Session):
    """Kiểm tra tính cô lập nghiêm ngặt giữa các VIA (Strict Per-VIA Isolation):
    VIA A (40 BMs, 10 TKQC) và VIA B (2 BMs, 2 TKQC) không bao giờ bị nhiễm chéo (cross-contamination)."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    uid_a = "100088402955133"
    bms_a = [{"bm_id": f"bm_a_{i}", "name": f"BM Alpha #{i}", "verification_status": "verified"} for i in range(40)]
    accs_a = [{"act_id": f"act_a_{i}", "name": f"TKQC Alpha #{i}", "amount_spent": "1000000", "currency": "VND"} for i in range(10)]

    payload_a = {
        "c_user": uid_a,
        "profile_name": "VIA Alpha Holding (40 BMs)",
        "cookies": f"c_user={uid_a}; xs=2%3Alive_cookie_xs_alpha%3A0%3A0;",
        "access_token": "EAAG_TOKEN_ALPHA_SAMPLE_1234567890",
        "business_managers": bms_a,
        "ad_accounts": accs_a,
    }

    resp_a = client.post("/api/v1/vias/extension-ingest", json=payload_a)
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["success"] is True
    assert len(data_a["bms"]) == 40
    assert len(data_a["accounts"]) == 10

    # Bây giờ ingest VIA B với chỉ 2 BMs và 2 TKQC
    uid_b = "100005100850747"
    bms_b = [
        {"bm_id": "bm_b_01", "name": "BM Beta Single 01", "verification_status": "not_verified"},
        {"bm_id": "bm_b_02", "name": "BM Beta Single 02", "verification_status": "not_verified"},
    ]
    accs_b = [
        {"act_id": "act_b_01", "name": "TKQC Beta 01", "amount_spent": "50000", "currency": "VND"},
        {"act_id": "act_b_02", "name": "TKQC Beta 02", "amount_spent": "75000", "currency": "VND"},
    ]

    payload_b = {
        "c_user": uid_b,
        "profile_name": "VIA Beta Small (2 BMs)",
        "cookies": f"c_user={uid_b}; xs=2%3Alive_cookie_xs_beta%3A0%3A0;",
        "access_token": "EAAB_TOKEN_BETA_SAMPLE_9876543210",
        "business_managers": bms_b,
        "ad_accounts": accs_b,
    }

    resp_b = client.post("/api/v1/vias/extension-ingest", json=payload_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["success"] is True

    # QUAN TRỌNG: VIA B không bị rò rỉ 40 BMs của VIA A
    assert len(data_b["bms"]) == 2
    assert len(data_b["accounts"]) == 2
    b_bm_ids = {b["bm_id"] for b in data_b["bms"]}
    assert b_bm_ids == {"bm_b_01", "bm_b_02"}

    # Kiểm tra trong DB:
    via_a_db = db.scalar(select(ViaProfile).where(ViaProfile.uid == uid_a))
    via_b_db = db.scalar(select(ViaProfile).where(ViaProfile.uid == uid_b))

    bms_a_db = db.scalars(select(SyncedBM).where(SyncedBM.via_profile_id == via_a_db.id)).all()
    bms_b_db = db.scalars(select(SyncedBM).where(SyncedBM.via_profile_id == via_b_db.id)).all()

    assert len(bms_a_db) == 40
    assert len(bms_b_db) == 2

    app.dependency_overrides.clear()


def test_extension_ping_and_health(db: Session):
    """Kiểm tra lightweight unauthenticated ping cho extension tự động dò cổng."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    # Ping endpoint
    resp = client.get("/api/v1/vias/ping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["connected"] is True

    # Health endpoint
    h_resp = client.get("/health")
    assert h_resp.status_code == 200
    h_data = h_resp.json()
    assert h_data["status"] == "ok"
    assert h_data["connected"] is True

    app.dependency_overrides.clear()


def test_campaign_drafts_and_remote_commands(db: Session):
    """Kiểm tra API Campaign Drafts và hàng đợi Remote Via Commands."""
    from app.models.extension_remote import CampaignDraft, RemoteViaCommand

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    # 1. Tạo campaign draft thủ công
    draft_payload = {
        "draft_name": "Chiến Dịch Bán Lẻ Mùa Hè",
        "draft_code": "SUMMER-RETAIL-01",
        "objective": "OUTCOME_ENGAGEMENT",
        "daily_budget": 350000.0,
        "targeting_json": '{"countries": ["VN"], "age_min": 20}',
        "initial_status": "PAUSED",
    }
    create_resp = client.post("/api/v1/vias/campaign-drafts", json=draft_payload)
    assert create_resp.status_code == 200
    draft_data = create_resp.json()
    assert draft_data["success"] is True
    draft_id = draft_data["draft_id"]

    # 2. Hút bản nháp từ TKQC
    cap_resp = client.post(
        "/api/v1/vias/campaign-drafts/capture-from-act",
        json={
            "via_uid": "10009988",
            "act_id": "act_889977",
            "draft_name": "Bản Nháp Hút Từ TK 889977",
        },
    )
    assert cap_resp.status_code == 200
    assert cap_resp.json()["success"] is True

    # 3. Lấy danh sách drafts
    list_resp = client.get("/api/v1/vias/campaign-drafts")
    assert list_resp.status_code == 200
    drafts = list_resp.json()
    assert len(drafts) >= 2

    # 4. Tạo lệnh RemoteViaCommand trong DB
    cust = Customer(name="Anh Nam Khách VIP", telegram_username="nam_vip", telegram_chat_id="555666")
    db.add(cust)
    db.flush()

    cmd = RemoteViaCommand(
        via_uid="10009988",
        act_id="act_889977",
        customer_id=cust.id,
        draft_id=draft_id,
        draft_name="Chiến Dịch Bán Lẻ Mùa Hè",
        command_type="SET_CAMP_FROM_DRAFT",
        payload_json='{"name": "Camp Auto Test"}',
        status="PENDING",
    )
    db.add(cmd)
    db.commit()

    # 5. Extension poll pending command theo c_user
    poll_resp = client.get("/api/v1/vias/remote-commands/pending?c_user=10009988")
    assert poll_resp.status_code == 200
    pending_cmds = poll_resp.json()
    assert len(pending_cmds) >= 1
    target_cmd = next(c for c in pending_cmds if c["id"] == cmd.id)
    assert target_cmd["act_id"] == "act_889977"
    assert target_cmd["draft"]["draft_code"] == "SUMMER-RETAIL-01"

    # 6. Extension báo cáo hoàn thành
    comp_resp = client.post(
        f"/api/v1/vias/remote-commands/{cmd.id}/complete",
        json={
            "status": "COMPLETED",
            "result_json": '{"campaign_id": "cmp_live_123", "status": "ACTIVE"}',
        },
    )
    assert comp_resp.status_code == 200
    assert comp_resp.json()["status"] == "COMPLETED"

    # Verify trong DB
    db.refresh(cmd)
    assert cmd.status == "COMPLETED"
    assert cmd.completed_at is not None

    app.dependency_overrides.clear()


def test_customer_spend_summary_reconciliation(db: Session):
    """Kiểm tra báo cáo chi tiêu khách hàng tính đúng quy tắc 4% phí dịch vụ."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    # Tạo VIA mẫu
    via_spend = ViaProfile(
        uid="1000777888",
        profile_name="VIA-SPEND",
        profile_dir="profiles/via_1000777888",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
        encrypted_credentials="enc_spend_via",
        token_status="ACTIVE",
    )
    # Tạo khách hàng với mức phí mặc định (None -> 4%)
    cust_default = Customer(name="Khách Hàng Mặc Định 4%", fee_rate=None)
    # Tạo khách hàng với mức phí riêng 5.5%
    cust_custom = Customer(name="Khách Hàng Riêng 5.5%", fee_rate=5.5)
    db.add_all([via_spend, cust_default, cust_custom])
    db.flush()

    # Gán 2 TKQC cho cust_default (tổng spend = 1,000,000)
    acc1 = SyncedAdAccount(
        via_profile_id=via_spend.id,
        act_id="201",
        name="TK Default 1",
        amount_spent=600000.0,
        balance=50000.0,
        threshold_amount=100000.0,
        currency="VND",
        account_status=1,
        customer_id=cust_default.id,
    )
    acc2 = SyncedAdAccount(
        via_profile_id=via_spend.id,
        act_id="202",
        name="TK Default 2",
        amount_spent=400000.0,
        balance=0.0,
        threshold_amount=50000.0,
        currency="VND",
        account_status=1,
        customer_id=cust_default.id,
    )
    # Gán 1 TKQC cho cust_custom (spend = 2,000,000)
    acc3 = SyncedAdAccount(
        via_profile_id=via_spend.id,
        act_id="203",
        name="TK Custom 1",
        amount_spent=2000000.0,
        balance=0.0,
        threshold_amount=200000.0,
        currency="VND",
        account_status=1,
        customer_id=cust_custom.id,
    )
    db.add_all([acc1, acc2, acc3])
    db.commit()

    resp = client.get("/api/v1/vias/customer-spend-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # Kiểm tra cust_default: raw_spend = 1,000,000 | 4% fee = 40,000 | total_payable = 1,040,000
    cust1_rep = next(c for c in data["customers"] if c["customer_id"] == cust_default.id)
    assert cust1_rep["raw_spend"] == 1000000.0
    assert cust1_rep["fee_rate_percent"] == 4.0
    assert cust1_rep["fee_amount"] == 40000.0
    assert cust1_rep["total_payable"] == 1040000.0
    assert cust1_rep["account_count"] == 2

    # Kiểm tra cust_custom: raw_spend = 2,000,000 | 5.5% fee = 110,000 | total_payable = 2,110,000
    cust2_rep = next(c for c in data["customers"] if c["customer_id"] == cust_custom.id)
    assert cust2_rep["raw_spend"] == 2000000.0
    assert cust2_rep["fee_rate_percent"] == 5.5
    assert cust2_rep["fee_amount"] == 110000.0
    assert cust2_rep["total_payable"] == 2110000.0
    assert cust2_rep["account_count"] == 1

    # Grand totals
    gt = data["grand_totals"]
    assert gt["grand_raw_spend"] == 3000000.0
    assert gt["grand_fee_amount"] == 150000.0
    assert gt["grand_total_payable"] == 3150000.0

    app.dependency_overrides.clear()


def test_telegram_setcamp_customer_ownership_verification(db: Session):
    """Kiểm tra Telegram bot command parser và xác thực quyền sở hữu nghiêm ngặt."""
    from app.services.telegram_bot import TelegramBotAgent
    from app.models.extension_remote import CampaignDraft, RemoteViaCommand

    # 1. Tạo VIA, Customer và TKQC
    via = ViaProfile(
        uid="1000888999",
        profile_name="VIA-BOT-01",
        profile_dir="profiles/via_1000888999",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
        encrypted_credentials="enc_bot_via",
        token_status="ACTIVE",
    )
    cust = Customer(
        name="Khách Hàng Chính Chủ",
        telegram_username="chinh_chu_ads",
        telegram_chat_id="778899",
    )
    db.add_all([via, cust])
    db.flush()

    acc = SyncedAdAccount(
        via_profile_id=via.id,
        act_id="777888999",
        name="TKQC Khách VIP",
        customer_id=cust.id,
    )
    draft = CampaignDraft(
        draft_code="DRAFT-VIP-01",
        draft_name="Camp Chuyển Đổi VIP",
        daily_budget=500000.0,
    )
    db.add_all([acc, draft])
    db.commit()

    agent = TelegramBotAgent()
    agent.telegram.allowed_chat_ids = ["123456", "778899"]

    # TH1: Người dùng lạ gõ lệnh tự nhiên Pattern 1 -> BỊ TỪ CHỐI
    update_stranger = {
        "message": {
            "chat": {"id": 123456},
            "from": {"username": "ke_la_mat", "first_name": "Kẻ Lạ"},
            "text": "set ads tài khoản ID: 777888999 theo Camp Chuyển Đổi VIP",
        }
    }
    res1 = agent.process_update(db, update_stranger)
    assert res1 is not None
    assert res1["text"] == "⛔ Lỗi: Telegram của bạn chưa được liên kết với khách hàng nào trên hệ thống."

    # TH2: Chính chủ gửi lệnh tự nhiên Pattern 1 -> THÀNH CÔNG và tạo RemoteViaCommand
    update_owner_nat = {
        "message": {
            "chat": {"id": 778899},
            "from": {"username": "chinh_chu_ads", "first_name": "Chính Chủ"},
            "text": "set ads tài khoản ID: 777888999 theo Camp Chuyển Đổi VIP",
        }
    }
    res2 = agent.process_update(db, update_owner_nat)
    assert res2 is not None
    assert "Đã tiếp nhận lệnh Set Camp" in res2["text"]
    assert "act_777888999" in res2["text"]

    # TH3: Chính chủ gửi lệnh rút gọn Pattern 2: /setcamp <act_id> <draft> -> THÀNH CÔNG
    update_owner_slash = {
        "message": {
            "chat": {"id": 778899},
            "from": {"username": "chinh_chu_ads", "first_name": "Chính Chủ"},
            "text": "/setcamp 777888999 DRAFT-VIP-01",
        }
    }
    res3 = agent.process_update(db, update_owner_slash)
    assert res3 is not None
    assert "Đã tiếp nhận lệnh Set Camp" in res3["text"]

    # Kiểm tra trong bảng RemoteViaCommand có 2 lệnh PENDING được tạo cho via 1000888999
    cmds = db.scalars(
        select(RemoteViaCommand).where(RemoteViaCommand.act_id == "act_777888999")
    ).all()
    assert len(cmds) == 2
    assert all(c.status == "PENDING" for c in cmds)
    assert all(c.via_uid == "1000888999" for c in cmds)
    assert all(c.payload["status"] == "PAUSED" for c in cmds)


