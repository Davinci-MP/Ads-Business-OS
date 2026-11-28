-- Dọn dữ liệu Meta GIẢ LẬP (mock) bị job ghi vào DB server trước PR #17.
-- Chủ dự án đã đồng ý dọn (2026-11-28). Chỉ xóa dòng mock: tài khoản 'act_mock_%' và
-- dữ liệu con của chúng. KHÔNG đụng audit_log (nhật ký thật) và dữ liệu của tài khoản thật.
-- Chạy trên Postgres (Railway → Postgres → Data → Query). Chạy BƯỚC 1 trước để xem số dòng.

-- ===================== BƯỚC 1: XEM TRƯỚC (không thay đổi gì) =====================
WITH mock_acc AS (
    SELECT id FROM ad_accounts WHERE meta_ad_account_id LIKE 'act\_mock\_%' ESCAPE '\'
), mock_cmp AS (
    SELECT id FROM campaigns WHERE ad_account_id IN (SELECT id FROM mock_acc)
)
SELECT 'ad_accounts' AS bang, count(*) AS so_dong FROM mock_acc
UNION ALL SELECT 'campaigns', count(*) FROM mock_cmp
UNION ALL SELECT 'spend_snapshots', count(*) FROM spend_snapshots WHERE campaign_id IN (SELECT id FROM mock_cmp)
UNION ALL SELECT 'drift_records', count(*) FROM drift_records WHERE campaign_id IN (SELECT id FROM mock_cmp)
UNION ALL SELECT 'ad_account_assignments', count(*) FROM ad_account_assignments WHERE ad_account_id IN (SELECT id FROM mock_acc)
UNION ALL SELECT 'meta_account_risks', count(*) FROM meta_account_risks WHERE account_id LIKE 'act\_mock\_%' ESCAPE '\';

-- ===================== BƯỚC 2: XÓA (một transaction, lỗi là hoàn tác hết) =====================
BEGIN;

CREATE TEMP TABLE mock_acc ON COMMIT DROP AS
    SELECT id FROM ad_accounts WHERE meta_ad_account_id LIKE 'act\_mock\_%' ESCAPE '\';
CREATE TEMP TABLE mock_cmp ON COMMIT DROP AS
    SELECT id FROM campaigns WHERE ad_account_id IN (SELECT id FROM mock_acc);

DELETE FROM drift_records WHERE campaign_id IN (SELECT id FROM mock_cmp);
DELETE FROM spend_snapshots WHERE campaign_id IN (SELECT id FROM mock_cmp);
DELETE FROM campaigns WHERE id IN (SELECT id FROM mock_cmp);
DELETE FROM ad_account_assignments WHERE ad_account_id IN (SELECT id FROM mock_acc);
UPDATE ad_accounts SET replaced_by_id = NULL WHERE replaced_by_id IN (SELECT id FROM mock_acc);
DELETE FROM ad_accounts WHERE id IN (SELECT id FROM mock_acc);
DELETE FROM meta_account_risks WHERE account_id LIKE 'act\_mock\_%' ESCAPE '\';

COMMIT;
