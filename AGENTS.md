# AGENTS.md — Ads Business OS

## Lệnh chạy (PowerShell, Windows; chạy tại thư mục ghi rõ)

| Làm gì | Thư mục | Lệnh |
|---|---|---|
| Backend hot reload | `apps/api` | `.venv\Scripts\python.exe -m uvicorn app.main:app --reload` |
| Test toàn bộ backend | `apps/api` | `.venv\Scripts\python.exe -m pytest -q tests` |
| Test 1 file / lọc tên | `apps/api` | `.venv\Scripts\python.exe -m pytest -q tests\test_meta_sync.py` / `-k "tên"` |
| Migration | `apps/api` | `.venv\Scripts\python.exe -m alembic upgrade head` (SQLite mặc định; `ADSOS_DATABASE_URL` cho Postgres) |
| Web dev | `apps/web` | `npm.cmd run dev` (dùng `npm.cmd`, không `npm.ps1`) |
| Build web (gồm typecheck) | `apps/web` | `npm.cmd run build` |
| Full stack local | `infra` | `docker compose --env-file env\.env.example up` |

Không có lệnh lint/typecheck riêng cho backend; `npm.cmd run build` là bước kiểm tra frontend.

## Môi trường & biến quan trọng
- `APP_ENV=local|staging|production` — guard mọi ghi thật; staging chỉ đọc; production cần phê duyệt trước khi deploy
- SQLite chỉ local/test; production bắt buộc Postgres qua `ADSOS_DATABASE_URL`
- Windows + Python 3.14 cần `tzdata` (có trong `requirements.txt`) cho múi giờ `Asia/Ho_Chi_Minh`
- Secrets chỉ qua env; `.env` trong `.gitignore`; khóa JSON service account Google đặt **ngoài repo**, trỏ qua `ADSOS_GOOGLE_SERVICE_ACCOUNT_FILE`
- Meta API mặc định **v26.0** (env `ADSOS_META_API_VERSION`), hỗ trợ đọc và ghi (mutations) qua Session Cloud Hub & Extension per D-065, mock mode khi chưa có token, **không fallback live→mock khi lỗi**
- Session Cloud Hub (D-065): Trích xuất và đồng bộ session cookie (`c_user`, `xs`, `datr`), token EAAG, EAAB, fb_dtsg từ browser profiles VIA; mã hóa ở trạng thái nghỉ bằng Fernet; cho phép trạng thái campaign ACTIVE hoặc PAUSED.

## Kiến trúc (monorepo)
- `apps/api` — FastAPI: `app/main.py` entry; `app/api/v1/` chỉ route HTTP; nghiệp vụ ở `app/services/`; connector ngoài ở `app/connectors/` (Meta, Sheets, Telegram, TRON); `app/models/` SQLAlchemy; `app/jobs/` scheduler; `alembic/` migration (bắt buộc upgrade + downgrade)
- `apps/web` — Next.js App Router; `apps/web/lib/api.ts` client gọi backend; web không đọc Google Sheets trực tiếp
- Scheduler múi giờ Asia/Ho_Chi_Minh: sync hàng giờ + checkpoint 09:00 riêng; single-flight (1 fetch Meta/lượt), idempotent retry, lỗi Meta giữ nguyên dữ liệu cũ, grace 15 phút rồi `MISSED_CHECKPOINT`

## Quy tắc cứng (không ngoại lệ)
- Không tự tạo công thức tài chính/đối soát mới. Công thức đã duyệt ở `docs/DECISIONS.md`; chưa rõ → `NEEDS_CONFIRMATION`, hỏi chủ dự án; không tự chuyển NEEDS_CONFIRMATION thành đã duyệt.
- Không ghi dữ liệu thật vào Google Sheets / giao dịch tiền thật chưa phê duyệt. Staging chỉ đọc. Ghi thật qua approval flow + audit log + backup.
- Chi tiêu Meta = tổng tích lũy từ khi campaign bắt đầu. Mỗi lần cập nhật chỉ append snapshot mới (`(campaign_id, snapshot_at)` unique), không cộng dồn snapshot cũ; hiển thị snapshot VERIFIED mới nhất.
- `Tiền trôi = chi tiêu hiện tại − chi tiêu mốc 09:00` (cùng kỳ đối soát).
- Phí dịch vụ mặc định 4% (mức riêng của khách nếu đã xác nhận), khoản riêng, không gộp vào chi tiêu Meta.
- Chế độ chia 30/70 mặc định TẮT; công thức chia chưa duyệt → không triển khai.
- Dữ liệu API lỗi/không chắc chắn → giữ giá trị cũ, gắn `UNVERIFIED`, báo lỗi; không ghi đè bằng 0.
- Không xoá dữ liệu lịch sử — chỉ đổi trạng thái (ACTIVE/RESTRICTED/REPLACED/DEAD).
- Tiền tính bằng `Decimal`, làm tròn `ROUND_HALF_UP`; không dùng float/banker's rounding. Giữ riêng từng tiền tệ; không quy đổi/cộng chéo nếu chưa có tỷ giá duyệt.
- Không lưu secret/token trong mã nguồn, log, test, commit.

## Kiểm thử & merge
- Thêm/pytest test khi thay đổi hành vi (idempotency, giữ dữ liệu khi lỗi). Chạy test tập trung trước, rồi toàn bộ backend test + `npm.cmd run build` khi ảnh hưởng frontend.
- Migration phải reversible (upgrade/downgrade); chạy trên DB riêng trước khi áp local.
- Không test ghi trực tiếp vào Google Sheets thật.

## Kết thúc phiên
1. Cập nhật `docs/PROJECT_STATUS.md`.
2. Quyết định mới được chủ dự án duyệt → ghi vào `docs/DECISIONS.md`, loại khỏi NEEDS_CONFIRMATION.
3. Quy tắc kinh doanh chưa ghi chép → thêm `NEEDS_CONFIRMATION`, không tự hành động.

## Tài liệu tham khảo (tải qua opencode.json)
`docs/BUSINESS_RULES.md`, `docs/CAMPAIGN_RULES.md`, `docs/FINANCE_RULES.md`, `docs/PROJECT_ARCHITECTURE.md`, `docs/DEVELOPMENT_RULES.md`, `docs/DECISIONS.md`, `docs/PROJECT_STATUS.md`

## Skills (`.opencode/skills/`)
`meta-ads-sync`, `google-sheets`, `finance-reconciliation`, `telegram-automation`, `account-management`, `testing-and-security` — dùng khi đúng chủ đề.


## Kết nối sàn chỉ đọc (2026-10-29)
Đọc docs/BINANCE_CONNECTION.md trước khi sửa connector, form credentials hoặc scheduler sàn. Ngoại lệ secrets: API Key/Secret sàn nhập qua UI được mã hóa Fernet ở backend; master key và mã quản trị vẫn qua env, ngoài repo. Không dùng khóa đã lộ trong chat. Chỉ dùng test fixture theo schema API chính thức, không đặt tên trường quyền giả. Không cộng ví blockchain với tài khoản sàn. Không mở endpoint quản trị ra LAN/Internet.
