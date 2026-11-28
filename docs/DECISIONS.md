# DECISIONS.md — Quyết định đã duyệt

> Quy tắc: thay đổi quy tắc kinh doanh/đối soát phải được **chủ dự án phê duyệt rồi mới ghi vào đây**. Agent KHÔNG TỰ sửa mục đã duyệt, KHÔNG TỰ chuyển NEEDS_CONFIRMATION thành "đã duyệt".

## Đã duyệt — 2026-10-26 (khởi tạo dự án)

| # | Quyết định |
|---|---|
| D-001 | Stack: frontend Next.js + React; backend Python FastAPI; database PostgreSQL; automation Cron/Cloud Scheduler |
| D-002 | Đang quản lý 31 khách hàng; 1 khách dùng nhiều ad account; account bị hạn chế và thay thế thường xuyên; giữ nguyên lịch sử account/campaign cũ |
| D-003 | Sử dụng nhiều Facebook cá nhân + nhiều Business Manager; khách liên hệ qua Telegram |
| D-004 | Dữ liệu chi tiêu/công nợ hiện quản lý bằng Google Sheets; giữ nguyên cấu trúc + công thức bảng đang vận hành |
| D-005 | Thanh toán: USDT TRC20 vào một ví chung hoặc chuyển khoản ngân hàng |
| D-006 | Tên campaign theo ngày: mã dạng `1025`, `2510` kết hợp tên khách; nhận diện theo Campaign ID + tên + khách + kỳ báo cáo |
| D-007 | Ad account thuộc nhiều múi giờ: UTC+7, UTC-7, UTC+3, UTC+5; truy vấn thời gian phải theo múi giờ account |
| D-008 | Chi tiêu lấy là tổng tích lũy từ khi campaign bắt đầu; không cộng trùng; chỉ append snapshot |
| D-009 | Lưu mốc chi tiêu buổi sáng 09:00 giờ Việt Nam; tự cập nhật tổng tích lũy mỗi giờ |
| D-010 | Theo dõi tiền trôi phát sinh sau khi campaign dừng; không xoá lịch sử |
| D-011 | Dữ liệu API lỗi/chưa chắc chắn không ghi đè số đã xác nhận; gắn cờ `UNVERIFIED` |
| D-012 | Quản lý riêng biệt: chi tiêu thực, đối soát theo hợp đồng, phí tài khoản, phí thẻ, lợi nhuận |
| D-013 | Hỗ trợ tỷ giá USDT/VND và tỷ giá thanh toán theo cấu hình |
| D-014 | Hỗ trợ công thức phí 4% và chia chênh lệch 30/70 theo thỏa thuận từng khách **— bị thay thế một phần bởi D-021 và D-022 (2026-10-26)** |
| D-015 | Theo dõi USDT TRC20 trên ví chung; không cộng tiền nạp khi chưa xác định giao dịch thuộc khách nào |
| D-016 | Mọi giao dịch có lịch sử + chống ghi trùng; hành động thanh toán tiền thật yêu cầu phê duyệt + integration có quyền hợp lệ |
| D-017 | Theo dõi công nợ + cảnh báo số dư gần hết |
| D-018 | Hệ thống chạy local (hot reload), có Local/Staging/Production; Staging đọc dữ liệu thật quyền hợp lệ nhưng không ghi bảng thật |
| D-019 | Không lưu secret trong mã nguồn; ưu tiên API chính thức + quyền hợp lệ |
| D-020 | 7 phân hệ: quản lý khách/account, sync campaign & chi tiêu, Google Sheets, USDT/công nợ, Telegram bot, phân tích, dashboard |

## Đã duyệt — 2026-10-26 (cập nhật #2: quy tắc tài chính)

| # | Quyết định |
|---|---|
| D-021 | Phí dịch vụ mặc định **4% cho khách chưa có mức riêng được xác nhận**, tính trên chi tiêu quảng cáo thực tế đã đối soát. D-043 cập nhật cơ sở tiền tệ/cách quy đổi: USD → VND theo kỳ tỷ giá, sau đó áp mức phí đã xác nhận của khách; công thức cũ trong quyết định này không được dùng để bỏ qua tỷ giá USD/VND. Phí là **khoản riêng**, không gộp vào chi tiêu Meta. Mức riêng của khách không bị ghi đè bởi mặc định. |
| D-022 | Chế độ chia lợi nhuận 30/70 là **chế độ đặc biệt, mặc định TẮT**; chỉ bật khi chủ dự án cấu hình cho khách được chọn. Số liệu điều chỉnh được chủ dự án **nhập tay**, lưu bảng riêng có nhật ký + phê duyệt; KHÔNG tự tạo/suy diễn điều chỉnh từ Meta; KHÔNG tự thay đổi chi tiêu thực; KHÔNG áp dụng cho khách thông thường; công thức chia chỉ áp dụng sau khi chủ dự án xác nhận cách tính chính thức |
| D-023 | `Tiền trôi = Chi tiêu hiện tại − Chi tiêu mốc 09:00` (giờ Việt Nam, cùng kỳ đối soát). Tiếp tục sync tích lũy mỗi giờ; mốc 09:00 cố định; chi tiêu hiện tại theo Meta mới nhất; không cộng trùng; phí 4% tính lại trên chi tiêu hiện hành; Meta điều chỉnh muộn → cập nhật khoản tạm tính, giữ lịch sử đã chốt |
| D-024 | Google Sheets: giữ nguyên công thức/cấu trúc đang vận hành; tách biệt chi tiêu thực, phí dịch vụ 4%, số liệu điều chỉnh thủ công, công nợ; không ghi bảng thật khi chưa phê duyệt; thử nghiệm chức năng mới trên bản sao; mỗi cập nhật có lịch sử + chống ghi trùng |
| D-025 | Database phải hỗ trợ **2 chế độ đối soát**: (1) khách thông thường — phí dịch vụ 4% trên chi tiêu thực; (2) khách chế độ điều chỉnh thủ công — số liệu điều chỉnh nhập tay riêng; công thức chia 30/70 chờ xác nhận chính thức |

## Đã duyệt — 2026-10-26 (cập nhật #3: campaign naming + S3 Meta connector + Sheets module đọc)

| # | Quyết định |
|---|---|
| D-026 | Nhận diện campaign (giải quyết Q-001): hỗ trợ **cả hai định dạng mã ngày MMDD và DDMM** trong tên campaign — ví dụ `1025` (MMDD) và `2510` (DDMM) đều tương ứng ngày 25/10. Phải đối chiếu đủ: **tên khách + Ad Account ID + Campaign ID + kỳ báo cáo**. KHÔNG tự ghép campaign khi: trùng tên, sai khách, hoặc không xác định được ngày (mã 4 số có 2 cách đọc hợp lệ và khác nhau → `UNRECOGNIZED` chờ xác nhận). Campaign ID chỉ được lưu gán khách **sau khi xác nhận** đủ các điều kiện trên |
| D-027 | ~~S3 Meta Connector được phê duyệt triển khai...~~ **BỊ THAY THẾ VÀ VÔ HIỆU HÓA BỞI D-065 (2026-11-10)**: Cho phép kết nối đầy đủ API Token + Session Cloud Hub (trích xuất và đồng bộ session cookie, EAAG, EAAB, fb_dtsg từ browser profile VIA được mã hóa Fernet); cho phép toàn bộ Graph API v26.0 và GraphQL read/write mutations; trạng thái campaign/boost có thể cấu hình ACTIVE hoặc PAUSED. |
| D-028 | Google Sheets (giải quyết một phần Q-007): cho phép **xây module đọc + phân tích cấu trúc bảng + cấu hình mapping**; ghi chỉ được kiểm thử trên **bản sao** Google Sheets; **KHÔNG sửa hoặc ghi vào bảng Production**. Cấu trúc thực của bảng hiện hành vẫn chờ xác nhận (Q-007 tiếp tục mở) |

