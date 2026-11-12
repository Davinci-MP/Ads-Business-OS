"""Sổ ngân sách có phê duyệt."""
from alembic import op
import sqlalchemy as sa
revision = "prepaid_20261030"
down_revision = "risk_20261030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("client_balances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(20, 6), nullable=False),
        sa.Column("low_threshold", sa.Numeric(20, 6)),
        sa.Column("deposit_info", sa.Text()),
        sa.Column("low_alert_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("customer_id", "currency", name="uq_client_balance_currency"))
    op.create_table("ledger_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(20, 6), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("source_ledger_id", sa.Integer(), sa.ForeignKey("ledger_entries.id"), unique=True),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_by", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_table("ledger_transactions")
    op.drop_table("client_balances")
