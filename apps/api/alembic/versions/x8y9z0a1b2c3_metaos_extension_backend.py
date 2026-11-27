"""metaOs extension report sharing backend

Revision ID: x8y9z0a1b2c3
Revises: w7x8y9z0a1b2
Create Date: 2026-11-20 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "x8y9z0a1b2c3"
down_revision = "w7x8y9z0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extension_report_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("client_key_id", sa.Integer(), sa.ForeignKey("extension_client_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("account_name", sa.String(255), server_default="", nullable=False),
        sa.Column("currency", sa.String(16), server_default="", nullable=False),
        sa.Column("scope_type", sa.String(32), server_default="account", nullable=False),
        sa.Column("campaign_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("public_id", name="uq_extension_report_shares_public_id"),
    )
    op.create_index("ix_extension_report_shares_public_id", "extension_report_shares", ["public_id"])
    op.create_index("ix_extension_report_shares_client_key_id", "extension_report_shares", ["client_key_id"])
    op.create_index("ix_extension_report_shares_account_id", "extension_report_shares", ["account_id"])
    op.create_index("ix_extension_report_shares_status", "extension_report_shares", ["status"])

    op.create_table(
        "extension_report_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("share_id", sa.Integer(), sa.ForeignKey("extension_report_shares.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("share_id", "content_hash", name="uq_extension_share_snapshot_hash"),
    )
    op.create_index("ix_extension_report_snapshots_share_id", "extension_report_snapshots", ["share_id"])

    op.create_table(
        "extension_report_edits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("share_id", sa.Integer(), sa.ForeignKey("extension_report_shares.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(16), server_default="", nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), server_default="PENDING", nullable=False),
        sa.Column("result_message", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("public_id", name="uq_extension_report_edits_public_id"),
    )
    op.create_index("ix_extension_report_edits_public_id", "extension_report_edits", ["public_id"])
    op.create_index("ix_extension_report_edits_share_id", "extension_report_edits", ["share_id"])
    op.create_index("ix_extension_report_edits_account_id", "extension_report_edits", ["account_id"])
    op.create_index("ix_extension_report_edits_status", "extension_report_edits", ["status"])


def downgrade() -> None:
    op.drop_index("ix_extension_report_edits_status", table_name="extension_report_edits")
    op.drop_index("ix_extension_report_edits_account_id", table_name="extension_report_edits")
    op.drop_index("ix_extension_report_edits_share_id", table_name="extension_report_edits")
    op.drop_index("ix_extension_report_edits_public_id", table_name="extension_report_edits")
    op.drop_table("extension_report_edits")
    op.drop_index("ix_extension_report_snapshots_share_id", table_name="extension_report_snapshots")
    op.drop_table("extension_report_snapshots")
    op.drop_index("ix_extension_report_shares_status", table_name="extension_report_shares")
    op.drop_index("ix_extension_report_shares_account_id", table_name="extension_report_shares")
    op.drop_index("ix_extension_report_shares_client_key_id", table_name="extension_report_shares")
    op.drop_index("ix_extension_report_shares_public_id", table_name="extension_report_shares")
    op.drop_table("extension_report_shares")
