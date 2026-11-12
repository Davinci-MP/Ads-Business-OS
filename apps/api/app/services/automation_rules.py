"""Dịch vụ đánh giá và thực thi các quy tắc tự động hóa (Automation Rules Engine)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.connectors.meta import MetaAdsConnector
from app.connectors.telegram import TelegramBotConnector
from app.models.campaign import Campaign
from app.models.ad_account import AdAccount
from app.models.customer import utcnow
from app.models.exchange import ExchangeCardSnapshot
from app.models.finance import AuditLog
from app.models.spend import DriftRecord, SpendSnapshot
from app.models.telegram import AutomationRule
from app.services.remote_commands import enqueue_extension_command

logger = logging.getLogger(__name__)

DEFAULT_RULES = [
    {
        "name": "Tự động tạm dừng chiến dịch khi chi tiêu ngày vượt hạn mức",
        "rule_type": "AUTO_PAUSE_SPEND_LIMIT",
        "threshold": Decimal("10000000"),
        "currency": "VND",
        "action_type": "AUTO_PAUSE",
        "is_enabled": True,
    },
    {
        "name": "Cảnh báo số dư thẻ ảo VCC PingPong dưới 50 USD",
        "rule_type": "ALERT_LOW_VCC_BALANCE",
        "threshold": Decimal("50.00"),
        "currency": "USD",
        "action_type": "TELEGRAM_ALERT",
        "is_enabled": True,
    },
    {
        "name": "Báo cáo tổng kết hiệu suất hàng ngày tới Admin",
        "rule_type": "DAILY_REPORT_SCHEDULE",
        "threshold": Decimal("0"),
        "currency": "VND",
        "action_type": "DAILY_DIGEST",
        "is_enabled": True,
    },
    {
        "name": "Cảnh báo tiền trôi bất thường vượt 2.000.000 đ",
        "rule_type": "ALERT_HIGH_DRIFT_SPEND",
        "threshold": Decimal("2000000"),
        "currency": "VND",
        "action_type": "TELEGRAM_ALERT",
        "is_enabled": True,
    },
]


def ensure_default_rules(db: Session) -> list[AutomationRule]:
    """Khởi tạo các quy tắc tự động hóa mặc định nếu bảng đang trống."""
    count = db.execute(select(AutomationRule)).scalars().all()
    if not count:
        created = []
        for r in DEFAULT_RULES:
            rule = AutomationRule(
                name=r["name"],
                rule_type=r["rule_type"],
                threshold=r["threshold"],
                currency=r["currency"],
                action_type=r["action_type"],
                is_enabled=r["is_enabled"],
            )
            db.add(rule)
            created.append(rule)
        db.commit()
        return created
    return list(count)


def evaluate_automation_rules(
    db: Session,
    meta_connector: Optional[MetaAdsConnector] = None,
    telegram_connector: Optional[TelegramBotConnector] = None,
) -> dict[str, Any]:
    """Quét và thực thi toàn bộ các quy tắc tự động hóa đang bật."""
    telegram = telegram_connector or TelegramBotConnector()

    rules = db.execute(select(AutomationRule).where(AutomationRule.is_enabled == True)).scalars().all()
    triggered_actions = []

    for rule in rules:
        try:
            # 1. AUTO_PAUSE_SPEND_LIMIT
            if rule.rule_type == "AUTO_PAUSE_SPEND_LIMIT":
                # Kiểm tra các campaign ACTIVE
                active_campaigns = db.execute(select(Campaign).where(Campaign.meta_status == "ACTIVE")).scalars().all()
                for camp in active_campaigns:
                    if rule.target_entity_id and rule.target_entity_id != camp.meta_campaign_id:
                        continue
                    # Lấy snapshot chi tiêu mới nhất
                    latest_snap = db.execute(
                        select(SpendSnapshot)
                        .where(SpendSnapshot.campaign_id == camp.id)
                        .order_by(desc(SpendSnapshot.snapshot_at))
                        .limit(1)
                    ).scalar_one_or_none()

                    if latest_snap and latest_snap.spend_amount >= rule.threshold:
                        account = db.get(AdAccount, camp.ad_account_id)
                        if account is None:
                            continue
                        enqueue_extension_command(
                            db,
                            act_id=account.meta_ad_account_id,
                            command_type="SET_CAMPAIGN_STATUS",
                            payload={"campaign_id": camp.meta_campaign_id, "status": "PAUSED"},
                            customer_id=camp.customer_id,
                            requested_by="automation_rule",
                        )
                        # Gửi tin nhắn cảnh báo
                        msg = (
                            f"🚨 <b>QUY TẮC TỰ ĐỘNG: ĐÃ XẾP LỆNH TẠM DỪNG CHIẾN DỊCH</b>\n\n"
                            f"• Chiến dịch: <b>{camp.name}</b> (<code>{camp.meta_campaign_id}</code>)\n"
                            f"• Chi tiêu tích luỹ: <b>{float(latest_snap.spend_amount):,.0f} {rule.currency}</b>\n"
                            f"• Ngưỡng quy tắc: <b>{float(rule.threshold):,.0f} {rule.currency}</b>\n"
                            f"• Thao tác: Đã xếp lệnh Extension chuyển sang ⏸ <b>PAUSED (Tạm dừng)</b>."
                        )
                        telegram.send_admin_message(msg)
                        rule.last_triggered_at = utcnow()
                        rule.trigger_count += 1
                        triggered_actions.append({
                            "rule_id": rule.id,
                            "rule_name": rule.name,
                            "action": "AUTO_PAUSE",
                            "entity": camp.meta_campaign_id,
                        })

            # 2. ALERT_LOW_VCC_BALANCE
            elif rule.rule_type == "ALERT_LOW_VCC_BALANCE":
                cards = db.execute(select(ExchangeCardSnapshot).order_by(desc(ExchangeCardSnapshot.read_at))).scalars().all()
                seen_cards = set()
                for card in cards:
                    if card.card_id in seen_cards:
                        continue
                    seen_cards.add(card.card_id)
                    if card.status == "ACTIVE" and card.available_balance is not None and card.available_balance < rule.threshold:
                        msg = (
                            f"⚠️ <b>QUY TẮC TỰ ĐỘNG: SỐ DƯ THẺ VCC XUỐNG THẤP</b>\n\n"
                            f"• Thẻ: <b>{card.card_name}</b> (**** {card.last4})\n"
                            f"• Số dư khả dụng: <b>{float(card.available_balance):,.2f} {card.currency}</b>\n"
                            f"• Ngưỡng cảnh báo: <b>{float(rule.threshold):,.2f} {rule.currency}</b>\n"
                            f"<i>Vui lòng nạp thêm tiền vào nguồn thẻ để không gián đoạn thanh toán ads.</i>"
                        )
                        telegram.send_admin_message(msg)
                        rule.last_triggered_at = utcnow()
                        rule.trigger_count += 1
                        triggered_actions.append({
                            "rule_id": rule.id,
                            "rule_name": rule.name,
                            "action": "TELEGRAM_ALERT",
                            "entity": f"card_{card.card_id}",
                        })

            # 3. ALERT_HIGH_DRIFT_SPEND
            elif rule.rule_type == "ALERT_HIGH_DRIFT_SPEND":
                recent_drifts = db.execute(
                    select(DriftRecord)
                    .where(DriftRecord.drift_amount > rule.threshold)
                    .order_by(desc(DriftRecord.checkpoint_at))
                    .limit(5)
                ).scalars().all()
                for dr in recent_drifts:
                    msg = (
                        f"⚠️ <b>QUY TẮC TỰ ĐỘNG: TIỀN TRÔI PHÁT SINH CAO</b>\n\n"
                        f"• Tiền trôi: <b>{float(dr.drift_amount):,.0f} {rule.currency}</b>\n"
                        f"• Ngưỡng cảnh báo: <b>{float(rule.threshold):,.0f} {rule.currency}</b>\n"
                        f"• Thời điểm mốc: {dr.checkpoint_at.isoformat() if dr.checkpoint_at else ''}"
                    )
                    telegram.send_admin_message(msg)
                    rule.last_triggered_at = utcnow()
                    rule.trigger_count += 1
                    triggered_actions.append({
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "action": "DRIFT_ALERT",
                        "entity": f"drift_{dr.id}",
                    })
                    break  # Gửi 1 thông báo đại diện tránh spam

            # 4. DAILY_REPORT_SCHEDULE
            elif rule.rule_type == "DAILY_REPORT_SCHEDULE":
                # Gửi báo cáo tóm tắt
                msg = (
                    "📊 <b>BÁO CÁO ĐỊNH KỲ TỰ ĐỘNG — ADS BUSINESS OS</b>\n\n"
                    "Hệ thống đã hoàn tất đánh giá các quy tắc tự động hóa và đồng bộ dữ liệu lúc này.\n"
                    "Gõ <code>/baocao today</code> trên bot để xem chi tiết chi phí & hiệu suất."
                )
                telegram.send_admin_message(msg)
                rule.last_triggered_at = utcnow()
                rule.trigger_count += 1
                triggered_actions.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "action": "DAILY_DIGEST",
                    "entity": "daily_summary",
                })

        except Exception as exc:
            logger.error("Lỗi khi đánh giá quy tắc %s (id=%s): %s", rule.name, rule.id, exc, exc_info=True)

    db.commit()
    return {
        "rules_checked": len(rules),
        "triggered_count": len(triggered_actions),
        "actions": triggered_actions,
    }
