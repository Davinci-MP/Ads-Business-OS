---
name: finance-reconciliation
description: Use when handling money logic — cong no (debt), deposits (nap tien), USDT TRC20 wallet transactions, exchange rates (USDT/VND, ty gia thanh toan), phi 4% service fee on actual spend (default), chia chenh lech 30/70 manual adjustment mode, balance warnings, tien troi formula (current spend minus 09:00 checkpoint), or reconciling spend between Meta/Postgres/Google Sheets. NEVER invent financial formulas; confirmed formulas live in docs/DECISIONS.md only.
---

# Finance Reconciliation

Kiểm soát mọi logic tiền. **Agent không tự đặt ra công thức tài chính.** Công thức đã duyệt nằm trong `docs/FINANCE_RULES.md` + `docs/DECISIONS.md`; chưa có → gắn `NEEDS_CONFIRMATION` và hỏi chủ dự án.

## Nguyên tắc

1. **Tách sổ**: chi tiêu thực / đối soát theo hợp đồng / phí tài khoản / phí thẻ / lợi nhuận — mỗi khoản một ledger riêng, không trộn.
2. Chống ghi trùng là **ràng buộc tầng DB** (unique: tx hash, idempotency key) — không chỉ ở tầng app.
3. **Nạp USDT**: chỉ ghi công nợ cho khách khi match chắc chắn (hash + số tiền + khung thời gian + khách khai báo). Chưa match → pool `UNMATCHED`, không cộng dư khách.
4. **Phí dịch vụ (D-021)**: mặc định 4% trên chi tiêu thực (Meta Ads đã đối soát): `phí = chi tiêu × 4%`, `tổng = chi tiêu + phí`. Khoản riêng trong ledger, không gộp vào chi tiêu Meta. Config `customers.fee_rate` cho phép phí riêng từng khách; KHÔNG đổi mặc định 4%.
5. **Chế độ chia lợi nhuận 30/70 (D-022)**: mặc định TẮT (`customers.recon_mode = SIMPLE_FEE`). Chỉ chủ dự án bật (`PROFIT_SHARE`) mới được tạo điều chỉnh thủ công — nhập tay vào `manual_adjustments`, flow `DRAFT → APPROVED → APPLIED`, có audit. KHÔNG suy diễn số liệu từ Meta; KHÔNG đổi số chi tiêu thực. KHÔNG implement/chạy công thức chia cho tới khi được duyệt chính thức (Q-004).
6. **Tiền trôi (D-023)**: `tiền trôi = chi tiêu hiện tại − chi tiêu mốc 09:00`. Phí 4% tính lại trên chi tiêu hiện hành sau mỗi lần cập nhật. Meta điều chỉnh muộn → tạo phiên bản tạm tính mới (TEMP), giữ nguyên lịch sử đã chốt (FINAL).
7. Tỷ giá lấy từ bảng `exchange_rates` (config), ghi kèm giá trị + nguồn + thời điểm áp dụng. Nguồn dữ liệu tỷ giá mặc định → `NEEDS_CONFIRMATION` (Q-005) — chưa duyệt thì không tự cài nguồn.
8. Mọi hành động tiền thật phải qua **approval flow**: `CREATED → APPROVED → EXECUTED` + audit log. Bot Telegram tự động **không được** tự xác nhận tiền.
9. Số liệu nghi ngờ: giữ số cũ, giá trị mới gắn `UNVERIFIED`.

## Quy trình đối soát

1. Đọc chi tiêu tích lũy từ Postgres (source of truth của hệ; xem skill `meta-ads-sync`).
2. Đọc số Sheets hiện hành (skill `google-sheets`, chỉ đọc).
3. Tính chênh lệch **theo công thức đã duyệt**; xuất báo cáo per khách/campaign, ghi rõ nguồn số.
4. Nếu cần cập nhật Sheets → tạo write-request, không ghi trực tiếp.

## Quy trình kiểm thử

Kiểm thử theo 2 chế độ đối soát (D-025), **khách thông thường trước, sau đó chế độ điều chỉnh thủ công với dữ liệu mẫu**:

- **Khách thông thường (fee 4%):**
  - Phí dịch vụ = chi tiêu thực × 4%; tổng = chi tiêu + phí.
  - Phí là khoản riêng (entry_kind `SERVICE_FEE`), không trộn entry `ACTUAL_SPEND`.
  - Tính lại phí trên chi tiêu hiện hành → phải tạo phiên bản mới; entry đã `FINAL` (đã chốt) không bị ghi đè.
- **Chế độ điều chỉnh thủ công (30/70):**
  - Khách chưa bật chế độ → tạo điều chỉnh phải bị từ chối.
  - Khách đã bật → tạo điều chỉnh DRAFT; chưa APPROVED không được APPLIED; mọi thao tác có audit log.
  - Công thức chia lợi nhuận (Q-004) chưa duyệt → KHÔNG có/implement hàm tính chia.
- **Tiền trôi:** checkpoint 09:00 = 100, hiện tại = 130 → trôi = 30; tính theo công thức D-023.
- **Idempotency:** chèn lại giao dịch USDT cùng tx hash → KHÔNG tạo bản mới; assert có cảnh báo.
- **Approval flow:** giao dịch chưa `APPROVED` → bị chặn, không `EXECUTED`.
- **UNMATCHED:** giao dịch không match được khách → vào pool, dư khách không đổi.
- Lệnh chạy (đã kiểm chứng, từ thư mục `apps/api`): `.venv\Scripts\python.exe -m pytest -q tests` — test liên quan: `tests/test_finance_rules.py`, `tests/test_manual_adjustments.py`, `tests/test_drift_rules.py`.