## Đã duyệt — 2026-10-26 (cập nhật #4: Q-013 grace + Telegram admin + S5 dashboard)

| # | Quyết định |
|---|---|
| D-029 | Q-013 ĐÃ DUYỆT: `ADSOS_CHECKPOINT_GRACE_MINUTES = 15`. Checkpoint trong cửa sổ grace phải lưu **thời điểm lấy dữ liệu thực tế** (snapshot_at = giờ fetch thật, không gán cứng 09:00). KHÔNG dùng dữ liệu lấy sau để tạo checkpoint giả 09:00; bỏ lỡ cửa sổ → `MISSED_CHECKPOINT`, không tự tạo checkpoint giả |
| D-030 | S4 được duyệt kèm ràng buộc chống trùng lặp: 09:00 hai job cùng chạy → chạy đúng MỘT lượt fetch Meta (job sau bỏ qua khi checkpoint/sync gần nhất đã hoàn thành); single-flight lock chống chạy đồng thời cùng campaign/kỳ; scheduler 1-instance qua port-lock (nhiều uvicorn worker → chỉ 1 worker chạy scheduler); idempotency job retry giữ nguyên |
| D-031 | Telegram admin module ĐƯỢC DUYỆT: bot token + admin chat id **chỉ qua biến môi trường/Secret Manager**; không hardcode, không log secret, không gửi token vào hội thoại. Nếu Telegram lỗi, kết quả đồng bộ KHÔNG mất — lỗi gửi ghi vào outbox để gửi lại ở lần chạy sau |
| D-032 | S5 Dashboard (Next.js, chạy localhost): màn hình Tổng quan khách hàng, Campaign, Tài khoản, Giám sát hệ thống; dữ liệu lấy từ backend DB, không dùng dữ liệu giả làm dữ liệu thật; giao diện tiếng Việt; không ghi Google Sheets Production; không deploy Production |

## Đã duyệt — 2026-10-26 (cập nhật #5: S6+ kiểm thử cấu trúc Google Sheets thật — chỉ đọc)

| # | Quyết định |
|---|---|
| D-033 | S6+ kiểm thử cấu trúc Google Sheets **CHỈ ĐỌC** (mở rộng D-024/D-028): (1) giữ nguyên toàn bộ dữ liệu + công thức bảng hiện hành; (2) nhập **Spreadsheet URL hoặc ID** từ màn hình quản trị `/sheets`; (3) đọc metadata chi tiết qua `spreadsheets.get` (GET-only): tab, số dòng/cột, **merged cells, công thức, numberFormat, locale, màu nền**; (4) phân tích định dạng số **ưu tiên numberFormat + locale + effectiveValue chuẩn**, KHÔNG chỉ dựa dấu phẩy/chấm — ô dạng text-số mơ hồ (grouping đơn 1 dấu + đuôi 3 chữ số; ngày cả 2 phần ≤12) → **NEEDS_CONFIRMATION (Q-007)**, không tự xác nhận; (5) preview mapping **nguồn→đích** trên màn hình, lưu mapping chỉ sau khi chủ dự án xác nhận (PROPOSED → CONFIRMED, có audit log); (6) đọc bảng thật chỉ khi có access token **chỉ đọc** qua env (`ADSOS_GOOGLE_SHEETS_ACCESS_TOKEN`, scope `sheets.readonly` hoặc service account reader); (7) thứ tự kiểm thử: **bảng khách hàng trước, bảng tổng công ty sau**; (8) KHÔNG ghi gì vào Google Sheets Production — ghi có kiểm soát là giai đoạn riêng cần phê duyệt. Token/credentials không nằm trong mã nguồn, log hay hội thoại (Q-009) |

## Đã duyệt — 2026-10-26 (cập nhật #6: S6+ live read-only với service account)

| # | Quyết định |
|---|---|
| D-034 | S6+ **live read-only ĐƯỢC PHÊ DUYỆT** — tuyệt đối **chưa phê duyệt ghi** vào bảng đang vận hành: (1) connector bổ sung xác thực **Google service account (google-auth)**: scope cố định `https://www.googleapis.com/auth/spreadsheets.readonly`, service account được share bảng với quyền **Viewer**; access token do google-auth quản lý và **tự làm mới ~1h/lần**; vẫn hỗ trợ access token tĩnh qua env cho test nhanh; (2) key JSON service account nằm **NGOÀI repo**, trỏ qua env (`ADSOS_GOOGLE_SERVICE_ACCOUNT_FILE` hoặc `ADSOS_GOOGLE_SERVICE_ACCOUNT_JSON`, fallback chuẩn `GOOGLE_APPLICATION_CREDENTIALS`); không hardcode, không log, không commit credentials; (3) KHÔNG tạo endpoint cập nhật/xoá/thay đổi dữ liệu Google Sheets thật; (4) thứ tự kiểm thử giữ nguyên: bảng khách hàng trước, bảng tổng công ty sau — chủ dự án tự cấu hình quyền + nhập URL ở `/sheets`, mapping cần chủ dự án xác nhận từng sheet; (5) KHÔNG dùng dữ liệu giả báo cáo là đã kết nối thật — mock luôn được gắn nhãn rõ; giữ nguyên mọi quy tắc đối soát đã duyệt (D-008/D-009/D-021/D-022/D-023/D-026) |

## Đã duyệt — 2026-10-27 (cập nhật #7: Q-007 chuyển luồng Meta Campaign nghiêm ngặt + đối chiếu)

