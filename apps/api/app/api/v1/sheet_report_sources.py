"""Nguồn báo cáo Sheets nội bộ; không ghi Google Sheets hoặc sổ tài chính."""
from datetime import datetime
from copy import deepcopy
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.sheets import SheetsAPIError, parse_spreadsheet_url
from app.core.config import settings
from app.jobs.sheet_reports import scheduler_status
from app.db import get_db
from app.models.customer import Customer
from app.models.finance import AuditLog
from app.models.sheet_reports import (
    SheetReportClosure, SheetReportCustomerLink, SheetReportSettings, SheetReportSnapshot,
    SheetReportSource, SheetReportSyncAttempt,
)
from app.services.sheet_report_store import MAPPING_CONFIG, MAPPING_VERSION, SyncBusy, compare_rollover, latest_snapshot, read_source_report, sync_source
from app.services.sheets_report import enrich_sheets_report
from app.services.sheet_year_summary import build_customer_year_summary, build_year_summary
from app.services.customer_sheets import customer_sheets_overview
from app.services.customer_setup import SetupError, apply_setup, setup_proposals
from app.services.link_review import build_link_review

router = APIRouter(prefix="/sheets/sources", tags=["sheet-report-sources"])


class SourceCreate(BaseModel):
    spreadsheet: str
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    name: str = Field(min_length=1, max_length=255)
    replace_existing: bool = False
    set_default: bool = False
    sync_enabled: bool = False


class SourceUpdate(BaseModel):
    set_default: bool = False
    sync_enabled: Optional[bool] = None


class ClosureCreate(BaseModel):
    snapshot_id: int
    acknowledge_partial: bool = False


class SheetWritebackRequest(BaseModel):
    report_date: str = Field(..., description="Ngày báo cáo (YYYY-MM-DD hoặc DD/MM/YYYY)")
    client_ids: Optional[list[int]] = Field(None, description="Danh sách ID khách hàng (mặc định tất cả)")
    dry_run: bool = Field(True, description="Chế độ xem trước (không sửa dữ liệu)")
    auto_create_borders: bool = Field(True, description="Tự động kẻ viền và công thức")


class CustomerLinkCreate(BaseModel):
    sheet_id: int
    customer_id: int
    confirm_renamed: bool = False


class SetupItem(BaseModel):
    sheet_id: int
    action: str
    expected_source_sheet: str
    customer_id: Optional[int] = None
    name: Optional[str] = None


class SetupApply(BaseModel):
    items: list[SetupItem] = Field(min_length=1, max_length=200)
    confirm: bool = False


def _source(session: Session, source_id: int) -> SheetReportSource:
    source = session.get(SheetReportSource, source_id)
    if source is None:
        raise HTTPException(404, "Không tìm thấy nguồn báo cáo")
    return source


@router.get("/{source_id}/customer-setup")
def customer_setup(source_id: int, db: Session = Depends(get_db)) -> dict:
    return setup_proposals(db, _source(db, source_id))


@router.post("/{source_id}/customer-setup")
def customer_setup_apply(source_id: int, body: SetupApply, db: Session = Depends(get_db)) -> dict:
    if not body.confirm:
        raise HTTPException(400, "Cần xác nhận rõ trước khi ghi hồ sơ/liên kết.")
    try:
        return apply_setup(db, _source(db, source_id), [item.model_dump() for item in body.items])
    except SetupError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{source_id}/customer-overview")
def customer_overview(source_id: int, db: Session = Depends(get_db)) -> dict:
    return customer_sheets_overview(db, _source(db, source_id))


def _attempt(item: SheetReportSyncAttempt | None) -> dict | None:
    if item is None:
        return None
    return {"id": item.id, "started_at": item.started_at, "finished_at": item.finished_at,
            "status": item.status, "error": item.error, "snapshot_id": item.snapshot_id, "trigger": item.trigger}


def _snapshot(item: SheetReportSnapshot | None, include_report: bool = False) -> dict | None:
    if item is None:
        return None
    result = {"id": item.id, "source_id": item.source_id, "read_at": item.read_at,
              "mapping_version": item.mapping_version, "quality": item.quality}
    if include_report:
        result["report"] = item.report
    return result


