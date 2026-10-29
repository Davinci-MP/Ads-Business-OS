# PROJECT_ARCHITECTURE.md — Cấu trúc dự án

> Trước khi thêm/sửa service, connector hoặc cấu trúc dữ liệu → đọc tài liệu này. Có đề xuất kiến trúc thay đổi → cập nhật tài liệu này trước, rồi mới code.

## 1. Kiểu xây dựng

**Monorepo** gồm 3 khối: backend (FastAPI), frontend (Next.js), tài liệu/skill OpenCode.

```
ads-business-os/
├── AGENTS.md                 # Hướng dẫn bắt buộc cho OpenCode
├── opencode.json             # Cấu hình OpenCode: auto-load docs + skills
├── docs/                     # BUSINESS_RULES, CAMPAIGN_RULES, FINANCE_RULES,
│                             # PROJECT_ARCHITECTURE, DEVELOPMENT_RULES,
│                             # PROJECT_STATUS, DECISIONS
├── .opencode/skills/         # Skill hướng dẫn cho agent
├── apps/
│   ├── api/                  # FastAPI (Python 3.12)
│   │   ├── app/
│   │   │   ├── main.py       # Entry point FastAPI
│   │   │   ├── core/         # Config/env, bảo mật, deps
│   │   │   ├── models/       # SQLAlchemy ORM models
│   │   │   ├── schemas/      # Pydantic schemas
│   │   │   ├── api/v1/       # Routers REST
│   │   │   ├── services/     # Logic rule kinh doanh
│   │   │   ├── connectors/   # meta, sheets, telegram, tron
│   │   │   └── jobs/         # Scheduler (cron/APScheduler)
│   │   ├── alembic/          # Migrations (cần reversible)
│   │   ├── tests/            # pytest (unit + integration)
│   │   └── pyproject.toml
│   └── web/                  # Next.js + React (Dashboard)
│       ├── app/
│       └── package.json
├── infra/
│   ├── docker-compose.yml    # Local: postgres, api, web, scheduler
│   └── env/                  # .env.example per môi trường
└── .github/workflows/        # CI lint + test (sau scaffold)
```

## 2. Backend — FastAPI

- **Connectors** (`connectors/`): mỗi integration một module có interface tiếp xúc ngoài.
  - `meta.py` — Meta Marketing API (campaigns, insights).
  - `sheets.py` — Google Sheets API v4 (S6: chỉ đọc cấu trúc/giá trị ô, preview theo sheetId và mapping theo D-024/D-028; KHÔNG có method ghi; ghi có kiểm soát ở giai đoạn sau sau phê duyệt).
  - `telegram.py` — Telegram Bot API.
  - `tron.py` — TRON API (ví chung USDT TRC20).
- **Services** (`services/`): chỉ chứa logic kinh doanh, gọi connectors. Không trả HTTP response trực tiếp.
- **Jobs** (`jobs/`): mỗi job phải idempotent, có retry, không tự sửa công thức đã duyệt.

## 3. Mô hình dữ liệu (dự kiến sơ khởi, chi tiết hoá khi scaffold)

| Bảng | Ý nghĩa |
|---|---|
| `customers` | Thông tin khách (31), telegram_chat_id đánh dấu |
| `ad_accounts` | Ad account + BM + trạng thái (`ACTIVE`, `RESTRICTED`, `REPLACED`, `DEAD`) |
| `ad_account_assignments` | Liên kết khách ↔ account (N-N) theo thời gian |
| `campaigns` | Campaign + mã ngày + tên + khách sở hữu + kỳ báo cáo |
| `spend_snapshots` | Snapshot chi tiêu tích lũy (append-only, unique `(campaign_id, snapshot_at)`) |
| `drift_records` | Tiền trôi phát sinh sau khi campaign dừng |
| `ledger_transactions` | Ghi sổ vào từng khoản (chi tiêu thực / phí / đối soát / lợi nhuận) |
| `manual_reviews` | Đối chiếu thủ công (D-041): số quan sát tay vs baseline Sheets — MANUAL_REVIEWED/VISUALLY_REVIEWED, idempotent, không đè snapshot VERIFIED |
| `manual_review_observations` | Lịch sử quan sát append-only (D-042): mỗi lần kiểm tra hợp lệ = 1 dòng, `idempotency_key` UNIQUE, `observed_at` + `recorded_at`, late observation không ghi đè |
| `usdt_transactions` | Giao dịch TRC20, key unique `tx_hash`, có trạng thái match |
| `exchange_rates` | Bảng tỷ giá config (USDT/VND, thanh toán) |
| `sheet_mappings` | Mapping cấu trúc Google Sheets (sheet/cột → vai trò đối soát) — S6, module chỉ đọc (D-024/D-028); không đụng bảng thật |
| `approvals` / `audit_log` | Phê duyệt + lịch sử audit cho mọi ghi tài chính |

