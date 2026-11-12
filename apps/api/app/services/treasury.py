"""Tổng hợp nguồn vốn & ngân quỹ (Treasury Summary) — CHỈ ĐỌC từ snapshot DB.

Tập hợp dữ liệu từ:
1. Ví TRON On-chain (USDT)
2. Sàn Binance (Spot + Funding USDT)
3. Cổng PingPong (Nguồn tiền đa tệ & Thẻ ảo VCC)

Nguyên tắc:
- Không gọi API sàn/chuỗi khi xem bảng tin; chỉ tổng hợp các snapshot đã lưu.
- Không yêu cầu mã quản trị sàn để xem tổng quan, nhưng tuyệt đối KHÔNG trả secrets/keys.
- Giữ riêng từng tiền tệ theo D-056 / FINANCE_RULES; tính toán bằng Decimal.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.exchange import (
    EXCH_PROVIDER_BINANCE,
    EXCH_PROVIDER_PINGPONG,
    EXCH_STATUS_ACTIVE,
    EXCH_WALLET_FUNDING,
    EXCH_WALLET_SPOT,
    ExchangeBalanceSnapshot,
    ExchangeCardSnapshot,
    ExchangeConnection,
)
from app.models.finance import UsdtWallet, UsdtWalletBalance


def _to_dec(val: Any) -> Decimal:
    if val is None:
        return Decimal("0")
    try:
        d = Decimal(str(val))
        return d if d.is_finite() else Decimal("0")
    except Exception:
        return Decimal("0")


def get_treasury_summary(session: Session) -> dict[str, Any]:
    """Tổng hợp nguồn vốn toàn diện: TRON + Binance + PingPong."""

    # 1. TRON WALLETS
    tron_wallets = session.scalars(select(UsdtWallet)).all()
    tron_items = []
    total_tron_usdt = Decimal("0")

    for w in tron_wallets:
        latest_bal = session.scalars(
            select(UsdtWalletBalance)
            .where(UsdtWalletBalance.wallet_id == w.id)
            .order_by(UsdtWalletBalance.read_at.desc(), UsdtWalletBalance.id.desc())
            .limit(1)
        ).first()

        bal_dec = _to_dec(latest_bal.balance) if latest_bal else Decimal("0")
        total_tron_usdt += bal_dec
        tron_items.append({
            "id": w.id,
            "name": w.wallet_name,
            "address": w.wallet_address,
            "balance": str(bal_dec),
            "read_at": latest_bal.read_at.isoformat() if latest_bal else None,
            "last_error": w.last_error,
        })

    # 2. BINANCE CONNECTIONS
    binance_conns = session.scalars(
        select(ExchangeConnection).where(
            ExchangeConnection.provider == EXCH_PROVIDER_BINANCE,
            ExchangeConnection.status == EXCH_STATUS_ACTIVE,
        )
    ).all()

    binance_items = []
    total_binance_spot_usdt = Decimal("0")
    total_binance_funding_usdt = Decimal("0")

    for c in binance_conns:
        # Lấy snapshot mới nhất của Spot USDT
        spot_snap = session.scalars(
            select(ExchangeBalanceSnapshot)
            .where(
                ExchangeBalanceSnapshot.connection_id == c.id,
                ExchangeBalanceSnapshot.wallet_type == EXCH_WALLET_SPOT,
                ExchangeBalanceSnapshot.asset == "USDT",
            )
            .order_by(ExchangeBalanceSnapshot.read_at.desc(), ExchangeBalanceSnapshot.id.desc())
            .limit(1)
        ).first()

        # Lấy snapshot mới nhất của Funding USDT
        funding_snap = session.scalars(
            select(ExchangeBalanceSnapshot)
            .where(
                ExchangeBalanceSnapshot.connection_id == c.id,
                ExchangeBalanceSnapshot.wallet_type == EXCH_WALLET_FUNDING,
                ExchangeBalanceSnapshot.asset == "USDT",
            )
            .order_by(ExchangeBalanceSnapshot.read_at.desc(), ExchangeBalanceSnapshot.id.desc())
            .limit(1)
        ).first()

        spot_free = _to_dec(spot_snap.free) if spot_snap else Decimal("0")
        funding_free = _to_dec(funding_snap.free) if funding_snap else Decimal("0")
        conn_total = spot_free + funding_free

        total_binance_spot_usdt += spot_free
        total_binance_funding_usdt += funding_free

        latest_read = None
        if spot_snap and funding_snap:
            latest_read = max(spot_snap.read_at, funding_snap.read_at).isoformat()
        elif spot_snap:
            latest_read = spot_snap.read_at.isoformat()
        elif funding_snap:
            latest_read = funding_snap.read_at.isoformat()

        binance_items.append({
            "id": c.id,
            "label": c.label,
            "spot_free": str(spot_free),
            "funding_free": str(funding_free),
            "total_usdt": str(conn_total),
            "read_at": latest_read,
            "last_error": c.last_error,
        })

    total_binance_usdt = total_binance_spot_usdt + total_binance_funding_usdt

    # 3. PINGPONG CONNECTIONS (Balances & VCC)
    pingpong_conns = session.scalars(
        select(ExchangeConnection).where(
            ExchangeConnection.provider == EXCH_PROVIDER_PINGPONG,
            ExchangeConnection.status == EXCH_STATUS_ACTIVE,
        )
    ).all()

    pingpong_items = []
    pingpong_currencies_agg: dict[str, dict[str, Decimal]] = {}
    total_active_cards = 0
    total_cards_available_balance = Decimal("0")
    total_cards_spending_limit = Decimal("0")

    for c in pingpong_conns:
        # Lấy tất cả snapshots gần nhất của connection này
        raw_snaps = session.scalars(
            select(ExchangeBalanceSnapshot)
            .where(ExchangeBalanceSnapshot.connection_id == c.id)
            .order_by(ExchangeBalanceSnapshot.read_at.desc(), ExchangeBalanceSnapshot.id.desc())
            .limit(100)
        ).all()

        latest_by_curr: dict[str, ExchangeBalanceSnapshot] = {}
        for s in raw_snaps:
            if s.asset not in latest_by_curr:
                latest_by_curr[s.asset] = s

        balances_summary = {}
        for curr, s in latest_by_curr.items():
            avail = _to_dec(s.free)
            pending = _to_dec(s.locked)
            total = avail + pending
            balances_summary[curr] = {
                "available": str(avail),
                "pending": str(pending),
                "total": str(total),
            }

            if curr not in pingpong_currencies_agg:
                pingpong_currencies_agg[curr] = {"available": Decimal("0"), "pending": Decimal("0"), "total": Decimal("0")}
            pingpong_currencies_agg[curr]["available"] += avail
            pingpong_currencies_agg[curr]["pending"] += pending
            pingpong_currencies_agg[curr]["total"] += total

        # Thẻ ảo VCC
        card_snaps = session.scalars(
            select(ExchangeCardSnapshot)
            .where(ExchangeCardSnapshot.connection_id == c.id)
            .order_by(ExchangeCardSnapshot.read_at.desc(), ExchangeCardSnapshot.id.desc())
            .limit(200)
        ).all()

        latest_cards: dict[str, ExchangeCardSnapshot] = {}
        for card in card_snaps:
            if card.card_id not in latest_cards:
                latest_cards[card.card_id] = card

        conn_active_cards = 0
        conn_cards_balance = Decimal("0")
        conn_cards_limit = Decimal("0")

        for card in latest_cards.values():
            if card.status == "ACTIVE":
                conn_active_cards += 1
                c_bal = _to_dec(card.available_balance)
                c_lim = _to_dec(card.spending_limit)
                conn_cards_balance += c_bal
                conn_cards_limit += c_lim

        total_active_cards += conn_active_cards
        total_cards_available_balance += conn_cards_balance
        total_cards_spending_limit += conn_cards_limit

        pingpong_items.append({
            "id": c.id,
            "label": c.label,
            "balances": balances_summary,
            "active_cards_count": conn_active_cards,
            "cards_available_balance": str(conn_cards_balance),
            "cards_spending_limit": str(conn_cards_limit),
            "last_ok_at": c.last_ok_at.isoformat() if c.last_ok_at else None,
            "last_error": c.last_error,
        })

    # TỔNG HỢP VỐN THANH KHOẢN (Combined Liquid Funds)
    total_liquid_usdt = total_tron_usdt + total_binance_usdt
    total_pingpong_usd = pingpong_currencies_agg.get("USD", {}).get("available", Decimal("0"))

    # Tổng thanh khoản quy ước tương đương USD/USDT (1 USDT = 1 USD)
    grand_total_working_capital = total_liquid_usdt + total_pingpong_usd

    return {
        "summary": {
            "total_liquid_usdt": str(total_liquid_usdt),
            "total_pingpong_usd": str(total_pingpong_usd),
            "grand_total_working_capital": str(grand_total_working_capital),
            "total_active_vcc_cards": total_active_cards,
            "total_vcc_available_balance": str(total_cards_available_balance),
            "total_vcc_spending_limit": str(total_cards_spending_limit),
        },
        "breakdown": {
            "tron": {
                "total_usdt": str(total_tron_usdt),
                "wallets_count": len(tron_items),
                "items": tron_items,
            },
            "binance": {
                "total_usdt": str(total_binance_usdt),
                "spot_usdt": str(total_binance_spot_usdt),
                "funding_usdt": str(total_binance_funding_usdt),
                "accounts_count": len(binance_items),
                "items": binance_items,
            },
            "pingpong": {
                "total_usd": str(total_pingpong_usd),
                "currencies": {
                    k: {
                        "available": str(v["available"]),
                        "pending": str(v["pending"]),
                        "total": str(v["total"]),
                    }
                    for k, v in pingpong_currencies_agg.items()
                },
                "active_cards_count": total_active_cards,
                "cards_available_balance": str(total_cards_available_balance),
                "cards_spending_limit": str(total_cards_spending_limit),
                "accounts_count": len(pingpong_items),
                "items": pingpong_items,
            },
        },
    }
