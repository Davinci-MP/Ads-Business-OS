"""Token Meta trên server: lấy từ VIA đã cấp quyền OAuth; ngoài local không ghi dữ liệu mock."""

import itertools

import httpx
import pytest
from sqlalchemy import func, select

from app.connectors.meta import MetaAdsConnector
from app.core.config import settings
from app.jobs.meta_sync_job import checkpoint_9h_job, meta_sync_job
from app.models import SpendSnapshot
from app.models.via import SyncedAdAccount, ViaProfile
from app.services import meta_tokens
from app.services.meta_tokens import NO_META_TOKEN_STATUS, build_job_connector, mock_blocked
from app.services.via_manager import encrypt_via_credentials

REAL_VIA_TOKEN_SOURCES = meta_tokens.via_token_sources  # bản gốc, trước khi conftest tắt
_seq = itertools.count(1)


def _via(db, token, status="ACTIVE", acts=()):
    n = next(_seq)
    via = ViaProfile(
        uid=f"77000000{n:04d}",
        profile_name=f"VIA token {n}",
        profile_dir=f"profiles/tok{n}",
        user_agent="UA test",
        encrypted_credentials=encrypt_via_credentials({"access_token": token}),
        token_status=status,
    )
    db.add(via)
    db.flush()
    for act in acts:
        db.add(SyncedAdAccount(via_profile_id=via.id, act_id=act, name=f"TK {act}"))
    db.commit()
    return via


@pytest.fixture()
def real_sources(monkeypatch):
    monkeypatch.setattr(meta_tokens, "via_token_sources", REAL_VIA_TOKEN_SOURCES)
    monkeypatch.delenv("ADSOS_META_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ADSOS_META_TOKEN_MAP", raising=False)


def test_via_token_sources_chi_lay_via_active_va_gan_act_id(db, real_sources):
    _via(db, "EAAQtokenViaMot1", acts=["881001", "act_881002"])
    _via(db, "EAAQtokenHetHan2", status="EXPIRED", acts=["881003"])
    token_map, discovery = meta_tokens.via_token_sources(db)
    assert token_map["act_881001"] == "EAAQtokenViaMot1"
    assert token_map["act_881002"] == "EAAQtokenViaMot1"
    assert "act_881003" not in token_map
    assert "EAAQtokenViaMot1" in discovery
    assert "EAAQtokenHetHan2" not in discovery


def test_build_job_connector_live_khi_co_via_active(db, real_sources):
    _via(db, "EAAQtokenViaLive3", acts=["882001"])
    connector = build_job_connector(db)
    assert connector.mode == "live"
    assert connector.token_for_source("act_882001") == "EAAQtokenViaLive3"


def test_connector_liet_ke_tai_khoan_theo_tung_token_via_va_dinh_tuyen_token():
    seen = []

    def handler(request):
        seen.append(request)
        token = request.url.params.get("access_token")
        if request.url.path.endswith("/me/adaccounts"):
            act = {"tok-a": "act_1", "tok-b": "act_2"}[token]
            return httpx.Response(200, json={"data": [{"id": act, "name": act, "currency": "USD"}]})
        return httpx.Response(200, json={"data": []})

    connector = MetaAdsConnector(
        discovery_tokens=["tok-a", "tok-b", "tok-a"], use_mock=False, transport=httpx.MockTransport(handler)
    )
    accounts = connector.get_ad_accounts()
    assert [a["meta_ad_account_id"] for a in accounts] == ["act_1", "act_2"]
    connector.get_account_campaigns("act_2")
    assert seen[-1].url.params["access_token"] == "tok-b"
    assert sum(r.url.path.endswith("/me/adaccounts") for r in seen) == 2  # token trùng chỉ gọi 1 lần


def test_connector_bm_dung_duong_dan_business_id_khong_co_act():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": []})

    connector = MetaAdsConnector(
        token_map={"1234567890": "tok-bm"}, use_mock=False, transport=httpx.MockTransport(handler)
    )
    connector.get_ad_accounts()
    assert seen[0].url.path.endswith("/1234567890/owned_ad_accounts")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_ngoai_local_mock_bi_chan(env, monkeypatch):
    monkeypatch.setattr(settings, "app_env", env)
    assert mock_blocked(MetaAdsConnector(use_mock=True))
    monkeypatch.setattr(settings, "app_env", "local")
    assert not mock_blocked(MetaAdsConnector(use_mock=True))


def test_job_staging_khong_token_khong_ghi_du_lieu_mock(db, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "staging")
    before = db.execute(select(func.count(SpendSnapshot.id))).scalar_one()
    result = meta_sync_job(session=db, connector=MetaAdsConnector(use_mock=True))
    assert result["status"] == NO_META_TOKEN_STATUS
    result9 = checkpoint_9h_job(session=db, connector=MetaAdsConnector(use_mock=True))
    assert result9["status"] == NO_META_TOKEN_STATUS
    assert db.execute(select(func.count(SpendSnapshot.id))).scalar_one() == before


def test_api_run_sync_staging_khong_token_tra_409(monkeypatch, db):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    monkeypatch.setattr(settings, "app_env", "staging")
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).post("/api/v1/meta-sync/run")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code in (401, 403, 409)
    if response.status_code == 409:
        assert "Cấp quyền Facebook" in response.json()["detail"]
