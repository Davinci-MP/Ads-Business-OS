# Ads Business OS — Hướng dẫn cho Copilot

## Lệnh build, kiểm thử và chạy

Các lệnh dưới đây dùng cho PowerShell trên Windows. Chạy từ thư mục được ghi rõ.

### Backend (`apps/api`)

```powershell
# Chạy API với chế độ tự reload
.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# Chạy toàn bộ test backend
.venv\Scripts\python.exe -m pytest -q tests

# Chạy một file test
.venv\Scripts\python.exe -m pytest -q tests\test_meta_sync.py

# Chạy một test theo tên hoặc biểu thức lọc
.venv\Scripts\python.exe -m pytest -q tests\test_meta_sync.py -k "idempotency"

# Chạy migration (mặc định dùng SQLite; đặt ADSOS_DATABASE_URL nếu dùng PostgreSQL)
.venv\Scripts\python.exe -m alembic upgrade head
```

Fixture của backend test tạo một cơ sở dữ liệu SQLite tạm thời và chạy migration. Production dùng PostgreSQL. Hiện repository chưa có lệnh lint hoặc kiểm tra kiểu riêng cho backend.

### Frontend (`apps/web`)

```powershell
# Chạy Next.js ở chế độ phát triển
npm.cmd run dev

# Tạo bản build production
npm.cmd run build

# Chạy bản build production
npm.cmd run start
```

PowerShell có thể ưu tiên `npm.ps1`; hãy dùng `npm.cmd` như các lệnh trên.

### Chạy toàn bộ stack local

Từ thư mục gốc repository:

```powershell
docker compose --env-file env\.env.example up
```

File compose nằm tại [`infra/docker-compose.yml`](../infra/docker-compose.yml). Không dùng credential production hoặc integration có quyền ghi dữ liệu thật khi phát triển local.

## Kiến trúc

Đây là monorepo gồm backend FastAPI và dashboard Next.js:

- [`apps/api/app/main.py`](../apps/api/app/main.py) khởi tạo FastAPI, cấu hình CORS cho local, đăng ký các router versioned và khởi động scheduler tùy chọn thông qua lifespan.
- `app/api/v1/` chỉ chứa routing HTTP. Đặt quyết định nghiệp vụ trong `app/services/`, không đặt trong router.
- `app/services/` triển khai nhận diện campaign, đồng bộ Meta, báo cáo, đối chiếu thủ công, tài chính và so sánh Sheets. Service làm việc với SQLAlchemy session và không trả về HTTP response.
- `app/connectors/` cô lập các hệ thống bên ngoài (Meta, Google Sheets, Telegram và các integration thanh toán tương lai). Đặt logic API bên ngoài và xác thực tại đây; dùng chế độ mock/read-only khi giai đoạn hiện tại yêu cầu.
- `app/models/` là lớp persistence; các migration Alembic trong `apps/api/alembic/` là lịch sử schema. Mọi migration phải có cả `upgrade` và `downgrade`.
- `app/jobs/` chứa scheduler đồng bộ Meta theo giờ và checkpoint. Job phải an toàn khi retry và không chạy trùng khi có nhiều worker hoặc trigger chồng lấn.
- [`apps/web/app/`](../apps/web/app/) là dashboard Next.js App Router. [`apps/web/lib/api.ts`](../apps/web/lib/api.ts) là client dùng chung cho REST API; giao diện web đọc backend, không đọc Google Sheets trực tiếp.
- Luồng dữ liệu dự kiến là connector đọc dữ liệu bên ngoài → job/service backend → snapshot/ledger/báo cáo trong PostgreSQL → REST API → dashboard. Google Sheets là nguồn đối soát vận hành; ghi production phải qua flow phê duyệt/audit/backup.

## Quy ước riêng của repository

### Ngôn ngữ phản hồi

