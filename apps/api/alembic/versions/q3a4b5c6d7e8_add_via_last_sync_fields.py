"""Thêm thời điểm xác thực và hết hạn token VIA.

Revision ID: q3a4b5c6d7e8
Revises: p2f3a4b5c6d7
"""

from alembic import op
import sqlalchemy as sa


revision = "q3a4b5c6d7e8"
down_revision = "p2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("via_profiles", sa.Column("last_token_refresh", sa.DateTime(timezone=True), nullable=True))
    op.add_column("via_profiles", sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("via_profiles", "token_expires_at")
    op.drop_column("via_profiles", "last_token_refresh")
