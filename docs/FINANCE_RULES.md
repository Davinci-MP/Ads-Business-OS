# FINANCE_RULES.md — Quy tắc tài chính

> Bắt buộc đọc trước khi đụng vào logic tiền. **Không tự đặt ra công thức tài chính mới.** Công thức đã duyệt nằm trong `docs/DECISIONS.md`; chưa rõ → gắn `NEEDS_CONFIRMATION` và hỏi chủ dự án.

## 1. Phân tách các khoản (bắt buộc)

Các khoản được quản lý **riêng biệt, không trộn sổ**:

1. **Chi tiêu thực** — số chi tiêu Meta phát sinh thật, nguồn từ sync Meta (xem `CAMPAIGN_RULES.md`).
2. **Dữ liệu đối soát theo hợp đồng** — số đã thỏa thuận/khế ước với từng khách.
3. **Phí tài khoản** — chi phí duy trì/khai/mua account, thay account.
4. **Phí thẻ** — phí thanh toán thẻ bên cung cấp.
5. **Lợi nhuận** — suy ra từ các sổ trên, không tự là một nguồn dữ liệu.
6. **Phí dịch vụ** — 4% mặc định trên chi tiêu thực (D-021), là khoản riêng trong ledger.

Mỗi khoản một sổ riêng trong DB; không cộng gộp vào nhau.

## 2. Tỷ giá

- Có hai tỷ giá độc lập, không dùng thay thế lẫn nhau:
  - **USDT/VND nhận tiền**: người vận hành nhập theo nguồn đã chọn cho lần nhận tiền.
  - **USD/VND tính chi tiêu**: dùng để quy đổi chi tiêu TKQC USD sang ngân sách VND.
- Tỷ giá có ngày hiệu lực; thay đổi tỷ giá không tự tính lại giao dịch hoặc ngày đã ghi nhận trước đó. Lưu lịch sử tỷ giá, nguồn và tỷ giá thực tế đã áp dụng cho từng phát sinh.
- Chi tiêu Meta hiện được lưu dạng lifetime cumulative. **Không nhân toàn bộ lifetime spend với tỷ giá hiện hành**. Cách phân tách phần chi tiêu thuộc từng kỳ hiệu lực tỷ giá chưa được chốt; trước khi triển khai quy đổi/billing phải giải quyết Q-014. Khi dữ liệu không đủ để phân tách, báo rõ phần chưa xác định và không tự suy diễn.
- Nguồn cụ thể, cách ghi nhận nguồn và quy tắc thời điểm/ngày hiệu lực cần được chốt thêm tại Q-005.

## 2.1 Ngân sách VND, nhận tiền và phân bổ — ĐÃ DUYỆT (D-043/D-044, 2026-10-27)

- Ngân sách quảng cáo của khách theo dõi bằng **VND**. Giữ nguyên giá trị và currency gốc của từng giao dịch/snapshot (USDT, USD, VND); quy đổi tạo giá trị liên quan, không thay thế dữ liệu nguồn.
- Với khoản USDT được xác nhận nhận thực tế và phân bổ vào ngân sách:
  - `Ngân sách VND được ghi có = USDT phân bổ cho ngân sách × tỷ giá nhận USDT/VND áp dụng cho giao dịch`.
  - Chỉ phần phân bổ vào ngân sách được quy đổi/ghi có. Phần dùng cho mục đích khác hoặc chưa xác định không được nhập vào ngân sách quảng cáo.
- Với chi tiêu TKQC bằng USD, sau khi xác định được phần chi tiêu thuộc kỳ tỷ giá:
  - `Chi tiêu VND = Chi tiêu USD × tỷ giá tính chi tiêu USD/VND áp dụng`.
  - `Phí dịch vụ VND = Chi tiêu VND × mức phí đã xác nhận trong hồ sơ khách`.
  - `Tổng trừ ngân sách = Chi tiêu VND + Phí dịch vụ VND`.
