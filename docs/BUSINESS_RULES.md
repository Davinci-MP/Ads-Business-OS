# BUSINESS_RULES.md — Quy tắc kinh doanh

> Nguồn sự thật của bối cảnh kinh doanh. Bất kỳ quy tắc nào chưa ghi ở đây và chưa được duyệt trong `docs/DECISIONS.md` → gắn `NEEDS_CONFIRMATION`, không tự hành động.

## 1. Bối cảnh kinh doanh

- Công ty chuyên **cung cấp tài khoản quảng cáo Facebook** cho khách. Hiện quản lý **31 khách hàng**.
- **1 khách ↦ nhiều ad account**; account dễ bị hạn chế/khóa → phải **thay thế liên tục**. Lịch sử account cũ và campaign cũ phải giữ nguyên (chỉ đổi trạng thái).
- Sử dụng **nhiều Facebook cá nhân + nhiều Business Manager (BM)** khác nhau.
- Khách liên hệ, yêu cầu và báo sự cố qua **Telegram**.
- Dữ liệu chi tiêu & công nợ hiện đang quản lý bằng **Google Sheets** (một bảng đang vận hành). Cấu trúc và công thức của bảng này là bất biến cho đến khi được phê duyệt thay đổi.
- Thanh toán: **USDT TRC20 vào ví chung** hoặc **chuyển khoản ngân hàng**.

## 1.1 Mục tiêu sản phẩm và ưu tiên

- Hệ thống giúp một người vận hành kiểm soát khách hàng, BM/TKQC và quyền sử dụng; ngân sách quảng cáo, phí dịch vụ, công nợ và nguồn thanh toán; chất lượng vận hành, báo cáo tháng và lợi nhuận có căn cứ.
- Ưu tiên **độ đúng của dữ liệu và báo cáo trước tự động hóa**. Hệ thống phải hỗ trợ nhập liệu thủ công, đối chiếu và truy vết khi chưa có API.
- Thiết kế có thể mở rộng về sau cho nhiều người dùng, phân quyền và cổng khách hàng; đây là định hướng, chưa phải phạm vi triển khai hiện tại.
- Telegram không phải điều kiện để vận hành các luồng nhập liệu và đối soát hiện tại.

## 2. Bảy phân hệ

| # | Phân hệ | Trách nhiệm chính |
|---|---|---|
| 1 | Quản lý khách hàng & ad account | CRUD khách, account, BM; thay thế account bị hạn chế |
| 2 | Đồng bộ campaign & chi tiêu | Meta Marketing API: chi tiêu tích lũy, mốc 9h, tiền trôi |
| 3 | Kết nối Google Sheets | Đọc chuẩn bảng hiện hành; ghi có kiểm soát (approval) |
| 4 | USDT / tỷ giá / thanh toán / công nợ | Nhận tiền, phân bổ thủ công, tỷ giá, ngân sách, công nợ |
| 5 | Telegram Bot | Hỗ trợ thông báo/nhập liệu về sau; không bắt buộc cho vận hành hiện tại |
| 6 | Phân tích | Lợi nhuận, tuổi thọ account, chi phí thay account, LTV |
| 7 | Dashboard | Miêu tả tổng thể toàn hệ thống cho chủ doanh nghiệp |

## 3. Quy tắc tổng quan đã duyệt

1. **Mọi giao dịch và thay đổi số liệu tài chính phải có lịch sử và cơ chế chống ghi trùng** (unique key + append-only).
2. **Không xoá dữ liệu lịch sử** — chỉ đổi trạng thái.
3. **Hành động liên quan tiền thật** (ghi công nợ, xác nhận nạp, điều chỉnh) **phải qua phê duyệt** và thực hiện bằng integration có quyền hợp lệ.
4. Dữ liệu API lỗi/chưa chắc chắn → không đè số đã xác nhận (xem `docs/CAMPAIGN_RULES.md` và `docs/FINANCE_RULES.md`).
6. **Phí dịch vụ theo hồ sơ khách**: mức mặc định 4% theo D-021 nếu khách chưa có mức riêng đã xác nhận. Khi có quy tắc riêng của khách, áp dụng mức trong hồ sơ đó; phí là khoản riêng, không gộp vào chi tiêu Meta. Cơ sở quy đổi chi tiêu sang VND và thứ tự tính được cập nhật tại D-043.
7. **Chế độ điều chỉnh thủ công (chia 30/70)**: mặc định TẮT, chỉ chủ dự án bật cho khách chọn lọc; số liệu điều chỉnh nhập tay vào bảng riêng có nhật ký + phê duyệt; không suy diễn từ Meta; không áp dụng cho khách thông thường; công thức chia chờ xác nhận (D-022, Q-004).
8. **Tiền trôi = chi tiêu hiện tại − chi tiêu mốc 09:00** cùng kỳ đối soát (D-023); phí 4% tính lại trên chi tiêu hiện hành; Meta điều chỉnh muộn → cập nhật khoản tạm tính, giữ lịch sử đã chốt.
9. **Đối chiếu thủ công (manual_reviews, D-041):** hoạt động KHÔNG cần Meta token. `MANUAL_REVIEWED` = chủ dự án nhập số quan sát tay → MATCH/DIFF theo tolerance; `VISUALLY_REVIEWED` = chỉ kiểm bằng mắt, KHÔNG được tự coi là MATCH; snapshot `META_API_VERIFIED` từ Meta không bao giờ bị đổi nhãn; dữ liệu không đủ → hiển thị "—" (KHÔNG 0 giả).
10. **Nghiệm thu S17.1 (D-042):** lịch sử quan sát append-only (`manual_review_observations`, idempotency key UNIQUE, `observed_at`, quan sát muộn không ghi đè); kết luận MATCH/DIFF **chỉ ở mức Customer + Account + Ngày nghiệp vụ + Currency** khi đủ điều kiện (mapping CONFIRMED + baseline hợp lệ + đủ tập campaign + cùng currency + không xung đột) — thiếu bất kỳ → `INCOMPLETE`/`NEEDS_CONFIRMATION`, không tự phán; báo cáo nhóm theo currency, không cộng chéo tiền tệ, không gọi ĐẦY ĐỦ khi mock/thiếu dữ liệu.
11. **Ngân sách khách ghi bằng VND**; các khoản USDT/USD gốc vẫn phải được lưu cùng tỷ giá thực áp dụng, không ghi mất đơn vị tiền ban đầu (D-043).
12. **Phân bổ giao dịch nhận tiền là nghiệp vụ riêng**: chỉ phần phân bổ vào ngân sách quảng cáo được quy đổi và ghi có ngân sách; phần chưa phân bổ không được tự tính là ngân sách (D-044).
13. **Cấp TKQC là sự kiện bàn giao có lịch sử**: dư nợ trước bàn giao, khoản thu hộ dư nợ và tiền TKQC phải tách khỏi ngân sách chạy quảng cáo và khỏi chi phí/lợi nhuận thực tế của tài khoản (D-045).

## 4. Các mục đang chờ xác nhận

- Xem bảng `NEEDS_CONFIRMATION` trong `docs/DECISIONS.md` (định dạng mã ngày của khách, công thức chia 30/70 chính thức, nguồn tỷ giá, ngưỡng cảnh báo, cấu trúc Google Sheets hiện hành, v.v.).
- Agent phát hiện quy tắc kinh doanh mới chưa được ghi chép → bổ sung NEEDS_CONFIRMATION, không tự hành động theo quy tắc tự nghĩ ra.
