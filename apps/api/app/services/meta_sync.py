"""Service đồng bộ chi tiêu Meta — theo CAMPAIGN_RULES.md.

Bất biến:
- Chi tiêu = tổng tích lũy (insights lifetime). Append-only snapshot, không cộng dồn.
- Unique key (campaign_id, snapshot_at) → job idempotent.
- Checkpoint 09:00 Asia/Ho_Chi_Minh → is_checkpoint_9h = true (D-009).
- Chi tiêu monotonic: snapshot mới < snapshot VERIFIED mới nhất → ghi bản UNVERIFIED,
  không đè số đã xác nhận (D-011).
- Campaign PAUSED/ENDED vẫn poll → tiền trôi = hiện tại − mốc 09:00 (D-023).
- Nhận diện campaign theo D-026: cả MMDD/DDMM, đối chiếu tên khách + account +
  campaign id + kỳ báo cáo; không khớp → UNRECOGNIZED, không tự gán khách.
- CHỈ ĐỌC từ Meta; không ghi Google Sheets (D-027/D-024).
"""

from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.meta import MetaAdsConnector, MetaAPIError
from app.core.config import settings
from app.models import AuditLog
from app.models.ad_account import ACCOUNT_ACTIVE, AdAccount, AdAccountAssignment
from app.models.campaign import (
    RECOGNITION_CONFIRMED,
    RECOGNITION_UNRECOGNIZED,
    Campaign,
)
from app.models.customer import Customer, utcnow
from app.models.spend import DATA_UNVERIFIED, DATA_VERIFIED, DriftRecord, SpendSnapshot
from app.services.finance import compute_drift
from app.services.recon import get_checkpoint_spend_snapshot, get_current_spend_snapshot

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

STOPPED_STATUSES = {"PAUSED", "ENDED"}
# Mã ngày trong tên campaign (D-026 + D-039): 1025/2510 (4 số liền) hoặc 10/25, 25/10 (2/2).
# Word boundary: KHÔNG nhận số 4 chữ số nằm giữa ký tự chữ+số khác (tránh mã KH/TK 6 chữ số).
_DATE_CODE_RE = re.compile(r"(?<![0-9/])(\d{4}|(\d{2})[/](\d{2}))(?![0-9/])")

# Single-flight lock (D-030): chống chạy đồng thời 2 lượt sync cùng campaign/kỳ
SYNC_LOCK = threading.Lock()
LAST_SYNC_COMPLETED_AT: Optional[datetime] = None
RECENT_RUN_WINDOW_MINUTES = 15


def _vn_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(VN_TZ).date()


def is_recent_sync_completed(now: datetime, window_minutes: int = RECENT_RUN_WINDOW_MINUTES) -> bool:
    """Đúng 09:00 hai job (hourly + checkpoint) cùng chạy → lượt sau bỏ qua khi
    một lượt sync đã hoàn thành rất gần đây (tránh fetch Meta trùng lặp, D-030)."""
    global LAST_SYNC_COMPLETED_AT
    if LAST_SYNC_COMPLETED_AT is None:
        return False
    elapsed = (now - LAST_SYNC_COMPLETED_AT).total_seconds()
    return 0 <= elapsed < window_minutes * 60


def checkpoint_exists_for(session: Session, at: datetime) -> bool:
    """Đã có checkpoint 09:00 cho kỳ/ngày VN của `at` chưa (dùng chặn fetch trùng)."""
    target = _vn_date(at)
    rows = session.execute(
        select(SpendSnapshot).where(SpendSnapshot.is_checkpoint_9h.is_(True))
    ).scalars().all()
    return any(_vn_date(r.snapshot_at) == target for r in rows)


