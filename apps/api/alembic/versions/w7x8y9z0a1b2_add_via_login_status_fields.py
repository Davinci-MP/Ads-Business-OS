"""add via login status fields

Revision ID: w7x8y9z0a1b2
Revises: v6w7x8y9z0a1
Create Date: 2026-11-12 13:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "w7x8y9z0a1b2"
down_revision = "v6w7x8y9z0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("via_profiles") as batch_op:
        batch_op.add_column(sa.Column("login_status", sa.String(32), server_default="READY", nullable=False))
        batch_op.add_column(sa.Column("last_login_error", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("via_profiles") as batch_op:
        batch_op.drop_column("last_login_error")
        batch_op.drop_column("login_status")
