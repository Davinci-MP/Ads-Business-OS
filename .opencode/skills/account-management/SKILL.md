---
name: account-management
description: Use when managing the 31 customers and their Facebook assets — CRUD for khach hang (customers), ad accounts, Business Managers; replacing restricted/closed accounts; assigning accounts to customers over time (N-N history); campaign ownership and reporting periods; or building the dashboard REST endpoints for these entities.
---

# Account Management

Quản lý các entity kinh doanh: **khách hàng, ad account, BM, liên kết và lịch sử thay thế**. Đọc `docs/BUSINESS_RULES.md` + `docs/PROJECT_ARCHITECTURE.md` §3 trước.

## Nguyên tắc

1. **Không xoá** chỉ đổi trạng thái (`ACTIVE`, `RESTRICTED`, `REPLACED`, ...).
2. **Thay account giữ history**: account cũ → status `REPLACED` + linkage tới account thay thế; campaign cũ vẫn nối account cũ.
3. Mỗi khách dùng nhiều account; một account trong một thời điểm chỉ gán cho **một** khách — nếu phát hiện dùng shared account giữa các khách đồng thời → gắn `NEEDS_CONFIRMATION`.
4. Campaign chỉ được tạo/ghi nhận khi thuộc khách + kỳ rõ ràng; không tự tạo campaign qua bot (xem skill `telegram-automation`).

## Mô hình CRUD (FastAPI — đã implement S5)

- Bảng: `customers`, `ad_accounts` (có `purchase_cost`), `ad_account_assignments` (valid_from/valid_to), `campaigns` — theo `docs/PROJECT_ARCHITECTURE.md` §3; migration `7d2e4a61c5f9`.
- REST: `app/api/v1/dashboard.py` (endpoints `POST /customers`, `POST /ad-accounts`, gán/thay account, chi phí mua) + `app/services/accounts.py`; mọi mutation ghi audit log, không xoá lịch sử.
- Guard đã có (đã kiểm thử): 1 account = 1 khách tại một thời điểm; chỉ gán account `ACTIVE`; thay account → `REPLACED` + `replaced_by` + đóng `valid_to`.

## Quy trình kiểm thử

- **Unit:** tạo/sửa/khóa; assign account; **thay thế**: status account cũ `REPLACED` + history giữ nguyên, không mất assignment cũ.
- **Constraint:** assign account không `ACTIVE` phải bị chặn; DELETE phải bị chặn (chỉ được đổi status).
- **Seed:** 31 khách theo danh sách thật của chủ dự án (danh sách KHÔNG có trong repo — xin trực tiếp).
- Lệnh chạy (đã kiểm chứng, từ thư mục `apps/api`): `.venv\Scripts\python.exe -m pytest -q tests` — test liên quan: `tests/test_dashboard_s5.py` (tạo khách/account, guard gán/thay).
