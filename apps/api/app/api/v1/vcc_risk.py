"""Router API Quản trị Thẻ VCC PingPong, Cross-Mapping TKQC Meta và Động cơ Cảnh báo Rủi ro."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.risk_engine import RiskManagementEngine

router = APIRouter()


class ThresholdUpdatePayload(BaseModel):
    threshold: float = Field(..., ge=0, description="Ngưỡng số dư cảnh báo (USD)")


@router.get("/overview")
def get_vcc_risk_overview(session: Session = Depends(get_db)) -> dict[str, Any]:
    """Lấy tổng quan số dư Quỹ Master USD, tổng nợ Meta, danh sách thẻ và cảnh báo rủi ro."""
    try:
        return RiskManagementEngine.get_overview(session)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi khi đọc tổng quan rủi ro VCC: {exc}")


@router.post("/sync")
def trigger_vcc_risk_sync(session: Session = Depends(get_db)) -> dict[str, Any]:
    """Kích hoạt đồng bộ VCC từ PingPong và quét lại rủi ro tức thời."""
    try:
        return RiskManagementEngine.sync_and_evaluate(session)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi khi đồng bộ thẻ VCC và quét rủi ro: {exc}")


@router.put("/cards/{card_id}/threshold")
def update_card_threshold(
    card_id: str,
    payload: ThresholdUpdatePayload,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật ngưỡng cảnh báo số dư thấp cho một thẻ VCC cụ thể."""
    try:
        card = RiskManagementEngine.update_card_threshold(
            session=session,
            card_id=card_id,
            threshold=Decimal(str(payload.threshold)),
        )
        return {
            "ok": True,
            "card_id": card.id,
            "low_balance_threshold": float(card.low_balance_threshold),
            "message": f"Đã cập nhật ngưỡng cảnh báo cho thẻ *{card.last_four} thành {payload.threshold} USD",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật ngưỡng thẻ: {exc}")


@router.get("/cards/{card_id}/transactions")
def get_card_transactions(
    card_id: str,
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lấy lịch sử giao dịch/biến động số dư của một thẻ VCC cụ thể để hiển thị modal."""
    try:
        txns = RiskManagementEngine.get_card_transactions_history(session=session, card_id=card_id, limit=limit)
        return [
            {
                "id": t.id,
                "card_id": t.card_id,
                "auth_amount": float(t.auth_amount),
                "settle_amount": float(t.settle_amount),
                "currency": t.currency,
                "merchant_name": t.merchant_name or "FACEBOOK ADS",
                "status": t.status,
                "transaction_time": t.transaction_time.isoformat() if t.transaction_time else None,
            }
            for t in txns
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi khi đọc lịch sử giao dịch thẻ: {exc}")
