"""Kiểm thử S5 — Dashboard endpoints + quản lý ad account (D-032)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, delete, func, inspect as sa_inspect

from app.api.v1.dashboard import router
from app.connectors.meta import MetaAdsConnector
from app.main import app
from app.db import get_db
from app.models import AdAccount, AdAccountAssignment, AuditLog, Campaign, Customer, DriftRecord, SpendSnapshot
from app.services import accounts as accounts_service
from app.services.meta_sync import run_meta_sync


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clean_tables(db):
    yield
    db.rollback()
    db.execute(delete(DriftRecord))
    db.execute(delete(SpendSnapshot))
    db.execute(delete(Campaign))
    db.execute(delete(AdAccountAssignment))
    db.execute(delete(AuditLog))
    db.execute(delete(AdAccount))
    db.execute(delete(Customer))
    db.commit()


def mock_connector(**kwargs):
    return MetaAdsConnector(use_mock=True, **kwargs)


def seed(session, connector, extra_account=False):
    alpha = Customer(name="KH-S5-Alpha")
    beta = Customer(name="KH-S5-Beta")
    session.add_all([alpha, beta])
    session.flush()
    acc1 = AdAccount(
        meta_ad_account_id="act_mock_1", name="Acc 1",
        business_manager_id="bm_a", timezone_name="Asia/Ho_Chi_Minh",
    )
    session.add(acc1)
    session.flush()
    # một account chỉ phục vụ một khách tại một thời điểm (skill account-management)
    session.add(
        AdAccountAssignment(customer_id=alpha.id, ad_account_id=acc1.id, valid_from=utc(2026, 10, 1))
    )
    if extra_account:
        session.add(AdAccount(meta_ad_account_id="act_mock_9", name="Acc 9 rảnh", timezone_name="UTC"))
    connector.mock.rename_campaign("cmp_1001", f"{alpha.name} 1025")
    connector.mock.rename_campaign("cmp_1002", f"{beta.name} 2510")
    connector.mock.rename_campaign("cmp_1003", f"{alpha.name} 1102")
    connector.mock.rename_campaign("cmp_1004", f"{alpha.name} 1025 retired")
    session.commit()
    return alpha, beta, acc1


# --- cột purchase_cost đã migrate ---


def test_purchase_cost_column_exists(db):
    cols = {c["name"] for c in sa_inspect(db.bind).get_columns("ad_accounts")}
    assert "purchase_cost" in cols


def test_account_rows_do_not_claim_future_or_conflicting_assignments(db):
    from app.services.dashboard import account_rows

    alice = Customer(name="Alice")
    bob = Customer(name="Bob")
    account = AdAccount(meta_ad_account_id="act_history_test", name="a", timezone_name="UTC")
    db.add_all([alice, bob, account])
    db.flush()
    now = datetime.now(timezone.utc)
    db.add(AdAccountAssignment(customer_id=alice.id, ad_account_id=account.id,
                               valid_from=now + timedelta(days=1), valid_to=now + timedelta(days=2)))
    db.flush()
    row = account_rows(db)[0]
    assert row["customer_id"] is None
    assert row["assignment_status"] == "UNASSIGNED"
    db.add_all([
        AdAccountAssignment(customer_id=alice.id, ad_account_id=account.id,
                            valid_from=now - timedelta(days=2)),
        AdAccountAssignment(customer_id=bob.id, ad_account_id=account.id,
                            valid_from=now - timedelta(days=1), valid_to=now + timedelta(days=1)),
    ])
    db.flush()
    row = account_rows(db)[0]
    assert row["customer_id"] is None
    assert row["assignment_status"] == "CONFLICT"


def test_assignment_effective_time_does_not_overlap_or_rewrite_history(db):
    alice = Customer(name="Alice")
    bob = Customer(name="Bob")
    account = AdAccount(meta_ad_account_id="act_time_test", name="a", timezone_name="UTC")
    db.add_all([alice, bob, account])
    db.flush()
    now = datetime.now(timezone.utc)
    prior = AdAccountAssignment(customer_id=alice.id, ad_account_id=account.id,
                                valid_from=now - timedelta(days=3), valid_to=now - timedelta(days=1))
    db.add(prior)
    db.flush()
    with pytest.raises(accounts_service.AccountError, match="chồng lấn"):
        accounts_service.assign_account(db, bob.id, account.id, valid_from=now - timedelta(days=2))
    with pytest.raises(accounts_service.AccountError, match="tương lai"):
        accounts_service.assign_account(db, bob.id, account.id, valid_from=now + timedelta(days=1))
    start = now - timedelta(hours=12)
    new = accounts_service.assign_account(db, bob.id, account.id, valid_from=start)
    assert accounts_service.assign_account(db, bob.id, account.id, valid_from=start).id == new.id
    with pytest.raises(accounts_service.AccountError, match="thời điểm hiệu lực khác"):
        accounts_service.assign_account(db, bob.id, account.id, valid_from=now - timedelta(hours=1))
    assert prior.valid_to == now - timedelta(days=1)


def test_replace_rejects_occupied_target_and_preserves_old_assignment(db):
    alice, bob = Customer(name="Alice"), Customer(name="Bob")
    old = AdAccount(meta_ad_account_id="act_old_safe", name="old", timezone_name="UTC")
    target = AdAccount(meta_ad_account_id="act_occupied", name="target", timezone_name="UTC")
    db.add_all([alice, bob, old, target])
    db.flush()
    now = datetime.now(timezone.utc)
    old_assignment = AdAccountAssignment(customer_id=alice.id, ad_account_id=old.id, valid_from=now)
    db.add_all([old_assignment, AdAccountAssignment(customer_id=bob.id, ad_account_id=target.id, valid_from=now)])
    db.flush()
    with pytest.raises(accounts_service.AccountError, match="đã được phân công"):
        accounts_service.replace_account(db, old.id, target.meta_ad_account_id)
    assert old.status == "ACTIVE"
    assert old_assignment.valid_to is None


def test_account_rows_include_manual_restriction_timestamp(db):
    from app.services.dashboard import account_rows
    account = AdAccount(meta_ad_account_id="act_restricted_time", name="a", timezone_name="UTC")
    db.add(account)
    db.flush()
    accounts_service.restrict_account(db, account.id)
    row = account_rows(db)[0]
    assert row["status"] == "RESTRICTED"
    assert row["restricted_at"] == account.restricted_at.isoformat()


def test_transfer_is_atomic_preserves_history_and_rejects_stale_retry(db):
    from fastapi.testclient import TestClient

    alice, bob = Customer(name="Alice"), Customer(name="Bob")
    account = AdAccount(meta_ad_account_id="act_transfer_safe", name="a", timezone_name="UTC")
    db.add_all([alice, bob, account])
    db.flush()
    initial = AdAccountAssignment(customer_id=alice.id, ad_account_id=account.id,
                                  valid_from=datetime.now(timezone.utc) - timedelta(days=1))
    campaign = Campaign(meta_campaign_id="campaign_transfer_history", ad_account_id=account.id,
                        customer_id=alice.id, name="Alice", recognition_status="CONFIRMED")
    db.add_all([initial, campaign])
    db.commit()
    payload = {"ad_account_id": account.id, "customer_id": bob.id, "expected_assignment_id": initial.id}
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/api/v1/accounts/transfer", json=payload)
        assert response.status_code == 200, response.text
        retry = client.post("/api/v1/accounts/transfer", json=payload)
        assert retry.status_code == 409
        db.expire_all()
        history = db.scalars(select(AdAccountAssignment).where(
            AdAccountAssignment.ad_account_id == account.id).order_by(AdAccountAssignment.valid_from)).all()
        assert len(history) == 2
        assert history[0].customer_id == alice.id
        assert history[0].valid_to == history[1].valid_from
        assert history[1].customer_id == bob.id
        assert history[1].valid_to is None
        assert db.get(Campaign, campaign.id).customer_id == alice.id
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "account_transferred")) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_transfer_refuses_existing_ambiguous_open_assignments(db):
    alice, bob = Customer(name="Alice"), Customer(name="Bob")
    account = AdAccount(meta_ad_account_id="act_unique_assignment", name="a", timezone_name="UTC")
    db.add_all([alice, bob, account])
    db.flush()
    now = datetime.now(timezone.utc)
    db.add(AdAccountAssignment(customer_id=alice.id, ad_account_id=account.id, valid_from=now))
    db.flush()
    db.add(AdAccountAssignment(customer_id=bob.id, ad_account_id=account.id, valid_from=now - timedelta(days=1)))
    db.flush()
    first = db.scalar(select(AdAccountAssignment.id).where(AdAccountAssignment.customer_id == alice.id))
    with pytest.raises(accounts_service.AccountError, match="không rõ ràng"):
        accounts_service.transfer_account(db, account.id, bob.id, first)
    assert db.scalar(select(func.count(AdAccountAssignment.id)).where(
        AdAccountAssignment.ad_account_id == account.id, AdAccountAssignment.valid_to.is_(None))) == 2


# --- dashboard overview ---


def test_dashboard_overview_counts(db):
    seed(db, mock_connector())
    run_meta_sync(db, mock_connector(), now=utc(2026, 10, 26, 4, 0))
    from app.services.dashboard import overview

    data = overview(db)
    assert data["totals"]["customers"] == 2
    assert data["totals"]["accounts_total"] == 2  # 1 seeded + act_mock_2 từ mock sync
    assert data["totals"]["accounts_active"] == 2
    assert data["totals"]["campaigns_total"] == 5
    assert data["totals"]["campaigns_confirmed"] == 2  # cmp_1001 + cmp_1004 (alpha trên acc1)
    assert data["totals"]["campaigns_need_check"] == 3  # 1002 (KH Beta) + 1003 (lưỡng nghĩa) + 2001 (KH Gamma)
    assert data["mode"] == "mock"
    assert data["last_sync_at"] is not None


# --- dashboard campaigns ---


def test_dashboard_campaign_rows_fields(db):
    seed(db, mock_connector())
    run_meta_sync(db, mock_connector(), now=utc(2026, 10, 26, 4, 0))
    from app.services.dashboard import campaign_rows

    rows = {r["meta_campaign_id"]: r for r in campaign_rows(db)}
    row = rows["cmp_1001"]
    assert row["customer_name"] == "KH-S5-Alpha"
    assert row["report_period_start"] == "2026-10-25"
    assert row["timezone_name"] == "Asia/Ho_Chi_Minh"
    assert row["latest_spend"] == "1234.56"
    assert row["recognition_status"] == "CONFIRMED"
    assert row["updated_at"] is not None
    # chưa có checkpoint → None; drift None
    assert rows["cmp_1003"]["customer_id"] is None
    assert rows["cmp_1003"]["recognition_status"] == "UNRECOGNIZED"


def test_dashboard_shows_checkpoint_and_drift(db):
    seed(db, mock_connector())
    run_meta_sync(db, mock_connector(), now=utc(2026, 10, 26, 2, 0))  # checkpoint 09h VN
    db.expire_all()
    conn2 = mock_connector()
    conn2.mock.set_insight_spend("cmp_1004", 1500.0)
    run_meta_sync(db, conn2, now=utc(2026, 10, 26, 10, 0))
    from app.services.dashboard import campaign_rows

    row = {r["meta_campaign_id"]: r for r in campaign_rows(db)}["cmp_1004"]
    assert row["checkpoint_9h_spend"] == "1400.00"
    assert row["latest_spend"] == "1500.00"
    assert row["drift_amount"] == "100.00"
    assert row["meta_status"] == "PAUSED"


# --- quản lý account: assign / replace / cost ---


def test_assign_account_idempotent_and_audited(db):
    seed(db, mock_connector())
    account = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == "act_mock_2")).scalar_one_or_none()
    if account is None:
        account = AdAccount(meta_ad_account_id="act_mock_2", name="Acc 2", timezone_name="UTC")
        db.add(account)
        db.commit()
    customer = db.execute(select(Customer).where(Customer.name == "KH-S5-Beta")).scalar_one()
    first = accounts_service.assign_account(db, customer.id, account.id)
    count_before = db.execute(select(func.count(AdAccountAssignment.id))).scalar_one()
    second = accounts_service.assign_account(db, customer.id, account.id)
    count_after = db.execute(select(func.count(AdAccountAssignment.id))).scalar_one()
    assert first.id == second.id  # idempotent
    assert count_before == count_after
    audits = db.execute(select(AuditLog).where(AuditLog.action == "account_assigned")).scalars().all()
    assert audits


def test_replace_account_keeps_history(db):
    seed(db, mock_connector())
    acc1 = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == "act_mock_1")).scalar_one()
    old_assignments = db.execute(
        select(AdAccountAssignment).where(AdAccountAssignment.ad_account_id == acc1.id)
    ).scalars().all()
    assert len(old_assignments) == 1
    new_account = accounts_service.replace_account(
        db, acc1.id, "act_new_9", new_name="Acc 9", new_timezone_name="Asia/Ho_Chi_Minh"
    )
    db.commit()
    # account cũ giữ lại, trạng thái REPLACED, replaced_by trỏ mới; khách chuyển sang account mới
    db.expire_all()
    acc1 = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == "act_mock_1")).scalar_one()
    assert acc1.status == "REPLACED"
    assert acc1.replaced_by == new_account
    assert new_account.status == "ACTIVE"
    moved = db.execute(
        select(AdAccountAssignment).where(AdAccountAssignment.ad_account_id == new_account.id)
    ).scalars().all()
    assert len(moved) == 1 and moved[0].valid_to is None
    history_old = db.execute(
        select(AdAccountAssignment).where(AdAccountAssignment.ad_account_id == acc1.id)
    ).scalars().all()
    assert len(history_old) == 1 and history_old[0].valid_to is not None  # lịch sử cũ chỉ bị đóng
    audits = db.execute(select(AuditLog).where(AuditLog.action == "account_replaced")).scalars().all()
    assert audits


def test_set_purchase_cost(db):
    seed(db, mock_connector())
    acc1 = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == "act_mock_1")).scalar_one()
    accounts_service.set_purchase_cost(db, acc1.id, 99.5)
    db.commit()
    db.expire_all()
    acc1 = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == "act_mock_1")).scalar_one()
    assert acc1.purchase_cost == Decimal("99.50")


# --- endpoint dashboard (TestClient) ---


def test_dashboard_endpoints(db):
    seed(db, mock_connector())
    run_meta_sync(db, mock_connector(), now=utc(2026, 10, 26, 4, 0))
    app.dependency_overrides[get_db] = lambda: db
    try:
        from fastapi.testclient import TestClient

        client = TestClient(app)
        for path in ("/api/v1/dashboard/overview", "/api/v1/dashboard/campaigns",
                     "/api/v1/dashboard/accounts", "/api/v1/dashboard/system",
                     "/api/v1/customers", "/api/v1/ad-accounts"):
            resp = client.get(path)
            assert resp.status_code == 200, f"{path}: {resp.text}"
        system = client.get("/api/v1/dashboard/system").json()
        assert system["mode"] == "mock"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_account_management_endpoints(db):
    seed(db, mock_connector(), extra_account=True)
    from fastapi.testclient import TestClient

    acc_free = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == "act_mock_9")).scalar_one()
    acc1 = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == "act_mock_1")).scalar_one()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        # assign khách Beta → account rảnh act_mock_9 (acc1 đang mở cho alpha)
        resp = client.post("/api/v1/accounts/assign", json={"customer_id": 2, "ad_account_id": acc_free.id})
        assert resp.status_code == 200, resp.text
        # replace acc1 (đang dùng bởi alpha) → act_new_7
        resp = client.post(
            "/api/v1/accounts/replace",
            json={"old_account_id": acc1.id, "new_meta_ad_account_id": "act_new_7", "new_name": "Acc 7"},
        )
        assert resp.status_code == 200, resp.text
        resp = client.post(f"/api/v1/accounts/{acc1.id}/purchase-cost", json={"cost": 150.75})
        assert resp.status_code == 200, resp.text
        accounts = client.get("/api/v1/dashboard/accounts").json()
        replaced = next(a for a in accounts if a["meta_ad_account_id"] == "act_mock_1")
        assert replaced["status"] == "REPLACED"
        assert replaced["purchase_cost"] == "150.75"
        assert replaced["customer_name"] is None  # chuyển đi rồi; lịch sử trong assignment_history
        assert replaced["assignment_history"][-1]["customer_name"] == "KH-S5-Alpha"
        new_row = next(a for a in accounts if a["meta_ad_account_id"] == "act_new_7")
        assert new_row["customer_name"] == "KH-S5-Alpha"
        # gán tài khoản đã REPLACED → bị chặn (400)
        resp = client.post("/api/v1/accounts/assign", json={"customer_id": 2, "ad_account_id": acc1.id})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_assign_blocked_when_account_shared_or_inactive(db):
    seed(db, mock_connector())
    alpha = db.execute(select(Customer).where(Customer.name == "KH-S5-Alpha")).scalar_one()
    beta = db.execute(select(Customer).where(Customer.name == "KH-S5-Beta")).scalar_one()
    acc1 = db.execute(select(AdAccount).where(AdAccount.meta_ad_account_id == "act_mock_1")).scalar_one()
    # acc1 đang mở cho alpha → gán cho beta bị chặn (1 account = 1 khách tại một thời điểm)
    with pytest.raises(accounts_service.AccountError):
        accounts_service.assign_account(db, beta.id, acc1.id)
    # account không ACTIVE → bị chặn
    accounts_service.replace_account(db, acc1.id, "act_new_2")
    with pytest.raises(accounts_service.AccountError):
        accounts_service.assign_account(db, beta.id, acc1.id)


def test_create_customer_and_account_endpoints(db):
    seed(db, mock_connector())
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.post("/api/v1/customers", json={"name": "KH Mới 2026", "telegram_chat_id": "555"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "CREATED"
        # trùng tên bị chặn
        resp = client.post("/api/v1/customers", json={"name": "KH Mới 2026"})
        assert resp.status_code == 400
        resp = client.post(
            "/api/v1/ad-accounts",
            json={"meta_ad_account_id": "act_new_55", "name": "Acc 55", "timezone_name": "UTC"},
        )
        assert resp.status_code == 200, resp.text
        # trùng Act ID bị chặn
        resp = client.post("/api/v1/ad-accounts", json={"meta_ad_account_id": "act_new_55"})
        assert resp.status_code == 400
        customers = client.get("/api/v1/customers").json()
        assert any(c["name"] == "KH Mới 2026" for c in customers)
        ad_accounts = client.get("/api/v1/ad-accounts").json()
        assert any(a["meta_ad_account_id"] == "act_new_55" for a in ad_accounts)
    finally:
        app.dependency_overrides.pop(get_db, None)