- Khi người dùng viết tiếng Việt hoặc sử dụng `/init`, trả kết quả bằng tiếng Việt.
- Giữ nguyên tên biến, tên hàm, lệnh, đường dẫn, mã trạng thái và định danh kỹ thuật bằng ngôn ngữ gốc khi cần để có thể copy/chạy chính xác.

### Quy tắc nguồn sự thật và trình tự thay đổi

Trước khi thay đổi hành vi, đọc tài liệu phù hợp:

- [`docs/BUSINESS_RULES.md`](../docs/BUSINESS_RULES.md) — bối cảnh và bảy phân hệ.
- [`docs/CAMPAIGN_RULES.md`](../docs/CAMPAIGN_RULES.md) — nhận diện campaign, múi giờ account, chi tiêu tích lũy, checkpoint 09:00 và tiền trôi.
- [`docs/FINANCE_RULES.md`](../docs/FINANCE_RULES.md) — phí, tiền tệ, đối soát, USDT, công nợ và phê duyệt.
- [`docs/PROJECT_ARCHITECTURE.md`](../docs/PROJECT_ARCHITECTURE.md) — ranh giới module, luồng dữ liệu, môi trường và khôi phục.
- [`docs/DEVELOPMENT_RULES.md`](../docs/DEVELOPMENT_RULES.md) — an toàn môi trường, kiểm thử, migration và vận hành.
- [`docs/DECISIONS.md`](../docs/DECISIONS.md) — công thức đã duyệt và các mục còn `NEEDS_CONFIRMATION`.
- [`docs/PROJECT_STATUS.md`](../docs/PROJECT_STATUS.md) — trạng thái triển khai và giới hạn đã biết.

`AGENTS.md` cũng là hướng dẫn của repository và phải nhất quán với file này. Không tự đặt công thức tài chính hoặc quy tắc đối soát. Nếu yêu cầu chưa được quyết định, giữ nguyên hành vi hiện tại, gắn nhãn `NEEDS_CONFIRMATION` và hỏi chủ dự án thay vì tự quyết định.

### Toàn vẹn dữ liệu

- Chi tiêu Meta là tổng tích lũy từ khi campaign bắt đầu. Lưu mỗi lần lấy dữ liệu thành snapshot append-only và hiển thị snapshot VERIFIED mới nhất; không cộng các snapshot cũ với nhau.
- Chống ghi trùng bằng unique constraint ở database, không chỉ kiểm tra tại application. Retry của job và connector không được tạo snapshot, drift record, observation hoặc giao dịch TRON trùng.
- Nếu response API thiếu, lỗi, mơ hồ hoặc làm giảm giá trị tích lũy đã VERIFIED, giữ nguyên giá trị VERIFIED, ghi trạng thái lỗi/chưa xác minh và báo rõ vấn đề. Không thay dữ liệu đã xác nhận bằng `0` hoặc fallback giống như thành công.
- Giữ lịch sử campaign, account, assignment, snapshot và transaction. Đổi trạng thái account thành replaced/restricted/dead thay vì xóa lịch sử.
- Giữ riêng từng loại tiền tệ trong báo cáo và ledger. Không quy đổi hoặc cộng chéo tiền tệ nếu chưa có tỷ giá và quy tắc được duyệt.
- Observation đối chiếu thủ công là append-only và idempotent. Observation đến muộn vẫn được lưu nhưng không ghi đè observation hiện hành mới hơn. Đối chiếu thủ công không bao giờ trở thành snapshot Meta VERIFIED hoặc checkpoint 09:00.
- Dùng `Decimal` cho phép tính tiền và quy tắc `ROUND_HALF_UP` của repository; không dùng float nhị phân hoặc phép làm tròn banker của Python cho tiền.

### An toàn integration và môi trường

