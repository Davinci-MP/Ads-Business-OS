# Kiểm tra kết nối PingPong — 2026-11-03

## Phạm vi xác minh

Trang được chủ dự án cung cấp: https://developer.pingpongx.com/apiDocs/main

Đây là trang chọn nhiều bộ API, không phải API gateway. Mã trang chọn business từ query `business`, mặc định `Issuing`; phiên bản mặc định là phần tử đầu trong danh sách phiên bản. Tại thời điểm kiểm tra, mặc định là Issuing 2.7.1. Các mục khác gồm Flowmore, Currentz, Checkout, B2B và MPT. Không suy API được cấp cho tài khoản chỉ từ đường dẫn `/main`.

## Hợp đồng Issuing 2.7.1 đã kiểm tra

| Mục | Theo tài liệu chính thức |
|---|---|
| Production gateway | `https://gateway.pingpongx.com` |
| Sandbox gateway | `https://sandbox-gateway.pingpongx.com` |
| Credentials | `app_id`, `app_secret` được cấp cho ứng dụng; khác vai trò Merchant/Client ID |
| Lấy token | `GET /v2/token/get`, tham số query `app_id`, `app_secret` |
| Số dư | `GET /v2/vcc/open/account/balance/all`, header Authorization với token |
| Danh sách thẻ | `GET /v2/vcc/open/cards`, có phân trang `start_page`, `row` |
| Mã nghiệp vụ | `code = 6666` biểu thị thành công; không coi riêng HTTP 200 là thành công |
| Quyền | Không tìm thấy endpoint xác minh quyền khóa trong đặc tả đã đọc; không tự tạo trường quyền hoặc trả read_only=True khi API lỗi |

Không ghi request URL lấy token vào log vì query có secret. Không tự theo redirect mang token hoặc gửi credentials tới website. Không sử dụng bất kỳ credentials mẫu trong tài liệu cho kết nối thật.

Nguồn công khai mà chính trang sử dụng:

- https://cdn17.pingpongx.com/light/openAPI/apiDocs/baseInfo.json
- https://cdn17.pingpongx.com/light/openAPI/apiDocs/versionList.json
- https://cdn17.pingpongx.com/light/openAPI/apiDocs/Issuing/2.7.1.json

## Tình trạng connector trong repo

Chủ dự án đã xác nhận dùng **Issuing 2.7.1**. Connector được cập nhật theo hợp đồng phía trên, thay `/oauth/token`, `/v1/balances`, `/v1/cards` và chữ ký HMAC cũ. Form dùng App ID/App Secret, mặc định gateway production; chỉ cho phép hai gateway chính thức. Merchant ID cũ chỉ giữ như metadata, không truyền vào xác thực Issuing.

Đã bỏ `api_permissions()` và fallback read_only=True. Kết quả kiểm tra kết nối và bản ghi giữ `read_only_verified=False`: đọc thành công không chứng minh khóa chỉ có quyền đọc. Ứng dụng chỉ cung cấp GET token/số dư/danh sách thẻ, không có phương thức ghi/tạo thẻ/chuyển tiền. Người vận hành vẫn cần dùng khóa có quyền phù hợp và IP whitelist của PingPong. Chưa nghiệm thu bằng credentials thật.

Token chỉ được gửi tới gateway chính thức; query lấy token được bỏ khỏi request trước khi httpx ghi log/hiển thị lỗi. Không tự theo redirect. Danh sách thẻ đọc phân trang, chỉ giữ 4 số cuối, không đọc endpoint full PAN/CVV; hạn mức/số dư thẻ không có trong API danh sách giữ trống. Số dư thiếu/lỗi hoặc nhiều budget cùng tiền tệ chưa thể phân biệt trong model hiện tại sẽ báo lỗi và giữ snapshot cũ, không gộp hoặc bỏ âm thầm. UI không tự cộng free + pending thành tổng bằng float.

Để kết nối: nhập App ID/App Secret Issuing vào UI, để Base URL trống hoặc chọn `https://gateway.pingpongx.com` (production); dùng gateway sandbox chỉ với khóa sandbox. Khi sửa Base URL của kết nối cũ có thể giữ trống hai ô khóa để tái sử dụng ciphertext; backend kiểm tra lại trước khi lưu thay đổi. Không tự đổi cấu hình DB thật hoặc sử dụng khóa đã gửi qua chat.

## NEEDS_CONFIRMATION — Q-019

Business/version đã được xác nhận là Issuing 2.7.1; không còn chờ câu hỏi này. Quyền của khóa thật và IP whitelist/khả năng đọc tài khoản vẫn cần xác minh khi người dùng tự kết nối. Không yêu cầu gửi App Secret/API Secret trong chat. Các API thu tiền Currentz/Flowmore và nhà cung cấp khác vẫn ngoài phạm vi triển khai này.
