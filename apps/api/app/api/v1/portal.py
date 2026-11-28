"""API Cổng khách hàng (Client Portal) tra cứu số dư trả trước, chi tiêu và tài khoản."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.local_admin import require_local_admin_or_owner
from app.db import get_db
from app.models.ad_account import AdAccount, AdAccountAssignment
from app.models.campaign import Campaign
from app.models.customer import Customer, utcnow
from app.models.finance import AuditLog
from app.models.prepaid import ClientBalance, LedgerTransaction
from app.models.spend import DATA_VERIFIED, SpendSnapshot

router = APIRouter(prefix="/portal", tags=["cong-khach-hang"])


@router.get("/{token}")
def get_client_portal(
    token: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cổng công khai cho khách hàng tra cứu số dư trả trước, chi tiêu và tài khoản qua token bảo mật."""
    clean_token = token.strip()
    if not clean_token:
        raise HTTPException(status_code=400, detail="Mã truy cập không hợp lệ.")

    customer = db.scalar(
        select(Customer).where(Customer.portal_token == clean_token, Customer.is_active.is_(True))
    )
    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Cổng thông tin không tồn tại, sai mã truy cập hoặc tài khoản đã bị vô hiệu hóa.",
        )

    # 1. Số dư ví trả trước
    balances = db.scalars(
        select(ClientBalance)
        .where(ClientBalance.customer_id == customer.id)
        .order_by(ClientBalance.currency)
    ).all()
    balance_list = [
        {
            "currency": b.currency,
            "amount": str(b.amount),
            "low_threshold": str(b.low_threshold) if b.low_threshold is not None else None,
            "deposit_info": b.deposit_info or "Vui lòng liên hệ quản trị viên để nhận thông tin chuyển khoản.",
            "low_alert": b.low_alert_active,
        }
        for b in balances
    ]

    # 2. Tài khoản quảng cáo được phân bổ kèm cách ly theo khung thời gian (valid_from / valid_to)
    now = utcnow()
    assignments = db.scalars(
        select(AdAccountAssignment).where(
            AdAccountAssignment.customer_id == customer.id,
            AdAccountAssignment.valid_from <= now,
            or_(
                AdAccountAssignment.valid_to.is_(None),
                AdAccountAssignment.valid_to >= now,
            ),
        )
    ).all()

    assigned_accounts: list[dict[str, Any]] = []
    global_spend_by_curr: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))

    account_ids = [a.ad_account_id for a in assignments]
    if account_ids:
        ad_accs = db.scalars(select(AdAccount).where(AdAccount.id.in_(account_ids))).all()

        # Batch query loại bỏ N+1: Lấy snapshot VERIFIED mới nhất cho từng chiến dịch
        # strictly giới hạn trong khung thời gian [valid_from, valid_to] của khách hàng
        ranked_snaps = (
            select(
                SpendSnapshot.campaign_id,
                SpendSnapshot.spend_amount,
                SpendSnapshot.currency,
                SpendSnapshot.snapshot_at,
                Campaign.ad_account_id,
                func.row_number().over(
                    partition_by=SpendSnapshot.campaign_id,
                    order_by=desc(SpendSnapshot.snapshot_at),
                ).label("rn"),
            )
            .join(Campaign, Campaign.id == SpendSnapshot.campaign_id)
            .join(
                AdAccountAssignment,
                (AdAccountAssignment.ad_account_id == Campaign.ad_account_id)
                & (AdAccountAssignment.customer_id == customer.id),
            )
            .where(
                Campaign.ad_account_id.in_(account_ids),
                SpendSnapshot.data_status == DATA_VERIFIED,
                or_(Campaign.customer_id.is_(None), Campaign.customer_id == customer.id),
                SpendSnapshot.snapshot_at >= AdAccountAssignment.valid_from,
                or_(
                    AdAccountAssignment.valid_to.is_(None),
                    SpendSnapshot.snapshot_at <= AdAccountAssignment.valid_to,
                ),
            )
            .subquery()
        )

        latest_snaps = db.execute(
            select(
                ranked_snaps.c.ad_account_id,
                ranked_snaps.c.campaign_id,
                ranked_snaps.c.spend_amount,
                ranked_snaps.c.currency,
            ).where(ranked_snaps.c.rn == 1)
        ).all()

        acc_spend_by_curr: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0.00")))
        acc_campaign_ids: dict[int, set[int]] = defaultdict(set)

        for row in latest_snaps:
            acc_id = row.ad_account_id
            curr = (row.currency or "USD").upper()
            amt = Decimal(str(row.spend_amount))
            acc_spend_by_curr[acc_id][curr] += amt
            global_spend_by_curr[curr] += amt
            acc_campaign_ids[acc_id].add(row.campaign_id)

        # Lấy thêm các chiến dịch mới tạo trong kỳ chưa có snapshot
        valid_camps = db.execute(
            select(
                Campaign.ad_account_id,
                Campaign.id,
            )
            .join(
                AdAccountAssignment,
                (AdAccountAssignment.ad_account_id == Campaign.ad_account_id)
                & (AdAccountAssignment.customer_id == customer.id),
            )
            .where(
                Campaign.ad_account_id.in_(account_ids),
                or_(Campaign.customer_id.is_(None), Campaign.customer_id == customer.id),
                Campaign.created_at >= AdAccountAssignment.valid_from,
                or_(
                    AdAccountAssignment.valid_to.is_(None),
                    Campaign.created_at <= AdAccountAssignment.valid_to,
                ),
            )
        ).all()

        for c_row in valid_camps:
            acc_campaign_ids[c_row.ad_account_id].add(c_row.id)

        for acc in ad_accs:
            curr_map = acc_spend_by_curr[acc.id]
            if curr_map:
                primary_curr = next(iter(curr_map.keys()))
                primary_spend = curr_map[primary_curr]
            else:
                primary_curr = "USD"
                primary_spend = Decimal("0.00")

            assigned_accounts.append(
                {
                    "meta_ad_account_id": acc.meta_ad_account_id,
                    "name": acc.name,
                    "status": acc.status,
                    "timezone_name": acc.timezone_name,
                    "total_spend": float(primary_spend.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "currency": primary_curr,
                    "spend_by_currency": {
                        c: str(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                        for c, v in curr_map.items()
                    },
                    "campaign_count": len(acc_campaign_ids[acc.id]),
                }
            )

    # 3. Lịch sử giao dịch sổ cái gần đây
    transactions = db.scalars(
        select(LedgerTransaction)
        .where(LedgerTransaction.customer_id == customer.id)
        .order_by(desc(LedgerTransaction.id))
        .limit(20)
    ).all()
    tx_list = [
        {
            "id": tx.id,
            "amount": str(tx.amount),
            "currency": tx.currency,
            "kind": tx.kind,
            "status": tx.status,
            "evidence": tx.evidence,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
            "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
        }
        for tx in transactions
    ]

    totals_by_currency = {
        c: str(amt.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        for c, amt in global_spend_by_curr.items()
    }

    return {
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "fee_rate": float(customer.fee_rate) if customer.fee_rate else 0.04,
            "recon_mode": customer.recon_mode,
        },
        "balances": balance_list,
        "assigned_accounts": assigned_accounts,
        "totals_by_currency": totals_by_currency,
        "recent_transactions": tx_list,
    }


@router.post("/customers/{customer_id}/generate-token", dependencies=[Depends(require_local_admin_or_owner)])
def generate_portal_token(
    customer_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tạo hoặc làm mới mã truy cập cổng thông tin khách hàng (yêu cầu quản trị viên)."""
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng.")

    new_token = secrets.token_hex(32)
    customer.portal_token = new_token
    db.add(
        AuditLog(
            actor="web_ui",
            action="GENERATE_PORTAL_TOKEN",
            entity_type="customer",
            entity_id=str(customer.id),
            detail={"name": customer.name},
        )
    )
    db.commit()
    db.refresh(customer)

    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "portal_token": new_token,
        "portal_url": f"/portal/{new_token}",
    }


@router.delete("/customers/{customer_id}/token", dependencies=[Depends(require_local_admin_or_owner)])
def revoke_portal_token(
    customer_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Vô hiệu hóa mã truy cập cổng thông tin khách hàng."""
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng.")

    customer.portal_token = None
    db.add(
        AuditLog(
            actor="web_ui",
            action="REVOKE_PORTAL_TOKEN",
            entity_type="customer",
            entity_id=str(customer.id),
            detail={"name": customer.name},
        )
    )
    db.commit()

    return {"message": f"Đã vô hiệu hóa cổng thông tin của khách hàng {customer.name}."}
