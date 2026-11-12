"""Lưu lịch sử tác vụ tạo chiến dịch Meta Ads có kiểm soát (Controlled Write Path).

Reversible migration:
- upgrade: tạo bảng meta_campaign_tasks.
- downgrade: xoá bảng meta_campaign_tasks.
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meta_campaign_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ad_account_id", sa.String(64), nullable=False),
        sa.Column("campaign_name", sa.String(255), nullable=False),
        sa.Column("objective", sa.String(64), nullable=False),
        sa.Column("daily_budget", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("meta_campaign_id", sa.String(64), nullable=True),
        sa.Column("meta_adset_id", sa.String(64), nullable=True),
        sa.Column("meta_ad_id", sa.String(64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False, server_default="telegram_bot"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_meta_campaign_tasks_ad_account_id",
        "meta_campaign_tasks",
        ["ad_account_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_meta_campaign_tasks_ad_account_id", table_name="meta_campaign_tasks")
    op.drop_table("meta_campaign_tasks")