def _serialize(session: Session, source: SheetReportSource, defer_report: bool = False) -> dict:
    last = session.scalar(select(SheetReportSyncAttempt).where(
        SheetReportSyncAttempt.source_id == source.id).order_by(SheetReportSyncAttempt.id.desc()).limit(1))
    snapshot = latest_snapshot(session, source.id, defer_report=defer_report)
    closure = session.scalar(select(SheetReportClosure).where(SheetReportClosure.source_id == source.id))
    settings = session.get(SheetReportSettings, 1)
    return {
        "id": source.id, "period": source.period, "name": source.name,
        "spreadsheet_id": source.spreadsheet_id, "mapping_version": source.mapping_version,
        "active": source.active, "sync_enabled": source.sync_enabled,
        "is_default": bool(settings and settings.default_source_id == source.id),
        "last_attempt": _attempt(last), "latest_snapshot": _snapshot(snapshot),
        "closure": {"snapshot_id": closure.snapshot_id, "closed_at": closure.closed_at, "actor": closure.actor} if closure else None,
    }


@router.get("")
def list_sources(db: Session = Depends(get_db)) -> dict:
    items = db.scalars(select(SheetReportSource).order_by(
        SheetReportSource.period.desc(), SheetReportSource.id.desc())).all()
    return {"sources": [_serialize(db, item, defer_report=True) for item in items],
            "scheduler_enabled": settings.sheets_scheduler_enabled,
            "scheduler": scheduler_status(),
            "schedule": "15 phút khi backend đang chạy"}


@router.get("/year-summary")
def year_summary(
    year: int = Query(ge=1, le=9999),
    basis: str = Query("current", pattern=r"^(current|closed)$"),
    scope: str = Query("month", pattern=r"^(month|year|day)$"),
    month: Optional[str] = Query(None, pattern=r"^(0[1-9]|1[0-2])$"),
    date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    db: Session = Depends(get_db),
) -> dict:
    return build_year_summary(db, year, basis=basis, scope=scope, month=month, date=date)


