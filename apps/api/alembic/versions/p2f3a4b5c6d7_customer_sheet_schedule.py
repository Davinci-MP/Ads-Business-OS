"""Thêm cấu hình và lịch chạy Google Sheets theo khách hàng.

Revision ID: p2f3a4b5c6d7
Revises: n1e2f3a4b5c6
Create Date: 2026-11-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "p2f3a4b5c6d7"
down_revision = "n1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("sheet_url", sa.String(length=1024), nullable=True))
    op.add_column("customers", sa.Column("sheet_tab_name", sa.String(length=255), nullable=True))
    op.add_column("customers", sa.Column("sync_time", sa.String(length=5), nullable=True))
    op.create_index("ix_customers_sync_time", "customers", ["sync_time"], unique=False)
    op.create_table(
        "customer_sheet_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="CREATED", nullable=False),
        sa.Column("rows_json", sa.JSON(), nullable=True),
        sa.Column("backup_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("customer_id", "scheduled_for", name="uq_customer_sheet_sync_run"),
    )
    op.create_index("ix_customer_sheet_sync_runs_customer_id", "customer_sheet_sync_runs", ["customer_id"])
    op.create_index("ix_customer_sheet_sync_runs_scheduled_for", "customer_sheet_sync_runs", ["scheduled_for"])
    op.create_index("ix_customer_sheet_sync_runs_status", "customer_sheet_sync_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_customer_sheet_sync_runs_status", table_name="customer_sheet_sync_runs")
    op.drop_index("ix_customer_sheet_sync_runs_scheduled_for", table_name="customer_sheet_sync_runs")
    op.drop_index("ix_customer_sheet_sync_runs_customer_id", table_name="customer_sheet_sync_runs")
    op.drop_table("customer_sheet_sync_runs")
    op.drop_index("ix_customers_sync_time", table_name="customers")
    op.drop_column("customers", "sync_time")
    op.drop_column("customers", "sheet_tab_name")
    op.drop_column("customers", "sheet_url")