Tất cả bảng số mang **unique key chống ghi trùng** và **append-only** cho snapshot/flow (không update đè; ghi mốc mới).

## 4. Sơ đồ dòng dữ liệu V1

```
Meta Marketing API ──┐                                     ┌─→ PostgreSQL (ledger + snapshots)
Google Sheets ───────┼──→  apps/api (jobs + REST) ─────────┤
Telegram Bot ────────┤                                     └─→ apps/web (Dashboard)
TRON API (ví chung) ─┘
```

- Sync job chạy hằng giờ; checkpoint 09:00 giờ Việt Nam.
- Sheets: nguồn đọc đối soát; ghi chỉ qua approval (skill `google-sheets`).
- Web: chỉ đọc DB (trong V1 không qua Sheets trực tiếp).
- Tổng báo cáo Sheets theo năm đọc snapshot đã lưu qua `sheet_year_summary`: mỗi kỳ dùng bản chốt nếu có, kể cả sau khi thay nguồn, nếu không dùng bản hiện hành của nguồn đang hoạt động. Chỉ cộng phát sinh theo kỳ; số dư chọn một thời điểm, không cộng xuyên tháng. Tháng thiếu và nhiều bản chốt mâu thuẫn được báo rõ; không tự ghép khách hoặc ghi vào ledger.

## 5. Môi trường

| Môi trường | DB | Kết nối từ ngoài | Ghi |
|---|---|---|---|
| `local` | Postgres Docker; fallback SQLite nếu máy chưa có Docker | mock/local | tự do trong DB local |
| `staging` | Postgres staging | đọc thật (service account chỉ đọc, Meta token readonly) | **KHÔNG ghi bảng Sheets thật**; ghi vào DB staging |
| `production` | Postgres prod (bắt buộc Postgres) | đọc thật | chỉ với approval flow |

- Cấu hình phân biệt qua biến `APP_ENV` + file env tương ứng trong `infra/env/`.
- Mã nguồn phải có guard cho môi trường: hành động ghi Sheets thật phải bị chặn tại code khi `APP_ENV != production` (phòng thủ cả tầng infra).

## 6. Bảo mật & secret

- Secrets chỉ qua biến môi trường; `.env` nằm trong `.gitignore`.
- Google Sheets: dùng **service account** có quyền tối thiểu (reader cho staging; editor chỉ sau phê duyệt).
- Meta: token trong env; phạm vi quyền cần cho phép `ads_read`.
- TRON: địa chỉ ví trong config DB, key ký giao dịch (nếu có) phải nằm ngoài repo.
- Telegram: `TELEGRAM_BOT_TOKEN` từ env; webhook secret verify.

## 7. Khôi phục / Backup

- DB: `pg_dump` định kỳ (job); trước mỗi migration có backup.
- Mọi job ghi Sheets có backup dữ liệu cũ trước ghi.
- Quy trình khôi phục được hướng dẫn từng bước trong `DEVELOPMENT_RULES.md` khi code đã có.

## 8. Định hướng kiến trúc sản phẩm — đề xuất, chưa triển khai

Ưu tiên luồng nhập thủ công và đối chiếu trước khi tự động hóa. Các nội dung dưới đây mô tả ranh giới nghiệp vụ dự kiến; chưa phải thiết kế schema/API đã chốt và không được triển khai đồng loạt.

