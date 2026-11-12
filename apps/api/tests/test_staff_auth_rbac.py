from uuid import uuid4
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.customer import Customer
from app.models.extension_remote import RemoteViaCommand
from app.models.staff import StaffAuditLog
from app.models.via import SyncedAdAccount, SyncedBM, ViaProfile


def test_staff_auth_assignment_and_share_queue(db):
    customer = Customer(name=f"Khách E2E {uuid4().hex[:8]}")
    via = ViaProfile(
        uid=f"via-{uuid4().hex[:12]}",
        profile_name="VIA E2E",
        profile_dir="profiles/e2e",
        user_agent="pytest",
        encrypted_credentials="{}",
        token_status="ACTIVE",
    )
    db.add_all([customer, via])
    db.flush()
    bm = SyncedBM(bm_id=f"{uuid4().int}"[:15], via_profile_id=via.id, name="BM E2E")
    account = SyncedAdAccount(
        via_profile_id=via.id,
        customer_id=customer.id,
        bm_id=bm.bm_id,
        account_type="BM",
        act_id=str(uuid4().int)[:15],
        name="TKQC E2E",
    )
    db.add_all([bm, account])
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123"})
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        username = f"staff_{uuid4().hex[:10]}"
        created = client.post(
            "/api/v1/staff",
            headers=headers,
            json={
                "username": username,
                "full_name": "Nhân viên E2E",
                "email": "staff-e2e@example.com",
                "password": "Secure@123",
                "role": "STAFF_SUPPORT",
                "assigned_customer_ids": [],
            },
        )
        assert created.status_code == 201, created.text
        staff_id = created.json()["id"]

        updated = client.patch(
            f"/api/v1/staff/{staff_id}",
            headers=headers,
            json={"role": "STAFF_OPS", "assigned_customer_ids": [customer.id]},
        )
        assert updated.status_code == 200, updated.text

        listed = client.get("/api/v1/staff", headers=headers)
        assert listed.status_code == 200, listed.text
        saved = next(item for item in listed.json() if item["id"] == staff_id)
        assert saved["role"] == "STAFF_OPS"
        assert saved["assigned_customer_ids"] == [customer.id]

        account_update = client.patch(
            f"/api/v1/ads-check/accounts/{account.act_id}",
            headers=headers,
            json={"customer_id": customer.id, "service_fee_percent": "5.5"},
        )
        assert account_update.status_code == 200, account_update.text
        db.refresh(account)
        assert account.customer_id == customer.id
        assert account.service_fee_rate == Decimal("0.0550")

        staff_login = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "Secure@123"},
        )
        assert staff_login.status_code == 200, staff_login.text
        denied_admin_share = client.post(
            "/api/v1/ads-check/share-bm-accounts",
            headers={"Authorization": f"Bearer {staff_login.json()['access_token']}"},
            json={
                "bm_id": bm.bm_id,
                "customer_emails": ["customer@example.com"],
                "bm_role": "ADMIN",
                "ad_account_tasks": ["MANAGE"],
                "account_ids": [account.act_id],
            },
        )
        assert denied_admin_share.status_code == 403

        shared = client.post(
            "/api/v1/ads-check/share-bm-accounts",
            headers=headers,
            json={
                "bm_id": bm.bm_id,
                "customer_emails": ["customer@example.com"],
                "bm_role": "EMPLOYEE",
                "ad_account_tasks": ["ADVERTISE", "ANALYZE"],
                "account_ids": [account.act_id],
                "customer_id": customer.id,
            },
        )
        assert shared.status_code == 200, shared.text
        body = shared.json()
        assert body["results"] == [{"account_id": account.act_id, "status": "PENDING"}]
        assert db.scalar(
            select(RemoteViaCommand).where(RemoteViaCommand.public_id == body["command_id"])
        ).command_type == "SHARE_BM_ACCOUNTS"
        assert db.scalar(
            select(StaffAuditLog).where(
                StaffAuditLog.action_type == "SHARE_BM",
                StaffAuditLog.target_bm_id == bm.bm_id,
            ).order_by(StaffAuditLog.id.desc())
        ) is not None
    finally:
        app.dependency_overrides.pop(get_db, None)
