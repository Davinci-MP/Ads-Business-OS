"""Kết nối sàn: bảng cấu hình/credentials/volume snapshot/lịch sử đồng bộ (D-056).

Reversible: upgrade tạo 4 bảng; downgrade xoá ngược 4 bảng, không đụng bảng khác.
"""
from alembic import op
import sqlalchemy as sa

revision = "d4c7e0a1f835"
down_revision = "c9f8a3b1d2e6"
branch_labels = None
depends_on = None


def _utc_columns() -> list:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "exchange_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("wallet_types", sa.JSON(), nullable=False),
        sa.Column("read_only_verified", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("auto_sync", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_ok_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        *_utc_columns(),
    )
    op.create_index(
        "uq_exchange_connection_label", "exchange_connections", ["provider", "label"],
        unique=True,
    )
    op.create_table(
        "exchange_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("exchange_connections.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("encrypted_api_secret", sa.Text(), nullable=False),
        sa.Column("api_key_last4", sa.String(8), nullable=False),
        *_utc_columns(),
    )
    op.create_index(
        "uq_exchange_credentials_connection", "exchange_credentials", ["connection_id"],
        unique=True,
    )
    op.create_table(
        "exchange_balance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("exchange_connections.id"), nullable=False),
        sa.Column("wallet_type", sa.String(16), nullable=False),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("free", sa.Numeric(28, 8)),
        sa.Column("locked", sa.Numeric(28, 8)),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_exchange_snapshot_read", "exchange_balance_snapshots",
        ["connection_id", "wallet_type", "asset", "read_at"],
        unique=True,
    )
    op.create_table(
        "exchange_sync_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("exchange_connections.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("completed", sa.Boolean()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("detail", sa.JSON()),
        sa.Column("error_message", sa.Text()),
        sa.Column("triggered_by", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("exchange_sync_history")
    op.drop_index("uq_exchange_snapshot_read", table_name="exchange_balance_snapshots")
    op.drop_table("exchange_balance_snapshots")
    op.drop_index("uq_exchange_credentials_connection", table_name="exchange_credentials")
    op.drop_table("exchange_credentials")
    op.drop_index("uq_exchange_connection_label", table_name="exchange_connections")
    op.drop_table("exchange_connections")
