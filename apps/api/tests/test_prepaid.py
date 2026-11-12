from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from app.models.finance import LedgerEntry, TelegramOutbox
from app.models.prepaid import ClientBalance, LedgerTransaction
from app.services.prepaid import request_transaction, approve_transaction, process_approved_transactions, balance_for, check_low_balance
from conftest import make_customer


def request(db, customer, **kwargs):
    values = dict(customer_id=customer.id, currency="VND", amount="1000", kind="DEPOSIT", idempotency_key=f"deposit-{customer.id}", evidence="Biên nhận đã kiểm tra", actor="quản trị")
    values.update(kwargs)
    return request_transaction(db, **values)


def test_approval_required_idempotent_and_currency_separate(db):
    c = make_customer(db, "prepaid-idempotent")
    tx = request(db, c)
    assert process_approved_transactions(db) == 0
    assert request(db, c).id == tx.id
    with pytest.raises(ValueError, match="nội dung khác"):
        request(db, c, amount="2000")
    approve_transaction(db, tx.id, "chủ dự án")
    db.flush()
    assert process_approved_transactions(db) == 1
    assert process_approved_transactions(db) == 0
    assert balance_for(db, c.id, "VND").amount == Decimal("1000")
    assert balance_for(db, c.id, "USDT").amount == Decimal("0")


def test_final_source_debit_separate_and_negative_allowed(db):
    c = make_customer(db, "prepaid-debit")
    source = LedgerEntry(customer_id=c.id, currency="VND", amount=Decimal("500"), entry_kind="SERVICE_FEE", period_start=date(2026, 10, 30), period_end=date(2026, 10, 30), state="TEMP")
    db.add(source); db.flush()
    with pytest.raises(ValueError, match="đã chốt"):
        request(db, c, kind="SERVICE_FEE", amount="500", source_ledger_id=source.id)
    source.state = "FINAL"
    tx = request(db, c, kind="SERVICE_FEE", amount="500", source_ledger_id=source.id)
    approve_transaction(db, tx.id, "chủ dự án"); db.flush()
    assert process_approved_transactions(db) == 1
    assert balance_for(db, c.id, "VND").amount == Decimal("-500")
    with pytest.raises(ValueError, match="đã có đề nghị"):
        request(db, c, kind="SERVICE_FEE", amount="500", source_ledger_id=source.id, idempotency_key="duplicate-source")


def test_low_balance_outbox_once_then_rearms(db):
    c = make_customer(db, "prepaid-alert")
    b = balance_for(db, c.id, "VND")
    b.low_threshold = Decimal("200")
    count = db.scalar(select(func.count()).select_from(TelegramOutbox))
    check_low_balance(db, b); db.flush()
    check_low_balance(db, b); db.flush()
    assert db.scalar(select(func.count()).select_from(TelegramOutbox)) == count + 1
    b.amount = Decimal("300"); check_low_balance(db, b)
    b.amount = Decimal("100"); check_low_balance(db, b); db.flush()
    assert db.scalar(select(func.count()).select_from(TelegramOutbox)) == count + 2


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1", "0", "abc", "1e100", "99999999999999999"])
def test_invalid_money_rejected(db, amount):
    c = make_customer(db, f"prepaid-invalid-{amount}")
    with pytest.raises(ValueError):
        request(db, c, amount=amount)


def test_staging_does_not_mutate(db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "app_env", "staging")
    c = make_customer(db, "prepaid-staging")
    with pytest.raises(ValueError, match="local"):
        request(db, c)
    assert process_approved_transactions(db) == 0


def test_changed_final_source_not_deducted(db):
    c = make_customer(db, "prepaid-source-changed")
    source = LedgerEntry(customer_id=c.id, currency="VND", amount=Decimal("500"), entry_kind="SERVICE_FEE", period_start=date(2026, 10, 30), period_end=date(2026, 10, 30), state="FINAL")
    db.add(source); db.flush()
    tx = request(db, c, kind="SERVICE_FEE", amount="500", source_ledger_id=source.id)
    approve_transaction(db, tx.id, "chủ dự án")
    source.amount = Decimal("600")
    db.flush()
    assert process_approved_transactions(db) == 0
    assert tx.status == "NEEDS_CONFIRMATION"
    assert balance_for(db, c.id, "VND").amount == Decimal("0")


def test_prepaid_api_approval_flow_and_origin(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1.prepaid import router
    from app.db import get_db
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_db] = lambda: db
    client = TestClient(application)
    c = make_customer(db, "prepaid-api")
    payload = dict(customer_id=c.id, currency="VND", amount="1250.5", kind="DEPOSIT", idempotency_key="api-deposit", evidence="Biên nhận ngân hàng", actor="chủ dự án")
    assert client.post("/prepaid/transactions", json=payload, headers={"Origin": "https://khong-duoc-phep.example"}).status_code == 403
    result = client.post("/prepaid/transactions", json=payload)
    assert result.status_code == 200
    tx_id = result.json()["id"]
    assert client.post("/prepaid/process").json()["processed"] == 0
    assert client.post(f"/prepaid/transactions/{tx_id}/approve", json={"actor": "chủ dự án"}).status_code == 200
    assert client.post("/prepaid/process").json()["processed"] == 1
    assert client.post("/prepaid/process").json()["processed"] == 0
    rows = client.get("/prepaid").json()["balances"]
    assert next(row for row in rows if row["customer_id"] == c.id)["amount"] == "1251.000000"


def test_source_other_customer_or_currency_rejected(db):
    c = make_customer(db, "prepaid-source-owner")
    other = make_customer(db, "prepaid-source-other")
    source = LedgerEntry(customer_id=other.id, currency="USD", amount=Decimal("500"), entry_kind="ACTUAL_SPEND", period_start=date(2026, 10, 30), period_end=date(2026, 10, 30), state="FINAL")
    db.add(source); db.flush()
    with pytest.raises(ValueError, match="cùng khách"):
        request(db, c, kind="ACTUAL_SPEND", amount="500", source_ledger_id=source.id)
    with pytest.raises(ValueError, match="NEEDS_CONFIRMATION"):
        request(db, other, currency="USD", kind="ACTUAL_SPEND", amount="500", source_ledger_id=source.id)
