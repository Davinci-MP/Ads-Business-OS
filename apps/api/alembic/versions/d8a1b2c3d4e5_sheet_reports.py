"""Persist read-only Sheets sources, snapshots, sync history, and closures."""
from alembic import op
import sqlalchemy as sa

from app.models.types import UTCDateTime

revision = "d8a1b2c3d4e5"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sheet_report_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("spreadsheet_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("mapping_config", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("period", "spreadsheet_id", name="uq_sheet_source_period_workbook"),
    )
    op.create_index("uq_sheet_active_period", "sheet_report_sources", ["period"], unique=True,
                    sqlite_where=sa.text("active = 1"), postgresql_where=sa.text("active"))
    op.create_table(
        "sheet_report_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("default_source_id", sa.Integer(), sa.ForeignKey("sheet_report_sources.id")),
    )
    op.create_table(
        "sheet_report_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sheet_report_sources.id"), nullable=False),
        sa.Column("read_at", UTCDateTime(), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("mapping_config", sa.JSON(), nullable=False),
        sa.Column("quality", sa.String(32), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
    )
    op.create_index("ix_sheet_report_snapshots_source_id", "sheet_report_snapshots", ["source_id"])
    op.create_table(
        "sheet_report_sync_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sheet_report_sources.id"), nullable=False),
        sa.Column("started_at", UTCDateTime(), nullable=False),
        sa.Column("finished_at", UTCDateTime()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("sheet_report_snapshots.id")),
        sa.Column("error", sa.Text()),
        sa.Column("trigger", sa.String(24), nullable=False),
    )
    op.create_index("ix_sheet_report_sync_attempts_source_id", "sheet_report_sync_attempts", ["source_id"])
    op.create_table(
        "sheet_report_closures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sheet_report_sources.id"), nullable=False, unique=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("sheet_report_snapshots.id"), nullable=False),
        sa.Column("closed_at", UTCDateTime(), nullable=False),
        sa.Column("actor", sa.String(255)),
    )
    op.create_table(
        "sheet_report_customer_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sheet_report_sources.id"), nullable=False),
        sa.Column("sheet_id", sa.Integer(), nullable=False),
        sa.Column("source_title", sa.String(255), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index("uq_sheet_source_customer_tab", "sheet_report_customer_links", ["source_id", "sheet_id"],
                    unique=True, sqlite_where=sa.text("active = 1"), postgresql_where=sa.text("active"))
    op.create_index("uq_sheet_source_customer", "sheet_report_customer_links", ["source_id", "customer_id"],
                    unique=True, sqlite_where=sa.text("active = 1"), postgresql_where=sa.text("active"))


def downgrade() -> None:
    op.drop_index("uq_sheet_source_customer", table_name="sheet_report_customer_links")
    op.drop_index("uq_sheet_source_customer_tab", table_name="sheet_report_customer_links")
    op.drop_table("sheet_report_customer_links")
    op.drop_table("sheet_report_closures")
    op.drop_index("ix_sheet_report_sync_attempts_source_id", table_name="sheet_report_sync_attempts")
    op.drop_table("sheet_report_sync_attempts")
    op.drop_index("ix_sheet_report_snapshots_source_id", table_name="sheet_report_snapshots")
    op.drop_table("sheet_report_snapshots")
    op.drop_table("sheet_report_settings")
    op.drop_index("uq_sheet_active_period", table_name="sheet_report_sources")
    op.drop_table("sheet_report_sources")
