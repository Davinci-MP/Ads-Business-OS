---
name: meta-ads-sync
description: Use when working with Meta Marketing API or Facebook Ads data — campaign spend sync, hourly cumulative spend updates, the 09:00 Vietnam checkpoint, tien troi (spend drift detected after a campaign stops), identifying campaigns from campaign ID + name + customer + reporting period, or ad account timezones (UTC+7, UTC-7, UTC+3, UTC+5). Also use when fixing double-counted spend or overwritten confirmed numbers.
---

# Meta Ads Sync

Đồng bộ campaign và chi tiêu từ Meta Marketing API an toàn. Đọc `docs/CAMPAIGN_RULES.md` trước khi sửa code.

## Nguyên tắc bất biến

1. Chi tiêu luôn là **tổng tích lũy** từ lúc campaign bắt đầu → thời điểm check. KHÔNG dùng delta từng giờ làm số chính.
2. Cập nhật mỗi giờ = **append snapshot mới**, không cộng các snapshot cũ: `SUM(snapshots)` là sai; dùng snapshot mới nhất.
3. Chống trùng ở tầng DB: unique `(campaign_id, snapshot_at)`. Job phải idempotent.
4. Checkpoint **09:00 Asia/Ho_Chi_Minh hằng ngày** được đánh dấu `is_checkpoint_9h = true`; snapshot_at = **giờ fetch thực tế** trong cửa sổ grace 15 phút (`ADSOS_CHECKPOINT_GRACE_MINUTES`, D-029); quá cửa sổ → `MISSED_CHECKPOINT`, không tự tạo snapshot giả. Hai job cùng giờ chỉ chạy một lượt fetch (single-flight + port-lock, D-030). Telegram lỗi → thông báo vào `telegram_outbox` gửi lại lần sau (D-031). Chưa có token → chạy **mock mode** (D-027); live bị chặn cho tới khi chủ dự án cấp token (Q-009).
5. Campaign `PAUSED`/`ENDED` vẫn tiếp tục được poll để phát hiện **tiền trôi**. Công thức đã duyệt (D-023): `Tiền trôi = Chi tiêu hiện tại − Chi tiêu mốc 09:00` (cùng kỳ đối soát). Drift record unique theo `(campaign_id, checkpoint_snapshot_id)` — không tính trùng.
6. Chi tiêu tích lũy phải tăng đơn điệu; snapshot mới < snapshot cũ → nghi ngờ lỗi: giữ bản cũ, gắn `UNVERIFIED`.
7. API lỗi/không chắc chắn → không ghi đè số đã xác nhận; ghi bản ghi lỗi riêng, retry có giới hạn, cảnh báo admin.

## Quy trình đồng bộ

1. Token Meta lấy từ biến môi trường (không hardcode); token chỉ dùng quyền đọc (`ads_read`).
2. Lấy danh sách ad account đang hoạt động.
3. Với mỗi ad account: lấy campaigns (`/act_{ACCOUNT_ID}/campaigns`).
4. Nhận diện khách qua: Campaign ID + tên campaign (mã ngày 4 số — **cả hai định dạng MMDD và DDMM**, D-026: `1025` MMDD và `2510` DDMM đều = 25/10; mã có 2 cách đọc hợp lệ và khác nhau, ví dụ `1102` → không xác định được ngày) + tên khách + Ad Account ID + kỳ báo cáo. Thiếu/không khớp bất kỳ → `UNRECOGNIZED`, không tự gán khách, không tính tiền.
5. Lấy chi tiêu tích lũy (insights) — biên ngày theo **múi giờ của ad account** trong Meta API.
6. Ghi snapshot mới (append-only) vào Postgres; KHÔNG ghi vào Google Sheets ở bước này.
7. Job ghi log/audit chuẩn: bắt đầu → từng account → xong.

## Quy trình kiểm thử (bắt buộc trước khi merge)

- **Unit (mock Meta response):**
  - Checkpoint 9h: đúng giờ, đúng `is_checkpoint_9h`.
  - Chạy job 2 lần liên tiếp → số lượng snapshot không đổi (không cộng trùng).
  - API trả lỗi/giá trị rác → snapshot cũ giữ nguyên, có bản `UNVERIFIED`.
  - Campaign không nhận diện được → `UNRECOGNIZED`, không ghi ledger.
- **Integration (staging, quyền đọc thật):** chạy 1 lượt, đối chiếu số với Meta Ads UI. KHÔNG ghi (dù chỉ 1 cell).
- Lệnh chạy (đã kiểm chứng, từ thư mục `apps/api`): `.venv\Scripts\python.exe -m pytest -q tests` — test liên quan: `tests/test_meta_sync.py`, `tests/test_scheduler.py`, `tests/test_drift_rules.py`.
- Mọi thay đổi công thức/threshold tiền trôi phải có mục đã duyệt trong `docs/DECISIONS.md` trước.