- Mức phí mặc định 4% tiếp tục theo D-021 khi hồ sơ khách chưa có mức riêng được xác nhận. Không áp 4% ghi cứng đè lên quy tắc riêng của khách. Tiền TKQC và khoản thu hộ dư nợ khi bàn giao không chịu phí dịch vụ quảng cáo.
- Số dư ngân sách có thể âm (nợ). Báo cáo phải phân biệt **số dư thanh toán/ngân sách còn lại** với **khả năng chi Meta sau khi tính phí**; công thức chuyển đổi sang khả năng chi Meta chưa được tự định nghĩa.
- Lưu giao dịch nhận tiền tách biệt với các phân bổ. Mỗi giao dịch có thể chia cho `AD_BUDGET`, `PRE_HANDOFF_AD_DEBT`, `AD_ACCOUNT_FUNDS`, hoặc `UNALLOCATED`; tổng phân bổ không được vượt số USDT thực nhận. Phần chưa phân bổ giữ trạng thái riêng, không tự cộng ngân sách.
- Lưu bằng chứng giao dịch, thời điểm nhận/xác nhận, người xác nhận và lịch sử điều chỉnh; chống ghi trùng giao dịch ở mức database. Luồng nhập/xác nhận hiện tại phải sử dụng được thủ công, không phụ thuộc Telegram hay tự động kết nối ví.
- Ví dụ: nhận 1.000 USDT, phân bổ 100 USDT thanh toán hộ dư nợ, 15 USDT tiền TKQC, 885 USDT vào ngân sách → chỉ 885 USDT được quy đổi và ghi có ngân sách.

## 3. Phí dịch vụ 4% (mặc định) và chế độ 30/70

### 3.1 Phí dịch vụ — mức mặc định D-021, cơ sở VND D-043

- Mức mặc định vẫn là **4%** theo D-021, nhưng phải dùng mức riêng trong hồ sơ khi mức đó đã được xác nhận cho khách.
- Chi tiêu thực tế lấy từ dữ liệu Meta đã đối soát; trước khi tính tiền phải quy đổi phần USD theo đúng kỳ tỷ giá sang VND (Q-014).
- Công thức áp dụng sau quy đổi:
  - `Chi tiêu VND = Chi tiêu USD × tỷ giá USD/VND áp dụng`
  - `Phí dịch vụ VND = Chi tiêu VND × mức phí đã xác nhận của khách`
  - `Tổng trừ ngân sách = Chi tiêu VND + Phí dịch vụ VND`
- Phí dịch vụ phải **hiển thị thành khoản riêng**, không gộp vào chi tiêu Meta.
- Không dùng công thức phí này cho tiền TKQC hoặc khoản thu hộ dư nợ trước bàn giao tài khoản.

### 3.2 Chế độ chia lợi nhuận 30/70 (điều chỉnh thủ công) — ĐÃ DUYỆT cơ chế (D-022, 2026-10-26)

- Chế độ đặc biệt, **mặc định TẮT**. Chỉ bật khi chủ dự án chủ động cấu hình cho khách được chọn (`customers.recon_mode = PROFIT_SHARE`).
- **Số liệu điều chỉnh do chủ dự án nhập tay** — KHÔNG tự tạo hoặc suy diễn số liệu điều chỉnh từ Meta; KHÔNG tự thay đổi dữ liệu chi tiêu thực tế.
- Dữ liệu điều chỉnh lưu ở **bảng riêng** (`manual_adjustments`), có nhật ký và **phê duyệt** (`DRAFT → APPROVED → APPLIED`).
- KHÔNG áp dụng chế độ 30/70 cho khách thông thường — tạo điều chỉnh cho khách không bật chế độ phải bị từ chối.
- **Công thức phân chia lợi nhuận** chỉ áp dụng sau khi chủ dự án xác nhận cách tính chính thức (Q-004).
- Lợi nhuận = phí − chi phí account-billed (TẠM TÍNH, Q-004).

### 3.3 Tiền trôi & chi tiêu hiện hành — ĐÃ DUYỆT (D-023, 2026-10-26)

- Đồng bộ chi tiêu tích lũy mỗi giờ; mốc đối soát cố định **09:00 giờ Việt Nam**.
- Chi tiêu hiện tại cập nhật theo dữ liệu Meta mới nhất.
- `Tiền trôi = Chi tiêu hiện tại − Chi tiêu mốc 09:00` (cùng kỳ đối soát).
- Không cộng trùng chi tiêu sau mỗi lần cập nhật.
- Phí dịch vụ 4% phải được **tính lại trên số chi tiêu hiện hành**.
- Khi Meta điều chỉnh muộn → cập nhật các khoản tạm tính (state `TEMP`), **giữ nguyên lịch sử đã chốt** (state `FINAL`).

