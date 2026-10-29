"""S17.1 (D-042): bảng manual_review_observations append-only + cột hiện hành trên manual_reviews.

- Lịch sử quan sát: mỗi lần kiểm tra hợp lệ = 1 dòng, idempotency_key UNIQUE.
- Backfill: mỗi manual_reviews cũ tạo đúng 1 observation đầu tiên (giữ lịch sử).
- Reversible: downgrade drop bảng observation + drop cột thêm (giữ nguyên manual_reviews cũ).
"""
from alembic import op
import sqlalchemy as sa

from app.models.types import UTCDateTime

revision = "c3d4e5f6a7b8"
down_revision = "b1e5c7d9f241"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_review_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("review_id", sa.Integer(), sa.ForeignKey("manual_reviews.id"), nullable=False),
        sa.Column("observed_spend", sa.Numeric(16, 2), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("sheet_baseline", sa.Numeric(16, 2), nullable=True),
        sa.Column("delta_account_day", sa.Numeric(16, 2), nullable=True),
        sa.Column("match_status", sa.String(32), nullable=False, server_default="RECORDED"),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("observed_at", UTCDateTime(), nullable=False),
        sa.Column("recorded_at", UTCDateTime(), nullable=False),
        sa.Column("reviewed_by", sa.String(64), nullable=False, server_default="owner"),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_manual_review_observations_review", "manual_review_observations", ["review_id"])

    with op.batch_alter_table("manual_reviews") as batch:
        batch.add_column(sa.Column("last_observed_at", UTCDateTime(), nullable=True))
        batch.add_column(sa.Column("sheet_baseline_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("campaign_set_complete", sa.Boolean(), nullable=False, server_default=sa.false()))

    # Backfill: mỗi review cũ → đúng 1 observation (idempotency_key theo id — không trùng).
    # sheet_baseline_confirmed = 0 cho bản cũ: baseline cũ chưa chắc từ mapping CONFIRMED
    # → không tự coi là đã chốt (chờ chủ dự án xác nhận lại).
    op.execute(
        """
        INSERT INTO manual_review_observations
            (review_id, observed_spend, currency, sheet_baseline, delta_account_day,
             match_status, idempotency_key, observed_at, recorded_at, reviewed_by, note)
        SELECT id, observed_spend, currency, sheet_spend, delta, match_status,
               'backfill:' || id, created_at, created_at, reviewed_by,
               'backfill từ manual_reviews cũ (S17.1)'
        FROM manual_reviews
        """
    )
    op.execute(
        """
        UPDATE manual_reviews
        SET last_observed_at = created_at
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("manual_reviews") as batch:
        batch.drop_column("campaign_set_complete")
        batch.drop_column("sheet_baseline_confirmed")
        batch.drop_column("last_observed_at")
    op.drop_index("ix_manual_review_observations_review", table_name="manual_review_observations")
    op.drop_table("manual_review_observations")
