"""S5: purchase_cost cho ad_accounts + telegram_outbox (D-031). Reversible."""
from alembic import op
import sqlalchemy as sa

from app.models.types import UTCDateTime

revision = "7d2e4a61c5f9"
down_revision = "2090fc5b5421"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ad_accounts",
        sa.Column("purchase_cost", sa.Numeric(14, 2), nullable=True),
    )
    op.create_table(
        "telegram_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("sent_at", UTCDateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("telegram_outbox")
    op.drop_column("ad_accounts", "purchase_cost")