| # | Quyết định |
|---|---|
| D-035 | **KHÔNG tính chi tiêu dựa đơn thuần trên Ad Account ID + ngày Meta.** Quy trình bắt buộc theo trình tự: (1) khách hàng → ngày báo cáo → ad accounts thuộc khách trong kỳ đó (khóa: ngày + customer + ad account); (2) campaign của các accounts theo chuẩn mã ngày cả 2 dạng MMDD/DDMM (D-026) + tên khách + ngày báo cáo; (3) Campaign ID phải đúng định dạng (nếu entry không hợp lệ → không giữ/c xác nhận, cần ID đầy đủ); (4) tính chi tiêu giai đoạn đó theo từng customer/ad account/ngày báo cáo riêng — KHÔNG gộp trừ; (5) checkpoint điển hình 09:00 (grace 15' D-029) + sync hằng giờ — giao cuối ngày có thể lặp nhiều lần trong 1 ngày → tính tiền trôi = chênh lệch cột Trôi (KHÔNG tính trùng); (6) copie Sheets đối chiếu bằng Meta API nhưng đối chiếu MAPPING CONFIRMED (Q-007) mới đối chiếu, chưa đủ → NEEDS_CONFIRMATION. File workbook sẽ theo đúng cấu trúc tổng + tab khách (điều nhất cố: TỔNG T10 là bảng tông, sheet nhóm riêng cha của tổng: `SUMMARY` + `TEMPLATE` + `UNCLASSIFIED` (tab ALL / OLD) — KHÔNG tự đồng bộ dòng khách từ 3 tab này |
| D-036 | Q-007 chuyển luồng nghiêm ngặt. Chi tiêu Sheets phải so khớp theo CẶP (campaign khi được xác nhận giữa Sheets + Meta campaign đối chiếu: id khách + ngày + account + khoản Phí/Tổng/NS nhận riêng của bảng khách hàng như sau; nếu chưa khớp → NEEDS_CONFIRMATION— không tự tính tỷ giá. **الات đối chiếu mapping Q-007 đã CONFIRMED** mới chạy báo cáo so với DB; báo cáo chỉ đối chiếu chi tiêu ngày (max snapshot tích lũy cum(ngày) − cum(ngày trước), snapshot VERIFIED — D-008/D-011); sheet VND vs Meta USD → NEEDS_CONFIRMATION (chờ tỷ giá Q-005, không tự đổi tiền). Mọi báo cáo chỉ đọc — KHÔNG ghi/ngoài Sheets/DB |
| D-037 | Mapping Q-007 phải chủ dự án xác nhận rõ từng tab: bảng khách + 1 ngày khách (fusion all) — mapping được tự động + là 4 loại tab khách; mục 4: 5 tabs riêng tổng (T forms và T10 tổng + tab MẪU: TỔNG tổng). Phí theo khách: từng tab có công thức riêng (vd LUNA 5%) — mặc định giữ 4% D-021; chủ dự án xác nhận fee rate từng khách trước khi dùng cho tính tiền tự động; chưa xác nhận → ghi chú `fee_confirmed=False`, không tự tính fee |
| D-038 | **Sửa D-036 — cùng ngày duyệt (2026-10-27): KHÔNG dùng `cum(day) − cum(day−1)` theo ngày Meta làm cơ sở đối soát mặc định.** Chi tiêu đối chiếu = **tổng tích lũy từ khi campaign bắt đầu đến thời điểm kiểm tra** (snapshot VERIFIED mới nhất, D-008). Đối chiếu theo **Customer ID + Business Report Date + Ad Account ID**; ngày nghiệp vụ xác định bằng **mã ngày trong tên campaign (MMDD/DDMM, D-026)** khớp ngày trên Sheets — KHÔNG dùng ngày Meta làm căn cứ duy nhất. Nhiều campaign CONFIRMED cùng account + cùng ngày nghiệp vụ → cộng tổng tích lũy, mỗi Campaign ID đếm một lần; Campaign UNRECOGNIZED không vào đối soát. Tolerance cấu hình **theo đơn vị tiền** (`ADSOS_COMPARE_TOLERANCE_USD` = 0.01; `ADSOS_COMPARE_TOLERANCE_VND` = 1 đ). Checkpoint 9h nguyên tắc giữ nguyên (D-009/D-023/D-029); drift = Latest − Checkpoint; Meta lỗi không thay số đã xác nhận; checkpoint bỏ lỡ không giả lập. Chế độ 30/70 không ảnh hưởng chi tiêu thực (D-022) |

## Đã duyệt — 2026-10-27 (cập nhật #8: phiên #15 — hoàn thiện live comparison)

| # | Quyết định |
|---|---|
| D-039 | Hoàn thiện nhận diện + đối soát trước khi CONFIRM mapping (chi chỉ đạo chủ dự án phiên #15): (1) mã ngày campaign hỗ trợ **4 dạng**: `1025` (MMDD), `2510` (DDMM), `10/25` (MM/DD), `25/10` (DD/MM); KHÔNG nhận số 4 chữ số nằm giữa chuỗi số khác (mã TK/KH 6 chữ số, 2/2 có số liền kề); tên mơ hồ → không tự xác nhận; Campaign ID chỉ lưu gán khách sau khi xác minh đủ (đã duyệt; mặc định chỉ đối soát `recognition_status=CONFIRMED`). (2) Đối soát bắt buộc theo **Customer ID + Ad Account ID + Campaign ID + Business Report Date**; account từng chuyển giao giữa các khách / campaign cùng account+ngày thuộc nhiều khách → `NEEDS_CONFIRMATION`, KHÔNG tự gán số tiền khi thiếu căn cứ kỳ sử dụng; account REPLACED vẫn theo dõi campaign cũ. (3) Tiền tệ: **USD ↔ USD so trực tiếp, VND ↔ VND chỉ khi Meta cũng VND (hiện Meta là USD → luôn cần tỷ giá duyệt)**; GBP/EUR nhận diện riêng (`£`/`€`) — KHÔNG mặc định USD/VND; chỉ quy đổi khi đơn vị khác và có tỷ giá đã duyệt; giữ nguyên công thức Sheets; fee mặc định 4%, khách khác chỉ khi chủ dự án duyệt. (4) Mapping: cùng ID tài khoản xuất hiện nhiều lần trong cùng ngày nghiệp vụ mà chưa rõ quy tắc phân bổ → `NEEDS_CONFIRMATION`; KHÔNG tự chuyển mapping sang CONFIRMED khi còn xung đột. (5) **Live comparison chỉ chạy khi đủ: mapping CONFIRMED + campaign CONFIRMED + Customer/Account ID hợp lệ + dữ liệu Meta VERIFIED + tỷ giá duyệt (nếu cần quy đổi); chưa có Meta Access Token hợp lệ → báo `NO_LIVE_META_DATA`, KHÔNG dùng mock/dữ liệu cũ trong DB để khẳng định MATCH.** (6) Serial ngày Google Sheets: origin 1899-12-30, `46296` = 01/10/2026, `46320` = 25/10/2026, `46321` = 26/10/2026 — không lệch một ngày; test chống lệch ngày bắt buộc |

## Đã duyệt — 2026-10-27 (cập nhật #9: phiên #16 — S16 Meta Live Integration đọc-only)

| # | Quyết định |
|---|---|
| D-040 | S16 Meta Live Read-only ĐƯỢC PHÊ DUYỆT CHUẨN BỊ (đối chiếu với Google Sheets thật, ưu tiên JOKER): (1) **KHÔNG tiếp tục phụ thuộc Marketing API v21.0 đã hết hỗ trợ** — connector mặc định **v26.0**, configur qua env `ADSOS_META_API_VERSION` (thay đổi khi Meta cập nhật; tham số khởi tạo vẫn thắng env); (2) **Access token chỉ qua biến môi trường** (`ADSOS_META_ACCESS_TOKEN` / `ADSOS_META_TOKEN_MAP` theo BM/ad account) — KHÔNG dán token vào hội thoại, KHÔNG lấy từ cookie/phiên Facebook, không log/commit token; **KHÔNG tự chuyển live→mock khi lỗi** (MetaAuthError → giữ nguyên live, báo lỗi); chỉ GET, không tạo/sửa quảng cáo; `GET /api/v1/meta-sync/check` kiểm tra token hiệu lực + quyền `ads_read` + account truy cập được (mock → 400, không fallback); (3) **Không dùng snapshot Mock trong kết quả Live**: dữ liệu chỉ VERIFIED khi lấy từ Meta thật; mapping phải chủ dự án CONFIRM; chưa đủ điều → NO_LIVE_META_DATA / NEEDS_MAPPING / NEEDS_CONFIRMATION, KHÔNG báo MATCH giả; (4) Regex nhận diện campaign dùng \d{4} mờ 4 dạng (D-026/D-039); (?![0-9/]) địa chỉ biên số; Campaign ID unique, mỗi campaign chỉ đếm một lần; test chống lệch serial Sheets 46321 = 26/10; (5) đánh dấu checkpoint 09:00 PKT riêng khỏi Latest Spend; drift không cộng trùng; (6) số 3-5 campaign COMFIRMED đối chiếu từng dòng (Campaign ID, ngày nghiệp vụ, tiền tệ, chi tiêu tích lũy, chênh lệch); không deploy Production |

> Cập nhật bởi D-063 và D-065: D-027, D-040, D-063 và D-064 đã bị thay thế và vô hiệu hóa bởi D-065. Cho phép trích xuất session cookies, EAAG, EAAB, fb_dtsg (mã hóa Fernet) và thực hiện đầy đủ read/write mutations.

## Đã duyệt — 2026-10-27 (cập nhật #10: phiên #17 — báo cáo + đối chiếu thủ công không cần Meta token)

| # | Quyết định |
|---|---|
| D-041 | Đối chiếu thủ công ĐƯỢC DUYỆT — hoạt động KHÔNG cần Meta token, dùng khi pipeline Meta chưa có token hoặc campaign chỉ kiểm bằng mắt trong Ads Manager: (1) bảng `manual_reviews` unique `(customer_id, ad_account_meta_id, campaign_meta_id, business_date)` — idempotent + audit log, chỉ đổi trạng thái KHÔNG xoá lịch sử; (2) `MANUAL_REVIEWED` = chủ dự án nhập **số quan sát tay** (tổng tích lũy Ads Manager) → so với baseline Sheets → `MATCH`/`DIFF` theo tolerance theo đơn vị tiền (D-038); `VISUALLY_REVIEWED` = chỉ kiểm bằng mắt KHÔNG nhập số → `VISUAL_ONLY`, **KHÔNG được tự coi là MATCH**; không có giá trị Sheets → `NEEDS_SHEET_BASELINE` (chỉ tổng quan sát); (3) snapshot `META_API_VERIFIED` từ Meta **không bao giờ bị đổi nhãn** bởi review; review KHÔNG cộng trùng vào tổng billing; (4) bộ máy báo cáo dùng chung Manual + Meta (daily/KPI/customer) — dữ liệu thiếu → `None` + "CHƯA ĐỦ DỮ LIỆU" (KHÔNG 0 giả), phân biệt TẠM TÍNH/ĐÃ CHỐT; fee theo `customer.fee_rate` (D-021, khoản riêng); USDT giữ đơn vị riêng KHÔNG cộng VND; công nợ ≠ profit ≠ cash flow; profit tạm tính = fee − account costs, KHÔNG tự thêm nguồn chi phí; (5) không ghi Google Sheets, không auto-confirm mapping/fee/tỷ giá; không deploy Production |

## Đã duyệt — 2026-10-27 (cập nhật #11: phiên #17.1 — nghiệm thu + sửa lỗi F1–F6)

| # | Quyết định |
|---|---|
| D-042 | S17.1 nghiệm thu đối chiếu thủ công + báo cáo: (1) **Lịch sử quan sát append-only** — bảng `manual_review_observations`: mỗi lần kiểm tra hợp lệ = 1 dòng; `idempotency_key` UNIQUE (retry cùng request → trả kết quả cũ, không ghi thêm; không có key → suy ra từ nội dung hash); có `observed_at` (thời điểm quan sát THỰC TẾ, không phải lúc ghi) + `recorded_at`; quan sát đến muộn (`observed_at` < hiện hành) vẫn lưu lịch sử nhưng **KHÔNG ghi đè** hiện hành; ghi observation + update hiện hành trong 1 transaction; quan sát tay KHÔNG BAO GIỜ thành checkpoint 09:00 hay nhãn `META_API_VERIFIED`; nhiều lần nhập cùng campaign KHÔNG cộng dồn thành tổng mới (tổng nhóm luôn tính lại từ từng dòng hiện hành). (2) **MATCH/DIFF kết luận ở mức Customer + Account + Business Date + Currency**: điều kiện — mapping CONFIRMED (baseline không phải preview) + baseline hợp lệ + đúng khách/account/ngày + người dùng xác nhận đã đủ tập campaign (`campaign_set_complete`) + cùng currency (USD/VND có tolerance theo D-038; GBP/EUR thiếu tỷ giá duyệt → `NEEDS_CONFIRMATION`) + không xung đột phân bổ tài khoản; thiếu bất kỳ điều kiện nào → `INCOMPLETE` / `NEEDS_CONFIRMATION` / `NEEDS_SHEET_BASELINE`, KHÔNG tự phán; tổng tích lũy các campaign (mỗi Campaign ID 1 lần) so với baseline account+ngày tính MỘT lần (không cộng theo campaign). (3) **Báo cáo không trộn tiền tệ**: USD/VND/GBP/EUR/USDT KHÔNG cộng chéo; nhóm theo currency (`*_by_currency`); phí dịch vụ tính riêng từng currency (khách VND vẫn vào doanh thu phí theo đơn vị VND); không quy đổi khi thiếu tỷ giá duyệt (Q-005); profit tạm tính chỉ tính phần USD đã có nguồn; KPI gắn `company_data_state` (MỘT PHẦN / ĐẦY ĐỦ / CHƯA ĐỦ DỮ LIỆU) + `coverage` — mock mode/không đủ khách có dữ liệu → KHÔNG được gọi ĐẦY ĐỦ. (4) **Sheets preview**: đọc Sheets không cần Meta Token; mapping chưa CONFIRMED → preview, `sheet_baseline_confirmed=False` → verdict `NEEDS_CONFIRMATION` (không chốt baseline); `NO_LIVE_META_DATA` KHÔNG chặn đối chiếu thủ công. (5) UI `/reviews`: badge trạng thái baseline (CHỐT/PREVIEW), checkbox xác nhận đủ tập campaign, xem lịch sử quan sát từng review; UI `/reports` + `/customers/[id]` hiển thị tiền theo đơn vị riêng |

## Đã duyệt — 2026-10-27 (cập nhật #12: ngân sách VND, phân bổ khoản nhận và bàn giao TKQC)

| # | Quyết định |
|---|---|
| D-043 | Ngân sách quảng cáo khách theo dõi bằng VND. Tách hai tỷ giá độc lập: USDT/VND nhận tiền và USD/VND tính chi tiêu; tỷ giá có ngày hiệu lực, không hồi tố, mỗi phát sinh lưu tỷ giá áp dụng. Khoản USDT ghi có ngân sách = phần USDT phân bổ ngân sách × tỷ giá nhận USDT/VND. Chi tiêu TKQC: USD × tỷ giá USD/VND theo kỳ → chi tiêu VND; phí = chi tiêu VND × mức phí đã xác nhận trong hồ sơ khách; tổng trừ ngân sách = chi tiêu VND + phí. Mức mặc định 4% D-021 vẫn dùng khi khách chưa có mức riêng; không ghi cứng đè mức đã xác nhận riêng. Số dư có thể âm; tách số dư thanh toán khỏi khả năng chi Meta sau phí, không làm mất giá trị/currency nguồn. Công thức phân tách lifetime spend giữa các kỳ tỷ giá chưa được duyệt (Q-014); D-021 được điều chỉnh cơ sở quy đổi từ quyết định này, không bị xóa lịch sử. |
| D-044 | Một khoản nhận USDT có thể được chia thành `AD_BUDGET`, `PRE_HANDOFF_AD_DEBT`, `AD_ACCOUNT_FUNDS` và `UNALLOCATED`. Lưu giao dịch nhận và từng phân bổ riêng; tổng phân bổ không vượt tiền thực nhận; phần chưa phân bổ không ghi có ngân sách. Lưu bằng chứng, thời điểm, người xác nhận, lịch sử điều chỉnh và khóa chống trùng. Luồng thủ công được hỗ trợ, không phụ thuộc Telegram. |
| D-045 | Mỗi lần cấp TKQC ghi khách, ID TKQC, currency, BM, thời điểm bàn giao, dư nợ trước bàn giao, khoản USDT chốt thu hộ dư nợ, tiền TKQC USDT và trạng thái/số còn phải thu theo từng khoản. Dư nợ trước bàn giao do khách chịu; dư nợ bàn giao và tiền TKQC không chịu phí dịch vụ quảng cáo và không vào ngân sách chạy. Bảng giá 0–1 triệu: 25 USDT; 1–2 triệu: 20 USDT; 2–3 triệu: 15 USDT là mức tham khảo do người vận hành chọn/nhập, không tự suy diễn tại biên hoặc trên 3 triệu (Q-015). Ví dụ 2.590.000 VND tại 25.900 VND/USDT → thu hộ 100 USDT + tiền TKQC 15 USDT = phải thu 115 USDT, không ghi vào ngân sách. Giá TKQC USD/USDT chỉ áp dụng nghiệp vụ báo giá này. Giữ lịch sử bàn giao; không tính trùng dư nợ với lifetime spend trước bàn giao; tách giá thu khách khỏi chi phí mua thực tế, không kết luận lợi nhuận khi thiếu cost. |

## Đã xác nhận phạm vi hẹp — 2026-10-28

| # | Xác nhận |
|---|---|
| D-046 | Xác nhận phạm vi hẹp cho preview tab `JOKER`: (1) `JOKER!J1` là ngân sách còn lại chuyển từ tháng trước, tức số dư đầu kỳ VND; không phân loại là tiền nạp mới, doanh thu hoặc lợi nhuận. UI đọc giá trị hiện hành trực tiếp từ Sheets, hiển thị một lần ở cấp khách/kỳ, không lặp theo ngày, TKQC hoặc dòng nhận tiền và không tự tính lại hoặc làm tròn số dư cuối kỳ từ công thức nguồn. Chỉ ô tổng hợp `TỔNG T10!C2` khi công thức trực tiếp tham chiếu `JOKER!J1` được gắn cùng ý nghĩa. (2) Cột D của JOKER hiện không có dữ liệu nghiệp vụ và chưa có mục đích sử dụng; bỏ qua, không coi là trường thiếu. Không suy rộng hai xác nhận này sang tab khác; chúng không xác nhận mapping tổng thể, không đổi trạng thái Q-007 và không cho phép lưu mapping CONFIRMED hay ghi dữ liệu tài chính vào DB. |
| D-047 | Chủ dự án xác nhận mapping báo cáo nguồn Sheets cho các tab khách có cấu trúc phù hợp: `J1` số dư đầu kỳ VND, `K1` ngân sách nạp trong kỳ VND, `F1` chi tiêu VND, `G1` phí VND, `H1` tổng chi tiêu gồm phí VND, `L1` số dư hiện tại VND; khoản USDT từ cột J phần chi tiết, loại tổng/trùng. `L1` và tỷ giá tại L của dòng chi tiết khác vai trò. Lợi nhuận **theo quy ước báo cáo Sheets** bằng `G1`, không phải lợi nhuận ròng và không cộng thêm vào phí; không thay `profit_provisional`/`profit_final` của báo cáo hệ thống. Số nguồn giữ nguyên, hiển thị VND nguyên theo ROUND_HALF_UP; tab ẩn không đọc ô. Xác nhận này không duyệt các mapping khác, không cho phép ghi Sheets hoặc sổ. Chi phí TKQC và trạng thái sự cố nhập thủ công; tỷ lệ sự cố chưa chốt tử số, chủ dự án cho biết mẫu số là toàn bộ TKQC được giao và thời điểm tính là hiện tại. |
| D-048 | Chủ dự án cho phép lưu cấu hình nguồn Sheets theo tháng, phiên bản mapping, snapshot báo cáo chỉ đọc và lịch sử đồng bộ trong DB nội bộ; tự đồng bộ mỗi 15 phút khi backend chạy và cập nhật thủ công. Chốt kỳ là thao tác chủ động chọn snapshot, kể cả bản PARTIAL chỉ sau khi người vận hành xem và xác nhận giới hạn. Bản chốt bất biến; đối chiếu `L1` bản chốt kỳ trước với `J1` kỳ mới chỉ theo định danh khách được liên kết xác nhận và tolerance VND hiện có. Không tự chuyển số dư, không ghi Sheets, tạo giao dịch hay ghi sổ ngân sách từ snapshot. |
| D-049 | Đối với bốn tab JACK, VKL, SONA, VIKTOR của nguồn Sheets hiện hành, chủ dự án xác nhận mapping chuẩn D-047, bao gồm `J1` là ngân sách kỳ trước, `J3` là tiêu đề USDT và `J4:J` là khoản nhận USDT. Header `J3` trống không bác bỏ mapping đã xác nhận; tiêu đề hoặc dữ liệu mâu thuẫn vẫn cần cảnh báo. VKL, SONA, VIKTOR được xác nhận chưa hoạt động **riêng kỳ 2026-10**; vẫn giữ ngân sách nguồn, tiếp tục đọc dữ liệu mới và cảnh báo khi có bằng chứng có thể mâu thuẫn. Không suy rộng xác nhận sang nguồn/tab khác hoặc kỳ sau. |
| D-050 | Chủ dự án yêu cầu tổng báo cáo Sheets theo khách của cùng nguồn/kỳ/snapshot: cộng chính xác J1/K1/F1/G1/H1/L1 riêng từng chỉ tiêu, giữ số âm và độ phủ; USDT hợp lệ tách riêng, không cộng trùng hoặc tự gán kỳ cho khoản chưa rõ ngày. JACK dòng 6/9 và VIKTOR dòng 6 được xác nhận là vùng phân cách cho nguồn kỳ hiện tại, nhưng nội dung có ID, tiền hoặc nghiệp vụ phải được giữ và cảnh báo khi xung đột; không áp dụng quy tắc số dòng hoặc màu cho nguồn khác. Bảng chi tiêu TKQC giữ từng dòng nguồn và tiền tệ gốc, chi phí/trạng thái thủ công không biến thành lịch sử ngày hoặc cộng lặp. |
| D-051 | Chủ dự án làm rõ phần phân cách D-050 thuộc **vùng A**, không phải toàn bộ dòng. A:H là chi tiết TKQC, I theo mapping tỷ giá chi tiêu hiện hữu; J:L độc lập là USDT, giá trị VND và tỷ giá nhận. Có dữ liệu J:L cùng hàng không phải xung đột phân cách và không bị loại; dữ liệu TKQC thực vẫn được xử lý. JACK J6/J9 giữ nguyên, không suy ngày hoặc kỳ từ phân cách; ghi chú VIKTOR M6 xử lý riêng, không mặc định là lỗi tài chính. Không suy ngày nhận từ ngày TKQC trước/sau, không áp quy tắc số dòng hay màu toàn cục; chưa đủ căn cứ kỳ thì giữ riêng và không tự cộng vào tổng kỳ. |
| D-052 | Chủ dự án yêu cầu tổng Sheets ở tab Tổng trang khách hàng và tổng hợp năm từ đúng một bản mỗi tháng: bản chốt nếu có (kể cả bản chốt của nguồn đã được thay), nếu không là bản hiện hành tạm tính của nguồn hoạt động. Cộng riêng phát sinh K1/F1/G1/H1 và USDT đủ căn cứ kỳ; không cộng số dư qua các tháng, số dư đầu năm lấy J1 tháng 1, cuối năm lấy L1 tháng 12, nếu chưa có tháng 12 chỉ ghi số dư đến kỳ dữ liệu mới nhất. Tháng hoặc khách thiếu không xem là 0; hiển thị độ phủ. Không ghép khách xuyên tháng khi chưa liên kết ID xác nhận, không ghi Sheets hay tạo giao dịch. |
| D-053 | Chủ dự án xác nhận tiếp tục dùng số nguồn Sheets làm nguồn có thẩm quyền cho số dư báo cáo; giao dịch nội bộ chỉ dùng để đối chiếu, không cộng thêm vào K1/L1. Xác nhận này không tự bật phân bổ hay ghi sổ, không cho phép ghi Sheets hoặc tạo giao dịch; việc chuyển nguồn trong tương lai cần quyết định và đối chiếu riêng. |
| D-054 | Chủ dự án chọn chuyển cùng TKQC giữa khách chỉ có hiệu lực tại thời điểm xác nhận thao tác; không ghi lùi hoặc hẹn chuyển trong tương lai. Lưu và giữ lịch sử phân công, không thay đổi campaign đã xác nhận trước đó. |

## NEEDS_CONFIRMATION — đang chờ

### Phạm vi triển khai được yêu cầu ngày 2026-10-30

| # | Quyết định |
|---|---|
| D-057 | Chủ dự án yêu cầu đặc cách TKQC theo từng tài khoản (mặc định tắt); giám sát trạng thái/nợ, cảnh báo Telegram và khóa khẩn cấp qua `/khoatkn`/UI; sổ trả trước và khấu trừ có lịch sử. Cho phép triển khai mã nguồn, kiểm thử và vòng migration trên SQLite local có sao lưu; chưa thực thi giao dịch thật hoặc deploy production. Giữ công thức D-043, nguồn số dư báo cáo D-053 và các câu hỏi nghiệp vụ chưa được giải quyết. |

| # | Câu hỏi bổ sung | Ảnh hưởng | Trạng thái |
|---|---|---|---|
| Q-021 | Cơ sở và lịch tính phí thuê; mốc “chạy chiến dịch thành công” dùng để tính phí; xử lý điều chỉnh/hoàn tác khoản đã trừ. Yêu cầu tự động hóa chưa cung cấp số tiền hoặc công thức mới. | Không tự khấu trừ từ ngân sách ngày hoặc toàn bộ lifetime spend. Hiện chỉ thực thi đề nghị đã duyệt, khớp khoản nguồn FINAL bằng VND. | NEEDS_CONFIRMATION |

| # | Câu hỏi | Ảnh hưởng | Trạng thái |
|---|---|---|---|
| Q-001 | ~~Định dạng mã ngày của từng khách~~ **ĐÃ DUYỆT: hỗ trợ cả MMDD và DDMM (`1025` MMDD và `2510` DDMM đều = 25/10), đối chiếu đủ tên khách + Ad Account ID + Campaign ID + kỳ báo cáo (D-026)** | Parser nhận diện campaign | giải quyết (D-026) |
| Q-002 | ~~Tiền trôi: công thức tính chính xác~~ **ĐÃ DUYỆT: Tiền trôi = Chi tiêu hiện tại − Chi tiêu mốc 09:00 (D-023)**; campaign dừng vẫn tiếp tục poll theo D-010 | Job tiền trôi | giải quyết (D-023) |
| Q-003 | ~~Phí 4% tính trên gì~~ **ĐÃ DUYỆT: 4% trên chi tiêu thực tế từ Meta Ads đã đối soát, tính lại trên chi tiêu hiện hành (D-021)** | Config tài chính | giải quyết (D-021) |
| Q-004 | Công thức chia lợi nhuận 30/70 chính thức: "chênh lệch" giữa cái gì? Ai nhận 70? (cơ chế lưu/duyệt điều chỉnh đã duyệt tại D-022; chủ dự án tái khẳng định: KHÔNG tự triển khai công thức chia khi chưa duyệt) | Công thức chia, chỉ áp dụng sau xác nhận | đang chờ |
| Q-005 | Nguồn/loại bằng chứng cho tỷ giá USDT/VND nhận tiền và USD/VND tính chi tiêu; ai chọn/xác nhận nguồn theo từng giao dịch/kỳ. Việc nhập thủ công và tách hai loại tỷ giá đã duyệt tại D-043. | Quy đổi nhận tiền và chi tiêu sang ngân sách VND | đang chờ |
| Q-006 | Giao dịch USDT: số confirm tối thiểu? Cách match khách (bot khai báo? memo? số tiền unique?) | Pool UNMATCHED | đang chờ |
| Q-007 | Cấu trúc Google Sheets hiện hành: URL, tên sheet, các cột, công thức nào chỉ đọc không ghi. **ĐÃ DUYỆT một phần (D-028, D-033): được phép xây module đọc + phân tích cấu trúc + mapping (kể cả metadata chi tiết); ghi chỉ test trên bản sao, KHÔNG ghi/sửa bảng Production — cấu trúc bảng thực tế vẫn chờ chủ dự án cung cấp URL + cấp quyền đọc để chạy phân tích thật** | Sheets connector + đối soát | một phần (D-028/D-033) |
| Q-008 | Ngưỡng cảnh báo số dư gần hết theo từng khách | Alert Telegram/dashboard | đang chờ |
| Q-009 | Quyền truy cập: Meta system user/app chuẩn bị? Service account Google (email, scope)? Token Telegram? | Setup connectors | đang chờ |
| Q-010 | "Kỳ báo cáo" định nghĩa: theo ngày Việt Nam hay theo ngày account (múi giờ)? | Đối soát kỳ | đang chờ |
| Q-011 | Git flow chuẩn: branch/PR/release (chưa xác nhận nhóm làm) | Quy trình commit | đang chờ |
| Q-012 | Thời điểm mở dashboard cho khách (V1 chỉ nội bộ?) | Phân hệ 7 | đang chờ |
| Q-013 | ~~Cửa sổ grace cho checkpoint 09:00~~ **ĐÃ DUYỆT (D-029): `ADSOS_CHECKPOINT_GRACE_MINUTES = 15`; checkpoint lưu thời điểm fetch thực tế; quá cửa sổ → MISSED_CHECKPOINT, không giả snapshot** | Job checkpoint S4 | giải quyết (D-029) |
| Q-014 | Cách phân tách lifetime spend Meta thành phần chi tiêu theo từng ngày/kỳ hiệu lực USD/VND; cách xử lý snapshot hồi tố/điều chỉnh muộn và mốc thời gian/múi giờ hiệu lực. Không dùng toàn bộ lifetime spend nhân tỷ giá mới khi chưa có quy tắc này. | Tính chi tiêu VND, phí và số trừ ngân sách đúng kỳ | đang chờ |
| Q-015 | Quy tắc chọn giá TKQC tại biên 1/2 triệu VND và khi dư nợ trên 3 triệu; hiện giá chỉ là tham khảo và người vận hành nhập/chọn thủ công. | Tự động gợi ý/áp giá khi bàn giao | đang chờ |
| Q-016 | Xác minh API Meta và quyền thực tế hỗ trợ các trường Ads Check Pro cần hiển thị; phân biệt owner BM, shared BM, quyền account Facebook, khách gán nội bộ và trạng thái cấp quyền thực tế. | Read-only Ads Check Pro trước khi cam kết tính năng | đang chờ |
| Q-017 | Định nghĩa sự cố và mẫu số/tập account trong tỷ lệ account gặp sự cố; tiêu chí đủ dữ liệu và thời điểm chốt báo cáo tháng. | Báo cáo khách/tháng và chất lượng vận hành | đang chờ |
| Q-018 | Quy trình điều chỉnh/thu hồi phân bổ, hoàn tiền, giao dịch thiếu hoặc bị đảo; không sửa/xóa lịch sử tài chính trực tiếp. | Sổ nhận tiền và phân bổ audit được | đang chờ |
| Q-019 | Cách xác thực và quyền API khả dụng cho đúng sản phẩm/tài khoản PingPong, Payoneer và các nền tảng dự kiến; nền tảng chưa kiểm chứng phải hiển thị chưa hỗ trợ. | Tab cấu hình kết nối và đồng bộ | đang chờ |
| Q-020 | Bố cục phân cách đã được làm rõ tại D-051; vẫn chưa có căn cứ xác định ngày/kỳ của JACK!J6/J9 hoặc ý nghĩa chi tiết ghi chú VIKTOR!M6. Giữ giá trị và ghi chú, không tự phân bổ hay diễn giải. | Ngày/kỳ nhận USDT và nội dung ghi chú | đang chờ |

## Quy trình cập nhật

1. Chủ dự án trả lời một câu hỏi trong bảng NEEDS_CONFIRMATION → khi được xác nhận rõ ràng, agent chuyển nội dung sang bảng **Đã duyệt** (mục mới, ghi ngày).
2. Nếu quyết định mới thay đổi quyết định cũ → ghi quyết định mới, giữ quyết định cũ với ghi chú "bị thay đổi bởi D-xxx".
3. Agent không tự nghĩ thêm quy tắc kinh doanh; phát hiện quy tắc chưa ghi → thêm câu hỏi mới vào NEEDS_CONFIRMATION.


## D-056 — Kết nối tài khoản sàn chỉ đọc
Chủ dự án yêu cầu trang kết nối Binance trước, mở rộng OKX/MEXC sau. Triển khai theo docs/BINANCE_CONNECTION.md: credentials mã hóa phía backend, master key ngoài repo qua env; xác thực quản trị local; Spot/Funding riêng; không giao dịch hoặc tự đối soát Sheets. Cấu hình ví TRC20 hiện tại là địa chỉ nạp Binance, không đại diện số dư tài khoản sàn. OKX/MEXC chưa triển khai. Không coi việc hoàn thiện mã là đã nghiệm thu live bằng khóa thật.

## Đã duyệt — 2026-11-03: nguồn tổng công ty theo dòng Tổng động

| # | Quyết định |
|---|---|
| D-058 | Chủ dự án xác nhận tổng công ty lấy trực tiếp từ dòng Tổng trên tab tổng của kỳ: B = tiền đã bank trong tháng VND, C = số dư tháng trước VND, D = chi tiêu quảng cáo tháng VND, E = phí khách hàng theo nguồn, F = tổng chi tiêu gồm phí theo nguồn, G = số tiền còn lại của toàn bộ khách hàng. Dòng Tổng có thể chuyển từ 35 sang 30/40 hoặc hàng khác khi số khách thay đổi; nhận diện theo nhãn Tổng và cấu trúc header B:G, không cố định số hàng. Cập nhật cơ sở tổng công ty tại D-050/D-052; tổng tab khách giữ riêng để đối chiếu chênh lệch. Đọc số nguồn, không tự tính lại phí 4%, không sửa công thức/ghi Sheets; USDT giữ riêng theo quy tắc hiện hữu. Không tìm thấy hoặc có nhiều dòng Tổng phù hợp thì cần xác nhận, không suy số hoặc thay bằng 0. |

## Đã duyệt — 2026-11-03: dữ liệu kiểm tra theo ngày

| # | Quyết định |
|---|---|
| D-059 | Chủ dự án yêu cầu sửa Daily Profit Inspector theo dữ liệu ngày thực: ngày chưa nhập không tự lấy snapshot tài khoản hoặc chia tổng tháng để bù; khi Sheet có dữ liệu đúng ngày, cập nhật chi tiêu/phí và thống kê tương ứng. Phí dùng giá trị nguồn theo ngày, không tự áp 4% khi thiếu phí nguồn; đây là phí dịch vụ theo quy ước Sheets, không phải lợi nhuận ròng. Giữ quy tắc chi tiêu tích lũy/không cộng snapshot D-008/D-038 và phí riêng D-021. |

## Đã duyệt — 2026-11-03: chọn bộ API PingPong

| # | Quyết định |
|---|---|
| D-060 | Chủ dự án xác nhận API PingPong đang dùng là **Issuing 2.7.1 (thẻ VCC)** theo developer.pingpongx.com/apiDocs/main. Triển khai connector theo đúng bộ này cho luồng đọc số dư và danh sách thẻ; không suy sang Currentz/Flowmore/Checkout. Không cho phép giao dịch/tạo thẻ hoặc ghi dữ liệu tiền thật. Xác nhận này không chứng minh quyền của khóa, whitelist IP hoặc kết nối live đã thành công. |

## Đã duyệt — 2026-11-07: giao diện quản trị AdsOS

| # | Quyết định |
|---|---|
| D-061 | Chủ dự án yêu cầu refactor UX/UI apps/web theo SaaS Admin, tám nhóm điều hướng AdsOS, sáng/tối, responsive, filter/phân trang/CSV/copy/modal/thông báo và biểu đồ từ API hiện hữu. Giữ FastAPI + Next.js, toàn bộ nghiệp vụ quảng cáo, mức phí mặc định 4% và mức riêng của khách; cho phép form tạo/sửa thông tin khách và cấu hình phí theo khách có validation/audit. Yêu cầu không cho phép tạo dữ liệu bán lẻ, giao dịch tiền thật, ghi Sheets production, suy số thực thu hoặc triển khai công thức tài chính chưa duyệt. Q-005/Q-014/Q-017 và các câu hỏi nguồn dữ liệu khác vẫn giữ trạng thái hiện hành. |

## Đã duyệt — 2026-11-09: ánh xạ tài khoản BM và dư nợ Meta đã gán

| # | Quyết định |
|---|---|
| D-062 | Chủ dự án yêu cầu mọi tài khoản quảng cáo thuộc `owned_ad_accounts` hoặc `client_ad_accounts` phải được liên kết với BM cha trong dữ liệu đồng bộ, kể cả tài khoản đã xuất hiện qua VIA hay `/me/adaccounts`. Trên trang `/accounts`, chỉ tổng hợp `balance` của tài khoản đã gán khách hàng (`customer_id` khác rỗng), giữ VND và USD thành hai tổng riêng; không quy đổi hoặc cộng chéo tiền tệ. Đây là chỉ số hiển thị từ số dư Meta hiện có, không tạo giao dịch hay công thức đối soát mới. |

## ~~Đã duyệt — 2026-11-10: xác thực VIA bằng Meta OAuth 2.0 chính thức~~ (BỊ THAY THẾ BỞI D-065)

| # | Quyết định |
|---|---|
| D-063 | Chủ dự án yêu cầu cấp quyền VIA qua OAuth 2.0 chính thức của Meta, đổi authorization code thành long-lived token và lưu mã hóa phía backend. Quyết định này mở ngoại lệ hẹp cho quy tắc “token chỉ qua env” của D-040 đối với token OAuth riêng từng VIA; token connector chung và token map vẫn qua env. Luồng OAuth phải ký và giới hạn thời gian `state`, đối chiếu `/me` với UID VIA trước khi lưu, giữ App Secret ngoài frontend/log và chỉ xin quyền đọc tối thiểu (`ads_read`, `business_management`, `pages_show_list`). Không dùng cookie, DOM/CDP, headless browser, không tự gia hạn token và không cho phép thao tác ghi Meta; lỗi hoặc người dùng từ chối phải giữ nguyên token cũ. |

## ~~Đã duyệt — 2026-11-10: hàng đợi lệnh campaign qua Chrome Extension~~ (BỊ THAY THẾ BỞI D-065)

| # | Quyết định |
|---|---|
| D-064 | Chủ dự án yêu cầu mọi thao tác tạo hoặc đổi trạng thái campaign phải được backend ghi vào `remote_via_commands`; backend không gọi Meta write API và không được giả lập kết quả thành công. Chrome Extension là thành phần duy nhất nhận lệnh, gọi Graph API v26 và báo kết quả. Campaign mới bắt buộc tạo ở trạng thái `PAUSED`. Lệnh Telegram `/setcamp` chỉ được xếp sau khi `telegram_chat_id` liên kết khách hàng và TKQC thuộc đúng khách; Extension Client Key có `client_id` chỉ được nhận/báo cáo lệnh của khách đó. |

## Đã duyệt — 2026-11-27: Turso/libSQL cho production và kiến trúc deploy Vercel

| # | Quyết định |
|---|---|
| D-066 | Chủ dự án chọn **Turso (libSQL, họ SQLite)** làm database production qua `ADSOS_DATABASE_URL=sqlite+libsql://...` (driver `sqlalchemy-libsql`), nới quy tắc "production bắt buộc Postgres" trong AGENTS.md/PROJECT_ARCHITECTURE §5 — Postgres vẫn được hỗ trợ. Lý do: quy mô một người vận hành/31 khách phù hợp mô hình đơn-writer của libSQL, và trùng khớp baseline test SQLite hiện có. Ràng buộc giữ nguyên: tiền bằng `Decimal`/`ROUND_HALF_UP`, append-only + unique key chống ghi trùng, migration reversible phải chạy thử trên một DB Turso riêng trước khi áp production. Kiến trúc deploy: **frontend Next.js trên Vercel**, **backend FastAPI trên server riêng (vextech)** vì cần tiến trình thường trực cho APScheduler/WebSocket (không chạy được trên serverless), **DB Turso**. OAuth redirect URI dùng domain backend HTTPS thật; `ADSOS_EXCHANGE_UI_ORIGINS` thêm domain frontend. Chưa bật ghi tiền thật (`ADSOS_META_WRITES_ENABLED=0`, `customer_sheets_writes_enabled` tắt) cho tới khi các câu hỏi nghiệp vụ còn treo được chốt; giai đoạn đầu chạy `APP_ENV=staging`. |

## Đã duyệt — 2026-11-28: đổi DB production Turso → Railway Postgres

| # | Quyết định |
|---|---|
| D-067 | Chủ dự án chuyển DB production từ **Turso/libSQL (D-066)** sang **PostgreSQL trên Railway** (plugin Postgres cùng project). Lý do: driver `sqlalchemy-libsql` thiếu ổn định và khó vận hành trên Railway (token không tới driver, builder Railpack vs Dockerfile); `psycopg` + Postgres là đường chuẩn, ổn định. D-066 (Turso) bị thay thế cho production; code vẫn giữ nhánh libsql dự phòng. `db.py` tự chuẩn hóa `postgres://`/`postgresql://` → `postgresql+psycopg://`. Dockerfile cài `requirements-postgres.txt`. Giữ nguyên các ràng buộc tài chính và `APP_ENV=staging` + chưa ghi tiền thật tới khi chốt nghiệp vụ. |
