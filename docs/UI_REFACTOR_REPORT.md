# Nghiệm thu giao diện AdsOS Pro — 07/11/2026

## Kết quả triển khai

Giữ FastAPI và Next.js App Router, tái sử dụng nghiệp vụ AdsOS. Không thêm dữ liệu bán lẻ, không tạo giao dịch tiền thật hoặc ghi Google Sheets. Recharts đã có trong dự án; không cài thêm thư viện giao diện, quản lý trạng thái hay biểu tượng.

| Khu vực | Hành vi đã triển khai |
|---|---|
| Khung ứng dụng | Sidebar tám mục, thu gọn 256→80 px, drawer mobile, nền mờ, phím Escape/Tab và khôi phục focus, trạng thái đọc máy chủ, thông tin quản trị viên |
| Thanh đầu trang | Tìm TKQC/tên/thẻ, UID VIA, tên/Telegram khách; Ctrl+K, kết quả điều hướng đúng bộ lọc; chuyển sáng/tối lưu localStorage; cảnh báo thanh toán và số lệnh đang chờ |
| Thông báo | Context dùng chung, bốn loại thành công/lỗi/cảnh báo/thông tin, tự đóng sau 4 giây, có nút đóng và vùng đọc cho công cụ hỗ trợ |
| `/dashboard` | Bốn thẻ vận hành; chọn 7/30/90/365 ngày và tiền tệ; biểu đồ chi tiêu/phí; so sánh ngày khi có hai mốc và mẫu số hợp lệ; top TKQC lũy kế; năm lệnh chờ; liên kết tài chính/nguồn/sàn |
| `/accounts` | Giữ lọc và gán khách, đọc đầy đủ các trang API; thêm phân trang 10/20/50, chọn tài khoản theo trang, CSV thoát ký tự/công thức, sao chép có xử lý lỗi; kiểm tra nguồn/số dư qua luồng đồng bộ hiện hữu |
| Báo cáo phí | Chọn khách, đọc báo cáo nghiệp vụ, giữ riêng tiền tệ; phí nguồn tách chi tiêu, không cộng tiền tệ hoặc tự gọi là đã thu; sao chép báo cáo gửi khách |
| `/bms` | Trang riêng có tìm kiếm, lọc BM cho thuê, phân trang, VIA quản lý, số TKQC và bật/tắt vai trò cho thuê qua API hiện hữu |
| `/vias` | Giữ luồng trình duyệt, đăng nhập, lấy phiên, 2FA, nhập tay và đồng bộ có sẵn; đồng bộ bộ lọc từ tìm kiếm toàn cục; chuẩn hóa nhãn, màu, trạng thái theo theme |
| `/customers` | Bảng/thẻ, tìm tên/Telegram, phân trang, số tài khoản, chi tiêu theo tiền tệ; modal tạo/sửa tên, Telegram, phí riêng và gán thêm TKQC; API nội bộ kiểm tra quyền local, Decimal, trùng tên và audit |
| `/analytics` | Biểu đồ xu hướng, cơ cấu BM theo từng tiền tệ từ ảnh đọc lũy kế, biểu đồ khách theo báo cáo nghiệp vụ; liên kết rủi ro TKQC/VCC |
| `/auto-set-camp` | Danh sách và tạo bản nháp có tên/mục tiêu/ngân sách, trạng thái tạm dừng; danh sách lệnh đang chờ, sao chép mã; không tự chạy hoặc đánh dấu hoàn thành lệnh |
| `/settings` | Các tab chung/phí/Telegram/giao diện; lưu tên không gian và mức điền sẵn cho khách mới; đổi sáng/tối và mật độ bảng; mở đúng cấu hình nguồn tỷ giá, Bot, Meta, ví và sàn |
| Tương thích | Giữ màn hình trước tại `/operations`, tổng tài chính tại `/customers/finance`, giữ các route cũ `/reports`, `/config`, `/clients`, `/telegram`, `/campaigns` và các trang chi tiết |

## Độ đúng dữ liệu và phạm vi nghiệp vụ

- Chi tiêu và phí chưa có nguồn live không được trình bày như số tiền thật; chế độ thử nghiệm có trạng thái riêng, biểu đồ thật không lấy dữ liệu thử nghiệm để lấp chỗ trống.
- Phí đối soát không phải tiền đã thu hoặc lợi nhuận ròng. Chưa có nguồn xác nhận thực thu thì không tạo số thực thu.
- Top TKQC lấy ảnh đọc lũy kế và được ghi rõ. Không tự dùng snapshot lũy kế làm chi tiêu riêng hôm nay (D-008/D-038/D-059).
- Cơ cấu BM là ảnh đọc lũy kế hiện tại, không giả lập thành số liệu lịch sử cho bộ lọc ngày.
- Tỷ giá theo kỳ/nguồn được xác nhận; settings mở mapping nguồn, không tạo tỷ giá tài chính toàn cục để áp ngược lịch sử. Mức điền sẵn phí trên trình duyệt chỉ tác động form tạo khách, không thay đổi khách hiện hữu.
- Số liệu trạng thái hiện tại không chứng minh lịch sử đổi thẻ, tụt ngưỡng hay tỷ lệ sự cố. Những thống kê cần Q-014/Q-017 hoặc dữ liệu lịch sử vẫn chưa xác nhận.
- Tổng hợp số tiền trên giao diện dùng chuỗi thập phân/BigInt; chuyển sang Number chỉ để đặt tọa độ biểu đồ. Các tiền tệ không cộng chéo. `step="any"` trong input cũ là giá trị HTML, không phải kiểu TypeScript `any`; đã loại kiểu `any` khỏi mã TS/TSX.
- Tạo/sửa khách qua service có audit, Decimal và rào chắn quản trị local. Chỉ mở các form trong kiểm tra trình duyệt; các phép ghi kiểm thử dùng DB test riêng.

## Kiểm chứng

- Backend: 604 kiểm thử đạt; sau bổ sung rào chắn tạo khách đã chạy lại kiểm thử tập trung và bộ đầy đủ (kết quả cuối ghi ở PROJECT_STATUS).
- Frontend: TypeScript strict, Next.js build, 12 kiểm thử Node cho số tiền chính xác, làm tròn, CSV, ngày Việt Nam, so sánh ngày và lỗi API không lộ input.
- Chrome headless: tám trang × desktop 1440 px, tablet 1024 px, mobile 390 px; 24 lượt không tràn ngang, không có lỗi JavaScript. Đã kiểm tra chuyển theme, sidebar, drawer, phân trang, mở/đóng modal khách và tab giao diện.
- Không submit form nghiệp vụ thật, không gọi hành động đăng nhập Facebook/thẻ/giao dịch hoặc ghi Sheets trong kiểm tra trình duyệt. Chưa nghiệm thu quyền API/live của các dịch vụ ngoài bằng credentials thật.

Ảnh và kết quả kiểm tra ở `artifacts/ui-refactor/`: `dashboard-dark.png`, `dashboard-light.png`, `dashboard-mobile.png`, `mobile-navigation.png`, `browser-check.json`.

Lệnh chạy: `npm.cmd run dev` tại `apps/web`. Trang chính `/` và `/dashboard`. Không triển khai production.
