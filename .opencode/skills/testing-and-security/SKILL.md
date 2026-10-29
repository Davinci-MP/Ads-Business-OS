---
name: testing-and-security
description: Use when writing or running tests (pytest, Next.js checks, job idempotency), deciding Staging vs Production behavior, handling secrets (.env, service account JSON, bot tokens, Meta access tokens), approval/audit flows for money-related writes, backup & recovery (rollback plans), or preparing anything for merge. Safe-data verification steps live here.
---

# Testing & Security

Kiểm tra và bảo mật toàn dự án. Đọc `docs/DEVELOPMENT_RULES.md` + `docs/PROJECT_ARCHITECTURE.md` trước.

## Nguyên tắc kiểm thử

1. Mọi hành vi kinh doanh phải có test bám theo đúng quy tắc trong `docs/` (unit + integration + idempotency).
2. **Job nền phải idempotent** — chạy nhiều lần không sinh trùng/nhảy số.
3. Migration Alembic bắt buộc có `upgrade()` + `downgrade()`.
4. Test chạy local không phụ thuộc prod; connector ngoài (Meta/Sheets/Telegram/TRON) dùng mock hoặc Staging read-only.

## Môi trường

- **Local:** không token thật; mọi connector mock/docker-compose.
- **Staging:** token **readonly thật** cho Meta/Sheets; **KHÔNG** ghi Sheets thật; ghi vào DB staging hoặc bản copy Sheets.
- **Production:** chỉ deploy sau phê duyệt chủ dự án; trước deploy phải có: backup DB, migration reverse plan.

## Bảo mật

1. Secret chỉ qua env; `.env` và `.env.*` nằm trong `.gitignore`; service-account JSON không nằm trong repo.
2. Không in log token/PII khách (chat Telegram, số tiền, lời nhắn).
3. Chỉ dùng API chính thức: Meta Marketing API, Google Sheets API, Telegram Bot API, TRON API.
4. Ghi tài chính thật phải qua `CREATED → APPROVED → EXECUTED` + audit log.
5. Trước khi merge: quét xem có secret lỡ vào mã nguồn (grep từ khoá `token`, `secret`, `api_key`, `password`); kiểm tra `.gitignore` còn phủ `.env`.

## Quy trình kiểm thử trước khi merge

1. **Unit/integration backend** (từ thư mục `apps/api`): `.venv\Scripts\python.exe -m pytest -q tests` (chạy full suite, hoặc tập con liên quan PR).
2. **Frontend** (từ thư mục `apps/web`): `npm.cmd run build` (PowerShell chặn `npm.ps1` — bắt buộc dùng `npm.cmd`). `npm run lint` chưa được kiểm chứng — không dùng cho tới khi được ghi vào `AGENTS.md`.
3. **Idempotency:** chạy job sync 2 lần → không snapshot mới trùng, tổng không nhảy vọt.
4. **Backup/restore test:** dump DB thử nghiệm → restore lại nguyên trạng.
5. Chỉ dùng lệnh đã kiểm chứng trong `AGENTS.md`; lệnh chưa có trong đó → không dùng (hỏi chủ dự án trước).


## Kết nối sàn chỉ đọc (2026-10-29)
Đọc docs/BINANCE_CONNECTION.md trước khi sửa connector, form credentials hoặc scheduler sàn. Ngoại lệ secrets: API Key/Secret sàn nhập qua UI được mã hóa Fernet ở backend; master key và mã quản trị vẫn qua env, ngoài repo. Không dùng khóa đã lộ trong chat. Chỉ dùng test fixture theo schema API chính thức, không đặt tên trường quyền giả. Không cộng ví blockchain với tài khoản sàn. Không mở endpoint quản trị ra LAN/Internet.
