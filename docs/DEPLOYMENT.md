# DEPLOYMENT.md — Triển khai thật (D-066)

> Kiến trúc kết nối thật cho Ads Business OS. Giai đoạn đầu chạy `APP_ENV=staging` (đọc thật, chưa ghi tiền thật) cho tới khi các câu hỏi nghiệp vụ còn treo (Q-005, Q-014…) được chốt.

## 1. Topology

```
                 ┌────────────────────────── Vercel ──────────────────────────┐
Người dùng ──►   │  Frontend Next.js  (ads.vextech.vn)                         │
                 │  NEXT_PUBLIC_API_URL = https://api.vextech.vn               │
                 └──────────────────────────┬─────────────────────────────────┘
                                            │ HTTPS
                 ┌──────────────── Server vextech (tiến trình thường trực) ────┐
                 │  Caddy (api.vextech.vn, Let's Encrypt)                      │
                 │     └─► uvicorn FastAPI :8000  (+ APScheduler, WebSocket)   │
                 └──────────────────────────┬─────────────────────────────────┘
                                            │ libSQL (HTTPS + authToken)
                                   ┌────────▼─────────┐
                                   │  Turso (libSQL)  │
                                   └──────────────────┘
```

**Vì sao tách backend khỏi Vercel:** APScheduler (sync hằng giờ, checkpoint 09:00, polling Telegram, keepalive token) cần tiến trình chạy liên tục. Vercel serverless không giữ tiến trình nền → scheduler không chạy. Backend phải ở server thường trực (vextech, hoặc Railway/Render/Fly).

## 2. Database — Turso (libSQL)

```powershell
# Cài driver
.venv\Scripts\python.exe -m pip install -r requirements-turso.txt

# Tạo DB trên Turso (CLI của Turso) rồi lấy URL + token
# ADSOS_DATABASE_URL dạng:
#   sqlite+libsql://<db>-<org>.turso.io/?authToken=<token>&secure=true
```

Migration (chạy thử trên **một DB Turso riêng** trước khi áp production — bắt buộc theo D-066):
```powershell
$env:ADSOS_DATABASE_URL = "sqlite+libsql://...staging...&secure=true"
.venv\Scripts\python.exe -m alembic upgrade head
```

## 3. Backend trên server vextech

1. Copy mã nguồn `apps/api`, tạo venv, `pip install -r requirements.txt -r requirements-turso.txt`.
2. Đặt biến môi trường (xem `infra/env/.env.example`), tối thiểu:
   ```
   ADSOS_APP_ENV=staging
   ADSOS_DATABASE_URL=sqlite+libsql://...&secure=true
   FACEBOOK_APP_ID=1129040860035919
   FACEBOOK_APP_SECRET=<app-secret>
   FACEBOOK_REDIRECT_URI=https://api.vextech.vn/api/v1/oauth/facebook/callback
   ADSOS_EXCHANGE_UI_ORIGINS=https://ads.vextech.vn
   ADSOS_STAFF_AUTH_SECRET=<chuỗi mạnh>
   ADSOS_EXCHANGE_MASTER_KEY=<32-byte Fernet base64>
   ADSOS_EXCHANGE_ADMIN_TOKEN=<>=32 ký tự>
   ```
3. Chạy (dùng process manager: systemd / pm2 / supervisor):
   ```
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
4. Đặt Caddy trước (`infra/Caddyfile`) để có HTTPS `api.vextech.vn`:
   ```
   caddy run --config infra/Caddyfile
   ```

## 4. Frontend trên Vercel

- Root directory: `apps/web`. Framework: Next.js (tự nhận).
- Project Settings → Environment Variables:
  ```
  NEXT_PUBLIC_API_URL = https://api.vextech.vn
  ```
- Gắn domain `ads.vextech.vn` vào project Vercel.

## 5. Phía Meta (App 1129040860035919)

- **App Domains:** `vextech.vn`
- **Site URL:** `https://ads.vextech.vn`
- **Facebook Login → Valid OAuth Redirect URIs:** `https://api.vextech.vn/api/v1/oauth/facebook/callback` (trùng khít `FACEBOOK_REDIRECT_URI`)
- App để **Development Mode** vẫn dùng được: Dev Mode chỉ giới hạn *ai* cấp quyền (tài khoản có vai trò app). Thêm các tài khoản Facebook quản lý TKQC vào **App Roles** và chấp nhận lời mời.
- Scope tối thiểu đọc: `ads_read`, `business_management`, `pages_show_list`. App Review chỉ cần khi mở cho tài khoản ngoài hoặc công khai.

