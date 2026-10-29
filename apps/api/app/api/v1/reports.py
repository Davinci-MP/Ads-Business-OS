"""REST endpoints báo cáo kinh doanh (S17) — chỉ đọc DB, không gọi Sheets ghi."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import reports

router = APIRouter(tags=["reports"])


def _parse_date(value: Optional[str], name: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{name} không hợp lệ (YYYY-MM-DD)") from exc


@router.get("/reports/daily")
def reports_daily(
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    customer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return reports.daily_spend_rows(db, date_from=_parse_date(date_from, "from"), date_to=_parse_date(date_to, "to"), customer_id=customer_id)


@router.get("/reports/transactions")
def reports_transactions(
    limit: int = Query(5, ge=1, le=50),
    customer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return reports.recent_transactions(db, limit=limit, customer_id=customer_id)


@router.get("/reports/kpi")
def reports_kpi(
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return reports.company_kpi(db, date_from=_parse_date(date_from, "from"), date_to=_parse_date(date_to, "to"))


@router.get("/reports/customers/{customer_id}")
def report_customer(
    customer_id: int,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    report = reports.customer_report(
        db,
        customer_id,
        date_from=_parse_date(date_from, "from"),
        date_to=_parse_date(date_to, "to"),
    )
    if report.get("error"):
        raise HTTPException(status_code=404, detail=report["error"])
    return report
