"""Ví USDT TRC20: bảng cấu hình ví được theo dõi + lịch sử số dư (chỉ đọc on-chain).

Reversible: upgrade tạo 2 bảng; downgrade xoá 2 bảng (không đụng bảng khác).
"""
from alembic import op
import sqlalchemy as sa

revision = "c9f8a3b1d2e6"
down_revision = "a7c3e1f9b204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usdt_wallets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("wallet_name", sa.String(255), nullable=False),
        sa.Column("wallet_address", sa.String(128), nullable=False),
        sa.Column("network", sa.String(32), nullable=False),
        sa.Column("contract", sa.String(64), nullable=False),
        sa.Column("auto_sync", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_ok_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_usdt_wallet_address", "usdt_wallets", ["wallet_address"], unique=True)
    op.create_table(
        "usdt_wallet_balances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("wallet_id", sa.Integer(), sa.ForeignKey("usdt_wallets.id"), nullable=False),
        sa.Column("wallet_address", sa.String(128), nullable=False),
        sa.Column("balance", sa.Numeric(28, 6)),
        sa.Column("note", sa.Text()),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_usdt_wallet_balance_read", "usdt_wallet_balances", ["wallet_id", "read_at", "source"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_usdt_wallet_balance_read", table_name="usdt_wallet_balances")
    op.drop_table("usdt_wallet_balances")
    op.drop_index("uq_usdt_wallet_address", table_name="usdt_wallets")
    op.drop_table("usdt_wallets")
