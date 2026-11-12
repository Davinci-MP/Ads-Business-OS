"""Tạo bảng telegram_bot_configs, automation_rules, telegram_activity_logs.

Reversible migration:
- upgrade: tạo 3 bảng telegram_bot_configs, automation_rules, telegram_activity_logs.
- downgrade: xoá 3 bảng.
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. telegram_bot_configs
    op.create_table(
        "telegram_bot_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("encrypted_bot_token", sa.Text(), nullable=True),
        sa.Column("admin_chat_id", sa.String(64), nullable=True),
        sa.Column("allowed_chat_ids", sa.Text(), nullable=True),
        sa.Column("webhook_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 2. automation_rules
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(64), nullable=False),
        sa.Column("threshold", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("currency", sa.String(16), server_default="VND", nullable=False),
        sa.Column("target_entity_id", sa.String(64), nullable=True),
        sa.Column("action_type", sa.String(64), server_default="TELEGRAM_ALERT", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 3. telegram_activity_logs
    op.create_table(
        "telegram_activity_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.String(64), nullable=False),
        sa.Column("username", sa.String(128), nullable=True),
        sa.Column("command", sa.String(255), nullable=False),
        sa.Column("response_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="SUCCESS", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_telegram_activity_logs_chat_id",
        "telegram_activity_logs",
        ["chat_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_activity_logs_chat_id", table_name="telegram_activity_logs")
    op.drop_table("telegram_activity_logs")
    op.drop_table("automation_rules")
    op.drop_table("telegram_bot_configs")
