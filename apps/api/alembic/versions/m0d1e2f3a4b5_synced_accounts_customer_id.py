"""Add customer_id to synced_ad_accounts for SMIT customer assignment.

Revision ID: m0d1e2f3a4b5
Revises: l9c0d1e2f3a4
Create Date: 2026-11-03 21:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m0d1e2f3a4b5"
down_revision = "l9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns("synced_ad_accounts")]
    if "customer_id" not in cols:
        with op.batch_alter_table("synced_ad_accounts") as batch_op:
            batch_op.add_column(
                sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL", name="fk_synced_ad_accounts_customer_id"), nullable=True)
            )
            batch_op.create_index("ix_synced_ad_accounts_customer_id", ["customer_id"])


def downgrade():
    with op.batch_alter_table("synced_ad_accounts") as batch_op:
        batch_op.drop_index("ix_synced_ad_accounts_customer_id")
        batch_op.drop_column("customer_id")
