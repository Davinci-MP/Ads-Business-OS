from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models import Customer, AuditLog
from app.services.accounts import AccountError, create_customer, update_customer_profile


def test_customer_profile_defaults_and_exact_custom_fee_are_audited(db):
    customer = create_customer(db, "Khách giao diện")
    db.flush()
    assert customer.fee_rate == Decimal("0.04")
    created = db.scalar(select(AuditLog).where(AuditLog.action == "customer_created", AuditLog.entity_id == "Khách giao diện"))
    assert created.detail["fee_rate"] == "0.04"
    update_customer_profile(db, customer.id, "Khách đã sửa", "-100123", "@khach", Decimal("0.045"))
    assert customer.fee_rate == Decimal("0.045")
    assert customer.telegram_username == "khach"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "customer_profile_updated")) is not None


@pytest.mark.parametrize("rate", ["-0.01", "1.01", "NaN"])
def test_invalid_fee_never_changes_customer(db, rate):
    customer = create_customer(db, "Phí giữ nguyên")
    with pytest.raises(AccountError):
        update_customer_profile(db, customer.id, "Tên mới", None, None, Decimal(rate))
    assert customer.name == "Phí giữ nguyên"
    assert customer.fee_rate == Decimal("0.04")


def test_duplicate_customer_name_keeps_existing_profile(db):
    create_customer(db, "Tên đã tồn tại")
    customer = create_customer(db, "Tên giữ lại")
    with pytest.raises(AccountError):
        update_customer_profile(db, customer.id, "Tên đã tồn tại", None, None, Decimal("0.05"))
    assert customer.name == "Tên giữ lại"


def test_customer_profile_api_validates_and_serializes_decimal(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/api/v1/customers", json={
            "name":"Khách API UI", "fee_rate":"0.045", "telegram_username":"@api_ui",
            "sheet_url":"https://docs.google.com/spreadsheets/d/12345678901234567890/edit",
            "sheet_tab_name":"JOKER", "sync_time":"09:15",
        })
        assert response.status_code == 200
        customer_id = response.json()["customer_id"]
        response = client.patch(f"/api/v1/customers/{customer_id}", json={"name":"Khách API UI mới", "fee_rate":"0.05"})
        assert response.status_code == 200
        profile = next(c for c in client.get("/api/v1/customers").json() if c["id"] == customer_id)
        assert Decimal(profile["fee_rate"]) == Decimal("0.05")
        assert profile["sheet_tab_name"] is None
        assert profile["sync_time"] is None
        assert client.patch(f"/api/v1/customers/{customer_id}", json={"name":"x","fee_rate":"2"}).status_code == 422
        assert db.get(Customer, customer_id).fee_rate == Decimal("0.05")
        deleted = client.delete(f"/api/v1/customers/{customer_id}")
        assert deleted.status_code == 200
        assert db.get(Customer, customer_id).is_active is False
        assert client.post("/api/v1/customers", json={"name":"Không được tạo"}, headers={"origin":"https://example.invalid"}).status_code == 403
    finally:
        client.close()
        app.dependency_overrides.clear()