def is_checkpoint_time(now: datetime) -> bool:
    """09:00 giờ VN, trong cửa sổ grace (mặc định 15 phút — xem Q-013).

    Quá cửa sổ: nếu còn chạy trễ → KHÔNG dùng dữ liệu lấy sau để giả làm snapshot 09:00
    (đánh dấu MISSED_CHECKPOINT ở job wrapper, D-009/CAMPAIGN_RULES §3).
    """
    vn = now.astimezone(VN_TZ)
    return vn.hour == 9 and vn.minute <= settings.checkpoint_grace_minutes


@dataclass
class SyncSummary:
    accounts_synced: int = 0
    campaigns_synced: int = 0
    snapshots_added: int = 0
    checkpoints_9h: int = 0
    unverified: list[str] = field(default_factory=list)
    api_errors: list[str] = field(default_factory=list)
    drift_records: int = 0
    unrecognized: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "accounts_synced": self.accounts_synced,
            "campaigns_synced": self.campaigns_synced,
            "snapshots_added": self.snapshots_added,
            "checkpoints_9h": self.checkpoints_9h,
            "unverified": self.unverified,
            "api_errors": self.api_errors,
            "drift_records": self.drift_records,
            "unrecognized": self.unrecognized,
        }


# --- nhận diện campaign (D-026) ---


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    folded = folded.replace("đ", "d").replace("Đ", "D")
    return " ".join(folded.lower().split())


def extract_report_dates(name: str) -> Optional[date]:
    """Rút mã ngày khỏi tên campaign — hỗ trợ 4 dạng (D-026 + D-039):

    - `1025` (MMDD) và `2510` (DDMM): 4 số liền — cả 2 cách đọc hợp lệ khi cùng
      cho ra 1 ngày thì chấp nhận; 2 ngày khác nhau → None (mơ hồ, không tự ghép).
    - `10/25` (MM/DD) và `25/10` (DD/MM): có dấu `/` — phân tách mặc nhiên, chỉ
      đọc đúng định dạng theo vị trí; MM/DD và DD/MM cho cùng ngày → chấp nhận.

    Chỉ nhận token ngày khi: nhóm số là 4 chữ số liễng (word boundary, tránh
    mã TK/khác 6 chữ số) hoặc 2/2 với `/`; KHÔNG tự xác nhận khi tên mơ hồ.

    Trả về:
    - date: xác định được duy nhất 1 ngày hợp lệ.
    - None: không có mã, hoặc 2 cách đọc hợp lệ khác nhau → không tự ghép (D-026).
    """
    candidates: set[date] = set()
    year = datetime.now(timezone.utc).year
    for match in _DATE_CODE_RE.finditer(name):
        token = match.group(1)
        if "/" in token:
            mm_s, dd_s = token.split("/")
            try:
                candidates.add(date(year, int(mm_s), int(dd_s)))  # MM/DD
            except ValueError:
                pass
            try:
                candidates.add(date(year, int(dd_s), int(mm_s)))  # DD/MM cũng đọc — cùng ngày thì ok
            except ValueError:
                pass
        else:
            mm, dd = int(token[:2]), int(token[2:])
            try:
                candidates.add(date(year, mm, dd))  # MMDD
            except ValueError:
                pass
            try:
                candidates.add(date(year, dd, mm))  # DDMM
            except ValueError:
                pass
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def find_customer_by_name(campaign_name: str, customers: list[Customer]) -> Optional[Customer]:
    """Tên khách phải xuất hiện trong tên campaign; trùng >1 khách → không ghép."""
    normalized = normalize_name(campaign_name)
    matches = [c for c in customers if normalize_name(c.name) and normalize_name(c.name) in normalized]
    if len(matches) != 1:
        return None
    return matches[0]


def _account_assigned_to(session: Session, account_id: int, customer_id: int) -> bool:
    assignment = session.execute(
        select(AdAccountAssignment)
        .where(
            AdAccountAssignment.ad_account_id == account_id,
            AdAccountAssignment.customer_id == customer_id,
            AdAccountAssignment.valid_to.is_(None),
        )
    ).scalar_one_or_none()
    return assignment is not None


