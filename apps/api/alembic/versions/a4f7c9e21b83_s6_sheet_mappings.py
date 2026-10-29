"""S6: bảng sheet_mappings — mapping cấu trúc Google Sheets (D-024/D-028, chỉ đọc). Reversible."""
from alembic import op
import sqlalchemy as sa

from app.models.types import UTCDateTime

revision = "a4f7c9e21b83"
down_revision = "7d2e4a61c5f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sheet_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("spreadsheet_key", sa.String(length=128), nullable=False),
        sa.Column("sheet_name", sa.String(length=128), nullable=False),
        sa.Column("column_index", sa.Integer(), nullable=False),
        sa.Column("column_letter", sa.String(length=4), nullable=True),
        sa.Column("header", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("field", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PROPOSED"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("confirmed_at", UTCDateTime(), nullable=True),
        sa.UniqueConstraint("spreadsheet_key", "sheet_name", "column_index", name="uq_sheet_mapping_column"),
    )


def downgrade() -> None:
    op.drop_table("sheet_mappings")
