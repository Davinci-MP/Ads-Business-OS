"""Kiểm thử tác vụ kiểm tra token và tự đồng bộ tài sản VIA."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.jobs.asset_sync import scheduled_asset_sync
from app.jobs.token_keepalive import TokenValidationResult, auto_verify_via_tokens, validate_via_token
from app.models.via import SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.via_manager import encrypt_via_credentials, sync_via_all_assets


def _factory(db):
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _isolate_via_job_rows(db):
    """Không để trạng thái VIA từ test khác lọt vào truy vấn batch."""
    existing = {via.id: via.token_status for via in db.scalars(select(ViaProfile)).all()}
    for via_id in existing:
        db.get(ViaProfile, via_id).token_status = "NONE"
    db.commit()
    yield
    db.rollback()
    for via in db.scalars(select(ViaProfile)).all():
        if via.id not in existing:
            db.delete(via)
        else:
            via.token_status = existing[via.id]
    db.commit()


def _add_via(
    db,
    uid: str,
    *,
    token_status: str = "ACTIVE",
    last_token_refresh=None,
    token_expires_at=None,
) -> ViaProfile:
    via = ViaProfile(
        uid=uid,
        profile_name=f"VIA {uid}",
        profile_dir=f"profiles/{uid}",
        user_agent="Trình duyệt kiểm thử",
        encrypted_credentials=encrypt_via_credentials(
            {"access_token": "EAA_TEST_FIXTURE_NOT_A_REAL_TOKEN_12345", "cookie": "cookie-kiem-thu"}
        ),
        token_status=token_status,
        last_token_refresh=last_token_refresh,
        token_expires_at=token_expires_at,
    )
    db.add(via)
    db.commit()
    return via


def test_keepalive_checks_active_tokens_warns_near_expiry_and_preserves_credentials(db, monkeypatch):
    now = datetime(2026, 11, 9, 3, 0, tzinfo=timezone.utc)
    active = _add_via(db, "via-active", last_token_refresh=now - timedelta(hours=2))
    expiring = _add_via(db, "via-expiring", token_expires_at=now + timedelta(hours=12))
    inactive = _add_via(db, "via-inactive", token_status="EXPIRED")
    old_credentials = active.encrypted_credentials
    graph_calls = 0

    def fake_get(*args, **kwargs):
        nonlocal graph_calls
        graph_calls += 1
        return httpx.Response(200, json={"id": "uid-kiem-thu"})

    monkeypatch.setattr("app.jobs.token_keepalive.httpx.get", fake_get)
    monkeypatch.setattr(settings, "via_token_jitter_min_seconds", 0.0)
    monkeypatch.setattr(settings, "via_token_jitter_max_seconds", 0.0)
    result = auto_verify_via_tokens(
        session_factory=_factory(db),
        validator=validate_via_token,
        now=now,
        sleep_fn=lambda _: None,
    )

    db.expire_all()
    assert result == {"status": "OK", "checked": 2, "active": 1, "failed": 1, "skipped": 0}
    assert graph_calls == 2
    assert db.get(ViaProfile, active.id).last_token_refresh == now
    assert db.get(ViaProfile, active.id).encrypted_credentials == old_credentials
    assert db.get(ViaProfile, expiring.id).token_status == "WARNING"
    assert db.get(ViaProfile, expiring.id).last_token_refresh == now
    assert db.get(ViaProfile, inactive.id).token_status == "EXPIRED"


def test_keepalive_isolates_failure_per_via(db, monkeypatch):
    first = _add_via(db, "via-loi")
    second = _add_via(db, "via-het-han")
    third = _add_via(db, "via-tiep-tuc")

    def validator(via):
        if via.id == first.id:
            raise RuntimeError("lỗi kiểm thử")
        if via.id == second.id:
            return TokenValidationResult(False, "EXPIRED", "Token đã hết hạn")
        return TokenValidationResult(True, "ACTIVE", "Token hợp lệ")

    monkeypatch.setattr(settings, "via_token_jitter_min_seconds", 0.0)
    monkeypatch.setattr(settings, "via_token_jitter_max_seconds", 0.0)
    result = auto_verify_via_tokens(
        session_factory=_factory(db),
        validator=validator,
        sleep_fn=lambda _: None,
    )

    db.expire_all()
    assert result["checked"] == 3
    assert result["active"] == 1
    assert result["failed"] == 2
    assert db.get(ViaProfile, first.id).token_status == "ACTIVE"
    assert db.get(ViaProfile, second.id).token_status == "EXPIRED"
    assert db.get(ViaProfile, third.id).token_status == "ACTIVE"


def test_asset_sync_upserts_and_marks_missing_assets_inactive(db):
    via = _add_via(db, "via-assets")
    db.add_all(
        [
            SyncedBM(bm_id="bm-keep", via_profile_id=via.id, name="BM cũ", status="ACTIVE"),
            SyncedBM(bm_id="bm-missing", via_profile_id=via.id, name="BM mất quyền", status="ACTIVE"),
            SyncedAdAccount(
                via_profile_id=via.id,
                act_id="act-keep",
                name="TKQC cũ",
                status_dot="LIVE",
                account_status=1,
            ),
            SyncedAdAccount(
                via_profile_id=via.id,
                act_id="act-missing",
                name="TKQC mất quyền",
                status_dot="LIVE",
                account_status=1,
            ),
            SyncedPage(via_profile_id=via.id, page_id="page-keep", name="Trang cũ", is_published=True),
            SyncedPage(via_profile_id=via.id, page_id="page-missing", name="Trang mất quyền", is_published=True),
        ]
    )
    db.commit()

    result = sync_via_all_assets(
        db,
        via.id,
        mock_mode=True,
        mark_missing_inactive=True,
        allow_cookie_token_recovery=False,
        mock_data={
            "bms": [{"bm_id": "bm-keep", "name": "BM mới", "status": "ACTIVE"}],
            "personal_accounts": [
                {
                    "act_id": "act-keep",
                    "name": "TKQC đã cập nhật",
                    "status_dot": "LIVE",
                    "account_status": 1,
                    "balance": 120,
                    "currency": "USD",
                },
                {
                    "act_id": "act-new",
                    "name": "TKQC mới",
                    "status_dot": "LIVE",
                    "account_status": 1,
                    "balance": 20,
                    "currency": "USD",
                },
            ],
            "bm_accounts": [],
            "pages": [
                {"page_id": "page-keep", "name": "Trang mới", "is_published": True},
                {"page_id": "page-new", "name": "Trang vừa cấp", "is_published": True},
            ],
        },
    )

    assert result["success"] is True
    assert db.query(SyncedBM).filter_by(bm_id="bm-keep", via_profile_id=via.id).one().name == "BM mới"
    assert db.query(SyncedBM).filter_by(bm_id="bm-missing", via_profile_id=via.id).one().status == "DISCONNECTED"
    assert db.query(SyncedAdAccount).filter_by(act_id="act-keep").one().balance == 120
    missing_account = db.query(SyncedAdAccount).filter_by(act_id="act-missing").one()
    assert missing_account.status_dot == "DIE"
    assert missing_account.disable_reason == "DISCONNECTED"
    assert db.query(SyncedAdAccount).filter_by(act_id="act-new").one()
    assert db.query(SyncedPage).filter_by(page_id="page-missing", via_profile_id=via.id).one().is_published is False
    assert db.query(SyncedPage).filter_by(page_id="page-new", via_profile_id=via.id).one()


def test_scheduled_asset_sync_continues_after_one_via_fails(db):
    first = _add_via(db, "via-sync-1")
    second = _add_via(db, "via-sync-2")
    calls: list[tuple[int, bool, bool]] = []

    def fake_sync(*, session, via_id, allow_cookie_token_recovery, mark_missing_inactive):
        calls.append((via_id, allow_cookie_token_recovery, mark_missing_inactive))
        if via_id == first.id:
            raise RuntimeError("lỗi đồng bộ kiểm thử")
        session.get(ViaProfile, via_id).last_synced_at = datetime.now(timezone.utc)
        session.commit()
        return {"success": True, "status": "ACTIVE"}

    result = scheduled_asset_sync(session_factory=_factory(db), sync_callable=fake_sync)

    assert result == {"status": "OK", "total": 2, "success": 1, "failed": 1}
    assert calls == [(first.id, False, True), (second.id, False, True)]
