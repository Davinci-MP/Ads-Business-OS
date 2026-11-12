"""Dịch vụ xử lý lệnh Telegram Bot Agent cho Ads Business OS (Báo cáo & Chiến dịch Meta Ads).

Tuân thủ nghiêm ngặt:
- Phân quyền Whitelist (chỉ chat ID được cấp phép mới được thực thi).
- Safe Write Guardrails (Tạo camp luôn ở trạng thái PAUSED, kiểm soát hạn mức ngân sách).
- Phản hồi 100% bằng Tiếng Việt (HTML formatting).
- Ghi nhật ký hoạt động (TelegramActivityLog) cho mọi lệnh nhận được.
"""

from __future__ import annotations

import logging
import re
import shlex
from typing import Any, Optional

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.connectors.meta import MetaAdsConnector, decrypt_token_if_encrypted
from app.connectors.telegram import TelegramBotConnector
from app.core.config import settings
from app.models.customer import Customer, utcnow
from app.models.telegram import TelegramActivityLog, TelegramBotConfig
from app.services.remote_commands import enqueue_set_camp

logger = logging.getLogger(__name__)


def get_configured_telegram_connector(db: Optional[Session] = None) -> TelegramBotConnector:
    """Khởi tạo TelegramBotConnector từ DB cấu hình (nếu có) hoặc từ env/settings."""
    if db is not None:
        try:
            cfg = db.execute(
                select(TelegramBotConfig)
                .where(TelegramBotConfig.is_active == True)
                .order_by(desc(TelegramBotConfig.id))
                .limit(1)
            ).scalar_one_or_none()
            if cfg:
                raw_tok = cfg.encrypted_bot_token or ""
                tok = decrypt_token_if_encrypted(raw_tok) or raw_tok
                allowed = [c.strip() for c in (cfg.allowed_chat_ids or "").split(",") if c.strip()]
                return TelegramBotConnector(
                    bot_token=tok or None,
                    admin_chat_id=cfg.admin_chat_id or None,
                    allowed_chat_ids=allowed,
                )
        except Exception as exc:
            logger.warning("Không thể đọc telegram_bot_configs từ DB: %s", exc)

    return TelegramBotConnector()


