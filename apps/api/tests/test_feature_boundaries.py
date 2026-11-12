from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.connectors.meta import MetaAdsConnector
from app.connectors.telegram import TelegramBotConnector
from app.main import app
from app.models import Base, AdAccount, MetaAccountRisk
from app.services.meta_campaign_builder import CampaignCreationRequest, build_and_create_campaign, toggle_campaign_status
from app.services.telegram_bot import TelegramBotAgent


def test_emergency_lock_cannot_be_overridden():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AdAccount(meta_ad_account_id="act_mock_1", name="Thử nghiệm", timezone_name="UTC", allow_violated_accounts=True))
        db.add(MetaAccountRisk(account_id="act_mock_1", locked=True))
        db.commit()
        with MetaAdsConnector(use_mock=True) as meta:
            request = CampaignCreationRequest(ad_account_id="act_mock_1", campaign_name="Khóa khẩn cấp", daily_budget=Decimal("1000"))
            with pytest.raises(ValueError, match="khóa an toàn"):
                build_and_create_campaign(db, meta, request)
            with pytest.raises(ValueError, match="khóa an toàn"):
                toggle_campaign_status(db, meta, "cmp_1001", "ACTIVE")
            with pytest.raises(ValueError, match="Chưa xác minh"):
                toggle_campaign_status(db, meta, "unknown_campaign", "ACTIVE")
    engine.dispose()


def test_financial_and_meta_admin_endpoints_reject_remote_clients():
    client = TestClient(app, client=("192.0.2.1", 1234))
    for path in ("/api/v1/meta-risk", "/api/v1/prepaid", "/api/v1/meta/accounts/billing"):
        assert client.get(path).status_code == 403


def test_new_validation_errors_are_vietnamese():
    client = TestClient(app)
    response = client.post("/api/v1/prepaid/transactions", json={})
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Dữ liệu không hợp lệ")


def test_lock_command_requires_admin_chat():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    tg = TelegramBotConnector(admin_chat_id="100", allowed_chat_ids=["200"], use_mock=True)
    with Session(engine) as db, MetaAdsConnector(use_mock=True) as meta:
        agent = TelegramBotAgent(meta_connector=meta, telegram_connector=tg)
        result = agent.process_update(db, {"message": {"chat": {"id": 200}, "text": "/khoatkn act_mock_1"}})
        assert result["status"] == "rejected"
        assert db.get(MetaAccountRisk, "act_mock_1") is None
    engine.dispose()
