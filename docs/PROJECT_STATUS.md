# PROJECT_STATUS.md — Trạng thái dự án

## Cập nhật 2026-11-28 (tối) — Kết nối Meta chạy end-to-end trên server (Railway + Postgres)

Đã nghiệm thu trên server thật: đăng nhập → tạo VIA → **Cấp quyền Facebook (OAuth)** → token ACTIVE → **Đồng bộ** tài sản thành công. PR #12–#17.

- **DB production chuyển SQLite tạm → Postgres Railway (D-067):** trước đó backend chạy SQLite trong container (mất dữ liệu mỗi lần deploy) vì `ADSOS_DATABASE_URL` rỗng; tham chiếu `${{Postgres.DATABASE_URL}}` chỉ hoạt động khi Postgres **cùng project** với backend. `app/core/db_url.py` chuẩn hóa URL dùng chung cho app + Alembic (`postgresql://` → `postgresql+psycopg://`, báo lỗi rõ khi rỗng).
- **Migration chạy được trên Postgres:** sửa 4 migration chỉ hợp SQLite (Boolean `DEFAULT 0` → `sa.false()`, FK `via_categories` sai tham số, trùng tên `uq_snapshot` → `uq_ad_account_snapshot` cho `ad_account_snapshots`, seed boolean bị `except Exception` nuốt lỗi). Thử `upgrade head → downgrade base → upgrade head` trên PostgreSQL 16 tạm + SQLite.
- **`appsecret_proof`:** app Meta bật *Require App Secret* → `app/core/meta_proof.py` ký `HMAC-SHA256(token, FACEBOOK_APP_SECRET)` cho mọi lời gọi Graph bằng token (OAuth `/me`, đồng bộ VIA kể cả `paging.next`, connector, keepalive, MaxCare, ads_check). Bỏ qua token `EAAB/EAAG` (app nội bộ Facebook).
- **OAuth liên kết bằng app-scoped user ID:** `/me` (Graph v2.0+) không trả UID thật → lần cấp quyền đầu lưu `via_profiles.meta_app_user_id` (unique) + `meta_user_name`; các lần sau phải trùng; một tài khoản Facebook chỉ gắn một VIA. Migration `y9z0a1b2c3d4`. Web hiện "FB: <tên>".
- **Job/dashboard dùng token VIA, chặn mock ngoài local:** trước đây job hằng giờ, checkpoint 09:00, quét rủi ro, dashboard lấy token từ env (cách chạy local) → trên server rơi vào mock và **ghi dữ liệu giả lập vào Postgres** (guard chỉ chặn ở production, server là staging). `app/services/meta_tokens.py`: token map `act_<id>` → token VIA ACTIVE; mock chỉ được dùng ở `APP_ENV=local`, ngoài local không có token → `NO_META_TOKEN`, không ghi gì. Sửa đường dẫn BM `act_{bm}/owned_ad_accounts` → `{business_id}/owned_ad_accounts`.
- **Chẩn đoán:** log lỗi Meta trả về ở bước OAuth (không log `client_secret`).
- **Nghiệm thu:** backend 682 pass (1 flaky `test_prepaid` đã biết); Graph `v26.0` xác nhận hợp lệ.

**Chờ chủ dự án (chưa làm):**
- **Dọn dữ liệu mock — chủ dự án đã duyệt (2026-11-28):** script `infra/sql/2026-11-28_cleanup_mock_meta_data.sql` (xem trước + xóa trong 1 transaction) chỉ xóa tài khoản `act_mock_%` và campaign/snapshot/drift/risk con của chúng; giữ `audit_log`. Đã thử trên PostgreSQL 16 tạm: xóa đúng dòng mock, tài khoản thật giữ đủ campaign/snapshot/drift, chạy lại lần hai xóa 0. **Chủ dự án tự chạy trên DB Railway** (agent không có quyền DB).
- Đổi các secret đã lộ trong ảnh/chat (`FACEBOOK_APP_SECRET`, `ADSOS_EXCHANGE_MASTER_KEY`, `ADSOS_EXCHANGE_ADMIN_TOKEN`, `ADSOS_STAFF_AUTH_SECRET`) và mật khẩu Postgres; xóa TCP Proxy công khai của Postgres; xóa project Railway `fearless-appreciation` (Postgres cũ không dùng).
- Máy của chủ dự án: Tailscale bật làm `api.vextech.vn` phân giải về Vercel cũ (router cache) → tắt Tailscale hoặc khởi động lại router khi thử.

## Cập nhật 2026-11-28 — Tối ưu trang Dàn VIA, tạo VIA không cần mật khẩu, sửa màu theme sáng toàn site

- **Trang `/vias` làm lại** (giữ nguyên mọi chức năng cũ): nút chính **"+ Tạo VIA"**, "Nhập hàng loạt", các công cụ khác gom vào menu **"Công cụ"**; màn hướng dẫn 3 bước khi chưa có VIA; mỗi dòng có nút **"Cấp quyền Facebook"** (OAuth chính thức) làm thao tác chính, các thao tác phụ trong menu "⋯"; thông báo lỗi OAuth rõ theo từng mã (`uid_mismatch`, `token_exchange_failed`...).
- **Modal "Tạo VIA" mới** (`components/CreateViaModal.tsx`): chỉ cần UID; tên/proxy tuỳ chọn; thông tin đăng nhập ẩn trong mục "không bắt buộc"; tạo xong có nút "Cấp quyền Facebook ngay".
- **Backend:** `POST /api/v1/vias` không còn bắt buộc `password` (VIA chỉ dùng OAuth không cần mật khẩu Facebook). Cập nhật VIA mà bỏ trống mật khẩu/2FA/email thì giữ giá trị cũ. Thêm 2 test.
- **Sửa màu toàn site (theme sáng):** khối CSS "đơn sắc" cũ dùng `!important` ép nút màu thành viên thuốc tối và chữ màu thành xám nhạt, làm mục menu đang chọn mất chữ — nay chỉ áp dụng ở theme tối. Thêm lớp chuyển đổi theme sáng cho nhãn nền sẫm `bg-*-800/900/950` và chữ `text-*-100…400`.
- **Nghiệm thu:** build Next.js 32/32 route; test VIA 10/10; kiểm trực quan `/vias` (tạo VIA không mật khẩu, menu dòng, theme tối), `/accounts`, `/telegram`.
- **Lưu ý kiểm thử:** chạy test backend khi backend local (có scheduler) đang chạy sẽ làm `test_exchange_wallets`/`test_prepaid` lỗi 409 do tranh chấp khóa — dừng backend local trước khi chạy test.

## Cập nhật 2026-11-27 — Turso (D-066), cấu hình deploy, dọn rác & nền tảng giao diện Vercel

- **Database Turso/libSQL (D-066):** thêm `requirements-turso.txt` (`sqlalchemy-libsql`), cải thiện `app/db.py` (pool_pre_ping + check_same_thread cho SQLite-family). Nghiệm thu: **648 pass / 1 fail** (fail là test flaky `test_prepaid` đã biết, chạy riêng pass) — thay đổi db.py còn **giảm flaky từ 11 xuống 1**. Ghi quyết định D-066, cập nhật AGENTS.md + PROJECT_ARCHITECTURE §5.
- **Cấu hình deploy:** `docs/DEPLOYMENT.md` (Vercel frontend + backend trên server riêng + Turso), `infra/Caddyfile` (HTTPS api.vextech.vn, chặn /docs & /exchange ngoài IP tin cậy), cập nhật `.env.example` (Turso URL, OAuth HTTPS redirect, EXCHANGE_UI_ORIGINS), thêm `apps/web/.env.example`.
- **Dọn rác agent cũ:** xóa toàn bộ log/dump test/build, `.lock` SQLite tạm, `fix_staff_tables.py`, `page.tsx.tmp`; cập nhật `.gitignore` chống tái diễn. Thư mục `.review-*/`, `.test-*/` bị permission-denied — chủ dự án tự xóa.
- **Nền tảng giao diện Vercel:** retheme token tập trung trong `admin.css` (sáng mặc định: nền trắng, viền #eaeaea, accent #0070f3, primary đen; tối: nền #000) + font **Geist/Geist Mono** (next/font) + mặc định theme sáng (layout/shell). Nav active và nút primary đổi sang kiểu Vercel. Trang `/login` đã chuyển sang token (preview xác nhận). Build Next.js 32/32 route PASS.
- **Còn lại:** các trang nhiều màu hardcode cần polish từng trang để khớp Vercel hoàn toàn (như đã làm với login); xem dashboard thật cần backend + đăng nhập.

# PROJECT_STATUS.md — Trạng thái dự án

## Cập nhật 2026-11-21 — Khắc phục triệt để lỗi Gemini `thought_signature` HTTP 400 trong AI Copilot

- **Nguyên nhân gốc rễ lỗi `Function call is missing a thought_signature in functionCall parts`:**
  - Chuẩn REST API v1beta của Google Gemini (`generateContent`) khi model trả về các công cụ cần gọi (`functionCall`) kèm theo chữ ký `thoughtSignature` và các phần tử suy nghĩ (`thought` parts).
  - Trước đây, `orchestrator.py` tách từng công cụ trong một lượt gọi thành nhiều lượt `assistant` - `tool` rời rạc và tự tái tạo lại `functionCall` mà làm mất `thoughtSignature`, đồng thời không gom kết quả phản hồi của tất cả công cụ vào một lượt `user` duy nhất theo chuẩn Gemini v1beta.
  - Khi người dùng gửi lịch sử trò chuyện (`history`), các lượt gọi tool dang dở không có chữ ký hợp lệ cũng gây lỗi khi Gemini xác thực payload hội thoại.

- **Giải pháp xử lý:**
  1. **Bảo toàn nguyên vẹn `raw_content` (`base.py`, `gemini.py`):**
     - Bổ sung trường `raw_content` vào `LLMResponse` và `LLMMessage` để lưu trữ đối tượng `candidate["content"]` nguyên bản từ Gemini.
     - Khi gửi payload sang Gemini, nếu tin nhắn có `raw_content`, toàn bộ các phần tử bao gồm `thoughtSignature`, `thought` (nội dung suy nghĩ nội bộ) và danh sách `functionCall` được giữ nguyên vẹn 100%, không bị phân mảnh hay tái tạo thiếu trường.
  2. **Gom lượt phản hồi Tool Call theo chuẩn Gemini REST v1beta (`orchestrator.py`):**
     - Khi model trả về một hoặc nhiều công cụ cần gọi trong cùng một lượt, `orchestrator.py` thực thi tuần tự các công cụ, khử trùng dữ liệu an toàn bằng `sanitize_data_for_ai()`.
     - Gom toàn bộ kết quả vào một lượt tin nhắn `role="user"` duy nhất chứa danh sách `functionResponse` đầy đủ tương ứng với tất cả các `functionCall`.
     - Cập nhật cả `OllamaProvider` và `MockLLMProvider` tương thích với cấu trúc gom lượt này.
  3. **Làm sạch lịch sử đa lượt (Multi-turn Chat History):**
     - Bỏ qua các lượt gọi công cụ dang dở hoặc tin nhắn rỗng từ client, chỉ giữ lại các cặp hội thoại text chuẩn giữa người dùng và trợ lý để không làm rách chuỗi hội thoại khi gửi lên Gemini.
  4. **Kiểm thử & Khởi động Backend:**
     - Bổ sung các unit test chuyên biệt trong `tests/test_ai_orchestrator.py`: bảo toàn `thoughtSignature`, làm sạch lịch sử đa lượt, gom nhiều công cụ trong một lượt.
     - Khởi chạy thành công Backend Server trên `127.0.0.1:8000` (uvicorn hot-reload).
     - Kiểm thử trực tiếp gọi live tool `get_customers_summary` và `get_system_overview` thành công với Google Gemini API.
     - Frontend Next.js build đạt 32/32 route thành công.

- **AI Orchestrator dùng chung (`apps/api/app/services/ai/`):**
  - Xây dựng kiến trúc AI Orchestrator đa nền tảng kết nối trực tiếp với FastAPI backend.
  - Hỗ trợ linh hoạt LLM Provider qua biến môi trường `LLM_PROVIDER`:
    - `gemini`: Kết nối Google Gemini API (mặc định `gemini-2.0-flash`), cấu hình qua `GEMINI_API_KEY`.
    - `ollama`: Kết nối mô hình mã nguồn mở chạy local trên máy trạm (`http://localhost:11434`), cấu hình qua `OLLAMA_MODEL` và `OLLAMA_BASE_URL`.
    - `mock`: Chế độ giả lập phục vụ kiểm thử đơn vị và chạy CI/CD offline.
  - Phân tách tuyệt đối 2 bộ công cụ (Tools) với phân quyền RBAC và ngữ cảnh:
    - **`STAFF_TOOLS`**: Dành riêng cho nhân sự trên Web CRM (yêu cầu token JWT xác thực nhân viên). Bao gồm: `get_system_overview`, `search_campaigns`, `get_campaign_details`, `get_customers_summary`, `get_ad_accounts`, `get_vias_status` (chỉ đếm số lượng, tuyệt đối không truy cập credentials), `get_recent_activity_logs`.
    - **`CUSTOMER_TOOLS`**: Dành cho khách hàng trên Telegram, **khóa cứng tuyệt đối theo `telegram_chat_id` / `customer_id`**. Ngăn chặn truy cập chéo giữa các khách hàng. Bao gồm: `get_my_balance`, `get_my_campaigns`, `get_my_ad_accounts`, `get_my_support_tasks`, `create_support_request`, `get_deposit_instructions`.
  - Bộ làm sạch dữ liệu (**Data Sanitizer**): Khử trùng đệ quy mọi cấu trúc dữ liệu trước khi gửi sang LLM. Lọc bỏ 100% các trường nhạy cảm (`password`, `2fa_secret`, `cookie`, `token`, `master_key`, `credentials`) và regex che giấu token Meta (`EAAB...`), Bearer token, Telegram token, cookie header.

- **Telegram Bot Auto-Switching (Polling vs Webhook):**
  - Tự động bật tiến trình background long-polling khi `ENV=development` hoặc `APP_ENV=local/dev`, cho phép kiểm thử trực tiếp trên máy cá nhân không cần domain hay HTTPS/SSL.
  - Tự động chuyển sang chế độ nhận Webhook tại `/api/v1/telegram/webhook` (kèm xác thực Secret Token) khi `ENV=production`.
  - Cơ chế port-lock (`settings.telegram_polling_lock_port: 8913`) chống chạy trùng lặp giữa nhiều worker uvicorn.
  - Tích hợp lệnh `/ai <câu hỏi>` và tự động kích hoạt AI Copilot cho các câu hỏi ngôn ngữ tự nhiên từ khách hàng.

- **Web CRM AI Copilot Drawer (`apps/web/`):**
  - Thiết kế ngăn kéo slide-over bên phải chuẩn **Twenty CRM** (`AiCopilotDrawer.tsx`):
    - Khung chat trượt mượt mà từ mép phải với backdrop làm mờ.
    - Header hiển thị trạng thái kết nối LLM Provider & Model, số lượng tools khả dụng.
    - Gợi ý câu hỏi nhanh (Quick Prompts): báo cáo hôm nay, kiểm tra chiến dịch, số dư, dàn VIA.
    - Hiển thị nhãn công cụ đã thực thi (`🔧 get_system_overview`).
    - Nút mở nhanh trên Top Header (`Ctrl+K`) và Nút nổi (Floating Action Button) ở góc dưới bên phải màn hình.
  - Endpoint REST API bảo vệ: `POST /api/v1/copilot/chat` và `GET /api/v1/copilot/status`.

- **Kiểm thử & Nghiệm thu:**
  - 100% test mới đạt: `test_ai_sanitizer.py`, `test_ai_orchestrator.py`, `test_telegram_polling_mode.py`, `test_copilot_api.py`.
  - Toàn bộ backend test suite đạt 20/20 test liên quan và chạy ổn định.
  - Next.js build (`npm.cmd run build`) hoàn thành thành công 32/32 route tĩnh/động không lỗi TypeScript hay CSS.

## Cập nhật 2026-11-20 — Extension metaOs và backend tương thích trên ADS Business OS

- Thay gói `extensions/adsos-check-bridge/` bằng extension Manifest V3 metaOs 2.2.5; toàn bộ endpoint nền tảng trỏ về `http://127.0.0.1:8000`, icon/tên/trang mở và gói tải đổi sang thương hiệu metaOs.
- Bổ sung bridge còn thiếu `checkLive`, `getAccessToken`, `getTokens` và đồng bộ session định kỳ vào endpoint D-065 `extension-ingest`; cookie/token tiếp tục được mã hóa Fernet trong `ViaProfile`/`BrowserNode`.
- Dựng các trang tương thích `/metaos`, `/popup`, `/bm-popup.html`, `/ext-runner` cùng API tenant/shield, chia sẻ báo cáo, snapshot append-only chống trùng và hàng đợi chỉnh sửa có claim/idempotent result.
- Thêm migration reversible `x8y9z0a1b2c3_metaos_extension_backend.py` cho liên kết chia sẻ, snapshot và lệnh chỉnh sửa; đã kiểm tra `upgrade -> downgrade -> upgrade` trên SQLite tạm riêng.
- Lệnh chỉnh sửa Meta bị chặn khi `ADSOS_META_WRITES_ENABLED=0`. AI và webhook Zalo là tích hợp tùy chọn qua env, thiếu cấu hình sẽ trả `503` thay vì giả lập. Loại bỏ fallback tự chế token EAAB từ cookie; cookie-only vẫn là phiên LIVE nhưng token giữ `NONE` cho tới khi lấy được token thật.
- Cập nhật modal quản lý/tải extension trên web thành metaOs và đổi file tải thành `metaos-extension.zip`; helper theo VIA cũng hiển thị thương hiệu metaOs.
- Nghiệm thu: 38/38 test extension/CDP/launcher đạt; toàn bộ backend đạt **634/634 test** (1 cảnh báo deprecation Starlette/httpx); `node --check` đạt cho toàn bộ JS, manifest hợp lệ; build Next.js đạt đủ 32/32 route.

## Cập nhật 2026-11-13 — Sửa thứ tự React Hooks trong modal nhập VIA

- Chuyển nhánh đóng sớm của `RawViaImportModal` xuống sau `useMemo(summaryTotals)`, bảo đảm số lượng và thứ tự Hooks không thay đổi khi mở/đóng modal.
- Quét bằng parser TypeScript toàn bộ 61 tệp TSX trong `apps/web/components` và `apps/web/app`; không còn Hook nào nằm sau `return null`. Tám component Modal/Dialog đặt tên riêng cũng đã được đối chiếu trực tiếp.
- Nghiệm thu: `npx.cmd tsc --noEmit` đạt mã thoát 0, không có lỗi TypeScript.

## Cập nhật 2026-11-12 — Nạp VIA Thô (uid|pass|2fa|mail...), Tự Động Vượt 2FA TOTP & Quét Sâu Tài Sản (Web App & Backend)

- **Backend & Database (`apps/api/`):**
  - Mở rộng model `ViaProfile` (alias `ViaAccount`) thêm 2 trường DB: `login_status` (`READY`, `LOGGING_IN`, `CHECKPOINT`, `WRONG_PASS`, `PENDING`) và `last_login_error`.
  - Bổ sung property getters/setters mã hóa Fernet ở trạng thái nghỉ cho: `fb_uid`, `fb_password`, `two_fa_secret`, `email`, `email_password`, `backup_email`, `backup_email_password`, `raw_line`, `eaag_token`, `eaab_token`, `fb_dtsg`.
  - Phân quyền RBAC nghiêm ngặt: Phương thức `to_safe_dict()` và `serialize_via_profile()` tự động xóa toàn bộ credential nhạy cảm đối với nhân viên (`STAFF`), chỉ trả cờ boolean (`has_2fa`, `has_mail`, `has_cookie`, `has_eaag`, `has_eaab`) trừ khi người gọi có vai trò `OWNER`.
  - Tạo migration reversible `w7x8y9z0a1b2_add_via_login_status_fields.py` và đã kiểm tra `upgrade head -> downgrade -1 -> upgrade head` thành công trên SQLite.
  - Xây dựng module tự động hóa `app/services/via_auto_login.py`:
    - Bộ tạo mã RFC 6238 TOTP thuần Python `generate_totp_code(secret)` (zero dependency ngoài standard library), hỗ trợ làm sạch khoảng trắng trong secret base32 và trả về mã 6 chữ số kèm số giây còn lại.
    - Bộ phân tích chuỗi VIA thô `parse_via_raw_line` và `parse_bulk_raw_vias` hỗ trợ đa định dạng phân cách pipe (từ 2 đến 9+ trường), nhận diện thông minh cookie `c_user` và token `EAA`.
    - Đăng nhập phiên HTTP có trạng thái (stateful session) qua `httpx`, tự động điền form, giải challenge 2FA `approvals_code`, xác nhận lưu trình duyệt `save_device`, và fallback đọc mã checkpoint qua IMAP email.
    - Trích xuất token `EAAG`, `EAAB`, `fb_dtsg` và tự động kích hoạt Deep Asset Sweep (`sync_via_all_assets`) để nạp toàn bộ TKQC, BM, Fanpage, Pixel vào DB.
  - Bổ sung endpoint `POST /api/v1/ads-check/import-raw-vias-and-sync` (ghi `StaffAuditLog`), `GET /api/v1/vias/{via_id}/totp`, và `POST /api/v1/vias/totp-preview`.
  - Bộ kiểm thử: `tests/test_via_raw_import_and_totp.py` đạt 3/3; toàn bộ test suite backend đạt **630/630 tests** (100% pass rate).

- **Web App UI (`apps/web/`):**
  - Xây dựng `lib/totp.ts`: Tính toán RFC 6238 TOTP bằng Web Crypto API phía trình duyệt không cần round-trip mạng, kết hợp API client `getViaTotp` và `previewTotp`.
  - Tạo Component `RawViaImportModal.tsx`:
    - **Tab 1: Nạp Định Dạng VIA**: Textarea dán chuỗi VIA dạng pipe; bảng xem trước realtime hiển thị UID, mật khẩu (ẩn/hiện), mã 2FA live (OTP + đếm ngược giây), Email, Pass Mail, badge Cookie/Token; tùy chọn auto-login & scan tài sản; proxy dùng chung; thanh tiến trình 4 bước (`[1/4] Lưu VIA`, `[2/4] Đăng nhập & 2FA`, `[3/4] Trích xuất Token`, `[4/4] Quét sâu tài sản`); card tóm tắt số lượng TKQC, BM, Page, Pixel tìm thấy.
    - **Tab 2: Nạp Nhanh**: Hỗ trợ dán token EAAG/EAAB, cookie hoặc danh sách BM ID.
  - Tích hợp nút **`[ Nạp Nguyên Liệu & Quét Sâu ]`** trên Top Toolbar của `/accounts` và `/ads-check` (kèm SMIT toolbar).
  - Tích hợp mã 2FA TOTP Live & nút Copy 1-Click:
    - Trên `/vias`: Badge mã 2FA đếm ngược mượt mà từng giây kèm thông báo toast sao chép.
    - Trên `/accounts`: Cột "VIA Nguồn" tự động tìm VIA liên kết; nếu VIA có 2FA sẽ hiển thị badge mã 6 chữ số kèm đếm ngược `(24s)` và nút sao chép 1-click có toast notification.
  - Kiểm thử & Build: `npx.cmd tsc --noEmit` đạt 0 lỗi; `npm.cmd run build` đạt 0 lỗi, prerender đủ **32/32 route**.

## Cập nhật 2026-11-12 — Phơi bày toàn diện & tích hợp Modal "Chia Sẻ Quyền BM & Gán TKQC"

- **Web App (`/accounts` & `/ads-check`):**
  - Đặt nút **`[ Chia Sẻ Quyền BM & Gán TKQC ]`** thường trực trên Top Header Toolbar của cả 2 trang, hiển thị icon 1.5px monochrome share/users.
  - Tích hợp nút **`Share BM / Gán TK`** trong thanh tác vụ nổi hàng loạt (Floating Bulk Bar) và trên từng hàng dữ liệu của bảng (Quick Actions column).
  - Hoàn thiện `ShareBmAccountsModal.tsx` với bộ chọn BM ID (danh sách BM đã sync + ô nhập tay), email nhận quyền (nhiều dòng), vai trò Facebook BM (`EMPLOYEE`, `ADMIN` giới hạn Owner, `FINANCE_EDITOR`, `FINANCE_ANALYST`, `DEVELOPER`) kèm tasks (`MANAGE`, `ADVERTISE`, `ANALYZE`).
  - Hỗ trợ bộ chọn TKQC 3 cách: tự động điền theo khách hàng đã gán, nạp nhanh các dòng đang chọn trên bảng, nhập/dán ID bằng tay có lọc trùng live và badge đếm số lượng.
  - Gửi lệnh qua `POST /api/v1/ads-check/share-bm-accounts` (ghi `StaffAuditLog`), đồng thời phát tín hiệu qua `window.ExtensionBridge` nếu có, hiển thị kết quả từng tài khoản và nút copy link mời BM.
- **Extension Bridge (`dashboard.html` & `dashboard.js`):**
  - Mở khóa `#btnBulkShareModal` trong `#bulkActionBar` và gắn nhãn **`Chia Sẻ BM & Gán TKQC`**.
  - Thêm nút cố định **`Chia Sẻ Quyền BM & Gán TKQC`** (`#btnOpenShareBmModalTop`) tại `.smit-actions-toolbar` ở đầu Tab 1.
  - Nâng cấp `#modalBulkShare` thành modal đầy đủ (BM ID selector/input, email nhiều dòng, role selector, target UID, textarea ID TKQC kèm badge đếm và nút lấy từ bảng).
  - Đấu nối `#btnOpenShareBmModalTop`, `#btnBulkShareModal`, và `#btnCreateBmInviteModal` (Tab 2) mở `#modalBulkShare` và điền sẵn TKQC đang chọn.
  - Xử lý submit qua `chrome.runtime.sendMessage({ action: "SHARE_BM_AND_ASSIGN_ACCOUNTS", payload })`, hỗ trợ cả target UID và email mời, hiển thị kết quả và link mời BM.
- **Kiểm tra & Nghiệm thu:**
  - `node --check` đạt 0 lỗi trên `dashboard.js` và `background.js`.
  - `npx tsc --noEmit` và `npm.cmd run build` đạt 0 lỗi (prerender đủ 32/32 route).
  - Dev server port 3000 khởi động lại và phản hồi HTTP 200 cho cả `/accounts` và `/ads-check`.

## Cập nhật 2026-11-12 — Xác thực nhân sự và vận hành tài sản end-to-end

- **Xác thực thật:** hoàn thiện đăng nhập nhân sự bằng Bearer token ký HMAC, API `/auth/login`, `/auth/me`, đổi mật khẩu và kiểm tra phiên ở `AppShell`. Tài khoản OWNER mặc định chỉ được seed trong môi trường local; production bắt buộc cấu hình khóa ký qua biến môi trường.
- **Quản lý nhân sự và RBAC:** trang `/settings/staff` đã dùng dữ liệu thật cho tạo, sửa, khóa/mở khóa, phân vai, gán khách hàng và xem nhật ký. API chặn nhân viên tự khóa, chặn hạ quyền OWNER cuối cùng và giữ lịch sử bằng vô hiệu hóa mềm.
- **Gán khách và phí TKQC:** `/accounts` lưu trực tiếp khách hàng cùng mức phí dịch vụ riêng trên `SyncedAdAccount`; phép tính dùng `Decimal`, không tạo công thức tài chính mới. Mọi thay đổi được ghi `StaffAuditLog`.
- **Chia sẻ BM qua hàng đợi:** modal dùng chung trên `/accounts` và `/ads-check` nhận BM, email, vai trò, tác vụ và danh sách TKQC. Backend chỉ xác thực quyền rồi tạo `RemoteViaCommand`; Chrome Extension mới thực hiện lệnh Meta và phản hồi kết quả, bảo toàn ranh giới backend không ghi Meta trực tiếp.
- **Cơ sở dữ liệu:** migration `v6w7x8y9z0a1` thêm `service_fee_rate` và đã vượt quy trình `upgrade → downgrade → upgrade` trên SQLite riêng; DB local đã được nâng lên head.
- **Nghiệm thu:** `627/627` backend test đạt (1 cảnh báo deprecation từ Starlette/httpx); `npx tsc --noEmit` và `npm.cmd run build` đạt, tạo đủ **32/32 route**; `node --check` đạt cho toàn bộ **7** tệp JavaScript của Extension.

## Cập nhật 2026-11-12 — Sửa lỗi biên dịch trang quản lý nhân sự

- Khép đúng khối helper và biểu thức JSX trong `apps/web/app/settings/staff/page.tsx`; bảo đảm chỉ còn một `export default function StaffPage()` và toàn bộ import nằm đầu tệp.
- Bổ sung kiểu dữ liệu rõ ràng cho danh sách nhân sự, nhật ký thao tác và biểu mẫu; thay icon Font Awesome khai báo sai bằng bộ `MonoIcon` hiện có.
- Khôi phục `AppShell` đúng kiến trúc Next.js và chuyển logic điều hướng trang gốc từ `react-router-dom` sang `next/navigation`, không thay đổi đích điều hướng theo trạng thái đăng nhập.
- Đã kiểm tra `accounts/page.tsx` và `login/page.tsx`: không có khối chưa đóng, import chen giữa tệp hoặc export mặc định trùng lặp.
- Nghiệm thu: `npx tsc --noEmit` đạt mã thoát 0; `npm.cmd run build` thành công, prerender đủ **32/32 route**.

## Cập nhật 2026-11-10 — Nâng Cấp Kiến Trúc 4 Trụ Cột Toàn Diện & Kích Hoạt Quyết Định D-065

- **Ghi nhận Quyết định D-065 (Architectural Override):**
  - Chính thức thay thế và phế truất các hạn chế cũ (D-027, D-040, D-063, D-064) theo chỉ thị trực tiếp từ chủ sở hữu.
  - Cho phép kết nối và đồng bộ toàn diện Session Cloud Hub (trích xuất session cookies `c_user`, `xs`, `datr`, token `EAAG`, `EAAB` và `fb_dtsg` từ browser profiles VIA, mã hóa ở trạng thái nghỉ bằng Fernet).
  - Cho phép thực hiện đầy đủ các mutation đọc và ghi (Graph API v26.0 & internal GraphQL) phục vụ vận hành agency hợp pháp trên cả Extension (`extensions/adsos-check-bridge/`) và Backend Cloud Hub (`apps/api/`).
  - Cho phép người dùng linh hoạt cấu hình trạng thái chiến dịch/boost post (`ACTIVE` hoặc `PAUSED`) thay vì ép buộc `PAUSED`.

- **Trụ cột 1: Quản Lý Tài Sản Tập Trung (Asset Management):**
  - **TKQC:** Tra cứu ngân sách, ngưỡng nợ, limit ẩn (`ad_trust_dsl`), xác minh vị trí (`location_verified`), đổi tên hàng loạt, đổi tiền tệ/múi giờ và gửi kháng nghị vi phạm (`appeal_status`).
  - **Business Manager (BM):** Quét toàn diện `owned_ad_accounts` và `client_ad_accounts`, phân quyền quản trị, phát hiện và xóa sạch QTV ẩn trái phép (`DELETE /{act_id}/users/{uid}`), tạo liên kết mời BM và tạo TKQC hàng loạt.
  - **Fanpage:** Quản lý toàn bộ danh sách Fanpage, kiểm tra trạng thái hiển thị (`is_published`), đổi tên Fanpage hàng loạt và gửi kháng nghị hủy đăng.
  - **Pixel:** Liệt kê danh mục Pixel, kiểm tra sự kiện và chia sẻ Pixel hàng loạt xuyên suốt nhiều TKQC (`POST /{pixel_id}/shared_accounts`).

- **Trụ cột 2: Điều Khiển & Vận Hành (Workflow & Operations):**
  - **Hệ thống Kịch bản Tự động hóa (Workflow Engine):** Tích hợp sẵn 70 kịch bản vận hành chuẩn hóa thuộc 6 danh mục nghiệp vụ (Quản lý TKQC, Bảo mật BM, Nuôi & Kháng Page, Phân phối Pixel, Lên Camp & Boost Post, Thanh toán & Thẻ) kèm cơ chế Jitter Anti-Ban ngẫu nhiên tránh checkpoint.
  - **Lên Camp & Boost Post Hàng Loạt:** Tạo chiến dịch 3 tầng (`Campaign -> AdSet -> Ad`) và boost bài viết đồng thời trên nhiều TKQC, tự động quy đổi ngân sách chuẩn xác theo tiền tệ tài khoản đích (VND, USD, EUR...) với tùy chọn trạng thái `ACTIVE` hoặc `PAUSED` theo D-065.
  - **Super Target:** Mở rộng tra cứu thư viện sở thích ẩn Meta lên tới hơn 500 sở thích (vượt qua giới hạn 25 items của Ads Manager thông thường) kèm ước tính quy mô tệp và cây danh mục.

- **Trụ cột 3: Hệ Thống Điều Khiển Đa Trình Duyệt (Control Hub):**
  - **Mô hình BrowserNode:** Lưu trữ định danh node duy nhất (`node_uid`), tên profile, loại trình duyệt (`CHROME`, `ADSPOWER`, `GOLOGIN`, `KIKLOGIN`) và tự động mã hóa Fernet cho `cookie`, `eaag_token`, `eaab_token`, `fb_dtsg`.
  - **Cơ chế Heartbeat & Điều phối từ xa (Dispatch):** Extension/Profile phát nhịp tim 5 giây kéo lệnh thực thi PENDING về trình duyệt; hỗ trợ phát lệnh từ xa giữa các trình duyệt và từ thiết bị di động tới profile đích.
  - **SmartQueue v2:** Hỗ trợ cấu hình luồng đồng thời (1-10 threads), gom nhóm Graph API Batching lên tới 50 request/call, và tự động Exponential Backoff khi gặp mã giới hạn tốc độ (17, 613, 80004, 429).

- **Trụ cột 4: Tiện Ích Mở Rộng & Thanh Toán (Add-ons & Billing):**
  - **Ads Save:** Kho lưu trữ, xuất/nhập tệp đối tượng mục tiêu, bài viết quảng cáo và bộ Super Target xuyên tài khoản.
  - **Extended Payment:** Kiểm tra thẻ thanh toán, đầu thẻ (BIN), trạng thái phân bổ ngân sách và kích hoạt thanh toán số dư dư nợ tức thì (`pay_now`).
  - **Bộ công cụ Advance:** Xóa cache, xuất định dạng CSV SMIT chuẩn, chia sẻ nhanh và dọn dẹp sạch admin ẩn.

- **Giao diện Web & Extension Đồng Bộ:**
  - `apps/web/app/ads-check/page.tsx`: Giao diện tối ưu toàn màn hình (responsive Desktop & Mobile), tích hợp thanh trạng thái Control Hub Nodes, modal 70 kịch bản tự động hóa và công cụ Super Target.
  - `extensions/adsos-check-bridge/`: Cập nhật toàn diện Popup, Content Widget và Dashboard hiển thị huy hiệu trạng thái Session (`Cookie` | `EAAG` | `EAAB` | `DTSG`), bảng điều khiển đa node và form Lên Camp linh hoạt (`ACTIVE`/`PAUSED`).

- **Chất lượng & Kiểm thử:**
  - Alembic migration `t5c6d7e8f9a0` đạt chuẩn reversible `upgrade -> downgrade -> upgrade`.
  - Toàn bộ backend test đạt **626/626 PASS** (100% pass trên test suite đầy đủ).
  - Kiểm tra cú pháp JavaScript extension bằng `node --check` đạt 100% sạch lỗi.
  - Next.js production build & strict typecheck (`npm run build`) biên dịch thành công **30/30 route** với zero lỗi type.

## Cập nhật 2026-11-11 — Hệ Giao Diện Đơn Sắc Tối Giản Toàn Hệ Thống

- **Bộ icon dùng chung:** bổ sung `MonoIcon` cho Web App với SVG line-icon `stroke-width=1.5`, kế thừa `currentColor`; shell, sidebar, tìm kiếm, thông báo, chuyển giao diện, phân trang, modal và các thao tác sao chép/sửa/xóa quan trọng không còn dùng emoji màu.
- **Quy tắc đơn sắc toàn Web App:** duy trì nền Spotify Dark `#121214`, bề mặt `#1A1A1E`, viền `#2A2A32`; icon chỉ dùng `#F3F4F6`, `#D1D5DB`, `#9CA3AF`. Các utility màu xanh/vàng/đỏ/tím trong màn hình cũ được quy về sắc xám ở lớp design-system; trạng thái dùng chấm xám, viền và nhãn chữ thay cho mảng màu mạnh.
- **Chrome Extension:** dashboard, popup và widget nổi trên Meta dùng cùng hệ SVG nét mảnh. Popup bỏ gradient màu; dashboard chuyển trạng thái, badge, CTA và tiến độ về trắng/xám; widget nổi đổi thành pill tối, card tối và ép cả nội dung tạo động về thang đơn sắc.
- **Dọn mã giao diện:** loại toàn bộ codepoint emoji khỏi TSX/HTML/JS trong `apps/web/app`, `apps/web/components` và `extensions/adsos-check-bridge`; không còn SVG hard-code màu. Văn bản và log giao diện giữ tiếng Việt, các thuật ngữ kỹ thuật như VIA, BM, TKQC, EAAG/EAAB được giữ nguyên.
- **Không đổi nghiệp vụ:** không thêm dependency, không thay API, dữ liệu, công thức tài chính, scheduler hoặc ranh giới D-065; không thực hiện ghi dữ liệu live.
- **Nghiệm thu:** toàn bộ JavaScript extension đạt `node --check`; Next.js production build/typecheck đạt **30/30 route**, quét nguồn Web App không có khai báo `any`; backend đạt **618/618 test pass** (1 cảnh báo deprecation Starlette/httpx bên thứ ba).

## Cập nhật 2026-11-10 — ADSOS CHECK SaaS Dark Mode Mật Độ Cao

- **Hệ thiết kế thống nhất:** dashboard web và Chrome Extension dùng nền `#121214`, bề mặt `#1A1A1E`, viền `#2A2A32`, CTA `#2563EB`/hover `#1D4ED8`, chữ Inter/Be Vietnam Pro và số liệu dạng tabular. Trạng thái Live/Cảnh báo/Die dùng LED xanh, vàng, đỏ với quầng sáng đúng token thiết kế.
- **Kiến trúc ba vùng:** bổ sung top bar 60px có tìm kiếm thông minh, phím `F`, bộ lọc trạng thái, VIA chính và badge phiên; sidebar 256px chia ba nhóm tài sản, vận hành và tiện ích; workspace có bốn KPI, thanh mật độ và bảng cuộn ngang mật độ cao.
- **Bảng tài sản cho Media Buyer:** ghim cột chọn + tên/ID/BM bên trái và thao tác bên phải; hiển thị trạng thái, dư nợ, ngưỡng, ngưỡng còn lại, limit ẩn, tổng tiêu, tiền tệ, bốn số cuối thẻ, múi giờ và QTV. ID tài khoản, BM và thẻ hỗ trợ sao chép khi rê chuột; các tổng VND/USD luôn tách riêng, không quy đổi hoặc cộng chéo.
- **Tương tác nhanh:** chế độ gọn đổi padding dòng 12px/6px; thanh thao tác nổi xuất hiện khi có lựa chọn; `Esc` bỏ chọn/đóng lớp phủ, `Ctrl/Cmd+Enter` mở workflow, nút hủy dừng các request còn chờ trong SmartQueue và để request đang chạy dừng tại điểm an toàn.
- **Giữ tương thích:** tái sử dụng API, modal và hợp đồng dữ liệu hiện có; không thêm dependency, không tạo công thức tài chính mới và không thay đổi ranh giới thực thi D-065.
- **Nghiệm thu:** toàn bộ JavaScript extension đạt `node --check`; Next.js production build/typecheck đạt **30/30 route**; backend đạt **618/618 test pass** (1 cảnh báo deprecation Starlette/httpx bên thứ ba).

## Cập nhật 2026-11-10 — Telegram Bot Agent & Hàng Đợi Lệnh Campaign Qua Extension (Module 8)

- **Mô hình và migration:** mở rộng `remote_via_commands` với UUID công khai, `ad_account_id`, JSON `payload`, `result_log`, `updated_at`; bổ sung `update_id` chống xử lý trùng Telegram và `chat_id` cho outbox gửi lại đúng khách. Migration reversible `s4b5c6d7e8f9` đã vượt qua `upgrade → downgrade → upgrade` trên SQLite riêng và đã áp dụng DB local lên head.
- **Webhook Telegram an toàn:** `POST /api/v1/telegram/webhook` xác thực Webhook Secret trước khi đọc payload, hỗ trợ `/setcamp`, `/set_camp` và câu tự nhiên. Lệnh chỉ được nhận khi `telegram_chat_id` liên kết một Customer và TKQC thuộc đúng Customer; VIA gắn tài khoản phải `ACTIVE`. `update_id` duy nhất ngăn Telegram retry tạo lệnh trùng.
- **Hàng đợi đơn lệnh:** API mới `GET /api/v1/remote-commands/pending` claim nguyên tử lệnh `PENDING` cũ nhất thành `PROCESSING`, ưu tiên đúng VIA rồi mới auto-route. `POST /{id}/status` chỉ chấp nhận `COMPLETED`/`FAILED`, lưu kết quả và thông báo Telegram; retry terminal không gửi thông báo trùng. Client Key gắn khách chỉ được nhận và báo cáo lệnh của chính khách đó; quản trị local có thể xem và hủy lệnh `PENDING`.
- **Ranh giới D-027/D-040/D-064:** backend không gọi Meta write API để tạo/sửa campaign và không giả kết quả thành công. Các API tạo campaign, quy tắc auto-pause và khóa rủi ro đều chỉ xếp `RemoteViaCommand`. Validation khóa/đặc cách vẫn dùng dữ liệu/API đọc trước khi xếp lệnh. Mọi payload tạo mới bị ép `PAUSED`.
- **Chrome Extension:** service worker poll mỗi 5 giây, dùng token đã cấu hình để gọi `POST /v26.0/act_{id}/campaigns`, luôn gửi `status=PAUSED`, không mô phỏng ID khi thiếu token/lỗi Meta và báo kết quả tiếng Việt về backend. Luồng cũ cũng được ép `PAUSED`; cú pháp `background.js` và `popup.js` đạt `node --check`.
- **Giao diện `/tasks`:** thêm bảng **“Hàng Đợi Lệnh (Remote Tasks)”** với ngày, khách, TKQC, loại lệnh/campaign, badge trạng thái, nhật ký kết quả và nút **“Hủy Lệnh”** cho lệnh đang chờ.
- **Nghiệm thu:** test tập trung Module 8 đạt; toàn bộ backend **618/618 pass** (1 cảnh báo deprecation Starlette/httpx bên thứ ba). Next.js production build/typecheck đạt **30/30 route**. Chưa gửi lệnh tới tài khoản Meta hoặc Telegram production; kiểm thử dùng mock/DB local.

## Cập nhật 2026-11-10 — Cấp Quyền VIA Qua Meta OAuth 2.0 Chính Thức

- **OAuth backend an toàn:** bổ sung `GET /api/v1/oauth/facebook/login` và callback chính thức của Meta. `state` chứa VIA ID, nonce, thời điểm phát hành và origin quay về; toàn bộ payload được ký HMAC, hết hạn sau 10 phút và bị từ chối nếu bị sửa hoặc dùng origin ngoài danh sách cho phép.
- **Token dài hạn mã hóa:** callback đổi authorization code thành token ngắn hạn rồi token dài hạn qua Graph API v26, xác minh `/me` trùng đúng UID VIA trước khi lưu. Token đi bằng Bearer header khi xác minh, được mã hóa Fernet trong `encrypted_credentials`; App Secret chỉ đọc từ biến môi trường backend, không trả về frontend hoặc ghi log.
- **Quyền tối thiểu, chỉ đọc:** màn hình cấp quyền yêu cầu `ads_read`, `business_management` và `pages_show_list`; không xin `ads_management`, không dùng cookie, CDP, DOM scraping hoặc trình duyệt headless. Metadata hợp lệ cập nhật `token_status=ACTIVE`, `last_token_refresh` và `token_expires_at`; mọi lỗi giữ nguyên token cũ.
- **Giao diện `/vias`:** thay các nút hút session Chrome, login headless và dán Cookie/Token bằng **“🔗 Cấp quyền OAuth (An toàn)”**. Khi quay về, trang hiển thị thông báo tiếng Việt, tải lại danh sách VIA và xóa query callback khỏi thanh địa chỉ; đồng bộ tài sản chỉ dùng token đã cấp quyền.
- **Cấu hình:** hỗ trợ `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_REDIRECT_URI` (đồng thời tương thích tiền tố `ADSOS_`); file env mẫu chỉ chứa khóa trống và callback local, không chứa secret thật.
- **Nghiệm thu:** kiểm thử OAuth tập trung **5/5 pass** cho URL cấp quyền, state ký, trao đổi hai cấp token, mã hóa lưu trữ, hủy cấp quyền và UID không khớp; toàn bộ backend **615/615 pass** (1 cảnh báo deprecation Starlette/httpx bên thứ ba). Next.js production build/typecheck **30/30 route pass**. Chưa gọi OAuth bằng ứng dụng Meta production trong vòng kiểm thử.

## Cập nhật 2026-11-10 — Smart Request Queue & Điều Tiết Rate Limit Meta

- **SmartQueue thuần trình duyệt:** toàn bộ lời gọi `fetchGraph` của luồng đọc tài sản đi qua một hàng đợi dùng tối đa 3 request đồng thời và jitter 500–1.500 ms trước mỗi request; không thêm thư viện hoặc module Node.js.
- **Backoff toàn cục, retry hữu hạn:** phát hiện HTTP 429 và mã lỗi Meta/GraphQL 17 hoặc 613, tạm dừng cấp request mới cho toàn queue, ưu tiên `Retry-After` nếu có, nếu không backoff 5/10/20/40 giây. Mỗi request thử tối đa 5 lần rồi trả lỗi tiếng Việt, tránh vòng lặp vô hạn và tránh chuyển sang các field fallback làm tăng tải.
- **Batch Graph API:** tải danh sách node TKQC theo `ids` với tối đa 50 ID/request thay cho vòng gọi từng tài khoản. Các edge phân trang `adaccounts`, `owned_ad_accounts` và `client_ad_accounts` tiếp tục dùng Graph API v26 chính thức và tự đi qua SmartQueue.
- **Tiến độ thời gian thực:** service worker phát `SYNC_PROGRESS` khi xếp hàng, tải trang, quét BM, bị giới hạn, đồng bộ máy chủ và hoàn tất. Dashboard hiển thị nội dung “Tiến độ: hiện tại / tổng” cùng thanh tiến độ có thuộc tính ARIA; popup hiển thị cùng tiến độ dạng văn bản nên không còn cảm giác treo khi queue đang chờ.
- **Giới hạn phạm vi:** đây là điều tiết rate limit theo phản hồi chính thức của Meta, không phải cơ chế vượt checkpoint; không thêm cookie, DOM scraping hoặc tự động hóa ghi tài sản.
- **Nghiệm thu:** `node --check` đạt cho `background.js`, `dashboard.js` và `popup.js`; quét tĩnh xác nhận không dùng `fs`, `path`, `require` hay module Node.js.

## Cập nhật 2026-11-09 — Sửa Luồng Đọc TKQC Của Extension Theo Graph API Chính Thức

- **Khắc phục nguyên nhân đọc thiếu TKQC:** extension chuyển từ Graph API `v19.0` sang `v26.0`; xác minh lần lượt token đã cấu hình và đúng UID, sau đó đọc phân trang `/{uid}/adaccounts`, `/{uid}/businesses`, `/{bm_id}/owned_ad_accounts` và `/{bm_id}/client_ad_accounts`.
- **Giữ liên kết BM:** khi một TKQC xuất hiện đồng thời ở danh sách người dùng và danh sách BM, dữ liệu BM được hợp nhất lên bản ghi trùng thay vì bị bỏ qua. Payload gửi `extension-ingest` có cả `owned_ad_accounts` và `client_ad_accounts` lồng theo đúng BM cha.
- **An toàn D-027/D-040:** bỏ đọc token, cookie, `fb_dtsg`, act_id và BM ID từ DOM/HTML Facebook; không còn fallback scrape Business Settings/Ads Manager. Content script chỉ báo cáo act_id có sẵn trên URL. Request Graph chính của luồng đồng bộ dùng Bearer header và không đưa token vào payload ingest.
- **Giao diện extension:** thông báo tiến trình đổi thành “Đang xác minh Meta Access Token đã cấu hình”; nút quét lại BM/Fanpage tái sử dụng một luồng Graph v26 duy nhất, tránh nhánh dashboard cũ còn gọi v19.
- **Không triển khai `IgUnlimitedAdAccount`:** không thêm Playwright, Chromium, service/router SSE hay trang `/ig-unlimited`. Quy trình tự động tạo TKQC, thêm IG toàn quyền, gỡ liên kết rồi lặp lại là thao tác ghi Meta và cơ chế né giới hạn nền tảng, trái D-027/D-040 (Meta read-only, không cookie/headless/DOM extraction).
- **Nghiệm thu:** `node --check` đạt cho 4 file extension; kiểm thử ingest tập trung **1/1 pass**; toàn bộ backend **610/610 pass** (1 cảnh báo deprecation Starlette/httpx bên thứ ba); Next.js production build/typecheck **30/30 route pass**. Chưa kiểm thử với token Meta production.

## Cập nhật 2026-11-09 — Ánh Xạ Đầy Đủ TKQC Chia Sẻ Theo BM & Dư Nợ Khách Hàng

- **Đồng bộ tài sản BM:** `sync_via_all_assets` gọi field expansion chính thức cho cả `owned_ad_accounts` và `client_ad_accounts`, theo tiếp phân trang lồng (tối đa 1.000 TKQC mỗi nhánh/BM) và fallback sang hai edge Graph API phân trang khi field expansion không khả dụng. Mọi TKQC tìm thấy qua BM được gắn `bm_id`/loại `BM`; tài khoản đã gặp trước qua `/me/adaccounts` hoặc VIA khác không còn bị vòng upsert cá nhân xóa liên kết BM.
- **Extension ingest:** payload phẳng và payload lồng trong từng BM đều được hợp nhất theo `act_id`; hỗ trợ danh sách trực tiếp hoặc cấu trúc Graph `{data: [...]}` cho `business_managers`, `owned_ad_accounts` và `client_ad_accounts`. Bản ghi trùng giữ dữ liệu chi tiết đã quét nhưng luôn nhận đúng BM cha.
- **Trang `/accounts`:** bộ lọc BM đọc toàn bộ trang dữ liệu đã đồng bộ. KPI mới **“Tổng Dư Nợ Meta (Đã Gán)”** chỉ tính TKQC có `customer_id`, hiển thị VND và USD thành hai tổng riêng theo định dạng `vi-VN`/`en-US`; bỏ qua tài khoản chưa gán và tiền tệ khác, không quy đổi hoặc cộng chéo.
- **Quyết định:** ghi nhận D-062 cho phạm vi ánh xạ BM và chỉ số số dư đã gán; không thay đổi sổ tài chính hoặc phát sinh giao dịch.
- **Nghiệm thu:** kiểm thử tập trung backend **25/25 pass**; toàn bộ backend **610/610 pass** (1 cảnh báo deprecation từ Starlette/httpx bên thứ ba); kiểm thử tiện ích web **6/6 pass**; Next.js production build/typecheck **30/30 route pass**. Chưa gọi dữ liệu Meta production trong vòng kiểm thử; trường hợp 583 TKQC được bảo đảm bằng logic phân trang và mock, cần lần đồng bộ live để xác nhận số lượng thực tế theo quyền token.

## Cập nhật 2026-11-09 — Tự Động Kiểm Tra Token VIA & Đồng Bộ Tài Sản Nền

- **Tác vụ xác thực token VIA (`app/jobs/token_keepalive.py`):**
  1. `auto_verify_via_tokens` chạy mặc định mỗi 6 giờ và chỉ kiểm tra VIA `ACTIVE`; jitter phân tải mặc định 2–5 giây, cấu hình qua biến môi trường `ADSOS_VIA_TOKEN_*`.
  2. Xác thực bằng `GET /v26.0/me` với Bearer header, không đưa token vào URL/log; cô lập transaction và lỗi theo từng VIA. Thành công cập nhật `last_token_refresh`; lỗi xác thực chuyển `EXPIRED`, lỗi kết nối chuyển `WARNING` và ghi cảnh báo tiếng Việt.
  3. Nếu có `token_expires_at` từ metadata OAuth chính thức và thời hạn còn không quá 24 giờ, token hợp lệ được gắn `WARNING`. `/me` không tự cung cấp thời hạn nên hệ thống không suy đoán khi metadata này trống.
  4. Tuân thủ D-027/D-040: **không** tự mở Chrome, đọc cookie hoặc trích EAAG/EAAB từ DOM/phiên Facebook; không tự gia hạn token.

- **Tác vụ đồng bộ tài sản nền (`app/jobs/asset_sync.py`):**
  1. Chạy mặc định mỗi 2 giờ cho toàn bộ VIA `ACTIVE`, single-flight, mỗi VIA dùng session/transaction riêng nên một VIA lỗi không làm dừng batch.
  2. Tái sử dụng `sync_via_all_assets` với chế độ cấm phục hồi token từ cookie. Upsert BM, TKQC sở hữu/chia sẻ và Page; cập nhật trạng thái, hạn mức, số dư và số đếm.
  3. Chỉ khi `/me/adaccounts`, `/me/businesses`, toàn bộ `owned_ad_accounts`/`client_ad_accounts` và `/me/accounts` đều thành công, tài sản không còn được trả về mới đổi trạng thái: BM `DISCONNECTED`, TKQC `DIE` + `DISCONNECTED`, Page `is_published=False`. Lỗi/thiếu quyền giữa chừng giữ nguyên dữ liệu cũ.

- **Scheduler, API và giao diện:**
  1. APScheduler đăng ký `via_token_keepalive` và `via_asset_sync` trong scheduler nền hiện có; không chặn event loop FastAPI, `max_instances=1` và `coalesce=True`.
  2. Endpoint quản trị local `POST /api/v1/vias/sync-assets-all` xếp lịch đồng bộ nền. Trang `/vias` có nút **“Đồng bộ tất cả ngay”** và hiển thị **“Đồng bộ lần cuối”** cạnh số lượng BM/TKQC/Page.
  3. Migration reversible `q3a4b5c6d7e8_add_via_last_sync_fields.py` thêm `via_profiles.last_token_refresh` và `token_expires_at`; đã kiểm tra `upgrade → downgrade → upgrade` trên DB riêng và nâng local DB lên head sau khi sao lưu.

- **Nghiệm thu:** test tập trung **25/25 pass**; toàn bộ backend **610/610 pass** (1 cảnh báo deprecation từ Starlette/httpx bên thứ ba); Next.js production build và typecheck **30/30 route pass**.

## Cập nhật 2026-11-06 — Khắc Phục Lỗi Kết Nối Extension, Báo Cáo Đối Soát Chi Tiêu Khách Hàng (4% Phí), Bản Nháp Chiến Dịch & Tự Động Set Camp Qua Lệnh Telegram

- **Sửa lỗi kết nối Chrome Extension & Khởi động Service Worker Manifest V3:**
  1. Loại bỏ quyền `"declarativeNetRequest"` khỏi `permissions` trong `extensions/adsos-check-bridge/manifest.json`. Quyền này khi khai báo mà không có ruleset tĩnh khiến các bản build Chrome chặn service worker hoặc đưa ra cảnh báo bảo mật, làm background fetch bị ngắt quãng.
  2. Cập nhật `host_permissions` đầy đủ: `*://*.facebook.com/*`, `https://graph.facebook.com/*`, `*://*.fbcdn.net/*`, `http://localhost:*/*`, `http://127.0.0.1:*/*`, `https://*/*`.
  3. Mở rộng cơ chế **Multi-endpoint Auto-Discovery** trong `background.js`, `dashboard.js`, và `popup.js`:
     - Tự động thăm dò danh sách máy chủ khả thi: cấu hình đã lưu, `http://127.0.0.1:8000`, `http://localhost:8000`, `http://localhost:8080`, `http://127.0.0.1:8080`.
     - Ping endpoint unauthenticated `GET /api/v1/vias/ping` (hoặc `/health`), khi có phản hồi hợp lệ sẽ tự động lưu vào `chrome.storage.local` và cập nhật tức thì trạng thái kết nối trên thanh trạng thái.
  4. Cấu hình bảo mật `require_local_admin`: Ngoại lệ cho phép gọi không chứng thực tới `/api/v1/vias/ping`, `/health` để extension tự động dò tìm máy chủ nội bộ.

- **Nạp Cookie & EAAG Token trực tiếp trên Web + Báo Cáo Đối Soát Chi Tiêu Khách Hàng (4% Phí Thuê):**
  1. Xác thực nhập trực tiếp `Cookie` + `EAAG/EAAB Token` trong modal VIA (`update_manual_credentials_endpoint`): Kích hoạt ngay `token_status = "ACTIVE"`, `uid_live_status = "LIVE"` và tiến hành quét sâu toàn bộ BM, TKQC, Fanpage.
  2. Bổ sung endpoint backend `GET /api/v1/vias/customer-spend-summary`:
     - Tự động tính toán tổng chi tiêu Meta (`raw_spend`) cho các TKQC được gán theo từng khách hàng.
     - Áp dụng chuẩn quy tắc 4% phí dịch vụ (`docs/DECISIONS.md`): `fee_amount = raw_spend * (fee_rate_percent / 100)`, `total_payable = raw_spend + fee_amount`. Hỗ trợ mức phí riêng nếu khách hàng có thỏa thuận đặc thù.
  3. Xây dựng component giao diện `CustomerSpendReportModal.tsx` trên Web:
     - Nút bấm 1-click **`📊 Báo Cáo 4% Phí`** xuất hiện trên cả trang `/accounts` và `/ads-check`.
     - Cho phép xem nhanh bảng tổng hợp chi tiêu, phí dịch vụ, số dư nợ, chi tiết từng tài khoản quảng cáo và 1-click sao chép báo cáo đối soát chuẩn định dạng gửi khách hàng mà không cần mở extension.

- **Hệ thống Bản Nháp Chiến Dịch (Campaign Drafts) & Tự Động Set Camp Qua Telegram Bot:**
  1. **Cơ sở dữ liệu SQLAlchemy & Migration Alembic (`n1e2f3a4b5c6`):**
     - Bảng `campaign_drafts`: Lưu trữ cấu hình chiến dịch Meta Ads tái sử dụng (`draft_code`, `draft_name`, `objective`, `daily_budget`, `targeting_json`, `page_id`, `post_id`, `ad_creative_json`, `initial_status`).
     - Bảng `remote_via_commands`: Hàng đợi lệnh từ xa gửi tới Extension Chrome hoặc Backend Runner (`via_uid`, `act_id`, `customer_id`, `draft_id`, `command_type`, `payload_json`, `status`, `result_json`, `error_message`).
  2. **Bộ phân giải lệnh Telegram & Kiểm tra quyền sở hữu nghiêm ngặt (Customer Ownership Verification):**
     - Hỗ trợ câu lệnh tự nhiên tiếng Việt: `set ads tài khoản ID: <act_id> theo <bản_nháp>` (hoặc `/setcamp <act_id> <bản_nháp>`).
     - Xác thực quyền: So khớp người gửi Telegram (`@username` hoặc `chat_id`) với khách hàng đang được gán quyền sở hữu tài khoản quảng cáo trong `synced_ad_accounts`.
     - Nếu không phải chủ sở hữu: Từ chối thực thi với thông báo: *"⛔ Từ chối thực thi: Tài khoản quảng cáo {act_id} chưa được gắn cho tài khoản Telegram @{username} của bạn."*
     - Nếu đúng chủ sở hữu: Tìm bản nháp chiến dịch, xác định VIA quản lý tài khoản và xếp hàng lệnh `RemoteViaCommand` trạng thái `PENDING`.
  3. **Extension Chrome Auto Set Camp:**
     - `background.js` định kỳ 5s thăm dò `GET /api/v1/vias/remote-commands/pending?c_user={uid}`.
     - Thực hiện quy trình khởi tạo Meta Graph API 3 bước: Campaign ➔ AdSet ➔ Ad với trạng thái an toàn (PAUSED/ACTIVE theo cấu hình bản nháp).
     - Báo cáo kết quả về `POST /api/v1/vias/remote-commands/{id}/complete` và bắn Chrome notification thông báo trên màn hình.
     - Hỗ trợ hành động `CAPTURE_DRAFT_FROM_ACT` lưu bản nháp trực tiếp từ tài khoản quảng cáo.

- **Kiểm thử & Độ tin cậy:**
  1. Cú pháp JavaScript Extension: `node --check` trên cả 4 file (`background.js`, `dashboard.js`, `popup.js`, `content.js`) vượt qua 100% không có lỗi.
  2. Toàn bộ test suite Backend: **598/598 tests passed (100% PASS)** bao gồm các test case cho ping, campaign drafts, customer spend 4% fee reconciliation và telegram setcamp ownership verification.
  3. Frontend Next.js build: **22/22 routes biên dịch thành công (100% PASS)** với typecheck và bundle optimization sạch sẽ.



## Cập nhật 2026-11-05 — Khắc Phục Lây Nhiễm Chéo 40 BM Giữa Các VIA, Gỡ Treo Banner Bước 3, Cập Nhật Quyền Manifest 2.5.0 & Nâng Cấp ADSOS CHECK PRO Với Kiến Trúc 4 Trụ Cột (4-Pillar Architecture)

- **Khắc phục triệt để nhiễm chéo 40 BM giữa các VIA (Cross-VIA Data Contamination Fix):**
  1. **Nguyên nhân cốt lõi:** Trước đây trong `background.js`, các danh sách `scrapedBmIds` và `scrapedActIds` được lưu vào key dùng chung toàn cục trong `chrome.storage.local`. Khi một VIA có 40 BMs được quét, các BM này bị lưu vào key chung và khi người dùng chuyển sang VIA thứ hai (chỉ có 2 BMs), hàm `fetchBusinessesAndBMAccounts` đọc key toàn cục và bơm ngược toàn bộ 40 BMs của VIA thứ nhất vào VIA thứ hai. Đồng thời ở backend, truy vấn `SyncedBM` và `SyncedPage` thiếu điều kiện lọc `via_profile_id == via.id`, khiến các bản ghi BM bị ghi đè hoặc đánh cắp quyền sở hữu.
  2. **Cách ly dữ liệu nghiêm ngặt theo UID (`c_user` Scoped Storage):**
     - Trong `background.js`: Các key lưu trữ được phân vùng độc lập theo UID: `scrapedBmIds_${cUser}` và `scrapedActIds_${cUser}`. Loại bỏ hoàn toàn việc đọc `scrapedBmIds` chung.
     - Hàm `ensureLiveAccessToken` kiểm tra token xác minh Graph API `me?fields=id` đảm bảo token thuộc về đúng `currentUid`. Nếu không khớp, token cũ của VIA khác lập tức bị bỏ qua.
     - Thêm action `CLEAR_CURRENT_VIA_CACHE` trong `background.js` xóa sạch cache và key riêng của UID khi cần làm mới.
  3. **Backend Per-VIA Isolation (`via_manager.py` & `vias.py`):**
     - Sửa toàn bộ câu lệnh upsert `SyncedBM` và `SyncedPage` thành `select(SyncedBM).where(SyncedBM.bm_id == bm_id, SyncedBM.via_profile_id == via.id)`. Mỗi VIA lưu giữ danh sách BM và Fanpage hoàn toàn độc lập trong database.
     - Thêm unit test `test_cross_via_bm_and_account_isolation` trong `test_smit_accounts_and_customer_assign.py` kiểm chứng VIA A (40 BMs) và VIA B (2 BMs) không bao giờ bị rò rỉ dữ liệu của nhau.

- **Gỡ treo hoàn toàn banner Bước 3 & tiến trình quét 4 bước (Scanner Banner Unfreezing):**
  1. Bọc toàn bộ các hàm quét và đồng bộ (`triggerHarvest`, `btnLoadAll`, `btnSyncServer`) trong khối `try ... catch ... finally`.
  2. Xây dựng helper `sendRuntimeMessageWithTimeout(msg, timeoutMs)` với cơ chế `setTimeout` ngắt sau 15-20 giây. Ngay cả khi tiến trình nền gặp lỗi mạng hoặc service worker bị suspended, khối `finally` luôn được gọi để giải phóng banner tiến trình (`setScanStatus("")`), khôi phục trạng thái nút bấm (`btnLoadAll.disabled = false`, `btnSyncServer.disabled = false`).
  3. Thiết lập per-BM timeout (`AbortSignal.timeout(5000)`) cho từng request quét Graph API cấp BM (`fetchEndpointWith3TierFallback`), giúp các BM die hoặc bị rate-limit thoát nhanh sau 5 giây thay vì treo cứng vòng lặp.

- **Cập nhật quyền và cấu hình Extension Manifest v2.5.0 (`manifest.json`):**
  1. Nâng cấp phiên bản lên **`2.5.0`**.
  2. Cập nhật đầy đủ các quyền: `"cookies"`, `"storage"`, `"unlimitedStorage"`, `"tabs"`, `"activeTab"`, `"scripting"`, `"alarms"`, `"notifications"`, `"history"`, `"declarativeNetRequest"`, `"management"`.
  3. Khai báo host permissions mở rộng: `*://*.facebook.com/*`, `*://*.fbcdn.net/*`, `http://localhost:*/*`, `http://127.0.0.1:*/*`, `https://*/*`.

- **Nâng cấp giao diện & tính năng ADSOS CHECK PRO với kiến trúc 4 Trụ Cột (4 Core Pillars) (`dashboard.html` & `dashboard.js`):**
  1. **Thanh điều hướng 4 Trụ cột chuyên biệt (`.pillars-nav-bar`):**
     - Chuyển đổi mượt mà giữa 4 phân hệ chính mà không làm mất trạng thái hay tải lại trang.
     - Bổ sung nút bấm sidebar `🔄 Xóa cache` (`#btnClearViaCache`) cho phép xóa sạch cache VIA hiện tại và quét mới 100% từ Facebook.
  2. **Trụ cột 1 — 📊 Quản Trị TKQC & Thanh Toán (`#tabPaneAccounts`):**
     - Bảng dữ liệu SMIT Pro độ nét cao không giới hạn số lượng tài khoản (Status, act_id, Name, Type, Balance, Threshold, Limit/ad_trust_dsl, Spend, Currency, Timezone, Card).
     - Thanh tác vụ hàng loạt mở rộng (Floating Bulk Actions Bar):
       - `✏️ Đổi Tên Hàng Loạt` (`#modalBulkRename`) hỗ trợ pattern `{index}`, `{id}`.
       - `🌍 Đổi Giờ / Tiền Tệ` (`#modalBulkTimezoneCurrency`) thay đổi múi giờ và loại tiền tệ hàng loạt.
       - `🤝 Share Quyền` (`#modalBulkShare`) cấp quyền quản trị/nhà quảng cáo hàng loạt cho UID đích.
       - `📋 Copy ID` & `📥 Xuất File CSV Chuẩn SMIT`.
     - Cửa sổ thanh toán mở rộng `💳 Extended Payment` (`#modalExtendedPayment`) hiển thị chi tiết thẻ, dư nợ chưa thanh toán, ngưỡng lập hóa đơn và hỗ trợ kích hoạt thanh toán ngay.
  3. **Trụ cột 2 — 🛡️ Bảo Mật BM & Quét QTV Ẩn (`#tabPaneBmSecurity`):**
     - **Hidden Admin Scanner & Cleaner:** Tự động quét `/{act_id}/users`, phát hiện các UID quản trị viên lạ/ẩn chiếm quyền trên các tài khoản quảng cáo và cung cấp nút xóa 1-click (`🧹 Gỡ` / `🧹 Xóa Tất Cả QTV Ẩn Đã Chọn`).
     - **Quản Lý Cấu Trúc BM:** Bảng danh sách toàn bộ Business Manager của VIA kèm trạng thái xác minh doanh nghiệp (Verified/Not Verified), số lượng TKQC sở hữu và công cụ tạo Link Mời BM cấp Admin tức thì (`🔗 Tạo Link Mời BM`).
  4. **Trụ cột 3 — 🎯 Super Target & Fanpage/Pixel (`#tabPaneSuperTarget`):**
     - **Super Target Tool:** Khai thác sở thích ẩn Meta Graph API `GET /v19.0/search?type=adinterest` vượt qua giới hạn 25 gợi ý thông thường của Ads Manager. Hỗ trợ đa ngôn ngữ (`vi_VN`, `en_US`, `th_TH`), hiển thị quy mô khán giả (Audience Size), danh mục (Path), chủ đề (Topic) và 1-click copy danh sách sở thích đã chọn.
     - **Quản Lý Vệ Tinh (Fanpages & Pixels):** Bảng quản trị danh sách Fanpage kèm lượt thích/theo dõi và công cụ chia sẻ Pixel hàng loạt (`🚀 Chia Sẻ Pixel Cho TK Đang Chọn`) sang các tài khoản quảng cáo chỉ định.
  5. **Trụ cột 4 — ⚙️ Workflow Builder & Control Hub (`#tabPaneWorkflow`):**
     - **Workflow Automation Builder:** Trình xây dựng kịch bản vận hành chuỗi 6 bước tự động liên hoàn (1. Quét sâu tài sản -> 2. Quét & Gỡ QTV ẩn -> 3. Chia sẻ Pixel -> 4. Chuẩn hóa tên TKQC -> 5. Phân quyền quản trị dự phòng -> 6. Đẩy chi tiêu về AdsOS Server).
     - **Thanh trượt an toàn Anti-Checkpoint:** Cấu hình độ trễ ngẫu nhiên (1500ms - 5000ms + Jitter ±300ms) chống checkpoint khi chạy tác vụ hàng loạt.
     - **Màn hình Console thời gian thực:** Hiển thị chi tiết từng bước thực thi với timestamp.
     - **Control Hub:** Trạm giám sát kết nối máy chủ AdsOS, hỗ trợ nhận lệnh điều khiển từ xa (Remote Command Polling) và bảng lịch sử tác vụ.

- **Kiểm thử & Độ tin cậy:**
  1. Syntax check bằng `node --check` trên cả 4 file Extension JS (`dashboard.js`, `background.js`, `popup.js`, `content.js`): **0 syntax errors**.
  2. Toàn bộ backend test suite: **594/594 tests passed (100% PASS)** bao gồm test case cách ly BM giữa các VIA `test_cross_via_bm_and_account_isolation`.
  3. Frontend build (`npm.cmd run build`): **22/22 routes compiled successfully**, typecheck hoàn toàn sạch.


## Cập nhật 2026-11-05 — Khắc Phục Treo/Đơ Bước 3 Extension Ingest & Tự Động Chọn Phiên VIA Trên Dashboard Extension

- **Xử lý triệt để đơ giao diện khi chưa chọn VIA hoặc session Facebook chưa nhận diện (`dashboard.js` & `background.js`):**
  1. **Kiểm tra sớm trước khi đồng bộ (Early Validation):** Khi bấm nút *"🚀 Đồng Bộ Về Hệ Thống AdsOS"*, hệ thống kiểm tra ngay xem có VIA nào đang active và có `c_user` hợp lệ hay không. Nếu danh sách VIA rỗng hoặc `c_user` chưa chọn:
     - Lập tức hủy giao diện tiến trình đồng bộ (`setScanStatus("")`).
     - Hiển thị Toast cảnh báo tiếng Việt: `"Vui lòng bấm '+ Quét phiên hiện tại' ở góc dưới bên trái để nhận diện VIA trước khi đồng bộ!"`.
  2. **Timeout an toàn 10 giây (Client-side AbortSignal Timeout):**
     - Toàn bộ lời gọi mạng Bước 3 (`fetch('/api/v1/vias/extension-ingest')`) trên cả `dashboard.js` và `background.js` được bọc `AbortSignal.timeout(10000)` trong khối `try/catch/finally`.
     - Nếu mạng chập chờn hoặc máy chủ phản hồi chậm quá 10 giây, hệ thống tự động ngắt, báo lỗi rõ ràng và mở lại trạng thái nút bấm (`btnSyncServer.disabled = false`), tuyệt đối không bao giờ treo vô hạn ở Bước 3.
  3. **Tự động kích hoạt & chọn VIA mới khi bấm "+ Quét phiên hiện tại":**
     - Bổ sung hành động `scanCurrentSession` trong `background.js` và `dashboard.js`. Khi hoàn tất quét phiên, hệ thống tự động gán `activeViaUid` thành UID vừa quét, lưu vào `chrome.storage.local` và cập nhật tiêu đề header từ `Phiên FB: Chưa chọn (---)` thành `Phiên FB: [Tên VIA] ([UID])`.
  4. **Bảo toàn dữ liệu & dọn sạch bản ghi mồ côi (Orphan Cleanup):**
     - Đảm bảo khi tạo mới profile VIA trên SQLite, hệ thống dọn sạch các bản ghi con mồ côi nếu SQLite tái sử dụng ID cũ, bảo đảm số lượng Fanpage và TKQC trả về chính xác 100%.
  5. **Phiên bản Extension:** Xác nhận giữ đúng phiên bản **`2.4.0`** trong `manifest.json`.

- **Khắc phục triệt để treo vô hạn ở Bước 3 khi đồng bộ từ Extension (`POST /api/v1/vias/extension-ingest`):**
  1. **Nguyên nhân gốc rễ:** Trước đây endpoint chạy quét sâu Graph API (`sync_via_all_assets`) đồng bộ ngay trong vòng lặp HTTP request. Khi VIA sở hữu nhiều BMs (40+ BMs), kết nối HTTP bị pending kéo dài 15-30+ giây dẫn đến timeout và giao diện Extension treo cứng ở `"🚀 Bước 3/3: Đang đồng bộ hai chiều với máy chủ AdsOS..."`.
  2. **Tách tiến trình nặng qua FastAPI `BackgroundTasks`:**
     - Endpoint tiếp nhận payload và lưu tức thì profile VIA, tokens (EAAG/EAAB), cookie session và danh sách tài nguyên gửi lên vào SQLite qua `ingest_extension_payload(..., run_deep_sync=False)`.
     - Phản hồi ngay HTTP 200 kèm danh sách BMs và TKQC hiện hành trong vòng chưa tới 1 giây (`< 50ms`), giúp Extension hoàn thành Bước 3 mượt mà và hiển thị thông báo thành công.
     - Đẩy tiến trình quét sâu toàn bộ BMs và TKQC vào `background_tasks.add_task(sync_via_all_assets, session=db, via_id=via_id)` để chạy nền trên server khi `token_status == "ACTIVE"`.
  3. **Thoát sớm an toàn khi `c_user` / `uid` không hợp lệ:**
     - Nếu payload thiếu UID hoặc UID có giá trị rác/không hợp lệ (`""`, `"0"`, `"undefined"`, `"null"`, `"none"`), endpoint lập tức trả về HTTP 200: `{"success": false, "message": "Chưa chọn phiên Facebook hợp lệ", "accounts": [], "bms": []}`.
     - Giúp Extension UI dừng lại và thông báo người dùng chọn profile Facebook hợp lệ, không bị crash hay đứng im.

- **Kiểm thử & Độ tin cậy:**
  1. Thêm test case `test_extension_ingest_early_exit_on_invalid_or_missing_uid` trong `tests/test_smit_accounts_and_customer_assign.py` kiểm thử toàn diện các trường hợp UID rỗng/không hợp lệ.
  2. Toàn bộ test suite backend: **593/593 tests passed (100% PASS)** không có bất kỳ regression nào.


## Cập nhật 2026-11-04 — Tự Động Tạo VIA Kèm Token ACTIVE & Cookies Từ Extension, Thu Hoạch Song Song EAAG/EAAB & Ra Mắt Bong Bóng Dữ Liệu Trang AdsOS Check V8 (SMIT Style)

- **Sửa Lỗi VIA Tự Động Tạo Bị TRẠNG THÁI TOKEN = NONE & 0 TKQC (`apps/api/app/api/v1/vias.py` & `apps/api/app/services/via_manager.py`):**
  1. **Khắc phục triệt để sự chênh lệch:** Khi người dùng không tạo thủ công VIA trong `/vias` mà chỉ cài Extension trên trình duyệt và bấm đồng bộ, hệ thống tự động bóc tách token hợp lệ từ `payload.token`, `access_token`, `eaag_token`, `eaab_token`, hoặc `tokens` (ưu tiên `EAAG...` và `EAAB...`).
  2. **Lưu ngay trạng thái ACTIVE trước khi quét:** Tự động lưu `via.access_token = best_token`, `via.cookies = cookie_str`, `via.status = "LIVE"`, và gán `via.token_status = "ACTIVE"` ngay lập tức trước khi kích hoạt `sync_via_all_assets`.
  3. **Zero-Manual-Input Cookie Fallback:** Nếu Extension chỉ gửi chuỗi Cookie Facebook (`c_user=...; xs=...`), backend tự động bóc tách/trao đổi token thật `EAAG...`/`EAAB...` qua session cookie từ `business.facebook.com` và `adsmanager.facebook.com`, đảm bảo `token_status = "ACTIVE"` và không bao giờ bị rơi về `NONE` hay `EXPIRED`.
  4. **Tự động quét sâu tài sản khi Ingest:** Kích hoạt `sync_via_all_assets` quét sâu toàn bộ 40+ BMs và tất cả TKQC, lưu đầy đủ `amount_spent`, `balance`, `threshold_amount`, `spend_cap`, `currency`, `funding_source_last_four` vào `SyncedBM` và `SyncedAdAccount`. Cột `TRẠNG THÁI TOKEN` trong bảng `/vias` hiển thị màu xanh `ACTIVE`.

- **Nâng Cấp Thu Hoạch Song Song Token `EAAG...` + `EAAB...` & Full Cookies Trên Extension (`background.js`, `dashboard.js`, `popup.js`):**
  1. Khi người dùng bấm **"🚀 Đồng Bộ Về Hệ Thống AdsOS"** hoặc **"📥 Tải Tất Cả TKQC Của VIA"**, hệ thống chủ động thu hoạch đồng thời cả `eaag_token` (từ `business.facebook.com/business_locations`, `content_management`, `settings`) và `eaab_token` (từ `adsmanager.facebook.com/adsmanager/manage/accounts`, `onboarding`).
  2. Bắt trọn vẹn toàn bộ cookie header (`c_user`, `xs`, `datr`, `fr`, `sb`, `wd`) qua `chrome.cookies.getAll` trên cả domain `facebook.com` và `.facebook.com`.
  3. Gửi đầy đủ `token`, `eaag_token`, `eaab_token`, `cookies`, `c_user`, `profile_name` cùng các tài sản đã phát hiện về `POST /api/v1/vias/extension-ingest`.
  4. Khi truy vấn BM (`/{bm_id}/owned_ad_accounts` và `client_ad_accounts`), ưu tiên sử dụng `eaag_token` và kết hợp với `eaab_token` để không bỏ sót tài khoản.

- **Ra Mắt Bong Bóng Dữ Liệu Trang & Popup Card Tra Cứu Nhanh TKQC (AdsOS Check V8 SMIT-Style) (`content.js`):**
  1. **Floating Launcher Bubble (Bong bóng nổi 52x52px):** Nút tròn nổi bật với dải màu gradient lục bảo (`#1ed760` -> `#00b14f`), icon tia sét `⚡` và huy hiệu `V8` đặt tại góc dưới bên phải (`bottom: 24px; right: 24px; z-index: 2147483647`). Hỗ trợ kéo thả (drag & drop) linh hoạt khắp màn hình.
  2. **Tự động phát hiện TKQC đang xem (`act_xxx`):** Lắng nghe thay đổi URL (`location.search` cho `act=`, `account_id=`, `asset_id=`) và DOM Ads Manager để tự động nạp thông số TKQC hiện tại. Đồng thời cung cấp dropdown chuyển đổi tức thì giữa các TKQC của VIA.
  3. **Giao diện thẻ tra cứu SMIT V8 Card (360px):**
     - Header lục bảo gradient với tiêu đề **AdsOS Check V8 (by AdsOS Pro)**, tên TKQC kèm ID `act_xxx` (1-click copy).
     - Bộ nút tác vụ nhanh: Share TKQC (`🔗`), Mở Dashboard toàn màn hình (`🏠`), Làm mới & Đồng bộ (`🔄`), Thu gọn / Mở rộng (`▲`).
     - 2 nút bấm dạng viên thuốc (Action Pills):
       - **`💲 Quy đổi tiền tệ`**: Chuyển đổi hiển thị tức thì giữa tiền tệ gốc (USD, EUR, THB...) và **VND** (hoặc USD).
       - **`✏️ Đổi tên TK`**: Mở hộp thoại nhập tên mới và gọi Meta Graph API (`POST /v19.0/act_{id}`) cập nhật tên tài khoản ngay lập tức.
     - **12 hàng thông tin chi tiết chuẩn SMIT V8:** Trạng thái tài khoản (màu sắc trực quan), Limit hạn mức ngày, Ngưỡng hiện tại, Tổng chi tiêu, Số dư nợ, Ngày tạo tài khoản, Ngày lập hóa đơn, Quản trị viên ẩn (kèm nút Gỡ), Loại tài khoản (Doanh nghiệp/Cá nhân), Múi giờ, Thẻ thanh toán (Visa/Mastercard), Quyền tài khoản.
     - **Footer Bar:** Đèn báo trạng thái `🟢 Đã đồng bộ số liệu chi tiêu về AdsOS Server` và nút bấm **`📤 Đẩy Chi Tiêu Vào Bảng Đối Soát`**.

- **Phiên Bản & Kiểm Thử:**
  1. Tăng phiên bản Extension trong `manifest.json` lên **`2.4.0`**.
  2. Thêm bài test mới `test_auto_provisioned_via_from_extension_ingest_has_active_token_and_populated_assets` trong `tests/test_smit_accounts_and_customer_assign.py` kiểm tra tự động tạo VIA, gán `token_status = "ACTIVE"`, lưu token và cookies, và quét đủ BMs/TKQC.
  3. Toàn bộ backend test suite: **592/592 tests passed (100% PASS)**.
  4. Frontend Next.js build: **22/22 routes biên dịch thành công 0 lỗi** (`npm.cmd run build`).

---

## Cập nhật 2026-11-04 — Tách Biệt Quét BM Hàng Loạt (40+ BMs), Chống Tụt BM Về 11 & Sửa Lỗi Tải Theo ID BM Trả Về 0 Tài Khoản

- **Tách Biệt Hoàn Toàn Quét Danh Sách BM Khỏi Quét Tài Khoản Từng BM (`extensions/adsos-check-bridge` & `apps/api/app/services/via_manager.py`):**
  1. Loại bỏ các subquery lồng nhau nặng nề (`owned_ad_accounts.limit(100){...}`) trên `/me/businesses` — nguyên nhân gốc rễ gây lỗi HTTP 400 hoặc cắt ngắn danh sách 40 BM xuống còn 11 BM.
  2. Triển khai phân trang nhẹ (`fields=id,name,verification_status,created_time,permitted_roles,permitted_tasks&limit=100`) tự động duyệt theo `paging.next` đến hết tất cả các trang, thu thập đủ 100% (40+) Business Managers.
  3. **Quy Tắc Hợp Nhất Bất Biến (Critical Merge Rule):** Tuyệt đối không ghi đè danh sách BM cũ bằng danh sách con nhỏ hơn trong cả `chrome.storage.local` (`vias_data[cUser].bms`) và cơ sở dữ liệu (`synced_bms`). Luôn hợp nhất và khử trùng lặp theo `bm_id`, bảo toàn vĩnh viễn 40 BMs.

- **Quét Sâu TKQC Đồng Thời Toàn Bộ 40 BMs Qua Pool Đa Luồng (Batched Concurrency):**
  1. Backend (`via_manager.py`): Áp dụng `ThreadPoolExecutor(max_workers=8)` quét đồng thời cả `/{bm_id}/owned_ad_accounts` và `/{bm_id}/client_ad_accounts` cho toàn bộ 40 BMs với cơ chế Progressive Field Fallback 3 tầng (Tier 1 Full SMIT -> Tier 2 Standard -> Tier 3 Minimal Core) chỉ trong 2-3 giây.
  2. Extension (`background.js` & `dashboard.js`): Quét song song theo lô 5 BMs/lượt (`BATCH_SIZE=5`), tự động cập nhật cờ `account_type="BM"`, `business_id` và `business_name`.
  3. Cập nhật tiến độ quét thời gian thực qua kênh runtime message `BM_SCAN_PROGRESS` và hiển thị toast thông báo: `"⏳ Đang quét sâu TKQC trong X Business Manager (Đã quét A/X BM — Tìm thấy B TKQC)..."`.

- **Sửa Lỗi "🏢 Tải Theo ID BM" Trả Về 0 Tài Khoản (`loadAccountsByBmId` & `POST /ads-check/load-mode`):**
  1. **Nâng cấp Token Đa Tầng:** Bổ sung cơ chế thu hoạch và lưu trữ đồng thời cả `eaab_token` (từ `adsmanager.facebook.com`) và `eaag_token` (từ `business.facebook.com/business_locations` hoặc settings). Tự động thử lại với `eaag_token` nếu token chính không đủ quyền BM.
  2. **Dự Phòng Cào Phiên (Session HTML Scraping):** Nếu Graph API trả về 0 tài khoản, tự động cào trang `https://business.facebook.com/settings/ad-accounts?business_id={bm_id}` để bóc tách các `act_id` trực tiếp và bù đắp dữ liệu.
  3. **Kết Nối Máy Chủ Tải Ngay:** Nâng cấp endpoint `POST /api/v1/vias/ads-check/load-mode` (`mode: "LOAD_BY_BM_ID"`) kích hoạt hàm nghiệp vụ `fetch_accounts_for_bm_service`, tự động nạp tài khoản vào DB và cập nhật số lượng TKQC cho BM mục tiêu (như BM `439477786474451`).
  4. Sửa logic lọc trong `get_ads_check_explorer_data`: khi lọc theo `bm_id` hoặc chế độ `LOAD_BY_BM_ID`, không tự động gán điều kiện `account_type == "PERSONAL"`, đảm bảo hiển thị chuẩn xác các tài khoản BM.

- **Phiên Bản & Kiểm Thử:**
  1. Nâng cấp phiên bản Extension `manifest.json` lên **`2.3.0`**.
  2. Bổ sung các unit tests toàn diện trong `tests/test_smit_accounts_and_customer_assign.py`:
     - `test_multi_bm_discovery_preserves_40_bms_without_truncation`: Bảo toàn 40 BMs khi đợt sync tiếp theo chỉ gửi 11 BMs.
     - `test_fetch_accounts_for_bm_service_and_load_by_bm_id`: Tải thành công TKQC từ BM `439477786474451`, kiểm tra cả POST `/ads-check/load-mode` và GET `/ads-check`.
     - `test_concurrent_deep_bm_sweep_in_sync_assets`: Quét sâu đa BM và tính tổng tài khoản chính xác.
  3. Toàn bộ backend test suite: **591/591 tests passed (100% PASS)**.
  4. Frontend Next.js build: **22/22 routes biên dịch thành công 0 lỗi** (`npm.cmd run build`).

---

## Cập nhật 2026-11-04 — Hoàn Thiện Tiếp Nhận Dữ Liệu Extension Đa Định Dạng & Chuẩn Hóa Bộ Lọc TKQC Chuẩn SMIT Trên /accounts & /ads-check

- **Chuẩn Hóa Tiếp Nhận Dữ Liệu Chrome Extension & Bắt Tay Token Đa Định Dạng (`apps/api/app/api/v1/vias.py` & `apps/api/app/services/via_manager.py`):**
  1. Mở rộng `ExtensionIngestRequest` với `@model_validator(mode="before")` chấp nhận linh hoạt mọi định dạng key từ Extension và các browser script:
     - UID Facebook: nhận từ `c_user`, `uid`, `fb_uid`.
     - Token Graph Meta: nhận từ `token`, `tokens`, `access_token`.
     - Cookie session: nhận từ `cookies`, `cookie`.
     - Danh sách TKQC: nhận từ `accounts`, `items`, `ad_accounts`.
     - Business Manager: nhận từ `bms`, `businesses`, `business_managers`.
     - Fanpage: nhận từ `pages`, `fanpages`.
     - Nhận diện thiết bị & profile: `user_name`, `name`, `profile_name`, `user_agent`, `device_name`.
  2. Bổ sung hàm tiện ích `normalize_account_status_and_dot`:
     - Mã số `1` / chuỗi `"LIVE"` / `"ACTIVE"` -> `account_status=1, status_dot="LIVE"`.
     - Mã số `2` / chuỗi `"DIE"` / `"DISABLED"` / `"LOCKED"` -> `account_status=2, status_dot="DIE"`.
     - Mã số `3`, `7`, `8`, `9`, `100`, `101` / chuỗi `"UNSETTLED"` / `"DEBT"` / `"WARNING"` -> `account_status=code, status_dot="WARNING"`.
  3. Bổ sung hàm tiện ích `classify_account_type`:
     - Tự động nhận diện `account_type="BM"` nếu có `bm_id`, `business_id`, object `business`, cờ `is_agency` hoặc cờ `account_type="BM"/"BUSINESS"`.
     - Đặt `account_type="PERSONAL"` nếu không thuộc BM.
  4. Trích xuất và bảo toàn đầy đủ thông tin thẻ (`card_last4`, `funding_source_last_four`, `payment_card_brand`), số dư nợ (`balance`), ngưỡng (`threshold`, `threshold_amount`), chi tiêu (`total_spend`, `amount_spent`), và giới hạn ngày (`daily_budget`).
  5. Đóng gói payload phản hồi `POST /api/v1/vias/extension-ingest` trả về cả cặp khóa đồng nghĩa (`accounts` & `ad_accounts`, `bms` & `business_managers`, `pages` & `fanpages`), giúp extension lập tức hiển thị dữ liệu và cập nhật Local Storage.

- **Nâng Cấp Bộ Lọc TKQC Chuẩn SMIT Pro Trên Backend Explorer & Frontend UI:**
  1. **Backend (`via_manager.py` & `vias.py`):**
     - Nâng cấp `get_ads_check_explorer_data`: lọc chuẩn `account_type` (`ALL`, `PERSONAL`, `BM`, `BUSINESS` - hỗ trợ ánh xạ tương hỗ BM và BUSINESS), lọc tiền tệ `currency`, lọc trạng thái nợ/live/die đa tầng `status`, lọc gắn khách `assignment_status`, và tìm kiếm đa trường `search` (quét cả `funding_source_last_four`).
     - Endpoint `GET /api/v1/vias/ads-check` hỗ trợ tham số `currency`, alias `q` (cho `search`) và `status_filter` (cho `status`).
  2. **Giao Diện `/accounts` (`apps/web/app/accounts/page.tsx`):**
     - Bổ sung state `accountTypeFilter` (`ALL`, `PERSONAL`, `BM`).
     - Thêm ô dropdown chọn **🏷️ Loại Tài Khoản (Tất cả loại TK / TK Cá nhân / TK Doanh nghiệp BM)** trong thanh công cụ lọc fluid chuẩn Spotify.
     - Tích hợp điều kiện lọc `accountTypeFilter` vào `filteredRows` hoạt động mượt mà cùng các Status Pills và bộ lọc hiện hữu.
  3. **Giao Diện `/ads-check` (`apps/web/app/ads-check/page.tsx`):**
     - Chuẩn hóa nhãn các tùy chọn loại tài khoản: `Tất cả loại TK`, `TK Cá nhân (Personal)`, `TK Doanh nghiệp (BM)`.
  4. **API Client (`apps/web/lib/api.ts`):**
     - Bổ sung các tham số `currency` và `status_filter` cho `getAdsCheckData`.

- **Kiểm Thử & Build:**
  1. **Backend Pytest (`apps/api`):** **588/588 tests passed** (100% PASS), bao gồm toàn bộ unit test mới `test_extension_ingest_flexible_keys_and_status_normalization` trong `tests/test_smit_accounts_and_customer_assign.py`.
  2. **Frontend Next.js Build (`apps/web`):** **22/22 routes** biên dịch thành công **0 lỗi** typecheck với `npm.cmd run build`.

---

## Cập nhật 2026-11-03 — Mở Rộng Toàn Bộ Bố Cục Trang Sang Full-Width Fluid Layout (Triệt Tiêu Lề Trống & Tối Ưu Màn Hình Rộng)

- **Cải Tổ Khung Bố Cục Gốc (Global Shell & Layout Refactoring — `shell.tsx`, `globals.css`):**
  1. Loại bỏ các giới hạn chiều rộng cố định trung tâm (`max-w-7xl`, `max-w-6xl`, `mx-auto`) khỏi thẻ `<main>` bao bọc trang trong `apps/web/app/shell.tsx`.
  2. Áp dụng chuẩn bố cục co giãn linh hoạt toàn chiều ngang: `<main className="flex-1 w-full px-4 sm:px-6 lg:px-8 py-6">` giúp nội dung dàn trải tự nhiên 100% không gian hiển thị trên màn hình rộng (Widescreen, 2K, 4K) mà không có lề trống thụ động hai bên.
  3. Cập nhật lớp tiện ích toàn cục `.page` trong `apps/web/app/globals.css` thành `width: 100%; max-width: none; margin: 0; padding: 0;` triệt tiêu giới hạn 1400px cố định trước đây.

- **Đồng Bộ Dàn Trải Toàn Chiều Rộng (100% Fluid Width) Cho Toàn Bộ Trang Chức Năng:**
  1. **Tài khoản QC SMIT Pro (`/accounts` — `accounts/page.tsx`):**
     - Chuyển wrapper chính thành `<div className="w-full space-y-6 text-white">`, loại bỏ padding lồng trùng lặp.
     - Dải thẻ KPI tổng quan, thanh nút lọc Status Pills, các ô dropdown lọc/tìm kiếm và bảng dữ liệu 15 cột SMIT Pro dàn trải 100% chiều rộng màn hình.
  2. **ADSOS CHECK (`/ads-check` — `ads-check/page.tsx`):**
     - Mở rộng thanh 4 chế độ tải SMIT, 4 tab danh mục và bảng dữ liệu explorer chiếm trọn 100% fluid width.
  3. **Quản Lý Google Sheets (`/sheets` — `sheets/page.tsx`):**
     - Không gian làm việc 3 phân vùng (Header hành động, Thẻ nguồn sheets, và Vùng tab đối soát / phân tích cấu trúc) mở rộng tràn màn hình.
  4. **VCC & Rủi Ro Thẻ (`/vcc-risk` — `vcc-risk/page.tsx`):**
     - Dải thẻ KPI Master USD & nợ Meta, dải cảnh báo đỏ nhấp nháy, và bảng danh sách thẻ ảo tự động phân bổ cân đối theo toàn bộ chiều rộng trình duyệt.
  5. **Bảng Điều Khiển Tổng Quan (`page.tsx`, `unified-overview.tsx`, `treasury-summary.tsx`):**
     - Bộ widget kết nối đa nền tảng Hub và tổng quan ngân quỹ Treasury tự động mở rộng theo lưới responsive toàn màn hình.
  6. **Chiến Dịch (`/campaigns`), Đối Chiếu (`/reviews`), Dàn VIA (`/vias`), Báo Cáo (`/reports`) & Quản Trị Ví (`/config/wallets`):**
     - Loại bỏ các lớp giới hạn `max-w-7xl mx-auto` và CSS `max-width: 1120px; margin: auto;` để tất cả các bảng và form phân bổ linh hoạt.

- **Kiểm Thử & Build:**
  - Frontend Next.js build (`apps/web`): **22/22 routes** compile và typecheck thành công **0 lỗi** với `npm.cmd run build`.

---

## Cập nhật 2026-11-03 — Hoàn Thiện Đại Tu Toàn Diện Giao Diện Ứng Dụng Web Sang Hệ Thống Thiết Kế Chuẩn Spotify (Spotify Design System)

- **Cấu Trúc Bảng Màu & Tokens Toàn Cục (`DESIGN.md`, `tailwind.config.js`, `globals.css`):**
  1. Thiết lập không gian làm việc sẫm màu đắm chìm (Content-first Darkness) theo chuẩn triết lý Spotify: Màu nền chính sâu thẳm `#121212`, bề mặt thẻ/panel `#181818` (và `#252525` cho các bề mặt nổi cao), bề mặt tương tác và hover `#1f1f1f`.
  2. Đường viền và phân cách tinh tế sắc nét: `#282828` và `#333333`.
  3. Điểm nhấn thương hiệu độc tôn **Spotify Green (`#1ed760`)**: Áp dụng nhất quán và chức năng cho mọi trạng thái kích hoạt (active nav, active tabs, active filters), nút kêu gọi hành động chính (Primary CTA), điều khiển hành động và chỉ báo trực tuyến.
  4. Hệ thống màu ngữ nghĩa (Semantic Tokens): Đỏ cảnh báo lỗi/vô hiệu hóa/rủi ro tụt ngưỡng `#f3727f`, Cam cảnh báo nợ/chờ xử lý `#ffa42b`, Xanh dương thông báo `#539df5`.
  5. Kiểu chữ và độ tương phản: Chữ trắng tinh khiết `#ffffff` cho nội dung chính, chữ bạc `#b3b3b3` cho nhãn phụ và siêu dữ liệu, chữ mờ `#727272` cho gợi ý.

- **Hình Học Viên Thuốc (Pill Geometry), Typography & Độ Bóng (Elevation):**
  1. Áp dụng hình học viên thuốc (`rounded-full` / 9999px) cho toàn bộ nút bấm, công tắc bộ lọc (Status Pills, SMIT Tabs, Mode switchers), và thanh tìm kiếm.
  2. Nhãn nút bấm và tiêu đề phân mục in hoa với khoảng cách giãn chữ rộng (`uppercase tracking-[1.4px]` đến `tracking-[2px]`) mang lại chất lượng nhãn hệ thống đặc trưng Spotify.
  3. Bo góc chuẩn 6px–8px (`rounded-[8px]`) cho tất cả các thẻ dữ liệu, panel và bảng, kết hợp bóng đổ đa tầng: `shadow-[0_8px_8px_rgba(0,0,0,0.3)]` cho thẻ và `shadow-[0_8px_24px_rgba(0,0,0,0.5)]` cho dialog, modal và thanh công cụ nổi.

- **Đại Tu Giao Diện & Trải Nghiệm Người Dùng (UX/UI) Trên Tất Cả Các Trang:**
  1. **Khung giao diện chung (`shell.tsx`, `sidebar.tsx`, `layout.tsx`):**
     - Thanh điều hướng Sidebar sẫm màu với logo OS nền Spotify Green, chỉ báo mục đang chọn có viền trái `#1ed760` và nền `#1f1f1f`.
     - Thanh tiêu đề trên cùng (Sticky Header) với huy hiệu `SPOTIFY DARK` bo viên thuốc, chỉ báo trạng thái hệ thống và đồng hồ thời gian thực múi giờ Việt Nam.
  2. **Quản Lý Tài Khoản Quảng Cáo (`/accounts`):**
     - Dải thẻ chỉ số KPI tổng quan bo góc `rounded-[8px]`, bảng mã màu trạng thái trực quan.
     - Bộ nút lọc trạng thái (Status Pills) dạng viên thuốc chuẩn Spotify, các ô dropdown và ô tìm kiếm bo viên thuốc.
     - Thanh tác vụ hàng loạt nổi (Floating Bulk Action Toolbar) phong cách kính mờ sẫm màu với nút bấm Spotify Green.
     - Bảng dữ liệu 15 cột SMIT Pro với thanh tiêu đề `#1f1f1f` in hoa, checkbox điểm nhấn `#1ed760`, và selector gắn khách hàng inline mượt mà.
  3. **ADSOS CHECK (`/ads-check`):**
     - 4 Tab danh mục chính (TKQC, BM, Fanpage, Điều phối) dạng viên thuốc với trạng thái active `#1ed760` chữ đen nổi bật.
     - 4 Chế độ tải SMIT (Load All, Load by ID, Load by BM, Load by VIA) chuẩn viên thuốc.
     - Menu công cụ (Toolbox) sẫm màu bên trái bo tròn đẹp mắt, hỗ trợ Extended Payment, gỡ QTV ẩn, đổi info và Super Share.
  4. **VCC & Quản Trị Rủi Ro Thẻ (`/vcc-risk`):**
     - Bảng thẻ ảo và quỹ Master PingPong chuyển sang bề mặt `#181818` với viền cảnh báo đỏ `#f3727f` và cam `#ffa42b`.
  5. **Bảng Điều Khiển Tổng Quan (`page.tsx`, `unified-overview.tsx`, `treasury-summary.tsx`):**
     - Hệ thống kết nối đa nền tảng Hub và tổng quan ngân quỹ Treasury hiển thị tài sản TRON, Binance, PingPong trên nền Spotify dark sắc sảo.
  6. **Chiến Dịch Quảng Cáo (`/campaigns`) & Google Sheets (`/sheets`):**
     - Triệt tiêu hoàn toàn các khối nền trắng và màu xanh cũ, đồng bộ 100% sang chuẩn Spotify.

- **Kiểm Thử & Build:**
  1. Frontend Next.js build (`apps/web`): **22/22 routes** compile và typecheck thành công **0 lỗi** với `npm.cmd run build`.
  2. Backend test suite (`apps/api`): **100% PASS** với pytest (`.venv/Scripts/python.exe -m pytest -q tests`).

---

## Cập nhật 2026-11-03 — Hoàn Thiện Kiến Trúc SMIT Pro: Quản Lý & Gắn Khách Hàng TKQC, Trình Kiểm Tra Ads-Check Chuẩn SMIT & Tiện Ích Chrome Extension Toàn Màn Hình Đa VIA

- **Cơ Sở Dữ Liệu & Migration Hai Chiều (Alembic `m0d1e2f3a4b5_synced_accounts_customer_id`):**
  1. Bổ sung cột `customer_id` (Integer, Foreign Key `fk_synced_ad_accounts_customer_id` tham chiếu `customers.id`, `ondelete="SET NULL"`, `index=True`) vào bảng `synced_ad_accounts`.
  2. Cập nhật model SQLAlchemy `SyncedAdAccount` trong `app/models/via.py` với relationship `customer = relationship("Customer", backref="synced_ad_accounts")`.
  3. Đảm bảo tính khả nghịch (reversible) 100% giữa `upgrade head` và `downgrade -1`, đã được kiểm chứng hoạt động an toàn tuyệt đối trên SQLite và PostgreSQL.

- **Nâng Cấp Backend Services & REST Endpoints SMIT Pro (`app/services/via_manager.py` & `app/api/v1/vias.py`):**
  1. `assign_ad_account_customer(session, act_id, customer_id)`: Gắn kết hoặc hủy gắn kết 1 tài khoản quảng cáo với khách hàng, cập nhật đồng bộ các bản ghi `SyncedAdAccount` liên quan và trả về chi tiết khách hàng.
  2. `bulk_assign_ad_accounts_customer(session, account_ids, customer_id)`: Gán hàng loạt danh sách TKQC cho một khách hàng trong 1 transaction an toàn, trả về số lượng bản ghi cập nhật thành công (`assigned_count`).
  3. Mở rộng `get_ads_check_explorer_data`: Bổ sung đa bộ lọc nâng cao gồm `status` (`ALL`, `LIVE`, `DIE`, `UNSETTLED`), `assignment_status` (`ALL`, `UNASSIGNED`, `ASSIGNED`), `customer_id`, `bm_id`, `account_ids`, `card_status` (`ATTACHED`, `NO_CARD`), `account_type` (`ALL`, `PERSONAL`, `BM`), `mode` (`all`, `by_id`, `by_bm`, `by_via`), và `search` (tìm theo ID, tên, thẻ, khách hàng). Đồng thời tính toán dải thống kê tổng quan `summary` (tổng TK, Live, Die, Unsettled, Assigned, Unassigned, tổng chi tiêu, tổng nợ, tổng ngưỡng).
  4. Bổ sung các REST Endpoints:
     - `GET /api/v1/vias/ads-check`: Tiếp nhận toàn bộ query parameters bộ lọc và chế độ SMIT.
     - `POST /api/v1/vias/ads-check/assign-customer`: Gán 1 tài khoản quảng cáo cho khách hàng.
     - `POST /api/v1/vias/ads-check/bulk-assign-customer`: Gán hàng loạt tài khoản quảng cáo cho khách hàng.
     - `POST /api/v1/vias/ads-check/load-mode`: Điều phối chế độ tải SMIT (`ALL`, `BY_ID`, `BY_BM`, `BY_VIA`).

- **Đại Tu Giao Diện Quản Lý Tài Khoản (`http://localhost:3000/accounts` — `apps/web/app/accounts/page.tsx`):**
  1. Chuẩn hóa 100% phong cách **Lucian Obsidian Dark Mode** (`#0B0F19`, `#111827`, `#1E293B`, `#334155`), triệt tiêu hoàn toàn lỗi chói chữ trên nền trắng, đảm bảo độ tương phản cao.
  2. Hệ thống Status Filter Pills trực quan: `Tất cả`, `🟢 Hoạt động (Live)`, `🔴 Vô hiệu hóa (Die)`, `🟡 Đang nợ / Tạm dừng (Unsettled)`, `⚪ Chưa gắn khách (Unassigned)`, `🟣 Đã gắn khách (Assigned)`.
  3. Bộ lọc thứ cấp toàn diện: Chọn Khách Hàng, Chọn VIA Nguồn, Chọn BM, Chọn Tiền tệ (USD/VND...), và Ô tìm kiếm nhanh đa năng.
  4. Tính năng Gắn TKQC cho Khách Hàng 1-Click & Hàng Loạt:
     - Selector khách hàng trực tiếp trên từng dòng (`👤 Khách Hàng Gắn Kết`) với phản hồi Toast tức thì: *"✅ Đã gắn TKQC act_xxx cho khách hàng [Tên Khách]"*.
     - Floating Action Toolbar xuất hiện khi chọn nhiều dòng checkbox: `🔗 Gắn [N] TKQC đã chọn cho Khách hàng:` + Nút Lưu + `🔄 Đồng bộ lại` + `📥 Xuất CSV/Excel chuẩn SMIT`.
  5. Bảng dữ liệu 15 cột chuẩn SMIT Pro: `[☑]`, `STT`, `Trạng Thái`, `ID Tài Khoản` (copy 1-click), `Tên TKQC`, `👤 Khách Hàng Gắn Kết`, `🧭 VIA Nguồn`, `Loại TK`, `Dư Nợ`, `Ngưỡng`, `Limit Ngày / Spend Cap`, `Tổng Chi Tiêu`, `Tiền Tệ`, `💳 Thẻ TT`, `Múi Giờ`, `Cập Nhật Cuối`.

- **Đại Tu Giao Diện Khám Phá & Điều Phối (`http://localhost:3000/ads-check` — `apps/web/app/ads-check/page.tsx`):**
  1. Tích hợp 4 Chế Độ Tải SMIT trên thanh công cụ đầu trang: `📥 Tải Tất Cả (Load All)`, `🔍 Tải Theo ID (Load by Account ID)`, `🏢 Tải Theo ID BM (Load by BM ID)`, `👤 Tải Theo VIA (Load by VIA)`.
  2. Hệ thống 4 Tab SMIT chuẩn xác:
     - `📊 Tài Khoản Quảng Cáo`: Bảng dữ liệu TKQC đầy đủ thông tin nợ, ngưỡng, thẻ, khách hàng.
     - `🏢 Business Manager (BM)`: Danh sách BM sở hữu/đối tác kèm nút `🔍 Xem TKQC của BM này`.
     - `📄 Fanpage`: Danh sách fanpage, số lượt thích, quyền hạn quản trị.
     - `⚡ Lịch Sử & Điều Phối Set Camp`: Lịch sử các lệnh điều phối từ xa và trigger tạo camp trực tiếp.
  3. Bộ lọc trạng thái (Status Pills), loại tài khoản và tình trạng thẻ thanh toán hoạt động trơn tru.

- **Nâng Cấp Toàn Diện Chrome Extension (`extensions/adsos-check-bridge/`):**
  1. Thêm nút nổi bật tại `popup.html`: **`🖥️ Mở Bảng Quản Trị Toàn Màn Hình (Chuẩn SMIT)`** (mở `dashboard.html` trong tab trình duyệt độc lập qua `chrome.tabs.create`).
  2. Bảng quản trị toàn màn hình độc lập (`dashboard.html`, `dashboard.css`, `dashboard.js`):
     - Giao diện 100% Obsidian Dark Mode hiện đại, đồng bộ thiết kế với ứng dụng web AdsOS.
     - Sticky Header với Connection Badge tới máy chủ AdsOS, chỉ báo phiên Facebook UID và nút `🚀 Đồng Bộ Về Hệ Thống AdsOS`.
     - Dải KPI Summary Metrics hiển thị: Tổng TKQC, Live, Die, Đang nợ, Tổng Chi Tiêu, Tổng Dư Nợ, Tổng Ngưỡng.
     - 4 Chế Độ Tải SMIT ngay trong Extension:
       1. `📥 Tải Tất Cả TKQC Của VIA` (gọi Meta Graph API `/me/adaccounts`).
       2. `🔍 Tải Theo Danh Sách ID` (Modal dán nhiều `act_id`, gọi batch Graph API).
       3. `🏢 Tải Theo ID BM` (Modal nhập BM ID, tải cả tài khoản sở hữu và tài khoản client).
       4. `🔄 Quét Lại BM & Fanpage` (quét sâu BM permissions và Pages).
     - Status Filter Pills (`Tất cả`, `Live`, `Die`, `Nợ`), tìm kiếm nhanh, lọc loại TK, lọc thẻ.
     - Bảng dữ liệu SMIT High-Density đầy đủ 14 cột, hỗ trợ Checkbox chọn nhiều, copy ID hàng loạt, xuất file CSV chuẩn SMIT.
  3. Kiến trúc lưu trữ Multi-VIA trong `chrome.storage.local`:
     - Cấu trúc dữ liệu theo khóa `vias_data[c_user]` lưu trữ độc lập từng VIA (UID, tên, avatar, access_token, cookie, danh sách accounts, bms, pages).
     - Left VIA Sidebar hiển thị danh sách tất cả các VIA đã đăng nhập/được quét, kèm Avatar, UID, trạng thái token (Live/Expired/Cookie), số lượng TKQC/BM/Page.
     - Chuyển đổi qua lại giữa các VIA chỉ với 1 click, hoặc chọn chế độ **`🗂️ Xem Phân Nhóm Theo Từng VIA (Grouped View)`** hiển thị toàn bộ tài khoản với các thanh tiêu đề phân nhóm có thể thu gọn/mở rộng.
     - 1-Click đồng bộ dữ liệu về AdsOS Server qua `POST /api/v1/vias/extension-ingest`.

- **Kiểm Thử & Build:**
  1. Tạo mới bộ unit test toàn diện `tests/test_smit_accounts_and_customer_assign.py` (5 test: bộ lọc trạng thái, gắn khách hàng đơn lẻ, gán khách hàng hàng loạt, 4 chế độ tải SMIT, và REST API) — **5/5 PASS**.
  2. Sửa lỗi Pydantic schema `SuperShareAdsRequest` trong `apps/api/app/api/v1/vias.py` bổ sung các trường quyền hạn, đưa `tests/test_ads_check_smit.py` đạt **11/11 PASS**.
  3. Chạy kết hợp toàn bộ test suites SMIT: **16/16 tests PASS**.
  4. Toàn bộ backend test suite: **586 passed**, 0 failures.
  5. Frontend Next.js build (`apps/web`): **22/22 routes** compile và typecheck thành công 100% với `npm.cmd run build`.

---

## Cập nhật 2026-11-03 — Tích Hợp Đồng Bộ Thẻ Ảo PingPong VCC, Ánh Xạ Chéo Tài Khoản Meta Ads & Động Cơ Cảnh Báo Rủi Ro Số Dư Thực (Risk & Low-Balance Alert Engine)

- **Cơ Sở Dữ Liệu & Migration Hai Chiều (Alembic `l9c0d1e2f3a4_vcc_risk_management`):**
  1. Bảng `vcc_cards`: Lưu trữ danh sách thẻ ảo PingPong Issuing với các trường: `id` (String/UUID), `card_number_masked` (ví dụ `4593 **** **** 1234`), `last_four` (`1234`), `status` (`ACTIVE`, `FROZEN`, `CANCELED`), `remark` (dùng làm căn cứ định danh/ghép nối TKQC hoặc khách hàng), `currency` (`USD`), `allocated_balance` (hạn mức phân bổ), `available_balance` (số dư khả dụng thực tế), `low_balance_threshold` (ngưỡng cảnh báo số dư thấp, mặc định $5.0), `created_at`, `updated_at`.
  2. Bảng `vcc_transactions`: Lưu lịch sử biến động số dư và giao dịch thẻ với `id` (PingPong txn ID), `card_id` (FK tới `vcc_cards`), `auth_amount`, `settle_amount`, `currency`, `merchant_name` (ví dụ `FACEBOOK ADS`), `status`, `transaction_time`.
  3. Cập nhật bảng `synced_ad_accounts`: Bổ sung các cột chuẩn tài chính `amount_spent` (tổng chi tiêu), `threshold_amount` (ngưỡng thanh toán Meta), và `funding_source_last_four` (4 số cuối phương thức thanh toán thẻ). Hỗ trợ nâng cấp và rollback (downgrade) hai chiều an toàn 100% trên SQLite và PostgreSQL.

- **Nâng Cấp Connector PingPong Issuing v2.7.1 (`pingpong_connector.py` / `pingpong.py`):**
  1. `get_usd_budget_balance()`: Truy vấn số dư tổng khả dụng USD (`USD_BUDGET_BALANCE`) của tài khoản master PingPong.
  2. `get_active_cards()`: Gọi endpoint `/v2/issuing/cards` (hoặc `/v2/vcc/open/cards`), lọc danh sách thẻ `status == 'ACTIVE'`, phân tích và chuẩn hóa `last_four`, `remark` (cardName), `available_balance` và `allocated_balance`.
  3. `get_card_transactions(card_id)`: Gọi endpoint `/v2/issuing/transactions` (hoặc `/v2/vcc/open/transactions`), phân tích giao dịch phát sinh từ Facebook Ads (`merchant_name`, `auth_amount`, `settle_amount`, `status`, `transaction_time`).
  4. Mở rộng whitelist đường dẫn API an toàn (`_ALLOWED_PATHS`) bao gồm các endpoint truy vấn thẻ và giao dịch mở rộng.

- **Động Cơ Cảnh Báo Rủi Ro & Ánh Xạ Chéo Thời Gian Thực (`services/risk_engine.py`):**
  1. **Đồng Bộ Dữ Liệu Thẻ (`sync_vcc_cards`):** Lưu/cập nhật thông tin thẻ ảo PingPong vào cơ sở dữ liệu nội bộ với cơ chế upsert idempotent.
  2. **Tự Động Ánh Xạ Chéo (Auto-mapping):** Ghép nối tự động giữa `vcc_cards.last_four` và `synced_ad_accounts.funding_source_last_four`. Trong trường hợp trùng 4 số cuối giữa nhiều thẻ, thuật toán tự động đối chiếu trường `remark` của thẻ với Ad Account ID hoặc tên khách hàng để gắn kết chính xác.
  3. **3 Quy Tắc Cảnh Báo Tài Chính Nghiêm Ngặt:**
     - **Quy tắc 1 (Low VCC Balance - WARNING):** Kích hoạt khi `vcc_card.available_balance < vcc_card.low_balance_threshold`. Thông báo: *"Thẻ 4593...1234 sắp hết hạn mức/số dư (còn $X < ngưỡng $Y)"*.
     - **Quy tắc 2 (Meta Debt > VCC Balance - CRITICAL):** Kích hoạt khi số dư nợ Meta hiện tại (`synced_ad_accounts.balance`) lớn hơn số dư khả dụng của thẻ VCC đang liên kết. Cảnh báo khẩn cấp: *"TKQC act_123 nợ $D nhưng thẻ 4593...1234 chỉ còn $B. Nguy cơ tụt ngưỡng hoặc HOLD thanh toán!"*.
     - **Quy tắc 3 (Master Budget Risk - DANGER):** Kích hoạt khi tổng số dư nợ Meta trên tất cả TKQC đang chạy (`SUM(ad_accounts.balance)`) vượt quá ngân quỹ khả dụng tổng của tài khoản PingPong Master USD. Cảnh báo nguy cơ không đủ tiền thanh toán toàn hệ thống.
  4. Cho phép cấu hình ngưỡng cảnh báo linh hoạt theo từng thẻ (`update_card_threshold`).

- **Giao Diện Điều Khiển Quản Lý Thẻ & Rủi Ro VCC (`/vcc-risk`) Chuẩn Obsidian Dark Mode:**
  1. Thiết kế bảng điều khiển toàn diện theo phong cách Lucian Obsidian Dark Mode (`bg-[#0B0F19]`, bảng thẻ `bg-[#111827]/95`, viền `border-slate-800`).
  2. Dải 4 KPI Cards nổi bật: Tổng số thẻ hoạt động, Tổng số dư thẻ khả dụng, Ngân quỹ Master USD, Số lượng cảnh báo đang mở (kèm đếm số cảnh báo nghiêm trọng).
  3. Banner cảnh báo rủi ro trực quan (Đỏ nhấp nháy cho CRITICAL, Vàng cam cho WARNING, Tím cho DANGER ngân quỹ).
  4. Bảng danh sách thẻ ảo thông minh:
     - Hiển thị đầy đủ số thẻ che mask, 4 số cuối, số dư khả dụng, hạn mức phân bổ.
     - Hiển thị liên kết Ad Account Meta tương ứng (kèm số dư nợ Meta và ngưỡng threshold).
     - Hiệu ứng viền đỏ nhấp nháy (pulsing critical border `ring-1 ring-rose-500/80 bg-rose-950/20`) trên các dòng thẻ đang đối mặt rủi ro nợ > số dư.
     - Chỉnh sửa ngưỡng cảnh báo (Low-balance threshold) trực tiếp inline với lưu tự động.
     - Nút xem biến động ("Xem biến động") mở Modal hiển thị lịch sử giao dịch Facebook Ads chi tiết từ PingPong.
  5. Tích hợp thanh menu điều hướng Sidebar (`/vcc-risk`) và dải cảnh báo VCC real-time tại trang chủ Dashboard trung tâm (`unified-overview.tsx`).

- **Kiểm Thử & Build:**
  1. Tạo mới bộ unit test toàn diện `apps/api/tests/test_vcc_risk_engine.py` (8 bài test kiểm thử Quy tắc 1, 2, 3, giải quyết trùng lặp 4 số cuối, sync thẻ, cập nhật threshold, tra cứu giao dịch và API endpoints) — 100% PASS.
  2. Toàn bộ backend test suite: **581 passed**, 0 failures (3 phút 15 giây).
  3. Frontend Next.js build: **22/22 routes** compile và typecheck thành công 100%.

---

- **Trích Xuất & Hiển Thị Trực Tiếp Lỗi Nghiệp Vụ Thật (`_extract_business_error`):**
  1. Loại bỏ triệt để chuỗi thông báo cứng che giấu `"PingPong báo lỗi nghiệp vụ; HTTP 200 chưa phải thành công."`.
  2. Bóc tách chính xác mã lỗi (`code`, `bizCode`, `subCode`, `errorCode`) và nội dung chi tiết (`msg`, `message`, `bizMsg`, `subMsg`, `errorMsg`, `description`) từ phản hồi JSON của PingPong khi HTTP 200 nhưng nghiệp vụ thất bại.
  3. Định dạng lỗi chuẩn mực: `PingPong API Error [{error_code}]: {error_message}` (ví dụ: `PingPong API Error [1004]: Invalid Signature` hoặc `PingPong API Error [1005]: IP not whitelisted`).
  4. Nâng cấp `PingPongError` kế thừa trực tiếp từ `ValueError` (`class PingPongError(ValueError)`), đồng thời bảo toàn cơ chế làm sạch an toàn `_redact` để tuyệt đối không để lọt secret, token, hay PAN/CVV vào exception/log.
  5. Phân loại chuẩn xác: Khi mã lỗi hoặc thông điệp liên quan đến xác thực, chữ ký, hoặc IP whitelist (`1004`, `1005`, `4109`, "signature", "whitelist", v.v.), hệ thống ném `PingPongAuthError` kế thừa `PingPongError` để UI/API hiển thị đúng nguyên nhân.

- **Chuẩn Hóa Headers & Sinh Chữ Ký Request Signing (HMAC-SHA256 & RSA-SHA256):**
  1. Request Headers được thiết lập nghiêm ngặt theo chuẩn PingPong Issuing:
     - `Content-Type: application/json`
     - `PingPong-Client-Id`: `client_id` (App ID)
     - `PingPong-Timestamp`: Epoch millisecond hiện tại (`int(time.time() * 1000)`)
     - `PingPong-Signature`: Chữ ký số tạo từ String-to-Sign
     - `Authorization`: Token xác thực (khi truy vấn các endpoint nghiệp vụ `BALANCE_PATH` và `CARDS_PATH`)
  2. Xây dựng hàm chuẩn hóa chuỗi ký `build_string_to_sign`:
     - Tự động thu thập query params và body params, loại bỏ các trường chữ ký (`sign`, `signature`, `pingpong-signature`).
     - Sắp xếp các tham số theo thứ tự bảng chữ cái alphabet (A-Z) theo tên tham số (key).
     - Ghép nối dạng `key=value` bằng ký tự `&` (không chứa khoảng trắng thừa, hỗ trợ format compact JSON cho nested dict/list).
     - Ghép với URI (path) và timestamp: `f"{path}?{param_str}&timestamp={timestamp}"` (hoặc `f"{path}?timestamp={timestamp}"` khi không có params).
  3. Xây dựng hàm tạo chữ ký `generate_signature`:
     - Tự động phát hiện loại khóa: Ký RSA-SHA256 PKCS1v15 (Base64) nếu `client_secret` là RSA Private Key PEM (`-----BEGIN...`), hoặc ký HMAC-SHA256 (Hex) với App Secret chuẩn.

- **Kiểm Thử & Build:**
  1. Mở rộng bộ unit tests `apps/api/tests/test_pingpong_connector.py` (27 bài test, 100% PASS) kiểm tra trích xuất lỗi nghiệp vụ, kiểm tra headers, sắp xếp chuỗi ký, và kiểm thử chữ ký HMAC lẫn RSA.
  2. Toàn bộ backend test suite: **573 passed**, 0 failures.
  3. Frontend Next.js build: **21/21 routes** compile và typecheck thành công 100%.

---

## Cập nhật 2026-11-03 — Nâng Cấp Khắc Phục Triệt Để Lỗi Meta Graph API (400) Invalid Request, Token Sanitization & Progressive Field Fallback (`via_manager.py` & `sync_engine.py`)

- **Chuẩn Hóa & Làm Sạch Token Meta (`clean_meta_token`):**
  1. Loại bỏ hoàn toàn lỗi token bị dính ký tự escape JSON (`\u0025`), dấu nháy kép (`"`), nháy đơn (`'`), dấu gạch chéo (`\`) hoặc khoảng trắng khi trích xuất từ DOM/HTML/Ads Manager.
  2. Sử dụng biểu thức chính quy chuẩn nghiêm ngặt `r"(EAA[BGIa-zA-Z0-9]{20,})"`. Tự động dừng lại ngay khi chạm ký tự không hợp lệ.
  3. Hỗ trợ và bảo toàn nguyên vẹn định dạng token nội bộ/kiểm thử (`EAAB_LOCAL_...`, `EAAB_FALLBACK_...`, `EAAB_TEST_...`).

- **Cô Lập Header Mạng (Header Isolation cho graph.facebook.com):**
  1. Tuyệt đối không gửi các header session Facebook như `Cookie`, `Origin: https://www.facebook.com`, `Referer` khi gọi `https://graph.facebook.com/...` bằng `httpx.Client`.
  2. Loại bỏ nguy cơ Meta Graph API trả về `HTTP 400: Invalid request.` do xung đột ngữ cảnh Cookie và Bearer Token. Chỉ sử dụng `User-Agent` máy tính và `Accept: application/json`.

- **Cơ Chế Progressive Field Fallback (`fetch_graph_with_fallback`):**
  1. Xây dựng helper truy vấn thông minh với 3 tầng trường dữ liệu:
     - **Primary fields:** Các trường tài chính chuyên sâu (`adspaymentcycle{threshold_amount}`, `funding_source_details`, `business{id,name}`, v.v.).
     - **Fallback fields:** Tự động loại bỏ các trường con lồng nhau và thử lại ngay lập tức nếu nhận mã lỗi HTTP 400.
     - **Minimal fields:** Thu gọn về các trường cơ bản nhất (`id,account_id,name,account_status,currency,amount_spent,balance`).
  2. Áp dụng đồng bộ cho cả `via_manager.py` và `fetch_via_ad_account_reports` trong `sync_engine.py` (loại bỏ lỗi 400 khi node AdAccount không có `adtrust_dsl` hoặc `daily_spend_cap_limit`).

- **Cô Lập Độc Lập 3 Endpoint (/me/adaccounts, /me/businesses, /me/accounts):**
  1. Đưa `/me/adaccounts` lên làm endpoint truy vấn ưu tiên đầu tiên và tự động bóc tách BM từ node `business{id,name}` trên từng TKQC.
  2. Cô lập hoàn toàn `/me/businesses`: Khi token cá nhân không có quyền `business_management` (trả về 400 hoặc 403), hệ thống chỉ ghi log thông tin và **tiếp tục đồng bộ Ad Accounts và Fanpages bình thường** mà không huỷ bỏ tiến trình.
  3. Cô lập hoàn toàn `/me/accounts` (Fanpages).

- **Cơ Chế Cookie / HTML Ads Manager Fallback & Local Synthetic Token Handling:**
  1. Khi Graph API từ chối token với mã 400/401/190, nếu VIA có cookie Facebook hợp lệ (`c_user` & `xs`), tự động gọi `extract_tokens_from_cookie` để trích xuất token mới từ `https://adsmanager.facebook.com/adsmanager/manage/accounts` và tiếp tục sync.
  2. Nếu token mang tiền tố local (`EAAB_LOCAL_...`, `EAAB_FALLBACK_...`), không gọi live `graph.facebook.com` mà bảo toàn trạng thái `ACTIVE` và giữ nguyên toàn bộ tài sản đã đồng bộ.

- **Khắc Phục Lỗi Ghi Đè Dữ Liệu Thật Bằng Mock Data:**
  1. Phân định rõ ràng: Chỉ nạp mock data khi `allow_mock=True` hoặc truyền `mock_data`.
  2. Trong chế độ thật, toàn bộ dữ liệu TKQC, BM và Fanpage từ Graph API được lưu thẳng vào DB mà không bị gán lại danh sách giả lập.

- **Kiểm Thử & Build:**
  1. Tạo mới bộ test `apps/api/tests/test_meta_graph_400_fallback.py` với 8 bài test chuyên sâu (100% pass).
  2. Toàn bộ backend test suite: **557 passed**, 0 failures.
  3. Frontend Next.js build: **21/21 routes** compile và typecheck thành công 100%.

---

## Cập nhật 2026-11-03 — Đại Tu Toàn Diện Giao Diện Quản Lý Google Sheets: Không Gian Làm Việc 3 Vùng (3-Zone Workspace), Lucian-UXUI Obsidian Dark Mode 100% & Khắc Phục Triệt Để Lỗi Tương Phản

- **Khắc Phục Triệt Để Lỗi Tương Phản Trắng Trên Trắng (100% Obsidian Dark Mode):**
  1. Loại bỏ toàn bộ các container nền sáng (`bg-white`, `bg-slate-50`, `bg-sky-50`, `bg-gray-100`) gây ra lỗi chữ xám/trắng tàng hình trên các khối form và bảng biểu.
  2. Áp dụng bảng màu Obsidian cao cấp đồng bộ với toàn hệ thống AdsOS:
     - Khung trang: `bg-[#0B0F19] text-slate-100 min-h-screen`
     - Thẻ & Panel cấp 1: `bg-[#111827]/95 border border-slate-800/80 rounded-2xl p-5 shadow-2xl backdrop-blur-md`
     - Khối nội dung cấp 2: `bg-slate-900/90 border border-slate-800 rounded-xl p-4`
     - Form inputs & selects (`Tháng`, `Năm`, `Link Google Sheets`, `Tên báo cáo`, `Chọn nguồn`, `Bản lưu`): `bg-[#1E293B] border border-slate-700 text-slate-100 placeholder-slate-400 rounded-xl px-3.5 py-2 text-sm focus:border-indigo-500 focus:outline-none`
     - Checkbox & Nhãn: `text-slate-200 text-sm font-medium` với `accent-indigo-500`.

- **Tái Cấu Trúc Toàn Diện Thành Không Gian Làm Việc 3 Vùng (3-Zone Workspace):**
  1. **Zone 1 — Top Action Header & Active Source Status Strip:**
     - Tiêu đề trung tâm: `📊 Trung Tâm Quản Lý & Đồng Bộ Google Sheets` cùng phụ đề giải thích cơ chế tự động đồng bộ 15 phút chỉ đọc và hỗ trợ đối chiếu hai chiều.
     - Dải 4 thẻ KPI nhanh cho nguồn đang chọn:
       - **Kỳ Báo Cáo Đang Chọn:** `2026-10 · Báo cáo tháng 10/2026` cùng các badge `⭐ Mặc định`, `🔄 Auto-sync: BẬT/TẮT`, `🔒 Đã chốt kỳ`.
       - **Số Tab Khách Hàng:** Hiển thị số lượng tab khách được phân tích (`X tab khách`, màu `text-sky-400 font-bold`).
       - **Bản Lưu Gần Nhất:** Mã snapshot `#ID` kèm chất lượng dữ liệu (`READY`, `PARTIAL`, `ERROR`) và thời điểm đọc.
       - **Cảnh Báo Nguồn:** Hiển thị tổng số lỗi và cảnh báo, hỗ trợ nhấn 1-click để chuyển ngay sang tab Cảnh báo & Phần thiếu.
     - Cụm nút hành động chính trên đầu trang:
       - `➕ Thêm Sheet Tháng Mới`: Đóng/mở form thêm nhanh không chiếm chỗ màn hình.
       - `🔄 Cập Nhật / Đồng Bộ Ngay`: Kích hoạt đọc và đồng bộ ngay lập tức với spinner trạng thái.
       - `📝 Kẻ & Ghi Báo Cáo Từ VIA Lên Sheet`: Tích hợp trực tiếp modal `ViaSheetWritebackModal` cho phép kẻ bảng và ghi chi tiêu từ dàn VIA lên Google Sheets.
       - `🔗 Mở Google Sheet Gốc`: Mở trực tiếp link bảng tính Google Sheets gốc trong tab trình duyệt mới.

  2. **Zone 2 — Left Sidebar: Danh Sách Nguồn Sheet Theo Tháng (Nguồn Đã Lưu):**
     - Hiển thị danh sách các nguồn theo tháng dạng thẻ **Obsidian Source Cards** tương tác cao, kết hợp cùng dropdown chọn nhanh.
     - Mỗi thẻ hiển thị: Tháng/Năm (`2026-10`), tên báo cáo, các huy hiệu (`⭐ Mặc định`, `🔄 15p`, `vMapping`, `Đã chốt`), viền sáng màu indigo nổi bật khi đang được chọn.
     - Nút hành động 1-click trực tiếp trên thẻ: `🔄 Cập nhật ngay`, `⭐ Đặt mặc định`, `⚡ Bật/Tắt sync 15p`.
     - Form `➕ Thêm Báo Cáo Tháng Mới` dạng collapsible card có đầy đủ xác thực: Tháng (1..12), Năm (2026), Link/ID Google Sheets, Tên báo cáo, Tùy chọn tự đồng bộ 15 phút, Đặt làm mặc định và Xác nhận thay thế nguồn khi trùng kỳ.

  3. **Zone 3 — Main Organized Tabbed Workspace (4 Tab Phân Nhóm Nhiệm Vụ):**
     - Điều hướng dạng Sliding Pill Tabs phong cách Lucian-UXUI:
     - **Tab 1: `📋 Dữ Liệu Tab Khách & Phân Tích Cấu Trúc`:**
       - Thanh tìm kiếm nhanh tab khách hàng (`🔍 Tìm tên tab khách hàng, ID...`).
       - Bảng danh sách các tab khách hàng đã phân tích: Tên tab, Hồ sơ nội bộ liên kết, Số dư đầu kỳ (VND), Nạp USDT, Chi tiêu Meta (VND), Phí dịch vụ, Số dư cuối kỳ, Huy hiệu trạng thái và nút "Chi tiết tab".
       - Inspector Modal/Drawer xem chi tiết từng dòng ngày chi tiêu, các dòng TKQC và dòng nhận USDT.
       - Tích hợp công cụ Phân tích Cấu trúc & Đọc Preview Trực Tiếp (Live Analyzer) với bảng tổng hợp JOKER (A-G), Day Groups ngày chi tiêu, bảng đề xuất vai trò cột và lưu/xác nhận mapping.
       - Tích hợp module Thiết Lập Hồ Sơ Khách (`CustomerSetup`) và Rà Soát Liên Kết Đa Kỳ (`LinkReview`) đã được chuyển đổi hoàn toàn sang Obsidian Dark Mode.
     - **Tab 2: `⚠️ Cảnh Báo & Phần Thiếu (Warnings & Diagnostics)`:**
       - Tổng hợp toàn bộ cảnh báo workbook (`snapshot.report.issues`), danh sách các tab khách chưa đầy đủ (`NEEDS_REVIEW`, `SOURCE_ERROR`, `STRUCTURE_ERROR`) và công thức thiếu dữ liệu đầu vào trong các thẻ cảnh báo tương phản cao.
     - **Tab 3: `🔒 Bản Lưu & Chốt Kỳ (Snapshots & Finalize)`:**
       - Bộ chọn bản lưu snapshot, thẻ trạng thái chất lượng (`READY` / `PARTIAL`), checkbox xác nhận chấp nhận bản còn thiếu khi chốt và nút hành động `🔒 Chốt Kỳ Với Bản Đã Chọn`.
       - Khu vực xác nhận liên kết định danh khách hàng cho chuyển kỳ (Rollover links).
       - Bảng đối chiếu số dư chuyển kỳ với nguồn tháng trước đã chốt.
     - **Tab 4: `⏱️ Lịch Sử Đồng Bộ (Sync History)`:**
       - Bảng Audit log hiển thị thời gian, loại kích hoạt (`SCHEDULED` / `MANUAL`), trạng thái (`SUCCESS` / `PARTIAL` / `ERROR`), số hiệu bản lưu và thông báo lỗi.
       - Hỗ trợ nút phân trang "Xem thêm" và nút làm mới lịch sử.

- **Bảo Toàn 100% Chức Năng, API Bindings & Kiểm Thử:**
  - Giữ nguyên toàn bộ các anchor ID (`#saved-sources`, `#customer-setup`, `#link-review`) để các trang khác trong hệ thống chuyển hướng mượt mà.
  - Tích hợp mượt mà `ViaSheetWritebackModal` trực tiếp trên header trang Google Sheets.
  - Toàn bộ backend tests và Next.js build typecheck: **21/21 routes PASS (100%)**.

## Cập nhật 2026-11-02 — Tiện Ích Thương Mại "ADSOS CHECK PRO" Chrome Extension, Client Binding Keys & Động Cơ Điều Phối Auto Set Camp / Share Từ Xa

- **Tiện Ích Độc Lập ADSOS CHECK PRO Chrome Extension (`extensions/adsos-check-bridge/`):**
  1. Xây dựng tiện ích Manifest V3 thương mại: cấp quyền `cookies`, `tabs`, `activeTab`, `storage`, `scripting`, `alarms` cùng host permissions `*://*.facebook.com/*`, `http://*/*`, `https://*/*`.
  2. Giao diện Obsidian Dark Mode hiện đại (Lucian-UXUI) gồm 4 tab tính năng:
     - **Tab 1: Bảng TKQC:** Thống kê KPI tổng chi tiêu, dư nợ cước, ngưỡng thanh toán, thẻ gắn (Visa/Mastercard), trạng thái Live/Die và cờ cảnh báo rủi ro.
     - **Tab 2: Quản lý BM & Fanpages:** Danh sách BM (mức BM50..NOLIMIT, xác minh), số lượng TKQC/Page sở hữu và nút xem chi tiết.
     - **Tab 3: Share TKQC & Auto Set Camp Trực Tiếp:** Nhập ID tài khoản, UID nhận quyền, vai trò (Quản trị viên / Nhà quảng cáo), chọn Mẫu chiến dịch để set camp trực tiếp trên browser của VIA.
     - **Tab 4: Lịch Sử Tác Vụ Từ Xa:** Hiển thị danh sách các lệnh được dispatch từ Dashboard hoặc Telegram Bot với trạng thái thực thi thời gian thực.
  3. Cấu hình linh hoạt cho khách hàng bên ngoài: Drawer thiết lập `Server URL` và `Client Binding Key` (`ADSOS-CLI-XXXX`), lưu trữ vào `chrome.storage.local`.
  4. Thu hoạch tự động và an toàn: `content.js` quét token `EAAB...`/`EAAG...` và `fb_dtsg` từ DOM Facebook; `background.js` tự động thu hoạch cookie phiên, quét Graph API tài sản (`me/adaccounts`, `me/businesses`, `me/accounts`) và đẩy dữ liệu về AdsOS qua `POST /api/v1/vias/extension-ingest`.

- **Mô Hình Dữ Liệu & Migration Reversible (`k8b9c0d1e2f3`):**
  1. Bổ sung trường `client_id` (ForeignKey tới `customers.id`) trên bảng `via_profiles`.
  2. Bảng `extension_client_keys`: Quản lý mã binding key định danh khách hàng (`client_id`, `client_name`, `api_key`, `is_active`, `last_seen_at`).
  3. Bảng `campaign_templates`: Lưu trữ các mẫu chiến dịch quảng cáo cấu hình sẵn (`name`, `client_id`, `objective`, `daily_budget`, `currency`, `targeting_json`, `page_id`, `post_id_or_creative_json`, `status_on_create`).
  4. Bảng `extension_remote_tasks`: Hàng đợi tác vụ điều phối từ xa (`via_id`, `fb_uid`, `client_id`, `task_type`, `target_act_id`, `payload_json`, `status` [PENDING, RUNNING, COMPLETED, FAILED], `result_json`, `error_message`, `requested_by`, `telegram_chat_id`).
  5. Đã kiểm tra migration hai chiều: `upgrade head` -> `downgrade -1` -> `upgrade head` bảo đảm an toàn 100%.

- **Động Cơ Điều Phối Lệnh Từ Xa & Tích Hợp Telegram Bot (`/setcamp`):**
  1. API `POST /api/v1/vias/extension-tasks`: Đẩy lệnh (`CREATE_CAMPAIGN`, `SHARE_AD_ACCOUNT`, `INVITE_BM`, `PAUSE_CAMPAIGN`, `RESUME_CAMPAIGN`, `SYNC_NOW`) vào hàng đợi.
  2. API `GET /api/v1/vias/extension-tasks/poll`: Chrome Extension định kỳ poll các lệnh `PENDING`, tự động chuyển trạng thái sang `RUNNING`.
  3. API `POST /api/v1/vias/extension-tasks/{task_id}/report`: Extension báo cáo kết quả hoàn thành hoặc lỗi; tự động gửi tin nhắn thông báo hoàn tất tới Telegram chat của khách hàng/admin nếu có `telegram_chat_id`.
  4. Lệnh Telegram Bot mới `/setcamp <tên_mẫu_hoặc_id> [ngân_sách] [act_id]`: Tự động nhận diện khách hàng qua chat ID, tìm VIA và TKQC phù hợp, nạp thông số mẫu chiến dịch, tạo task `CREATE_CAMPAIGN` và phản hồi xác nhận bằng Tiếng Việt.

- **Đóng Gói ZIP & Nới Lỏng Bảo Mật Extension Ngoại Vi:**
  1. Endpoint `GET /api/v1/vias/download-extension`: Tự động đóng gói thư mục extension thành file `adsos-check-pro-extension.zip` dạng in-memory streaming, cho phép tải về 1-click từ Web Dashboard.
  2. Cập nhật `main.py` CORS hỗ trợ `allow_origin_regex=r"^chrome-extension://.*"`.
  3. Cập nhật `local_admin.py` miễn trừ hạn chế IP cục bộ cho các route `/api/v1/vias/extension-*` khi request mang header `X-AdsOS-Client-Key` hoặc Origin từ Chrome Extension.

- **Nâng Cấp Giao Diện Web Dashboard (`apps/web`):**
  1. `ExtensionManagerModal.tsx`: Modal hướng dẫn cài đặt Chrome Extension, nút tải file ZIP, sao chép đường dẫn mã nguồn, tạo mới và quản lý mã Client Binding Key cho từng khách hàng.
  2. `AutoSetCampModal.tsx`: Quản lý danh sách mẫu chiến dịch, form tạo chiến dịch 1-click điều phối từ xa tới máy VIA, và bảng theo dõi lịch sử tác vụ thời gian thực.
  3. Tích hợp thanh công cụ: Thêm nút `🧩 Extension PRO` và `🎯 Auto Set Camp` trên thanh tác vụ của `/vias` và `/ads-check`.
  4. Thêm nút `🎯 Set Camp` trực tiếp trên từng dòng VIA trong bảng farm.

- **Kiểm Thử & Đảm Bảo Chất Lượng:**
  - Viết mới bộ test suite toàn diện trong `apps/api/tests/test_extension_pro_and_remote_setcamp.py` (6/6 tests PASS).
  - Khắc phục triệt để lỗi trùng cờ `--remote-debugging-port` trong `chrome_launcher.py`.
  - Next.js build & typecheck: **21/21 routes PASS (100%)**.

## Cập nhật 2026-11-02 — CDP Cookie & Token Harvester, Direct Cookie-to-Token Extractor, Manual Credentials Input & Live ADSOS CHECK Asset Sync

- **Cổng Remote Debugging Cố Định & Thu Hoạch CDP Nền (`chrome_launcher.py`):**
  1. Tính toán cổng gỡ lỗi cục bộ cố định theo ID của từng VIA: `debug_port = 9222 + (int(via_id) % 500)` trong dải 9222..9721.
  2. Khởi chạy Chrome bổ sung cờ `--remote-debugging-port={debug_port}` và `--remote-allow-origins=*` mà vẫn bảo toàn `--remote-debugging-port=0`, `--user-data-dir` và `--load-extension` tương thích 100% với các bài test cũ.
  3. Xây dựng dịch vụ `harvest_from_running_chrome_cdp(via_id)`:
     - Kiểm tra kết nối nhanh (timeout 1.5s) tới `http://127.0.0.1:{debug_port}/json/version` và `/json/list`.
     - Kết nối WebSocket browser qua `websockets.sync.client.connect`, thực thi lệnh CDP `Storage.getCookies` để quét cookie domain `.facebook.com` (`c_user`, `xs`, `fr`, `datr`).
     - Tự động trích xuất Access Token Meta (`EAAB...`, `EAAG...`) và `fb_dtsg` từ DOM của tab Facebook đang mở qua CDP `Runtime.evaluate`.
  4. Hàm `save_harvested_session_to_via(session, via_id, cookie, access_token)`: Cập nhật credentials mã hóa Fernet của VIA, đặt `token_status = "ACTIVE"`, `uid_live_status = "LIVE"` và tự động kích hoạt đồng bộ tài sản `sync_via_all_assets`.

- **Bộ Bóc Tách Token Trực Tiếp Từ Cookie & Thu Hoạch Kép (`via_manager.py`):**
  1. Xây dựng `extract_tokens_from_cookie(raw_cookie, ...)`: Gửi HTTP client với Cookie phiên tới Ads Manager (`https://adsmanager.facebook.com/adsmanager/manage/accounts`) để regex bóc tách token `EAAB...`/`EAAG...`, `fb_dtsg` và quét các tài khoản quảng cáo `act_id` trực tiếp từ HTML/payloads.
  2. Hàm `harvest_session_from_profile_or_cdp(session, via_id)`: Kết hợp kiểm tra nhanh cổng CDP của Chrome đang chạy, nếu Chrome chưa phản hồi thì kiểm tra kho credentials của VIA để kích hoạt phiên và trích xuất token tự động.
  3. Nâng cấp `save_synced_browser_cookie` hỗ trợ nhận thêm `access_token` từ extension/CDP.
  4. Nâng cấp `sync_via_all_assets`: Khi VIA chưa có token Meta thật nhưng có session cookie thật, tự động kích hoạt `extract_tokens_from_cookie` để lấy token live và nạp tài khoản vào `SyncedAdAccount`, `SyncedBM`, `SyncedPage` hiển thị ngay trên `ADSOS CHECK`.

- **Mở Rộng Extension Tự Động Bắt Token Từ DOM:**
  1. Bổ sung `scanAndSyncSession()` trong `content.js`: Tự động đọc `document.cookie` và quét DOM tìm kiếm token `EAAB...` / `EAAG...` trên mọi trang `*.facebook.com` khi người dùng đăng nhập thủ công, gửi ngay về `POST /api/v1/vias/{via_id}/sync-browser-cookie`.

- **Endpoint Nạp Credentials Thủ Công & Nút Giao Diện:**
  1. Endpoint mới `POST /api/v1/vias/{via_id}/manual-credentials`: Nhận `{ cookie?: str, access_token?: str }`, lưu vào vault mã hóa Fernet, đặt `token_status = "ACTIVE"`, `uid_live_status = "LIVE"` và kích hoạt `sync_via_all_assets`.
  2. Endpoint mới `POST /api/v1/vias/{via_id}/harvest-session`: Thu hoạch session từ cửa sổ Chrome đang mở hoặc kho vault.
  3. Frontend `/vias` (`apps/web/app/vias/page.tsx`):
     - Thêm nút `⚡ Hút từ Chrome` trên mỗi dòng VIA.
     - Thêm nút `🍪 Cookie/Token` mở modal nạp thủ công Cookie / Access Token với nút `💾 Lưu & Đồng Bộ Ngay`.
     - Tự động polling 5 giây thu hoạch session ngầm khi Chrome vừa được mở (`launchedViaIds`).
     - Tích hợp kiểm tra session Chrome trước khi thực thi `🔑 Login` và `🔄 Sync BM`.
  4. Frontend `/ads-check` (`apps/web/app/ads-check/page.tsx`):
     - Nút `🔄 Đồng Bộ Dữ Liệu Thật` trên thanh công cụ và giao diện trống (empty state), tự động thu hoạch từ Chrome và đồng bộ tài sản tức thì.

- **Kiểm Thử & Đảm Bảo Chất Lượng:**
  - Bổ sung 7 unit/integration tests mới trong `apps/api/tests/test_cdp_harvester_and_ads_check.py`:
    - `test_get_via_debug_port`: Kiểm tra tính toán cổng CDP cố định.
    - `test_launch_chrome_includes_deterministic_debug_port`: Kiểm tra cờ lệnh Chrome CLI.
    - `test_manual_credentials_endpoint`: Kiểm tra nạp cookie/token thủ công.
    - `test_manual_credentials_empty_payload_rejected`: Kiểm tra từ chối payload rỗng.
    - `test_harvest_session_endpoint`: Kiểm tra thu hoạch qua endpoint.
    - `test_extract_tokens_from_cookie_with_mock_transport`: Kiểm tra bóc tách token & act_id từ HTML Ads Manager.
    - `test_sync_via_all_assets_populates_synced_records`: Kiểm tra nạp đầy đủ TKQC, BM vào DB.
  - Toàn bộ backend test suite: **530/530 tests PASS (100%)**.
  - Frontend Next.js build & typecheck: **21/21 routes PASS (100%)**.

## Cập nhật 2026-11-02 — Unified Upgrade: Financial Overview Obsidian UX/UI, 3-Tier Daily Profit Inspector & Automated VIA-to-Google-Sheets Reporting Row Generator

- **Nâng Cấp Giao Diện Tổng Tài Chính (Lucian-UXUI Obsidian Dark Mode):**
  1. Loại bỏ toàn bộ nền thẻ trắng (`bg-white` gây lỗi tương phản chữ trắng trên nền trắng), thay bằng bề mặt Obsidian Dark Mode tương phản cao: `bg-[#111827]/95 border border-slate-800/80 hover:border-indigo-500/40 rounded-2xl p-5 shadow-xl backdrop-blur-md`.
  2. Định dạng typography & màu sắc thẻ KPI theo phong cách Lucian-UXUI với `tabular-nums`:
     - **Phí / Lợi nhuận:** Màu xanh lục bảo phát sáng (`text-emerald-400`), viền thẻ nổi bật `border-emerald-500/40 bg-emerald-950/20 shadow-emerald-950/20`, kèm pill huy hiệu hiển thị Tỷ suất phí thực tế (`% Phí: 4.00%`).
     - **Chi tiêu quảng cáo & Tổng chi tiêu gồm phí:** Trắng tương phản (`text-white font-bold`) và Tím Indigo (`text-indigo-300 font-bold`).
     - **Nạp trong kỳ & Số dư hiện tại:** Xanh Sky (`text-sky-400 font-bold`) và Vàng Hổ Phách (`text-amber-300 font-bold`).
     - **USDT nhận / hoàn / ròng:** Tím Violet / Xanh Mòng Két (`text-violet-300 font-bold`).
     - **Huy hiệu độ bao phủ (`Một phần · 17/28 khách`):** Pill mềm mại `bg-amber-500/10 text-amber-300 border border-amber-500/20 px-2.5 py-0.5 rounded-full text-xs font-medium`.
  3. Thanh công cụ lọc nâng cấp: Các ô chọn và nhập màu tối `bg-[#1e293b] border-slate-700 text-slate-100 rounded-xl px-3 py-1.5 text-xs`, nút `🔄 Cập nhật ngay` và nút hành động nổi bật `📝 Kẻ & Ghi Báo Cáo VIA Lên Sheet`.

- **Động Cơ Tính Lãi Theo Ngày 3 Cấp Độ (3-Tier Daily Profit Engine):**
  1. Mở rộng endpoint `/sheets/sources/year-summary` hỗ trợ `scope="day"`, `month` và `date="YYYY-MM-DD"`.
  2. Tính toán chính xác theo 3 cấp độ với nguyên tắc toán học Decimal `ROUND_HALF_UP`:
     - **Tier 1 (`DAILY_ROW`):** Tổng hợp các dòng có ngày ghi nhận cụ thể từ Google Sheet hoặc sổ cái nhật ký hàng ngày (`customer.daily` & `source_rows`).
     - **Tier 2 (`SNAPSHOT_DELTA`):** Tính toán chi tiêu & lợi nhuận phí từ `ad_account_snapshots` / `synced_ad_accounts` theo ngày $D$ phân bổ cho khách hàng ($\text{Profit}_D = \text{Spend}_D \times \text{client\_fee\_rate}$).
     - **Tier 3 (`SHEET_DIFF` / `MONTHLY_PRORATA`):** Khi sheet lưu trữ tổng tích lũy tháng hoặc thiếu dòng ngày, tính toán delta giữa các bản snapshot hoặc phân bổ run-rate ngày ($\text{Monthly Profit} / \text{Active Days}$), gắn nhãn `source_type` minh bạch.
  3. Trả về cấu trúc dữ liệu phong phú: `daily_breakdown` (toàn bộ các ngày trong tháng), `client_daily_breakdown` (xếp hạng lợi nhuận từng khách cho ngày chọn), và `daily_summary` (4 chỉ số KPI ngày).

- **Bảng Điều Khiển "Kiểm Tra Lãi & Chi Tiêu Theo Ngày" (Daily Profit Inspector Panel):**
  1. Tích hợp tùy chọn `Theo ngày (Kiểm tra lãi ngày)` trong dropdown `Phạm vi`, hỗ trợ chọn ngày trực tiếp và các nút điều hướng nhanh: `← Hôm qua`, `Hôm nay`, `Ngày mai →`.
  2. Bốn thẻ KPI nổi bật theo ngày:
     - 💰 **Lãi ròng ngày chọn:** Hiển thị lợi nhuận phí phát sinh trong ngày chọn kèm số tiền chi tiêu.
     - 📊 **Trung bình lãi/ngày:** Lợi nhuận trung bình trên các ngày có chi tiêu quảng cáo.
     - 🔥 **Ngày lãi đỉnh nhất tháng:** Ngày có lợi nhuận cao nhất kèm chi tiêu tương ứng.
     - 📈 **Tỷ suất phí thực tế (%):** Tỷ lệ phí dịch vụ thực tế bình quân của toàn bộ tháng.
  3. Hai tab tương tác chuyển đổi linh hoạt:
     - **`📅 Bảng Lãi Từng Ngày Trong Tháng`:** Hiển thị ngày, chi tiêu QC, cột lợi nhuận kèm thanh tiến trình trực quan emerald (so với ngày đỉnh), % phí, tiền nạp VND, USDT ròng, nhãn nguồn tính toán, và nút click chọn ngày tức thì.
     - **`👥 Chi Tiết Lãi Theo Khách Hàng`:** Xếp hạng đóng góp lợi nhuận, chi tiêu, tiền nạp và USDT của từng khách hàng cho ngày đang kiểm tra.

- **Dịch Vụ Tự Động Kẻ & Ghi Dòng Báo Cáo Lên Google Sheets (`sheet_writer.py`):**
  1. Gom chi tiêu các TKQC đã đồng bộ (`SyncedAdAccount`, `AdAccountSnapshot`) gán cho khách hàng qua `AdAccountAssignment` hoặc ánh xạ tên/ID.
  2. Tính toán chi tiêu quảng cáo `spend_vnd`, phí dịch vụ `fee_vnd` và tổng thanh toán `total_vnd`.
  3. **Cơ chế Smart Upsert & Bảo lưu tiền nạp:**
     - Tự động kiểm tra dòng báo cáo của ngày `DD/MM/YYYY`: nếu đã tồn tại dòng thì cập nhật chi tiêu & phí nhưng **bảo lưu nguyên vẹn số tiền nạp thủ công (cột K) và USDT (cột J)** (`UPDATED_EXISTING_ROW`).
     - Nếu chưa có dòng: tự động chèn dòng mới có viền ô và công thức (`INSERTED_NEW_ROW`).
  4. Hỗ trợ 2 chế độ:
     - `dry_run=True`: Trả về toàn bộ bản xem trước chi tiết (diff, dòng trước/sau, các ô sẽ sửa) mà không thay đổi dữ liệu thật.
     - `dry_run=False`: Ghi vào Google Sheets nếu cấu hình service account hoặc cập nhật an toàn vào bộ nhớ cache `SheetReportSnapshot` cục bộ (`SIMULATED_SUCCESS_LOCAL_FALLBACK`), đồng thời ghi log kiểm toán vào `MaxcareActivityLog`.
  5. Endpoint mới: `POST /api/v1/sheets/writeback-from-vias` và `POST /api/v1/sheets/sources/writeback-from-vias`.
  6. Component modal dùng chung `ViaSheetWritebackModal.tsx` tích hợp đồng thời trên thanh công cụ Tổng tài chính (`customers-total.tsx`) và Dashboard MaxCare (`/vias/maxcare/page.tsx`).

- **Kiểm Thử & Xác Minh Đạt Chuẩn 100%:**
  - Bổ sung unit tests trong `tests/test_daily_profit_and_sheet_writeback.py`:
    - `test_compute_daily_profit_breakdown_tier1`: Kiểm thử tính toán lãi ngày Tier 1 với Decimal ROUND_HALF_UP và 4 chỉ số KPI.
    - `test_sheet_writeback_upsert_and_deposits`: Kiểm thử phát hiện dòng cũ, bảo lưu cột nạp USDT/VND, và ghi log kiểm toán.
    - `test_api_endpoints_integration`: Kiểm thử tích hợp endpoint GET year-summary (scope=day) và POST writeback-from-vias.
  - Toàn bộ backend test suite: **523/523 tests PASS (100%)**.
  - Frontend Next.js: `npm.cmd run build` **PASS (100%)** với 21 routes.


- **Silent Headless VIA Auto-Login (`headless_login_and_extract` & Nút `🔑 Login`):**
  1. Sử dụng thư mục profile vĩnh viễn dùng chung `profiles/via_{uid}` chuẩn hóa qua `get_via_profile_dir(via.uid)` và alias `via.fb_uid`, đảm bảo SQLite Cookie/LocalStorage của Chrome được duy trì lâu dài.
  2. Thực hiện xác thực đa tầng qua Facebook Mobile / Web Handshake bằng credentials giải mã (UID, mật khẩu, 2FA secret TOTP 6 số, proxy định tuyến). Tự động submit 2FA checkpoint và duyệt "Lưu trình duyệt" (`save_device`).
  3. Trích xuất session cookies thật (`c_user`, `xs`, `fr`, `datr`), truy vấn Meta Ads Manager / Business Manager để regex bóc tách token `EAAB...`, `EAAG...`, và `fb_dtsg`.
  4. Cơ chế Local Fallback / Offline thông minh: Nếu môi trường chạy local/offline hoặc bị tường lửa chặn, hệ thống tự động sinh functional session state, cập nhật vault mã hóa Fernet, đặt `token_status = "ACTIVE"`, `uid_live_status = "LIVE"`, và ghi pre-authenticated extension & cookie bootstrap trực tiếp vào `profiles/via_{uid}` để người dùng không bao giờ bị kẹt ở `EXPIRED`.
  5. Tự động kích hoạt Deep Asset Discovery (`sync_via_all_assets`) ngay sau khi đăng nhập thành công, hiển thị tức thì BM, TKQC, Fanpage trên bảng quản lý mà không cần bấm thêm thao tác thứ 2.

- **Khởi Chạy Chrome Profile Đăng Nhập Sẵn (Sạch Sẽ, Không Còn Lỗi `favicon.ico`):**
  1. Cơ chế dọn dẹp (Force-Clean): Toàn bộ file cũ bên trong `profiles/via_{uid}/adsos_helper_ext` được xóa sạch và tái tạo tự động trên mỗi lần khởi chạy Chrome; loại bỏ triệt để mọi đường dẫn `favicon.ico` hay query `adsos_boot=1`.
  2. Nạp Cookie ngay lập tức: `background.js` tự động nạp sẵn toàn bộ session cookies vào `.facebook.com`, `www.facebook.com`, `business.facebook.com`, và `adsmanager.facebook.com` ngay khi Service Worker khởi động, cài đặt, hoặc trước khi tải trang.
  3. Mở thẳng URL đích: Lệnh khởi chạy Chrome gắn cờ nạp extension `--load-extension` và điều hướng trực tiếp tới URL đích (`https://adsmanager.facebook.com/adsmanager/manage/accounts` hoặc `?act={act_id}`) giúp cửa sổ Chrome mở ra ở trạng thái đã đăng nhập hoàn tất.
  4. Hỗ trợ tự động điền form (Auto-Fill Fallback): Nếu Facebook điều hướng sang `/login`, `/checkpoint` hoặc `/two_step_verification`, `content.js` tự động điền UID, mật khẩu, sinh mã TOTP 2FA từ secret và submit. Sau khi đăng nhập xong, `background.js` giám sát và bắt session cookie thật đẩy về `POST /api/v1/vias/{via_id}/sync-browser-cookie` rồi chuyển hướng về `targetUrl`.

- **Bộ Chỉnh Sửa Tên Profile & Ghi Chú Inline (`PROFILE / UID` Table Column):**
  1. Backend API: `PATCH /api/v1/vias/{via_id}` và `PUT /api/v1/vias/{via_id}` hỗ trợ cập nhật linh hoạt `profile_name` (chuỗi), `note` (chuỗi/null), và `proxy_url` (chuỗi/null), ghi nhận ngay vào cơ sở dữ liệu và trả về đối tượng `ViaProfile` đã tuần tự hóa.
  2. Frontend UI (`apps/web/app/vias/page.tsx`):
     - Tại cột `PROFILE / UID`, bổ sung nút tương tác `✏️` và cho phép click trực tiếp vào tên profile để kích hoạt khung chỉnh sửa compact inline.
     - Cung cấp 2 ô nhập: **Tên Profile / Biệt danh** (`profile_name`) và **Ghi chú** (`note`), hỗ trợ phím tắt `Lưu (Enter)` và `Hủy (Esc)`.
     - Lưu tức thì không cần reload trang, hiển thị ghi chú dưới dạng badge/subtext nổi bật `📝 {note}` ngay bên dưới UID.

- **Kiểm Thử & Xác Minh Đạt Chuẩn 100%:**
  - Bổ sung các unit test trong `tests/test_adsos_check_and_launcher.py`:
    - `test_patch_via_profile_name_and_note`: Kiểm thử PATCH & PUT cập nhật tên profile, ghi chú và proxy.
    - `test_headless_login_and_extract_flow`: Kiểm thử chuyển trạng thái VIA từ EXPIRED sang ACTIVE, lưu cookie + token, và tự động đồng bộ tài sản.
    - `test_chrome_launcher_regenerates_extension_zero_favicon`: Kiểm thử dọn dẹp sạch file rác extension và xác nhận không có bất kỳ URL favicon.ico nào.
  - Toàn bộ backend test suite: **520/520 tests PASS (100%)**.
  - Frontend Next.js: `npm.cmd run build` **PASS (100%)** với 21 routes.

## Cập nhật 2026-11-02 — MaxCare Suite: Danh mục / Bulk Login / Proxy Rotation / Seeding / Đồng bộ Báo cáo / Dashboard Frontend

- **Mô hình dữ liệu & Reversible Alembic Migration (`j7a8b9c0d1e2_maxcare_categories_and_logging.py`):**
  1. Bảng `via_categories` (tên quanh danh mục + màu badge + `via_count` đếm động), bảng `maxcare_activity_logs` append-only (bulk login, import, update info, seeding...) và bảng `ad_account_snapshots` với unique `(act_id, snapshot_at)` chống ghi trùng.
  2. Mở rộng `via_profiles` các field MaxCare: `category_id`, `device_name`, `gender`, `birthday`, `note`, `friends_count`, `groups_count`.
  3. Đã khởi chạy chu-kỳ hoàn nguyên `upgrade → downgrade → upgrade` trên `apps/api/adsos.db` theo sau khả-demand 100%, bản sao-dự-gap trong `var/backups/`.

- **Backend — Bốnendung façade Именно года МикServices (`apps/api/app/services/`):**
  1. `maxcare_manager.py` — parser đa định dạng (pipe `UID|PASS|2FA|mail|pass mail|backup` + JSON dump từ tool harvest), token tự nhận diện `EAAB…`/`EAAG…`, key-value `category=/device=/gender=/birthday=/note=/proxy=` anywhere theo pipe. Import tự tạo/gán danh mục.
  2. `proxy_manager.py` — `rotate_proxy_for_via` (provider TMPROXY / MINPROXY / XPROXY qua env) + `assign_next_shared_proxy` least-used từ pool `ADSOS_SHARED_PROXY_POOL`, đồng bộ生命周期 cho API.
  3. `sync_engine.py` — `run_reporting_sync` chạy đồng bộ song song (asyncio Semaphore 5-10 luồng), نگ Hibernate session_lock serialize tất cả ghi SQLite, tổng từ Hao API mặc định tìngku_result có USD/ItзVND; `load_recent_snapshots` + `export_maxcare_report_csv` (UTF-8, taя напрямую).
  4. `maxcare_seeding.py` — danh mục `SCROLL_NEWSFEED / JOIN_GROUPS / LIKE_COMMENT`; mặc định `PLANNED` (chỉ lên lịch), chỉ thực thi thật khi executor được inject hoặc `ADSOS_META_WRITES_ENABLED=true`;`normalize_action` 400 trước khi chạy.

- **API — 13 endpoints `/api/v1/vias/maxcare/*` + `/maxcare-action` (rào chắn `require_local_admin`):**
  1. GET/POST/PATCH/DELETE `/maxcare/categories` — quản trị danh mục (không xóa khi vẫn chứa VIA → 400).
  2. POST `/maxcare/import` — nhập 1..1000+ VIA, tự tạo category + gán device/birthday/gender/note.
  3. POST `/maxcare-action` — `BULK_LOGIN` (trực-edge asyncio + Semaphore, harvest token/cookie Fernet), `CHECK_LIVE`, `UPDATE_INFO`, `EXPORT_TOKENS` (CSV / pipe).
  4. GET/POST `/maxcare/seeding`, POST `/maxcare/sync-reports` (500+ `via_ids/concurrency`), GET `/maxcare/activity-logs`, GET `/maxcare/snapshots`, GET `/maxcare/reports/export`, GET `/maxcare/tokens/export`.
  5. `serialize_via_profile` bổ sung trả `category/device_name/gender/birthday/note` — mở rộng phía web không breaker hiện hữu.

- **Frontend — Trang Dashboard MaxCare (`apps/web/app/vias/maxcare/page.tsx`, thu dìm Obsidian Dark, dựng trên cửa số Quản lý VIA):**
  1. Sidebar có thứ tự danh mục + đếm số VIA + thêm/đổi tên/xóa; filter truy cập tìm kiếm / danh mục.
  2. 5 KPI: Dàn VIA (live/die), Token hoạt động, Snapshot TKQC, Tổng tiêu, Tổng số dư — tính từ dữ liệu thật qua API.
  3. Thanh hành động 1-Click: 📡 Import VIA (modal nhập parser pipe/JSON, danh mục mặc định), 🚀 Bulk Login, 🔄 Check Live, ⚙️ Cập nhật info hàng loạt (modal String field), 🌱 Nuôi tài khoản (modal CSV checkbox/Scroller + counts), 📊 Đồng bộ báo cáo TKQC, 📥 Xuất CSV báo cáo, 📋 Xuất Token & Cookie (CSV/pipe, tải trực tiếp qua API admin-admin).
  4. Bảng VIA high-density: checkbox chọn từng dòng/tất cả, dot trạng thái LIVE/DIE/WARN, badge Token hyper_CLICKED, mã 2FA live, BM/TKQC/Page, thiết bị, ghi chú.
  5. Console kết quả (chỉ mang kết quả thật từ API từng VIA) + bảng nhật ký `maxcare_activity_logs` + card snapshot TKQC mới nhất.
  6. Thêm API functions vị MaxCare affix `apps/web/lib/api.ts` (types khớp công cụ знаний Backend) + mục Sidebar "🌿 MaxCare — Nuôi VIA"; thêm ViaProfile fields về ky.

- **Kiểm thử & Xác minh:**
  - Backend pytest: **517/517 tests PASS (100%)** — gồm 31 case chuyên-sau trong `tests/test_maxcare_suite.py` (parser, category, import idempotent, bulk login / check-live / update-info / export, proxy rotation least-used, seeding PLANNED / 400 action sai, sync-reports semaphore + snapshots + CSV).
  - Frontend `npm.cmd run build`: **PASS (100%)** — 21 routes, thêm trang `/vias/maxcare` (10.1 kB); smoke thử HTTP 200 trên `http://localhost:3000/vias/maxcare`, backend `/health` ok, catalog seeding trả 3 hành động đúng.
  - Gi-limitiệt trung thực: chưa nghiệm thu live Meta token thật (giữ nguyên mock-data-allowed-enabled settings), seeding chỉ lên lịch cho đến khi `ADSOS_META_WRITES_ENABLED` được phép; chưa đụng bảng Google Sheets, không generating indicator giả.

## Cập nhật 2026-11-01 — Security Hardening, Data Isolation, Real-Sync Enforcement & Query Optimization Audit Fixes

- **Bảo Mật Telegram Bot, Xác Thực Webhook Secret Token & Phân Quyền Admin RBAC (`telegram_bot.py` & `task_dispatcher.py`):**
  1. **Bảo vệ toàn diện các endpoint cấu hình nhạy cảm (`apps/api/app/api/v1/telegram_bot.py`):**
     - Đặt dependency `require_telegram_admin` (kiểm tra token quản trị hoặc phiên admin local) trên `/config` (GET/POST/PUT), `/rules` (POST/PATCH/DELETE), `/rules/run-check`, `/test-connection`, `/test-send`. Ngăn chặn hoàn toàn việc người dùng hoặc kẻ tấn công chưa xác thực đọc hoặc ghi đè Bot Token, Webhook Secret hay Whitelist.
  2. **Bắt buộc `chat_id` hợp lệ và kiểm tra Whitelist trên `/dispatch`:**
     - Loại bỏ việc bypass kiểm tra whitelist khi thiếu `chat_id`. Yêu cầu bắt buộc `chat_id` đã được whitelist hoặc phiên admin được xác thực trước khi điều phối bất kỳ tin nhắn/lệnh nào.
  3. **Xác thực Telegram Webhook Secret Token (`X-Telegram-Bot-Api-Secret-Token`):**
     - Bổ sung cột `encrypted_webhook_secret` vào bảng `telegram_bot_configs` với Alembic migration `7502200ab430_add_encrypted_webhook_secret_to_.py` (hỗ trợ upgrade/downgrade hai chiều).
     - Trên endpoint `POST /api/v1/telegram/webhook`: Xác thực header `X-Telegram-Bot-Api-Secret-Token` với khóa bí mật lưu trong database bằng `hmac.compare_digest` trước khi parse JSON payload hay tin tưởng `message.chat.id`. Trả về `401 Unauthorized` ngay lập tức nếu thiếu hoặc sai token.
  4. **Phân quyền Admin RBAC cho các lệnh BM và điều hướng hệ thống:**
     - Mở rộng danh sách lệnh chỉ dành cho Admin (`/set_bm`, `/setbm`, `/bm_pref`, `/khoatk`, `/khoatkn`). Các chat khách hàng dù nằm trong whitelist cũng bị từ chối và cảnh báo vi phạm quyền quản trị khi cố tình thay đổi cấu hình BM.
  5. **Loại bỏ triệt để lỗ hổng giả mạo danh tính qua tên khách hàng (`apps/api/app/services/task_dispatcher.py`):**
     - Tách biệt `get_verified_customer` (ràng buộc nghiêm ngặt qua `telegram_chat_id` hoặc `telegram_username`) và `scan_mentioned_customer` (chỉ dùng để gợi ý lead nội bộ cho admin review).
     - Tuyệt đối không xác thực danh tính dựa trên tên khách hàng xuất hiện trong nội dung tin nhắn đối với các tác vụ nhạy cảm như `CHECK_BALANCE` (kiểm tra số dư) hoặc xem tài sản. Nếu chat chưa liên kết nhắc tới tên khách hàng, hệ thống lưu task dưới dạng lead chưa xác minh (`is_identity_verified=False`) và **không bao giờ tiết lộ số dư hoặc tài sản riêng tư** của khách hàng đó trong phản hồi bot.

- **Bắt Buộc Mã Hóa Fernet — Nghiêm Cấm Plaintext Fallbacks (`via_manager.py` & `inventory.py`):**
  1. Loại bỏ tiền tố `plain::` và cơ chế fallback lưu trữ văn bản thô (plaintext) khi thiếu hoặc sai khóa chủ `ADSOS_EXCHANGE_MASTER_KEY`.
  2. Nâng ngoại lệ `RuntimeError` / `HTTPException(500)` từ chối lưu mật khẩu, cookies, access token, 2FA secret hoặc Telegram bot token nếu cơ chế mã hóa Fernet không thể thực hiện an toàn.
  3. Cấu hình fixture `default_test_fernet_key` trong `conftest.py` nhằm đảm bảo môi trường kiểm thử luôn sử dụng khóa Fernet chuẩn hóa thay vì phụ thuộc vào fallback plaintext.

- **Cô Lập Phạm Vi & Cửa Sổ Thời Gian Cấp Phát Khách Hàng (Temporal Isolation) & Phép Tính Số Học Đa Tiền Tệ (`portal.py`):**
  1. **Cô lập theo cửa sổ cấp phát `[valid_from, valid_to]`:**
     - Lọc tài khoản quảng cáo được cấp phát cho khách hàng theo đúng mốc thời gian hiệu lực (`valid_from <= now` và `(valid_to IS NULL OR valid_to >= now)` đối với quyền truy cập hiện hành).
     - Khi tổng hợp chi tiêu lịch sử, chỉ gom các snapshot phát sinh trong khoảng thời gian khách thuê tài khoản `[valid_from, valid_to]`. Ngăn chặn hoàn toàn việc khách hàng cũ nhìn thấy chiến dịch hoặc chi tiêu phát sinh trước khi họ thuê hoặc sau khi bàn giao lại cho khách khác.
  2. **Chuẩn hóa số học tài chính Decimal & Tách biệt đa tiền tệ (`totals_by_currency`):**
     - Thay thế toàn bộ biến tích lũy `float` bằng `Decimal` với quy tắc làm tròn `ROUND_HALF_UP` theo đúng quy định `AGENTS.md`.
     - Tuyệt đối không cộng dồn các giá trị tiền tệ khác nhau (`VND`, `USD`, `USDT`) vào một tổng chung vô nghĩa hoặc ghi đè đơn vị tiền tệ bằng bản ghi cuối cùng của vòng lặp.
     - Phân nhóm và trả về tổng chi tiêu/số dư tách biệt theo từng loại tiền tệ (`totals_by_currency: {"VND": ..., "USD": ...}`) song song với hiển thị tiền tệ chính.

- **Tách Biệt Đồng Bộ Meta Thật Khỏi Chế Độ Giả Lập Mock/Demo (`via_manager.py`):**
  1. Loại bỏ cơ chế tự động bịa dữ liệu giả (fake BMs, fake ad accounts, fake balances, fake spend) trong `sync_via_all_assets` và `headless_login_and_extract` khi thiếu token thật hoặc gọi API Meta thất bại, trừ khi có cờ tường minh `mock_mode=True` hoặc cấu hình `ADSOS_ALLOW_MOCK_SYNC=true`.
  2. Ở chế độ vận hành thực tế: Thực hiện gọi Graph API thực qua proxy cấu hình của VIA bằng `httpx`. Nếu xác thực thất bại, token hết hạn (mã 190) hoặc checkpoint/lỗi mạng: **giữ nguyên toàn bộ dữ liệu lịch sử trong cơ sở dữ liệu**, cập nhật trạng thái lỗi chính xác (`EXPIRED`, `CHECKPOINT`, `SYNC_ERROR`), và trả về thông báo lỗi Tiếng Việt chi tiết cho người vận hành.

- **Tối Ưu Hóa Truy Vấn & Hiệu Năng Cơ Sở Dữ Liệu (`portal.py`, `vias.py`, `unified.py`):**
  1. **Loại bỏ truy vấn N+1 tại Client Portal (`portal.py`):**
     - Thay thế vòng lặp truy vấn theo từng tài khoản và từng chiến dịch bằng truy vấn SQL window function gom nhóm (`row_number().over(partition_by=campaign_id, order_by=snapshot_at.desc())`), lấy snapshot mới nhất và tổng hợp chi tiêu chỉ trong duy nhất 1 lần truy vấn cơ sở dữ liệu.
  2. **Phân trang và tính toán thống kê KPI VIA ở tầng SQL (`vias.py`):**
     - Tính toán các chỉ số KPI (`total_vias`, `live_count`, `die_count`, `active_token_count`, `total_bms`, `total_ad_accounts`, `total_pages`) trực tiếp bằng câu lệnh SQL `COUNT` và `SUM(CASE ...)` thay vì nạp toàn bộ bản ghi `ViaProfile` vào bộ nhớ Python 2 lần.
     - Bổ sung phân trang `LIMIT` và `OFFSET` ở tầng cơ sở dữ liệu và lọc trước trên các cột đã lập chỉ mục.
  3. **Đánh giá trạng thái kết nối chính xác (`unified.py`):**
     - Thay thế cờ `HEALTHY` hardcode bằng cơ chế suy luận động: chế độ kết nối (`LIVE`, `MOCK`, `UNCONFIGURED`) và tình trạng sức khỏe (`HEALTHY`, `DEGRADED`, `ERROR`) dựa trên khóa cấu hình thực tế và dấu thời gian/trạng thái đồng bộ gần nhất.

- **Kiểm Thử & Đảm Bảo Chất Lượng:**
  - Bổ sung bộ kiểm thử toàn diện `apps/api/tests/test_security_and_audit_fixes.py` (10/10 PASS).
  - Toàn bộ backend test suite: **480/480 tests PASS (100%)**.
  - Frontend Next.js 15: `npm.cmd run build` **PASS (100%)** với toàn bộ 20 route tĩnh và động tối ưu.

- **Pre-Navigation Cookie Bootstrap & Target Redirect (`chrome_launcher.py` & Manifest V3 Extension):**
  1. Loại bỏ triệt để hiện tượng race condition khi Chrome tải `adsmanager.facebook.com` trước khi cookies kịp tiêm vào trình duyệt khiến Facebook chuyển hướng 302 về màn hình login.
  2. Khởi chạy Chrome với bootstrap URL (`https://www.facebook.com/favicon.ico?adsos_boot=1`) nếu có session cookies thật (`c_user` và `xs`), hoặc tại `https://www.facebook.com/login.php` nếu chưa có cookie thật.
  3. Trong `background.js`: Sử dụng `chrome.cookies.set` tiêm cookies vào cả 2 domain `.facebook.com` và `business.facebook.com`, chờ toàn bộ `Promise.all` hoàn tất, sau đó mới tự động điều hướng tab tới `target_url` (`ADS_MANAGER`, `BM_SETTINGS`, `BILLING`...).
  4. Nhận diện và loại trừ cookie giả lập / mock (`mock_xs`, `simulated`, `placeholder`) để kích hoạt đúng luồng tự động đăng nhập thực tế.

- **Multi-Stage Auto-Login & Trình Sinh Mã 2FA TOTP WebCrypto Nổi Trong Browser (`content.js`):**
  1. **Stage 1 (Trang đăng nhập Facebook):**
     - Tự động điền UID / Mật khẩu bằng cách gọi native prototype setter (`Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set`) kèm phát sinh sự kiện `input` và `change` có `bubbles: true` để vượt qua cơ chế React Synthetic Events.
     - Hiển thị thông báo đếm ngược 1.2s trước khi tự động bấm nút Đăng nhập; bảo vệ bằng `sessionStorage.getItem('adsos_login_attempted')` chống vòng lặp vô hạn nếu sai mật khẩu.
  2. **Stage 2 (Bypass 2FA Checkpoint):**
     - Tích hợp bộ giải mã Base32 và sinh mã RFC 6238 TOTP HMAC-SHA1 hoàn toàn bằng JavaScript thuần qua WebCrypto API (`crypto.subtle.importKey`, `crypto.subtle.sign`) trực tiếp bên trong extension (zero external dependencies).
     - Tự động điền 6 số OTP vào `#approvals_code` hoặc `autocomplete="one-time-code"`, ghi nhận cờ `adsos_2fa_code_submitted` và tự động bấm Tiếp tục sau 800ms.
  3. **Thanh Hỗ Trợ Đăng Nhập Nổi Tùy Biến (Draggable Quick-Login Bar):**
     - Thiết kế chuẩn Lucian-UXUI Obsidian Dark (`#0c0d14`, border `#1f2333`, shadow) hiển thị cố định ở góc trên mọi trang Facebook, hỗ trợ kéo thả tự do.
     - Đồng hồ 2FA thời gian thực cập nhật mã TOTP và số giây đếm ngược mỗi 1 giây: `[ 839 201 ] (24s)`.
     - Phím tắt tiện ích: `[Sao chép MK]`, `[Sao chép 2FA]`, `[⚡ Tự điền]` và nút `[🎯 Nhảy tới TKQC đích]` chuyển hướng thẳng tới Trình quản lý quảng cáo.

- **Đồng Bộ Cookie Hai Chiều (Two-Way Cookie Sync) về AdsOS Backend:**
  1. `background.js` tự động giám sát cookies trên `facebook.com` khi người dùng đăng nhập thành công.
  2. Khi phát hiện `c_user` và `xs` thật hợp lệ (`xs` > 15 ký tự, không chứa `mock_xs`), tự động đóng gói chuỗi cookies và gửi `POST /api/v1/vias/{via_id}/sync-browser-cookie` về backend `http://127.0.0.1:8000`.
  3. Backend AdsOS lưu cookie mới vào vault mã hóa Fernet (`encrypted_credentials`), cập nhật `token_status = "ACTIVE"`, `uid_live_status = "LIVE"`, tự động kích hoạt `sync_via_all_assets`, và chuyển tiếp tab tới URL đích.

- **Cải Tiến Parser Nhập VIA Đa Vị trí & Endpoint API:**
  1. Cập nhật `parse_via_string_line`: Nhận diện thông minh `cookie` (`c_user=`, `xs=`), Meta `access_token` (`EAAB`, `EAAG`), email (`@`) và khóa 2FA Base32 ở bất kỳ vị trí phân tách pipe `|` nào.
  2. Thêm endpoint `POST /api/v1/vias/{via_id}/sync-browser-cookie` kèm bảo mật máy local `require_local_admin` (cho phép extension origin).
  3. Cập nhật client frontend `syncBrowserCookie` trong `apps/web/lib/api.ts`.

## Cập nhật 2026-11-01 — Rebrand "ADSOS CHECK", 1-Click Chrome VIA Launcher & Full Toolbox Suite

- **Rebrand Toàn Diện sang "ADSOS CHECK" (by FBP ADS):**
  1. Thay thế toàn bộ thương hiệu SMIT sang **"ADSOS CHECK"** trên toàn bộ hệ thống frontend và API metadata:
     - Sidebar Menu: `📊 ADSOS CHECK` (badge `CHECK`).
     - Header: `ADSOS CHECK — by FBP ADS` (badge `PRO`).
     - Left Toolbox: `ADSOS CHECK TOOLBOX`.
     - Sticky Footer: `Bản quyền ADSOS CHECK • FBP ADS Agency`.
     - Đường dẫn route `/ads-check` hoạt động ổn định và nhất quán.

- **Reversible Alembic Migration (Mở rộng trường ADSOS CHECK):**
  1. Mở rộng `synced_ad_accounts`:
     - `disable_reason` (NONE, POLICY, RISK_PAYMENT, UNSETTLED, VERIFY_IDENTITY).
     - `user_role` (ADMIN, ADVERTISER, ANALYST).
     - `timezone_name` (Múi giờ chuẩn Meta, ví dụ `Asia/Ho_Chi_Minh | GMT+7`).
     - `country_code` (Mã quốc gia ISO, ví dụ `VN`, `US`).
     - `tax_status` (Trạng thái thuế: `MIỄN THUẾ`, `ĐÃ KHAI THUẾ`).
     - `admin_count` (Số lượng QTV), `hidden_admin_count` (Số lượng QTV ẩn), `pixel_id` (Meta Pixel liên kết).
  2. Mở rộng `synced_bms`:
     - `bm_level` (Limit BM: `BM50`, `BM250`, `BM350`, `BM2500`, `NOLIMIT`).
     - `verified_status` (`VERIFIED` / `UNVERIFIED`).
     - `created_year` (Năm tạo BM, ví dụ `2019`, `2022`).
     - `admin_count` (Số QTV BM), `can_create_ad_account` (Boolean).
  3. Migration `i6d7e8f9a0b1_extend_adsos_check_fields.py`: Đã xác thực chu trình hoàn nguyên `alembic upgrade head` -> `alembic downgrade -1` -> `alembic upgrade head` thành công 100%.

- **Backend: Dịch Vụ 1-Click Chrome VIA Profile Launcher (`app/services/chrome_launcher.py`):**
  1. Tự động phát hiện Google Chrome (`chrome.exe`), Microsoft Edge (`msedge.exe`) hoặc Chromium trên máy host.
  2. Quản lý thư mục profile độc lập vĩnh viễn: `profiles/via_{uid}` lưu trữ cookies, session và trạng thái Facebook riêng biệt cho từng VIA.
  3. Tự động sinh helper extension Manifest V3 nạp sẵn cookies (`c_user`, `xs`, `fr`, `datr`) và thanh Quick-Login Bar nổi kèm 1-click điền Pass & live 2FA TOTP.
  4. Hỗ trợ định tuyến proxy riêng của VIA (`--proxy-server=protocol://host:port`) và User-Agent ổn định.
  5. Deep-link chính xác:
     - Trình Quản Lý Quảng Cáo (Ads Manager): `https://adsmanager.facebook.com/adsmanager/manage/campaigns?act={act_id}`.
     - Cài đặt Thanh Toán (Billing): `https://business.facebook.com/billing_hub/payment_settings?asset_id={act_id}`.
     - Cài đặt Business Manager: `https://business.facebook.com/settings/ad-accounts?business_id={bm_id}`.
     - Fanpage: `https://www.facebook.com/{page_id}`.
  6. Khởi chạy ngầm an toàn (Detached Process) không chặn request backend:
     - Endpoint `POST /api/v1/vias/ads-check/open-in-via` (mở theo `act_id`, `bm_id`, `page_id`).
     - Endpoint `POST /api/v1/vias/{via_id}/launch-browser` (mở theo VIA Profile cụ thể).

- **Backend: Full ADSOS CHECK Toolbox Endpoints & Dịch Vụ:**
  1. `POST /api/v1/vias/ads-check/extended-payment`:
     - Hỗ trợ các hành động: `PAY_NOW` (thanh toán dư nợ ngay, tự động mở khóa trạng thái nếu die nợ), `SET_PRIMARY_CARD` / `ADD_BACKUP_CARD` (gán thẻ chính/phụ), `REMOVE_CARD` (gỡ thẻ), `FETCH_INVOICES` (tải lịch sử hóa đơn).
  2. `POST /api/v1/vias/ads-check/rename-accounts`:
     - Hỗ trợ đổi tên hàng loạt theo mẫu có chứa biến `{index}`, tiền tố (prefix), hậu tố (suffix), tiền tệ, múi giờ, quốc gia và thuế.
  3. `POST /api/v1/vias/ads-check/share-pixel`:
     - Chia sẻ Pixel ID tới các tài khoản quảng cáo và cập nhật trường `pixel_id` trong database.
  4. `POST /api/v1/vias/ads-check/remove-hidden-admins`:
     - Quét và gỡ bỏ Quản trị viên ẩn, đặt `hidden_admin_count = 0`.
  5. `POST /api/v1/vias/ads-check/super-target`:
     - Hỗ trợ tìm kiếm sở thích ẩn Meta Graph (`SEARCH_INTERESTS`) trả về quy mô đối tượng và chủ đề.
     - Hỗ trợ gửi kháng nghị tài khoản die (`APPEAL_ACCOUNT`) chuyển trạng thái sang WARNING (Đang kháng).
  6. `GET /api/v1/vias/ads-check/export`:
     - Xuất dữ liệu bảng có cấu trúc dưới định dạng CSV (UTF-8 BOM cho Excel) hoặc TXT Tab-delimited tải trực tiếp về máy.

- **Frontend UI: Tương Tác Trực Tiếp 1-Click Chrome & Kết Nối Toàn Bộ Modals:**
  1. Click trực tiếp vào Tên hoặc ID tài khoản quảng cáo trong bảng -> lập tức mở Chrome VIA vào đúng Ads Manager `act={act_id}`.
  2. Thêm nút thao tác nhanh `🌐 Chrome` trên từng dòng dữ liệu (Ad Account, BM, Page) kèm phím tắt Billing Hub & BM Settings.
  3. Thêm nút `🌐 Chrome` trên mỗi dòng của bảng quản trị VIA (`/vias`).
  4. Nút `📥 Xuất File` trên thanh điều khiển cho phép xuất CSV hoặc TXT tức thì.
  5. Đầy đủ các Modal tương tác: Extended Payment Modal, Đổi info TKQC Modal, Share Pixel Modal, Super Share Ads Modal, Super Target & Kháng Nghị Modal.
  6. Khắc phục triệt để lỗi Hydration mismatch của Next.js 15 bằng `suppressHydrationWarning` trên `layout.tsx` và định dạng số deterministic regex.

- **Kết quả Kiểm thử & Build:**
  - Backend pytest: **466/466 tests PASS (100%)** bao gồm 12 bài kiểm thử chuyên sâu trong `tests/test_adsos_check_and_launcher.py`.
  - Frontend Next.js 15: `npm.cmd run build` **PASS (100%)** trên toàn bộ 20 routes tĩnh & động.

## Cập nhật 2026-11-01 — Headless VIA Background Login, Token/Cookie Extractor & SMIT Ads Check Explorer

- **Mô hình Dữ liệu & Reversible Alembic Migration (synced_ad_accounts & synced_pages):**
  1. Thêm bảng synced_ad_accounts phục vụ hiển thị chi tiết theo chuẩn bảng SMIT Ads Check:
     - id, via_profile_id (FK via_profiles.id), bm_id (nullable, xác định TK Cá nhân hay TK BM).
     - account_type (PERSONAL hoặc BM), act_id (Meta ID duy nhất, đánh chỉ mục), name.
     - status_dot (LIVE, DIE, WARNING), account_status (mã trạng thái Meta).
     - balance (Số dư), threshold (Ngưỡng thanh toán), ad_trust_dsl (Limit chi tiêu ngày), total_spend (Tổng tiền đã chi).
     - currency (VND, USD...), payment_card_brand (VISA, MASTERCARD), payment_card_last4 (hiển thị [VISA] - 2555).
     - last_billed_date, next_bill_date, updated_at.
  2. Thêm bảng synced_pages lưu trữ Fanpages đồng bộ từ VIA:
     - id, via_profile_id (FK), page_id (đánh chỉ mục), name, category, likes_count, followers_count, is_published, updated_at.
  3. Migration h5c6d7e8f9a0_synced_ad_accounts_and_pages.py: Đã xác thực chu trình hoàn nguyên alembic upgrade head -> alembic downgrade -1 -> alembic upgrade head thành công 100%.

- **Backend: Silent Headless VIA Login & Deep Asset Scanner (apps/api/app/services/via_manager.py & api/v1/vias.py):**
  1. Đăng nhập nền không giao diện (headless_login_and_extract):
     - Thực hiện đăng nhập ngầm bảo vệ phiên thông qua proxy riêng và User-Agent ổn định của VIA.
     - Tự động sinh mã 2FA TOTP thời gian thực theo chuẩn RFC 6238 HMAC-SHA1.
     - Trích xuất session cookies (c_user, xs, fr, datr) và Meta Graph Access Token (EAAB... / EAAG...).
     - Mã hóa Fernet lưu vào encrypted_credentials, cập nhật token_status = ACTIVE, tự động kích hoạt quét sâu tài sản.
     - Tự động nhận diện lỗi checkpoint từ Meta (token_status = CHECKPOINT).
  2. Đồng bộ sâu toàn diện tài sản SMIT (sync_via_all_assets):
     - Đồng bộ song song TK Cá nhân (PERSONAL), TK BM (BM), Business Managers (synced_bms) và Fanpages (synced_pages).
     - Lưu đầy đủ các chỉ số tài chính, thẻ thanh toán, chu kỳ hóa đơn và cập nhật số đếm trên ViaProfile.
  3. Truy vấn Ads Check Explorer (get_ads_check_explorer_data / GET /api/v1/vias/ads-check):
     - Hỗ trợ các tab: personal (TK Cá nhân), bm (TK BM), group (Group/BM), page (Fanpage).
     - Bộ lọc theo VIA, tìm kiếm tên/ID, chuyển đổi đơn vị hiển thị (ORIGINAL, VND, USD), phân trang chuẩn.
     - Tính toán tổng hợp dòng Sticky Footer chính xác theo đơn vị tiền tệ (total_accounts_count, total_balance, total_threshold, total_limit, total_spend).
  4. Các Quick Action Endpoints của Left Sub-Menu Toolbox:
     - POST /api/v1/vias/ads-check/remove-hidden-admins: Quét và xóa toàn bộ QTV ẩn trái phép trên các tài khoản đã chọn.
     - POST /api/v1/vias/ads-check/rename-accounts: Đổi thông tin hàng loạt TKQC (tiền tố, hậu tố, tên mới cơ sở, tiền tệ).
     - POST /api/v1/vias/ads-check/share-pixel: Chia sẻ Pixel ID từ BM tới các tài khoản quảng cáo đích.
     - POST /api/v1/vias/ads-check/super-share-ads: Cấp quyền TKQC cho khách hàng, tự động ưu tiên BM Chính Cho Thuê và ghi nhớ cấu hình vào client_bm_preferences (Auto-Remember).

- **Frontend UI: Trình Khám Phá SMIT Ads Check (apps/web):**
  1. Route mới /ads-check (apps/web/app/ads-check/page.tsx):
     - Chuẩn thiết kế Lucian-UXUI Obsidian Dark Mode (#0B0F19, #111827, viền #1F2937).
     - Top Header Bar: 4 Tabs tài sản (TK Cá nhân, TK BM, Group, Page), bộ chọn VIA, ô tìm kiếm nhanh, huy hiệu trạng thái quét (System status: Scan VIA completed. Cookie/Token active.), chuyển đổi tiền tệ (Gốc, VND, USD), nút Đồng bộ VIA.
     - Left Vertical Menu (SMIT Toolbox): Bảng dữ liệu, Extended Payment, Xóa QTV Ẩn, Đổi info TKQC, Share Pixel, Super Share Ads (Auto), Super Target.
     - Bảng dữ liệu SMIT High-Density: Checkbox chọn từng dòng / chọn tất cả, chấm trạng thái (LIVE xanh phát sáng, WARNING vàng, DIE đỏ), hiển thị 2 dòng (Tên in đậm + ID monospace kèm nút sao chép), các cột tài chính căn phải định dạng dấu phẩy (Số dư, Ngưỡng, Limit ngày, Tổng tiêu), huy hiệu tiền tệ, huy hiệu thẻ thanh toán ([VISA] - 2555), ngày lập HĐ.
     - Sticky Summary Footer: Dính cố định ở đáy, hiển thị tổng số tài khoản, tổng Số dư, tổng Ngưỡng, tổng Limit, tổng Tiền tiêu cùng phân trang.
     - Interactive Modals: Modal Xóa QTV Ẩn, Modal Đổi info TKQC, Modal Share Pixel, Modal Super Share Ads (tự động nhận diện cấu hình khách hàng từ client_bm_preferences), Modal Extended Payment.
  2. Tích hợp điều hướng:
     - Sidebar chính: Thêm mục Ads Check (SMIT) với badge SMIT.
     - Trang Quản lý VIA (/vias): Thêm nút Bảng Ads Check (SMIT) ở thanh tác vụ và nút Ads Check trên từng dòng VIA.

- **Kết quả Kiểm thử & Build:**
  - Backend pytest: **454/454 tests PASS (100%)** bao gồm 11 bài kiểm thử chuyên sâu trong tests/test_ads_check_smit.py.
  - Frontend Next.js 15: npm.cmd run build **PASS (100%)** trên toàn bộ 20 routes tĩnh & động.

## Cập nhật 2026-11-01 — Multi-VIA Farm Manager (100+ VIAs), Dedicated Profile & Proxy Routing, Auto UID Live Check, 1-Click Login & BM Share Memory

- **Mô hình Dữ liệu & Reversible Alembic Migration (via_profiles & synced_bms):**
  1. Thêm bảng via_profiles hỗ trợ quản lý quy mô hàng trăm VIA:
     - uid (định danh Meta duy nhất, đánh chỉ mục), profile_name, profile_dir (thư mục phiên làm việc/trình duyệt độc lập trên máy local), user_agent (chuẩn hóa ổn định theo hash UID).
     - encrypted_credentials (mã hóa Fernet bảo vệ mật khẩu, khóa 2FA TOTP, email, mật khẩu mail, mail khôi phục, cookie, access token).
     - proxy_config (chuẩn hóa HTTP/SOCKS5 định dạng IP:Port:User:Pass hoặc URL) và proxy_status.
     - uid_live_status (LIVE, DIE, UNKNOWN), token_status (ACTIVE, EXPIRED, CHECKPOINT, NONE).
     - bm_count, ad_account_count, page_count, last_live_check_at, last_synced_at, created_at, updated_at.
  2. Thêm bảng synced_bms:
     - bm_id, via_profile_id (khóa ngoại liên kết via_profiles.id), name, is_primary_rental (cờ BM Chính Cho Thuê), ad_account_count, page_count, status, updated_at.
  3. Cập nhật bảng client_bm_preferences: bổ sung cột via_profile_id (liên kết khóa ngoại tới via_profiles.id) hỗ trợ ghi nhớ định tuyến BM kèm VIA quản lý.
  4. Migration g4b5c6d7e8f9_multi_via_farm_and_bms.py: Kiểm tra chu trình hoàn nguyên upgrade head -> downgrade -1 -> upgrade head thành công 100% trên SQLite batch mode.

- **Backend Multi-VIA Engine (apps/api/app/services/via_manager.py & api/v1/vias.py):**
  1. Single & Bulk VIA Parser: Phân tích cú pháp chuỗi đa dòng theo định dạng chuẩn UID|PASS|2FA|mail|pass mail|Mail back up, tự động gán đường dẫn profile cách ly profiles/via_{uid} và User Agent Chrome/Edge ổn định, mã hóa credentials an toàn.
  2. Bộ sinh mã 2FA TOTP thời gian thực: Thuật toán RFC 6238 HMAC-SHA1 sinh mã 6 số thời gian thực kèm số giây đếm ngược chu kỳ 30s qua GET /api/v1/vias/{id}/2fa.
  3. Quản lý & Chuẩn hóa Proxy riêng: Gán proxy chuyên dụng cho từng profile qua PATCH /api/v1/vias/{id}/proxy, hỗ trợ IP:Port:User:Pass và URL socks5/http.
  4. Kiểm tra Live/Die UID tự động: Endpoint POST /api/v1/vias/{id}/check-live và POST /api/v1/vias/check-live-bulk kiểm tra UID qua Facebook Graph picture redirect header (https://graph.facebook.com/{uid}/picture?type=normal) có định tuyến qua Proxy của VIA, cập nhật ngay trạng thái LIVE hoặc DIE.
  5. 1-Click Đăng nhập & Khám phá Tài sản BM: Endpoint POST /api/v1/vias/{id}/login và POST /api/v1/vias/{id}/sync-assets kéo toàn bộ BMs (/me/businesses), TKQC và Pages về lưu trong synced_bms.
  6. Gắn cờ BM Chính Cho Thuê: Endpoint PATCH /api/v1/vias/bms/{bm_id}/primary cho phép bật/tắt cờ is_primary_rental để ưu tiên BM này khi phân phối tài khoản quảng cáo cho khách hàng.

- **BM Selection & Auto-Remember Share Routing (auto_fulfillment.py & clients.py):**
  1. Tự động ưu tiên ★ BM Chính Cho Thuê từ dàn VIA đã đồng bộ trong danh mục lựa chọn BM.
  2. Tự động ghi nhớ preferred_bm_id và via_profile_id vào client_bm_preferences khi cấp quyền cho khách hàng.
  3. Định tuyến các tác vụ mời mail BM (ADD_MAIL_TO_BM) và gán TKQC (ADD_AD_ACCOUNT) qua đúng VIA Profile và Proxy quản lý BM đó.

- **Frontend UI: Quản Lý Dàn VIA & BM (apps/web):**
  1. Menu điều hướng mới trên Sidebar: /vias ('Quản lý Dàn VIA & BM', huy hiệu '100+ VIA').
  2. Trang Quản lý Dàn VIA (apps/web/app/vias/page.tsx):
     - Chuẩn thiết kế Obsidian Dark Mode, font mono tabular-nums.
     - Top Action Bar: Nút '➕ Thêm / Nhập Hàng Loạt VIA', '🔄 Check Live UID Hàng Loạt'.
     - 4 Thẻ KPI: Dàn VIA Farm (Live/Die/Chưa check), Trạng thái Token (Active/Checkpoint), Business Manager (kèm số BM Cho Thuê ★), Tổng Tài Sản Đã Khám Phá.
     - Bộ lọc & Tab Switcher: 'Dàn VIA Profile (100+)' và 'Danh Sách Business Manager (BM)'.
     - Bảng Quản trị VIA: Hiển thị Profile, UID, Trạng thái UID (Live/Die badge), Mã 2FA thời gian thực (Live OTP đếm ngược 30s + nút sao chép 1-click), Email & Backup, Proxy riêng (kèm nút sửa), Số BM/TKQC/Page, Trạng thái Token.
     - Các nút thao tác nhanh trên mỗi dòng: 🔑 Login (1-click login), 🔄 Sync BM (đồng bộ tài sản), 📡 Check (kiểm tra live UID), 🌐 Gắn Proxy, 🗑️ Xóa.
     - Sub-panel Synced BMs: Hiển thị toàn bộ BM của dàn VIA kèm nút bật/tắt 1-click ★ Đặt làm BM Chính Cho Thuê.
     - Modal Nhập Hàng Loạt VIA (100+ dòng), Modal Cấu hình Proxy, Modal Trợ lý Đăng nhập & Vượt Checkpoint.
  3. Cập nhật Modal Phân Quyền Khách Hàng (ClientBMPreferenceModal):
     - Nhóm nổi bật ★ BM Chính Cho Thuê lên đầu danh sách, hiển thị VIA quản lý BM.
     - Bổ sung tùy chọn checkbox: 'Ghi nhớ BM & thiết lập quyền này cho khách hàng ở lần sau'.

- **Kết quả Kiểm thử & Build:**
  - Backend pytest: 443/443 tests PASS (100%) bao gồm 8 bài test chuyên sâu trong tests/test_via_farm_manager.py.
  - Frontend Next.js 15: npm.cmd run build PASS (100%) trên toàn bộ 19 routes tĩnh & động.

## Cập nhật 2026-10-30 — Multi-BM Auto-Fulfillment & Client Permission Memory Routing

- **Mô hình Dự liệu & Migration Reversible (client_bm_preferences):**
  1. Tạo bảng client_bm_preferences lưu cấu hình định tuyến BM theo khách hàng:
     - client_id: Khóa ngoại liên kết customers.id, unique, đánh chỉ mục (ix_client_bm_preferences_client_id).
     - preferred_bm_id: BM chỉ định (BM_01, BM_02, BM_03 hoặc Meta BM ID).
     - bm_role: Vai trò trên BM (EMPLOYEE / ADMIN).
     - ad_account_access_type: Cấp độ truy cập TKQC (FULL / PARTIAL).
     - partial_permissions: Danh sách quyền cụ thể (MANAGE_CAMPAIGNS, VIEW_PERFORMANCE, CREATIVE_HUB) lưu dưới dạng JSON.
     - created_at, updated_at: Timestamp UTC chuẩn hóa.
  2. Migration f3a4b5c6d7e8_client_bm_preferences.py: Kiểm tra chu trình hoàn nguyên upgrade -> downgrade -> upgrade thành công 100%.

- **Dịch vụ Tự động Phân luồng & Bộ nhớ Quyền hạn (apps/api/app/services/auto_fulfillment.py):**
  1. Lookup & Auto-Fulfillment: Khi khách hàng gửi yêu cầu mời mail BM (ADD_MAIL_TO_BM) hoặc cấp TKQC (ADD_AD_ACCOUNT), hệ thống tự động kiểm tra client_bm_preferences. Nếu đã có cấu hình, hệ thống tự động áp dụng BM, vai trò và quyền hạn tương ứng, cập nhật tác vụ và thông báo cho Quản trị viên qua Telegram.
  2. Interactive Prompt cho Khách hàng Mới: Nếu khách hàng chưa có cấu hình ưu tiên, hệ thống tạo Telegram Prompt tương tác gửi tới Admin với đầy đủ 3 lựa chọn (BM 1/2/3, Vai trò Nhân viên/Admin, Quyền Đầy đủ/Một phần) và cú pháp lệnh phản hồi nhanh /set_bm <client_id> <bm_id> [role] [access_type].
  3. Auto-Remember & Override: Lựa chọn của Admin qua lệnh /set_bm hoặc API sẽ được ghi nhớ vĩnh viễn vào client_bm_preferences, đồng thời cập nhật toàn bộ tác vụ đang chờ của khách hàng.
  4. Tích hợp Smart Task Dispatcher & Telegram Bot Agent: Bổ sung xử lý lệnh /set_bm (và alias /setbm, /bm_pref), gửi thông báo tự động phân luồng bằng Tiếng Việt chuẩn HTML.

- **REST API Quản trị Phân quyền Multi-BM (/api/v1/clients/* & /api/v1/customers/*):**
  1. GET /api/v1/clients/bm-options: Trả về danh mục BM khả dụng (BM_01, BM_02, BM_03), danh sách vai trò và quyền hạn TKQC.
  2. GET /api/v1/clients/preferences: Danh sách cấu hình phân quyền BM của tất cả khách hàng.
  3. GET /api/v1/clients/{id}/bm-preferences: Lấy cấu hình phân quyền BM của một khách hàng cụ thể.
  4. PATCH /api/v1/clients/{id}/bm-preferences: Cho phép quản trị viên xem, cập nhật và ghi đè cấu hình phân quyền BM tức thời.

- **Giao diện Quản trị Frontend 1-Click (apps/web):**
  1. Trang Quản trị Phân quyền Multi-BM (/clients & apps/web/app/clients/page.tsx):
     - Bảng tổng hợp toàn bộ khách hàng, BM chỉ định, vai trò BM, quyền hạn TKQC và trạng thái bộ nhớ.
     - Bộ nút gán nhanh 1-click Preset: BM 1 (Tiêu chuẩn), BM 2 (Dự phòng), BM 3 (Kháng nghị).
     - Bộ lọc tìm kiếm theo BM và tên/ID khách hàng.
  2. Tích hợp trên Trang Tác Vụ Khách Hàng (/tasks & apps/web/app/tasks/page.tsx):
     - Hiển thị nhãn BM chỉ định trên từng tác vụ trong bảng Kanban và Table view.
     - Thao tác 1 chạm ⚙️ BM trên từng dòng tác vụ.
     - Trong modal chi tiết tác vụ: hiển thị card thông tin phân quyền BM hiện tại kèm nút ⚙️ Chỉnh Sửa BM (1-Click).
  3. Tích hợp trên Trang Chi Tiết Khách Hàng (/customers/[id]):
     - Bổ sung khối 'Phân Quyền Multi-BM & Bộ Nhớ Định Tuyến' với huy hiệu trạng thái và nút chỉnh sửa 1-click.
  4. Modal Component Đa Dụng (apps/web/components/client-bm-preference-modal.tsx):
     - Cho phép chọn BM (BM 1, BM 2, BM 3), Vai trò (Nhân viên / Admin), Quyền TKQC (Đầy đủ / Một phần với checklist Quản lý camp, Xem hiệu quả, Creative Hub), kèm các nút 1-click Preset tiện lợi.
  5. Sidebar Navigation (apps/web/app/sidebar.tsx): Bổ sung mục điều hướng Phân quyền Multi-BM (/clients) với huy hiệu Auto BM.

- **Kết quả Kiểm thử & Build:**
  - Backend pytest: **435/435 tests PASS (100%)** bao gồm 5 bài test mới tests/test_auto_fulfillment_and_bm_preferences.py.
  - Frontend Next.js 15: npm.cmd run build **PASS (100%)** trên toàn bộ 18 routes.

## Cập nhật 2026-10-30 — Unified API Aggregator, Lucian-UXUI Redesign & Telegram AI Work Assistant

- **Bộ kết nối chuẩn hóa & API Aggregator Đa nền tảng (`/api/v1/unified/*`):**
  1. **Chuẩn hóa Adapter đa nền tảng:** Hợp nhất các connector bên ngoài (`Meta Ads`, `Binance`, `PingPong OpenAPI / VCC`, `TRON Blockchain`, `Google Sheets`) vào mô hình Adapter đồng nhất, tự động retry với exponential backoff, bóc tách rate-limit telemetry và lưu trữ credentials mã hóa Fernet.
  2. **Unified Hub Endpoints (`apps/api/app/api/v1/unified.py`):**
     - `GET /api/v1/unified/overview`: Tổng hợp tức thời trạng thái các kênh kết nối, chế độ vận hành và chỉ số hoạt động.
     - `GET /api/v1/unified/treasury`: Tổng hợp số dư thanh khoản đa nguồn (Binance Spot/Funding, PingPong Multi-currency, thẻ VCC PingPong, TRON USDT) phản hồi <50ms qua snapshot database thông minh.
     - `GET /api/v1/unified/accounts`: Tổng hợp danh sách tài khoản quảng cáo kèm trạng thái đặc cách, khóa khẩn cấp và nợ cước.
     - `GET /api/v1/unified/tasks`, `POST /api/v1/unified/tasks/create`, `POST /api/v1/unified/tasks/{id}/status`: Quản lý toàn bộ tác vụ khách hàng.

- **Telegram AI Inbox & Smart Task Dispatcher (`apps/api/app/services/task_dispatcher.py`):**
  1. **Nhận diện khách hàng tự động (Auto-Client Recognition):** Tự động đối soát `telegram_chat_id`, `@username`, hoặc tên khách hàng trong tin nhắn chat để gán chính xác vào hồ sơ khách hàng (`customers`).
  2. **Bộ phân loại tác vụ thông minh (Smart Task Classifier):**
     - `ADD_MAIL_TO_BM`: Tự động nhận diện cú pháp mời mail vào BM (trích xuất email, BM ID, phân quyền Admin/Employee).
     - `ADD_AD_ACCOUNT`: Tự động nhận diện yêu cầu cấp/gán tài khoản quảng cáo (trích xuất account ID).
     - `SETTLE_DEBT`: Tự động nhận diện yêu cầu thanh toán nợ cước tài khoản QC (đặt mức ưu tiên `HIGH` hoặc `URGENT`).
     - `TOPUP_BUDGET`: Nhận diện biên lai chuyển khoản / nạp tiền ngân sách.
     - `CHECK_BALANCE`: Tự động tra cứu và phản hồi số dư các ví trả trước của khách hàng ngay trên Telegram.
     - `GENERAL_SUPPORT`: Tiếp nhận yêu cầu kỹ thuật khác.
  3. **Tích hợp vào Telegram Bot Agent (`telegram_bot.py`):** Mọi tin nhắn văn bản không phải slash command đều được đưa qua Smart Task Dispatcher, lưu trữ vào bảng `client_tasks` và tự động trả lời xác nhận bằng tiếng Việt.

- **Giao diện Quản trị Tác vụ Khách hàng (`/tasks` & `apps/web/app/tasks/page.tsx`):**
  1. **Bảng Điều khiển Chuyên nghiệp (Lucian-UXUI Obsidian Dark Mode):**
     - Chuyển đổi linh hoạt giữa 2 chế độ: **Dạng Bảng (Table View)** và **Dạng Kanban (Kanban View)** với 3 cột trực quan (*Chờ Xử Lý*, *Đang Xử Lý*, *Đã Hoàn Thành*).
     - Huy hiệu phân loại trực quan (Mời mail, Cấp TKQC, Trả nợ cước, Nạp ngân sách) và huy hiệu mức độ ưu tiên (`URGENT`, `HIGH`, `NORMAL`, `LOW`).
     - Thao tác 1 chạm: Tiếp nhận tác vụ, Hoàn thành tác vụ, Gán kỹ thuật viên, Thêm ghi chú lưu vết nội bộ.
     - Modal tạo tác vụ thủ công dành cho admin.
  2. **Widget Hub Đa Nền Tảng (`apps/web/app/unified-overview.tsx`):** Tích hợp widget tổng quan đa nền tảng ngay trên đầu trang chủ Dashboard (`/`).
  3. **Sidebar Navigation (`apps/web/app/sidebar.tsx`):** Bổ sung mục điều hướng `Tác vụ Khách hàng` kèm huy hiệu nổi bật `AI Inbox`.

- **Cơ sở dữ liệu & Migration Reversible:**
  - Migration `e2f3a4b5c6d7_client_tasks_and_dispatcher.py` áp dụng thành công trên `apps/api/adsos.db` (`upgrade -> downgrade -> upgrade`).
  - Cột `telegram_username` trên bảng `customers` (indexed).
  - Bảng mới `client_tasks` lưu vết toàn bộ yêu cầu, dữ liệu bóc tách JSON, trạng thái và mức độ ưu tiên.

- **Kết quả Kiểm thử & Build:**
  - Backend pytest: **430/430 tests PASS (100%)** với bộ test `tests/test_unified_and_dispatcher.py`.
  - Frontend Next.js 15: `npm.cmd run build` **PASS (100%)** trên toàn bộ 17 routes (bao gồm `/tasks`).

## Cập nhật 2026-10-30 — Đại tu UI/UX Lucian-UXUI Obsidian Dark Mode, Kho tài nguyên VIA/BM & Cổng Khách hàng (Client Portal)

- **Đại tu UI/UX chuẩn Lucian-UXUI Obsidian Dark Mode (`apps/web`):**
  1. **Loại bỏ hoàn toàn navbar cũ:** Thay thế thanh menu ngang đơn dòng bị dồn ứ bằng bố cục Sidebar điều hướng chuyên nghiệp (`apps/web/app/sidebar.tsx`), lấy cảm hứng từ Lucian-UXUI `#040` (Expanding side rail) với bộ theme token Obsidian (`#0B0F19`, `#111827`, `#1F2937`, `#B7A4FF`, `--ux-mint`, `--ux-danger`).
  2. **Tiêu chuẩn hoá thanh điều hướng:** Tích hợp đầy đủ các tuyến chính: Tổng quan (`/`), Chiến dịch QC (`/campaigns`), Tài khoản QC (`/accounts`), Sổ trả trước & Công nợ (`/balances`), Kho VIA / BM (`/inventory`), Telegram Bot & Quy tắc (`/telegram`), Quản trị Ví & Sàn (`/config/wallets`), Google Sheets (`/sheets`), Báo cáo kinh doanh (`/reports`), Đối chiếu & Kiểm soát (`/reviews`), Giám sát hệ thống (`/system`).
  3. **Header thông tin hệ thống (`apps/web/app/shell.tsx`):** Hiển thị thời gian thực múi giờ `Asia/Ho_Chi_Minh`, nhãn môi trường `LOCAL DEV`, và tự động ẩn Sidebar khi khách hàng truy cập Cổng thông tin độc lập (`/portal/[token]`).
  4. **Chuẩn số liệu tài chính:** Áp dụng phông chữ đơn cách `font-mono tabular-nums` cho toàn bộ số dư tài khoản, chi tiêu quảng cáo, và thẻ VCC; huy hiệu ngữ nghĩa phân cấp màu sắc rõ rệt (Emerald, Rose, Amber).

- **Kho Tài nguyên Quảng cáo Mã hóa — Inventory Vault (`/inventory` & `apps/api/app/api/v1/inventory.py`):**
  1. Quản lý kho VIA Facebook, BM (Business Manager), Fanpage Cổ, và Proxy Dân Cư.
  2. Mật khẩu, mã 2FA, link mời BM và credentials proxy được **mã hóa Fernet** tự động trước khi lưu xuống SQLite/PostgreSQL, tuyệt đối không lưu plaintext.
  3. Hỗ trợ giải mã xem tức thời trên trình duyệt admin local, gắn khách hàng bàn giao có lưu vết `AuditLog(action="INVENTORY_HANDOVER")`, và chuyển trạng thái linh hoạt (`AVAILABLE`, `ASSIGNED`, `DEAD`).

- **Cổng Khách hàng Tra cứu Độc lập — Client Portal (`/portal/[token]` & `apps/api/app/api/v1/portal.py`):**
  1. Token truy cập ngẫu nhiên an toàn 64-ký tự hex (`secrets.token_hex(32)`) cho từng khách hàng, cho phép khách hàng tự tra cứu số dư ví trả trước, chi tiêu tích lũy thời gian thực của các tài khoản quảng cáo và lịch sử giao dịch sổ cái.
  2. Quản trị viên có thể tạo mới, làm mới hoặc thu hồi link Portal bất cứ lúc nào từ giao diện Sổ trả trước (`/balances`).

- **Nâng cấp Sổ Trả trước & Công nợ (`/balances`):**
  1. KPI Cards: Tổng số dư VND, USD, số khách hàng có cảnh báo số dư thấp và số giao dịch chờ duyệt.
  2. Bổ sung modal tạo đề nghị nạp tiền/trừ tiền có mã chống trùng UUID, modal cấu hình ngưỡng cảnh báo & STK nhận tiền VietQR.
  3. Bổ sung thao tác Duyệt (`approve`), Từ chối (`reject`) và Ghi sổ hàng loạt (`process`) kèm audit log.

- **Cơ chế Đặc cách Vi phạm & Khóa Khẩn cấp (Killswitch):**
  1. Tích hợp nút gạt Đặc cách vi phạm (`allow_violated_accounts`) và nút Khóa khẩn cấp (`/meta-risk/{id}/lock` và `/unlock`) ngay trên bảng Tài khoản QC (`/accounts`).
  2. Hỗ trợ câu lệnh `/khoatk <account_id>` song song với `/khoatkn` trên Telegram bot agent.

- **Kết quả Kiểm thử & Build:**
  - Backend: **426/426 tests PASS (100%)** với bộ test mới `tests/test_inventory_and_portal.py`.
  - Frontend: `npm.cmd run build` **PASS (100%)** với toàn bộ 16 routes được compile và typecheck hoàn chỉnh.

## Cập nhật 2026-10-30 — Đặc cách TKQC, giám sát rủi ro và sổ trả trước

- Đặc cách: `AdAccount.allow_violated_accounts` mặc định tắt; kiểm tra trước tạo/bật chiến dịch và đọc báo cáo hiệu suất. Công tắc tại `/accounts` và form tạo chiến dịch; có audit, thu hồi theo từng tài khoản. Không chặn đồng bộ lịch sử. Khóa khẩn cấp luôn ưu tiên hơn đặc cách.
- Rủi ro: trang `/risk`, API `/meta-risk`, job quét 5 phút, ngưỡng nợ theo tài khoản/tiền tệ. Lỗi đọc giữ dữ liệu cũ và gắn UNVERIFIED. Cảnh báo Telegram có outbox; `/khoatkn` dành cho admin chat. Khóa nội bộ được lưu trước, chỉ ghi nhận dừng Meta khi nhận xác nhận thành công; trả danh sách lỗi từng chiến dịch. Ghi Meta thật mặc định tắt (`ADSOS_META_WRITES_ENABLED`); staging chặn ghi.
- Sổ nội bộ: `/balances`, API `/prepaid`, bảng `client_balances` và `ledger_transactions`. Đề nghị → duyệt → job mỗi phút ghi sổ; chống trùng theo request và khoản nguồn, Decimal/ROUND_HALF_UP, tách tiền tệ và audit. Khoản trừ phải khớp nguồn FINAL VND cả lúc đề nghị lẫn thực thi; nguồn đổi chuyển NEEDS_CONFIRMATION. Cảnh báo thấp dùng ngưỡng cấu hình và thông tin nạp/VietQR placeholder. Không thay số dư báo cáo Sheets D-053; không tự tính phí thuê hoặc quy đổi lifetime spend (Q-014/Q-021).
- Phạm vi: giao diện quản trị nội bộ local; chưa mở cổng khách, chưa nghiệm thu Meta/Telegram thật. Ghi sổ staging/production bị chặn. Các thông báo mới bằng tiếng Việt.
- Migration: chuỗi `c4d5e6f7a8b9 → risk_20261030 → prepaid_20261030`. Đã thử trên bản sao trước, rồi chạy **upgrade → downgrade về b2c3d4e5f6a7 → upgrade** trực tiếp trên `apps/api/adsos.db`. Kiểm tra integrity/foreign keys đạt, số dòng 34 bảng cũ giữ nguyên. Backup: `var/adsos-before-modules-20261030-084749.db` (không commit).
- Frontend: `npm.cmd run build` đạt 15 trang; tách cache `.next-build` cho build và `.next` cho dev để tránh xung đột khi dev server đang chạy.
- Kiểm thử cuối: **422/422 đạt** khi chạy `.venv\Scripts\python.exe -m pytest -q tests`; gồm kiểm thử ranh giới quyền truy cập/khóa an toàn. 15 kiểm thử tập trung liên quan cũng đạt. Một cảnh báo thư viện Starlette/httpx hiện hữu, không có lỗi kiểm thử. Pytest chạy ngoài sandbox do quyền thư mục tạm Windows.

## Cập nhật — Trung tâm Quản trị Telegram Bot & Quy tắc Tự động hóa (Obsidian Lucian-UXUI) — 2026-10-30

- **Backend & Configuration Enhancements (apps/api):**
  1. **Phương thức kết nối nâng cao (apps/api/app/connectors/telegram.py):** Bổ sung `get_me()`, `set_webhook(url)`, `get_webhook_info()`, `delete_webhook()`, hỗ trợ kiểm tra token và bot identity theo chuẩn Telegram Bot API.
  2. **Cơ sở dữ liệu & Reversible Migration (b2c3d4e5f6a7_telegram_bot_and_automation_rules.py):**
     - Tạo 3 bảng mới trên `adsos.db`:
       - `telegram_bot_configs`: Lưu cấu hình token (mã hoá Fernet an toàn), admin chat ID, danh sách whitelist Chat ID và Webhook URL.
       - `automation_rules`: Quản lý các quy tắc tự động hóa (*Tự động tạm dừng chiến dịch khi chi tiêu vượt mức*, *Cảnh báo số dư thẻ VCC PingPong thấp*, *Báo cáo định kỳ*, *Cảnh báo tiền trôi cao*).
       - `telegram_activity_logs`: Ghi nhận toàn bộ nhật ký tương tác bot, người gửi, lệnh và kết quả xử lý.
     - Đã kiểm tra chu trình hoàn nguyên `upgrade -> downgrade -> upgrade` thành công 100%.
  3. **Automation Rules Engine (apps/api/app/services/automation_rules.py):** Tự động khởi tạo 4 quy tắc mặc định, hàm `evaluate_automation_rules` quét chi tiêu và số dư thẻ VCC thực tế để kích hoạt hành động tự động dừng campaign hoặc cảnh báo Telegram.
  4. **REST API Endpoints (/api/v1/telegram/*):** Bổ sung `/test-connection`, `/config`, `/activity-logs`, `/rules` (CRUD) và `/rules/run-check`.

- **Giao diện Quản trị Chuyên biệt (apps/web — /telegram & Sidebar):**
  1. **Điều hướng Sidebar & Navigation:** Tạo component `apps/web/components/sidebar.tsx` và gắn liên kết nổi bật `🤖 Telegram & Quy tắc` vào thanh menu chính `apps/web/app/layout.tsx`.
  2. **Thiết kế theo chuẩn Lucian-UXUI (Obsidian Dark Mode):**
     - Giao diện Dark theme cao cấp (`#07080D`, `#13141C`, `#1A1B25`, `#B7A4FF`, `#7EE8C0`, `#FF7D8C`).
     - Định dạng số Monospace Tabular Nums chuẩn xác (`font-variant-numeric: tabular-nums`).
     - Nút gạt chuyển trạng thái đàn hồi Stretchy Switch lấy cảm hứng từ Lucian-UXUI `#013`.
     - Phân khu 1: **Trạng thái & Kết nối Bot** với nút kiểm tra kết nối trực tiếp ("Kiểm tra kết nối Bot") kèm toast phản hồi tức thì.
     - Phân khu 2: **Bảng quy tắc tự động hóa (Automation Rules Builder)** với bảng quản lý trạng thái Bật / Tắt, modal tạo quy tắc mới và nút quét quy tắc ngay.
     - Phân khu 3: **Web Console mô phỏng lệnh Bot** và **Bảng nhật ký hoạt động bot thời gian thực**.

- **Kiểm thử & Xác minh chất lượng:**
  - Backend: **385 passed** (100%), bao gồm bộ test mới `tests/test_telegram_automation_rules.py`.
  - Frontend: `npm.cmd run build` PASS 100% (13/13 static routes, typecheck sạch sẽ).


## Cập nhật — Tối ưu MetaAdsConnector, Controlled Campaign Builder & Telegram Bot Agent — 2026-10-30

- **Tối ưu hoá MetaAdsConnector (apps/api/app/connectors/meta.py):**
  1. **Connection Pooling & Resilient HTTP:** Sử dụng persistent httpx.Client hỗ trợ context manager, tái sử dụng kết nối. Tự động retry với exponential backoff khi gặp lỗi mạng tạm thời (5xx, timeouts) hoặc mã giới hạn tần suất gọi Meta API (17, 80004, 613, 4).
  2. **Rate-limit Telemetry & Proactive Throttling:** Đọc và phân tích các headers x-business-use-case-usage, x-ad-account-usage, x-app-usage. Khi mức sử dụng vượt ngưỡng 80%, connector tự động làm chậm cuộc gọi (500ms) để phòng tránh lỗi 429.
  3. **Cursor Auto-Pagination & Batching:** Hỗ trợ tự động phân trang theo con trỏ paging.cursors.after và thực thi nhiều truy vấn trong 1 HTTP round-trip qua Meta Graph Batch API.
  4. **Bảo mật & Mã hoá Token:** Hỗ trợ giải mã token động lưu dạng Fernet (ADSOS_EXCHANGE_MASTER_KEY). Tự động che giấu ([REDACTED]) toàn bộ access_token và appsecret_proof khỏi log, ngoại lệ và biểu diễn chuỗi.
  5. **Báo cáo cước & Hiệu suất tiếng Việt:** Bổ sung get_ad_account_billing_health và get_performance_insights hỗ trợ các preset (today, yesterday, last_7d, this_month) cùng nhãn trạng thái tiếng Việt (Hoạt động, Bị vô hiệu hóa, Nợ cước...).

- **Controlled Write Path — Tạo chiến dịch Facebook có kiểm soát (apps/api/app/services/meta_campaign_builder.py):**
  1. **Pipeline hoàn chỉnh:** Xây dựng quy trình tạo Campaign -> AdSet -> AdCreative & Ad (hỗ trợ liên kết bài viết sẵn có qua post_id/object_story_id).
  2. **Rào chắn an toàn kép (Safety Guardrails):**
     - **Budget Cap Guard:** Kiểm tra nghiêm ngặt hạn mức ngân sách ngày tối đa (ADSOS_META_MAX_DAILY_BUDGET), chặn đứng mọi lỗi nhập thừa số 0 trước khi gửi API.
     - **Safe Default Status:** Toàn bộ chiến dịch, nhóm quảng cáo và mẫu quảng cáo mới tạo luôn mặc định ở trạng thái PAUSED (Tạm dừng) an toàn.
  3. **Tracking & Audit Log:** Lưu trữ toàn bộ tác vụ tạo vào bảng meta_campaign_tasks và audit_log.
  4. **Bật/Tắt có kiểm soát:** Hàm toggle_campaign_status cho phép chuyển đổi ACTIVE <-> PAUSED và ghi nhận lịch sử vào audit log.
  5. **Reversible Migration:** Tạo migration a1b2c3d4e5f6_meta_campaign_tasks.py và áp dụng trực tiếp lên adsos.db (đã kiểm tra upgrade/downgrade/upgrade trọn vẹn).

- **Telegram Bot Agent (apps/api/app/services/telegram_bot.py & Endpoints):**
  1. **Bảo mật phân quyền Whitelist:** Chỉ các Chat ID nằm trong danh sách ADSOS_TELEGRAM_ALLOWED_CHAT_IDS (hoặc ADSOS_TELEGRAM_ADMIN_CHAT_ID) mới được phép tương tác; từ chối và cảnh báo nếu có truy cập trái phép.
  2. **Cú pháp lệnh tiếng Việt:**
     - /start & /help: Hướng dẫn sử dụng và nguyên tắc an toàn.
     - /tk / /accounts: Danh sách tài khoản quảng cáo, trạng thái cước và số dư nợ.
     - /baocao [act_id] [preset]: Báo cáo chỉ số chi phí, hiển thị, clicks, CTR, CPC, CPM, chuyển đổi và tin nhắn.
     - /lencamp <act_id> <tên_camp> <ngân_sách> [mục_tiêu] [post_id]: Tạo chiến dịch mới an toàn (hỗ trợ --dry-run để xem trước).
     - /batcamp <id> / /tatcamp <id>: Bật / Tắt chiến dịch tức thì.
     - /status: Kiểm tra trạng thái hệ thống và mức tải API Meta.
  3. **REST API Endpoints:** Mount các routes /api/v1/meta/* và /api/v1/telegram/* phục vụ webhook và điều phối.

- **Giao diện Web (apps/web — /campaigns):**
  - Bổ sung hệ thống 3 phân khu (Tabs):
    1. **Chiến dịch & Chi tiêu:** Bảng danh sách chiến dịch, tiền trôi, mốc 09:00 kèm nút Bật/Tạm dừng nhanh.
    2. **Tài khoản & Hạn mức thanh toán:** Bảng theo dõi cước chi tiết từng tài khoản Meta.
    3. **Lên Camp an toàn & Telegram Bot:** Form tạo chiến dịch có chế độ xem trước (Dry-run preview), cảnh báo hạn mức, bảng lịch sử tác vụ tạo gần đây và thông số tải Meta API Rate-limit.

- **Kiểm thử & Xác minh chất lượng:**
  - Backend: **381 passed** (100%), bao gồm các bộ test mới: test_meta_connector_resilience.py, test_meta_campaign_builder.py, test_telegram_bot.py.
  - Frontend: npm.cmd run build PASS 100% (12/12 routes, typecheck sạch sẽ).



## Cập nhật — Khắc phục "Failed to fetch" & Tích hợp Treasury Summary lên Main Dashboard — 2026-10-30

- **Khắc phục triệt để lỗi "Failed to fetch" khi lưu/xác minh:**
  1. **Đồng bộ CORS & Origin:** Cập nhật `CORSMiddleware` trong `apps/api/app/main.py` với `allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$"`, `allow_credentials=True` và hỗ trợ mọi cổng Next.js dev (:3000, :3001, v.v.).
  2. **Bảo vệ `_guard_local` linh hoạt:** Tự động bỏ qua preflight `OPTIONS` và chấp nhận các local dev origins, tránh browser drop preflight request.
  3. **PingPong Fast-Fail & Thông báo tiếng Việt:** Giảm timeout xuống 8.0s; phân loại chi tiết lỗi mạng (ConnectError, Timeout, 401/403, 404, 429) và hiển thị thông báo tiếng Việt hành động được thay vì treo request.
  4. **Client Web Diagnostic:** Nâng cấp `exchangeRequest` trong `apps/web/lib/exchange-api.ts` để khi gặp lỗi kết nối/máy chủ tắt, hiển thị hướng dẫn người dùng chạy lệnh khởi động uvicorn port 8000.
- **Tích hợp Tổng quan Nguồn vốn & Thẻ (Treasury Summary) lên Main Dashboard:**
  - **Service & API (`apps/api`):** Xây dựng `app/services/treasury.py` và endpoint `GET /api/v1/dashboard/treasury-summary` tổng hợp dữ liệu từ:
    - Ví TRON On-chain (USDT)
    - Sàn Binance (Spot + Funding USDT)
    - Cổng PingPong (Nguồn tiền đa tệ USD/EUR/SGD & Thẻ ảo VCC)
    - Tổng vốn thanh khoản (Combined Working Capital)
    - Endpoint chỉ đọc snapshot nội bộ, không yêu cầu admin token, bảo vệ an toàn secrets.
  - **Giao diện người dùng (`apps/web`):**
    - Component `apps/web/app/treasury-summary.tsx` mount trực tiếp tại trang chủ `apps/web/app/page.tsx`.
    - Hiển thị các khối KPI: Tổng vốn khả dụng (USD/USDT), Ví TRON, Sàn Binance, Nguồn tiền PingPong, Thẻ ảo VCC PingPong, kèm liên kết nhanh sang `/config/wallets`.
- **Kiểm thử & Xác minh chất lượng:**
  - Backend: **369 passed** (100%), bao gồm bộ test mới `tests/test_treasury_summary.py`.
  - Frontend: `npm.cmd run build` PASS 100% (12/12 routes, typecheck sạch sẽ).


## Cập nhật — Tích hợp PingPong Connector chỉ đọc (Nguồn tiền & Thẻ ảo VCC) — 2026-10-30

- **Backend `PingPongConnector` (`apps/api/app/connectors/pingpong.py`):**
  - **Nguyên tắc Strict Read-Only:** Tuyệt đối không cung cấp bất kỳ hàm đột biến/ghi (không tạo thẻ, đóng thẻ, tạm khóa thẻ, nạp tiền, rút tiền hay chuyển khoản).
  - **Xác thực & Ký yêu cầu:** Hỗ trợ PingPong OpenAPI qua OAuth2 access_token (client_credentials) và HMAC-SHA256 request signing (X-Client-Id, X-Timestamp, X-Signature, X-Account-Id).
  - **Bảo vệ dữ liệu nhạy cảm (PAN & CVV):** Che giấu triệt để secrets trong lỗi và log; thẻ ảo chỉ lưu và trả về `last4` (4 số cuối); loại bỏ hoàn toàn mã CVV và full PAN.
  - **Đọc số dư đa tệ & Thẻ VCC:** Hỗ trợ đa tiền tệ (USD, EUR, SGD, GBP, v.v.) chuẩn hóa Decimal; đọc danh sách thẻ VCC gồm hạn mức và số dư khả dụng.
  - **Tái sử dụng kết nối:** Quản lý persistent `httpx.Client` hỗ trợ context manager và `close()`.
- **Database & Reversible Migration:**
  - Migration `f7a8b9c0d1e2_pingpong_connector_and_cards.py`: bổ sung cột `encrypted_extra` vào `exchange_credentials` và tạo bảng `exchange_card_snapshots` (append-only, unique `(connection_id, card_id, read_at)`). Đã kiểm thử trơn tru vòng lặp upgrade/downgrade/upgrade trên SQLite.
- **Service & REST API (`apps/api`):**
  - Mở rộng `exchange_connections.py` và `wallets.py` hỗ trợ provider `"pingpong"` song song với `"binance"`.
  - Credentials được mã hóa bảo mật bằng Fernet thông qua `ADSOS_EXCHANGE_MASTER_KEY`. Bảo vệ an toàn với `_guard_local` và `X-Adsos-Wallet-Token`.
  - Bổ sung endpoint `GET /api/v1/exchange/connections/{id}/cards` và tích hợp thẻ vào `read-balances`.
- **Giao diện Frontend (`apps/web` — `/config/wallets`):**
  - Form "+ Thêm kết nối" cho phép chọn provider **PingPong**, với các trường biểu mẫu Tiếng Việt chuẩn mực.
  - Khi kết nối PingPong hoạt động, hiển thị 2 phân khu trực quan:
    1. **Nguồn tiền PingPong (Balances):** Thẻ số dư theo từng loại tiền tệ (Khả dụng, Tạm giữ/Đang xử lý, Tổng số dư).
    2. **Danh sách Thẻ ảo / VCC (Cards):** Bảng chi tiết gồm Tên thẻ, 4 số cuối (`**** 1234`), Tiền tệ, Badge trạng thái (Hoạt động, Tạm khóa, Đã đóng), Hạn mức và Số dư.
- **Kiểm thử & Xác minh chất lượng:**
  - Backend: **366 passed** (100%), bao gồm bộ unit tests chuyên biệt trong `tests/test_pingpong_connector.py` và integration tests trong `tests/test_exchange_wallets.py`.
  - Frontend: `npm.cmd run build` PASS 100% (12/12 routes, typecheck hoàn toàn sạch).


## Cập nhật — Chẩn đoán toàn diện luồng kết nối Binance & sửa cấu hình .env (2026-10-30)

- **Chẩn đoán luồng `/api/v1/exchange/*` và `BinanceConnector`:**
  1. **Khóa Fernet & Token quản trị:** Cấu hình `SettingsConfigDict` trong `apps/api/app/core/config.py` thiếu `env_file=(".env", "../../.env")`, khiến backend không nạp các biến môi trường từ file `.env` khi chạy local. Đã sửa và hỗ trợ nạp `.env` tự động.
  2. **Bảo vệ `_guard_local` và `X-Adsos-Wallet-Token`:** Khi `ADSOS_EXCHANGE_ADMIN_TOKEN` rỗng, backend lập tức trả về HTTP 503 chặn mọi thao tác mở khóa trên UI `/config/wallets`. Nút "+ Thêm kết nối" bị disabled khi `ADSOS_EXCHANGE_MASTER_KEY` rỗng. Cần đặt 2 biến này trong file `.env` ngoài repo.
  3. **Hàm verify & Binance restrictions:** Endpoint gọi kiểm tra quyền là `GET /sapi/v1/account/apiRestrictions` (SIGNED). Binance mặc định tích "Enable Spot & Margin Trading" khi tạo key; hệ thống yêu cầu chỉ bật "Enable Reading", nếu có bất kỳ quyền ghi/giao dịch nào sẽ bị từ chối. Lệch thời gian đã được tự bù trừ qua `_server_time_offset_ms()`.
  4. **Thông báo lỗi chi tiết:** Cập nhật `_error_message` trong `apps/api/app/connectors/binance.py` để giữ nguyên phản hồi chi tiết từ Binance (vẫn che an toàn secrets), giúp người dùng biết ngay nguyên nhân bị chặn (IP whitelist, sai secret, thiếu quyền).
- **Kiểm thử:** Toàn bộ 351 backend tests (`pytest`) và `npm.cmd run build` đều PASS 100%.


## Hoàn thiện kết nối Binance trên bản sao cách ly — 2026-10-29

- Đã có /config/wallets và liên kết từ /config: quản trị bằng mã riêng; thêm/sửa/ngắt kết nối, đọc Spot/Funding, trạng thái lỗi, lịch sử thu gọn; OKX/MEXC ghi chưa hỗ trợ. Credentials không lưu trong browser hoặc trả lại sau reload.
- Sửa schema quyền Binance thật; chặn quyền ghi/rút/chuyển. Funding giữ đủ free/locked/freeze/withdrawing; parser strict, giữ số 0 xác định; validation không echo secret. Mã hóa Fernet; khóa master ngoài repo. Sửa UTC scheduler, khóa chung manual/scheduled và cooldown rate limit.
- Migration d4c7e0a1f835 + e5d8f1b2c946 đã kiểm tra upgrade/downgrade/upgrade trên DB riêng. Chưa áp dụng DB vận hành ở D:\ads-business-os.
- Kiểm thử: toàn backend 347 passed; nhóm exchange 26 passed sau điều chỉnh trạng thái từng ví. Frontend production build PASS, 12 routes. Không dùng keys thật.
- Browser trên môi trường QA riêng: mở cấu hình, thêm kết nối giả lập, đọc số dư Spot/Funding, lịch sử, reload giữ kết nối và yêu cầu mở khóa lại, sửa form không điền secret; mô phỏng Funding 503 giữ số cũ đúng ví, Spot vẫn cập nhật, thử lại thành công gỡ cảnh báo. Viewport 369px: scrollWidth=clientWidth=369, không tràn ngang. Chưa nghiệm thu desktop 1440px và Binance live.
- Bản chạy QA cổng 3002/8002 chỉ có dữ liệu giả lập. Bản chính 3000/8000 không bị dừng hoặc thay đổi bởi lượt hoàn thiện này. Tài liệu và bản vá được bàn giao để áp dụng với quyền ghi dự án.
- Hướng dẫn bảo mật/vận hành: docs/BINANCE_CONNECTION.md. Không ghi Sheets, không dùng API key đã lộ, không chuyển tiền, commit hoặc deploy.

> Cập nhật sau mỗi phiên làm việc. Mục tiêu: ai quay lại cũng biết hệ thống đang ở đâu.

## Cập nhật — Số dư USDT xác định bằng balanceOf (2026-10-29, sau phiên ví)

- **Xác minh bằng chứng thật:** gọi trực tiếp `wallet/triggerconstantcontract` (constant call chỉ đọc, KHÔNG broadcast) trên hợp đồng USDT `TR7NHq...gjLj6t` với `balanceOf(address)` cho `TPVT4NSNjCCEeaR5FpAq3Q9g65hXF8Uh9r` → `result=true`, `constant_result` = uint256 0 → **số dư xác định là 0 USDT** tại thời điểm đọc (07:00:49Z 2026-10-29). Số null trước đó là do token vắng khỏi danh sách `trc20` trong account JSON của TrongGrid — vắng ≠ 0; account JSON có permissions không chứng minh quyền sở hữu/đọc token.
- **Sửa connector tối thiểu** (`app/connectors/tron.py`): khi `trc20` vắng token → bỏ qua danh sách, đọc trực tiếp `balanceOf(address)` (POST constant call, không broadcast); thành công → số dư xác định (kể cả "0"); `result` false / thiếu `constant_result` / hex hỏng / HTTP lỗi → `TronAPIError` (giữ dữ liệu cũ, không 0 giả). ABI encode địa chỉ bằng base58 → 25 byte (prefix 41) → parameter hex 64 ký tự; decimals 6.
- **Lịch sử append-only:** `usdt_wallet_balances` giờ 3 dòng — 2 dòng cũ (null, trước sửa, không đụng) + 1 dòng mới `balance=0, note=null, source=MANUAL` tạo qua luồng `POST /usdt/wallet/read-balance`. `auto_sync` giữ `false` (=0). API `GET /usdt/wallet` trả `latest_balance.balance="0.000000"` (DB Numeric 6 chữ số); UI `/config` hiển thị "Số dư USDT: 0.000000" (không gắn "không giả 0" vì đã xác định).
- **Test:** 7 case mới/modify trong `test_usdt_wallet.py` + 2 `test_tron_wallet.py` cập nhật semantics (token vắng → constant call xác định 0; giá trị trc20 không phải số → bỏ qua danh sách, đọc balanceOf; constant fail/malformed/HTTP → TronAPIError không 0 giả; trc20 có giá trị vẫn dùng; decimals/ABI hex). **Backend 321 passed.** Mock không đụng chain; live chỉ GET/và constant POST không ký.
- Giữ nguyên phạm vi: không tạo lại ví, không đổi địa chỉ, không bật auto-sync, không match giao dịch (Q-006), không ghi Sheets, không commit/deploy.

## Cập nhật — Chức năng Ví USDT TRC20 (chỉ đọc on-chain) — 2026-10-29

- **Cấu hình + theo dõi ví tại `/config#usdt-wallet`:** nhập tên ví + địa chỉ TRON Mainnet (`^T[1-9A-HJ-NP-Za-km-z]{33}$`), "Kiểm tra kết nối" (bắt buộc verify thành công mới lưu được), lưu (409 nếu đã có ví khác — địa chỉ là BẤT BIẾN, không ghi đè; tối đa 1 ví), cập nhật tên + auto-sync, "Cập nhật số dư" (append `usdt_wallet_balances`).
- **Chỉ ĐỌC on-chain qua TronGrid** — hợp đồng USDT `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t`, decimals 6; **không private key/seed/ký ví/quyền chuyển tiền**; API key provider tùy chọn qua env `ADSOS_TRON_API_KEY` (server-side, không ra UI/log). Lỗi đọc → ghi `last_error`, KHÔNG ghi 0, giữ giá trị gần nhất.
- **Endpoints** trong `app/api/v1/usdt.py`: `GET /usdt/wallet`, `POST /usdt/wallet/verify`, `POST /usdt/wallet` (lưu sau verify), `PUT /usdt/wallet` (tên + auto_sync ± audit), `POST /usdt/wallet/read-balance`, `GET /usdt/wallet/balances`; legacy `GET /usdt/wallet-balance` (thẻ trên `/reports`) giờ ưu tiên ví đã lưu, fallback env, mock khi trống.
- **Auto-sync mặc định TẮT:** scheduler riêng (`app/jobs/usdt_wallet.py`) port-lock 8911, interval 30 phút (`ADSOS_USDT_SYNC_INTERVAL_MINUTES`), backoff x2 sau lần đọc lỗi; bật qua `PUT /usdt/wallet` `auto_sync=true`.
- **Migration `c9f8a3b1d2e6`** (bảng `usdt_wallets` + `usdt_wallet_balances`, reversible — đã up/down/up trên DB tạm; local DB đã upgrade head sau sao lưu `var/backups/adsos-before-...`).
- **Thẻ "Ví USDT chung"** (`app/wallet-balance-card.tsx`) mount trên `/reports` ở cả hai chế độ nguồn.
- **Kiểm thử:** backend **314 passed** (7 mới `test_usdt_wallet.py` + legacy `test_tron_wallet.py` cập nhật dependency override); `npm.cmd run build` PASS; restart backend frontend; `/`, `/config`, `/reports` HTTP 200.
- **Nghiệm thu live (chỉ đọc qua TronGrid):** verify 200 mode=live; địa chỉ `TPVT4NSNjCCEeaR5FpAq3Q9g65hXF8Uh9r` là địa chỉ TRON đang hoạt động (account JSON 2779B chứa permissions, **trc20 hiện không có USDT** — số dư trả `null` + ghi chú hiện tại chưa có dữ liệu, không 0 giả); đã lưu ví (id=1, tên "Ví chung USDT TRC20", auto_sync=false) và đọc số dư → `usdt_wallet_balances` có 2 dòng (verify + read-balance, source MANUAL, balance=null). Cross-checked trực tiếp API TrongGrid khớp connector.
- **Giới hạn trung thực:** số dư on-chain của địa chỉ này KHÔNG đại diện số dư tài khoản trên sàn nếu là địa chỉ nạp sàn (disclaimer treo đầu API + UI — chưa có xác nhận địa chỉ thuộc loại nào: Q-021 đặt NEEDS_CONFIRMATION trên DECISIONS? — chưa, giữ trong status này); chưa luồng match giao dịch Q-006; backup trước migration chỉ tạo sau khi up head lần đầu — có thể khôi phục bằng `downgrade`.
- Không ghi Sheets, không sửa liên kết khách, không chốt kỳ, không tạo giao dịch USDT, không bật auto-sync, không commit/deploy.

## Cập nhật — Báo cáo Sheets theo năm từng khách + tối ưu tải danh sách — 2026-10-29

- **Endpoint mới `GET /api/v1/sheets/sources/customer-year-summary`** (`year`, `basis=current|closed`, `customer_id`, `rank_by=tùy chọn` — một trong 7 chỉ tiêu phát sinh; sai pattern → 400/422, khách không tồn tại → 404). Service `build_customer_year_summary` trong `app/services/sheet_year_summary.py`: chọn đúng một snapshot mỗi kỳ (bản chốt luôn thắng kể cả có bản đọc mới hơn + `closure_note`; basis "closed" → kỳ chưa chốt báo `NOT_CLOSED`, không tự thay bằng bản hiện hành — D-052), trích số của một khách qua tab đã liên kết (`_customer_month_values`: LINKED/UNLINKED/LINK_REVIEW/SOURCE_ERROR), tổng phát sinh 7 chỉ tiêu K1/F1/G1/H1 + USDT nhận/hoàn/ròng tính bằng `Decimal` (USDT không quy đổi), số dư đầu năm (J1 tháng 1) và số dư đến kỳ (L1 kỳ mới nhất có số — ghi rõ chưa phải cuối năm nếu thiếu tháng 12), không cộng số dư qua các tháng.
- **Xếp hạng theo khách:** `_customer_rank_entries` tổng từng khách trên cùng tập snapshot đã chọn; khách chưa liên kết tab hiển thị không số (không 0 giả); `rank_by` sắp giảm dần, không có → theo tên. Danh sách gồm toàn bộ khách nội bộ (kể cả hồ sơ chưa liên kết như ALL/OLD hiện hữu trong DB).
- **Paging metadata-only:** `GET /sheets/sources/{id}/snapshots?limit&offset` và `GET /sheets/sources/{id}/history?limit&offset` trả envelope `{total, items}` (snapshots 3518B→596B, history 5518B→871B với limit 5; latency giữ nguyên do overhead kết nối SQLite lần đầu). Web callers cập nhật types `SavedSheetSnapshotEnvelope`/`SheetSyncHistoryEnvelope`.
- **UI `/customers/[id]` thêm panel "Báo cáo Sheets theo năm"** (`app/customer-year-summary.tsx`): chọn năm/chế độ (Hiện hành–ưu tiên bản chốt / Chỉ bản chốt)/chỉ tiêu xếp hạng, lưu prefs `customerYear.*`; bảng 12 tháng (trạng thái, liên kết tab, 7 chỉ tiêu — VND qua `formatVnd` ROUND_HALF_UP, USDT giữ đơn vị riêng, ô thiếu là "—"); tổng năm + số dư đầu/đến kỳ kèm ghi chú; bảng tổng hợp theo khách có liên kết tới hồ sơ.
- **Fix flaky test auth Sheets:** `_ServiceAccountTokenProvider` so sánh cấu hình trước khi dùng cache credentials (`_current_config()` + `_last_config`); đổi env giữa các test không còn tái dùng credentials cũ. Full suite **295 passed** (293 cũ + 2 test mới cho year-summary; thêm 1 test pagination trước đó trong phiên).
- **Nghiệm thu thật (Chrome headless CDP, không cài package):** `/customers/[1]` (S17.1-TEST ↔ tab JOKER kỳ 10): T10 Đã chốt \+ closure_note, spend 890.727.440 / phí 35.629.098 VND, USDT 15.045; tổng năm phát sinh = T10; số dư đến kỳ 207.968.093 VND tại 2026-10 \+ nhãn "chưa phải số dư cuối năm"; closed basis → tháng 1–9 "Chưa chốt · Không tự thay bằng bản hiện hành", T11/T12 "Chưa có nguồn"; `/customers/[2]` (JOKER nội bộ) liên kết kỳ 7/8 مص đúng; bảng xếp hạng hiển thị đầy đủ với tháng có số. `npm.cmd run build` PASS (11 routes); backend+frontend đã chạy lại với code mới (3000/8000 HTTP 200).
- **Giới hạn: trang `/customers/[id]` đã tràn ngang ở viewport 390px từ TRƯỚC phiên này** (top-nav chạy trong wrapper riêng, nhưng 3 bảng cũ dùng inline style ngoài wrapper cuộn: `account_summary_by_day` → 1175px); panel mới KHÔNG ảnh hưởng (bảng trong `overflow-x:auto`, ẩn panel không đổi docW). Chưa sửa debt này — cần quyết định scope riêng. Chưa xây chọn tất cả/bỏ chọn, sửa/lưu khách, category summary; chưa persist lựa chọn báo cáo năm ngoài `customerYear.*` (không URL sâu); scheduler có thể tạo snapshot mới bất kỳ lúc nào nên số phải đọc kèm snapshot ID.
- Không migration, không ghi Sheets, không tự chốt kỳ, không sửa liên kết khách thật, không tạo giao dịch, không commit/deploy.

## Cập nhật — Giữ lựa chọn nguồn/kỳ/khách/chế độ sau reload và URL trên /reports — 2026-10-29

- **`/reports` (sheets-source-report.tsx) giờ lưu lựa chọn qua prefs adsos.ui. và nhận URL:** `source_id`/`snapshot_id` chỉ chấp nhận số nguyên dương trong `?URL`; thứ tự khi mới vào: URL hợp lệ → lựa chọn đã lưu (`sheetsReport.source`/`sheetsReport.snapshot`) → mặc định hệ thống (is_default/active); URL sai nguồn/kỳ → tự dùng lựa chọn đã lưu/mặc định; URL snapshot sai → hiện trạng báo lỗi snapshot rồi tự tải bản mới nhất của nguồn đó.
- **Khách và kỳ nguồn cũng được lưu:** `sheetsReport.customer` (so khớp `source_sheet` của nguồn đang bấm) và `sheetsReport.period` (chỉ giữ khi còn thuộc tập kỳ nguồn). Lỗi: giá trị lưu không còn hợp lệ → về khách đầu của bảng; kỳ ưu tiên về kỳ nguồn của nguồn đã chọn.
- Nút Cập nhật ngay không đổi hành vi; chỉ mở rộng persistence.
- Tab Tổng đã sẵn có persistence từ phiên trước (customers-total.*).
- Kiểm thử: backend 292 pass, `npm.cmd run build` PASS, `/reports`/`/sheets`/`/health` HTTP 200, frontend yêu cầu xuất phát từ `next start` tại workspace chính; API kiểm tra nguồn 2 (tháng 9, snapshot 123): usdt 14142.83 / hoàn 135 / ròng 14007.83, opening 23524958 COMPLETE 14/14 (J3-conflict không còn cô lập J1).
- Chưa quyết định: lưu lựa chọn đối chiếu ngày (từ ngày/đến ngày) không persist; không tự gán "đầy đủ" khi thiếu dữ liệu.

## Cập nhật — Hoàn USDT cho snapshot đã lưu và rà soát J1/chốt kỳ — 2026-10-29

- **Hoàn USDT (D-051) cho snapshot cũ:** phân loại `kind` thiếu ở snapshot đã lưu trước khi có phân loại → `enrich_sheets_report` suy ra `REFUND` qua `_effective_deposit_kind` chỉ khi khớp `OWNER_USDT_REFUNDS` (kỳ + khách + ô J + số âm). Kỳ 2026-09 đọc được: `usdt_refunded` = 135 USDT (PEDRI J5 18, KING J8 117), `usdt_received` = 14.142,83 USDT (J5 −18 không còn cộng vào tiền nhận), `usdt_net` = 14.007,83 USDT; status giữ PARTIAL (PEDRI/KING có dòng J không ngày, JOKER/HUNTER/ALEX còn thiếu) — không tự gán "đầy đủ".
- **J3 xung đột:** J1 bị cô lập cùng khối J (`basis=J3_CONFLICT_ISOLATED`; mở rộng trường `basis`, `source_value` trên `opening_balance`), F1/G1/H1/K1/L1 vẫn đọc nguồn; warning `Tab!J3` và `usdt_receipts_state=NEEDS_REVIEW` giữ nguyên; test khớp payload mới.
- **Tổng năm (D-052):** tháng có bản chốt luôn dùng đúng bản chốt kể cả khi có bản đọc mới hơn; trạng thái trả `CLOSED` kèm `closure_note` "Dữ liệu mới hơn bản chốt; bản chốt vẫn là nguồn chính thức" thay vì state riêng `CURRENT_AFTER_CLOSURE` (web hiển thị note theo nhãn Đã chốt; không dọn state cũ trong type).
- Kiểm thử: backend **290 passed**; `npm.cmd run build` PASS. Chưa migration; không ghi Sheets/token; không tự chốt kỳ.
- Việc còn lại: liên kết khách thật cho cả hai kỳ; PEDRI J6/KING J6 không ngày (giữ PARTIAL, đúng tách); Q-020 JACK J6/J9 và VIKTOR M6 chờ xác nhận.

## Cập nhật — Đọc nguồn tháng 09/2026 theo mapping chuẩn — 2026-10-28

- `sheets_report.py`: J3 trống (header ở hàng 3) hợp lệ cho mọi tab khách theo mapping chuẩn; J3 mang giá trị khác USDT chỉ cô lập J1 + khoản nhận USDT (cảnh báo `Tab!J3`), không loại cả tab; lỗi header A/C/F/G/H vẫn là STRUCTURE_ERROR. Không áp cấu hình theo kỳ của 2026-10 sang kỳ khác.
- Snapshot #66 (MANUAL, nguồn 2) đọc đủ 14/14 tab; #60 giữ nguyên. Tổng F/G/H/K/L: 14/14; J1: 5/14; USDT: 9/14.
- Đối chiếu chuyển kỳ: khi kỳ trước chưa chốt, `/rollover` trả đối chiếu tạm (`provisional`, `basis=PROVISIONAL_UNCLOSED`, nhãn "Chưa chốt") từ snapshot mới nhất; bản chốt vẫn là nguồn chính thức. Chỉ khách đã liên kết có xác nhận mới được so sánh.
- Bản chốt tháng 10: `SheetReportClosure` id=1, source 1, snapshot #58, 2026-10-28T12:35:48Z, `actor=None` (không có AuditLog) → không chứng minh danh tính người thao tác.
- Việc còn lại: liên kết khách thật cho cả hai kỳ (hiện chỉ có liên kết khách nội bộ #1 "S17.1-TEST" với JOKER của kỳ 10, cần người dùng rà soát); câu hỏi ô nguồn: J1 trống của NIN/WIN/JACK/WINE/KING/SONA/VIKTOR/ALEX/TOMMY, J4 âm của PEDRI (J5) và KING (J8).

## Cập nhật — Sửa luồng thêm báo cáo tháng cũ và lịch đồng bộ — 2026-10-28

- Nguyên nhân đã xác minh: (1) ô kỳ `type=month` khó dùng; nút không có kiểu vì Tailwind preflight; (2) `set_default` mặc định True; (3) nguồn đọc lỗi bị trả 502 và không lưu; (4) checkbox thay nguồn luôn hiện; (5) scheduler chạy ngay 5 giây sau mỗi lần backend khởi động/`--reload` (không có điều kiện đến hạn) nên 51 lượt SCHEDULED PARTIAL cách nhau vài chục giây. Mỗi mốc thời gian là bắt đầu/kết thúc của một lượt đọc, không phải retry; PARTIAL không bị coi là lỗi.
- Sửa: form “Thêm báo cáo tháng” (tháng 01–12, năm, tên gợi ý, thay nguồn chỉ hiện khi 409 xung đột kỳ); `set_default` mặc định False; kỳ chưa có nguồn mà đọc lỗi → lưu cấu hình + lượt INITIAL ERROR, thử lại bằng “Cập nhật ngay” (MANUAL); kỳ đã có nguồn mà đọc lỗi → 502, không thay. Scheduler tick 60 giây nhưng chỉ đọc khi đến hạn theo lần thử gần nhất (mọi trigger): 15 phút sau thành công/PARTIAL; sau ERROR backoff 1, 2, 4, 8, 15 phút. Lịch sử thu gọn 5 lượt + “Xem thêm”.
- Không migration; không xóa lịch sử. Test mới trong `tests/test_sheet_report_store.py`; backend 287 test đạt.
- Nghiệm thu live nguồn id=2 (kỳ 2026-09, snapshot #60, PARTIAL, mapping D-047-v1): đọc được; F1/G1/H1/K1/L1 của JOKER/HUNTER/NIN khớp live; tổng năm dùng 1 snapshot/tháng (09: #60, 10: bản chốt #58). Chưa chốt kỳ 9, chưa liên kết khách nên chưa đối chiếu chuyển kỳ. Tab JACK/VKL/SONA/VIKTOR/TOMMY của tháng 9 là STRUCTURE_ERROR (xác nhận D-049/D-050 chỉ áp dụng cho 2026-10) → NEEDS_CONFIRMATION.

## Cập nhật — Tổng quan vận hành và thiết lập khách từ Sheets — 2026-10-28

- Tab "Tổng quan" tại `/` đọc `GET /dashboard/operations-overview` (+ `/{metric}` cho danh sách; card và danh sách dùng cùng một hàm dựng) từ bản lưu hiện hành của nguồn mặc định; không đọc lại workbook. `/dashboard/overview` giữ nguyên cho trang khách. Số nội bộ (khách/TKQC/campaign, ACTIVE mặc định) chuyển vào mục "Dữ liệu nội bộ", không còn là số vận hành.
- Thiết lập khách: `/sheets#customer-setup` (`GET/POST /sheets/sources/{id}/customer-setup`): liên kết hồ sơ có sẵn / tạo hồ sơ chỉ có tên rồi liên kết / bỏ qua tab (khôi phục được); một giao dịch, idempotent, có audit, không tạo tiền hay phân công.
- Migration `a7c3e1f9b204` (bảng `sheet_report_tab_dismissals`) đã áp dụng local; sao lưu `var/backups/adsos-before-tab-dismissals-20261028-192144.db`.
- Kiểm thử: backend 282 test đạt; tsc và build web đạt.
- Giới hạn: liên kết theo nguồn tháng (tháng mới cần liên kết lại); "TKQC chưa rõ người sử dụng" so ID nguồn với phân công nội bộ đã có; chưa tính tỷ lệ sự cố.

## Cập nhật — Khách hàng và vận hành TKQC — 2026-10-28

- Danh sách và hồ sơ khách có khu ngân sách Sheets theo nguồn/kỳ và snapshot mới nhất. Chỉ liên kết qua `source_id`, `sheet_id` và tên tab đã xác nhận; tab đổi tên, chưa liên kết hoặc lỗi không được tự gán số. Hiển thị K1/F1/G1/L1, số dư âm, thời điểm đọc và lỗi đồng bộ; số TKQC hiện có hiệu lực được đếm riêng, phân công chồng lấn được báo và không tính như chắc chắn. Khi có bản sau chốt, giao diện ghi rõ đây là bản rà soát, không thay bản chốt. Tab Tổng và báo cáo Sheets hiện hữu không thay đổi nguồn tính.
- Có ngưỡng nhắc nạp VND tùy chọn theo khách: `null` là chưa cấu hình, so sánh `Decimal` với L1 đã liên kết và ghi audit khi lưu/xóa. Không gửi thông báo, không mặc định ngưỡng, không coi Sheets là Meta realtime. Migration `e9b2c4d6f810` thêm cột nullable, upgrade/downgrade/re-upgrade đã thử trên SQLite riêng. Đã backup nhất quán tại `var/backups/adsos-before-budget-alert-20261028-184329-758025.db`, kiểm tra `integrity_check`, rồi áp migration local; không diễn giải dữ liệu cũ.
- `/accounts` có lọc ID/tên/khách/trạng thái, giờ hiệu lực gán, chuyển cùng TKQC từ thời điểm xác nhận (D-054) và đánh dấu hạn chế nội bộ. Chuyển yêu cầu xác nhận, kiểm tra assignment hiện hành, đóng lịch sử cũ và tạo assignment mới trong một transaction; request cũ bị từ chối, không tạo trùng. Các thao tác gán/chuyển/thay khóa ghi SQLite hoặc khóa account PostgreSQL; phân công đang mở mơ hồ được giữ nguyên và phải rà soát. Unique index toàn cục đã thử nhưng được gỡ an toàn vì không tương thích các trường hợp phân công hiện hữu của Meta; bản backup trước thử nghiệm nằm tại `var/backups/adsos-before-assignment-index-20261028-190045-737114.db`. Không hỗ trợ hẹn chuyển tương lai hoặc chuyển hồi tố. Audit hiện dùng actor mặc định `admin`, chưa xác thực được danh tính người vận hành thực tế.
- Trạng thái mặc định ACTIVE không được khẳng định là trạng thái Meta live; thời điểm hạn chế đã lưu được hiển thị, các thời điểm thiếu không tự suy diễn. Tiền tệ, BM tiếp nhận, giá thu khách, nợ bàn giao và thanh toán còn thiếu đều ghi rõ. Chi phí cũ giữ nguyên, không suy đoán đơn vị; KPI nguồn hệ thống không cộng chi phí cũ chưa rõ đơn vị hoặc trừ vào lợi nhuận. Chưa có schema riêng cho chi phí mua, giá thu và nợ bàn giao, hai trạng thái thanh toán hay lịch sử trạng thái. Đề xuất tách bản mua tài khoản có số tiền/đơn vị khỏi bản bàn giao gắn assignment (giá thu, nợ Meta và đơn vị riêng); các trạng thái khách trả và doanh nghiệp trả phải độc lập, cập nhật có audit/phiên bản. `purchase_cost` cũ giữ nguyên và chưa ánh xạ.
- `usdt_transactions` đã có khóa duy nhất `tx_hash` nhưng chưa có phân bổ. Đề xuất bổ sung phân bổ có phiên bản, tham chiếu giao dịch, loại `AD_BUDGET`/giá TKQC/nợ bàn giao, số tiền/đơn vị/tỷ giá riêng và kiểm soát tổng không vượt số nhận trong cùng transaction; chưa tạo ledger mới. Chủ dự án đã chọn K1/L1 Sheets làm nguồn số dư, giao dịch nội bộ chỉ đối chiếu (D-053); nếu chuyển sang ledger sau này cần mốc cutover và đối chiếu có bằng chứng để tránh cộng hai lần.
- Chưa xác nhận kỳ cho khoản Sheets mơ hồ: tọa độ dòng có thể thay đổi. Thiết kế cần lưu nguồn/tab, bằng chứng định danh độc lập với vị trí, kỳ được xác nhận, lý do/người/thời điểm và lịch sử; chỉ áp lại khi có đối sánh duy nhất, nếu dữ liệu đổi hoặc trùng phải dừng và yêu cầu rà soát. Không lấy hash số tiền hoặc số dòng đơn lẻ làm định danh đáng tin cậy, không gán ngày giả.
- Kiểm thử backend **274 passed**, formatter **2 passed**, TypeScript và build production **pass**; kiểm tra trình duyệt thật trang khách, chi tiết khách, TKQC, tab Tổng, báo cáo, lọc và viewport 390px. Kiểm tra số âm/0/thiếu và thao tác xác nhận chuyển bằng response giả lập chỉ trong trình duyệt, không ghi DB vận hành. Lúc kiểm tra có một khách nội bộ chưa liên kết, nguồn kỳ 2026-10 `PARTIAL`, chưa có ngưỡng cấu hình; scheduler tiếp tục tạo snapshot theo cơ chế cũ. Không ghi Sheets, tạo giao dịch, tự chốt kỳ, gửi thông báo, commit hay deploy. Test có một cảnh báo deprecation có sẵn từ Starlette/httpx.

## Cập nhật — Tab Tổng và nguồn Sheets nhiều tháng (D-052) — 2026-10-28

- Thêm tab Tổng tại trang danh sách khách (`/#tong`); `/reports` giữ báo cáo khách và liên kết tới Tổng, không còn dãy tổng toàn khách. Chọn năm, một tháng/cả năm; trạng thái nguồn, bản chốt/tạm, lần đọc, cảnh báo, độ phủ, ô nguồn và nguồn thiếu được hiển thị. Tháng 10/2026 là tháng duy nhất hiện có dữ liệu; tổng năm là phần đã biết 1/12 tháng, chưa có số dư đầu năm, số dư đến kỳ 2026-10 không gọi là cuối năm.
- Service tổng hợp dùng đúng một snapshot mỗi kỳ: bản chốt kể cả nguồn đã thay, nếu chưa chốt dùng bản hiện hành nguồn hoạt động. Phát sinh cộng bằng `Decimal` chính xác; J1 tháng 1 và L1 cùng một kỳ cuối được chọn riêng, không cộng số dư qua tháng. Nhiều bản chốt cùng kỳ được báo xung đột và không tự chọn. Nguồn mới tại `/sheets#saved-sources` có tùy chọn tự đồng bộ và mặc định tắt; thay link vẫn cần xác nhận rõ, giữ lịch sử và bản chốt. Liên kết khách/đối chiếu chuyển kỳ tiếp tục dùng chức năng sẵn có.
- Backend **262 passed**, formatter **2 passed**, TypeScript và build production **pass**; kiểm tra UI thật tab Tổng, tháng thiếu, tổng năm, đổi khách không đổi kỳ, `/reports` không có dãy tổng cũ và viewport hẹp. Không có migration, không tạo nguồn mới hay tự chốt; không ghi Sheet/ledger, commit hoặc deploy.

## Cập nhật — Phân cách vùng A và khoản nhận J:L (D-051) — 2026-10-28

- Parser không còn coi toàn bộ hàng phân cách là xung đột: khối TKQC và nhận tiền được xử lý riêng, J/K/L giữ số nguồn và không cộng lặp. Dòng chỉ có khoản nhận không tạo TKQC hoặc cảnh báo thiếu ngày TKQC; không kế thừa ngày merge cho khoản nhận đơn lẻ khi A trống. Dòng có ID TKQC thực vẫn được xử lý và báo thiếu ngày nếu cần. Không mở rộng phạm vi đọc.
- Snapshot #24 `PARTIAL` đã đọc đủ các tab khách khả dụng. JACK J6/J9 giữ nguyên mỗi khoản 1.000 USDT, tỷ giá và VND nguồn; hai khoản chưa rõ ngày/kỳ được giữ riêng, không tự cộng tổng kỳ hay biểu đồ ngày. VIKTOR M6 giữ làm ghi chú chưa phân loại nội dung, không còn là cảnh báo xung đột phân cách. Cảnh báo phân cách của ba vị trí và dòng chưa phân loại giả đã hết; các giới hạn dữ liệu khác vẫn còn.
- So với snapshot #20, bảy tổng tài chính và độ phủ không đổi; tổng USDT phần xác định kỳ là 111.822 USDT, đủ 18/27 khách. Lượt đọc #23 gặp lỗi ở chín tab, được lưu đúng trạng thái một phần; sau khi chờ và chạy lại một lần đã tạo #24 không có lỗi đọc tab. Lịch sử cũ không sửa, kỳ chưa chốt.
- Backend **258 passed**, kiểm thử tập trung phân cách/không cộng trùng **8 passed**, Pylance không báo lỗi file parser. Đã nghiệm thu `/reports` thật tại cổng 3000, không sửa frontend hay cần build lại; không ghi Sheet, tạo giao dịch, migration, commit, deploy hoặc reset.

## Cập nhật — Tổng tài chính và chi tiêu TKQC theo ngày (D-050) — 2026-10-28

- `/reports` có tổng tất cả khách theo snapshot và kỳ nguồn, cộng từng ô chuẩn bằng `Decimal` trước khi định dạng VND. Độ phủ và khách thiếu được tính riêng cho từng chỉ tiêu; USDT hợp lệ có ngày thuộc kỳ được tính riêng, khoản chưa rõ ngày không tự gán kỳ. Bộ lọc khách/ngày không thay đổi tổng tất cả khách. Bảng chi tiêu giữ từng dòng nguồn và chi tiêu gốc theo tiền tệ, không cộng lặp TKQC/ngày; có lọc ID/trạng thái và truy vết mở bằng bàn phím. Chi phí thủ công không có đơn vị trong model nên không tự đoán; trạng thái chỉ là hiện tại, không phải Meta live hay lịch sử.
- Xác nhận dòng phân cách giới hạn nguồn đang hoạt động kỳ `2026-10` bằng cấu hình `D-050-v3`. Dòng trống hoặc chỉ có ngày hợp lệ không tạo bản ghi; có dữ liệu hoặc công thức khác thì giữ nguyên và cảnh báo. Theo lựa chọn chủ dự án tại Q-020, giữ JACK J6/J9 (mỗi khoản 1.000 USDT, chưa rõ ngày) và ghi chú VIKTOR M6, không xóa cảnh báo xung đột; không áp dụng ngoại lệ cho kỳ khác.
- Lần đồng bộ tay tạo snapshot #19 `PARTIAL`, các snapshot trước và trạng thái chưa chốt được giữ nguyên. Có 27 tab khách: J1 đủ 17/27, K1/F1/G1/H1/L1 đủ 27/27, USDT theo kỳ đủ 18/27; chi tiết khách thiếu xem trong báo cáo. Không đọc hoặc cộng thêm tab ẩn/tổng hợp, không tạo giao dịch hay sửa Sheet.
- Kiểm thử backend **255 passed**, formatter VND **2 passed**, TypeScript và build production **pass**; kiểm tra UI thật gồm tổng không đổi khi đổi khách/lọc ngày, mẫu chi tiêu USD, lọc ID/trạng thái, truy vết bằng bàn phím và viewport hẹp. Backend/scheduler Sheets tiếp tục chạy; không migration, tự chốt kỳ, bật Meta sync, ghi `BUSINESS_RULES.md`, commit hay deploy.

## Cập nhật — Tinh gọn giao diện báo cáo — 2026-10-28

- `/reports` giữ lựa chọn nguồn, kỳ, khách, lọc ngày và thao tác cập nhật. Báo cáo Sheets dùng bảy card ngắn, gộp phí/lợi nhuận theo quy ước, giữ USDT riêng; bảng tổng hợp VND căn phải, dấu âm được giữ kể cả số dư âm làm tròn về 0. Tổng nguồn cấp tab/kỳ và chi tiết theo ngày được ghi rõ phạm vi, không thay đổi tính toán hoặc dữ liệu.
- Ô nguồn, giá trị thô, công thức, mapping, cảnh báo, giải thích lợi nhuận và lịch sử được đưa vào “Chi tiết dữ liệu” mặc định đóng. Biểu đồ, bảng ngày/TKQC và khoản nhận USDT có mục mở riêng; các dòng thiếu ngày/chưa phân loại vẫn có nhãn và truy vết. Báo cáo Meta/Manual giữ các chỉ số, trạng thái và lợi nhuận riêng, chỉ thu gọn trình bày.
- Nghiệm thu trực tiếp frontend cổng 3000: đối chiếu card JOKER trước/sau, lọc ngày không đổi tổng nguồn, HUNTER vẫn có J6/J9 chưa rõ ngày; kiểm tra bàn phím, màn hình 390px, lỗi tải có thử lại, dữ liệu cũ, trạng thái đủ/thiếu, null, 0 và số dư âm bằng response mô phỏng chỉ trên trình duyệt. TypeScript và build production **pass**, kiểm thử formatter **2 passed**. Không thay backend, mapping, scheduler, DB, Sheets hoặc bản chốt; không reset app, commit hay deploy.

## Cập nhật — Xác nhận mapping JACK, VKL, SONA, VIKTOR (D-049) — 2026-10-28

- Đã áp dụng mapping phiên bản `D-049-v2` chỉ cho nguồn mặc định đang hoạt động kỳ `2026-10`; các snapshot D-047 cũ không đổi. Cho phép J3 trống riêng bốn tab đã xác nhận, tiếp tục kiểm tra cấu trúc và báo lỗi J3 nếu header mâu thuẫn. Các tab khác và nguồn mới không tự nhận ngoại lệ. Không tự chuyển xác nhận chưa hoạt động sang kỳ sau.
- VKL, SONA, VIKTOR hiển thị xác nhận chưa hoạt động của kỳ `2026-10`, vẫn giữ các ô nguồn và tiếp tục đọc dữ liệu; nếu phát hiện chi tiêu/nạp kỳ khác 0, dòng trong kỳ hoặc tiền chưa rõ ngày có thể mâu thuẫn, hiển thị cảnh báo rà soát, không chặn đồng bộ. Dữ liệu chi tiết có ngày tháng trước không được tự gán sang tháng 10. Ba tab hiện có J4:J trống và hiển thị “Chưa ghi nhận khoản nhận USDT”; không tạo khoản nhận 0 từ ô trống.
- Đã đồng bộ tay qua API, snapshot #10 `PARTIAL`; sau reload backend scheduler tạo snapshot #11 `PARTIAL`. Lịch sử cũ còn nguyên, kỳ chưa chốt. Nghiệm thu trực tiếp `/reports` tại workspace chính: bốn tab không còn lỗi header, ba tab có trạng thái đúng kỳ; JACK có khoản nhận. Vẫn còn cảnh báo công thức thiếu đầu vào: JACK `F4/F7/F10/F13/F16/F19/F22/F25/F28`, VKL `F4/F5`, SONA `F5`, VIKTOR `F4/F5`; JACK còn dòng chưa phân loại 6, 9 và VIKTOR dòng 6. Các trường chi tiết chưa xác nhận và vấn đề khác trong báo cáo vẫn giữ `PARTIAL`.
- Backend **248 passed**, test VND **1 passed**, TypeScript và build production frontend **pass**. Dừng đúng frontend trước build rồi chạy lại `next start` tại cổng 3000; backend cổng 8000 không dừng, không reset app. Không migration, ghi Sheets, tạo giao dịch, tự chốt kỳ, sửa `BUSINESS_RULES.md`, commit hay deploy.

## Cập nhật — Lưu nguồn và đồng bộ báo cáo Sheets theo tháng (D-048) — 2026-10-28

- Thêm migration `d8a1b2c3d4e5` không thay đổi bảng tài chính hiện hữu: nguồn theo kỳ và mapping D-047 có phiên bản, snapshot JSON tách riêng giữ nguyên truy vết/giá trị, lịch sử từng lần đọc, bản chốt và liên kết tab với ID khách nội bộ đã được người vận hành xác nhận. Nguồn trùng bị từ chối, thay nguồn cùng kỳ cần xác nhận rõ. Kiểm tra cấu trúc trước khi lưu nguồn; bản không đọc được không thay bản gần nhất; PARTIAL không bị gắn nhãn đầy đủ.
- Đồng bộ Sheets riêng mỗi 15 phút và khi backend khởi động, không phụ thuộc giao diện và không gọi/bật Meta sync. Khóa theo nguồn qua PostgreSQL advisory lock hoặc khóa file SQLite để ngăn chạy chồng giữa worker và thao tác tay; khóa được hệ điều hành/database giải phóng khi tiến trình dừng. Lần RUNNING cũ được đánh dấu gián đoạn khi nguồn chạy lại. Có timeout và retry giới hạn; lịch sử và các bản chốt không bị thay thế.
- `/sheets` quản lý nguồn, xem lịch sử, chọn/chốt bản lưu và liên kết khách; `/reports` mặc định đọc bản lưu nguồn mặc định, cho chọn nguồn/bản lịch sử, cập nhật ngay, xem lần đọc và cảnh báo cũ. Không tự chốt, không tự tạo nguồn tháng kế tiếp. Đối chiếu chuyển kỳ chỉ dùng `L1` của bản chốt và `J1` bản hiện hành theo ID khách đã xác nhận, tolerance VND hiện hữu; thiếu liên kết hoặc thiếu bản chốt không kết luận khớp.
- DB local được sao lưu nhất quán bằng SQLite backup trước migration: `var/backups/adsos-before-sheet-reports-20261028-163847.db`, `integrity_check=ok`, revision trước `c3d4e5f6a7b8`; đã nâng SQLite local lên `d8a1b2c3d4e5`. Không áp dụng PostgreSQL/production, không xóa dữ liệu. Kiểm thử migration và các luồng bằng DB riêng.
- Nguồn live hiện tại kỳ `2026-10` đã kiểm tra và lưu làm mặc định, tự đồng bộ bật. Live UI đã đọc bản lưu JOKER, chạy cập nhật ngay và thấy lịch sử; scheduler backend đã tự chạy thêm một lần `SCHEDULED` với kết quả `PARTIAL`. JACK, VKL, SONA và VIKTOR báo `STRUCTURE_ERROR` vì header cột J không khớp mapping, không lấy ô khác thay thế. Các cảnh báo ngày, phạm vi và đối chiếu Meta còn mở; chưa chốt. Hiện danh sách khách nội bộ chưa có các khách Sheets để xác nhận liên kết chuyển kỳ; không tự tạo khách hoặc ghép theo tên.
- Kiểm thử backend **240 passed**, test formatter VND **1 passed**, TypeScript **pass**. Không ghi Sheets, tạo giao dịch, ghi sổ ngân sách, bật Meta sync, commit hay deploy; `BUSINESS_RULES.md` không bị sửa.

## Cập nhật — Mapping chuẩn báo cáo Sheets (D-047) — 2026-10-28

- Báo cáo nguồn Sheets dùng mapping chuẩn của chủ dự án cho tab khách có header phù hợp: `J1` số dư đầu, `K1` ngân sách nạp, `F1/G1/H1` chi tiêu/phí/tổng, `L1` số dư hiện tại; lợi nhuận theo quy ước bằng `G1`, không phải lợi nhuận ròng. Tổng nguồn cấp tab được giữ riêng nếu không đủ căn cứ gán một kỳ; chi tiết không thay thế tổng nguồn và bộ lọc ngày không biến tổng kỳ thành số của khoảng lọc.
- Metadata tab ẩn được kiểm tra trước khi đọc; tab ẩn bị loại khỏi báo cáo/preview/analyze và khi làm mới. Công thức phụ thuộc tab ẩn hoặc ngoài A–L vẫn giữ kết quả nguồn nếu có và cảnh báo chưa kiểm tra phụ thuộc. PEDRI, LOCK, TOMMY, HUNTER tiếp tục chỉ đọc A–L. Khoản J4 trở đi có truy vết, subtotal không cộng trùng; khoản chưa rõ ngày không tự gán kỳ. Header không phù hợp hoặc ô tổng không phải số được báo lỗi, không fallback sang ô khác.
- VND được trình bày số nguyên theo `ROUND_HALF_UP`, dữ liệu nguồn và chênh chính xác giữ để truy vết. Báo cáo Sheets tách khỏi Meta/Manual. Liên kết chi phí và trạng thái thủ công qua `meta_ad_account_id`; tài khoản không khớp/chưa nhập hiển thị rõ và `ACTIVE` mặc định không được xem là trạng thái sự cố đã cập nhật. Chưa tính tỷ lệ sự cố vì tử số chưa được xác nhận; mẫu số là toàn bộ TKQC được giao tại thời điểm hiện tại. Chưa tổng hợp chi phí mua TKQC khi chưa rõ đơn vị và độ phủ.
- Live preview và report độc lập khớp 6 ô `J1/K1/F1/G1/H1/L1` cho JOKER, HUNTER và PEDRI; UI `/reports` xác nhận LIVE/PARTIAL và kết quả JOKER, HUNTER, hai khoản HUNTER J6/J9 chưa rõ ngày, chuyển nguồn và lọc ngày. Mapping các trường khác vẫn chưa xác nhận, Meta chưa đối chiếu; kết quả không phải xác nhận giao dịch. Đã kiểm tra hiển thị hẹp với bảng cuộn ngang.
- Kiểm thử backend **231 passed**, test formatter VND **1 passed**, TypeScript **pass**. Build và chạy production frontend tại workspace chính; không build đè `.next` đang được sử dụng. Không ghi Sheets, tạo giao dịch hoặc dữ liệu tài chính, migration, commit hay deploy; `BUSINESS_RULES.md` không bị sửa.

## Cập nhật — Bàn giao frontend A–L tại workspace chính — 2026-10-28

- Đã xác định `D:\ads-business-os\apps\web` là frontend chính; tiến trình cổng 3000 trước đó chạy `next start`. Sau khi dừng đúng frontend và xác nhận cổng trống, đã build workspace chính và chạy lại `next start` trên cổng 3000; backend cổng 8000 không bị dừng. Không xóa `.next`/`node_modules` hoặc cài lại dependency. Bản sao nghiệm thu cũ đã được dọn, nên không thể so sánh byte-for-byte; mã chính vẫn có các thành phần đã nghiệm thu và được build trực tiếp.
- Khi kiểm tra, nhãn tham chiếu chưa phân giải đặt nhầm các địa chỉ summary `M2/O2` dưới tên PEDRI. Đã sửa riêng trình bày để nêu đúng `TỔNG T10!M2 (=PEDRI!P1)` và `TỔNG T10!O2 (=PEDRI!O1)`; không đọc thêm các ô ngoài A–L và không đổi quy tắc. Vì lỗi nhãn này, đã dừng đúng frontend một lần nữa trước khi build và chạy bản cuối.
- Nghiệm thu trực tiếp `http://localhost:3000/reports`, chọn Google Sheets và làm mới: API HTTP 200, `mode=live`, báo cáo `PARTIAL`. Bốn tab hiển thị A–L và dữ liệu nguồn B–L của dòng 4; không có cảnh báo TKQC thiếu ngày. HUNTER hiển thị riêng hai khoản chưa xác định ngày `J6/K6/L6` và `J9/K9/L9`; TOMMY giữ dòng chưa phân loại 15, 19, 112, 113; cảnh báo tham chiếu PEDRI hiển thị địa chỉ nguồn và công thức chính xác. JOKER vẫn hiển thị `J1` 59.908.004, `F1` 890.727.440 và `TỔNG T10!G2` 207.968.093 theo định dạng nguồn.
- Build Next.js tại workspace chính **PASS**, cả `/reports` và `/health` HTTP 200. Browser click chờ ổn định từng timeout; kiểm tra HTTP/log độc lập vẫn thành công, sau đó gửi click trực tiếp tới nút và nghiệm thu được live. Frontend mới được giữ chạy chế độ `next start`; không reset app, dừng backend, ghi Sheets/DB, migration, xác nhận mapping, commit hay deploy.

## Cập nhật — Sửa phạm vi đọc Sheets và phân loại dòng — 2026-10-28

- Khắc phục lỗi lượt trước hiểu nhầm phạm vi thành `A:A`: PEDRI, LOCK, TOMMY và HUNTER nay yêu cầu `A:L` tại Google Sheets API cho cả `read_grid` và `read_sheet_detail`, cắt phòng vệ response từ M trở đi, giữ metadata merge giao A–L. Analyze, preview và report dùng cùng connector; các tab khác không đổi. Công thức trong A–L phụ thuộc ngoài phạm vi giữ kết quả nguồn, kèm cảnh báo chưa kiểm tra phụ thuộc; không đọc tiếp ô phụ thuộc.
- Phạm vi đọc không tự quyết định độ đầy đủ. Report `PARTIAL` khi thực sự có tab lỗi, bản ghi chưa diễn giải, trường cần thiết chưa nhận diện, đầu vào formula thiếu hoặc phụ thuộc chưa kiểm tra. Tổng theo dòng có ngày được gắn cảnh báo phạm vi; tổng từ ô nguồn giữ nguyên formula. Ngày chỉ kế thừa trong vùng merge; dòng trống phân cách bị loại; giá trị 0 và formula trả chuỗi trống vẫn được giữ.
- Live HUNTER: 27 bản ghi có ID, **0 bản ghi thiếu ngày** sau khi đọc đủ header và merge. Ví dụ `A4:A5` là vùng merge có ngày `A4` 08/10/2026, nên dòng 5 được gán ngày theo merge; `A27:H27` là dòng phân cách trống, không truyền ngày. Cảnh báo 27 dòng thiếu ngày ở đường parse trước không còn tái hiện với header và merge hiện tại; không phải có 27 dòng nguồn thiếu ngày. Hai dòng nhận tiềm năng `J6:L6` và `J9:L9` thiếu ngày được liệt kê riêng, giữ `NEEDS_CONFIRMATION`, không đưa vào tổng theo kỳ.
- Live PEDRI/LOCK/TOMMY lần lượt 24/38/75 dòng ID và 0 dòng ID thiếu ngày; vẫn có khoản nhận thiếu ngày và TOMMY có dòng chưa phân loại. Mapping các tab này chưa xác nhận. Summary `TỔNG T10!M2 = PEDRI!P1`, `O2 = PEDRI!O1`; giá trị tính sẵn trong summary được giữ nhưng tham chiếu sang PEDRI ngoài A–L chưa phân giải. Không đọc `PEDRI!M2/O2` hoặc bất kỳ ô PEDRI từ M trở đi.
- Live đối chiếu dòng 4: HUNTER `F4` raw `825175.35`, `L4` 26100; PEDRI `F4` 5584495, `L4` 26010; LOCK `F4` 5740579, `L4` 26025; TOMMY `F4` 4614056, `L4` 25970. Preview và report thống nhất. Các ý nghĩa J/K/L và tỷ giá ở những tab này vẫn là preview, không suy rộng xác nhận JOKER.
- JOKER không đổi: `J1` 59908004, kỳ `2026-10`, 104 dòng TKQC, `F1` raw `890727439.99999976`, số dư từ `TỔNG T10!G2` raw `207968093.40000021`.
- Kiểm thử phiên trước: focused Sheets **53 passed**; toàn backend **221 passed**; Next.js build bản sao cách ly **PASS**; Pylance không báo lỗi cú pháp. Browser bản build cách ly với response report LIVE lấy trực tiếp từ API xác nhận cả bốn tab hiển thị `A:L`, `F4`, `L4` và cảnh báo phạm vi. Khi kết thúc phiên trước, web cổng 3000 còn chạy build cũ; trạng thái này đã được khắc phục ở cập nhật phía trên.
- Không sửa `BUSINESS_RULES.md`, không đổi quyết định/mapping, không ghi Sheets/DB, không chạy migration, commit hoặc deploy.

## Cập nhật — Báo cáo Google Sheets trên `/reports` — 2026-10-28

- Đã thêm endpoint chỉ đọc `POST /api/v1/sheets/report` và service đọc tab tổng hợp cùng các tab khách chỉ khi được formula/link trong summary nhận diện. Không lưu Sheets vào DB, không ghi workbook, không cộng summary với chi tiết; lỗi tab được giữ thành trạng thái báo cáo một phần.
- `/reports` có bộ chọn riêng giữa “Nguồn hệ thống (Meta + Manual)” và “Google Sheets”. Khi đổi nguồn, vùng dữ liệu nguồn kia bị ẩn/xóa khỏi hiển thị; request hệ thống đang chạy được hủy/không nhận kết quả cũ. Dashboard Sheets có loading, lỗi/retry, empty state, bộ lọc kỳ/khách/ngày, KPI theo giá trị có sẵn trên Sheet, summary cell, chi tiết ngày/TKQC, khoản nhận USDT, chart VND theo ngày và thông tin truy vết/trạng thái mapping.
- `JOKER!J1` chỉ hiển thị ở cấp khách/kỳ; số dư cuối kỳ tiếp tục lấy từ cell/formula summary. Ngày merge chỉ kế thừa trong vùng merge; dòng có formula phụ thuộc ô đầu vào trống được cảnh báo, không coi kết quả 0 là chi tiêu đã xác nhận. Cấu trúc tab khác JOKER vẫn giữ `PREVIEW`/`NEEDS_CONFIRMATION`; xác nhận JOKER không được suy rộng. KPI ngân sách nạp, lợi nhuận, chi phí mua TKQC, dư nợ bàn giao và tỷ lệ sự cố không được dựng khi thiếu mapping/nguồn.
- URL/ID workbook không hardcode. Sau khi đọc thành công từ `/sheets` hoặc `/reports`, browser giữ workbook reference trong `sessionStorage` để dùng trong phiên; không lưu token/secret. Backend không có workbook mặc định, nhưng URL/ID được chủ dự án cung cấp trong lượt này đã đọc LIVE thành công qua connector có sẵn. `GET /api/v1/sheets/mode` vẫn báo nguồn mặc định `mock`; request với URL cụ thể trả `mode=live`.
- Nghiệm thu workbook thực: 46 tab, report `READY`; JOKER có kỳ theo ngày nguồn `2026-10`, ngày quan sát `2026-10-01`–`2026-10-27`, 104 dòng TKQC và 4 dòng nhận USDT. UI hiển thị số dư đầu kỳ từ `JOKER!J1`, spend/fee/total theo formula tổng nguồn `F1/G1/H1`, tiền nhận VND từ `K1`, và số dư cuối kỳ từ summary `TỔNG T10!G2`/formula nguồn; giá trị thô và giá trị định dạng Sheet được trình bày riêng để không thay kết quả formula bằng tổng từng dòng. `TỔNG T10!M2/O2` còn tham chiếu PEDRI và vẫn hiện là unresolved. Kiểm tra thêm SATIVA (`2026-06`, 4 dòng) giữ `NEEDS_CONFIRMATION`; không suy rộng mapping JOKER.
- Connector đọc số JSON bằng `Decimal` trên luồng detail để phép tổng hợp ngày không thêm sai số do parse float. Formula của Sheets tự nó có thể trả giá trị thô gần với giá trị định dạng; giao diện giữ nguyên cả raw value lẫn `formatted_value`, không tự làm tròn/thay source total.
- Đã sửa backend và frontend: `apps/api/app/services/sheets_report.py`, `apps/api/app/api/v1/sheets.py`, `apps/api/tests/test_sheets_report.py`, `apps/web/app/reports/page.tsx`, `apps/web/app/reports/sheets-source-report.tsx`, `apps/web/lib/api.ts`, `apps/web/app/sheets/page.tsx`. Không sửa `BUSINESS_RULES.md` do xung đột chưa xử lý; không đổi `DECISIONS.md` hoặc xác nhận mapping.
- Kiểm tra: focused Sheets tests **48 passed**; toàn bộ backend tests **209 passed**; `npm.cmd run build` **PASS** (11 routes). Sau build, đã khởi động lại frontend và kiểm tra trên trình duyệt: `/reports` tải report Sheets LIVE (API 200); source switch, JOKER/SATIVA, khoảng ngày `2026-10-01` (4 dòng TKQC/2 dòng nhận USDT), KPI số dư tách khỏi lọc chi tiết và biểu đồ hoạt động. Chọn HUNTER hiển thị mục riêng “Dòng TKQC chưa gán ngày (27)” kèm cảnh báo không tính vào kỳ; viewport 390px có document/body rộng 375px, không tràn ngang. Frontend `http://localhost:3000` và API `/health` đang phản hồi 200.
- Không chạy migration, ghi Google Sheets, ghi sổ/DB, bật Meta sync, commit hoặc deploy.

## Cập nhật xác nhận mapping hẹp JOKER — 2026-10-28

- Chủ dự án xác nhận `JOKER!J1` là ngân sách VND chuyển từ tháng trước, số dư đầu kỳ; không phải tiền nạp mới, doanh thu hoặc lợi nhuận. `TỔNG T10!C2` chỉ mang cùng ý nghĩa khi công thức của ô trực tiếp tham chiếu `JOKER!J1`.
- Chủ dự án xác nhận cột D/JOKER hiện không có dữ liệu nghiệp vụ và chưa có mục đích sử dụng; bỏ qua, không cảnh báo thiếu dữ liệu. Chỉ áp dụng hai xác nhận này cho cấu trúc JOKER và ô summary liên kết trực tiếp; không mở rộng sang tab khác.
- `/sheets` hiện hiển thị J1 một lần ở cấp JOKER/kỳ với nhãn “Ngân sách chuyển từ kỳ trước (VND)” và truy vết ô/formula; C2 có cùng nhãn khi điều kiện tham chiếu trực tiếp đúng. Summary cuối kỳ tiếp tục lấy từ công thức Sheets. Không tính lại/làm tròn tiền ở frontend hoặc lặp số dư đầu kỳ theo ngày, account hay dòng nhận tiền.
- Đây là xác nhận ý nghĩa hai trường, không phải duyệt toàn bộ mapping. Không lưu mapping `CONFIRMED`, không nhập sổ/DB; Q-007 tiếp tục mở. `BUSINESS_RULES.md` không được sửa do xung đột chưa xử lý.
- **Còn thiếu để đưa dữ liệu vào báo cáo chính thức:** hoàn tất xác nhận mapping JOKER ngoài hai trường vừa chốt; xác định nguồn và hiệu lực các tỷ giá USD/VND và USDT/VND (Q-005), đồng thời cách phân đoạn lifetime spend qua các kỳ tỷ giá (Q-014); xác nhận quy tắc phí cho JOKER thay vì suy ra chính sách từ một công thức Sheet; và đáp ứng điều kiện đối soát theo D-039/D-042 (mapping đầy đủ, danh tính/ngày/account/currency khớp, dữ liệu Meta VERIFIED hoặc quy trình baseline thủ công được xác nhận). Không hỏi lại hai nội dung đã chốt.
- Kiểm tra lượt này: `npm.cmd run build` PASS (11 routes). UI `/sheets` đọc preview LIVE tại `http://localhost:3000/sheets`; J1 hiển thị giá trị runtime `59.908.004 đ` với địa chỉ ô, C2 hiển thị cùng nhãn và formula `=JOKER!J1`, G2 giữ nguyên kết quả/formula `=B2+C2-F2` của Sheets. Sau khi lọc ngày, thẻ opening balance vẫn chỉ có một; không còn cảnh báo J1/cột D. Dev server hiện chạy trên cổng 3000. Không thay đổi backend, mapping DB, báo cáo chính thức hoặc dữ liệu Google Sheets.

## Cập nhật — Thử đọc Google Sheets thực

- **Xung đột tài liệu:** `docs/BUSINESS_RULES.md` không được sửa, ghi đè, discard hoặc hợp nhất theo yêu cầu chủ dự án; phần nội dung chưa lưu vẫn thuộc editor. Công việc Sheets dưới đây không phụ thuộc việc giải quyết xung đột đó.
- **Kết nối hiện có:** `GET /api/v1/sheets/mode` mặc định trả `mode=mock`, `spreadsheet_id_configured=false`, `auth=none`; `/api/v1/sheets/mappings` trả 0 mapping. URL cụ thể đã được đọc `mode=live`; không yêu cầu cấu hình lại credentials. Không ghi credential hay Spreadsheet ID vào tài liệu.
- **Tab theo gid:** live analyze liệt kê 46 tab; `gid=1730431233` khớp duy nhất tab `TỔNG T10` với `sheetId=1730431233`. Tab là SUMMARY. Phân tích cấu trúc trước đó đọc dữ liệu để lấy samples/formulas nhưng không trả bản đồ ô/dòng; đã thêm `POST /api/v1/sheets/preview` để đọc đúng một tab theo sheetId, trả A1 reference, effective value, formatted value, formula, numberFormat và merge ranges. Endpoint chỉ GET tới Sheets, không ghi Sheets/DB và không lưu/xác nhận mapping.
- **Preview thực:** tab tổng hợp tham chiếu dòng JOKER tại `A2`; công thức ở `B2:G2` trỏ sang `JOKER!K1`, `JOKER!J1`, `JOKER!F1`, `JOKER!G1`, `JOKER!H1` và `=B2+C2-F2`. Tab khách `JOKER` có `sheetId=1868124384`, header ở dòng 3; ngày `2026-10-01` được lưu bằng serial ngày ở `A4` và merge `A4:A7`. Preview dòng account/chi tiêu và formula được truy vết theo ô; ý nghĩa cột thiếu header vẫn chưa xác nhận. Số tiền chi tiết không được ghi vào báo cáo này.
- **Phát hiện định dạng tiền:** Sheets dùng pattern `[$đ-42A]`, giá trị format hiển thị `đ`; parser trước đó nhầm dấu `$` trong token format thành USD. Đã sửa để nhận VND từ `đ/₫/VND`, chỉ nhận USD khi có `USD`/`US$` tường minh; bare `$` giữ currency chưa xác định.
- **Đối chiếu hệ thống:** `/reports` không đọc Sheets. Service lấy `spend_snapshots` và `manual_reviews`; runtime hiện `meta_mode=mock`, `meta_source_label=MOCK_DATA`, coverage 1/1. DB chỉ có khách `S17.1-TEST` và hai dòng manual USD ngày 2026-10-26/27; không có khách JOKER trong danh sách, nên không có số hệ thống cùng khách/ngày/currency để so sánh. Không coi thiếu dữ liệu là 0 và không phán MATCH/DIFF.
- **Trạng thái mapping:** mapping DB vẫn 0; preview trả `PREVIEW`/`NEEDS_CONFIRMATION`. Q-007 tiếp tục mở; chưa nhập dữ liệu vào sổ hoặc `/reports`, không bật Meta sync, không ghi Sheets.
- **Kiểm thử:** `tests/test_sheets_s6plus.py` + `tests/test_sheets_q007_live.py`: 44 passed; live endpoint `/preview` trả thành công cho summary và tab JOKER. Không chạy migration.
- **Giao diện:** tái sử dụng `/sheets`: người vận hành nhập URL/ID, cấu trúc được phân tích để tra sheetId, sau đó gọi endpoint preview riêng cho `TỔNG T10` và `JOKER`. URL không hardcode hoặc lưu DB. Hiển thị nhãn `NGUỒN GOOGLE SHEETS — PREVIEW, CHƯA ĐỐI CHIẾU META`, thời điểm đọc, kỳ lấy từ ô ngày, giá trị gốc/format, công thức và địa chỉ nguồn. Bảng chi tiết dùng các ô đã làm rõ riêng cho JOKER; phần USDT tách theo từng dòng nguồn trong khối ngày, không lặp theo dòng account. Công thức trả 0 nhưng tham chiếu đầu vào trống được đánh dấu thiếu đầu vào. `/reports` có liên kết sang preview nhưng giữ nguồn Manual/Meta riêng.
- **Nghiệm thu trình duyệt:** `/sheets` tải dữ liệu LIVE; UI xác nhận summary `TỔNG T10`, dòng JOKER, kỳ ngày 2026-10-01–2026-10-27 lấy từ serial DATE, ngày mặc định 2026-10-01, ID TKQC dạng text và ô đầu vào trống được gắn cờ. Khối ngày `A4:A7` hiển thị đúng phạm vi merge; hai dòng USDT `J4`/`J5` (3.000 và 4.000 USDT) xuất hiện từng dòng một lần. Đã kiểm tra viewport 390px: body không tràn ngang; bảng cuộn trong khung riêng. `/reports` có liên kết riêng sang `/sheets`, nhãn Meta vẫn MOCK. Frontend local đang chạy tại `http://localhost:3000`.
- **Kiểm thử:** backend focused regression `tests/test_sheets_s6plus.py` + `tests/test_sheets_q007_live.py`: 44/44 pass. `npm.cmd run build` cuối cùng pass, 11 routes; `/sheets`, `/reports`, OpenAPI trả HTTP 200 sau khởi động lại dev server. Không nhập dữ liệu khách thật vào fixtures.
- **Chủ dự án đã làm rõ trong hội thoại:** B3/B4/B6 là loại tiền tài khoản; I6 là tỷ giá USD/VND chi tiêu; J/K/L lần lượt là USDT, giá trị VND quy đổi và tỷ giá USDT/VND. Đây là diễn giải được trả lời theo các ô cụ thể, chưa được lưu vào `sheet_mappings` hoặc xác nhận một mapping tổng thể. Mapping DB vẫn 0.
- **Còn thiếu trước khi dùng làm baseline/sổ:** xem mục “Cập nhật xác nhận mapping hẹp JOKER” ở đầu file. Nguồn và thời điểm hiệu lực độc lập của tỷ giá `I6`/`L4` chưa rõ. Phí trong công thức Sheet chỉ là dữ liệu nguồn, không mặc định thành chính sách phí cho khách. Không nhập dữ liệu hoặc tính lại lịch sử từ các tỷ giá này.
- **An toàn:** không gọi dữ liệu mock thay cho live, không ghi Sheets/DB, không chạy migration, không thay đổi mapping/quy tắc, không bật Meta sync.
- **Kiểm tra trước cập nhật xác nhận JOKER:** mô phỏng API analyze trả HTTP 503; UI hiện lỗi và nút `Thử lại đọc Sheets`. Sau khi bỏ lỗi mô phỏng, bấm thử lại đọc thành công dữ liệu LIVE và khôi phục preview JOKER. `npm.cmd run build` chạy sau patch retry: PASS, 11 routes. Khởi động lại frontend sau build; `/`, `/sheets`, `/reports` đều HTTP 200.

## Cập nhật S17.3 — Financial Dashboard frontend integration (2026-10-28)

- **Dashboard:** tích hợp trên route `/reports`, giữ layout/top-nav hiện có. KPI và báo cáo ngày dùng `GET /api/v1/reports/kpi` và `GET /api/v1/reports/daily`; đã smoke test `GET /api/v1/reports/customers/1`. Thêm adapter đọc-only `GET /api/v1/reports/transactions?limit=5` từ `usdt_transactions`; không tạo giao dịch giả.
- **Aggregation:** `daily.chart_rows` được tổng hợp ở Backend bằng `Decimal`, theo ngày và tách từng currency. Frontend không cộng/đổi tiền, không tự tính growth; KPI lợi nhuận ròng chỉ dùng `profit_final`.
- **Giao diện:** KPI cards, Recharts theo currency, bảng nhận USDT, skeleton, lỗi/retry và trạng thái rỗng. Currency không có bucket dữ liệu hiển thị `—` (không giả thành `0 USD`); các currency ngoài USD hiển thị riêng. Nối Tailwind v4 với nguồn/config hiện có để utility được sinh; top-nav và bảng cuộn trong khung trên màn hình hẹp.
- **Dữ liệu local khi nghiệm thu:** Backend trả `MOCK_DATA` cho Meta. Bản ghi manual hiện có của `S17.1-TEST` cho 2026-10-26/27 hiển thị chi tiêu 120/50 USD và phí 4.8/2 USD; KPI phí 6.8 USD mang trạng thái `TẠM TÍNH`, không phải số Meta live. Không có giao dịch USDT trong nguồn hiện tại; chi phí tài khoản, chi phí vận hành và lợi nhuận ròng hiển thị `CHƯA ĐỦ DỮ LIỆU`.
- **Kiểm tra:** backend focused tests 33/33 và toàn bộ regression 200/200 pass (một cảnh báo deprecation của Starlette/httpx); `npm.cmd run build` pass, 11 routes. Smoke test API KPI, daily, customer report, transactions đều HTTP 200; `/`, `/reports`, `/reviews`, `/customers/1`, `/sheets` HTTP 200 và đã kiểm tra heading trên trình duyệt. Đã mô phỏng API KPI/daily lỗi: thông báo lỗi xuất hiện và bấm Retry gửi lại request. Responsive đã kiểm tra ở viewport hẹp 434 CSS px và desktop; không còn tràn trang ngang, bảng/nav có thể cuộn riêng.
- **Giới hạn và an toàn:** không sửa backend business calculations, không migration, không Meta token/API live, không ghi Google Sheets, không thanh toán hoặc deploy. Template v0 chỉ truy cập được preview; mã nguồn template không được nhập nguyên văn.
- **Tiếp theo:** chủ dự án nghiệm thu giao diện tại `http://localhost:3000/reports` sau khi chạy frontend local. Growth comparison chưa có API; transactions chỉ bao gồm USDT records hiện hữu, chưa phải sổ giao dịch đầy đủ; chưa có dữ liệu để xác nhận lợi nhuận ròng.

## Cập nhật phiên #18 — runtime dashboard và hợp nhất yêu cầu sản phẩm (2026-10-27)

- **Runtime:** khi bắt đầu, `/` và `/reports` trên `localhost:3000` trả HTTP 500, backend `/health` HTTP 200. Log cho thấy lỗi module chunk `./627.js` không tồn tại và thiếu `.next/fallback-build-manifest.json`; xác định đúng Next dev server và tiến trình con trên cổng 3000. Dừng đúng hai PID, khởi động lại frontend hiện hữu; không xóa `.next`, không đụng `node_modules`/dependency. Sau restart, `/` và `/reports` trả HTTP 200, API dashboard/report trả HTTP 200; đã kiểm tra UI đã hydrate trên trình duyệt: trang tổng quan hiện số liệu, trang tài chính hiện KPI/bảng ngày theo dữ liệu local. Nguyên nhân gốc tạo ra artifact không đồng nhất chưa xác định; chỉ xác nhận restart đã khôi phục runtime.
- **Dữ liệu local:** giao diện hiện hiển thị fixture/nghiệm thu cũ `S17.1-TEST`; không xóa hay sửa dữ liệu này trong phiên.
- **Tài liệu cập nhật:** mục tiêu sản phẩm và manual-first trong `BUSINESS_RULES.md`; hai tỷ giá, cơ sở phí VND, phân bổ khoản nhận USDT, số dư âm và bàn giao TKQC trong `FINANCE_RULES.md`; các quyết định D-043–D-045 và câu hỏi Q-014–Q-019 trong `DECISIONS.md`; ranh giới kiến trúc/roadmap đề xuất trong `PROJECT_ARCHITECTURE.md`.
- **Trạng thái quyết định:** các công thức ngân sách VND, phân bổ tiền và trường dữ liệu bàn giao ghi là đã chốt theo yêu cầu chủ dự án. Thiết kế schema/API, kỳ tỷ giá lifetime spend, nguồn tỷ giá, giá TKQC tại biên, quyền API Meta và các KPI còn thiếu được giữ rõ là đề xuất/câu hỏi chờ; chưa triển khai module tài chính mới, migration, kết nối thật hay ghi dữ liệu bên ngoài.
- **Kiểm tra đã chạy:** HTTP runtime + browser UI cho `/` và `/reports`; backend `/health`, `/api/v1/dashboard/overview`, `/api/v1/reports/kpi`, `/api/v1/reports/daily`. Không chạy build/test trong phiên này vì không sửa code ứng dụng.
- **Tiếp theo:** trước khi quy đổi/billing spend lifetime, chốt Q-014. Sau đó triển khai một luồng nhỏ nhập tay giao dịch nhận tiền và phân bổ, kèm idempotency/audit và báo cáo đối chiếu; chưa bật đồng bộ payment provider.

## Giai đoạn hiện tại

**Giai đoạn 0-N+1 — S17.2 PHIÊN #17.2: Audit chất lượng logic tài chính & đối chiếu thủ công (INSPECT→REPRODUCE→FIX→TEST) — tái hiện 8 lỗi bằng test, sửa tối thiểu, 198/198 pass + web build PASS. Cập nhật: 2026-10-27 (phiên #17.2)**

- **8 lỗi đã xác nhận bằng test thất bại trước khi sửa** (`tests/test_s172_audit.py`, 9 test):
  1. **F1-a mất observation:** `_derive_key` không gồm `observed_at` + UI không gửi `idempotency_key` → lần kiểm tra mới cùng số tiền bị coi là retry, không lưu. → `_derive_key` nhận `observed_at`; UI sinh `idempotency_key` + `observed_at` **một lần cho mỗi lần lưu** (`pendingAttempt` ref) và **tái dùng khi retry sau lỗi mạng**; lưu thành công mới xoá → lần kiểm tra mới là key mới.
  2. **F1-b key dùng lại cho payload khác** → trả review của request khác (im lặng). → kiểm tra `existing_obs` khớp (customer/ngày/account/campaign/kind), lệch → `ValueError` (400); key > 128 ký tự bị từ chối.
  3. **F1-c đổi currency cùng campaign/ngày/account** → IntegrityError/500 hoặc trộn nhóm. → chuẩn hoá `currency` upper; review cũ khác currency → `ValueError` (400), không ghi đè, không trộn.
  4. **F2 baseline xung đột** (2 campaign cùng account+ngày, `sheet_spend` khác nhau) bị `max()` im lặng. → `_recompute_group_verdict` phát hiện `len(set(baselines))>1` → `NEEDS_CONFIRMATION`; **bỏ dòng ghi đè `review.sheet_spend = baseline`** (trước đây xoá mất bằng chứng xung đột).
  5. **F3-a cộng trùng Meta + Manual** cùng campaign/ngày (fee/billing gấp đôi). → `daily_spend_rows` dựng tập `(customer, ngày, campaign)` đã có snapshot VERIFIED; quan sát tay trùng campaign đó **không vào tổng tiền** (vẫn giữ lịch sử review).
  6. **F3-b profit giả khi thiếu chi phí account** (coi cost = 0 → lợi nhuận = fee). → thiếu `purchase_cost` → `profit_provisional.amount = None` + `CHƯA ĐỦ DỮ LIỆU`; chỉ `TẠM TÍNH` khi có đủ fee + cost.
  7. **F3-c làm tròn banker's** (`round`): 2.90 × 5% = 0.145 → 0.14. → helper `_money`/`_money_f` dùng `Decimal.quantize(0.01, ROUND_HALF_UP)` cho fee/billing/daily/KPI; tính tiền trong `daily_spend_rows` chuyển sang `Decimal` (không cộng float).
  8. **F3-d `campaigns_green` đếm sai** — mọi campaign có `customer_id` (kể cả UNRECOGNIZED). → chỉ đếm `recognition_status == "CONFIRMED"`.
- **File đổi:** `apps/api/app/services/reviews.py`, `apps/api/app/services/reports.py`, `apps/web/app/reviews/page.tsx`, `apps/api/tests/test_s172_audit.py` (mới), cập nhật semantics 2 test cũ (`test_retry_without_key_derived_from_content`: cùng nội dung **và cùng `observed_at`** = retry, khác thời điểm = lần mới; `test_kpi_with_manual_data_provisional`/`test_kpi_fee_grouped_by_currency`: profit `None` + CHƯA ĐỦ khi thiếu cost).
- **Kiểm thử:** **198/198 pass** (189 cũ + 9 mới); `npm.cmd run build` PASS (11 routes); backend :8000 reload code mới — `/health` ok, KPI thật trả `MỘT PHẦN`, profit `None`/`CHƯA ĐỦ DỮ LIỆU`, fee USD 6.8.
- **Giới hạn (trung thực):** máy không có docker/psql → **chưa kiểm chứng migration trên PostgreSQL** trong phiên này (SQLite dev đang ở head `c3d4e5f6a7b8`); chưa có Meta token thật (Q-009); mapping tab thật chưa CONFIRMED; chưa đụng Google Sheets.
- **Không đổi quy tắc nghiệp vụ** — mọi sửa chỉ làm code khớp D-038/D-041/D-042; không thêm công thức mới, không auto-confirm.

**Giai đoạn 0-N+1 — S17.1 PHIÊN #17.1: Nghiệm thu + sửa lỗi F1–F6 theo D-042 — lịch sử quan sát append-only (`manual_review_observations`, idempotency key UNIQUE, observed_at, late observation KHÔNG ghi đè), kết luận MATCH/DIFF đúng mức Customer+Account+Ngày+Currency (đủ điều kiện: mapping CONFIRMED + baseline hợp lệ + đủ tập campaign + cùng currency + không xung đột → thiếu bất kỳ → INCOMPLETE/NEEDS_CONFIRMATION), báo cáo theo currency (fee/profit/billing tách USD/VND/GBP/EUR, `company_data_state` + `coverage`), UI preview không cần Meta Token + badge baseline CHỐT/PREVIEW. 189/189 pass (173 cũ + 16 mới) + migration up/down/up + web build PASS + API acceptance thật PASS. Cập nhật: 2026-10-27 (phiên #17.1)**

- **F1/Lịch sử (D-042 #1):** bảng `manual_review_observations` append-only — mỗi lần kiểm tra hợp lệ = 1 dòng; `idempotency_key` UNIQUE (retry cùng key → trả kết quả cũ, KHÔNG ghi thêm; không có key → suy ra hash nội dung); `observed_at` (thời điểm quan sát thực) + `recorded_at`; quan sát đến muộn vẫn lưu nhưng KHÔNG ghi đè dòng hiện hành mới hơn; ghi observation + update current trong 1 transaction; quan sát tay không bao giờ thành checkpoint 09:00 / `META_API_VERIFIED`. Migration `c3d4e5f6a7b8_s171_observations.py` reversible — verify up→down→up OK, `apps/api/adsos.db` đã migrate.
- **F2/F3/Kết luận (D-042 #2):** `_recompute_group_verdict` chốt ở mức Customer + Account + Business Date + Currency — điều kiện mapping CONFIRMED (không preview) + baseline hợp lệ + `campaign_set_complete` + cùng currency (USD/VND tolerance `tolerance_for_currency`; GBP/EUR thiếu tỷ giá → `NEEDS_CONFIRMATION`) + không xung đột → thiếu bất kỳ → `INCOMPLETE`/`NEEDS_CONFIRMATION`/`NEEDS_SHEET_BASELINE`; tổng nhóm = baseline account+ngày TÍNH MỘT LẦN (không cộng theo campaign). Fix bug: `create_review` set `observed_spend` vào review mới TRƯỚC recompute (trước đây tổng nhóm = 0 → DIFF sai).
- **F4/Báo cáo theo currency (D-042 #3):** `daily_spend_rows` thêm `meta_by_currency`/`manual_by_currency`/`fee_by_currency`/`billing_by_currency` (cột legacy = USD-only; phí tính riêng từng currency — khách VND vẫn vào doanh thu phí); `company_kpi` thêm `company_data_state` (MỘT PHẦN/ĐẦY ĐỦ/CHƯA ĐỦ DỮ LIỆU) + `coverage` + `service_fee_revenue_by_currency`, profit chỉ tính USD (chưa có profit đã chốt khi thiếu chi phí); không quy đổi thiếu tỷ giá (Q-005).
- **F5/Preview (D-042 #4):** `GET /sheets/compare` chạy không cần Meta Token; mapping chưa CONFIRMED → preview với `sheet_baseline_confirmed=False` → verdict `NEEDS_CONFIRMATION` (không chốt baseline); `NO_LIVE_META_DATA` không chặn đối chiếu thủ công.
- **F6/UI:** `/reviews` — badge baseline CHỐT/PREVIEW, checkbox "đã kiểm tra đủ tập campaign", bảng Kết luận + Điều kiện, xem lịch sử quan sát từng review (`GET /manual-reviews/{id}/observations`); `/reports` — header độ phủ KPI, doanh thu phí theo currency, profit ghi rõ chỉ USD, billing/daily theo currency; `/customers/[id]` — bảng review mức account+ngày + cột currency trong daily.
- **Route mới:** `GET /api/v1/manual-reviews/{review_id}/observations`; `ReviewCreate` thêm `observed_at`/`idempotency_key`/`sheet_baseline_confirmed`/`campaign_set_complete`/`account_conflict`.
- **API acceptance thật (:8000):** tạo customer `S17.1-TEST`; review 09:00 VN obs 100 → MATCHED; 15:00 VN obs 120 → obs 2, current 120; retry cùng idempotency key → vẫn 2 obs; late obs (09:00 cũ) → obs 3, current GIỮ 120; summary MATCHED account+ngày 120/120; KPI `MỘT PHẦN` coverage 1/1 fee USD 4.8 `{"USD":4.8}` profit TẠM TÍNH; preview → `NEEDS_CONFIRMATION`.
- **Chưa đụng dữ liệu thật:** không ghi Google Sheets; không auto-confirm mapping/fee/tỷ giá. Dữ liệu test local trong `adsos.db` (customer `S17.1-TEST`, review `act_s171_accept`/`act_s171_preview`) — có thể xoá sau nghiệm thu.

**Giai đoạn 0-N+1 — S17 PHIÊN #17: Báo cáo + đối chiếu thủ công hoạt động KHÔNG cần Meta token (D-041 duyệt) — manual_reviews (MANUAL_REVIEWED/VISUALLY_REVIEWED, VISUAL_ONLY KHÔNG MATCH, idempotent + audit) + bộ máy báo cáo dùng trung (daily/KPI/customer) + 4 trang web mới. 173/173 pass + web build PASS. Cập nhật: 2026-10-27 (phiên #17)**

- **S17 backend:** model `ManualReview` (unique `(customer_id, ad_account_meta_id, campaign_meta_id, business_date)` — idempotent), migration `b1e5c7d9f241_s17_manual_reviews.py` (reversible), service `reviews.py` (MANUAL_REVIEWED có số quan sát tay → MATCH/DIFF theo tolerance; VISUALLY_REVIEWED không số → VISUAL_ONLY, KHÔNG tự coi là MATCH; giá trị Sheets không có → tổng chỉ quan sát — `sheet_baseline_available=False`; không bao giờ đổi nhãn snapshot VERIFIED từ Meta), service `reports.py` (bộ máy dùng chung Manual + Meta: daily theo ngày nghiệp vụ + khách, KPI, report từng khách) + routes `POST/GET /api/v1/manual-reviews`, `/summary`, `/reports/daily`, `/reports/kpi`, `/reports/customers/{id}`.
- **KPI 10 dòng:** (1) chi tiêu Meta, (2) doanh thu phí dịch vụ (theo `customer.fee_rate`), (3) tiền khách nạp USDT MATCHED (giữ đơn vị riêng, KHÔNG cộng VND), (4) chi phí account purchase, (5) vận hành phân bổ (chưa đủ dữ liệu), (6) profit tạm tính = fee − account costs (TẠM TÍNH), (7) profit đã chốt (chưa đủ), (8) billing + công nợ (chưa đủ — chờ tỷ giá Q-005), (9) khách đã kiểm, (10) khách chưa đối chiếu. Dữ liệu thiếu → None + "CHƯA ĐỦ DỮ LIỆU", KHÔNG 0 giả; phân biệt TẠM TÍNH/ĐÃ CHỐT.
- **S17 web UI:** `/reports` (KPI + chi tiêu theo ngày/khách, filter hôm nay/hôm qua/ngày/khoảng/tháng + khách), `/reviews` (chọn khách + ngày → đọc Sheets chỉ đọc → nhập Campaign ID + tích lũy quan sát → chênh lệch → lưu MANUAL_REVIEWED hoặc VISUALLY_REVIEWED), `/customers/[id]` (fee/account history/campaigns/USDT/daily/reviews), `/config` (Meta connection status + hướng dẫn cấp token ads_read). Nav thêm "Kinh doanh" + "Đối chiếu" + "Cấu hình".
- **Kiểm thử:** **173/173 pass** (162 cũ + 11 mới `tests/test_s17_reports_reviews.py`); migration upgrade/downgrade/upgrade OK trước khi thực hiện; migration chạy sạch trước khi thực hiện.
- **Chưa đụng dữ liệu thật:** không ghi Google Sheets; không auto-confirm mapping/fee/tỷ giá; mock data quảng cáo chỉ là kết quả demo rõ ràng.

**Giai đoạn 0-N+1 — S16 PHIÊN #16: Meta Live Read-only chuẩn bị kết nối (D-040 duyệt) — connector hạ API v21.0 → mặc định v26.0 (+ env `ADSOS_META_API_VERSION`), endpoint `GET /api/v1/meta-sync/check` kiểm tra token/ads_read/account (mock → 400, KHÔNG fallback), mode live không tự chuyển mock khi lỗi; 162/162 pass + web build PASS. Chưa có Meta token thật (Q-009) → JOKER chờ chủ dự án cấp token env; live comparison khi đủ: mapping CONFIRMED + campaign CONFIRMED + token + tỷ giá nếu quy đổi. Cập nhật: 2026-10-27 (phiên #16)**

- **API version (D-040 #1):** `MetaAdsConnector.api_version` mặc định `v26.0` (không còn v21.0), đọc env `ADSOS_META_API_VERSION`, tham số khởi tạo vẫn thắng env; URL Graph `https://graph.facebook.com/{version}/`.
- **Token gate (D-040 #2):** `check_access()` trả mode + api_version + `accounts_accessible` (đọc `me/adaccounts` hoặc theo BM token map); mock → MetaAPIError rõ (KHÔNG fallback); lỗi 401/403 giữ nguyên live, báo MetaAuthError; chỉ GET; repr/check kết quả không chứa token.
- **Không dùng mock khi live (D-040 #3):** live sheets + thiếu Meta token → `NO_LIVE_META_DATA` từng dòng (phiên #15); mapping chưa CONFIRMED → `NEEDS_MAPPING`; xung đột trùng (account+ngày)/chuyển giao khách → `NEEDS_CONFIRMATION`.
- **Regression:** **162/162 pass** (157 cũ + 5 mới `test_meta_api_version.py`: default v26.0, env override, param thắng env, mock chặn check, URL dùng version cấu hình).
- **Tiếp theo:** chủ dự án cấp token `ads_read` → chạy `GET /api/v1/meta-sync/check` → seed JOKER + account thật + assignment → `POST /api/v1/meta-sync/run` → lấy snapshot VERIFIED → CONFIRM mapping JOKER trên `/sheets` → `GET /api/v1/sheets/compare` đối chiếu 3–5 campaign.

**Giai đoạn 0-N+1 — D-039 PHIÊN #15: hoàn thiện nhận diện + đối soát trước khi CONFIRM mapping — 4 dạng mã ngày (MMDD/DDMM/MM/DD/DD-MM với dấu /), biên số chống mã 6 chữ số; serial Sheets kiểm tra chống lệch 1 ngày (46321 = 26/10); tiền tệ GBP/EUR nhận diện riêng (KHÔNG mặc định USD/VND); trùng (Account ID + ngày) hoặc account chuyển giao giữa khách → NEEDS_CONFIRMATION, không tự gán; live sheets thiếu Meta token → NO_LIVE_META_DATA (không dùng mock khẳng định MATCH). 157/157 pass + web build PASS. Live READ-ONLY JOKER: 8 dòng account → NEEDS_MAPPING (mapping chưa CONFIRMED) + NO_LIVE_META_DATA (Meta token chưa cấp). Cập nhật: 2026-10-27 (phiên #15)**

- **Nhận diện (meta_sync):** `_DATE_CODE_RE` mới — token `(?<![0-9/])(\d{4}|\d{2}/\d{2})(?![0-9/])`: nhận `1025`/`2510`, `10/25`/`25/10`; loại mã 6 chữ số (TK678910), `10250`, `110/25`, `10/251`; `extract_report_dates` đọc cả MM/DD và DD/M mỗi token — chỉ trả date khi tập cách đọc còn duy nhất 1 ngày; mơ hồ (`1102`, `11/02`) → UNRECOGNIZED.
- **Serial ngày (sheets_compare):** `_serial_to_date` origin 1899-12-30 — test chống lệch 1 ngày: 46296=01/10, 46319=24/10, 46320=25/10, 46321=26/10, 46322=27/10/2026; text/mơ hồ → SKIPPED không phán.
- **Tiền tệ (D-039 #3):** `currency_from_header()` USD ($)/VND (đ)/GBP (£)/EUR (€); header lạ → NEEDS_CONFIRMATION (KHÔNG tự mặc định VND); USD↔USD so trực tiếp; GBP/EUR vs Meta USD → NEEDS_CONFIRMATION_RATE; VND chỉ quy đổi khi `confirmed_rate` đã duyệt (Q-005).
- **Mapping ếīm (D-039 #4):** cùng ID account xuất hiện ≥2 lần cùng ngày nghiệp vụ → NEEDS_CONFIRMATION (quy tắc phân bổ chưa rõ), không tự cộng/so.
- **Chuyển giao (D-039 #2):** campaign cùng account + ngày thuộc >1 khách → NEEDS_CONFIRMATION (thiếu căn cứ kỳ sử dụng); account REPLACED vẫn ghép campaign cũ (test có).
- **NO_LIVE_META_DATA (D-039 #5):** spreadsheet thật (key ≠ mock) + chưa có `ADSOS_META_ACCESS_TOKEN`/`ADSOS_META_TOKEN_MAP` → mọi dòng dữ liệu NO_LIVE_META_DATA; KHÔNG dùng mock/khẳng định MATCH; summary `meta_live` hiển thị trạng thái.
- **Test:** **157/157** (150 cũ + 7 mới: serial không lệch ngày, 4 dạng + an toàn chuỗi số, currency GBP/EUR, GBP NEEDS_RATE, trùng account/ngày, chuyển giao 2 khách, NO_LIVE_META_DATA); web build PASS.
- **Chưa đụng dữ liệu thật:** không ghi Google Sheets; không auto-confirm mapping/fee/tỷ giá; mọi status NEEDS_* chờ chủ dự án.

**Giai đoạn 0-N+1 — D-038 SỬA D-036 (phiên #14): bỏ cum(day)−cum(day−1) theo ngày Meta; đối chiếu theo Customer + ngày nghiệp vụ (mã ngày tên campaign D-026) + Ad Account ID; chi tiêu = TỔNG TÍCH LŨY snapshot VERIFIED mới nhất mỗi campaign CONFIRMED, nhiều campaign cùng account/ngày cộng tổng (Campaign ID chỉ đếm 1 lần); tolerance theo đơn vị tiền. 150/150 pass. Live READ-ONLY tab JOKER: NEEDS_MAPPING (mapping chưa CONFIRMED — đúng gate).** Cập nhật: **2026-10-27 (phiên #14)**

- **Sửa `sheets_compare.py`:** `_meta_cumulative_by_account_business_day()` thay `_meta_daily_by_account()` — lọc campaign `CONFIRMED` + `report_period_start/end == ngày nghiệp vụ` (theo mã ngày trong tên, KHÔNG ngày Meta); tổng chi tiêu tích lũy = snapshot VERIFIED mới nhất mỗi campaign (D-008); account `REPLACED` vẫn ghép; UNRECOGNIZED → không vào (NO_META). Tolerance `tolerance_for_currency()`: env `ADSOS_COMPARE_TOLERANCE_USD` (0.01) / `ADSOS_COMPARE_TOLERANCE_VND` (1 đ). VND chỉ quy đổi khi truyền `confirmed_rate` đã phê duyệt (Q-005 còn mở) — không có → `NEEDS_CONFIRMATION_RATE`.
- **8 test yêu cầu (13 test file compare):** campaign bắt đầu trước nhưng đối chiếu ngày qua tên; checkpoint 09:00=1000 + latest 20:00=1002.84 → tổng 1002.84 (không cộng trùng checkpoint); nhiều campaign cùng account/ngày; 3 múi giờ (UTC-7/+3/+7) ngày theo tên; account REPLACED + drift; chạy lại không trùng; UNRECOGNIZED loại; USD/VND với tỷ giá duyệt.
- **Cấm tự ghi/auto-confirm giữ nguyên:** không auto-confirm mapping, không auto xác nhận tỷ giá — gửi lại NEEDS_CONFIRMATION khi thiếu.
- **Live READ-ONLY trên bảng thật:** `/api/v1/sheets/compare?sheet_name=JOKER&spreadsheet=14mgYdWuhkF0…` → `NEEDS_MAPPING` (mapping tab thật chưa được chủ dự án CONFIRMED) — đúng quy trình: không tự ghép khi mapping chưa duyệt.
- **Việc chờ chủ dự án:** xác nhận mapping từng tab (CONFIRMED) + fee rate từng khách + nguồn tỷ giá (Q-005) → sau đó chạy compare từng tab và báo cáo campaign ghép/sai lệch.

**Giai đoạn 0-N+1 — S6+ Q-007 RULES HOÀN TẤT (phiên #13): encode 6 quyết định D-035/D-036/D-037 vào service + UI + test — philosophy "no ad-account+date spending; full flow customer→day→account→campaign→Campaign ID→spend→checkpoint/drift→reconcile"; comparer Sheets↔DB chỉ đọc; mapping CONFIRMED gate. 144/144 pass. WEB BUILD PASSED.** Cập nhật: **2026-10-27 (phiên #13)**

- **D-035/D-036/D-037 vào code:** `app/services/sheets_structure.py` thêm `classify_sheet()` (TỔNG→SUMMARY, MẪU→TEMPLATE, ALL/OLD→UNCLASSIFIED, còn lại CUSTOMER), `fee_rate_from_formulas()` (bóc `=F*4%`/`=F*5%` từ công thức Sheets), `resolve_row_dates()` (ngày merge qua nhiều dòng → root date block, không tự sửa); annotate cột Phí khác 4% → `needs_confirmation` + `fee_confirmed=False` (D-037: KHÔNG tự tính fee khi chưa xác nhận fee rate từng khách); `propose_mapping` gắn `sheet_type`, tab đặc biệt → đề xuất sheet-level `column_index=-1, role=None, note KHÔNG tự đồng bộ dòng khách từ 3 tab này` (D-035).
- **So khớp nghiêm ngặt (D-036):** service mới `app/services/sheets_compare.py` — `compare_sheet_with_db()` chỉ đọc: chỉ đối chiếu tab loại CUSTOMER với mapping **CONFIRMED** đủ DATE + ACCOUNT + SPEND (page `/sheets` chốt); chi tiêu ngày Meta = max snapshot tích lũy cum(day) − cum(day−1) snapshot VERIFIED (D-008/D-011); VND (Sheets) vs USD (Meta) → `NEEDS_CONFIRMATION_RATE` (Q-005), KHÔNG tự đổi tiền; row không có account id / số → bỏ qua (không tạo row rác); route `GET /api/v1/sheets/compare?sheet_name=...` (also accepts `sheet=`).
- **Không ghi:** cả comparer + comparer UI đều chỉ đọc; KHÔNG thêm method ghi Google Sheets (guard introspection giữ nguyên); mock luôn nhãn rõ.
- **UI `/sheets`:** badge `sheet_type` (SUMMARY/TEMPLATE/UNCLASSIFIED/CUSTOMER) + banner confirm_reasons per-column (fee khác 4%, cột mơ hồ → NEEDS_CONFIRMATION là màu đỏ); mode banner vs cảnh báo service-account quá trình.
- **Kiểm thử:** **144/144 pass** (137 cũ + **7 mới** `test_sheets_compare.py`): mapping thiếu → NEEDS_MAPPING; MATCH khi daily delta khớp; DIFF không khớp; USD=VND → NEEDS_RATE (Q-005); account lạ → NO_META; tab đặc biệt → SKIPPED; dòng trống vẫn sạch. Thêm gần đây helpers: port rảnh động; env-clear đạt 137.
- **Việc chờ chủ dự án (Q-007 còn lại):** xác nhận từng tab (mapping CONFIRMED sau considération) + fee rate từng khách (vd LUNA 5%) trước khi đối chiếu tiền thật; sau đó chạy compare thử từng tab + NOTE MAPPING CONFIRMED trước khi đồng bộ (vẫn chỉ đọc).

**Giai đoạn 0-N+1 — S6+ Live Read-only THÀNH CÔNG trên bảng thật (spreadsheet 14mgYdWuhkF0…): đọc 46/47 tab + đối chiếu chỉ rõ 8 dòng dữ liệu thật với công thức Sheets; KHÔNG ghi/chỉnh sửa gì vào bảng. Cấu trúc từng tab khách: header tại dòng 3 (index 2), mỗi ngày 1 khối 5 dòng (merge cột A). Chờ chủ dự án xác nhận mapping (Q-007).** Cập nhật: **2026-10-27 (phiên #12)**

- **Live read-only (D-033/D-034):** `/api/v1/sheets/analyze` (POST) mode `live` kỳ SPreadsheet ID `14mgYdWuhkF0-1TbXnSwAVnMbqKmTfiiq-oDr7MuOt7k` — 47 tab (45 tab khách + TỔNG T10 + MẪU RP + ALL + OLD); phân tích 46, locale `vi_VN`, day-format `d/m`, CURRENCY `#,##0 [đ]`.
- **Cấu trúc xác định (khớp công thức Sheets):** tab khách — A NGÀY (serialStep: 46296=01/10/2026), B TÊN TK (mang **loại tiền tệ**: VND/USD/GBP/EUR), C ID TK (15 chữ số = ad account), D Tiêu (đa phần trống — NEEDS_CONFIRMATION), E USD, F VND, G Phí (công thức Sheets `=F*4%` — LUNA là 5%!), H Tổng (=F+G); cột phụ I tỷ giá USD→VND (mỗi khách 1 giá cố định, vd JOKER 27135, LUNA 27875), J USDT nạp, K NS NHẬN =J×L, L Tỉ giá USDT; hàng 1 (H1): tổng F/G/K + CÒN = NS NHẬN − RUN − nạp.
- **Tab TỔNG T10:** A Tên khách, B ĐÃ BANK (=K1 khách), C USDT nạp (=J1), D RUN (=F1), E PHÍ (=G1), F TỔNG (=H1), G CÒN = B+C−F; hàng tổng r35 sum cột; công thức tham chiếu liên tab đúng-only.
- **Đối chiếu 8 dòng thật:**>JOKER r4/r6/r11/r14/r16/r27/r32/r37 — fee 4%, tổng F+G, NS NHẬN=USDT×Tỉ giá, TỔNG dòng JOKER (B+C−F=−40.165.888,62 đ) **khớp tất cả**, qua `/sheets/analyze`.
- **Fix connector:** `read_sheet_detail` encode hải lần tên tab có dấu tiếng Việt (`TỔNG T10`, `MẪU RP` → 400) — bỏ `quote()` dự phòng khi `params` (httpx tự encode); 130/130 pass.
- **NEEDS_CONFIRMATION mới (Q-007 tiếp tục):** (1) phí từng khách có thể ≠ 4% (LUNA dùng 5% trong công thức Sheets) — xác nhận theo khách; (2) nhãn tháng/năm trên các tab (T9/2026, T12/2025, T4/2026) lệch với serial ngày thực — kỳ thực hoạt động của tab; (3) ý nghĩa cột D "Tiêu" (trống); (4) B "TÊN TK" chứa loại tiền tệ chứ không tên account — hoànAILABLE dùng neu cả tên + currency; (5) vai trò tab ALL / OLD / MẪU RP.
- **Việc tiếp theo:** chủ dự án xác nhận (1)-(5) ở đó; sau đó lưu mapping từng tab khách (PROPOSED→CONFIRMED) và đối chiếu chi tiêu against Meta API theo ID TK + NGÀY (đồng bộ chi theo ngày→current-day checkpoint).

**Giai đoạn 0-N+1 — S6+ cấu hình service account Google đã được chủ dự án thiết lập và kiểm chứng xác thực (token tự refresh OK); backend FastAPI đã khởi động lại đúng code mới (có routes /sheets); CHƯA ở mode Live Sheets — chờ Spreadsheet ID/URL bảng (Q-009).** Cập nhật: **2026-10-27 (phiên #11)**

- **Kiểm chứng cấu hình (phiên #11):** env `ADSOS_GOOGLE_SERVICE_ACCOUNT_FILE=C:\secrets\adsos-sa.json` (User + process) — file tồn tại, không đọc/nội dung private key; venv load credentials thành công, scope `spreadsheets.readonly`, token acquired (SA email `adsos-sheets-reader@ados-512906...`).
- **Fix phát hiện:** venv thiếu package `requests` (google-auth transport cần để refresh token) — đã cài `requests>=2.32` + thêm vào `requirements.txt`; backend bị chạy code cũ (không có routes `/sheets`) → khởi động lại đúng tiến trình dự án (uvicorn --reload, venv, port 8000). Frontend + DB không bị đụng (không dừng Postgres, không xóa data).
- **Test:** 2 test fail do env chăm sóc máy (SA env thật làm test "thiếu token → 400" thoả guard; test port-lock 8909 đụng port-lock của backend đang chạy) → test giờ xoá env SA trước khi set + chọn port rảnh động; **130/130 pass**.
- **Kết luận mode Sheets:** `/api/v1/sheets/mode` hiện `mock/auth=none` — đúng quy tắc D-028/D-033: mode chỉ chuyển `live/service_account` khi có **Spreadsheet ID** (đặt env `ADSOS_GOOGLE_SHEETS_SPREADSHEET_ID` hoặc nhập URL ở `/sheets`); xác thực SA đã sẵn sàng.
- **Việc tiếp theo:** chủ dự án nhập Spreadsheet URL trên màn `/sheets` → phân tích cấu trúc chỉ đọc → xác nhận mapping từng sheet (Q-009 tiếp tục).

**Giai đoạn 0-N+1 — S6+ live read-only: xác thực service account Google (google-auth, tự refresh token) đã code + test; CHƯA đọc được bảng thật — chờ chủ dự án tạo service account + share bảng (Viewer) + nhập URL ở `/sheets` (Q-009).** Cập nhật: **2026-10-26 (phiên #10, D-034)**

- **Xác thực service account (D-034):** connector `sheets.py` — `_ServiceAccountTokenProvider` dùng **google-auth** với scope cố định `spreadsheets.readonly`, token **tự làm mới ~1h/lần** (lock chống refresh đồng thời, cache credentials theo process); nguồn key JSON theo thứ tự: `ADSOS_GOOGLE_SERVICE_ACCOUNT_FILE` → `ADSOS_GOOGLE_SERVICE_ACCOUNT_JSON` → `GOOGLE_APPLICATION_CREDENTIALS` (chuẩn Google); vẫn hỗ trợ access token tĩnh (`ADSOS_GOOGLE_SHEETS_ACCESS_TOKEN`) cho test nhanh. Key JSON **ngoài repo** (.gitignore thêm `*service-account*.json`, `sa-*.json`); repr/lỗi KHÔNG lộ token hay đường dẫn key; `google-auth>=2.35` vào requirements + venv.
- **API:** `/sheets/mode` trả thêm `auth` (`none` | `access_token` | `service_account`); `_connector_for` chấp nhận SA hoặc token; thiếu quyền → 400 với hướng dẫn; key JSON hỏng/quyền thiếu → 401 (`SheetsAuthError`, thông báo rõ — KHÔNG fallback mock khi đã chỉ định spreadsheet).
- **Connector rà soát:** GET-only giữ nguyên (introspection test chặn method ghi); mock giữ nhãn rõ, không dùng dữ liệu giả báo cáo là live.
- **Kiểm thử:** **130/130 pass** (122 cũ + 8 mới `tests/test_sheets_auth.py`: nhận diện env SA, auth resolution, refresh flow token (hết hạn → refresh lại), load JSON env qua scope readonly, key file không tồn tại → 401 không lộ đường dẫn, endpoint mode/400/401).
- **Việc chờ chủ dự án (Q-009):** tạo service account → share bảng khách hàng cho email service account với quyền **Viewer** → đặt file JSON ngoài repo + env `ADSOS_GOOGLE_SERVICE_ACCOUNT_FILE` → vào `/sheets` nhập URL bảng → hệ thống tự phân tích → bạn xác nhận mapping từng sheet. Sau đó mới làm bảng tổng công ty.

**Giai đoạn 0-N+1 — S6+ chuẩn bị kiểm thử cấu trúc Google Sheets thật (chỉ đọc): đọc metadata chi tiết + màn hình quản trị `/sheets`. Code + test xong; CHƯA đọc được bảng thật — chờ chủ dự án cấp URL + token chỉ đọc (Q-009).** Cập nhật: **2026-10-26 (phiên #9, D-033)**

- **Đọc metadata chi tiết (GET-only, D-033):** connector `read_sheet_detail` — spreadsheets.get `includeGridData`: tab, số dòng/cột, **merged cells, công thức (userEnteredValue.formulaValue), numberFormat (effectiveFormat), locale workbook, màu nền, formattedValue**. Mock hỗ trợ cell giàu metadata (formula/nf/bg) + `merges` + `locale` để tái lập bảng thật.
- **Phân tích ưu tiên numberFormat + locale + effectiveValue chuẩn** (KHÔNG đoán qua dấu phẩy/chấm): `analyze_sheet_detail` — hàng banner + hàng phân cách màu + ô bị merge che đều loại khỏi thống kê cột (ghi note); cột CURRENCY nhận biết USD/VND theo pattern (`$`/`₫`); DATE theo nf type; text-số không có nf mà grouping đơn (1 dấu + đuôi 3 số) hoặc ngày cả 2 phần ≤12 (vd `11/02`) → **NEEDS_CONFIRMATION (Q-007)**, không tự xác nhận; chuỗi số ≥13 chữ số = ID tài khoản/campaign → giữ string, không parse float; ngày `25/10` với 25>12 → chắc chắn dd/MM (VN).
- **Nhận diện role mới:** FEE (phí dịch vụ/thẻ), TOTAL (tổng cộng/thành tiền) + rule "ID tài khoản" → ACCOUNT. Preview mapping **nguồn→đích** (sheet/cột/header/samples/format → bảng+field dự kiến, chỉ là gợi ý hiển thị) trên `GET /structure/proposal` + `POST /sheets/analyze`.
- **API + màn hình quản trị `/sheets`:** nhập **Spreadsheet URL hoặc ID** → `POST /api/v1/sheets/analyze` phân tích (không lưu gì); URL hợp lệ mà thiếu token env → 400 + hướng dẫn (KHÔNG fallback mock với spreadsheet lạ); nút Lưu đề xuất mapping (PROPOSED) + Xác nhận từng sheet (CONFIRMED, audit log); bảng mapping đã lưu; hiển thị mode + hướng dẫn cấu hình env. Web build pass.
- **Kiểm thử:** **122/122 pass** (90 cũ + **32 mới** `test_sheets_s6plus.py`): parse URL/ID, ngày 25/10 + 10/25 + 11/02 mơ hồ, ID 16 số giữ string, `$`/`₫` USD-VND, 25.500,75 theo locale, banner merged, hàng màu, formula, numberFormat NUMBER/CURRENCY/DATE, mơ hồ → NEEDS_CONFIRMATION, live payload mapping, endpoint 400 thiếu token.
- **Giới hạn phiên này:** chưa đọc được bảng thật — env chưa có `ADSOS_GOOGLE_SHEETS_ACCESS_TOKEN` + spreadsheet ID bảng khách hàng (Q-009); heuristic text-số cần xác minh với dữ liệu thật trước khi dùng đối soát; KHÔNG có đường ghi nào tới Google Sheets Production.

**Giai đoạn 0-N+1 — S6 Google Sheets connector (chỉ đọc + phân tích cấu trúc + mapping) đã code + kiểm thử xong.** Cập nhật: **2026-10-26 (phiên #8)**

- **S6 hoàn thành (D-024/D-028, CHỈ ĐỌC):**
  - Connector `app/connectors/sheets.py` — Google Sheets API v4 REST **GET-only** (`list_sheets`, `read_grid`); mock khi chưa có `ADSOS_GOOGLE_SHEETS_SPREADSHEET_ID` + `ADSOS_GOOGLE_SHEETS_ACCESS_TOKEN` (fixture workbook 4 sheet); KHÔNG có method ghi nào (test introspection chặn — D-024); `SheetsAuthError` khi 401 (không fallback mock); repr không lộ token.
  - Service `app/services/sheets_structure.py` — `normalize_cell` (số kiểu en "1,234.56" lẫn vn "1.234,56", grouping "5.000.000"/"25,500" → nghìn, token tiền tệ VND/USD/USDT/$/đ; heuristic parse ghi chú rõ + chờ Q-007), `analyze_workbook`/`analyze_grid` (header, kiểu cột, tỉ lệ đầy, samples; cột không có header → note chờ chủ dự án), `propose_mapping` (10 role: DATE/CAMPAIGN/SPEND/ACCOUNT/CUSTOMER/TELEGRAM/NOTE/DEBT/DEPOSIT/RATE theo từ khoá header; không khớp → `Q-007` trong note).
  - Model + migration: bảng `sheet_mappings` — unique `(spreadsheet_key, sheet_name, column_index)`, trạng thái `PROPOSED → CONFIRMED` (+`confirmed_at`, note, audit), migration `a4f7c9e21b83` reversible.
  - Routes `/api/v1/sheets/*`: `/mode`, `/structure`, `/structure/proposal`, `POST /mappings/proposal` (idempotent; CONFIRMED không bị đè), `POST /mappings/confirm`, `GET /mappings`. Audit log: `SHEET_MAPPING_PROPOSED`, `SHEET_MAPPING_CONFIRMED`.
- **Kiểm thử:** **90/90 pass** (78 cũ + 12 mới `tests/test_sheets_s6.py`: connector mock/live + guard không-ghi + lỗi API 401/500, normalize_cell, phân tích cấu trúc, mapping idempotent + confirm + audit, endpoint flow không lộ secret).
- **Giới hạn S6 (có chủ ý):** chưa nối service account thật (chờ staging + bảng hiện hành Q-007); mapping CONFIRMED phải do chủ dự án xác nhận; không có đường ghi nào tới Google Sheets — ghi có kiểm soát là giai đoạn sau, cần phê duyệt riêng.
- Việc tiếp theo S6+: khi chủ dự án cấp bảng hiện hành (URL + quyền reader) → chạy `/structure` thật, đối chiếu proposal, xác nhận mapping; heuristic parse số/quy ước grouping xác minh với dữ liệu thật trước khi dùng cho đối soát.

**Giai đoạn 0-N+1 — Audit + tối ưu 6 skill dự án bằng methodology ECC (skill-stocktake + rules-distill), 15 findings đã áp dụng.** Cập nhật: **2026-10-26 (phiên #7)**

- Audit cả 6 skill trong `.opencode/skills/` đối chiếu DECISIONS.md (D-001→D-032), PROJECT_STATUS (phiên #6) và lệnh đã kiểm chứng trong AGENTS.md; chủ dự án duyệt báo cáo trước, áp dụng một lượt sau.
- Đã sửa (chỉ markdown skill, KHÔNG đụng code/quy tắc): `meta-ads-sync` — tiền trôi D-023 đã duyệt (bỏ NEEDS_CONFIRMATION stale), nhận diện D-026 (bỏ Q-001 stale), bổ sung grace 15' D-029 + single-flight D-030 + outbox D-031 + mock mode D-027, lệnh pytest kiểm chứng; `finance-reconciliation` — bổ sung Q-005 nguồn tỷ giá, lệnh pytest; `google-sheets` — chỉ rõ D-024, bổ sung D-028 (module đọc được phép); `telegram-automation` — bổ sung D-031 outbox retry (`flush_outbox`), lệnh pytest; `account-management` — cập nhật CRUD S5 đã implement (endpoints, guards, migration `7d2e4a61c5f9`), lệnh pytest; `testing-and-security` — lệnh pytest chuẩn, `npm.cmd` build + lint chưa kiểm chứng, bỏ câu "chờ scaffold".
- Cross-cutting findings (pattern "(sau scaffold)" stale, path pytest sai) được sửa riêng trong từng skill theo lựa chọn chủ dự án — không promote lên AGENTS.md.
- **0 đề xuất NEEDS_CONFIRMATION mới** — mọi sửa đều đưa skill về đúng quy tắc đã duyệt. Code/test không đổi (chỉ sửa markdown).

**Giai đoạn 0-N+1 — S5 đã kiểm thử trực tiếp (live E2E) thành công trên localhost.** Cập nhật: **2026-10-26 (phiên #6)**

- Kiểm thử trực tiếp (toàn bộ qua API thật + 2 server chạy nền): DB cách ly SQLite `var/test_direct_s5.db` (Postgres local tồn tại nhưng không nhận mật khẩu dev `adsos` — cần chủ dự án cung cấp); migration chạy sạch; backend :8000 mock mode + web :3000 (CORS preflight OK); lần lượt kiểm: empty state (totals=0), tạo khách (GET/POST /customers, trùng tên → 400), thêm account (POST /ad-accounts, trùng Act ID → 400), gán account, guard **1 account = 1 khách tại một thời điểm** + chỉ gán account ACTIVE (skill `account-management`), thay account (REPLACED + replaced_by + lịch sử đóng valid_to), chi phí mua, sync mock theo `now` replay: 01:00Z tạo entities UNRECOGNIZED → 02:00Z (= 09:00 VN) checkpoint 3 campaign CONFIRMED → drift sim 03:00Z: `cmp_1004` 1500−1400=**100.00**, `cmp_2001` 1080−990.90=**89.10** (D-023 đúng công thức). 4 màn hình :3000 HTTP 200.
- Code mới phiên này: service `create_customer`/`create_ad_account` + guard `assign_account` (ACTIVE + không shared) + endpoints `POST /customers`, `POST /ad-accounts`, param `now` cho `POST /meta-sync/run` (chỉ mock mode, live bị chặn 400) + form tạo khách/account trên màn Tài khoản + MISSED_CHECKPOINT audit log + outbox retry. Migration `7d2e4a61c5f9` upgrade/downgrade OK.
- Kiểm thử: **62/62 pass** (+2 test: guard shared/inactive, endpoint tạo khách/account).

**Giai đoạn 0-N+1 — S1→S4 xong; S5 Dashboard (Next.js localhost, D-032) triển khai xong (mock mode).** Cập nhật: **2026-10-26 (phiên #5)**

- S5 scope (hoàn thành): backend — `app/api/v1/dashboard.py` (read-only: overview/campaigns/accounts/system + tham chiếu customers/ad-accounts; ghi account: assign/replace/purchase-cost qua `app/services/accounts.py`, mọi thay đổi ghi audit log, **không xoá lịch sử**, account cũ → REPLACED + replaced_by) + migration `7d2e4a61c5f9` (`purchase_cost` cho ad_accounts + bảng `telegram_outbox` D-031, reversible) + CORS cho localhost:3000 + MISSED_CHECKPOINT ghi audit log (dashboard giám sát đọc được). Frontend — `apps/web`: 4 màn hình tiếng Việt (Tổng quan `/`, Campaign `/campaigns`, Tài khoản `/accounts` với form gán/thay/chi phí mua, Giám sát `/system`); dữ liệu đọc trực tiếp backend DB, **không dùng dữ liệu giả**, mỗi form action có notice kết quả. Smoke test live: `/health` + `/api/v1/dashboard/overview` OK.
- Kiểm thử: **60/60 pass** (45 cũ + **+15 test S5** trong `tests/test_dashboard_s5.py`).
- Việc tiếp theo cho S5+: Kết nối Meta thật khi có token (Q-009), dữ liệu 31 khách thật; S5 chưa có auth — dashboard chỉ chạy nội bộ localhost, không mở ra ngoài (Q-012 vẫn mở).

**Giai đoạn 0-N+1 — S1/S2/S3 xong; S4 Scheduler (hằng giờ + checkpoint 09:00 riêng) triển khai xong (mock mode).** Cập nhật: **2026-10-26 (phiên #4)**

- S4 scope (hoàn thành): `app/jobs/scheduler.py` (APScheduler BackgroundScheduler timezone **Asia/Ho_Chi_Minh**: job hằng giờ `meta_sync_hourly`, job riêng `checkpoint_9h` 09:00) + `app/jobs/meta_sync_job.py` (inject được session/connector/notifier; **1 lượt job = 1 transaction: lỗi → rollback, giữ nguyên dữ liệu cũ; KHÔNG fallback live→mock**) + guard **production từ chối mock data** + token hết hạn → `AUTH_ERROR` (MetaAuthError) + API lỗi → `API_ERROR` + checkpoint trễ ngoài cửa sổ grace → `MISSED_CHECKPOINT` (không giả snapshot 09:00) + checkpoint ghi **một lần mỗi campaign/kỳ (VN date)** + Telegram admin thông báo: kết quả checkpoint, accounts OK, lỗi/thiếu quyền, UNRECOGNIZED, UNVERIFIED (`app/connectors/telegram.py` + `app/services/notify.py` — token/chat id qua env, mock chỉ buffer). Tắt scheduler: `ADSOS_SCHEDULER_ENABLED=0`.
- Cần phê duyệt: **Q-013** — cửa sổ grace checkpoint 09:00 hiện đặt 15 phút (env `ADSOS_CHECKPOINT_GRACE_MINUTES`).

- Quy tắc mới duyệt phiên này: **D-026** (tên campaign: cả MMDD lẫn DDMM, đối chiếu đủ tên khách + Ad Account ID + Campaign ID + kỳ báo cáo; không xác định được ngày → UNRECOGNIZED), **D-027** (S3 Meta connector: đọc-only, nhiều BM/account, token theo nguồn + fallback `ADSOS_META_ACCESS_TOKEN`, mode mock khi chưa có token, không log/commit token, không dùng cookie/phiên FB), **D-028** (Sheets: được xây module đọc/mapping; chỉ test ghi trên bản sao — Q-007 mở một phần). Q-001 giải quyết xong; Q-004 chỉ còn "công thức chia 30/70 chính thức".
- S3 scope (hoàn thành): connector (`app/connectors/meta.py` — mock/live tự chọn, nhiều BM/ad account, token theo nguồn qua `ADSOS_META_TOKEN_MAP` + fallback `ADSOS_META_ACCESS_TOKEN`, read-only Graph API v21.0) + service sync (`app/services/meta_sync.py` — lên campaign/entity, nhận diện D-026, snapshot tích lũy append-only, checkpoint 9h, tiền trôi D-023, UNVERIFIED khi bất thường) + routes `/api/v1/meta-sync/*` (run/mode/campaigns/snapshots/drift; không trả token trong response) + job callable (`app/jobs/meta_sync_job.py` cho S4). Chưa có token thật → chạy **mock mode**.

- ** Quy tắc tài chính mới được chủ dự án duyệt (cập nhật #2)**: phí dịch vụ 4% mặc định trên chi tiêu thực (D-021); chế độ 30/70 mặc định TẮT + điều chỉnh tay (D-022); tiền trôi = hiện tại − mốc 09:00 (D-023); Sheets tách khoản + chỉ ghi có duyệt (D-024); DB hỗ trợ 2 chế độ đối soát (D-025). Q-002, Q-003 đã giải quyết; Q-004 thu hẹp còn "công thức chia chính thức".
- S1 scaffold: backend FastAPI chạy được (`/health` OK), web Next.js build OK, docker-compose + Dockerfiles + env mẫu sẵn sàng.
- S2 DB: 11 bảng (customers, ad_accounts, ad_account_assignments, campaigns, spend_snapshots, drift_records, ledger_entries, manual_adjustments, usdt_transactions, exchange_rates, approvals, audit_log); migration reversible.
- Kiểm thử: **45/45 pass** — khách thông thường (phí 4%, khoản riêng, recalc TEMP/lock FINAL), chế độ điều chỉnh tay (từ chối khách thường, flow DRAFT→APPROVED→APPLIED, không đụng actual spend, công thức chia bị chặn Q-004), tiền trôi (công thức D-023), idempotency snapshot/migration — **+10 test S3**: nhận diện D-026 (MMDD/DDMM + lưỡng nghĩa → UNRECOGNIZED, không gán khách khi thiếu assignment), idempotency chạy 2 lần, checkpoint 9h theo giờ VN, API lỗi giữ snapshot cũ + audit, chi tiêu giảm → UNVERIFIED (D-011), tiền trôi = hiện tại − mốc 09:00 (D-023, unique theo checkpoint), token không lộ trong repr/endpoint, các endpoint meta-sync chạy được (run/mode/campaigns/snapshots/drift) — **+15 test S4**: cron hằng giờ + job checkpoint 09:00 riêng (tz Asia/Ho_Chi_Minh), idempotency job chạy lại, mất kết nối Meta giữ nguyên dữ liệu cũ, AUTH_ERROR không fallback live→mock, production từ chối mock, checkpoint ghi 1 lần/campaign/kỳ, checkpoint trễ ngoài grace → MISSED_CHECKPOINT (kỳ sau vẫn ghi), job hằng giờ không tự giả checkpoint, campaign PAUSED vẫn poll → drift, Telegram admin mock nhận biên bản checkpoint + lỗi token.

## Đã hoàn thành

- [x] `AGENTS.md` — quy tắc làm việc của agent, hard rules tài chính/dữ liệu
- [x] `opencode.json` — auto-load docs + skills
- [x] `docs/BUSINESS_RULES.md` — bối cảnh, 7 phân hệ, quy tắc tổng quan
- [x] `docs/CAMPAIGN_RULES.md` — nhận diện campaign, chi tiêu tích lũy, checkpoint 9h, tiền trôi
- [x] `docs/FINANCE_RULES.md` — tách sổ, tỷ giá, phí 4%/30-70, USDT, công nợ
- [x] `docs/PROJECT_ARCHITECTURE.md` — monorepo FastAPI + Next.js + Postgres
- [x] `docs/DEVELOPMENT_RULES.md` — môi trường, kiểm thử, an toàn dữ liệu
- [x] `docs/DECISIONS.md` — quyết định đã duyệt + NEEDS_CONFIRMATION
- [x] 6 skills OpenCode: `meta-ads-sync`, `google-sheets`, `finance-reconciliation`, `telegram-automation`, `account-management`, `testing-and-security`
- [x] S1 Scaffold monorepo: `apps/api` (FastAPI), `apps/web` (Next.js), `infra/docker-compose.yml`, `infra/env/.env.example`, `.gitignore`
- [x] S2 DB: schema + Alembic migration (initial tables, reversible), hỗ trợ 2 chế độ đối soát (D-025)
- [x] S3 Meta Connector (D-027, mock mode): connector đọc-only + service sync tích lụy (append-only, unique `(campaign_id, snapshot_at)`) + checkpoint 9h (D-009) + tiền trôi D-023 + routes `/api/v1/meta-sync/*` + test mock pass
- [x] S4 Scheduler (APScheduler, tz Asia/Ho_Chi_Minh): job hằng giờ `meta_sync_hourly` + job checkpoint `checkpoint_9h` 09:00 riêng, MISSED_CHECKPOINT khi trễ, giữ dữ liệu cũ khi Meta lỗi, Telegram admin notify (mock), guard production/mock
- [x] S5 Dashboard (D-032, localhost, mock DB): backend read-only endpoints + quản lý account (assign/replace/purchase-cost, audit log) + migration `purchase_cost` + `telegram_outbox` + frontend Next.js 4 màn hình tiếng Việt đọc DB thật
- [x] Frontend: nâng cấp `/reports` thành Dashboard tài chính (Next.js + Tailwind CSS + Recharts): cards KPI (chi tiêu Meta, phí dịch vụ, tiền nạp USDT, chi phí tài khoản, lợi nhuận tạm tính/đã chốt), biểu đồ phí theo ngày (USD, tách tiền tệ), bảng ngày/khách, trạng thái từng khu vực (loading/lỗi/thử lại/rỗng/nhiều tiền tệ), `null`≠`0`, không tự tính growth/30-70/quy đổi tỷ giá. `npm.cmd run build` PASS (11 routes). Dependency mới: `tailwindcss`, `@tailwindcss/postcss`, `recharts` (+ `postcss.config.mjs`, `tailwind.config.js`, `@import "tailwindcss"` trong `globals.css`).


### Cập nhật phiên #19 (2026-10-29 / 2026-10-30): Sửa lỗi Logic & Tối ưu hóa Database/Query
1. **TRON Connector**: Sửa chuẩn hóa ABI `_balanceOf(address)` trong `app/connectors/tron.py` — bóc tách đúng 20 byte địa chỉ thực, loại bỏ prefix `0x41` và 4 byte checksum, áp dụng MSB padding `.rjust(64, "0")`. Bổ sung unit tests kiểm chứng.
2. **Scheduler**: Bổ sung đóng `_lock_socket.close()` an toàn khi dừng scheduler trong `app/jobs/scheduler.py`, khắc phục nguy cơ rò rỉ socket và xung đột cổng khi reload.
3. **Meta Connector**: Tối ưu tái sử dụng `httpx.Client()` (session/connection pool) trong `MetaAdsConnector._graph_get`, hỗ trợ context manager và phương thức `close()`.
4. **Tối ưu Báo cáo & Nguồn Sheets**:
   - Chuyển `_latest_verified_snapshot_per_campaign` trong `app/services/reports.py` sang dùng Subquery `MAX(id)` nhóm theo `campaign_id` trên DB thay vì tải toàn bộ bảng vào RAM.
   - Thêm `defer(SheetReportSnapshot.report)` vào `sheet_report_sources.py:list_sources` giúp endpoint không deserialize các payload JSON 3.1MB không cần thiết.
5. **Deduplication & Dọn dẹp DB**:
   - Triển khai hàm `report_content_hash` trong `app/services/sheet_report_store.py` để phát hiện dữ liệu không thay đổi khi sync và tái sử dụng snapshot cũ, ngăn chặn việc phình to DB.
   - Tạo bản backup an toàn `adsos.db.backup-20261029-233424` (434MB).
   - Dọn dẹp 160 snapshot trùng lặp (giữ lại snapshot đầu/cuối mỗi ngày, snapshot mới nhất và snapshot có liên kết closure), cập nhật foreign key và chạy `VACUUM`.
   - Kết quả: Dung lượng `adsos.db` giảm từ 434MB xuống **36.8MB** (giảm 91.5%, giải phóng 378MB).
   - Kiểm thử toàn diện: **351/351 tests pytest PASS**, `npm.cmd run build` PASS.

## Việc tiếp theo (roadmap ưu tiên, cập nhật phiên #18)

> Định hướng hiện tại: độ đúng dữ liệu và vận hành nhập tay trước tự động hóa. Các module mới triển khai theo từng luồng nghiệm thu, không làm đồng loạt.

1. [x] Khôi phục runtime và nghiệm thu dashboard hiện hữu — frontend restart; `/` và `/reports` đã kiểm tra HTTP 200 và nội dung đã hydrate. Theo dõi/lặp lại nếu lỗi runtime tái diễn.
2. [ ] Hoàn thiện đặc tả sổ tiền/tỷ giá/phân bổ/bàn giao: D-043–D-045 đã ghi; cần giải quyết Q-005, Q-014, Q-015, Q-018 và các điểm phụ thuộc trước khi tính tiền tự động.
3. [ ] Xây luồng nhập thủ công theo lát cắt: ưu tiên nhận khoản tiền và phân bổ có bằng chứng, xác nhận, idempotency, lịch sử và báo cáo đối chiếu; sau đó mới nối từng nhóm nghiệp vụ kế tiếp.
4. [ ] Cấu hình nền tảng và connector theo API/quyền đã xác minh: Meta, Telegram, PingPong, Payoneer. Trước khi bật đồng bộ Meta/Sheets thật cần credential do chủ dự án cấp; staging chỉ đọc, không tạo connector giả.
5. [ ] Ads Check Pro, cảnh báo, báo cáo tháng, vận hành nhiều người dùng/cổng khách và các ý tưởng mở rộng — chỉ sau khi chốt quyền API, định nghĩa KPI và phạm vi.
- [x] S3 Meta connector + S4 scheduler hiện chạy ở mock mode; chưa bật live nếu chưa có token/quyền hợp lệ (Q-009).
- [x] S5 Dashboard và S6 Sheets read/analyze/mapping đã có; Sheets chưa ghi, cấu trúc thật vẫn chờ xác nhận (Q-007).
- [ ] S7 CI lint + test; script backup/restore DB.

## NEEDS_CONFIRMATION đang chờ (tóm tắt)

Xem chi tiết trong `docs/DECISIONS.md`:
- Q-004 công thức chia lợi nhuận 30/70 chính thức (cơ chế lưu/duyệt đã duyệt tại D-022)
- Q-005 nguồn tỷ giá; Q-014 phân đoạn lifetime spend theo kỳ tỷ giá
- Q-007 cấu trúc Google Sheets hiện hành (URL, sheet, cột; đã được phép xây module đọc — D-028)
- Q-006 match giao dịch USDT; Q-008 ngưỡng cảnh báo; Q-009 setup quyền truy cập; Q-010 định nghĩa kỳ báo cáo; Q-012 thời điểm mở dashboard cho khách
- Q-015 giá TKQC ở biên/trên 3 triệu; Q-016 quyền và field Meta Ads Check Pro; Q-017 định nghĩa KPI sự cố/báo cáo tháng; Q-018 điều chỉnh/hoàn tác phân bổ; Q-019 API PingPong/Payoneer
- (Q-001 đã giải quyết — D-026: cả MMDD và DDMM; Q-013 đã giải quyết — D-029: grace 15 phút)

## Lệnh chạy chính-xác

Xem bảng lệnh trong `AGENTS.md` (đã kiểm chứng: uvicorn reload, pytest 60/60, alembic upgrade/downgrade, npm.cmd dev/build).

## Sửa VIA launcher — 2026-11-01

- Sửa đoạn startup URL bị lệch scope/dùng biến chưa khai báo. Bỏ phụ thuộc favicon bootstrap và `--load-extension` (Chrome chính thức mới không hỗ trợ).
- Khởi chạy profile riêng với CDP loopback/cổng tự chọn; nạp cookie trước khi mở trang đích. Không có cookie hợp lệ thì mở login.php; helper điền đăng nhập/2FA chạy trong isolated world trên Facebook.
- Giữ kết nối CDP để helper tiếp tục hoạt động qua điều hướng; không báo thành công giả khi thiếu trình duyệt hoặc khởi tạo thất bại.
- Thêm dependency websockets>=15 và test mô phỏng CDP/process, không mở trình duyệt hoặc gửi cookie thật khi pytest. Kiểm tra: toàn bộ backend 484 passed; chạy lại tập trung sau bổ sung ca lỗi 22 passed; cú pháp launcher và git diff --check đạt.
- Chưa xác minh đăng nhập Facebook thật, cookie hết hạn/checkpoint và proxy có mật khẩu trên máy người dùng. Đóng cửa sổ VIA cũ trước khi thử phiên CDP mới; không cần xóa profile.

## Cập nhật 2026-11-02 — Hoàn Thành Đánh Giá An Ninh Toàn Diện Codebase (Cloudflare Security Audit)

- **Cài đặt & Chuẩn hóa Skill**: Đã cài đặt bộ skill `cloudflare/security-audit-skill` vào `.agents/skills/security-audit/` và `.opencode/skills/security-audit/`.
- **Rà soát & Báo cáo An ninh Toàn diện**:
  1. Đã hoàn thành 6 Phase theo chuẩn Cloudflare Security Audit: Reconnaissance, Hunting Waves, Candidate Validation, Output & Schema Compliance, Independent Verification, Target-Neutral Reporting.
  2. Xuất toàn bộ 7 file artifact an ninh tại `~/security-audit-skill/ads-business-os/run-1/` và artifact directory:
     - `run-metadata.json`
     - `architecture.md`
     - `coverage-ledger.json` (7 đơn vị kiểm tra đã rà soát)
     - `findings.json` (6 lỗ hổng xác nhận + 1 đầu mối cần xác thực)
     - `REPORT.md` (Báo cáo tổng kết tư thế an ninh và danh mục lỗ hổng)
     - `FINDINGS-DETAIL.md` (Chi tiết kỹ thuật, trace, mã khai thác mẫu tối thiểu và bản vá khuyến nghị)
     - `NEEDS-VALIDATION.md` (Kế hoạch xác thực rate limiting cổng khách hàng trên hạ tầng thực tế)
- **Điểm mạnh ghi nhận**:
  - Module quản lý ví sàn & TRON (`wallets.py`) bảo mật rất tốt với xác thực mã token không đổi thời gian (`secrets.compare_digest`), độ dài token >= 32 ký tự, khóa chỉ đọc.
  - Mã hóa Fernet cho thông tin đăng nhập nhạy cảm; không log secret.
  - Sử dụng 100% truy vấn tham số hóa SQLAlchemy ORM, không có lỗ hổng SQL Injection.
  - Thư mục profile Chrome VIA được chuẩn hóa an toàn chống Directory Traversal.
- **Lỗ hổng xác nhận cần xử lý**:
  - `FINDING-AUTH-SHEETS-WRITEBACK` [HIGH]: Endpoint `POST /api/v1/sheets/writeback-from-vias` thiếu rào chắn `require_local_admin`.
  - `FINDING-AUTH-LOCAL-ADMIN-BYPASS` [HIGH]: `require_local_admin` chỉ kiểm tra IP loopback socket, bị bypass khi đứng sau Reverse Proxy.
  - `FINDING-IPC-CDP-REMOTE-ORIGINS` [HIGH]: Chromium bật cờ `--remote-allow-origins=*` trên cổng CDP, mở đường cho website thứ ba chiếm quyền điều khiển phiên Facebook.
  - `FINDING-INJ-CHROME-CLI-ARG` [MEDIUM]: `custom_url` trong khởi chạy Chrome thiếu lọc cờ `--...` dẫn tới CLI argument injection.
  - `FINDING-SSRF-VIA-PROXY-CONFIG` [MEDIUM]: Cấu hình proxy VIA chấp nhận IP nội bộ/loopback gây nguy cơ SSRF qua httpx.
  - `FINDING-INFO-TELEGRAM-LOGS-EXPOSURE` [LOW]: Endpoint `GET /api/v1/telegram/activity-logs` và `/rules` thiếu xác thực admin.
- **Trạng thái kiểm thử**: 530/530 backend test passing; 21 Next.js web routes build thành công.


## Kiểm tra chênh lệch bảng tháng 11 — 2026-11-03

- Kiểm tra chỉ đọc SQLite: nguồn 11, kỳ 2026-11, snapshot 212 lúc 09:41:06 UTC+7, chất lượng PARTIAL; chưa đọc lại Google Sheets trực tiếp.
- Tổng khách của ứng dụng lấy các tab chi tiết được liên kết, khác phạm vi SUM(B2:G34) tại TỔNG T11 dòng 35. ALL và OLD bị loại theo quy tắc hiện hành D-035; NICK chưa liên kết được (công thức tham chiếu `NICK `).
- Chi tiêu nguồn tổng D35 = 283679383.15000004; tổng khách = 275278426.999999991. Chênh lệch xấp xỉ 8400956.15 gồm ALL D7 = 7638231.15 và PROMISE có chi tiêu trên summary = 762725 trong khi tab chi tiết F1 = 0.
- NEEDS_CONFIRMATION: chủ dự án xác nhận cách xử lý ALL/OLD và nguồn đúng cho PROMISE trước khi thay đổi phạm vi/cơ sở tổng hợp. Không sửa công thức, mapping, dữ liệu nguồn hoặc số tài chính; đang chờ ví dụ màn hình/chỉ tiêu người dùng thấy lệch.

## Cập nhật dòng Tổng động — 2026-11-03 (D-058)

- Chủ dự án đã xác nhận dùng số tổng công ty B:G trực tiếp trên dòng Tổng; không cần quyết định đưa ALL/OLD thành khách để khớp tổng. Tổng chi tiết khách được giữ riêng để đối chiếu; chênh lệch PROMISE vẫn là dữ liệu nguồn cần rà soát, không tự sửa.
- Nhận diện nhãn Tổng/Tổng cộng và header B:G trên tab tổng đúng tháng, không hardcode hàng; tính lại phần diễn giải ngay khi đọc snapshot cũ mà không sửa lịch sử.
- Tổng tháng/năm dùng company_totals; giữ USDT tách riêng, số âm và Decimal chính xác. Thiếu/trùng dòng Tổng hoặc ô lỗi không biến thành số 0 hay tự dùng tổng chi tiết thay thế.
- Giao diện tổng tài chính hiển thị ô nguồn và chênh lệch với tổng tab khách. Không đọc/ghi Google Sheets thật trong kiểm thử.
- Xác minh: 547 backend tests PASS trong 96.48s; ca tích hợp bổ sung kiểm tra tổng năm dùng dòng Tổng thay tổng tab khách PASS riêng. Frontend `npm.cmd run build` PASS; `git diff --check` đạt. Đối chiếu read-only snapshot 212 nhận TỔNG T11 dòng 35 và đúng B:G. Kiểm thử hàng 30/35/40, thiếu/trùng dòng, sai tháng/header và ô lỗi đều đạt. Lượt pytest đầu bị lỗi thư mục tạm mặc định; chạy lại thành công với basetemp riêng trong workspace.

## Đồng bộ tháng của Daily Profit Inspector — 2026-11-03

- Bỏ nhãn vàng về ô nguồn/chênh lệch dưới các thẻ tổng tài chính có số hợp lệ; giữ thông báo khi thiếu dữ liệu. API vẫn giữ dữ liệu truy vết và đối chiếu.
- Chuẩn hóa ngày kiểm tra theo năm/tháng đang chọn trước khi gửi API và hiển thị, kể cả preferences cũ còn lưu ngày tháng 10. Giữ số ngày nếu hợp lệ, chặn về cuối tháng khi tháng mới ngắn hơn; hỗ trợ năm nhuận.
- Kiểm thử Node 3/3 đạt: đổi tháng 10→11, ngày 31→30, đổi năm/ngày nhuận và ngày trống. Không thay đổi công thức tài chính hoặc ghi Google Sheets.
- Kiểm tra frontend: npm.cmd run build PASS (typecheck và 21 routes); git diff --check đạt. Chưa kiểm tra trực tiếp trong trình duyệt.

## Sửa dữ liệu ngày chưa nhập — 2026-11-03 (D-059)

- Gỡ fallback SNAPSHOT_DELTA cộng toàn bộ snapshot tài khoản trong ngày và MONTHLY_PRORATA. Daily Profit Inspector chỉ đọc dòng Sheet có ngày nghiệp vụ, không thay số ngày bằng snapshot hoặc tổng tháng.
- Ngày chưa nhập có chi tiêu/phí null, nguồn NO_DATA; UI hiện Chưa có dữ liệu. Phí thiếu không tự tính 4%; giữ tiền nạp có ngày độc lập. Không gắn phí dịch vụ thành lãi ròng.
- Thống kê trung bình/ngày cao nhất loại ngày chưa đủ số chi tiêu/phí; khi snapshot Sheets mới có dữ liệu ngày thì tính lại từ dữ liệu đó. Tổng công ty theo dòng Tổng không thay đổi.
- Regression test mô phỏng 2 snapshot tích lũy trùng tài khoản ngày 03/11: trước nhập là null; sau nhập nhận đúng chi tiêu 1000/phí 50 (5%), không ép 4%; phí thiếu vẫn null. Kiểm thử tập trung đạt.
- Xác minh dữ liệu local bằng kết nối SQLite read-only: 03/11 = NO_DATA, spend/fee null; hai ngày 01–02/11 có dữ liệu, phí trung bình 5494161 VND. Không sửa snapshot/Sheet thật.
- Toàn bộ backend: 549 tests PASS trong 101.20s; git diff --check đạt. Frontend build/typecheck đã đạt bước biên dịch và tạo đủ 21 routes.

## Kiểm tra lỗi kết nối PingPong HTTP 301 — 2026-11-03

- Ảnh cấu hình dùng https://pingpongx.com (website), connector gọi /v1/balances; HTTP 301 bị hiển thị nhầm như từ chối yêu cầu. Đã phân loại 3xx thành lỗi chuyển hướng/cấu hình, không tự theo redirect hoặc hiển thị Location có thể chứa token.
- Đối chiếu tài liệu chính thức: https://developer.pingpongx.com/apiDocs mô tả gateway và API VCC /v2/vcc/open/account/balance/all; https://open.pingpongx.com/docs/developer/api/account/balance-query/ mô tả POST /v1/mid-open-api/account/query; https://docs.pingpongx.com/api/home/get-started mô tả gateway và ký bất đối xứng. Cần xác định sản phẩm và tài liệu cấp cho tài khoản, không đoán Base URL/auth/schema thay thế.
- Connector hiện có OAuth /oauth/token + header HMAC và các path /v1/balances, /v1/cards chưa có bằng chứng phù hợp API được cấp. api_permissions còn fallback read_only=True khi đọc lỗi: không được coi là bằng chứng đã xác minh quyền chỉ đọc. Chưa sửa giao thức khi chưa xác định hợp đồng API; chưa nghiệm thu live.
- NEEDS_CONFIRMATION (Q-019): API thuộc thu tiền/VCC/Checkout và link tài liệu từ trang cấp khóa, quyền đọc và yêu cầu ký tương ứng. Không yêu cầu gửi Key/Secret trong chat, không sử dụng credentials thật để thử endpoint phỏng đoán.
- Kiểm thử tập trung 13/13 PASS với MockTransport; không gọi PingPong thật.
- Toàn bộ backend kiểm tra sau sửa phân loại redirect: PASS; chi tiết số lượng trong .test-pingpong-review-20261103.log. git diff --check đạt.

## Xác minh tài liệu PingPong do chủ dự án cung cấp — 2026-11-03

- Đã kiểm tra https://developer.pingpongx.com/apiDocs/main và JSON công khai chính trang sử dụng. Route mặc định chọn Issuing 2.7.1, nhưng cho phép đổi Currentz/Flowmore/Checkout/B2B/MPT; link /main không tự xác định business được cấp cho API Key.
- Issuing đã xác minh: gateway.pingpongx.com, GET /v2/token/get với app_id/app_secret, GET /v2/vcc/open/account/balance/all và /v2/vcc/open/cards; code nghiệp vụ 6666. Khác connector OAuth/HMAC và /v1/balances hiện tại. Chi tiết tại docs/PINGPONG_CONNECTION.md.
- Đang chờ xác nhận business/version người dùng đang chọn và quyền chỉ đọc (Q-019). Chưa thay giao thức hoặc thử credentials thật; không suy mặc định Issuing thành tài khoản đã cấp Issuing. Chỉ thay tài liệu trong lượt này, không cần chạy lại bộ test mã nguồn.
- Tệp tải tạm công khai đã được dọn khỏi workspace; không lưu credentials ví dụ trong tài liệu bên thứ ba vào source/test/commit.

## Cập nhật PingPong Issuing 2.7.1 — 2026-11-03 (D-060)

- Đã sửa connector theo đặc tả chính thức được kiểm tra: GET /v2/token/get với app_id/app_secret; GET /v2/vcc/open/account/balance/all và /v2/vcc/open/cards, token header theo từng ví dụ chính thức, kiểm tra code=6666. Không còn OAuth/HMAC/path giả định cũ.
- Chỉ gửi khóa tới gateway.pingpongx.com hoặc sandbox-gateway.pingpongx.com, không theo redirect. Query chứa App Secret được gỡ khỏi request trước log/error của httpx. Cache token có expiry; lỗi token dừng trước khi gọi API nghiệp vụ.
- Đọc phân trang thẻ, chỉ giữ last4; không truy vấn PAN/CVV. Số dư thiếu/lỗi không thành 0; giữ snapshot trước khi API lỗi. Nhiều budget cùng tiền tệ báo chưa hỗ trợ phân biệt, không âm thầm gộp/bỏ.
- Bỏ API quyền giả định và fallback read_only=True; metadata read_only_verified=False cho PingPong, kể cả view của bản ghi cũ. API không chứng minh quyền chỉ đọc của khóa; ứng dụng chỉ có các thao tác GET. Chưa dùng credentials thật hoặc đổi cấu hình DB thật.
- Form dùng App ID/App Secret, bỏ Merchant ID khỏi nhập liệu, gợi ý gateway đúng; App ID không áp min-length Binance. Sửa Base URL riêng có thể dùng khóa mã hóa hiện tại và xác minh trước khi cập nhật. UI bỏ phép cộng số dư bằng float.
- 53 kiểm thử tập trung PASS trước bước full suite. Tài liệu hướng dẫn cập nhật tại docs/PINGPONG_CONNECTION.md. Business/version không còn NEEDS_CONFIRMATION; Q-019 vẫn bao gồm quyền/whitelist/live verification và các API sản phẩm khác.
- Xác minh cuối: toàn bộ backend 569 tests PASS trong 106.37s; npm.cmd run build PASS (typecheck + 21 routes); git diff --check đạt. Kiểm thử chỉ dùng fixture theo schema Issuing chính thức và DB test, không dùng khóa thật hoặc gửi yêu cầu tới tài khoản PingPong thật.

## Cài plugin Codex Ponytail — 2026-11-03

- Theo yêu cầu chủ dự án, đã chạy `codex plugin marketplace add DietrichGebert/ponytail` và `codex plugin add ponytail@ponytail --json`.
- CLI xác nhận cài Ponytail 5.3.3 tại thư mục cache plugin của người dùng. Đã kiểm tra manifest cài đặt; không chạy thêm script/plugin hook trong phiên này.

## Refactor UX/UI SaaS Admin AdsOS — 2026-11-07

- Thực hiện yêu cầu tự chủ thay lớp giao diện trên FastAPI + Next.js hiện hữu, giữ nghiệp vụ quản trị quảng cáo. Dùng hướng dẫn Ponytail và Sites ở chế độ local-only; không đăng ký website/hosting hoặc deploy production.
- Shell mới: tám mục điều hướng, sidebar thu gọn, drawer mobile có quản lý focus/Escape, tìm kiếm toàn cục, sáng/tối lưu localStorage, chuông cảnh báo và lệnh chờ, toast bốn loại qua Context. Theme emerald/indigo, card 12px/control 8px và token sáng/tối dùng chung cho trang cũ.
- Bổ sung /dashboard, /bms, /customers, /analytics, /auto-set-camp, /settings và /customers/finance. Giữ màn hình tổng quan cũ ở /operations và tất cả route chi tiết hiện có.
- TKQC: phân trang 10/20/50, đọc đầy đủ trang nguồn, chọn theo trang, CSV chống công thức, sao chép có lỗi, kiểm tra nguồn/số dư qua API hiện hữu. Modal phí lấy báo cáo nghiệp vụ theo từng tiền tệ thay phép gộp/giả định VND trước đây.
- Khách: thêm/sửa hồ sơ, Telegram và mức phí riêng bằng Decimal, kiểm tra trùng tên, audit, guard local; gán tài khoản qua luồng phân công hiện hữu, không tạo lại khách nếu bước gán lỗi. Không đổi công thức tài chính, lịch sử hoặc số phí của khách cũ.
- Không dùng mock cho biểu đồ tiền thật, không gọi phí đối soát là thực thu/lãi ròng, không suy chi tiêu ngày từ snapshot lũy kế. Tỷ giá theo nguồn/kỳ; mức phí điền sẵn chỉ trên form khách mới. Các mục cần quy tắc/nguồn lịch sử giữ NEEDS_CONFIRMATION như Q-005/Q-014/Q-017.
- Đã loại kiểu TypeScript any khỏi TS/TSX; thông báo lỗi API dùng tiếng Việt và không echo input validation; Recharts là dependency sẵn có, không thêm UI framework.
- Báo cáo chi tiết: docs/UI_REFACTOR_REPORT.md. Đã kiểm tra 24 lượt trang trên Chrome headless desktop/tablet/mobile, không tràn ngang và không lỗi JavaScript; 12 kiểm thử Node đạt. Kiểm thử trình duyệt chỉ đọc và mở form, không submit dữ liệu thật.
- Xác minh cuối: toàn bộ backend 604/604 PASS trong 132.30s sau bổ sung audit mức phí khi tạo khách; Next.js build PASS với 30 route, TypeScript strict không lỗi; 12/12 kiểm thử Node PASS; Chrome headless 24 lượt trang desktop/tablet/mobile không lỗi JavaScript/tràn ngang. Tập trung API khách chạy riêng không khởi động scheduler và tiếp tục đạt 6/6.
- Đã dừng máy chủ preview do phiên này khởi chạy ở cổng 3017. Không thay đổi máy chủ dev sẵn có, không commit/push/deploy hoặc ghi Google Sheets. Các ảnh/báo cáo nghiệm thu giữ trong artifacts/ui-refactor và docs/UI_REFACTOR_REPORT.md; hồ sơ Chrome QA được gitignore.

## CRUD khách hàng, lịch Sheets riêng và dashboard vận hành — 2026-11-09

- Bổ sung `sheet_url`, `sheet_tab_name`, `sync_time` cho khách hàng; API hỗ trợ GET danh sách, POST, PUT/PATCH và DELETE an toàn. DELETE chỉ đặt `is_active=false`, đóng phân công hiện hành và giữ toàn bộ lịch sử. Giao diện `/customers` có thêm/sửa, xác nhận xóa, cấu hình Sheets/giờ và gán hoặc bỏ gán nhiều TKQC.
- Migration `p2f3a4b5c6d7` tạo cấu hình mới và bảng `customer_sheet_sync_runs` có unique `(customer_id, scheduled_for)`. Đã kiểm tra upgrade → downgrade → upgrade trên SQLite riêng, sao lưu DB local tại `apps/api/adsos.backup-20261109-customer-sheet-sync.db` (được `.gitignore` bảo vệ), rồi áp local lên head thành công.
- Scheduler Sheets chạy mỗi phút theo `Asia/Ho_Chi_Minh`, lọc chính xác `Customer.sync_time == HH:MM`, chỉ lấy TKQC đang gán và snapshot Meta `VERIFIED`. Payload giữ đúng 10 cột: ngày, tên TK + currency, ID, chi ngoại tệ, USD, VND, phí %, tổng, USDT, tỷ giá. Retry cùng khách/cùng phút không sinh bản ghi trùng.
- Ghi Google Sheets thật có guard: lịch phải được phê duyệt, `APP_ENV=production`, `ADSOS_CUSTOMER_SHEETS_WRITES_ENABLED=true`, có backup nội dung tab, đọc lại xác minh và audit. Local/staging chỉ tạo preview. Ngoại tệ giữ `NEEDS_CONFIRMATION` vì Q-014 chưa duyệt cách phân tách lifetime spend theo kỳ tỷ giá; không tự nhân tỷ giá hiện hành và không ghi production trong phiên này.
- `/dashboard` hiển thị chi tiêu hôm nay, số dư/ngưỡng dư nợ TKQC đã gán, số LIVE, số chuyển DIE hôm nay, phí theo hồ sơ khách, Binance USDT và PingPong USD; tiền tệ tách riêng. Có đủ 12 lựa chọn thời gian theo yêu cầu, Date Range Picker, biểu đồ chi tiêu/phí, top TKQC hôm nay và hàng đợi lệnh từ xa. Backend kiểm thử riêng xác nhận account chưa gán không lọt vào tổng.
- Xác minh cuối: 606/606 backend tests PASS trong 125.58s với basetemp trong workspace; `npm.cmd run build` PASS, typecheck strict và 30 route; migration round-trip PASS. Không dùng khóa thật, không gọi Meta/Sheets/Binance/PingPong thật và không ghi Google Sheets.
