from datetime import datetime, timezone
from pathlib import Path

import alembic.command
import alembic.config
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import AdAccount, AdAccountAssignment, Campaign, Customer
from app.models.campaign import RECOGNITION_CONFIRMED, RECOGNITION_UNRECOGNIZED
from app.models.customer import RECON_PROFIT_SHARE
from app.core.config import settings
from cryptography.fernet import Fernet

API_DIR = Path(__file__).resolve().parents[1]
TEST_DB_FILE = API_DIR / "test_adsos.db"


@pytest.fixture(autouse=True)
def default_test_fernet_key(monkeypatch):
    """Đảm bảo mọi test suite đều có Fernet test key hợp lệ, không phụ thuộc plaintext fallback."""
    if not getattr(settings, "exchange_master_key", ""):
        key = Fernet.generate_key().decode()
        monkeypatch.setattr(settings, "exchange_master_key", key)


def datetime_utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def engine():
    url = f"sqlite:///{TEST_DB_FILE}"
    if TEST_DB_FILE.exists():
        TEST_DB_FILE.unlink()
    alembic_cfg = alembic.config.Config(str(API_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    alembic.command.upgrade(alembic_cfg, "head")
    engine = create_engine(url, future=True)
    yield engine
    engine.dispose()
    if TEST_DB_FILE.exists():
        TEST_DB_FILE.unlink()


@pytest.fixture()
def db(engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def make_customer(session, name, **kwargs):
    customer = Customer(name=name, **kwargs)
    session.add(customer)
    session.commit()
    return customer


def make_profit_share_customer(session, name):
    return make_customer(session, name, recon_mode=RECON_PROFIT_SHARE, profit_share_enabled=True)


def make_campaign(session, meta_campaign_id, customer=None, name="1025-KH", meta_status="ACTIVE", stopped_at=None):
    account = AdAccount(
        meta_ad_account_id=f"act_{meta_campaign_id}",
        name="acc",
        timezone_name="Asia/Ho_Chi_Minh",
    )
    session.add(account)
    session.flush()
    if customer is not None:
        session.add(
            AdAccountAssignment(customer_id=customer.id, ad_account_id=account.id, valid_from=datetime_utc(2026, 10, 1))
        )
        session.flush()
    campaign = Campaign(
        meta_campaign_id=meta_campaign_id,
        ad_account_id=account.id,
        customer_id=customer.id if customer is not None else None,
        name=name,
        recognition_status=RECOGNITION_CONFIRMED if customer is not None else RECOGNITION_UNRECOGNIZED,
        meta_status=meta_status,
        stopped_at=stopped_at,
    )
    session.add(campaign)
    session.commit()
    return campaign


def add_snapshot(session, campaign, at, amount, is_checkpoint_9h=False, data_status="VERIFIED"):
    from decimal import Decimal

    from app.models.spend import SpendSnapshot

    snapshot = SpendSnapshot(
        campaign_id=campaign.id,
        snapshot_at=at,
        spend_amount=Decimal(amount),
        is_checkpoint_9h=is_checkpoint_9h,
        data_status=data_status,
    )
    session.add(snapshot)
    session.commit()
    return snapshot
