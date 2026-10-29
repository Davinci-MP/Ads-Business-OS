# DEVELOPMENT_RULES.md — Quy tắc phát triển

> Chạy, kiểm thử, môi trường, an toàn dữ liệu. Lệnh chạy chính-xác được ghi lại ở đây sau khi scaffold xong — **trước đó không dùng lệnh chưa được kiểm chứng**.

## 1. Môi trường

| Môi trường | Mục đích | Giới hạn |
|---|---|---|
| `local` | Phát triển, hot reload | Không token thật; connector ngoài dùng mock |
| `staging` | Kiểm thử với dữ liệu thật | **Chỉ đọc** Meta/Sheets thật; KHÔNG ghi bảng Sheets thật |
| `production` | Vận hành | Mọi deploy phải được chủ dự án phê duyệt |

- Khác nhau qua biến `APP_ENV=local|staging|production` + file env tương ứng.
- Code phải có guard theo `APP_ENV` cho mọi thao tác ghi "thật" (Sheets, tiền) — chặn ở tầng app, không dựa vào config người dùng.

## 2. Chạy trên localhost (hot reload)

Yêu cầu: hệ thống phải chạy được trên localhost và tự cập nhật giao diện khi sửa code.

- Backend: FastAPI chạy chế độ reload.
- Frontend: Next.js dev mode.
- Local đầy đủ qua `docker compose` trong `infra/` (postgres + api + web + scheduler).

Lệnh dùng hàng ngày sẽ được bổ sung chính xác vào đây + `AGENTS.md` ngay sau khi scaffold (không đoán mò lệnh).

## 3. Google Sheets — quy tắc an toàn dữ liệu

- **Giữ nguyên cấu trúc, tên sheet, cột và công thức của bảng đang vận hành.** Không "dọn dẹp cho gọn".
- Staging chỉ đọc (service account có quyền Reader). Ghi thật chỉ khi:
  1. Có phê duyệt của chủ dự án (xem `docs/DECISIONS.md`);
  2. Dry-run vào bản copy của sheet trước;
  3. Backup dữ liệu cũ trước khi ghi;
  4. Audit log ghi nhận ai đã duyệt/execcuted gì, khi nào.
- Ghi được thực thi bằng **API chính thức** (service account), không qua headless browser.

## 4. Quy tắc viết code

- Không lưu secret/token trong mã nguồn; `.env` trong `.gitignore`; mỗi môi trường file env riêng.
- Ưu tiên SDK/API chính thức: Meta Marketing API, Google API client, python-telegram-bot, TRON API.
- Mọi job chạy nền phải **idempotent** (chạy lại không sinh dữ liệu trùng) và có retry có giới hạn.
- Migration (Alembic) phải có `upgrade()` và `downgrade()`.
- Services tách khỏi routers; connectors tách khỏi services (xem `PROJECT_ARCHITECTURE.md`).
- Comment code chỉ khi giải thích ý "tại sao" không tự hiểu được.

## 5. Kiểm thử (bắt buộc trước khi merge)

| Loại | Phạm vi |
|---|---|
| Unit | Công thức/lề đã duyệt, parse dữ liệu, mock Meta/Sheets/Telegram/TRON |
| Integration | Connector gọi staging (chỉ đọc), job sync 1 lần, API CRUD |
| Idempotency | Job chạy 2 lần → snapshot/số liệu không trùng, không nhảy vọt |
| Rollback | Migration revert được; ghi Sheets có backup restore được |

- CI chạy lint + test cho mọi PR (thiết lập sau scaffold).
- Không test ghi trực tiếp vào Sheets thật — test ghi chỉ trên bản copy.

## 6. Phê duyệt & khôi phục

- Deploy Production: chỉ khi chủ dự án phê duyệt. Trước deploy: backup DB + chạy pilot ở staging.
- Khi làm hỏng dữ liệu: dừng job liên quan, khôi phục từ backup, báo chủ dự án — không cố "sửa lại bằng tay" để che lỗi.
- Thay đổi quy tắc kinh doanh: phải được duyệt → ghi vào `docs/DECISIONS.md` → rồi mới sửa code. Không đảo ngược trình tự.