- **Sổ tiền và ngân sách**: tách giao dịch nhận tiền, phân bổ giao dịch, khoản chi tiêu, phí dịch vụ, dư nợ bàn giao TKQC và tiền TKQC. Báo cáo tổng hợp từ các khoản có nguồn và trạng thái; không ghi một số dư thay vì giữ lịch sử phát sinh.
- **Tỷ giá**: quản lý riêng USDT/VND nhận tiền và USD/VND tính chi tiêu, có nguồn, ngày hiệu lực và giá trị thực được áp dụng cho từng phát sinh. Không hồi tố. Cần chốt cách phân bổ lifetime spend qua các kỳ tỷ giá (Q-014) trước khi thiết kế phép tính.
- **Nhận tiền thủ công**: ghi nhận khoản thực nhận cùng bằng chứng/người xác nhận; các phân bổ là bản ghi riêng, có tổng kiểm soát không vượt khoản nhận. UNALLOCATED không được tính là ngân sách. Cách điều chỉnh/hoàn tác cần bám Q-018.
- **Sự kiện bàn giao TKQC**: lưu quan hệ account-khách theo thời gian và snapshot dư nợ/giá thu tại bàn giao; tách khoản phải thu hộ/tiền TKQC khỏi ngân sách chạy và chi phí mua account. Dữ liệu Meta lifetime không được dùng lại để cộng dư nợ đã ghi nhận trước bàn giao.
- **Cấu hình tích hợp**: giao diện có thể nhập/ủy quyền, nhưng secret chỉ lưu và dùng phía backend. Trạng thái lưu cấu hình, xác minh credential/quyền và bật đồng bộ là các trạng thái riêng; không đánh dấu đã kết nối chỉ vì đã lưu token. Chỉ triển khai connector khi API, quyền và sản phẩm tài khoản thực tế được xác minh. Nền tảng chưa hỗ trợ cần có trạng thái rõ.
- **Ads Check Pro**: dự kiến hiển thị TKQC, BM, Page và kết nối Facebook. Phân biệt BM sở hữu, BM nhận chia sẻ, Facebook có quyền, khách được gán nội bộ và quyền thực tế trên Meta. Gán trong ứng dụng không chứng minh đã mời/cấp quyền. Đọc trước; thao tác mời/cấp quyền sau khi xác minh API và quyền. Một ad account duy nhất theo ID, dù xuất hiện qua nhiều kết nối, không được đếm hai lần.
- **Báo cáo khách/tháng**: hướng đến spend, fee, profit có căn cứ, ngân sách, công nợ quảng cáo, tiền TKQC/thu hộ, lịch sử cấp và thay account, độ phủ và thời điểm cập nhật. Chỉ đưa KPI sự cố vào khi định nghĩa/mẫu số được chốt (Q-017); không kết luận lợi nhuận khi thiếu chi phí thực.
- **Mở rộng sau**: màn hình công việc vận hành, nguồn tiền PingPong/thẻ/ngân hàng, nhiều người dùng/phân quyền/cổng khách, hỗ trợ nội dung/góc tiếp cận/target theo Page và mẫu setup chiến dịch. Telegram bot tạm gác, không phải điều kiện nhập liệu. Quản lý hồ sơ trình duyệt mới là ý tưởng, chưa có yêu cầu kỹ thuật.

Không yêu cầu Meta MCP làm điều kiện tiên quyết. Các field như spend cap, hạn mức ngày do Meta áp đặt, balance Meta, số dư thẻ/ngân hàng, ngày thu và ân hạn phải được xác minh trước khi đưa ra nhãn hoặc cam kết.


## Kết nối sàn — hoàn thiện 2026-10-29
Binance Spot/Funding chỉ đọc; credentials Fernet phía backend, master key qua env. Quản trị local yêu cầu token riêng qua header, không lưu token trên browser. Connector có whitelist, parser strict; snapshot giữ free/locked/freeze/withdrawing. Không cộng nguồn blockchain với tài khoản sàn. UI /config/wallets; OKX/MEXC chưa hỗ trợ.