@router.get("/customer-year-summary")
def customer_year_summary(
    year: int = Query(ge=1, le=9999),
    basis: str = Query("current", pattern=r"^(current|closed)$"),
    customer_id: int = Query(...),
    rank_by: Optional[str] = Query(None, pattern="^(budget_deposits_vnd|spend_vnd|fee|billing_total|usdt_received|usdt_refunded|usdt_net)$"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return build_customer_year_summary(db, year, basis=basis, customer_id=customer_id, rank_by=rank_by)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/link-review")
def link_review(db: Session = Depends(get_db)) -> dict:
    """Rà soát liên kết khách (CHỈ ĐỌC): danh sách tab/nguồn + đề xuất chờ người vận hành xác nhận."""
    return build_link_review(db)


@router.post("", status_code=201)
def create_source(body: SourceCreate, db: Session = Depends(get_db)) -> dict:
    try:
        spreadsheet_id = parse_spreadsheet_url(body.spreadsheet)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not body.name.strip():
        raise HTTPException(422, "Tên nguồn không được để trống")
    existing_same = db.scalar(select(SheetReportSource).where(
        SheetReportSource.period == body.period, SheetReportSource.spreadsheet_id == spreadsheet_id))
    if existing_same:
        raise HTTPException(409, "Nguồn này đã tồn tại trong kỳ; không tạo bản trùng.")
    existing = db.scalar(select(SheetReportSource).where(
        SheetReportSource.period == body.period, SheetReportSource.active.is_(True)))
    if existing and not body.replace_existing:
        raise HTTPException(409, "Kỳ đã có nguồn khác; cần xác nhận thay thế rõ ràng.")
    read_error: str | None = None
    try:
        report = read_source_report(spreadsheet_id, None, body.period, MAPPING_CONFIG)
    except SheetsAPIError as exc:
        if existing:
            raise HTTPException(502, f"Không kiểm tra được cấu trúc nguồn: {exc}") from exc
        # Kỳ chưa có nguồn: giữ cấu hình để người dùng thử lại, không báo đọc thành công.
        report = None
        read_error = f"Không kiểm tra được cấu trúc nguồn: {exc}"
    try:
        if existing:
            existing.active = False
            existing.sync_enabled = False
            db.flush()
            settings_row = db.get(SheetReportSettings, 1)
            if settings_row and settings_row.default_source_id == existing.id and not body.set_default:
                settings_row.default_source_id = None
        source = SheetReportSource(period=body.period, spreadsheet_id=spreadsheet_id,
                                   name=body.name.strip(), mapping_version=MAPPING_VERSION, mapping_config=MAPPING_CONFIG.copy(),
                                   active=True, sync_enabled=body.sync_enabled)
        db.add(source)
        db.flush()
        if report is None:
            now = datetime.now().astimezone()
            db.add(SheetReportSyncAttempt(
                source_id=source.id, started_at=now, finished_at=now,
                status="ERROR", error=read_error, trigger="INITIAL",
            ))
        else:
            snapshot = SheetReportSnapshot(
                source_id=source.id, read_at=datetime.fromisoformat(report["read_at"]),
                mapping_version=MAPPING_VERSION, mapping_config=MAPPING_CONFIG.copy(), quality=report["status"], report=report,
            )
            db.add(snapshot)
            db.flush()
            db.add(SheetReportSyncAttempt(
                source_id=source.id, started_at=snapshot.read_at, finished_at=datetime.now().astimezone(),
                status=report["status"], snapshot_id=snapshot.id, trigger="INITIAL",
            ))
        if body.set_default and report is not None:
            settings = db.get(SheetReportSettings, 1)
            if settings is None:
                settings = SheetReportSettings(id=1)
                db.add(settings)
            settings.default_source_id = source.id
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Nguồn hoặc kỳ đang được tạo/thay thế; tải lại trước khi thử.") from exc
    return _serialize(db, source)


@router.patch("/{source_id}")
def update_source(source_id: int, body: SourceUpdate, db: Session = Depends(get_db)) -> dict:
    source = _source(db, source_id)
    if not source.active:
        raise HTTPException(409, "Không thể bật hoặc chọn mặc định nguồn đã thay thế.")
    if body.sync_enabled is not None:
        source.sync_enabled = body.sync_enabled
    if body.set_default:
        settings = db.get(SheetReportSettings, 1)
        if not settings:
            settings = SheetReportSettings(id=1)
            db.add(settings)
        settings.default_source_id = source.id
    db.commit()
    return _serialize(db, source)


@router.post("/{source_id}/sync")
def sync(source_id: int, db: Session = Depends(get_db)) -> dict:
    _source(db, source_id)
    try:
        item = sync_source(db, source_id, "MANUAL")
    except SyncBusy as exc:
        raise HTTPException(409, "Nguồn đang được đồng bộ; không chạy chồng lấn.") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _attempt(item)


@router.get("/{source_id}/snapshots")
def snapshots(
    source_id: int, limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    _source(db, source_id)
    items = db.execute(
        select(
            SheetReportSnapshot.id, SheetReportSnapshot.source_id, SheetReportSnapshot.read_at,
            SheetReportSnapshot.mapping_version, SheetReportSnapshot.quality,
        ).where(SheetReportSnapshot.source_id == source_id)
        .order_by(SheetReportSnapshot.id.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(SheetReportSnapshot).where(
        SheetReportSnapshot.source_id == source_id)) or 0
    return {"total": total, "snapshots": [
        {"id": item.id, "source_id": item.source_id, "read_at": item.read_at,
         "mapping_version": item.mapping_version, "quality": item.quality} for item in items
    ]}


@router.get("/{source_id}/report")
def source_report(source_id: int, snapshot_id: Optional[int] = None, db: Session = Depends(get_db)) -> dict:
    source = _source(db, source_id)
    snapshot = db.get(SheetReportSnapshot, snapshot_id) if snapshot_id else latest_snapshot(db, source_id)
    if not snapshot or snapshot.source_id != source_id:
        raise HTTPException(404, "Nguồn chưa có bản báo cáo đã lưu.")
    result = _snapshot(snapshot, True)
    result["report"] = enrich_sheets_report(deepcopy(snapshot.report), source.period, source.spreadsheet_id)
    return result


@router.get("/{source_id}/history")
def history(
    source_id: int, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    _source(db, source_id)
    items = db.scalars(select(SheetReportSyncAttempt).where(
        SheetReportSyncAttempt.source_id == source_id
    ).order_by(SheetReportSyncAttempt.id.desc()).limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(SheetReportSyncAttempt).where(
        SheetReportSyncAttempt.source_id == source_id)) or 0
    return {"total": total, "history": [_attempt(item) for item in items]}


@router.post("/{source_id}/closure")
def close_period(source_id: int, body: ClosureCreate, db: Session = Depends(get_db)) -> dict:
    source = _source(db, source_id)
    snapshot = db.get(SheetReportSnapshot, body.snapshot_id)
    if not snapshot or snapshot.source_id != source_id:
        raise HTTPException(404, "Bản lưu không thuộc nguồn này.")
    if snapshot.quality != "READY" and not body.acknowledge_partial:
        raise HTTPException(409, "Bản lưu chưa đầy đủ; phải xác nhận đã xem cảnh báo trước khi chốt.")
    if db.scalar(select(SheetReportClosure.id).join(
        SheetReportSource, SheetReportSource.id == SheetReportClosure.source_id
    ).where(SheetReportSource.period == source.period)):
        raise HTTPException(409, "Kỳ đã có bản chốt; không ghi đè hoặc tạo bản chốt khác.")
    closure = SheetReportClosure(source_id=source_id, snapshot_id=snapshot.id)
    db.add(closure)
    # Không có xác thực ở phiên này: actor ghi "unknown" thay vì giả định danh người thao tác.
    db.add(AuditLog(
        actor="unknown", action="sheet_report_closed", entity_type="sheet_report_source", entity_id=str(source_id),
        detail={"snapshot_id": snapshot.id, "quality": snapshot.quality, "actor_recorded": False},
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Nguồn đã được chốt.") from exc
    return {"snapshot_id": closure.snapshot_id, "closed_at": closure.closed_at, "quality": snapshot.quality}


@router.get("/{source_id}/links")
def links(source_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _source(db, source_id)
    items = db.scalars(select(SheetReportCustomerLink).where(
        SheetReportCustomerLink.source_id == source_id, SheetReportCustomerLink.active.is_(True))).all()
    return [{"sheet_id": item.sheet_id, "source_title": item.source_title, "customer_id": item.customer_id} for item in items]


@router.post("/{source_id}/links")
def link_customer(source_id: int, body: CustomerLinkCreate, db: Session = Depends(get_db)) -> dict:
    _source(db, source_id)
    if db.get(Customer, body.customer_id) is None:
        raise HTTPException(404, "Không tìm thấy khách nội bộ.")
    snapshot = latest_snapshot(db, source_id)
    matches = [c for c in snapshot.report.get("customers", []) if c.get("sheet_id") == body.sheet_id] if snapshot else []
    if len(matches) != 1 or matches[0].get("profile_status") in ("STRUCTURE_ERROR", "SOURCE_ERROR"):
        raise HTTPException(409, "Không nhận diện được duy nhất tab khách hợp lệ trong bản mới nhất.")
    existing = db.scalar(select(SheetReportCustomerLink).where(
        SheetReportCustomerLink.source_id == source_id,
        SheetReportCustomerLink.sheet_id == body.sheet_id, SheetReportCustomerLink.active.is_(True)))
    if existing:
        if (not body.confirm_renamed or existing.customer_id != body.customer_id
                or existing.source_title == matches[0]["source_sheet"]):
            raise HTTPException(409, "Tab đã liên kết; chỉ xác nhận tên mới cho cùng khách và cùng sheet ID.")
        existing.active = False
        db.flush()
    item = SheetReportCustomerLink(source_id=source_id, sheet_id=body.sheet_id,
                                   source_title=matches[0]["source_sheet"], customer_id=body.customer_id, active=True)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Khách hoặc tab đã có liên kết; không tự ghi đè.") from exc
    return {"sheet_id": item.sheet_id, "source_title": item.source_title, "customer_id": item.customer_id}


@router.get("/{source_id}/rollover")
def rollover(source_id: int, previous_source_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    current, previous = _source(db, source_id), _source(db, previous_source_id)
    year, month = map(int, current.period.split("-"))
    expected = f"{year - 1:04d}-12" if month == 1 else f"{year:04d}-{month - 1:02d}"
    if previous.period != expected:
        raise HTTPException(400, "Nguồn trước không thuộc kỳ ngay trước kỳ hiện tại.")
    closure = db.scalar(select(SheetReportClosure).where(SheetReportClosure.source_id == previous_source_id))
    old_snapshot = db.get(SheetReportSnapshot, closure.snapshot_id) if closure else latest_snapshot(db, previous_source_id)
    new_snapshot = latest_snapshot(db, source_id)
    def unlinked(snapshot: SheetReportSnapshot | None, sid: int) -> list[str]:
        if snapshot is None:
            return []
        linked_ids = set(db.scalars(select(SheetReportCustomerLink.sheet_id).where(
            SheetReportCustomerLink.source_id == sid, SheetReportCustomerLink.active.is_(True))).all())
        return [c["source_sheet"] for c in snapshot.report.get("customers", [])
                if c.get("sheet_id") not in linked_ids]
    return {"previous_period": previous.period, "current_period": current.period,
            "previous_closed": bool(closure),
            "provisional": not closure,
            "basis_label": "Chính thức theo bản chốt" if closure else "Tạm thời — Chưa chốt",
            "note": "Chỉ so sánh khách có liên kết ID đã xác nhận; không sửa Sheets.",
            "unlinked_previous": unlinked(old_snapshot, previous_source_id),
            "unlinked_current": unlinked(new_snapshot, source_id),
            "customers": compare_rollover(db, previous_source_id, source_id)}


@router.post("/writeback-from-vias")
def writeback_from_vias_sources(
    body: SheetWritebackRequest,
    db: Session = Depends(get_db),
) -> dict:
    from app.services.sheet_writer import writeback_reporting_rows_to_sheets
    try:
        return writeback_reporting_rows_to_sheets(
            session=db,
            report_date_str=body.report_date,
            client_ids=body.client_ids,
            dry_run=body.dry_run,
            auto_create_borders=body.auto_create_borders,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc

