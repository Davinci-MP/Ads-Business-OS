# CAMPAIGN_RULES.md — Quy tắc campaign & chi tiêu Meta

> Bắt buộc đọc trước khi đụng vào logic nhận diện campaign, snapshot chi tiêu, checkpoint 9h, tiền trôi. Công thức chưa được duyệt trong `docs/DECISIONS.md` → gắn `NEEDS_CONFIRMATION`.

## 1. Nhận diện campaign

- Khách đặt tên campaign theo ngày: **mã ngày hỗ trợ 4 dạng (D-026 + D-039): `1025` (MMDD), `2510` (DDMM), `10/25` (MM/DD), `25/10` (DD/MM)**; cả dạng 4 số liền và 2/2 có dấu `/`; kết hợp tên khách.
- **KHÔNG nhận số nằm giữa chuỗi số khác** (mã TK/KH 6 chữ số, 2/2 có số liền kề) — chỉ token ngày liễng (biên số).
- **Nếu một mã có 2 cách đọc hợp lệ và cho ra 2 ngày khác nhau** (ví dụ `1102`: 02/11 hoặc 11/02; `11/02`: 02/11 hoặc 11/02) → không xác định được ngày → `UNRECOGNIZED` chờ chủ dự án xác nhận, **KHÔNG tự ghép**.
- Campaign chỉ được "chủ sở hữu" khi khớp đủ:
  1. **Campaign ID** (định danh chính)
  2. **Tên campaign** (chứa mã ngày + tên khách)
  3. **Khách hàng sở hữu** (nối với account khách tính phí)
  4. **Kỳ báo cáo** (khung ngày đối soát)
- Thiếu/không khớp bất kỳ → tag `UNRECOGNIZED`, **KHÔNG tự gán khách, KHÔNG tính tiền**. Báo lên Telegram/admin khi đã thiết lập cảnh báo.
- Một Campaign ID chỉ thuộc **một** khách và **một** kỳ báo cáo cho tới khi có hướng dẫn khác của chủ dự án; nếu nghi ngờ campaign bị dùng chung → gắn `NEEDS_CONFIRMATION`.

## 2. Múi giờ ad account

- Account phân bổ trên nhiều múi giờ: UTC+7, UTC-7, UTC+3, UTC+5.
- Mọi truy vấn theo khoảng thời gian (tính chi tiêu theo kỳ/năm/tuần) phải dùng múi giờ **của ad account** trong Meta API; không assume giờ Việt Nam ở mức truy vấn.
- Job scheduler (mốc 9h, cập nhật giờ) chạy theo **Asia/Ho_Chi_Minh** — cần lưu ý khi truy vết sự kiện trong account theo thời gian.

## 3. Chi tiêu tích lũy & chống cộng trùng

- Chi tiêu cần lấy là **tổng tích lũy** (insights chạy từ khi campaign bắt đầu đến thời điểm check) — KHÔNG phải delta từng giờ.
- **KHÔNG dùng `cum(day) − cum(day−1)` theo ngày Meta làm cơ sở đối soát** (D-036 bản cập nhật): ngày Meta không phải căn cứ duy nhất để xác định ngày nghiệp vụ — ngày nghiệp vụ xác định bằng mã ngày trong tên campaign (MMDD/DDMM, D-026) khớp ngày trên Google Sheets.
- Mỗi lần cập nhật chỉ **append snapshot mới**: `(campaign_id, snapshot_at, spend_value, source, is_checkpoint_9h)`.
- **TUYỆT ĐỐI không cộng dồn snapshot cũ** vào tổng — khi hiển thị/đối soát dùng chính snapshot mới nhất (VERIFIED).
- Unique key chống ghi trùng: `(campaign_id, snapshot_at)` — job chạy lại không tạo bản trùng (idempotent).
- Nhiều campaign hợp lệ (CONFIRMED) thuộc cùng một Ad Account + cùng ngày nghiệp vụ → **tổng tích lũy của các campaign được cộng**; mỗi Campaign ID chỉ đếm một lần. Campaign UNRECOGNIZED không được đưa vào đối soát.
- Checkpoint **09:00 Asia/Ho_Chi_Minh hằng ngày** được lưu riêng và đánh dấu `is_checkpoint_9h = true` (dùng đối soát buổi sáng). Checkpoint giữ nguyên sau khi ghi; **Latest Spend** cập nhật mỗi giờ; **Drift = Latest Spend − Checkpoint Spend** (D-023).
- Khi Meta API lỗi → không thay dữ liệu đã xác nhận bằng 0; checkpoint trễ ngoài grace → `MISSED_CHECKPOINT`, không giả lập checkpoint.
- Chi tiêu tích lũy phải là chuỗi tăng đơn điệu (monotonic). Nếu snapshot mới < snapshot cũ → nghi ngờ data lỗi: không overwrite, gắn `UNVERIFIED` và điều tra.
- Tolerance đối chiếu cấu hình **theo đơn vị tiền** (`ADSOS_COMPARE_TOLERANCE_USD` mặc định 0.01; `ADSOS_COMPARE_TOLERANCE_VND` mặc định 1 đ) — không dùng chung một giá trị cho VND/USD.

## 4. Tiền trôi (spend drift) — công thức đã duyệt (D-023)

- Định nghĩa: chi tiêu phát sinh sau khi campaign đã dừng.
- **Công thức đã duyệt: `Tiền trôi = Chi tiêu hiện tại − Chi tiêu mốc 09:00`** (cùng kỳ đối soát).
- Chi tiêu hiện tại luôn lấy theo dữ liệu Meta mới nhất (snapshot tích lũy mới nhất).
- Campaign `PAUSED`/`ENDED` vẫn nằm trong danh sách poll để bắt tiền trôi.
- Mỗi drift record unique theo `(campaign_id, checkpoint_snapshot_id)` — không tính trùng.
- Meta điều chỉnh muộn → cập nhật các khoản tạm tính, giữ nguyên lịch sử đã chốt (xem `FINANCE_RULES.md` §3.3).
- Campaign của account cũ (REPLACED) vẫn được poll — tiền trôi/campaign cũ vẫn vyện vào đối soát lịch sử.

## 5. Đối chiếu Google Sheets (D-036 bản cập nhật)

- Đối chiếu theo đáp án: **Customer ID + ngày nghiệp vụ (Business Report Date) + Ad Account ID**.
- Một dòng tài khoản trên Sheets có thể là **tổng của nhiều campaign hợp lệ** cùng ngày nghiệp vụ — cộng tổng tích lũy, không cộng trùng Campaign ID.
- Account USD → đối chiếu USD trước; quy đổi VND chỉ khi có **tỷ giá đã xác nhận**. Account VND → đối chiếu trực tiếp VND (vẫn cần tỷ giá duyệt cho Meta USD → VND, Q-005).
- Giữ nguyên công thức F/G/H Sheets; không sửa bảng gốc; phí mỗi khách cần xác nhận riêng (D-037).
- So khớp chỉ chạy khi mapping **CONFIRMED** (DATE + ACCOUNT + SPEND); thiếu → `NEEDS_MAPPING`.

## 5. Xử lý dữ liệu lỗi / không chắc chắn

- API trả lỗi hoặc giá trị bất thường → **KHÔNG ghi đè số đã xác nhận**:
  1. Giữ snapshot cũ.
  2. Ghi bản ghi lỗi (status `UNVERIFIED` / `API_ERROR`) — đánh dấu, không vào tổng chính thức.
  3. Retry có giới hạn; quá số lần retry → cảnh báo admin, job tiếp tục với account khác.

## 6. Lịch sử & thay thế account

- Không xoá campaign / account. Account bị hạn chế → trạng thái `REPLACED` + liên kết tới account thay thế.
- Campaign của account cũ giữ nguyên và vẫn nối với account cũ — dùng cho đối soát và phân tích lịch sử.

## 7. Kiểm thử bắt buộc (tóm tắt)

- Idempotency: chạy hàm sync 2 lần liên tiếp → số snapshot không thay đổi.
- Unit test mock Meta response, phủ các trường hợp: checkpoint 9h, snapshot chưa có, API lỗi không đè dữ liệu cũ, campaign `UNRECOGNIZED`.
- Xem chi tiết trong skill `.opencode/skills/meta-ads-sync/SKILL.md`.
