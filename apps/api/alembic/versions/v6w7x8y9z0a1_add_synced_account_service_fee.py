"""add synced account service fee

Revision ID: v6w7x8y9z0a1
Revises: u1v2w3x4y5z6
Create Date: 2026-11-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "v6w7x8y9z0a1"
down_revision = "u1v2w3x4y5z6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("synced_ad_accounts") as batch_op:
        batch_op.add_column(sa.Column("service_fee_rate", sa.Numeric(6, 4), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("synced_ad_accounts") as batch_op:
        batch_op.drop_column("service_fee_rate")
