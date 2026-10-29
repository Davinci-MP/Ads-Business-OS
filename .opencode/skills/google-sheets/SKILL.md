---
name: google-sheets
description: Use when reading or (only with approval) writing the production Google Sheets workbook, dealing with Google Sheets API / service account setup, reconciling Meta spend or debt with the live Sheets, mapping sheet/tab/column structures, fixing spreadsheet formulas, or planning dry-run/backup around real Sheets data. Staging never writes to the real workbook; live structure must not change.
---

# Google Sheets

Bảng Google Sheets đang **vận hành thật** — cấu trúc, tên sheet, cột và công thức là bất biến cho đến khi chủ dự án phê duyệt đổi. Tham khảo `docs/DEVELOPMENT_RULES.md` §3 và `docs/FINANCE_RULES.md`.

## Nguyên tắc

1. **Đọc là mặc định. Ghi là ngoại lệ có phê duyệt** (D-024: không ghi bảng thật khi chưa phê duyệt; thử nghiệm chức năng mới chỉ trên bản sao). Thiếu mục duyệt → không cam kết ghi dữ liệu thật.
2. Không đổi cấu trúc/công thức; không thêm sheet; không định dạng lại — kể cả "cho gọn".
3. Ghi thật phải theo trình tự: **dry-run vào bản copy** → preview đối soát khác biệt → backup giá trị cũ → ghi → kiểm tra công thức còn nguyên → audit log.
4. Spreadsheet ID và credentials qua biến môi trường (`GOOGLE_SHEETS_SPREADSHEET_ID` + service account JSON bên ngoài repo).
5. Staging dùng service account quyền **Reader**; chỉ Production có Editor và chỉ sau phê duyệt.

## Quy trình đọc

1. Liệt kê sheet + header metadata trước khi dùng — không assume tên sheet/cột. D-028 cho phép xây module **đọc + phân tích cấu trúc + mapping**; ghi chỉ test trên bản sao, KHÔNG ghi/sửa bảng Production. Cấu trúc bảng thực tế vẫn chờ chủ dự án cung cấp (Q-007).
2. Đọc raw, chuyển đổi theo mapping đã duyệt; chuẩn hoá số (dấu phẩy, đơn vị, kiểu trống).
3. So sánh với Postgres → **xuất báo cáo chênh lệch**, không tự "sửa" bên Sheets.

## Quy trình ghi (chỉ khi có phê duyệt)

1. Xin phép chủ dự án và ghi quyết định vào `docs/DECISIONS.md`.
2. Chuẩn bị dry-run: giá trị sẽ ghi + chênh lệch + bản copy demo.
3. Backup range cũ; thực thi qua API chính thức; đọc lại xác nhận.
4. Audit log: người duyệt, nội dung, thời điểm; có hướng dẫn restore từ backup nếu sai.

## Quy trình kiểm thử

- **Unit:** parse/normalize dùng fixture dữ liệu mẫu thu nhỏ (thiếu cột, giá trị lạ, định dạng khác).
- **Integration:** chỉ dùng **bản copy workbook** trên staging → tạo sheet copy → đọc/ghi → verify công thức (ví dụ `=SUM(...)`) không bị phá.
- **Rollback:** thực hiện ghi vào bản copy → restore từ backup → dữ liệu nguyên vẹn.
- Tuyệt đối không test ghi trực tiếp vào bảng thật, kể cả sửa 1 ô nhỏ.
