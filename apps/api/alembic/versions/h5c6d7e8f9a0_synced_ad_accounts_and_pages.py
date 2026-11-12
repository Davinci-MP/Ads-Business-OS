"""Tạo bảng synced_ad_accounts và synced_pages phục vụ SMIT Ads Check & Quản lý tài sản VIA.

Reversible migration:
- upgrade:
  - tạo bảng synced_ad_accounts (act_id, bm_id, account_type, balance, threshold, limit, total_spend, payment card, billing dates)
  - tạo bảng synced_pages (page_id, name, category, likes/followers, is_published)
- downgrade:
  - drop bảng synced_pages
  - drop bảng synced_ad_accounts
"""

from alembic import op
import sqlalchemy as sa

revision = "h5c6d7e8f9a0"
down_revision = "g4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Bảng synced_ad_accounts
    op.create_table(
        "synced_ad_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("via_profile_id", sa.Integer(), sa.ForeignKey("via_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bm_id", sa.String(64), nullable=True),
        sa.Column("account_type", sa.String(32), nullable=False, server_default="PERSONAL"),
        sa.Column("act_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status_dot", sa.String(32), nullable=False, server_default="LIVE"),
        sa.Column("account_status", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("balance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ad_trust_dsl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_spend", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(16), nullable=False, server_default="VND"),
        sa.Column("payment_card_brand", sa.String(32), nullable=True),
        sa.Column("payment_card_last4", sa.String(16), nullable=True),
        sa.Column("last_billed_date", sa.String(32), nullable=True),
        sa.Column("next_bill_date", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_synced_ad_accounts_act_id", "synced_ad_accounts", ["act_id"], unique=True)
    op.create_index("ix_synced_ad_accounts_via_profile_id", "synced_ad_accounts", ["via_profile_id"])
    op.create_index("ix_synced_ad_accounts_bm_id", "synced_ad_accounts", ["bm_id"])
    op.create_index("ix_synced_ad_accounts_account_type", "synced_ad_accounts", ["account_type"])
    op.create_index("ix_synced_ad_accounts_status_dot", "synced_ad_accounts", ["status_dot"])

    # 2. Bảng synced_pages
    op.create_table(
        "synced_pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("via_profile_id", sa.Integer(), sa.ForeignKey("via_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(128), nullable=True),
        sa.Column("likes_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("followers_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_synced_pages_via_profile_id", "synced_pages", ["via_profile_id"])
    op.create_index("ix_synced_pages_page_id", "synced_pages", ["page_id"])


def downgrade():
    op.drop_index("ix_synced_pages_page_id", table_name="synced_pages")
    op.drop_index("ix_synced_pages_via_profile_id", table_name="synced_pages")
    op.drop_table("synced_pages")

    op.drop_index("ix_synced_ad_accounts_status_dot", table_name="synced_ad_accounts")
    op.drop_index("ix_synced_ad_accounts_account_type", table_name="synced_ad_accounts")
    op.drop_index("ix_synced_ad_accounts_bm_id", table_name="synced_ad_accounts")
    op.drop_index("ix_synced_ad_accounts_via_profile_id", table_name="synced_ad_accounts")
    op.drop_index("ix_synced_ad_accounts_act_id", table_name="synced_ad_accounts")
    op.drop_table("synced_ad_accounts")