class TelegramBotAgent:
    """Agent tiếp nhận và điều phối các yêu cầu từ Telegram chat."""

    def __init__(
        self,
        meta_connector: Optional[MetaAdsConnector] = None,
        telegram_connector: Optional[TelegramBotConnector] = None,
    ) -> None:
        self.meta = meta_connector or MetaAdsConnector()
        self.telegram = telegram_connector or TelegramBotConnector()

    def process_update(self, session: Session, update: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Tiếp nhận Telegram Update object từ webhook hoặc polling."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return None

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()
        from_user = message.get("from", {})
        username = from_user.get("username") or from_user.get("first_name") or str(chat_id)

        if not chat_id or not text:
            return None

        update_id = str(update.get("update_id")) if update.get("update_id") is not None else None
        if update_id and session.scalar(
            select(TelegramActivityLog.id).where(TelegramActivityLog.update_id == update_id)
        ):
            return {"status": "duplicate", "chat_id": chat_id}

        # 1. Kiểm tra Whitelist Security Gate & Admin Policy trên BM/Khóa TK
        ADMIN_COMMANDS = {"/khoatkn", "/khoatk", "/set_bm", "/setbm", "/bm_pref"}
        cmd_first = text.split()[0].lower().split("@")[0]
        admin_command = cmd_first in ADMIN_COMMANDS
        is_admin = bool(self.telegram.admin_chat_id and str(chat_id) == str(self.telegram.admin_chat_id))
        natural_setcamp = re.match(
            r"^\s*set\s+ads\s+tài\s+khoản\s+(?:id\s*:?\s*)?([0-9a-zA-Z_]+)\s+theo\s+(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        is_setcamp = cmd_first in {"/setcamp", "/set_camp", "/autocamp"} or natural_setcamp is not None
        linked_customer = session.scalar(
            select(Customer).where(Customer.telegram_chat_id == str(chat_id))
        )

        if is_setcamp and linked_customer is None:
            reject_msg = "⛔ Lỗi: Telegram của bạn chưa được liên kết với khách hàng nào trên hệ thống."
            self.telegram.send_message(chat_id, reject_msg)
            session.add(
                TelegramActivityLog(
                    update_id=update_id,
                    chat_id=str(chat_id),
                    username=username,
                    command=text[:255],
                    response_summary=reject_msg,
                    status="REJECTED",
                )
            )
            session.commit()
            return {"status": "rejected", "chat_id": chat_id, "reason": "customer_not_linked", "text": reject_msg}

        if not is_setcamp and not self.telegram.is_chat_allowed(chat_id):
            reject_msg = (
                f"⛔ <b>Từ chối truy cập</b>\n\n"
                f"Chat ID <code>{chat_id}</code> chưa được phân quyền tương tác với Ads Business OS.\n"
                f"Vui lòng cấu hình <code>ADSOS_TELEGRAM_ALLOWED_CHAT_IDS</code>."
            )
            self.telegram.send_message(chat_id, reject_msg)
            try:
                log = TelegramActivityLog(
                    update_id=update_id,
                    chat_id=str(chat_id),
                    username=username,
                    command=text[:255],
                    response_summary=reject_msg[:250],
                    status="REJECTED",
                )
                session.add(log)
                session.commit()
            except Exception:
                session.rollback()
            return {"status": "rejected", "chat_id": chat_id, "reason": "unauthorized"}

        if admin_command and not is_admin:
            reject_msg = (
                f"⛔ <b>Từ chối thực thi lệnh quản trị</b>\n\n"
                f"Lệnh <code>{cmd_first}</code> chỉ dành riêng cho Quản trị viên (Admin).\n"
                f"Chat ID <code>{chat_id}</code> không có quyền cấu hình BM hoặc khóa tài khoản."
            )
            self.telegram.send_message(chat_id, reject_msg)
            try:
                log = TelegramActivityLog(
                    update_id=update_id,
                    chat_id=str(chat_id),
                    username=username,
                    command=text[:255],
                    response_summary=reject_msg[:250],
                    status="REJECTED",
                )
                session.add(log)
                session.commit()
            except Exception:
                session.rollback()
            return {"status": "rejected", "chat_id": chat_id, "reason": "admin_only"}

        # 2. Điều phối lệnh Bot hoặc Tự động phân loại tác vụ khách hàng
        sender_name = from_user.get("first_name") or username
        raw_tg_username = from_user.get("username")

        # Kiểm tra mẫu lệnh tự nhiên: "set ads tài khoản ID: <act_id> theo <draft>"
        nat_match = natural_setcamp
        if nat_match:
            act_arg = nat_match.group(1).strip()
            draft_arg = nat_match.group(2).strip()
            reply_text = self._handle_remote_setcamp(
                session=session,
                act_id_input=act_arg,
                draft_input=draft_arg,
                chat_id=str(chat_id),
                username=raw_tg_username,
            )
        elif text.startswith("/"):
            reply_text = self.dispatch_command(
                session,
                text,
                actor=f"tg_{username}",
                chat_id=str(chat_id),
                username=raw_tg_username,
            )
        else:
            from app.services.task_dispatcher import dispatch_client_message
            res = dispatch_client_message(
                session=session,
                chat_id=str(chat_id),
                username=from_user.get("username"),
                sender_name=sender_name,
                message_text=text,
                telegram_connector=self.telegram,
            )
            reply_text = res["reply_text"]
        if reply_text:
            self.telegram.send_message(chat_id, reply_text)
            # Ghi Activity Log
            try:
                log = TelegramActivityLog(
                    update_id=update_id,
                    chat_id=str(chat_id),
                    username=username,
                    command=text[:255],
                    response_summary=reply_text[:250],
                    status="SUCCESS",
                )
                session.add(log)
                session.commit()
            except Exception:
                session.rollback()
            return {"status": "processed", "chat_id": chat_id, "text": reply_text}

        return {"status": "ignored", "chat_id": chat_id}

    def dispatch_command(
        self,
        session: Session,
        command_line: str,
        actor: str = "telegram_bot",
        chat_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> str:
        """Phân tích cú pháp và thực thi lệnh bằng Tiếng Việt."""
        cmd_line = command_line.strip()
        if not cmd_line:
            return ""

        parts = cmd_line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd in ("/start", "/help", "tro-giup", "help"):
                return self._cmd_help()
            elif cmd in ("/setcamp", "/set_camp", "/autocamp"):
                if len(args) >= 2:
                    return self._handle_remote_setcamp(
                        session=session,
                        act_id_input=args[0],
                        draft_input=" ".join(args[1:]),
                        chat_id=chat_id or "0",
                        username=username,
                    )
                return "⚠️ Cú pháp: <code>/setcamp &lt;act_id&gt; &lt;tên_chiến_dịch&gt;</code>"
            elif cmd in ("/tk", "/accounts", "/taikhoan"):
                return self._cmd_accounts()
            elif cmd in ("/baocao", "/report"):
                return self._cmd_report(args, session)
            elif cmd in ("/lencamp", "/createcamp"):
                return "⚠️ Backend không tạo chiến dịch trực tiếp. Hãy dùng <code>/setcamp &lt;act_id&gt; &lt;tên_chiến_dịch&gt;</code>."
            elif cmd in ("/batcamp", "/startcamp", "/activate"):
                return "⛔ Không hỗ trợ bật chiến dịch từ backend. Mọi chiến dịch mới luôn ở trạng thái PAUSED."
            elif cmd in ("/tatcamp", "/pausecamp", "/deactivate"):
                return "⚠️ Lệnh thay đổi Meta phải được xếp hàng cho Chrome Extension; backend không gọi Meta trực tiếp."
            elif cmd in ("/khoatkn", "/khoatk"):
                if len(args) != 1:
                    return "Cú pháp: /khoatk &lt;mã_tài_khoản&gt; (hoặc /khoatkn &lt;mã_tài_khoản&gt;)"
                from app.services.meta_risk import lock_account
                result = lock_account(session, self.meta, args[0], actor)
                return result["message"]
            elif cmd in ("/set_bm", "/setbm", "/bm_pref"):
                return self._cmd_set_bm(session, args, actor=actor)
            elif cmd in ("/status", "/trangthai"):
                return self._cmd_status()
            else:
                return (
                    f"❓ Lệnh không hợp lệ: <code>{cmd}</code>\n"
                    f"Gõ <code>/help</code> để xem danh sách các câu lệnh được hỗ trợ."
                )
        except Exception as exc:
            logger.error("Lỗi thực thi lệnh Telegram [%s]: %s", cmd_line, exc, exc_info=True)
            return f"❌ <b>Thực thi thất bại:</b>\n<i>{str(exc)}</i>"

    def _cmd_help(self) -> str:
        max_budget = settings.meta_max_daily_budget
        return (
            "🤖 <b>ADS BUSINESS OS — TRỢ LÝ ĐIỀU KHIỂN & BÁO CÁO</b>\n\n"
            "Danh sách lệnh được hỗ trợ:\n"
            "• <code>/tk</code> hoặc <code>/accounts</code>: Xem danh sách tài khoản quảng cáo và tình trạng cước.\n"
            "• <code>/baocao [account_id] [preset]</code>: Báo cáo hiệu suất (preset: <i>today, yesterday, last_7d, this_month</i>).\n"
            "• <code>set ads tài khoản ID: &lt;act_id&gt; theo &lt;tên_chiến_dịch&gt;</code> hoặc <code>/setcamp &lt;act_id&gt; &lt;tên_chiến_dịch&gt;</code>:\n"
            "  Xác thực quyền sở hữu rồi xếp lệnh cho Chrome Extension; chiến dịch mới luôn là <b>PAUSED</b>.\n"
            "• <code>/status</code>: Kiểm tra trạng thái hệ thống.\n\n"
            "• <code>/set_bm &lt;client_id&gt; &lt;BM_01|BM_02|BM_03&gt; [EMPLOYEE|ADMIN] [FULL|PARTIAL]</code>: Cấu hình phân quyền và định tuyến BM tự động.\n"
            "• <code>/khoatk &lt;account_id&gt;</code> (hoặc <code>/khoatkn</code>): Khóa an toàn và dừng khẩn cấp mọi chiến dịch của tài khoản.\n"
            f"🛡️ <i>Rào chắn an toàn: Backend không ghi Meta; hạn mức tối đa {max_budget:,.0f} đ/ngày; trạng thái khởi tạo luôn là PAUSED.</i>"
        )

    def _cmd_status(self) -> str:
        mode_meta = self.meta.mode
        mode_tg = self.telegram.mode
        telemetry = getattr(self.meta, "telemetry", None)
        util = telemetry.max_util_pct if telemetry else 0.0

        return (
            "⚙️ <b>TRẠNG THÁI HỆ THỐNG ADS BUSINESS OS</b>\n\n"
            f"• Meta Ads Connector: <b>{mode_meta.upper()}</b> (v{self.meta.api_version})\n"
            f"• Rate-limit Usage: <b>{util:.1f}%</b> {'(⚠️ Đang làm chậm chủ động)' if util >= 80 else '(Bình thường)'}\n"
            f"• Telegram Agent: <b>{mode_tg.upper()}</b> ({len(self.telegram.allowed_chat_ids)} chats được phép)\n"
            f"• Hạn mức ngân sách ngày tối đa: <b>{settings.meta_max_daily_budget:,.0f} đ</b>"
        )

    def _cmd_accounts(self) -> str:
        accounts = self.meta.get_ad_accounts()
        if not accounts:
            return "ℹ️ Không tìm thấy tài khoản quảng cáo nào được liên kết."

        lines = ["📊 <b>DANH SÁCH TÀI KHOẢN QUẢNG CÁO</b>\n"]
        for acc in accounts:
            act_id = acc["meta_ad_account_id"]
            name = acc.get("name") or act_id
            curr = acc.get("currency", "USD")

            health = self.meta.get_ad_account_billing_health(act_id)
            status_label = health.get("account_status_label", "Hoạt động")
            status_emoji = "🟢" if health.get("account_status") == 1 else "🔴"
            spent = health.get("amount_spent", 0.0)
            balance = health.get("balance", 0.0)

            lines.append(
                f"{status_emoji} <b>{name}</b> (<code>{act_id}</code>)\n"
                f"   • Trạng thái: {status_label}\n"
                f"   • Đã chi tiêu: {spent:,.0f} {curr} | Nợ cước: {balance:,.0f} {curr}\n"
            )

        return "\n".join(lines)

    def _cmd_report(self, args: list[str], session: Session | None = None) -> str:
        preset = "today"
        account_id: Optional[str] = None

        if len(args) == 1:
            if args[0] in ("today", "yesterday", "last_7d", "this_month"):
                preset = args[0]
            else:
                account_id = args[0]
        elif len(args) >= 2:
            account_id = args[0]
            preset = args[1]

        target_accounts = []
        if account_id:
            act_fmt = account_id if account_id.startswith("act_") else f"act_{account_id}"
            target_accounts = [act_fmt]
        else:
            acc_list = self.meta.get_ad_accounts()
            target_accounts = [a["meta_ad_account_id"] for a in acc_list]

        if not target_accounts:
            return "ℹ️ Không có tài khoản nào để lập báo cáo."

        preset_names = {
            "today": "Hôm nay",
            "yesterday": "Hôm qua",
            "last_7d": "7 ngày qua",
            "this_month": "Tháng này",
        }
        period_title = preset_names.get(preset, preset)

        blocks = [f"📈 <b>BÁO CÁO HIỆU SUẤT ({period_title.upper()})</b>\n"]

        total_spend = 0.0
        total_clicks = 0
        total_impressions = 0
        total_conv = 0
        total_msgs = 0

        for act_id in target_accounts:
            if session is not None:
                from app.services.meta_account_policy import validate_account_policy
                validate_account_policy(session, self.meta, act_id)
            insights = self.meta.get_performance_insights(act_id, date_preset=preset)
            if not insights:
                blocks.append(f"• <code>{act_id}</code>: Chưa có dữ liệu phát sinh trong kỳ.")
                continue

            for row in insights:
                spend = row.get("spend", 0.0)
                imp = row.get("impressions", 0)
                clicks = row.get("clicks", 0)
                ctr = row.get("ctr", 0.0)
                cpc = row.get("cpc", 0.0)
                cpm = row.get("cpm", 0.0)
                conv = row.get("conversions", 0)
                msg = row.get("messages", 0)

                total_spend += spend
                total_clicks += clicks
                total_impressions += imp
                total_conv += conv
                total_msgs += msg

                cname = row.get("campaign_name") or row.get("campaign_id")
                blocks.append(
                    f"🎯 <b>{cname}</b> (<code>{act_id}</code>)\n"
                    f"   • Chi phí: <b>{spend:,.0f} đ</b>\n"
                    f"   • Lượt hiển thị: {imp:,} | Click: {clicks:,} (CTR: {ctr:.2f}%)\n"
                    f"   • CPC: {cpc:,.0f} đ | CPM: {cpm:,.0f} đ\n"
                    f"   • Chuyển đổi / Tin nhắn: <b>{conv}</b> / <b>{msg}</b>\n"
                )

        blocks.append(
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>TỔNG CỘNG:</b>\n"
            f"• Chi tiêu: <b>{total_spend:,.0f} đ</b>\n"
            f"• Lượt click: <b>{total_clicks:,}</b> (Hiển thị: {total_impressions:,})\n"
            f"• Chuyển đổi: <b>{total_conv}</b> | Tin nhắn: <b>{total_msgs}</b>"
        )

        return "\n".join(blocks)

    def _handle_remote_setcamp(
        self,
        session: Session,
        act_id_input: str,
        draft_input: str,
        chat_id: str,
        username: Optional[str] = None,
    ) -> str:
        """Xác thực bằng chat_id rồi chỉ xếp lệnh; backend không gọi Meta write API."""
        try:
            command = enqueue_set_camp(
                session,
                chat_id=str(chat_id),
                act_id=act_id_input,
                campaign_name=draft_input,
            )
        except PermissionError as exc:
            if str(exc) == "TELEGRAM_NOT_LINKED":
                return "⛔ Lỗi: Telegram của bạn chưa được liên kết với khách hàng nào trên hệ thống."
            clean_act = act_id_input.strip()
            return f"⛔ Lỗi: Bạn không có quyền điều khiển tài khoản {clean_act}."
        except ValueError as exc:
            return f"⚠️ Lỗi: {exc}"

        return (
            f"✅ Đã tiếp nhận lệnh Set Camp cho tài khoản {command.act_id}. "
            "Đang đưa vào hàng đợi để Extension xử lý..."
        )

    def _cmd_set_bm(self, session: Session, args: list[str], actor: str = "admin") -> str:
        """Cấu hình và ghi nhớ phân quyền BM cho khách hàng (/set_bm <client_id> <bm_id> [role] [access_type])."""
        if len(args) < 2:
            return (
                "⚠️ <b>Cú pháp lệnh chưa đầy đủ:</b>\n"
                "<code>/set_bm &lt;client_id&gt; &lt;BM_01|BM_02|BM_03&gt; [EMPLOYEE|ADMIN] [FULL|PARTIAL]</code>\n\n"
                "<i>Ví dụ:</i> <code>/set_bm 1 BM_01 EMPLOYEE FULL</code>"
            )
        try:
            client_id = int(args[0])
        except ValueError:
            return "❌ ID khách hàng phải là một số nguyên (ví dụ: 1, 2, 3)."

        preferred_bm_id = args[1].upper()
        bm_role = args[2].upper() if len(args) > 2 else "EMPLOYEE"
        access_type = args[3].upper() if len(args) > 3 else "FULL"

        from app.services.auto_fulfillment import (
            ACCESS_TYPE_LABELS,
            AVAILABLE_BMS,
            BM_ROLE_LABELS,
            apply_admin_bm_selection,
        )

        if preferred_bm_id not in AVAILABLE_BMS:
            valid_bms = ", ".join(AVAILABLE_BMS.keys())
            return f"❌ Mã BM <code>{preferred_bm_id}</code> không hợp lệ. Các BM khả dụng: {valid_bms}"

        try:
            res = apply_admin_bm_selection(
                session=session,
                client_id=client_id,
                preferred_bm_id=preferred_bm_id,
                bm_role=bm_role,
                ad_account_access_type=access_type,
                actor=actor,
            )
            bm_name = AVAILABLE_BMS.get(preferred_bm_id, {}).get("full_name", preferred_bm_id)
            return (
                "✅ <b>ĐÃ THIẾT LẬP & GHI NHỚ CẤU HÌNH PHÂN QUYỀN BM!</b>\n\n"
                f"• Khách hàng: <b>{res['client_name']}</b> (ID: <code>{client_id}</code>)\n"
                f"• BM tiếp nhận: <b>{bm_name}</b>\n"
                f"• Vai trò BM: <b>{BM_ROLE_LABELS.get(res['bm_role'], res['bm_role'])}</b>\n"
                f"• Quyền TKQC: <b>{ACCESS_TYPE_LABELS.get(res['ad_account_access_type'], res['ad_account_access_type'])}</b>\n"
                f"• Số tác vụ liên quan đã cập nhật: <b>{res['updated_tasks_count']}</b>\n\n"
                "⚡ <i>Hệ thống sẽ tự động ghi nhớ và áp dụng cấu hình này cho mọi yêu cầu sau của khách hàng!</i>"
            )
        except Exception as exc:
            return f"❌ Không thể lưu cấu hình BM: {str(exc)}"
