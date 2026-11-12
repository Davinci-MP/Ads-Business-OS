"""Add campaign_drafts and remote_via_commands tables.

Revision ID: n1e2f3a4b5c6
Revises: m0d1e2f3a4b5
Create Date: 2026-11-06 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "n1e2f3a4b5c6"
down_revision = "m0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if "campaign_drafts" not in tables:
        op.create_table(
            "campaign_drafts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("draft_code", sa.String(length=64), nullable=False),
            sa.Column("draft_name", sa.String(length=255), nullable=False),
            sa.Column("source_via_uid", sa.String(length=64), nullable=True),
            sa.Column("source_act_id", sa.String(length=64), nullable=True),
            sa.Column("source_campaign_id", sa.String(length=64), nullable=True),
            sa.Column("objective", sa.String(length=64), server_default="OUTCOME_ENGAGEMENT", nullable=False),
            sa.Column("buying_type", sa.String(length=32), server_default="AUCTION", nullable=False),
            sa.Column("daily_budget", sa.Float(), server_default="500000.0", nullable=False),
            sa.Column("lifetime_budget", sa.Float(), nullable=True),
            sa.Column("bid_strategy", sa.String(length=64), server_default="LOWEST_COST_WITHOUT_CAP", nullable=False),
            sa.Column("targeting_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("page_id", sa.String(length=64), nullable=True),
            sa.Column("pixel_id", sa.String(length=64), nullable=True),
            sa.Column("post_id", sa.String(length=128), nullable=True),
            sa.Column("ad_creative_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("initial_status", sa.String(length=32), server_default="PAUSED", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_campaign_drafts_draft_code", "campaign_drafts", ["draft_code"], unique=True)

    if "remote_via_commands" not in tables:
        op.create_table(
            "remote_via_commands",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("via_id", sa.Integer(), sa.ForeignKey("via_profiles.id", ondelete="SET NULL"), nullable=True),
            sa.Column("via_uid", sa.String(length=64), nullable=False),
            sa.Column("act_id", sa.String(length=64), nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
            sa.Column("draft_id", sa.Integer(), sa.ForeignKey("campaign_drafts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("draft_name", sa.String(length=255), nullable=True),
            sa.Column("command_type", sa.String(length=64), server_default="SET_CAMP_FROM_DRAFT", nullable=False),
            sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("requested_by_telegram", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_remote_via_commands_via_id", "remote_via_commands", ["via_id"])
        op.create_index("ix_remote_via_commands_via_uid", "remote_via_commands", ["via_uid"])
        op.create_index("ix_remote_via_commands_act_id", "remote_via_commands", ["act_id"])
        op.create_index("ix_remote_via_commands_customer_id", "remote_via_commands", ["customer_id"])
        op.create_index("ix_remote_via_commands_draft_id", "remote_via_commands", ["draft_id"])
        op.create_index("ix_remote_via_commands_status", "remote_via_commands", ["status"])


def downgrade():
    op.drop_table("remote_via_commands")
    op.drop_table("campaign_drafts")
