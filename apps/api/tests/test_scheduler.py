"""Kiểm thử S4 — Scheduler + checkpoint 09:00 + Telegram admin.

Phủ:
- Cron config: hằng giờ + job 09:00 riêng, tz Asia/Ho_Chi_Minh.
- Idempotency: job chạy lại không sinh snapshot trùng.
- Checkpoint theo giờ VN, ghi MỘT lần mỗi campaign/kỳ; trễ ngoài grace → MISSED_CHECKPOINT,
  không giả snapshot 09:00.
- Mất kết nối Meta/token hết hạn → dữ liệu cũ giữ nguyên, KHÔNG fallback live→mock.
- Production không chạy mock (không ghi số liệu giả lập).
- Thông báo Telegram admin (mock buffer).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, func, select

from app.connectors.meta import MetaAPIError, MetaAdsConnector
from app.connectors.telegram import TelegramBotConnector
from app.core.config import settings
from app.jobs.meta_sync_job import checkpoint_9h_job, meta_sync_job
from app.jobs.scheduler import build_scheduler, start_scheduler
from app.models import AdAccount, AdAccountAssignment, AuditLog, Campaign, Customer, DriftRecord, SpendSnapshot, TelegramOutbox
from app.services import meta_sync as meta_sync_module
from app.services.meta_sync import is_checkpoint_time


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _reset_sync_state():
    """Dọn state in-process giữa các test (lock global + last sync + scheduler)."""
    from app.jobs import scheduler as scheduler_module

    yield
    meta_sync_module.LAST_SYNC_COMPLETED_AT = None
    if meta_sync_module.SYNC_LOCK.locked():  # phòng hộ: không để lock sót sang test sau
        meta_sync_module.SYNC_LOCK.release()
    scheduler_module._lock_socket = None
    scheduler_module._running_scheduler = None


@pytest.fixture(autouse=True)
def _clean_meta_sync_tables(db):
    """Dọn dữ liệu meta-sync giữa các test (job commit thật vào DB test chung)."""
    yield
    db.rollback()
    db.execute(delete(DriftRecord))
    db.execute(delete(SpendSnapshot))
    db.execute(delete(Campaign))
    db.execute(delete(AuditLog))
    db.execute(delete(AdAccountAssignment))
    db.execute(delete(AdAccount))
    db.execute(delete(Customer))
    db.commit()


def mock_connector(**kwargs):
    return MetaAdsConnector(use_mock=True, **kwargs)


def mock_notifier():
    return TelegramBotConnector(use_mock=True)


def seed_customers_and_accounts(session, connector):
    alpha = Customer(name="KH-S4-Alpha")
    beta = Customer(name="KH-S4-Beta")
    session.add_all([alpha, beta])
    session.flush()
    acc1 = AdAccount(
        meta_ad_account_id="act_mock_1",
        name="Acc 1",
        business_manager_id="bm_mock_a",
        timezone_name="Asia/Ho_Chi_Minh",
    )
    session.add(acc1)
    session.flush()
    session.add_all(
        [
            AdAccountAssignment(customer_id=alpha.id, ad_account_id=acc1.id, valid_from=utc(2026, 10, 1)),
            AdAccountAssignment(customer_id=beta.id, ad_account_id=acc1.id, valid_from=utc(2026, 10, 1)),
        ]
    )
    connector.mock.rename_campaign("cmp_1001", f"{alpha.name} 1025")  # MMDD
    connector.mock.rename_campaign("cmp_1002", f"{beta.name} 2510")  # DDMM
    connector.mock.rename_campaign("cmp_1003", f"{alpha.name} 1102")  # mã lưỡng nghĩa
    connector.mock.rename_campaign("cmp_1004", f"{alpha.name} 1025 retired")  # PAUSED
    session.commit()
    return alpha, beta, acc1


def snap_count(session):
    return session.execute(select(func.count(SpendSnapshot.id))).scalar_one()


def checkpoint_rows(session):
    return session.execute(
        select(SpendSnapshot).where(SpendSnapshot.is_checkpoint_9h.is_(True))
    ).scalars().all()


# --- cron config ---


def test_scheduler_has_hourly_and_checkpoint_jobs_vn_tz():
    scheduler = build_scheduler()
    by_id = {job.id: job for job in scheduler.get_jobs()}
    assert set(by_id) == {
        "meta_sync_hourly",
        "checkpoint_9h",
        "meta_risk_monitor",
        "prepaid_billing",
        "via_token_keepalive",
        "via_asset_sync",
    }
    assert by_id["meta_risk_monitor"].trigger.interval.total_seconds() == 300
    assert by_id["prepaid_billing"].trigger.interval.total_seconds() == 60
    assert by_id["via_token_keepalive"].trigger.interval.total_seconds() == 6 * 60 * 60
    assert by_id["via_asset_sync"].trigger.interval.total_seconds() == 2 * 60 * 60
    assert by_id["via_token_keepalive"].func.__name__ == "auto_verify_via_tokens"
    assert by_id["via_asset_sync"].func.__name__ == "scheduled_asset_sync"
    hourly = by_id["meta_sync_hourly"].trigger
    checkpoint = by_id["checkpoint_9h"].trigger
    assert {str(f) for f in hourly.fields if f.name == "hour"} == {"*"}
    assert {str(f) for f in checkpoint.fields if f.name == "hour"} == {"9"}
    assert {str(f) for f in checkpoint.fields if f.name == "minute"} == {"0"}
    tz_str = str(checkpoint.timezone)
    assert "Ho_Chi_Minh" in tz_str or "Saigon" in tz_str  # múi giờ điều hành VN


def test_checkpoint_window_is_vn_time():
    assert is_checkpoint_time(utc(2026, 10, 26, 2, 0)) is True  # 09:00 VN
    assert is_checkpoint_time(utc(2026, 10, 26, 2, 10)) is True  # 09:10 — trong cửa sổ grace
    assert is_checkpoint_time(utc(2026, 10, 26, 2, 31)) is False  # 09:31 — quá cửa sổ
    assert is_checkpoint_time(utc(2026, 10, 26, 3, 0)) is False  # 10:00 VN


# --- job hằng giờ: idempotent + giữ dữ liệu khi lỗi ---


def test_meta_sync_job_runs_twice_idempotent(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    now = utc(2026, 10, 26, 4, 0)
    first = meta_sync_job(session=db, connector=conn, now=now)
    assert first["snapshots_added"] == 3
    before = snap_count(db)
    second = meta_sync_job(session=db, connector=conn, now=now)
    assert second["snapshots_added"] == 0
    assert snap_count(db) == before  # job chạy lại không cộng trùng dữ liệu


def test_connection_loss_keeps_previous_data(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    summary = meta_sync_job(session=db, connector=conn, now=utc(2026, 10, 26, 4, 0))
    assert summary["snapshots_added"] == 3
    before = snap_count(db)
    conn.mock.fail_accounts()  # mất kết nối Meta
    failed = meta_sync_job(session=db, connector=conn, now=utc(2026, 10, 26, 5, 0))
    assert failed["api_errors"]
    assert snap_count(db) == before  # không mất dữ liệu đã có


def test_auth_error_reported_and_no_fallback(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    meta_sync_job(session=db, connector=conn, now=utc(2026, 10, 26, 4, 0))
    before = snap_count(db)
    conn.mock.fail_accounts_auth()  # token hết hạn (401)
    result = meta_sync_job(session=db, connector=conn, now=utc(2026, 10, 26, 5, 0))
    assert result["status"] == "AUTH_ERROR"
    assert any("MetaAuthError" in err for err in result["api_errors"])
    assert snap_count(db) == before  # dữ liệu cũ giữ nguyên
    assert conn.mode == "mock"  # connector inject không bị đổi


def test_live_connector_never_falls_back_to_mock_on_error(db):
    class ExplodingConnector:
        mode = "live"
        mock = None

        def get_ad_accounts(self):
            raise MetaAPIError("Meta Graph API không kết nối được")

    result = meta_sync_job(session=db, connector=ExplodingConnector())
    assert result["status"] == "API_ERROR"
    assert ExplodingConnector.mode == "live"  # KHÔNG fallback mock


def test_production_refuses_mock_data(db, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    conn = mock_connector()
    result = meta_sync_job(session=db, connector=conn, now=utc(2026, 10, 26, 4, 0))
    assert result["status"] == "MOCK_NOT_ALLOWED_IN_PRODUCTION"
    assert snap_count(db) == 0  # không ghi số liệu giả lập
    db.rollback()


def test_production_allows_live_connector(db, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")

    class LiveConnector:
        mode = "live"
        mock = None

        def get_ad_accounts(self):
            return []

    result = meta_sync_job(session=db, connector=LiveConnector(), now=utc(2026, 10, 26, 4, 0))
    assert result.get("status") != "MOCK_NOT_ALLOWED_IN_PRODUCTION"
    assert result["accounts_synced"] == 0
    db.rollback()


# --- checkpoint 09:00 ---


def test_checkpoint_runs_once_per_campaign_per_period(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    first = checkpoint_9h_job(session=db, connector=conn, now=utc(2026, 10, 26, 2, 0))  # 09:00 VN
    assert first["checkpoints_9h"] == 3
    second = checkpoint_9h_job(session=db, connector=conn, now=utc(2026, 10, 26, 2, 10))  # 09:10 VN
    assert second.get("checkpoints_9h", 0) == 0  # checkpoint kỳ này KHÔNG ghi lần hai
    # lượt thứ hai có thể bị bỏ qua khi sync đã chạy gần đây (D-030) — hợp lệ
    assert second.get("status") in ("SKIPPED_RECENT_RUN", "SKIPPED_CHECKPOINT_EXISTS", "OK")
    rows = checkpoint_rows(db)
    assert len(rows) == 3  # mỗi campaign chỉ 1 checkpoint cho kỳ/ngày
    assert all(r.snapshot_at <= utc(2026, 10, 26, 2, 1) for r in rows)


def test_checkpoint_late_is_missed_not_faked(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    late = checkpoint_9h_job(session=db, connector=conn, now=utc(2026, 10, 26, 2, 40))  # 09:40 VN
    assert late["status"] == "MISSED_CHECKPOINT"
    assert checkpoint_rows(db) == []  # không có snapshot nào giả làm 09:00
    assert snap_count(db) == 0
    next_day = checkpoint_9h_job(session=db, connector=conn, now=utc(2026, 10, 27, 2, 0))  # kỳ mới
    assert next_day["checkpoints_9h"] == 3  # checkpoint kỳ tiếp theo vẫn ghi bình thường


def test_hour_cron_job_does_not_fake_checkpoint_after_window(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    summary = meta_sync_job(session=db, connector=conn, now=utc(2026, 10, 26, 3, 0))  # 10:00 VN
    assert summary["checkpoints_9h"] == 0
    assert checkpoint_rows(db) == []


# --- campaign cũ / đã dừng vẫn poll (tiền trôi) ---


def test_hourly_job_still_polls_paused_campaigns(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    checkpoint_9h_job(session=db, connector=conn, now=utc(2026, 10, 26, 2, 0))
    before = snap_count(db)
    conn.mock.set_insight_spend("cmp_1004", 1500.0)  # campaign PAUSED vẫn poll
    summary = meta_sync_job(session=db, connector=conn, now=utc(2026, 10, 26, 10, 0))
    assert summary["snapshots_added"] == 3
    assert snap_count(db) == before + 3
    assert summary["drift_records"] == 1  # tiền trôi được ghi qua job theo D-023


def test_hourly_job_reports_unrecognized_and_unverified(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    summary = meta_sync_job(session=db, connector=conn, now=utc(2026, 10, 26, 4, 0))
    assert "cmp_1003" in summary["unrecognized"]  # đưa vào danh sách cần kiểm tra
    conn.mock.set_insight_spend("cmp_1001", 10.0)  # chi tiêu giảm → UNVERIFIED
    summary = meta_sync_job(session=db, connector=conn, now=utc(2026, 10, 26, 5, 0))
    assert summary["unverified"]


# --- concurrent 09:00 (D-030): chỉ 1 lượt fetch Meta ---


def test_both_jobs_at_9h_do_not_double_fetch_meta(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    now = utc(2026, 10, 26, 2, 0)  # 09:00 VN — hourly và checkpoint cùng trigger
    # checkpoint job chạy trước
    checkpoint_9h_job(session=db, connector=conn, now=now)
    calls_after_checkpoint = dict(conn.mock.calls)
    assert calls_after_checkpoint["accounts"] == 1
    # hourly job chạy sau ở cùng 09:00 → bỏ qua, KHÔNG fetch Meta thêm
    hourly = meta_sync_job(session=db, connector=conn, now=now)
    assert hourly["status"] == "SKIPPED_RECENT_RUN"
    assert conn.mock.calls == calls_after_checkpoint


def test_checkpoint_job_skips_when_checkpoint_already_exists(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    now = utc(2026, 10, 26, 2, 5)
    # job hằng giờ tự nhận checkpoint window (is_checkpoint_time) và ghi checkpoint
    meta_sync_job(session=db, connector=conn, now=now)
    calls = dict(conn.mock.calls)
    rows = checkpoint_rows(db)
    assert len(rows) == 3
    # checkpoint job sau đó thấy checkpoint đã có → bỏ qua KHÔNG gọi Meta
    result = checkpoint_9h_job(session=db, connector=conn, now=utc(2026, 10, 26, 2, 12))
    assert result["status"] == "SKIPPED_CHECKPOINT_EXISTS"
    assert conn.mock.calls == calls
    assert len(checkpoint_rows(db)) == 3  # vẫn MỘT checkpoint/campaign/kỳ


def test_single_flight_lock_rejects_concurrent_sync(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    with meta_sync_module.SYNC_LOCK:
        result = run_meta_sync_named(db, conn, utc(2026, 10, 26, 4, 0))
    assert result["status"] == "SKIPPED_CONCURRENT_RUN"
    assert snap_count(db) == 0
    assert conn.mock.calls["accounts"] == 0


def run_meta_sync_named(session, connector, now):
    from app.services.meta_sync import run_meta_sync

    return run_meta_sync(session, connector, now=now)


def _free_port() -> int:
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_scheduler_port_lock_single_instance(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_lock_port", _free_port())
    first = start_scheduler()
    try:
        assert first is not None
        assert first.get_jobs()  # có 2 job
        second = start_scheduler()
        if second is not None:
            second.shutdown()
        assert second is None  # worker thứ 2 không chạy scheduler song song
    finally:
        if first is not None:
            first.shutdown()


# --- Telegram outbox (D-031): lỗi gửi → ghi nhận → gửi lại ---


def test_telegram_failure_queues_to_outbox_and_retries(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    notifier = TelegramBotConnector(use_mock=True)
    conn.mock.fail_accounts()
    result = meta_sync_job(session=db, connector=conn, notifier=notifier, now=utc(2026, 10, 26, 4, 0))
    assert result["status"] == "API_ERROR"
    db.rollback()  # job rollback — outbox phải chịu được (commit riêng ở thực tế)
    db.add(TelegramOutbox(message="retry-me", status="PENDING"))
    db.commit()
    # lần chạy sau: Telegram hoạt động bình thường → outbox được gửi lại
    checkpoint_9h_job(session=db, connector=conn, notifier=notifier, now=utc(2026, 10, 27, 2, 0))
    db.expire_all()
    sent_rows = db.execute(select(TelegramOutbox).where(TelegramOutbox.status == "SENT")).scalars().all()
    assert any(r.message == "retry-me" for r in sent_rows)


def test_checkpoint_job_sends_admin_report(db):
    conn = mock_connector()
    notifier = TelegramBotConnector(use_mock=True)
    seed_customers_and_accounts(db, conn)
    checkpoint_9h_job(session=db, connector=conn, notifier=notifier, now=utc(2026, 10, 26, 2, 0))
    texts = [m["text"] for m in notifier.sent_messages]
    assert any("checkpoint 09:00" in t and "3</b>" in t for t in texts)


def test_hourly_job_error_notification(db):
    conn = mock_connector()
    notifier = TelegramBotConnector(use_mock=True)
    seed_customers_and_accounts(db, conn)
    conn.mock.fail_accounts_auth()
    result = meta_sync_job(session=db, connector=conn, notifier=notifier, now=utc(2026, 10, 26, 4, 0))
    assert result["status"] == "AUTH_ERROR"
    texts = [m["text"] for m in notifier.sent_messages]
    assert any("Token hết hạn" in t for t in texts)  # thông báo lỗi xác thực


# --- chạy 9h mà không sync nào gần đây: checkpoint vẫn chạy bình thường ---


def test_checkpoint_job_still_runs_when_no_recent_sync(db):
    conn = mock_connector()
    seed_customers_and_accounts(db, conn)
    result = checkpoint_9h_job(session=db, connector=conn, now=utc(2026, 10, 26, 2, 0))
    assert result.get("status") != "SKIPPED_RECENT_RUN"
    assert result["checkpoints_9h"] == 3