## 6. Nghiệm thu kết nối

1. `https://api.vextech.vn/health` → `{"status":"ok"}`.
2. Mở `ads.vextech.vn/vias` → tạo VIA → cấp quyền Facebook → token dài hạn lưu mã hóa Fernet.
3. Scheduler tự đồng bộ; kiểm tra có `spend_snapshot` VERIFIED cho TKQC đầu tiên.

## 7. An toàn (bắt buộc)

- Giữ `ADSOS_META_WRITES_ENABLED=0` và `customer_sheets_writes_enabled` tắt tới khi chốt nghiệp vụ.
- Không để secret rỗng khi mở ra Internet; không commit `.env`/cert (đã có trong `.gitignore`).
- Caddyfile đã chặn `/docs`, `/api/v1/exchange/*` ngoài dải IP tin cậy — chỉnh dải IP cho đúng công ty bạn.
- `App Secret`, `authToken` Turso, master key: chỉ ở env phía backend, không ra frontend/log.

## 8. Backend trên Railway (chọn 2026-11-28 — vì hạ tầng là Vercel + Turso)

Vercel là serverless, không chạy được APScheduler/tiến trình nền của FastAPI. Backend đặt trên **Railway** (tiến trình thường trực, nối Git như Vercel); DB **Turso**; frontend **Vercel**.

Repo đã sẵn: `apps/api/Dockerfile` (cài `requirements-turso.txt`, CMD chạy `alembic upgrade head` rồi uvicorn theo `$PORT`) và `apps/api/railway.json` (healthcheck `/health`, 1 replica).

**Các bước (Railway dashboard):**
1. New Project → Deploy from GitHub repo → chọn `Davinci-MP/Ads-Business-OS`.
2. Service Settings → **Root Directory = `apps/api`** (monorepo).
3. Variables → đặt secret: `ADSOS_APP_ENV=staging`, `ADSOS_DATABASE_URL=sqlite+libsql://…turso.io/?authToken=…&secure=true`, `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_REDIRECT_URI=https://<railway-domain>/api/v1/oauth/facebook/callback`, `ADSOS_EXCHANGE_UI_ORIGINS=https://ads.vextech.vn`, `ADSOS_STAFF_AUTH_SECRET`, `ADSOS_EXCHANGE_MASTER_KEY`, `ADSOS_EXCHANGE_ADMIN_TOKEN`.
4. Deploy. Railway build Dockerfile → chạy migration lên Turso → start uvicorn.
5. Settings → Networking → **Generate Domain** (hoặc gắn `api.vextech.vn`). Kiểm `https://<domain>/health` → `{"status":"ok"}`.
6. Trên **Vercel** đặt `NEXT_PUBLIC_API_URL=https://<railway-domain>`; trên **Meta** thêm redirect URI đúng domain Railway.

> `numReplicas=1`: APScheduler + single-flight cần đúng 1 instance. Nếu build `libsql-experimental` lỗi thiếu wheel, đổi base trong Dockerfile sang `python:3.12` (full).

## 9. DB production: Railway Postgres (chọn 2026-11-28, D-067 — thay Turso)

Turso/libSQL gây lỗi driver khó khắc phục trên Railway. Chuyển sang **PostgreSQL** (plugin Railway cùng project), driver `psycopg`.

**Các bước:**
1. Railway project → **+ Create** → **Database** → **Add PostgreSQL**. Railway tạo service Postgres và tự cấp biến (`DATABASE_URL`, `PGHOST`...).
2. Service backend **Ads-Business-OS** → **Variables** → đặt:
   `ADSOS_DATABASE_URL = ${{Postgres.DATABASE_URL}}` (tham chiếu biến của service Postgres; tên service có thể là `Postgres`).
   - Không cần đổi scheme thủ công: `db.py` tự chuyển `postgresql://` → `postgresql+psycopg://`.
3. Giữ **Builder = Dockerfile** (Dockerfile nay cài `requirements-postgres.txt`).
4. Deploy. Dockerfile chạy `alembic upgrade head` lên Postgres rồi uvicorn.
5. Kiểm `https://<domain>/health` → `{"status":"ok"}`.

> Không còn dùng `ADSOS_DATABASE_URL` kiểu Turso. Xóa biến Turso cũ (và revoke token Turso đã lộ).
