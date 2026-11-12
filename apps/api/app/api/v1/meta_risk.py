from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.meta import MetaAPIError, MetaAdsConnector
from app.db import get_db
from app.core.local_admin import require_local_admin
from app.models.meta_risk import MetaAccountRisk
from app.models.finance import AuditLog
from app.core.config import settings
from app.services.meta_risk import get_risk, lock_account, scan_account_risks, unlock_account
from app.services.telegram_bot import get_configured_telegram_connector

router = APIRouter(prefix="/meta-risk", tags=["rủi ro Meta"], dependencies=[Depends(require_local_admin)])


@router.get("")
def list_risks(db: Session = Depends(get_db)):
    return [{"account_id": r.account_id, "account_status": r.account_status, "currency": r.currency,
             "debt": str(r.debt) if r.debt is not None else None,
             "debt_threshold": str(r.debt_threshold) if r.debt_threshold is not None else None,
             "locked": r.locked, "risk_code": r.risk_code, "data_status": r.data_status,
             "checked_at": r.checked_at, "last_error": r.last_error}
            for r in db.scalars(select(MetaAccountRisk).order_by(MetaAccountRisk.account_id))]


@router.post("/scan")
def scan(db: Session = Depends(get_db)):
    try:
        with MetaAdsConnector() as connector:
            result = scan_account_risks(db, connector, get_configured_telegram_connector(db))
        db.commit()
        return result
    except MetaAPIError:
        raise HTTPException(502, "Không đọc được danh sách tài khoản Meta; giữ nguyên dữ liệu cũ.")


@router.post("/{account_id}/lock")
def lock(account_id: str, db: Session = Depends(get_db)):
    try:
        with MetaAdsConnector() as connector:
            return lock_account(db, connector, account_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except MetaAPIError:
        raise HTTPException(502, "Đã khóa nội bộ nhưng chưa xác nhận dừng chiến dịch trên Meta.")


@router.post("/{account_id}/unlock")
def unlock(account_id: str, db: Session = Depends(get_db)):
    try:
        return unlock_account(db, account_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class ThresholdRequest(BaseModel):
    threshold: Decimal = Field(ge=0, allow_inf_nan=False)


@router.post("/{account_id}/threshold")
def threshold(account_id: str, body: ThresholdRequest, db: Session = Depends(get_db)):
    try:
        if settings.app_env == "staging":
            raise ValueError("Môi trường thử nghiệm chỉ đọc, không được sửa ngưỡng cảnh báo.")
        row = get_risk(db, account_id)
        if row.currency is None:
            raise ValueError("Cần quét trạng thái để xác định tiền tệ trước khi đặt ngưỡng.")
        row.debt_threshold = body.threshold
        db.add(AuditLog(actor="web_ui", action="SET_META_DEBT_THRESHOLD", entity_type="ad_account", entity_id=row.account_id, detail={"threshold": str(body.threshold), "currency": row.currency}))
        db.commit()
        return {"message": "Đã lưu ngưỡng nợ cước theo tiền tệ tài khoản."}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
