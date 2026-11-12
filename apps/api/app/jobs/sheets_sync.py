"""Chuẩn bị và thực thi đồng bộ Sheets theo giờ riêng của từng khách hàng.

Job chỉ chọn đúng `customers.sync_time == HH:MM` theo Asia/Ho_Chi_Minh. Ghi thật
chỉ chạy ở production khi lịch đã APPROVED và cờ ghi riêng được bật; staging/local
giữ preview để không ghi nhầm bảng vận hành.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.sheets import parse_spreadsheet_url
from app.core.config import settings
from app.db import SessionLocal
from app.models import (
    AdAccount,
    Approval,
    AuditLog,
    Campaign,
    Customer,
    CustomerSheetSyncRun,
    SpendSnapshot,
    SyncedAdAccount,
)
from app.models.campaign import RECOGNITION_CONFIRMED
from app.models.spend import DATA_VERIFIED, SOURCE_META_API

logger = logging.getLogger(__name__)
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _money(value: Decimal, currency: str) -> str:
    unit = Decimal("1") if currency == "VND" else Decimal("0.01")
    return format(value.quantize(unit, rounding=ROUND_HALF_UP), "f")


def _fee_percent(value: Decimal) -> str:
    return format((value * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _schedule_is_approved(db: Session, customer_id: int) -> bool:
    return db.scalar(select(Approval.id).where(
        Approval.entity_type == "CUSTOMER_SHEET_SCHEDULE",
        Approval.entity_id == str(customer_id),
        Approval.status == "APPROVED",
    ).order_by(Approval.id.desc())) is not None


def build_customer_rows(db: Session, customer: Customer, report_date) -> tuple[list[list[str]], bool]:
    """Tạo hàng theo đúng 10 cột; không suy daily spend từ chênh lệch snapshot."""
    accounts = db.scalars(select(SyncedAdAccount).where(
        SyncedAdAccount.customer_id == customer.id,
    ).order_by(SyncedAdAccount.act_id)).all()
    rows: list[list[str]] = []
    needs_rate_confirmation = False

    for synced in accounts:
        clean_act = synced.act_id.replace("act_", "").strip()
        account = db.scalar(select(AdAccount).where(or_(
            AdAccount.meta_ad_account_id == clean_act,
            AdAccount.meta_ad_account_id == f"act_{clean_act}",
        )))
        if account is None:
            continue
        campaigns = db.scalars(select(Campaign).where(
            Campaign.ad_account_id == account.id,
            Campaign.customer_id == customer.id,
            Campaign.report_period_end == report_date,
            Campaign.recognition_status == RECOGNITION_CONFIRMED,
        )).all()
        spend_by_currency: dict[str, Decimal] = {}
        for campaign in campaigns:
            snapshot = db.scalar(select(SpendSnapshot).where(
                SpendSnapshot.campaign_id == campaign.id,
                SpendSnapshot.data_status == DATA_VERIFIED,
                SpendSnapshot.source == SOURCE_META_API,
            ).order_by(SpendSnapshot.snapshot_at.desc(), SpendSnapshot.id.desc()).limit(1))
            if snapshot is None:
                continue
            currency = (snapshot.currency or synced.currency or "").upper()
            if not currency:
                continue
            spend_by_currency[currency] = spend_by_currency.get(currency, Decimal("0")) + Decimal(snapshot.spend_amount)

        fee_rate = Decimal(customer.fee_rate)
        for currency, spend in sorted(spend_by_currency.items()):
            fee = spend * fee_rate
            total = spend + fee
            foreign_spend = _money(spend, currency) if currency not in ("USD", "VND") else ""
            usd = _money(spend, currency) if currency == "USD" else ""
            vnd = _money(spend, currency) if currency == "VND" else ""
            if currency != "VND":
                # Q-014: chưa được dùng tỷ giá hiện hành cho lifetime spend Meta.
                needs_rate_confirmation = True
            rows.append([
                report_date.strftime("%d/%m/%Y"),
                f"{synced.name} ({currency})",
                clean_act,
                foreign_spend,
                usd,
                vnd,
                _fee_percent(fee_rate),
                _money(total, currency),
                "",
                "",
            ])
    return rows, needs_rate_confirmation


def _execute_live_write(db: Session, run: CustomerSheetSyncRun, customer: Customer) -> None:
    if settings.app_env != "production" or not settings.customer_sheets_writes_enabled:
        run.status = "PREVIEW_READY"
        return
    if not _schedule_is_approved(db, customer.id):
        run.status = "PENDING_APPROVAL"
        return
    if run.status == "NEEDS_CONFIRMATION":
        return

    import gspread

    service_account_file = os.environ.get("ADSOS_GOOGLE_SERVICE_ACCOUNT_FILE", "")
    service_account_json = os.environ.get("ADSOS_GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if service_account_file:
        client = gspread.service_account(filename=service_account_file)
    elif service_account_json:
        client = gspread.service_account_from_dict(json.loads(service_account_json))
    else:
        raise RuntimeError("Chưa cấu hình service account Google Sheets")

    workbook = client.open_by_key(parse_spreadsheet_url(customer.sheet_url or ""))
    worksheet = workbook.worksheet(customer.sheet_tab_name or "")
    before = worksheet.get_all_values()
    run.backup_json = before
    rows = run.rows_json or []
    worksheet.append_rows(rows, value_input_option="RAW")
    after = worksheet.get_all_values()
    if after[-len(rows):] != rows:
        raise RuntimeError("Đọc lại Google Sheets không khớp dữ liệu vừa ghi")
    run.status = "EXECUTED"
    run.executed_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        actor="scheduler",
        action="customer_sheet_sync_executed",
        entity_type="customer_sheet_sync_run",
        entity_id=str(run.id),
        detail={"customer_id": customer.id, "rows": len(rows), "backup_rows": len(before)},
    ))


def run_customer_sheets_sync(now: datetime | None = None, session: Session | None = None) -> dict[str, int]:
    owns_session = session is None
    db = session or SessionLocal()
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current_vn = current.astimezone(VN_TZ)
    scheduled_for = current_vn.replace(second=0, microsecond=0).astimezone(timezone.utc)
    sync_time = current_vn.strftime("%H:%M")
    summary = {"matched": 0, "created": 0, "executed": 0, "skipped": 0, "failed": 0}
    try:
        customers = db.scalars(select(Customer).where(
            Customer.is_active.is_(True),
            Customer.sync_time == sync_time,
        ).order_by(Customer.id)).all()
        summary["matched"] = len(customers)
        for customer in customers:
            existing = db.scalar(select(CustomerSheetSyncRun).where(
                CustomerSheetSyncRun.customer_id == customer.id,
                CustomerSheetSyncRun.scheduled_for == scheduled_for,
            ))
            if existing is not None:
                summary["skipped"] += 1
                continue
            rows, needs_confirmation = build_customer_rows(db, customer, current_vn.date())
            if not (customer.sheet_url and customer.sheet_tab_name):
                status = "NEEDS_CONFIGURATION"
            elif not rows:
                status = "NO_VERIFIED_DATA"
            elif needs_confirmation:
                status = "NEEDS_CONFIRMATION"
            elif not _schedule_is_approved(db, customer.id):
                status = "PENDING_APPROVAL"
            else:
                status = "CREATED"
            run = CustomerSheetSyncRun(
                customer_id=customer.id,
                scheduled_for=scheduled_for,
                report_date=current_vn.date(),
                status=status,
                rows_json=rows,
            )
            try:
                with db.begin_nested():
                    db.add(run)
                    db.flush()
            except IntegrityError:
                summary["skipped"] += 1
                continue
            summary["created"] += 1
            db.add(AuditLog(
                actor="scheduler",
                action="customer_sheet_sync_prepared",
                entity_type="customer_sheet_sync_run",
                entity_id=str(run.id),
                detail={"customer_id": customer.id, "rows": len(rows), "status": status},
            ))
            if status == "CREATED":
                try:
                    _execute_live_write(db, run, customer)
                except Exception as exc:
                    run.status = "FAILED"
                    run.error_message = f"{type(exc).__name__}: không thể ghi Google Sheets"
                    summary["failed"] += 1
                    logger.exception("Đồng bộ Sheets thất bại cho khách hàng ID %s", customer.id)
            if run.status == "EXECUTED":
                summary["executed"] += 1
        db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()
