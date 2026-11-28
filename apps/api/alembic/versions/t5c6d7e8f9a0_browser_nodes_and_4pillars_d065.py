"""Browser Nodes, 4-Pillar Workflow Presets, Saved Ad Assets, and Extended Metadata under D-065.

Revision ID: t5c6d7e8f9a0
Revises: s4b5c6d7e8f9
Create Date: 2026-11-10 20:30:00.000000
"""

from __future__ import annotations

import json
from alembic import op
import sqlalchemy as sa


revision = "t5c6d7e8f9a0"
down_revision = "s4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create browser_nodes table
    op.create_table(
        "browser_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("node_uid", sa.String(length=128), unique=True, nullable=False),
        sa.Column("node_name", sa.String(length=255), nullable=False),
        sa.Column("browser_type", sa.String(length=32), server_default="CHROME", nullable=False),
        sa.Column("via_id", sa.Integer(), sa.ForeignKey("via_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fb_uid", sa.String(length=64), nullable=True),
        sa.Column("eaag_token_enc", sa.Text(), nullable=True),
        sa.Column("eaab_token_enc", sa.Text(), nullable=True),
        sa.Column("cookie_enc", sa.Text(), nullable=True),
        sa.Column("fb_dtsg_enc", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="ONLINE", nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_browser_nodes_node_uid", "browser_nodes", ["node_uid"], unique=True)
    op.create_index("ix_browser_nodes_via_id", "browser_nodes", ["via_id"])
    op.create_index("ix_browser_nodes_fb_uid", "browser_nodes", ["fb_uid"])

    # 2. Create workflow_templates table
    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), unique=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("jitter_min_ms", sa.Integer(), server_default="1000", nullable=False),
        sa.Column("jitter_max_ms", sa.Integer(), server_default="3000", nullable=False),
        sa.Column("is_builtin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_workflow_templates_code", "workflow_templates", ["code"], unique=True)
    op.create_index("ix_workflow_templates_category", "workflow_templates", ["category"])

    # 3. Create saved_ad_assets table
    op.create_table(
        "saved_ad_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_account_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_saved_ad_assets_asset_type", "saved_ad_assets", ["asset_type"])
    op.create_index("ix_saved_ad_assets_source_account_id", "saved_ad_assets", ["source_account_id"])

    # 4. Alter synced_bms
    with op.batch_alter_table("synced_bms") as batch:
        batch.add_column(sa.Column("hidden_admin_count", sa.Integer(), server_default="0", nullable=False))

    # 5. Alter synced_ad_accounts
    with op.batch_alter_table("synced_ad_accounts") as batch:
        batch.add_column(sa.Column("hidden_limit", sa.Float(), server_default="0.0", nullable=False))
        batch.add_column(sa.Column("funding_source_summary", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("card_bin", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("location_verified", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.add_column(sa.Column("appeal_status", sa.String(length=64), server_default="NONE", nullable=False))
        batch.add_column(sa.Column("pixel_list", sa.JSON(), nullable=True))

    # 6. Alter synced_pages
    with op.batch_alter_table("synced_pages") as batch:
        batch.add_column(sa.Column("appeal_status", sa.String(length=64), server_default="NONE", nullable=False))

    # 7. Seed workflow presets
    bind = op.get_bind()
    try:
        from app.services.workflow_presets import BUILTIN_WORKFLOW_PRESETS
        for item in BUILTIN_WORKFLOW_PRESETS:
            bind.execute(
                sa.text(
                    "INSERT INTO workflow_templates (code, name, category, steps, jitter_min_ms, jitter_max_ms, is_builtin) "
                    "VALUES (:code, :name, :category, :steps, :jitter_min, :jitter_max, :is_builtin)"
                ),
                {
                    "code": item["code"],
                    "name": item["name"],
                    "category": item["category"],
                    "steps": json.dumps(item["steps"]),
                    "jitter_min": item["jitter_min_ms"],
                    "jitter_max": item["jitter_max_ms"],
                    "is_builtin": True,
                },
            )
    except ImportError:
        # Thiếu module preset thì bỏ qua seed; lỗi SQL thật phải nổi lên
        # (trên Postgres, nuốt lỗi sẽ làm hỏng cả transaction của migration).
        pass


def downgrade() -> None:
    # 1. Revert synced_pages
    with op.batch_alter_table("synced_pages") as batch:
        batch.drop_column("appeal_status")

    # 2. Revert synced_ad_accounts
    with op.batch_alter_table("synced_ad_accounts") as batch:
        batch.drop_column("pixel_list")
        batch.drop_column("appeal_status")
        batch.drop_column("location_verified")
        batch.drop_column("card_bin")
        batch.drop_column("funding_source_summary")
        batch.drop_column("hidden_limit")

    # 3. Revert synced_bms
    with op.batch_alter_table("synced_bms") as batch:
        batch.drop_column("hidden_admin_count")

    # 4. Drop tables
    op.drop_table("saved_ad_assets")
    op.drop_table("workflow_templates")
    op.drop_table("browser_nodes")