### 3.4 Đối chiếu thủ công (manual_reviews) — ĐÃ DUYỆT (D-041, 2026-10-27)

- Hoạt động **KHÔNG cần Meta token** — dùng khi pipeline Meta chưa có token / campaign chỉ có thể kiểm bằng mắt trong Ads Manager.
- `MANUAL_REVIEWED`: chủ dự án nhập **số quan sát tay** → chênh lệch với baseline Sheets → `MATCH`/`DIFF` theo tolerance; không có giá trị Sheets → `NEEDS_SHEET_BASELINE` (tổng chỉ quan sát, không tự phán).
- `VISUALLY_REVIEWED`: chỉ kiểm **bằng mắt**, không nhập số → trạng thái `VISUAL_ONLY`, **KHÔNG được tự coi là MATCH**.
- Snapshot `META_API_VERIFIED` từ Meta **không bao giờ bị đổi nhãn** bởi review.
- Review idempotent theo unique `(customer_id, ad_account_meta_id, campaign_meta_id, business_date)` + audit log; lưu kho (`manual_reviews`), không cộng trùng vào tổng billing.
- Dữ liệu thiếu → hiển thị `None` + "CHƯA ĐỦ DỮ LIỆU" (KHÔNG 0 giả); USDT giữ đơn vị riêng — không cộng với VND; công nợ ≠ profit ≠ cash flow.

### 3.5 Nghiệm thu S17.1 — ĐÃ DUYỆT (D-042, 2026-10-27)

- **Lịch sử quan sát append-only** (`manual_review_observations`): mỗi lần kiểm tra hợp lệ = 1 dòng; `idempotency_key` UNIQUE — retry cùng key trả kết quả cũ, không ghi thêm; `observed_at` = thời điểm quan sát thực; quan sát đến muộn vẫn lưu nhưng **không ghi đè** dòng hiện hành mới hơn; quan sát tay không bao giờ thành checkpoint 09:00 / `META_API_VERIFIED`.
- **Kết luận MATCH/DIFF chỉ ở mức Customer + Account + Business Date + Currency.** Điều kiện đủ: mapping CONFIRMED (baseline không phải preview) + baseline hợp lệ + đúng khách/account/ngày + người dùng xác nhận đủ tập campaign + cùng currency (USD/VND theo tolerance D-038; GBP/EUR thiếu tỷ giá duyệt → `NEEDS_CONFIRMATION`) + không xung đột phân bổ. Thiếu bất kỳ → `INCOMPLETE`/`NEEDS_CONFIRMATION`/`NEEDS_SHEET_BASELINE` — **không tự phán**. Tổng tích lũy các campaign so với baseline account+ngày tính **một lần** (không cộng theo campaign).
- **Báo cáo không trộn tiền tệ**: USD/VND/GBP/EUR/USDT không cộng chéo, nhóm theo currency (`*_by_currency`); phí dịch vụ tính riêng từng currency (khách VND vẫn vào doanh thu phí); không quy đổi khi thiếu tỷ giá duyệt (Q-005); profit chỉ tính phần USD đã có nguồn; KPI gắn `company_data_state` + `coverage` — mock mode / thiếu dữ liệu → không được gọi ĐẦY ĐỦ.
- **Sheets preview**: đọc Sheets không cần Meta Token; mapping chưa CONFIRMED → preview, `sheet_baseline_confirmed=False` → verdict `NEEDS_CONFIRMATION` (không chốt baseline).

## 4. USDT TRC20 & nạp tiền

- Giao dịch vào **một ví chung TRC20**, theo dõi qua **TRON API chính thức**.
- Giao dịch ghi nhận bằng key unique **tx hash** — hash trùng không tạo bản ghi mới (idempotent).
- **KHÔNG cộng tiền nạp cho khách khi chưa chắc giao dịch thuộc khách nào.**
  - Giao dịch chưa xác định → pool `UNMATCHED` (lưu hash, số tiền, thời gian, số confirm).
  - Match bằng: hash + số tiền + khung thời gian + khách khai báo khớp.
  - Sau khi match → chuyển sang ledger khách; phép gán phải có audit log.
