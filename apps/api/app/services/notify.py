"""Thông báo quản trị viên qua Telegram (S4) — không xác nhận thay đổi tài chính.

Nội dung:
- Kết quả đồng bộ checkpoint 09:00 (mode, số account ok, checkpoint ghi).
- Tài khoản lỗi / thiếu quyền (MetaAuthError nằm trong api_errors).
- Campaign UNRECOGNIZED cần kiểm tra.
- Chi tiêu bất thường (chi tiêu giảm → UNVERIFIED).
Mock mode (chưa cấu hình token) → chỉ buffer, KHÔNG gọi mạng.
"""

from __future__ import annotations

from typing import Any

from app.connectors.meta import MetaAuthError
from app.connectors.telegram import TelegramAPIError, TelegramBotConnector


def _mode_line(mode: str) -> str:
    return "🟢 <b>LIVE</b> (Meta thật)" if mode == "live" else "⚪ <b>MOCK</b> (dữ liệu giả lập)"


def format_sync_report(title: str, summary: dict[str, Any], mode: str) -> str:
    """Biên bản đồng bộ 1 lượt — chuẩn S4."""
    accounts_failed = sorted({err.split(":", 1)[0] for err in summary.get("api_errors", []) if ":" in err})
    lines = [
        f"<b>{title}</b>",
        _mode_line(mode),
        f"• Accounts sync OK: <b>{summary.get('accounts_synced', 0)}</b>",
        f"• Snapshot thêm: <b>{summary.get('snapshots_added', 0)}</b>"
        f" (checkpoint 9h: <b>{summary.get('checkpoints_9h', 0)}</b>)",
    ]
    if summary.get("unrecognized"):
        lines.append(f"⚠️ Campaign chưa nhận diện: <b>{len(summary['unrecognized'])}</b> — cần kiểm tra")
    if summary.get("unverified"):
        lines.append(f"🚨 Chi tiêu bất thường/UNVERIFIED: <b>{len(summary['unverified'])}</b>")
    if summary.get("api_errors"):
        auth = any(MetaAuthError.__name__ in err for err in summary["api_errors"])
        if auth:
            lines.append("🔐 <b>Token hết hạn/thiếu quyền</b> — cần cấp token `ads_read` mới")
        lines.append(f"❌ Lỗi API: <b>{len(summary['api_errors'])}</b> {accounts_failed}")
    return "\n".join(lines)


def notify_sync_result(
    title: str,
    summary: dict[str, Any],
    mode: str,
    notifier: TelegramBotConnector,
) -> bool:
    """Gửi một thông báo. Ném TelegramAPIError — caller chịu trách nhiệm queue/bỏ qua (D-031)."""
    notifier.send_admin_message(format_sync_report(title, summary, mode))
    return True
