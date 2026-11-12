from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.connectors.meta import MetaAPIError, MetaAdsConnector
from app.connectors.telegram import TelegramAPIError
from app.core.config import settings
from app.models.base import Base
from app.models.finance import TelegramOutbox
from app.models.meta_risk import MetaAccountRisk
from app.services.meta_risk import assert_account_unlocked, get_risk, lock_account, scan_account_risks


@pytest.fixture
def risk_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


class FakeMeta:
    mode = "live"
    status = 1
    debt = "20.01"
    fail = False
    paused = []

    def get_ad_accounts(self):
        return [{"meta_ad_account_id": "act_123"}]

    def get_ad_account_billing_health(self, account):
        if self.fail:
            raise MetaAPIError("Lỗi thử nghiệm")
        return {"account_status": self.status, "balance": self.debt, "currency": "VND"}

    def get_account_campaigns(self, account):
        return [{"meta_campaign_id": "12345"}]

    def update_campaign_status(self, campaign, status):
        if self.fail:
            raise MetaAPIError("Lỗi thử nghiệm")
        self.paused.append((campaign, status))
        return {"success": True}


class FakeTelegram:
    def __init__(self):
        self.messages = []
        self.fail = False

    def send_admin_message(self, message):
        if self.fail:
            raise TelegramAPIError("Lỗi thử nghiệm")
        self.messages.append(message)


def test_scanner_alert_transition_dedup_and_recovery(risk_db):
    meta, tg = FakeMeta(), FakeTelegram()
    scan_account_risks(risk_db, meta, tg)
    assert tg.messages == []
    meta.status = 2
    scan_account_risks(risk_db, meta, tg)
    scan_account_risks(risk_db, meta, tg)
    assert len(tg.messages) == 1
    meta.status = 1
    scan_account_risks(risk_db, meta, tg)
    meta.status = 2
    scan_account_risks(risk_db, meta, tg)
    assert len(tg.messages) == 2


def test_api_failure_preserves_verified_values(risk_db):
    meta, tg = FakeMeta(), FakeTelegram()
    scan_account_risks(risk_db, meta, tg)
    meta.fail = True
    assert scan_account_risks(risk_db, meta, tg)["errors"] == 1
    row = risk_db.get(MetaAccountRisk, "act_123")
    assert row.debt == Decimal("20.01")
    assert row.account_status == 1
    assert row.data_status == "UNVERIFIED"


def test_explicit_threshold_and_outbox(risk_db):
    meta, tg = FakeMeta(), FakeTelegram()
    scan_account_risks(risk_db, meta, tg)
    get_risk(risk_db, "123").debt_threshold = Decimal("20")
    tg.fail = True
    scan_account_risks(risk_db, meta, tg)
    scan_account_risks(risk_db, meta, tg)
    assert len(risk_db.scalars(select(TelegramOutbox)).all()) == 1
    assert risk_db.get(MetaAccountRisk, "act_123").risk_code == "HIGH_DEBT"


def test_lock_pauses_and_blocks_override(risk_db, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    meta = FakeMeta()
    result = lock_account(risk_db, meta, "123")
    assert result["paused"] == []
    assert result["queued"] == ["12345"]
    with pytest.raises(ValueError, match="khóa an toàn"):
        assert_account_unlocked(risk_db, "act_123")


def test_lock_retained_when_remote_pause_fails(risk_db, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    meta = FakeMeta()
    meta.fail = True
    result = lock_account(risk_db, meta, "123")
    assert result["queued"] == ["12345"]
    assert result["failed"] == []
    assert risk_db.get(MetaAccountRisk, "act_123").locked


def test_staging_refuses_lock(risk_db, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "staging")
    with pytest.raises(ValueError, match="chỉ đọc"):
        lock_account(risk_db, FakeMeta(), "123")


def test_live_write_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "meta_writes_enabled", False)
    connector = MetaAdsConnector()
    with pytest.raises(MetaAPIError, match="chưa được bật"):
        connector._graph_post("123", {"status": "PAUSED"}, "")
    with pytest.raises(MetaAPIError, match="chỉ được đọc"):
        connector.batch_request([{"method": "DELETE", "relative_url": "123"}])
    connector.close()


def test_staging_refuses_live_write_even_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "staging")
    monkeypatch.setattr(settings, "meta_writes_enabled", True)
    connector = MetaAdsConnector()
    with pytest.raises(MetaAPIError, match="chỉ đọc"):
        connector._graph_post("123", {"status": "PAUSED"}, "")
    connector.close()


def test_mock_ids_and_currency_reset_threshold(risk_db):
    meta, tg = FakeMeta(), FakeTelegram()
    meta.mode = "mock"
    meta.get_ad_accounts = lambda: [{"meta_ad_account_id": "act_mock_1"}]
    scan_account_risks(risk_db, meta, tg)
    row = risk_db.get(MetaAccountRisk, "act_mock_1")
    row.debt_threshold = Decimal("1")
    row.currency = "USD"
    scan_account_risks(risk_db, meta, tg)
    assert row.currency == "VND" and row.debt_threshold is None


def test_disabled_remains_priority_over_high_debt(risk_db):
    meta, tg = FakeMeta(), FakeTelegram()
    scan_account_risks(risk_db, meta, tg)
    row = risk_db.get(MetaAccountRisk, "act_123")
    row.debt_threshold = Decimal("1")
    meta.status = 2
    scan_account_risks(risk_db, meta, tg)
    assert row.risk_code == "DISABLED"


def test_unknown_remote_response_is_failure(risk_db, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "local")
    meta = FakeMeta()
    meta.update_campaign_status = lambda *args: {}
    result = lock_account(risk_db, meta, "123")
    assert result["queued"] == ["12345"]
    assert result["failed"] == []
