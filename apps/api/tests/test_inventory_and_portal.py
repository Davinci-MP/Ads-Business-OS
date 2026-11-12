from decimal import Decimal
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.inventory import decrypt_credentials, encrypt_credentials, router as inventory_router
from app.api.v1.meta_risk import router as meta_risk_router
from app.api.v1.portal import router as portal_router
from app.api.v1.prepaid import router as prepaid_router
from app.db import get_db
from app.models.ad_account import AdAccount, AdAccountAssignment
from app.models.customer import Customer
from app.models.inventory import InventoryItem, STATUS_AVAILABLE, STATUS_ASSIGNED, STATUS_DEAD
from app.models.meta_risk import MetaAccountRisk
from app.models.prepaid import ClientBalance
from conftest import make_customer


@pytest.fixture
def test_app(db):
    app = FastAPI()
    app.include_router(inventory_router)
    app.include_router(portal_router)
    app.include_router(prepaid_router)
    app.include_router(meta_risk_router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_inventory_encryption_and_crud(test_app, db):
    # 1. Test encryption helpers
    raw = "1000888999|password123|2FA_SECRET_KEY"
    encrypted = encrypt_credentials(raw)
    assert encrypted != raw
    decrypted = decrypt_credentials(encrypted)
    assert decrypted == raw

    # 2. Test create inventory item
    res = test_app.post(
        "/inventory",
        json={
            "item_type": "VIA",
            "name": "VIA US Cổ 2018",
            "credentials": raw,
            "notes": "Chuyên chạy thị trường US",
        },
    )
    assert res.status_code == 200, res.text
    item_data = res.json()
    assert item_data["name"] == "VIA US Cổ 2018"
    assert item_data["item_type"] == "VIA"
    assert item_data["status"] == STATUS_AVAILABLE
    assert item_data["has_credentials"] is True
    item_id = item_data["id"]

    # 3. Test list inventory items
    list_res = test_app.get("/inventory")
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(it["id"] == item_id for it in items)

    # 4. Test get credentials
    cred_res = test_app.get(f"/inventory/{item_id}/credentials")
    assert cred_res.status_code == 200
    assert cred_res.json()["credentials"] == raw

    # 5. Test handover to customer
    c = make_customer(db, "Khách Hàng Inventory")
    handover_res = test_app.post(
        f"/inventory/{item_id}/handover",
        json={"customer_id": c.id, "assigned_ad_account_id": "act_889900", "actor": "admin"},
    )
    assert handover_res.status_code == 200
    assert handover_res.json()["status"] == STATUS_ASSIGNED
    assert handover_res.json()["assigned_customer_id"] == c.id
    assert handover_res.json()["customer_name"] == c.name
    assert handover_res.json()["credentials"] == raw

    # 6. Test update status
    patch_res = test_app.patch(
        f"/inventory/{item_id}/status",
        json={"status": "DEAD", "notes": "Đã bị checkpoint 282"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == STATUS_DEAD
    assert patch_res.json()["notes"] == "Đã bị checkpoint 282"

    # 7. Test delete inventory item
    del_res = test_app.delete(f"/inventory/{item_id}")
    assert del_res.status_code == 200
    assert test_app.get(f"/inventory/{item_id}/credentials").status_code == 404


def test_client_portal_flow(test_app, db):
    c = make_customer(db, "Khách Hàng Portal VIP")
    bal = ClientBalance(customer_id=c.id, currency="VND", amount=Decimal("15000000"), low_threshold=Decimal("2000000"))
    db.add(bal)
    acc = AdAccount(meta_ad_account_id="act_portal_01", name="TKQC Portal Demo", timezone_name="Asia/Ho_Chi_Minh")
    db.add(acc)
    db.flush()
    assignment = AdAccountAssignment(customer_id=c.id, ad_account_id=acc.id, valid_from=c.created_at)
    db.add(assignment)
    db.commit()

    # 1. Before generating token, portal access fails
    fail_res = test_app.get("/portal/non-existent-token")
    assert fail_res.status_code == 404

    # 2. Generate token
    gen_res = test_app.post(f"/portal/customers/{c.id}/generate-token")
    assert gen_res.status_code == 200
    token = gen_res.json()["portal_token"]
    assert len(token) == 64

    # 3. Read client portal via public token
    portal_res = test_app.get(f"/portal/{token}")
    assert portal_res.status_code == 200
    data = portal_res.json()
    assert data["customer"]["name"] == "Khách Hàng Portal VIP"
    assert len(data["balances"]) >= 1
    assert data["balances"][0]["currency"] == "VND"
    assert Decimal(data["balances"][0]["amount"]) == Decimal("15000000")
    assert len(data["assigned_accounts"]) == 1
    assert data["assigned_accounts"][0]["meta_ad_account_id"] == "act_portal_01"

    # 4. Revoke token
    del_res = test_app.delete(f"/portal/customers/{c.id}/token")
    assert del_res.status_code == 200
    assert test_app.get(f"/portal/{token}").status_code == 404

    # Cleanup committed test fixtures to prevent cross-test state leakage
    db.delete(bal)
    db.delete(assignment)
    db.delete(acc)
    db.delete(c)
    db.commit()


def test_prepaid_transaction_rejection(test_app, db):
    c = make_customer(db, "Khách Hàng Reject Test")
    req_res = test_app.post(
        "/prepaid/transactions",
        json={
            "customer_id": c.id,
            "currency": "VND",
            "amount": "500000",
            "kind": "DEPOSIT",
            "idempotency_key": "dep-reject-01",
            "evidence": "Nạp tiền nhầm mã",
            "actor": "nhân viên",
        },
    )
    assert req_res.status_code == 200
    tx_id = req_res.json()["id"]
    assert req_res.json()["status"] == "CREATED"

    # Reject
    rej_res = test_app.post(f"/prepaid/transactions/{tx_id}/reject", json={"actor": "quản trị viên"})
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"


def test_meta_risk_unlock_endpoint(test_app, db):
    account_id = "act_risk_unlock_test"
    risk = MetaAccountRisk(account_id=account_id, locked=True, currency="VND")
    db.add(risk)
    db.commit()

    res = test_app.post(f"/meta-risk/{account_id}/unlock")
    assert res.status_code == 200
    assert res.json()["locked"] is False

    refreshed = db.get(MetaAccountRisk, account_id)
    assert refreshed.locked is False
