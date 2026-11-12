"""ADSOS Check Pro Extension: extension_client_keys, campaign_templates, extension_remote_tasks, and via_profiles.client_id.

Revision ID: k8b9c0d1e2f3
Revises: j7a8b9c0d1e2
Create Date: 2026-11-02 21:55:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "k8b9c0d1e2f3"
down_revision = "j7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add client_id to via_profiles
    with op.batch_alter_table("via_profiles") as batch_op:
        batch_op.add_column(sa.Column("client_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_via_profiles_client_id",
            "customers",
            ["client_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 2. Table extension_client_keys
    op.create_table(
        "extension_client_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("api_key", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["customers.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("api_key", name="uq_extension_client_keys_api_key"),
    )
    op.create_index("ix_extension_client_keys_api_key", "extension_client_keys", ["api_key"])
    op.create_index("ix_extension_client_keys_client_id", "extension_client_keys", ["client_id"])

    # 3. Table campaign_templates
    op.create_table(
        "campaign_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("objective", sa.String(64), nullable=False, server_default="OUTCOME_ENGAGEMENT"),
        sa.Column("daily_budget", sa.String(64), nullable=False, server_default="500000"),
        sa.Column("currency", sa.String(16), nullable=False, server_default="VND"),
        sa.Column("targeting_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("page_id", sa.String(64), nullable=True),
        sa.Column("post_id_or_creative_json", sa.Text(), nullable=True),
        sa.Column("status_on_create", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["customers.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_campaign_templates_client_id", "campaign_templates", ["client_id"])

    # 4. Table extension_remote_tasks
    op.create_table(
        "extension_remote_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("via_id", sa.Integer(), nullable=True),
        sa.Column("fb_uid", sa.String(64), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("target_act_id", sa.String(64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(64), nullable=False, server_default="WEB_ADMIN"),
        sa.Column("telegram_chat_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["via_id"], ["via_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["client_id"], ["customers.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_extension_remote_tasks_fb_uid", "extension_remote_tasks", ["fb_uid"])
    op.create_index("ix_extension_remote_tasks_status", "extension_remote_tasks", ["status"])
    op.create_index("ix_extension_remote_tasks_task_type", "extension_remote_tasks", ["task_type"])


def downgrade():
    op.drop_index("ix_extension_remote_tasks_task_type", table_name="extension_remote_tasks")
    op.drop_index("ix_extension_remote_tasks_status", table_name="extension_remote_tasks")
    op.drop_index("ix_extension_remote_tasks_fb_uid", table_name="extension_remote_tasks")
    op.drop_table("extension_remote_tasks")

    op.drop_index("ix_campaign_templates_client_id", table_name="campaign_templates")
    op.drop_table("campaign_templates")

    op.drop_index("ix_extension_client_keys_client_id", table_name="extension_client_keys")
    op.drop_index("ix_extension_client_keys_api_key", table_name="extension_client_keys")
    op.drop_table("extension_client_keys")

    with op.batch_alter_table("via_profiles") as batch_op:
        batch_op.drop_column("client_id")
