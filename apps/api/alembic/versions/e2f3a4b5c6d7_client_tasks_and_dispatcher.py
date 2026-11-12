"""Thêm telegram_username cho customers và tạo bảng client_tasks cho AI dispatcher.

Reversible migration:
- upgrade: thêm cột telegram_username vào customers, tạo bảng client_tasks.
- downgrade: xoá bảng client_tasks, xoá cột telegram_username.
"""
from alembic import op
import sqlalchemy as sa

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Thêm telegram_username vào customers
    with op.batch_alter_table("customers") as batch:
        batch.add_column(sa.Column("telegram_username", sa.String(64), nullable=True))
        batch.create_index("ix_customers_telegram_username", ["telegram_username"], unique=False)

    # 2. Tạo bảng client_tasks
    op.create_table(
        "client_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("telegram_chat_id", sa.String(64), nullable=False),
        sa.Column("telegram_username", sa.String(64), nullable=True),
        sa.Column("sender_name", sa.String(128), nullable=True),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("raw_message", sa.Text(), nullable=False),
        sa.Column("extracted_data", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="NORMAL"),
        sa.Column("assigned_to", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_client_tasks_telegram_chat_id", "client_tasks", ["telegram_chat_id"])
    op.create_index("ix_client_tasks_task_type", "client_tasks", ["task_type"])
    op.create_index("ix_client_tasks_status", "client_tasks", ["status"])


def downgrade():
    op.drop_index("ix_client_tasks_status", table_name="client_tasks")
    op.drop_index("ix_client_tasks_task_type", table_name="client_tasks")
    op.drop_index("ix_client_tasks_telegram_chat_id", table_name="client_tasks")
    op.drop_table("client_tasks")
    with op.batch_alter_table("customers") as batch:
        batch.drop_index("ix_customers_telegram_username")
        batch.drop_column("telegram_username")