def recognize_campaign(
    session: Session,
    campaign: Campaign,
    account: AdAccount,
    customers: list[Customer],
) -> Campaign:
    """Chỉ ghi nhận (CONFIRMED) khi khớp đủ 4 tiêu chí D-026. Không bao giờ gán sai khách."""
    if campaign.recognition_status == RECOGNITION_CONFIRMED and campaign.customer_id is not None:
        return campaign  # đã xác nhận — không tự đổi chủ sở hữu
    if campaign.ad_account_id != account.id:
        # Tiêu chí Ad Account ID: campaign phải trực thuộc đúng account đang poll.
        campaign.recognition_status = RECOGNITION_UNRECOGNIZED
        return campaign
    report_day = extract_report_dates(campaign.name)
    if report_day is None:
        campaign.recognition_status = RECOGNITION_UNRECOGNIZED
        campaign.customer_id = None
        campaign.report_period_start = None
        campaign.report_period_end = None
        return campaign
    customer = find_customer_by_name(campaign.name, customers)
    if customer is None or not _account_assigned_to(session, account.id, customer.id):
        campaign.recognition_status = RECOGNITION_UNRECOGNIZED
        campaign.customer_id = None
        campaign.report_period_start = None
        campaign.report_period_end = None
        return campaign
    campaign.recognition_status = RECOGNITION_CONFIRMED
    campaign.customer_id = customer.id
    campaign.report_period_start = report_day
    campaign.report_period_end = report_day
    session.add(
        AuditLog(
            actor="meta_sync",
            action="campaign_confirmed",
            entity_type="campaign",
            entity_id=campaign.meta_campaign_id,
            detail={"customer_id": customer.id, "report_day": report_day.isoformat()},
        )
    )
    return campaign


# --- đồng bộ accounts / campaigns ---


def sync_ad_accounts(session: Session, connector: MetaAdsConnector, summary: SyncSummary) -> list[AdAccount]:
    try:
        meta_accounts = connector.get_ad_accounts()
    except Exception as exc:  # noqa: BLE001 — lỗi listing account là fatal cho lượt chạy
        if isinstance(exc, MetaAPIError):
            raise
        summary.api_errors.append(f"accounts: {type(exc).__name__}")
        return []
    result: list[AdAccount] = []
    for meta_account in meta_accounts:
        account = session.execute(
            select(AdAccount).where(AdAccount.meta_ad_account_id == meta_account["meta_ad_account_id"])
        ).scalar_one_or_none()
        if account is None:
            account = AdAccount(
                meta_ad_account_id=meta_account["meta_ad_account_id"],
                name=meta_account["name"],
                business_manager_id=meta_account.get("business_manager_id"),
                timezone_name=meta_account.get("timezone_name") or "UTC",
                status=ACCOUNT_ACTIVE,
            )
            session.add(account)
        else:
            # không xoá/không đổi id; chỉ cập nhật thông tin mô tả nếu Meta trả mới
            account.name = meta_account["name"]
            account.timezone_name = meta_account.get("timezone_name") or account.timezone_name
            if meta_account.get("business_manager_id"):
                account.business_manager_id = meta_account["business_manager_id"]
        result.append(account)
    session.flush()
    summary.accounts_synced = len(result)
    return result


