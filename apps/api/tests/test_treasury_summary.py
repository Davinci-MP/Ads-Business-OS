"""Kiểm thử Tổng quan Nguồn vốn & Ngân quỹ (Treasury Summary)."""
from datetime import datetime, timezone
from decimal import Decimal

import alembic.command
import alembic.config
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db import get_db
from app.main import app
from app.models.exchange import (
    EXCH_PROVIDER_BINANCE,
    EXCH_PROVIDER_PINGPONG,
    EXCH_STATUS_ACTIVE,
    EXCH_WALLET_CARDS,
    EXCH_WALLET_FUNDING,
    EXCH_WALLET_SPOT,
    ExchangeBalanceSnapshot,
    ExchangeCardSnapshot,
    ExchangeConnection,
)
from app.models.finance import UsdtWallet, UsdtWalletBalance
from app.services import treasury as treasury_service


@pytest.fixture
def db(tmp_path):
    database = tmp_path / "treasury-test.db"
    cfg = alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    alembic.command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_empty_treasury_summary(db):
    """Khi DB chưa có ví/sàn/PingPong nào, trả về 0 an toàn."""
    res = treasury_service.get_treasury_summary(db)
    s = res["summary"]
    assert s["total_liquid_usdt"] == "0"
    assert s["total_pingpong_usd"] == "0"
    assert s["grand_total_working_capital"] == "0"
    assert s["total_active_vcc_cards"] == 0


def test_treasury_summary_aggregated(db):
    """Kiểm tra tổng hợp chính xác số dư từ TRON, Binance và PingPong VCC."""
    now = datetime.now(timezone.utc)

    # 1. Thêm ví TRON (100.50 USDT)
    tron = UsdtWallet(
        wallet_name="Ví TRON Tổng",
        wallet_address="TPVT4NSNjCCEeaR5FpAq3Q9g65hXF8Uh9r",
        contract="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    )
    db.add(tron)
    db.flush()
    db.add(UsdtWalletBalance(
        wallet_id=tron.id,
        wallet_address=tron.wallet_address,
        balance=Decimal("100.500000"),
        source="MANUAL",
        read_at=now,
    ))

    # 2. Thêm kết nối Binance (Spot 1500 + Funding 500 = 2000 USDT)
    binance = ExchangeConnection(
        provider=EXCH_PROVIDER_BINANCE,
        label="Binance Chính",
        status=EXCH_STATUS_ACTIVE,
        wallet_types=["spot", "funding"],
        read_only_verified=True,
    )
    db.add(binance)
    db.flush()
    db.add(ExchangeBalanceSnapshot(
        connection_id=binance.id,
        wallet_type=EXCH_WALLET_SPOT,
        asset="USDT",
        free=Decimal("1500.00"),
        locked=Decimal("0"),
        source="MANUAL",
        read_at=now,
    ))
    db.add(ExchangeBalanceSnapshot(
        connection_id=binance.id,
        wallet_type=EXCH_WALLET_FUNDING,
        asset="USDT",
        free=Decimal("500.00"),
        locked=Decimal("0"),
        source="MANUAL",
        read_at=now,
    ))

    # 3. Thêm kết nối PingPong (USD 5000 + 2 thẻ VCC: 1200 + 800)
    pingpong = ExchangeConnection(
        provider=EXCH_PROVIDER_PINGPONG,
        label="PingPong Chính",
        status=EXCH_STATUS_ACTIVE,
        wallet_types=["funding", "cards"],
        read_only_verified=True,
    )
    db.add(pingpong)
    db.flush()
    db.add(ExchangeBalanceSnapshot(
        connection_id=pingpong.id,
        wallet_type=EXCH_WALLET_FUNDING,
        asset="USD",
        free=Decimal("5000.00"),
        locked=Decimal("200.00"),
        source="MANUAL",
        read_at=now,
    ))
    db.add(ExchangeCardSnapshot(
        connection_id=pingpong.id,
        card_id="card_01",
        card_name="Media Buyer 1",
        last4="1111",
        currency="USD",
        status="ACTIVE",
        spending_limit=Decimal("2000.00"),
        available_balance=Decimal("1200.00"),
        read_at=now,
    ))
    db.add(ExchangeCardSnapshot(
        connection_id=pingpong.id,
        card_id="card_02",
        card_name="Media Buyer 2",
        last4="2222",
        currency="USD",
        status="ACTIVE",
        spending_limit=Decimal("1000.00"),
        available_balance=Decimal("800.00"),
        read_at=now,
    ))
    db.add(ExchangeCardSnapshot(
        connection_id=pingpong.id,
        card_id="card_03",
        card_name="Thẻ đóng",
        last4="3333",
        currency="USD",
        status="CLOSED",
        spending_limit=Decimal("500.00"),
        available_balance=Decimal("0"),
        read_at=now,
    ))
    db.commit()

    res = treasury_service.get_treasury_summary(db)
    s = res["summary"]

    # TRON: 100.50 + Binance: 2000.00 = 2100.50 USDT
    assert Decimal(s["total_liquid_usdt"]) == Decimal("2100.50")

    # PingPong: 5000.00 USD
    assert Decimal(s["total_pingpong_usd"]) == Decimal("5000.00")

    # Tổng vốn lưu động: 2100.50 + 5000.00 = 7100.50
    assert Decimal(s["grand_total_working_capital"]) == Decimal("7100.50")

    # Thẻ hoạt động: 2 thẻ (card_01 & card_02); số dư = 1200 + 800 = 2000.00
    assert s["total_active_vcc_cards"] == 2
    assert Decimal(s["total_vcc_available_balance"]) == Decimal("2000.00")
    assert Decimal(s["total_vcc_spending_limit"]) == Decimal("3000.00")


def test_treasury_api_endpoint(client, db):
    """Kiểm tra gọi API GET /api/v1/dashboard/treasury-summary."""
    resp = client.get("/api/v1/dashboard/treasury-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "breakdown" in data
    assert "tron" in data["breakdown"]
    assert "binance" in data["breakdown"]
    assert "pingpong" in data["breakdown"]
