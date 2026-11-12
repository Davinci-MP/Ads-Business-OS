from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.customer import Customer
from app.models.finance import AuditLog
from app.models.prepaid import ClientBalance, LedgerTransaction
from app.services import prepaid

def local_admin(request: Request):
    if request.client and request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(403, "Sổ ngân sách nội bộ chỉ được truy cập từ máy local.")
    if request.method != "GET":
        origin = request.headers.get("origin")
        if origin and origin not in {"http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"}:
            raise HTTPException(403, "Nguồn yêu cầu không được phép ghi sổ ngân sách.")


router = APIRouter(prefix="/prepaid", tags=["ngan-sach"], dependencies=[Depends(local_admin)])


class TransactionRequest(BaseModel):
    customer_id: int
    currency: str = "VND"
    amount: Decimal
    kind: str = "DEPOSIT"
    idempotency_key: str = Field(min_length=1, max_length=128)
    evidence: str = Field(min_length=1)
    actor: str = Field(min_length=1, max_length=64)
    source_ledger_id: Optional[int] = None


class ActorRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=64)


class ThresholdRequest(ActorRequest):
    currency: str = "VND"
    low_threshold: Optional[Decimal] = None
    deposit_info: str = ""


def tx_data(tx):
    return {"id": tx.id, "customer_id": tx.customer_id, "currency": tx.currency, "amount": str(tx.amount), "kind": tx.kind, "status": tx.status, "evidence": tx.evidence, "source_ledger_id": tx.source_ledger_id, "created_at": tx.created_at.isoformat(), "requested_by": tx.requested_by, "approved_by": tx.approved_by}


@router.get("")
def overview(db: Session = Depends(get_db)):
    names = {c.id: c.name for c in db.scalars(select(Customer))}
    return {"balances": [{"id": b.id, "customer_id": b.customer_id, "customer_name": names.get(b.customer_id), "currency": b.currency, "amount": str(b.amount), "low_threshold": str(b.low_threshold) if b.low_threshold is not None else None, "deposit_info": b.deposit_info, "low": b.low_alert_active} for b in db.scalars(select(ClientBalance).order_by(ClientBalance.id))], "transactions": [tx_data(t) for t in db.scalars(select(LedgerTransaction).order_by(LedgerTransaction.id.desc()).limit(200))], "notice": "Sổ ngân sách nội bộ thử nghiệm; số dư báo cáo Sheets vẫn là nguồn có thẩm quyền. Chỉ ghi khoản đã duyệt. Tự tính chi tiêu theo kỳ tỷ giá và phí thuê đang chờ xác nhận."}


@router.post("/transactions")
def request(req: TransactionRequest, db: Session = Depends(get_db)):
    try:
        tx = prepaid.request_transaction(db, **req.model_dump())
        db.commit()
        return tx_data(tx)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))


@router.post("/transactions/{tx_id}/approve")
def approve(tx_id: int, req: ActorRequest, db: Session = Depends(get_db)):
    try:
        tx = prepaid.approve_transaction(db, tx_id, req.actor)
        db.commit()
        return tx_data(tx)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))


@router.post("/transactions/{tx_id}/reject")
def reject(tx_id: int, req: ActorRequest, db: Session = Depends(get_db)):
    try:
        tx = prepaid.reject_transaction(db, tx_id, req.actor)
        db.commit()
        return tx_data(tx)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))


@router.post("/process")
def process(db: Session = Depends(get_db)):
    count = prepaid.process_approved_transactions(db)
    db.commit()
    return {"processed": count, "message": f"Đã ghi sổ {count} khoản được duyệt."}


@router.post("/customers/{customer_id}/threshold")
def configure(customer_id: int, req: ThresholdRequest, db: Session = Depends(get_db)):
    try:
        prepaid.writable()
        threshold = prepaid.money(req.low_threshold, req.currency) if req.low_threshold is not None else None
        if threshold is not None and threshold < 0:
            raise ValueError("Ngưỡng cảnh báo không được âm.")
        row = prepaid.balance_for(db, customer_id, req.currency)
        row.low_threshold, row.deposit_info = threshold, req.deposit_info
        prepaid.check_low_balance(db, row)
        db.add(AuditLog(actor=req.actor, action="PREPAID_THRESHOLD", entity_type="client_balance", entity_id=str(row.id)))
        db.commit()
        return {"message": "Đã lưu ngưỡng cảnh báo và thông tin nạp tiền."}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
