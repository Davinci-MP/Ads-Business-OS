"""Dịch vụ Quản trị Rủi ro Thẻ VCC PingPong, Cross-Mapping TKQC Meta và Động cơ Cảnh báo Tài chính."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.pingpong import PingPongConnector
from app.models.customer import utcnow
from app.models.exchange import ExchangeConnection, ExchangeCredentials, EXCH_PROVIDER_PINGPONG, EXCH_STATUS_ACTIVE
from app.models.vcc import VccCard, VccTransaction
from app.models.via import SyncedAdAccount

logger = logging.getLogger(__name__)


def _fmt_usd(val: Any) -> str:
    """Định dạng số tiền USD gọn gàng, loại bỏ các số 0 thừa."""
    try:
        d = Decimal(str(val))
        normalized = d.normalize()
        sign, digits, exp = normalized.as_tuple()
        if exp > 0:
            return str(int(d))
        return f"{normalized:f}"
    except Exception:
        return str(val)


def _get_fernet():
    import os
    from cryptography.fernet import Fernet
    key = os.environ.get("ADSOS_EXCHANGE_MASTER_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except Exception:
        return None


def get_pingpong_connector_from_db(session: Session, connection_id: Optional[int] = None) -> Optional[PingPongConnector]:
    """Khởi tạo PingPongConnector từ thông tin xác thực đã mã hóa trong DB (nếu có)."""
    fernet = _get_fernet()
    if not fernet:
        return None

    query = select(ExchangeConnection).where(
        ExchangeConnection.provider == EXCH_PROVIDER_PINGPONG,
        ExchangeConnection.status == EXCH_STATUS_ACTIVE,
    )
    if connection_id:
        query = query.where(ExchangeConnection.id == connection_id)
    conn_row = session.scalars(query).first()
    if not conn_row:
        return None

    cred_row = session.scalars(
        select(ExchangeCredentials).where(ExchangeCredentials.connection_id == conn_row.id)
    ).first()
    if not cred_row:
        return None

    try:
        client_id = fernet.decrypt(cred_row.encrypted_api_key.encode("utf-8")).decode("utf-8")
        client_secret = fernet.decrypt(cred_row.encrypted_api_secret.encode("utf-8")).decode("utf-8")
        account_id = None
        if cred_row.encrypted_extra:
            try:
                raw_extra = fernet.decrypt(cred_row.encrypted_extra.encode("utf-8")).decode("utf-8")
                account_id = json.loads(raw_extra).get("account_id")
            except Exception:
                pass

        return PingPongConnector(
            client_id=client_id,
            client_secret=client_secret,
            account_id=account_id,
            base_url=conn_row.base_url or "https://gateway.pingpongx.com",
        )
    except Exception as exc:
        logger.warning(f"Không thể khởi tạo PingPongConnector từ DB: {exc}")
        return None


class RiskManagementEngine:
    """Động cơ đồng bộ VCC, mapping chéo với TKQC Meta và phát cảnh báo rủi ro số dư."""

    @classmethod
    def sync_vcc_cards(
        cls,
        session: Session,
        connection_id: Optional[int] = None,
        connector: Optional[PingPongConnector] = None,
    ) -> list[VccCard]:
        """Đồng bộ danh sách thẻ VCC đang hoạt động từ PingPong vào bảng vcc_cards."""
        active_connector = connector or get_pingpong_connector_from_db(session, connection_id)
        if not active_connector:
            logger.info("Không có PingPong connector khả dụng để đồng bộ VCC, giữ nguyên dữ liệu hiện có.")
            return session.scalars(select(VccCard).where(VccCard.status == "ACTIVE")).all()

        try:
            cards_data = active_connector.get_active_cards()
        except Exception as exc:
            logger.error(f"Lỗi khi gọi PingPong get_active_cards: {exc}")
            return session.scalars(select(VccCard).where(VccCard.status == "ACTIVE")).all()

        synced_cards: list[VccCard] = []
        now = utcnow()
        for item in cards_data:
            card_id = str(item["id"])
            card = session.get(VccCard, card_id)
            if card:
                card.card_number_masked = item.get("card_number_masked") or card.card_number_masked
                card.last_four = str(item.get("last_four") or card.last_four)
                card.status = str(item.get("status") or "ACTIVE").upper()
                card.remark = str(item.get("remark") or card.remark or "")
                card.currency = str(item.get("currency") or card.currency or "USD")
                card.allocated_balance = Decimal(str(item.get("allocated_balance", card.allocated_balance)))
                card.available_balance = Decimal(str(item.get("available_balance", card.available_balance)))
                card.updated_at = now
            else:
                card = VccCard(
                    id=card_id,
                    card_number_masked=item.get("card_number_masked"),
                    last_four=str(item.get("last_four", "0000")),
                    status=str(item.get("status", "ACTIVE")).upper(),
                    remark=str(item.get("remark") or ""),
                    currency=str(item.get("currency") or "USD"),
                    allocated_balance=Decimal(str(item.get("allocated_balance", 0))),
                    available_balance=Decimal(str(item.get("available_balance", 0))),
                    low_balance_threshold=Decimal("5.0"),
                    created_at=now,
                    updated_at=now,
                )
                session.add(card)
            synced_cards.append(card)

        session.commit()
        return synced_cards

    @classmethod
    def auto_map_cards_to_ad_accounts(cls, session: Session) -> list[dict[str, Any]]:
        """Liên kết tự động các thẻ VCC hoạt động với các TKQC Meta.

        Logic khớp:
        1. Khớp 4 số cuối thẻ: vcc_card.last_four == synced_ad_account.funding_source_last_four (hoặc payment_card_last4).
        2. Nếu nhiều TKQC khớp cùng 4 số cuối, giải quyết bằng cách kiểm tra remark chứa act_id hoặc tên TKQC.
        """
        active_cards = session.scalars(select(VccCard).where(VccCard.status == "ACTIVE")).all()
        ad_accounts = session.scalars(select(SyncedAdAccount)).all()

        results: list[dict[str, Any]] = []

        for card in active_cards:
            matched_accounts: list[SyncedAdAccount] = []
            for acc in ad_accounts:
                acc_last4 = (acc.funding_source_last_four or acc.payment_card_last4 or "").strip()
                if acc_last4 and acc_last4 == card.last_four:
                    matched_accounts.append(acc)

            chosen_account: Optional[SyncedAdAccount] = None
            if len(matched_accounts) == 1:
                chosen_account = matched_accounts[0]
            elif len(matched_accounts) > 1:
                # Phân giải bằng remark
                card_remark_lower = (card.remark or "").lower()
                for acc in matched_accounts:
                    act_num = acc.act_id.replace("act_", "").strip()
                    if act_num and act_num in card_remark_lower:
                        chosen_account = acc
                        break
                    if acc.name and acc.name.lower() in card_remark_lower:
                        chosen_account = acc
                        break
                # Nếu vẫn chưa phân giải được, lấy tài khoản có chi tiêu/dư nợ lớn nhất
                if not chosen_account:
                    chosen_account = sorted(matched_accounts, key=lambda a: float(a.balance or 0), reverse=True)[0]

            results.append({
                "card": card,
                "ad_account": chosen_account,
                "all_matched_count": len(matched_accounts),
            })

        return results

    @classmethod
    def evaluate_alerts(
        cls,
        session: Session,
        master_usd_balance: Optional[Decimal] = None,
        connector: Optional[PingPongConnector] = None,
    ) -> list[dict[str, Any]]:
        """Đánh giá toàn bộ các quy tắc rủi ro và sinh đối tượng cảnh báo.

        - Quy tắc 1 (Low VCC Balance): available_balance < low_balance_threshold.
        - Quy tắc 2 (Meta Debt > VCC Balance - CRITICAL): ad_account.balance > vcc_card.available_balance.
        - Quy tắc 3 (Master Budget Risk): tổng nợ Meta của các TKQC > master_usd_balance.
        """
        mappings = cls.auto_map_cards_to_ad_accounts(session)
        alerts: list[dict[str, Any]] = []

        total_meta_debt = Decimal("0")
        all_accounts = session.scalars(select(SyncedAdAccount)).all()
        for acc in all_accounts:
            try:
                debt_val = Decimal(str(acc.balance or 0))
                if debt_val > 0:
                    total_meta_debt += debt_val
            except (InvalidOperation, ValueError):
                pass

        # Lấy Master USD Balance nếu chưa truyền vào
        actual_master_usd = master_usd_balance
        if actual_master_usd is None:
            active_connector = connector or get_pingpong_connector_from_db(session)
            if active_connector:
                try:
                    actual_master_usd = active_connector.get_usd_budget_balance()
                except Exception:
                    actual_master_usd = None

        # 1. Đánh giá Rule 1 & Rule 2 trên từng thẻ
        for item in mappings:
            card: VccCard = item["card"]
            acc: Optional[SyncedAdAccount] = item["ad_account"]
            card_avail = Decimal(str(card.available_balance or 0))
            card_thresh = Decimal(str(card.low_balance_threshold or 5.0))

            # Rule 1: Thẻ sắp hết tiền
            if card_avail < card_thresh:
                avail_disp = _fmt_usd(card_avail)
                alerts.append({
                    "rule": "RULE_1_LOW_VCC_BALANCE",
                    "severity": "WARNING",
                    "card_id": card.id,
                    "last_four": card.last_four,
                    "remark": card.remark or "—",
                    "available_balance": float(card_avail),
                    "threshold": float(card_thresh),
                    "message": f"Cảnh báo Thẻ: Thẻ *{card.last_four} ({card.remark or 'Chưa đặt tên'}) chỉ còn {avail_disp} USD.",
                })

            # Rule 2: Nợ Meta vượt quá số dư thẻ (NGUY HIỂM)
            if acc:
                try:
                    acc_debt = Decimal(str(acc.balance or 0))
                except (InvalidOperation, ValueError):
                    acc_debt = Decimal("0")

                if acc_debt > card_avail:
                    debt_disp = _fmt_usd(acc_debt)
                    avail_disp = _fmt_usd(card_avail)
                    alerts.append({
                        "rule": "RULE_2_META_DEBT_EXCEEDS_VCC_BALANCE",
                        "severity": "CRITICAL",
                        "card_id": card.id,
                        "last_four": card.last_four,
                        "act_id": acc.act_id,
                        "ad_account_name": acc.name,
                        "debt": float(acc_debt),
                        "available_balance": float(card_avail),
                        "message": (
                            f"🚨 NGUY HIỂM: TKQC {acc.act_id} đang nợ {debt_disp} USD "
                            f"nhưng thẻ *{card.last_four} chỉ còn {avail_disp} USD! Sẽ hụt tiền khi Meta charge!"
                        ),
                    })

        # 2. Đánh giá Rule 3: Nguy cơ cạn quỹ Master USD
        if actual_master_usd is not None and total_meta_debt > actual_master_usd:
            debt_disp = _fmt_usd(total_meta_debt)
            master_disp = _fmt_usd(actual_master_usd)
            alerts.append({
                "rule": "RULE_3_MASTER_BUDGET_DEFICIT",
                "severity": "CRITICAL",
                "master_usd_balance": float(actual_master_usd),
                "total_meta_debt": float(total_meta_debt),
                "deficit": float(total_meta_debt - actual_master_usd),
                "message": (
                    f"🚨 NGUY HIỂM: Tổng nợ Meta ({debt_disp} USD) vượt quá số dư "
                    f"Master Budget PingPong ({master_disp} USD)! Cần nạp thêm tiền ngay."
                ),
            })

        return alerts

    @classmethod
    def update_card_threshold(cls, session: Session, card_id: str, threshold: Decimal) -> VccCard:
        """Cập nhật ngưỡng cảnh báo số dư thấp cho một thẻ VCC."""
        card = session.get(VccCard, str(card_id).strip())
        if not card:
            raise ValueError(f"Không tìm thấy thẻ VCC #{card_id}")
        if threshold < 0:
            raise ValueError("Ngưỡng cảnh báo không thể là số âm")

        card.low_balance_threshold = Decimal(str(threshold))
        card.updated_at = utcnow()
        session.commit()
        return card

    @classmethod
    def get_card_transactions_history(
        cls,
        session: Session,
        card_id: str,
        limit: int = 50,
        connector: Optional[PingPongConnector] = None,
    ) -> list[VccTransaction]:
        """Lấy lịch sử biến động số dư / giao dịch của thẻ VCC."""
        card_id_clean = str(card_id).strip()
        active_connector = connector or get_pingpong_connector_from_db(session)
        if active_connector:
            try:
                txns = active_connector.get_card_transactions(card_id_clean, limit=limit)
                for t in txns:
                    txn_id = str(t["id"])
                    existing = session.get(VccTransaction, txn_id)
                    if not existing:
                        parsed_time = None
                        if t.get("transaction_time"):
                            try:
                                parsed_time = datetime.fromisoformat(str(t["transaction_time"]).replace("Z", "+00:00"))
                            except Exception:
                                pass
                        new_txn = VccTransaction(
                            id=txn_id,
                            card_id=card_id_clean,
                            auth_amount=t.get("auth_amount", Decimal("0")),
                            settle_amount=t.get("settle_amount", Decimal("0")),
                            currency=t.get("currency", "USD"),
                            merchant_name=t.get("merchant_name", "FACEBOOK ADS"),
                            status=t.get("status", "SETTLED"),
                            transaction_time=parsed_time or utcnow(),
                        )
                        session.add(new_txn)
                session.commit()
            except Exception as exc:
                logger.warning(f"Lỗi đồng bộ giao dịch thẻ #{card_id_clean}: {exc}")

        return session.scalars(
            select(VccTransaction)
            .where(VccTransaction.card_id == card_id_clean)
            .order_by(VccTransaction.transaction_time.desc())
            .limit(limit)
        ).all()

    @classmethod
    def get_overview(
        cls,
        session: Session,
        connector: Optional[PingPongConnector] = None,
    ) -> dict[str, Any]:
        """Tổng hợp số liệu KPI, danh sách thẻ và cảnh báo rủi ro cho Dashboard."""
        active_connector = connector or get_pingpong_connector_from_db(session)
        master_usd_balance = Decimal("0")
        if active_connector:
            try:
                master_usd_balance = active_connector.get_usd_budget_balance()
            except Exception:
                pass

        mappings = cls.auto_map_cards_to_ad_accounts(session)
        alerts = cls.evaluate_alerts(session, master_usd_balance=master_usd_balance, connector=active_connector)

        total_meta_debt = Decimal("0")
        card_views: list[dict[str, Any]] = []

        critical_cards_set = set()
        warning_cards_set = set()

        for a in alerts:
            if a.get("card_id"):
                if a["severity"] == "CRITICAL":
                    critical_cards_set.add(a["card_id"])
                elif a["severity"] == "WARNING":
                    warning_cards_set.add(a["card_id"])

        for item in mappings:
            card: VccCard = item["card"]
            acc: Optional[SyncedAdAccount] = item["ad_account"]

            acc_debt = Decimal(str(acc.balance or 0)) if acc else Decimal("0")
            if acc_debt > 0:
                total_meta_debt += acc_debt

            # Xác định trạng thái rủi ro
            if card.id in critical_cards_set:
                risk_status = "CRITICAL"
                risk_label = "🚨 Nguy cơ tụt ngưỡng"
            elif card.id in warning_cards_set:
                risk_status = "WARNING"
                risk_label = "⚠️ Sắp hết tiền"
            else:
                risk_status = "SAFE"
                risk_label = "✅ An toàn"

            card_views.append({
                "id": card.id,
                "card_number_masked": card.card_number_masked or f"**** **** **** {card.last_four}",
                "last_four": card.last_four,
                "remark": card.remark or "—",
                "status": card.status,
                "currency": card.currency,
                "allocated_balance": float(card.allocated_balance),
                "available_balance": float(card.available_balance),
                "low_balance_threshold": float(card.low_balance_threshold),
                "risk_status": risk_status,
                "risk_label": risk_label,
                "ad_account": {
                    "id": acc.id,
                    "act_id": acc.act_id,
                    "name": acc.name,
                    "balance": float(acc_debt),
                    "threshold": float(acc.threshold or acc.threshold_amount or 0),
                    "status_dot": acc.status_dot,
                } if acc else None,
                "created_at": card.created_at.isoformat() if card.created_at else None,
                "updated_at": card.updated_at.isoformat() if card.updated_at else None,
            })

        return {
            "master_usd_balance": float(master_usd_balance),
            "total_meta_debt": float(total_meta_debt),
            "total_active_cards": len(card_views),
            "critical_alerts_count": len([a for a in alerts if a["severity"] == "CRITICAL"]),
            "warning_alerts_count": len([a for a in alerts if a["severity"] == "WARNING"]),
            "cards": card_views,
            "alerts": alerts,
        }

    @classmethod
    def sync_and_evaluate(
        cls,
        session: Session,
        connection_id: Optional[int] = None,
        connector: Optional[PingPongConnector] = None,
    ) -> dict[str, Any]:
        """Kích hoạt đồng bộ VCC mới nhất từ PingPong và quét lại toàn bộ rủi ro."""
        cls.sync_vcc_cards(session, connection_id=connection_id, connector=connector)
        return cls.get_overview(session, connector=connector)