- Quy tắc số xác nhận và matching vẫn theo Q-006. Có thể vận hành bằng nhập thủ công trong khi chưa tích hợp TRON API.

## 4.1 Cấp TKQC và bàn giao dư nợ — ĐÃ DUYỆT (D-045, 2026-10-27)

- Mỗi lần bàn giao liên kết khách hàng, ID TKQC, currency, BM liên quan và thời điểm bàn giao; lưu dư nợ có sẵn ngay trước bàn giao, USDT chốt thu để thanh toán hộ dư nợ, giá tiền TKQC bằng USDT và trạng thái/giá trị còn phải thu của từng khoản.
- Dư nợ có sẵn trước bàn giao do khách chịu. Dư nợ bàn giao và tiền TKQC là khoản phải thu riêng, không cộng vào ngân sách quảng cáo và không chịu phí dịch vụ quảng cáo 4%.
- Ví dụ đã xác nhận: dư nợ bàn giao 2.590.000 VND, tỷ giá chốt 25.900 VND/USDT → 100 USDT thu hộ; cộng 15 USDT tiền TKQC → tổng phải thu 115 USDT, không ghi có ngân sách chạy.
- Giá tham khảo: dư nợ 0–1 triệu VND → 25 USDT; 1–2 triệu → 20 USDT; 2–3 triệu → 15 USDT. Đây chỉ là hướng dẫn; người vận hành chủ động chọn/nhập giá. Không tự chọn giá tại biên trùng nhau hoặc dư nợ trên 3 triệu (Q-015).
- Quy ước 15/20/25 USD tương ứng 15/20/25 USDT chỉ dùng cho báo giá TKQC này, không suy rộng USD = USDT.
- Giữ lịch sử account được bàn giao giữa khách. Không cộng trùng dư nợ trước bàn giao với lifetime spend đã phát sinh trước thời điểm bàn giao.
- Giá thu khách và chi phí thực mua account là hai khoản riêng. Thiếu chi phí mua thực tế thì không kết luận toàn bộ tiền TKQC là lợi nhuận.

## 5. Công nợ & cảnh báo

- Công nợ tính từ ledger; lưu snapshot công nợ theo thời điểm, có thể khôi phục.
- **Cảnh báo số dư gần hết** bắn lên Telegram admin + dashboard.
- Ngưỡng cảnh báo theo từng khách → `NEEDS_CONFIRMATION` (Q-008), chưa duyệt thì không cài giá trị mặc định.

## 6. Phê duyệt & an toàn

- Giao dịch liên quan tiền thật (xác nhận nạp, điều chỉnh công nợ, ghi Sheets tài chính) phải qua **approval flow** và thực hiện bằng integration có quyền hợp lệ.
- Ghi vào Sheets tài sau phê duyệt: chạy qua audit log + backup + phương án khôi phục (xem `DEVELOPMENT_RULES.md`, skill `google-sheets`).
- Chống ghi trùng là **ràng buộc tầng DB** (unique constraint), không chỉ tầng app.
- Số liệu có nghi ngờ/data lỗi: **giữ số cũ**, giá trị mới gắn cờ `UNVERIFIED` chờ đánh giá.

## 7. Kiểm thử bắt buộc (tóm tắt)

- Khách thông thường (mặc định): phí dịch vụ = chi tiêu thực × 4%; tổng = chi tiêu + phí; phí là khoản riêng.
- Tính lại phí trên chi tiêu hiện hành; Meta điều chỉnh muộn → khoản tạm tính cập nhật, lịch sử đã chốt giữ nguyên.
- Chế độ điều chỉnh thủ công (30/70): chỉ khách bật chế độ mới tạo điều chỉnh được; flow `DRAFT → APPROVED → APPLIED`; công thức chia chưa duyệt → không được implement/chạy.
- Tiền trôi = chi tiêu hiện tại − mốc 09:00.
- Idempotency: giao dịch USDT hash trùng → không tạo bản mới.
- Approval flow: giao dịch chưa được duyệt phải bị chặn.
- Chi tiết đầy đủ trong skill `.opencode/skills/finance-reconciliation/SKILL.md`.
