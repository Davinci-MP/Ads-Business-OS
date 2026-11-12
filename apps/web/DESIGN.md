# AdsOS Pro — Hệ thống giao diện quản trị

Nguồn chuẩn: `app/admin.css`, `components/admin-ui.tsx` và `tailwind.config.js`.

| Thành phần | Sáng | Tối |
|---|---|---|
| Nền trang | `#f6f8fb` | `#0b0f17` |
| Thẻ / bảng | `#ffffff` | `#121a29` |
| Bề mặt phụ | `#f3f6fb` | `#192235` |
| Nội dung chính | `#172338` | `#e9edf5` |
| Nội dung phụ | `#64748b` | `#96a3ba` |
| Viền | `#e4e9f1` | `#263247` |
| Điểm nhấn | Emerald `#059669` | Emerald `#10b981` |
| Điểm nhấn phụ | Indigo `#4f46e5` | Indigo `#818cf8` |

- Thẻ/bảng bo 12px; modal 14px; nút/input bo 8px. Font hệ thống có đầy đủ dấu tiếng Việt, không phụ thuộc font bản quyền.
- Sidebar desktop 256px/80px; drawer ở màn hình nhỏ; header 72px/64px. Nội dung tự co, bảng cuộn trong vùng riêng, không gây tràn ngang toàn trang.
- Theme qua `data-theme` và class `dark`, lưu `adsos.theme` trong localStorage. Các biến `--surface`, `--ink`, `--muted`, `--line` dùng chung cho màn hình mới và màn hình nghiệp vụ cũ.
- Dùng `PageHeading`, `Metric`, `Empty`, `ErrorNotice`, `Pagination`, `Modal`, `useToast`. Modal dùng dialog native; drawer giữ focus; tôn trọng giảm chuyển động của người dùng.
- Giữ nhãn tiếng Việt. Các trạng thái kỹ thuật/API không được mặc định thành số 0. Bốn loại toast tự đóng sau 4 giây.
- Recharts dùng nguồn báo cáo đã có, giữ riêng từng tiền tệ; không tạo dữ liệu mẫu để lấp biểu đồ. Chi tiêu lũy kế, chi tiêu theo ngày, phí đối soát và thực thu phải được ghi rõ nguồn và ý nghĩa.
- Định dạng tiền/số thập phân dùng `lib/admin-utils.mjs` hoặc helper sẵn có. Không tính tổng tiền bằng float; chỉ chuyển Number để vẽ tọa độ biểu đồ.
- Không thêm giao dịch/nguồn tiền hoặc thay công thức tài chính để đáp ứng một bố cục. Không hiển thị nút có thể gây hiểu nhầm là đã kết nối thật khi chưa có dữ liệu/quyền.

Chi tiết các màn hình và giới hạn nghiệm thu: `../../docs/UI_REFACTOR_REPORT.md`.