def sync_campaigns_for_account(
    session: Session,
    connector: MetaAdsConnector,
    account: AdAccount,
    customers: list[Customer],
    summary: SyncSummary,
) -> list[Campaign]:
    try:
        meta_campaigns = connector.get_account_campaigns(account.meta_ad_account_id)
    except Exception as exc:  # noqa: BLE001 — lỗi listing campaign fatal cho lượt chạy
        if isinstance(exc, MetaAPIError):
            raise
        summary.api_errors.append(f"campaigns[{account.meta_ad_account_id}]: {type(exc).__name__}")
        return []
    result: list[Campaign] = []
    for meta_campaign in meta_campaigns:
        campaign = session.execute(
            select(Campaign).where(Campaign.meta_campaign_id == meta_campaign["meta_campaign_id"])
        ).scalar_one_or_none()
        if campaign is None:
            campaign = Campaign(
                meta_campaign_id=meta_campaign["meta_campaign_id"],
                ad_account_id=account.id,
                name=meta_campaign["name"],
                recognition_status=RECOGNITION_UNRECOGNIZED,
                meta_status=meta_campaign["status"],
            )
            session.add(campaign)
        else:
            campaign.name = meta_campaign["name"]
            campaign.meta_status = meta_campaign["status"]
        if meta_campaign["status"] in STOPPED_STATUSES and campaign.stopped_at is None:
            campaign.stopped_at = utcnow()
        recognize_campaign(session, campaign, account, customers)
        if campaign.recognition_status == RECOGNITION_UNRECOGNIZED:
            summary.unrecognized.append(campaign.meta_campaign_id)
        result.append(campaign)
    session.flush()
    summary.campaigns_synced += len(result)
    return result


# --- snapshot chi tiêu ---


def _existing_snapshot(session: Session, campaign_id: int, snapshot_at: datetime) -> Optional[SpendSnapshot]:
    return session.execute(
        select(SpendSnapshot).where(
            SpendSnapshot.campaign_id == campaign_id,
            SpendSnapshot.snapshot_at == snapshot_at,
        )
    ).scalar_one_or_none()


def snapshot_campaign_spend(
    session: Session,
    connector: MetaAdsConnector,
    campaign: Campaign,
    account: AdAccount,
    now: datetime,
    is_checkpoint_9h: bool,
    summary: SyncSummary,
) -> None:
    if campaign.customer_id is None:
        return  # UNRECOGNIZED → không tính tiền (CAMPAIGN_RULES §1)
    try:
        insights = connector.get_campaign_insights(account.meta_ad_account_id, campaign.meta_campaign_id)
    except Exception as exc:  # noqa: BLE001
        summary.api_errors.append(f"insights[{campaign.meta_campaign_id}]: {type(exc).__name__}")
        session.add(
            AuditLog(
                actor="meta_sync",
                action="spend_api_error",
                entity_type="campaign",
                entity_id=campaign.meta_campaign_id,
                detail={"error": type(exc).__name__, "at": now.isoformat()},
            )
        )
        return
    if insights is None:
        summary.api_errors.append(f"insights[{campaign.meta_campaign_id}]: empty")
        return
    spend = Decimal(insights["spend"])
    latest_verified = get_current_spend_snapshot(session, campaign.id)
    non_monotonic = latest_verified is not None and spend < Decimal(latest_verified.spend_amount)
    if non_monotonic:
        # D-011: không ghi đè số đã xác nhận → snapshot mới gắn UNVERIFIED, điều tra sau.
        data_status = DATA_UNVERIFIED
        summary.unverified.append(f"{campaign.meta_campaign_id}: {spend} < {latest_verified.spend_amount}")
    else:
        data_status = DATA_VERIFIED
    # Checkpoint 09:00 chỉ ghi MỘT lần mỗi campaign / mỗi kỳ (VN date) — đã có → append thường
    flag_9h = is_checkpoint_9h
    if flag_9h and get_checkpoint_spend_snapshot(session, campaign.id, now) is not None:
        flag_9h = False
    existing = _existing_snapshot(session, campaign.id, now)
    if existing is not None:
        if existing.data_status == DATA_UNVERIFIED and data_status == DATA_VERIFIED:
            # upgrade UNVERIFIED → VERIFIED: bản UNVERIFIED chưa từng được xác nhận
            existing.spend_amount = spend
        return  # idempotent: snapshot tại mốc này đã có
    snapshot = SpendSnapshot(
        campaign_id=campaign.id,
        snapshot_at=now,
        spend_amount=spend,
        currency=insights.get("currency") or "USD",
        source="META_API",
        is_checkpoint_9h=flag_9h,
        data_status=data_status,
    )
    session.add(snapshot)
    session.flush()
    summary.snapshots_added += 1
    if flag_9h:
        summary.checkpoints_9h += 1
        session.add(
            AuditLog(
                actor="meta_sync",
                action="checkpoint_9h_saved",
                entity_type="campaign",
                entity_id=campaign.meta_campaign_id,
                detail={"spend": str(spend), "at": now.isoformat()},
            )
        )


