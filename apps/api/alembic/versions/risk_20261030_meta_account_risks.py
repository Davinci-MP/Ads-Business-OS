"""Theo dõi rủi ro tài khoản Meta."""
from alembic import op
import sqlalchemy as sa

revision = "risk_20261030"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("meta_account_risks",
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("account_status", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("debt", sa.Numeric(24, 6), nullable=True),
        sa.Column("debt_threshold", sa.Numeric(24, 6), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk_code", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("data_status", sa.String(16), nullable=False, server_default="UNVERIFIED"),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True))


def downgrade():
    op.drop_table("meta_account_risks")
