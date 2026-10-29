"""Preserve Funding components without backfilling historical unknowns."""
from alembic import op
import sqlalchemy as sa
revision = "e5d8f1b2c946"
down_revision = "d4c7e0a1f835"
branch_labels = None
depends_on = None
def upgrade():
    op.add_column("exchange_balance_snapshots", sa.Column("freeze", sa.Numeric(28, 8), nullable=True))
    op.add_column("exchange_balance_snapshots", sa.Column("withdrawing", sa.Numeric(28, 8), nullable=True))
def downgrade():
    with op.batch_alter_table("exchange_balance_snapshots") as batch:
        batch.drop_column("withdrawing")
        batch.drop_column("freeze")
