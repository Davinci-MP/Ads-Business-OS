"""Store an optional customer budget reminder threshold."""
from alembic import op
import sqlalchemy as sa

revision = "e9b2c4d6f810"
down_revision = "d8a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("budget_alert_threshold_vnd", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "budget_alert_threshold_vnd")
