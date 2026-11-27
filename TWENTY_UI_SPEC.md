# TWENTY CRM UI/UX SPECIFICATION FOR ADS BUSINESS OS

## 1. Triết lý thiết kế (Core Philosophy)
- **Tối giản mật độ cao (High-density Minimalism):** Tương tự Linear & Notion. Loại bỏ hoàn toàn bóng đổ (drop-shadow) rườm rà, hiệu ứng gradient lòe loẹt hay card bo góc quá lớn.
- **Phân tách bằng đường viền mỏng (Hairline Borders):** Sử dụng đường kẻ `1px solid` độ tương phản thấp để chia khối thay vì dùng nhiều màu nền khác nhau.
- **Icon đơn sắc (Monochrome Icons):** Sử dụng bộ icon nét mảnh (`stroke-width: 1.5px`, kích thước `16px`), màu xám trung tính, chỉ đổi sang màu sáng khi hover/active.

## 2. Hệ thống màu sắc (Dark Mode Palette)
- **Nền chính (Background Primary - Vùng bảng dữ liệu):** `#141414` hoặc `#171717`
- **Nền phụ (Background Secondary - Sidebar & Header):** `#1C1C1C`
- **Nền nổi / Hover (Surface Hover / Selected Row):** `#242424` / `#2A2A2A`
- **Đường viền chuẩn (Border Hairline):** `#2E2E2E` (chia cột, chia dòng, viền sidebar)
- **Đường viền focus (Border Active):** `#474747`
- **Chữ chính (Text Primary):** `#EBEBEB` (trắng dịu, không dùng trắng gắt `#FFFFFF` gây mỏi mắt)
- **Chữ phụ / Nhãn cột (Text Secondary / Muted):** `#8A8A8A`
- **Chữ mờ / Placeholder (Text Tertiary):** `#5C5C5C`
- **Màu nhấn (Accent Color):** `#1961ED` hoặc `#3B82F6` (chỉ dùng cho nút Primary Action chính như "+ Thêm VIA", "Nạp tiền" và trạng thái focus).
- **Trạng thái (Status Badges - Dạng Pill nhỏ nền mờ 15%):**
  - `Live / Active`: Chữ `#4ADE80`, nền `rgba(74, 222, 128, 0.12)`
  - `Hold / Checkpoint / Warning/ Error`: Chữ `#FACC15`, nền `rgba(250, 204, 21, 0.12)`
  - `Die / Disabled `: Chữ `#F87171`, nền `rgba(248, 113, 113, 0.12)`

## 3. Typography & Spacing
- **Font chữ:** `Inter`, hệ thống sans-serif chuẩn; dùng `JetBrains Mono` hoặc `Fira Code` (tabular-nums) cho các cột **UID, Ad Account ID, BM ID, Mã 2FA , Số tiền VND/USDT, Tỷ giá**.
- **Kích thước chữ:**
  - Tiêu đề trang: `16px` (`font-weight: 600`)
  - Dữ liệu trong bảng & Menu Sidebar: `13px` (`font-weight: 400` / `500`)
  - Nhãn tiêu đề cột (Table Header) & Tiêu đề nhóm Sidebar: `12px` (`font-weight: 500`, màu `#8A8A8A`)
- **Bo góc (Border Radius):** Rất gọn: `4px` cho nút bấm, input, badge; `6px` cho modal/dropdown.

## 4. Bố cục chuẩn (Layout Architecture)
- **Left Sidebar (Cố định `220px - 240px`, thu gọn được):**
  - Trên cùng: Tên Workspace (`CRM` / `FBPMEDIA`) + nút tìm kiếm nhanh (`Cmd/Ctrl + K`).
  - Nhóm **Vận hành (Operations)**: *Quản lý VIA*, *Business Managers (BM)*, *Tài khoản(TKQC)*, *Fanpages*.
  - Nhóm **Kinh doanh & Tài chính (Finance)**: *Khách thuê (Customers)*, * Nạp tiền*,.
  - Nhóm **Hệ thống (System)**: *Extension*, *Cấu hình Telegram & Binance*.
- **Main Workspace Area:**
  - **Top Bar (Cao `44px`):** Tên module bên trái + Các nút chuyển đổi View (`Table View` | `Kanban View`) + Nút hành động chính bên phải (`+ Import VIA`, `+ Tạo giao dịch`).
  - **Filter & Search Bar (Cao `36px`):** Thanh lọc nhanh theo trạng thái (`Live`, `Checkpoint`, `Hold`), tìm kiếm theo UID/ID và nút ẩn/hiện cột.
  - **Data Table (Bảng dữ liệu kiểu Notion/Airtable):**
    - Chiều cao mỗi dòng cố định `34px - 36px` (compact, hiển thị được nhiều tài khoản trên 1 màn hình).
    - Kẻ dọc mảnh giữa các cột, hover vào dòng hiện nút thao tác nhanh (Copy 2FA, Mở Profile Extension, Gán khách thuê).
    - Click vào một dòng sẽ mở **Right Slide-over Drawer (Ngăn kéo trượt từ bên phải rộng `480px - 600px`)** để xem chi tiết tài sản liên kết (VIA đang cầm BM nào, TKQC nào) mà không làm mất trang danh sách hiện tại.
    ## 5. Quy tắc kiến trúc mở rộng (Scalability Rules)
- **Tập trung hóa Menu:** Mọi mục trên Left Sidebar phải được cấu hình qua một file duy nhất `src/config/navigation.ts` (chia theo các nhóm: Operations, Finance, System).
- **Tái sử dụng UI Core:** Bắt buộc xây dựng bộ component dùng chung trong `src/components/twenty-core/` gồm: `AppShell`, `DataTable`, `StatusBadge`, `DetailDrawer`, và `FilterBar`. Mọi tính năng thêm mới trong tương lai đều phải lắp ghép từ bộ component này để đảm bảo đồng nhất 100% về giao diện.
- **Hỗ trợ Custom Fields (JSONB):** Các bảng chính (`via_profiles`, `ad_accounts`, `business_managers`, `customers`) cần hỗ trợ hiển thị các trường mở rộng lưu trong cột JSON `extra_fields` để có thể thêm cột mới trên UI mà không cần thay đổi cấu trúc bảng nhiều lần.