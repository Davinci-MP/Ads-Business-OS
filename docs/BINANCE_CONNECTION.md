# Ví & tài khoản sàn

Trang: `/config/wallets`, truy cập từ Cấu hình. Chỉ Binance Spot/Funding USDT được hỗ trợ; OKX/MEXC chưa hỗ trợ.

## Bảo mật local

- Backend bind `127.0.0.1`, không chạy qua proxy công khai. Mỗi request quản trị cần `X-Adsos-Wallet-Token`, so sánh với `ADSOS_EXCHANGE_ADMIN_TOKEN` (ít nhất 32 ký tự). Token chỉ ở bộ nhớ trang, reload phải mở lại.
- `ADSOS_EXCHANGE_MASTER_KEY` là Fernet key hợp lệ, lưu bền vững ngoài repo/DB. Mất key không giải mã được credentials đã lưu. Không tạo key mới mỗi lần khởi động.
- Chỉ credentials sàn được phép nhập qua UI và lưu ciphertext trong DB. Đây là ngoại lệ được chủ dự án yêu cầu đối với quy tắc secrets qua env; master key vẫn bắt buộc qua env. API không trả lại credentials, validation không echo input.
- Không dùng API key đã gửi vào chat; thu hồi và tạo key mới. Chỉ bật Reading. App kiểm tra `enableReading` và các quyền ghi/rút/chuyển thật của `/sapi/v1/account/apiRestrictions`, từ chối khi không đủ bằng chứng.
- Scheduler cần cả `ADSOS_EXCHANGE_SCHEDULER_ENABLED=true` và tùy chọn tự cập nhật của từng kết nối. Mặc định tắt, chu kỳ 30 phút. Manual/scheduled dùng chung khóa đọc và tôn trọng cooldown do Binance giới hạn.
- Cấu hình origin mặc định localhost:3000/127.0.0.1:3000 qua `ADSOS_EXCHANGE_UI_ORIGINS`. CORS không thay thế xác thực. Không bật trace/log request body chứa credentials.

## Ý nghĩa số liệu

- Mỗi ví Spot/Funding hiển thị khả dụng, khóa, đóng băng, đang rút riêng. Không tự cộng các trường khi chưa xác định ý nghĩa tổng.
- Danh sách đầy đủ hợp lệ không có USDT cho kết quả 0; thiếu/sai trường hoặc API lỗi giữ trạng thái lỗi, không 0 giả.
- Snapshot luôn có thời điểm. Lỗi một ví không ghi đè số thành công của ví đó; UI hiển thị thời điểm riêng và cảnh báo dữ liệu cũ.
- Không cộng nhiều kết nối vì có thể trùng tài khoản Binance. Không cộng ví TRC20 nạp sàn với số dư Binance. Không tự đối soát VND Sheets, tạo giao dịch hoặc ghi có ngân sách.
- Earn/Futures/Margin ngoài phạm vi. 8.953,04 USDT người dùng từng cung cấp không được hardcode.

## Nguồn kỹ thuật đã kiểm tra

- https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/account
- https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/asset

## Migration và vận hành

Hai revision: `d4c7e0a1f835` tạo cấu hình/credentials/snapshot/history, `e5d8f1b2c946` thêm freeze/withdrawing nullable cho lịch sử. Không backfill số 0 vào dữ liệu cũ thiếu trường.

Trước khi áp dụng: dừng frontend/backend của dự án, sao lưu SQLite bằng backup API, kiểm tra build, chạy Alembic upgrade head. Giữ backup master key ngoài repo cùng chính sách bảo vệ riêng. Không downgrade trên DB thật để thử nghiệm vì sẽ mất lịch sử bảng bị xóa; round-trip chỉ trên DB test.

Chưa nghiệm thu live Binance nếu chưa có key mới nhập trực tiếp bởi người dùng. Bản nghiệm thu cổng 3002 dùng giả lập trên DB riêng, không nhập key thật vào bản này.