# --- tiền trôi (D-023) ---


def record_drift_after_sync(
    session: Session, connector: MetaAdsConnector, now: datetime, summary: SyncSummary
) -> int:
    """Campaign PAUSED/ENDED vẫn poll; drift = hiện tại − mốc 09:00 cùng kỳ (D-023)."""
    count = 0
    campaigns = session.execute(
        select(Campaign).where(Campaign.meta_status.in_(STOPPED_STATUSES))
    ).scalars().all()
    for campaign in campaigns:
        if campaign.customer_id is None:
            continue
        latest = get_current_spend_snapshot(session, campaign.id)
        checkpoint = get_checkpoint_spend_snapshot(session, campaign.id, now)
        if latest is None or checkpoint is None or latest.id == checkpoint.id:
            continue
        drift = compute_drift(Decimal(latest.spend_amount), Decimal(checkpoint.spend_amount))
        existing = session.execute(
            select(DriftRecord).where(
                DriftRecord.campaign_id == campaign.id,
                DriftRecord.checkpoint_snapshot_id == checkpoint.id,
            )
        ).scalar_one_or_none()
        if existing is None and drift == 0:
            continue  # không có tiền trôi — không tạo record mới
        if existing is None:
            session.add(
                DriftRecord(
                    campaign_id=campaign.id,
                    checkpoint_snapshot_id=checkpoint.id,
                    latest_snapshot_id=latest.id,
                    drift_amount=drift,
                    currency=latest.currency,
                )
            )
            session.add(
                AuditLog(
                    actor="meta_sync",
                    action="drift_recorded",
                    entity_type="campaign",
                    entity_id=campaign.meta_campaign_id,
                    detail={"drift": str(drift), "checkpoint_snapshot_id": checkpoint.id},
                )
            )
            count += 1
        elif existing.drift_amount != drift:
            existing.drift_amount = drift
            existing.latest_snapshot_id = latest.id
    session.flush()
    summary.drift_records += count
    return count


# --- entrypoint job ---


def run_meta_sync(
    session: Session,
    connector: MetaAdsConnector,
    now: Optional[datetime] = None,
    force_checkpoint_9h: bool = False,
) -> dict[str, Any]:
    """Job đồng bộ 1 lượt (idempotent). Checkpoint tự đánh dấu khi trong cửa sổ 09:00 VN (D-029).

    Single-flight (D-030): lượt chạy khi đã có lượt khác đang giữ lock → SKIPPED_CONCURRENT_RUN.
    """
    global LAST_SYNC_COMPLETED_AT
    now = now or utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if not SYNC_LOCK.acquire(blocking=False):
        return {"status": "SKIPPED_CONCURRENT_RUN", "at": now.isoformat()}
    try:
        is_checkpoint_run = force_checkpoint_9h or is_checkpoint_time(now)
        summary = SyncSummary()
        customers = session.execute(select(Customer).where(Customer.is_active.is_(True))).scalars().all()
        for account in sync_ad_accounts(session, connector, summary):
            for campaign in sync_campaigns_for_account(session, connector, account, customers, summary):
                snapshot_campaign_spend(session, connector, campaign, account, now, is_checkpoint_run, summary)
        record_drift_after_sync(session, connector, now, summary)
        session.flush()
        LAST_SYNC_COMPLETED_AT = now
        return summary.as_dict()
    finally:
        SYNC_LOCK.release()
