"""Trường quét TKQC kiểu ToolFB qua Graph API chính thức.

spend_cap, created_time, business_name (BM sở hữu), user_tasks (quyền của VIA trên TK),
is_prepay, last_scanned_at — để trống khi Meta không trả (không điền giá trị giả). Reversible.

Revision ID: z0a1b2c3d4e5
Revises: y9z0a1b2c3d4
Create Date: 2026-11-28 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "z0a1b2c3d4e5"
down_revision = "y9z0a1b2c3d4"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("spend_cap", sa.Float()),
    ("created_time", sa.DateTime(timezone=True)),
    ("business_name", sa.String(length=255)),
    ("user_tasks", sa.String(length=128)),
    ("is_prepay", sa.Boolean()),
    ("last_scanned_at", sa.DateTime(timezone=True)),
)


def upgrade():
    with op.batch_alter_table("synced_ad_accounts") as batch:
        for name, type_ in _COLUMNS:
            batch.add_column(sa.Column(name, type_, nullable=True))


def downgrade():
    with op.batch_alter_table("synced_ad_accounts") as batch:
        for name, _ in reversed(_COLUMNS):
            batch.drop_column(name)
