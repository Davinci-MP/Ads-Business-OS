---
name: telegram-automation
description: Use when building or debugging the Telegram Bot — customers requesting campaigns, incident reporting, admin notifications (low balance, unrecognized campaigns, failed jobs), TG Bot API webhooks/polling, or mapping telegram chat ids to customers. The bot must never confirm real money actions without a checked approval.
---

# Telegram Automation

Telegram Bot phục vụ: khách **tạo yêu cầu campaign**, **báo sự cố**, hệ thống gửi **thông báo** (checkpoint lỗi, số dư thấp, campaign `UNRECOGNIZED`).

## Nguyên tắc

1. `TELEGRAM_BOT_TOKEN` từ biến môi trường; webhook phải verify secret; token không bao giờ log.
2. Chat ID ↔ khách mapping lưu trong DB; không tin username (thay đổi được).
3. Yêu cầu của khách (tạo campaign) → tạo **request** trong DB → admin phê duyệt → hệ thống mới thực hiện. Bot KHÔNG tự mở campaign hoặc tự xác nhận tiền.
4. Thông báo tự động chỉ là **thông báo**: lỗi job, kết quả checkpoint 9h, số dư thấp (ngưỡng chờ Q-008), tiền trôi phát hiện.
5. Mọi update xử lý phải idempotent (update_id trùng → bỏ qua); log mọi interactions. Gửi thông báo lỗi Telegram → message ghi vào `telegram_outbox` (PENDING), retry ở lần chạy sau (D-031, đã implement `flush_outbox` trong `app/jobs/meta_sync_job.py`) — kết quả đồng bộ không bị mất khi Telegram lỗi.
6. Validate payload, rate-limit đơn giản, không tin message ngoài domain.

## Quy trình

1. Nhận message → resolve khách (chat_id → customer).
2. Phân loại yêu cầu: `NEW_CAMPAIGN` / `INCIDENT` / `OTHER` → tạo record yêu cầu.
3. Gửi xác nhận đã nhận yêu cầu tới khách; tag/gửi thông báo tới admin để ra quyết định.
4. Thông báo hệ thống: push qua bot tới group admin (sự cố checkpoint, cảnh báo công nợ).

## Quy trình kiểm thử

- **Unit:** parse/command; resolve khách theo chat_id; idempotent update_id.
- **Integration:** dùng bot mock — assert đã gửi đúng message tới đúng chat; retry không sinh trùng.
- **Scenario:** low-balance event → admin nhận cảnh báo; request campaign mới → admin có notify; khách KHÔNG nhận được xác nhận tiền tự động.
- Lệnh chạy (đã kiểm chứng, từ thư mục `apps/api`): `.venv\Scripts\python.exe -m pytest -q tests` — test Telegram hiện nằm trong `tests/test_scheduler.py` (bot mock).
