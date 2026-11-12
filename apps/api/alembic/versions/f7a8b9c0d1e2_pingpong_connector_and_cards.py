"""Hỗ trợ PingPong connector và lưu snapshot thẻ ảo VCC.

Reversible migration:
- upgrade: thêm cột encrypted_extra vào exchange_credentials, tạo bảng exchange_card_snapshots.
- downgrade: xoá bảng exchange_card_snapshots, xoá cột encrypted_extra.
"""
from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "e5d8f1b2c946"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Thêm encrypted_extra vào exchange_credentials
    with op.batch_alter_table("exchange_credentials") as batch:
        batch.add_column(sa.Column("encrypted_extra", sa.Text(), nullable=True))

    # 2. Tạo bảng exchange_card_snapshots
    op.create_table(
        "exchange_card_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("exchange_connections.id"), nullable=False),
        sa.Column("card_id", sa.String(64), nullable=False),
        sa.Column("card_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("last4", sa.String(8), nullable=False),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("spending_limit", sa.Numeric(28, 8), nullable=True),
        sa.Column("available_balance", sa.Numeric(28, 8), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="MANUAL"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_exchange_card_snapshot_read",
        "exchange_card_snapshots",
        ["connection_id", "card_id", "read_at"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_exchange_card_snapshot_read", table_name="exchange_card_snapshots")
    op.drop_table("exchange_card_snapshots")
    with op.batch_alter_table("exchange_credentials") as batch:
        batch.drop_column("encrypted_extra")
