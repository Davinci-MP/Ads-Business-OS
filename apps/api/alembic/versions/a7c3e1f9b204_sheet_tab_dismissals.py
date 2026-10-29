"""Add reversible dismissals for Sheets tabs that are not customers."""
from alembic import op
import sqlalchemy as sa

revision = "a7c3e1f9b204"
down_revision = "e9b2c4d6f810"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sheet_report_tab_dismissals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sheet_report_sources.id"), nullable=False),
        sa.Column("sheet_id", sa.Integer(), nullable=False),
        sa.Column("source_title", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("actor", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_sheet_tab_dismissal", "sheet_report_tab_dismissals", ["source_id", "sheet_id"], unique=True,
        sqlite_where=sa.text("active = 1"), postgresql_where=sa.text("active"),
    )


def downgrade() -> None:
    op.drop_index("uq_sheet_tab_dismissal", table_name="sheet_report_tab_dismissals")
    op.drop_table("sheet_report_tab_dismissals")