- Secret và token lấy từ biến môi trường `ADSOS_*` hoặc file secret bên ngoài. Không đưa chúng vào source, test, log, commit hoặc nội dung hội thoại.
- Local/test có thể dùng SQLite và connector mock. Staging chỉ đọc dữ liệu bên ngoài thật và không được ghi Sheet vận hành. Thao tác production cần phê duyệt rõ ràng, audit log và backup; không tự deploy hoặc ghi production.
- Giữ nguyên cấu trúc, công thức và mapping cột Google Sheets nếu chưa được chủ dự án phê duyệt. Module Sheets hiện thiên về đọc/phân tích/đối chiếu.
- Truy vấn khoảng thời gian theo múi giờ của từng ad account trên Meta; checkpoint của scheduler dùng `Asia/Ho_Chi_Minh`. Campaign `PAUSED`/`ENDED` hoặc thuộc account đã thay thế vẫn có thể cần cho tiền trôi và đối soát lịch sử.
- Chỉ xác nhận quyền sở hữu campaign khi campaign ID, tên campaign/mã ngày, customer/account được gán và kỳ báo cáo đều khớp. Mã ngày mơ hồ phải giữ ở trạng thái chưa nhận diện.

### Kiểm chứng và bàn giao

Khi thay đổi hành vi, thêm hoặc cập nhật test pytest nhỏ nhất phù hợp, bao gồm idempotency và giữ nguyên dữ liệu khi lỗi nếu có liên quan. Chạy test tập trung trước, sau đó chạy toàn bộ backend test và web build khi thay đổi ảnh hưởng đến các phần đó. Kết thúc phiên, cập nhật [`docs/PROJECT_STATUS.md`](../docs/PROJECT_STATUS.md); chỉ cập nhật [`docs/DECISIONS.md`](../docs/DECISIONS.md) khi chủ dự án đã phê duyệt quyết định.

### Kiểm tra an toàn bắt buộc trước mỗi lần push

1. **Chặn database backup.** Không stage, commit hoặc push file khớp `*.db.backup-*`, dù file có nằm trong `.gitignore` hoặc chỉ tồn tại trong lịch sử local. Kiểm tra cả worktree/index bằng `git status --short`, diff staged, và các commit chưa push. Nếu phát hiện file đã bị commit, phải loại nó khỏi lịch sử trước khi push thay vì bỏ qua cảnh báo size/file hook của GitHub.
2. **Bảo vệ cấu hình Facebook extension.** Mọi thay đổi trong `extensions/adsos-check-bridge/manifest.json` phải được đối chiếu trực tiếp với `HEAD`. Không xóa hoặc làm suy giảm:
   - `content_scripts` cho `fb-opt-main.js` ở `world: "MAIN"` và `fb-opt-relay.js` ở isolated world trên `*://*.facebook.com/*` và `*://*.messenger.com/*`;
   - `web_accessible_resources` cho `fb-opt-main.js`, `fb-opt-relay.js`, `bridge-main.js`, và `bridge-main.js` trên localhost/127.0.0.1;
   - các `permissions`/`host_permissions` cần cho hành vi extension hiện tại.
   Chỉ cho phép thay đổi có chủ ý rõ ràng, chấp thuận của chủ dự án và kiểm thử extension tương ứng. Manifest phải vẫn là JSON hợp lệ.
3. **Đối chiếu quy tắc kinh doanh.** Khi `docs/BUSINESS_RULES.md` thay đổi, đối chiếu từng thay đổi liên quan với `docs/DECISIONS.md`, ưu tiên các quyết định đã duyệt D-021 và D-041 đến D-045. Không xóa, đảo nghĩa hoặc làm yếu quy tắc đã duyệt; quyết định mới/chỉnh sửa yêu cầu phê duyệt rõ ràng của chủ dự án trước khi cập nhật `DECISIONS.md`.
4. **Build trước khi push.** Luôn chạy `npm.cmd run build` trong `apps/web` và chỉ được push khi mã thoát thành công, kể cả khi thay đổi chính chỉ nằm ngoài frontend. Nếu build thất bại, dừng push và báo lỗi kèm đường dẫn kết quả.
