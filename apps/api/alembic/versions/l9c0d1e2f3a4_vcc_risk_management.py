"""VCC Risk Management: vcc_cards, vcc_transactions, and synced_ad_accounts funding fields.

Revision ID: l9c0d1e2f3a4
Revises: k8b9c0d1e2f3
Create Date: 2026-11-03 15:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "l9c0d1e2f3a4"
down_revision = "k8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Bảng vcc_cards
    op.create_table(
        "vcc_cards",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("card_number_masked", sa.String(64), nullable=True),
        sa.Column("last_four", sa.String(8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("remark", sa.String(255), nullable=True),
        sa.Column("currency", sa.String(16), nullable=False, server_default="USD"),
        sa.Column("allocated_balance", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("available_balance", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("low_balance_threshold", sa.Numeric(18, 4), nullable=False, server_default="5.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vcc_cards_last_four", "vcc_cards", ["last_four"])
    op.create_index("ix_vcc_cards_status", "vcc_cards", ["status"])
    op.create_index("ix_vcc_cards_remark", "vcc_cards", ["remark"])

    # 2. Bảng vcc_transactions
    op.create_table(
        "vcc_transactions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("card_id", sa.String(64), sa.ForeignKey("vcc_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auth_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("settle_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(16), nullable=False, server_default="USD"),
        sa.Column("merchant_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="SETTLED"),
        sa.Column("transaction_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_vcc_transactions_card_id", "vcc_transactions", ["card_id"])

    # 3. Bổ sung trường cho synced_ad_accounts
    with op.batch_alter_table("synced_ad_accounts") as batch_op:
        batch_op.add_column(sa.Column("amount_spent", sa.Float(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("threshold_amount", sa.Float(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("funding_source_last_four", sa.String(16), nullable=True))

    # Sao chép dữ liệu từ các cột tương đương sẵn có nếu có
    bind = op.get_bind()
    try:
        bind.execute(
            sa.text(
                "UPDATE synced_ad_accounts SET "
                "amount_spent = COALESCE(total_spend, 0), "
                "threshold_amount = COALESCE(threshold, 0), "
                "funding_source_last_four = payment_card_last4 "
                "WHERE amount_spent IS NULL OR amount_spent = 0"
            )
        )
    except Exception:
        pass


def downgrade():
    with op.batch_alter_table("synced_ad_accounts") as batch_op:
        batch_op.drop_column("funding_source_last_four")
        batch_op.drop_column("threshold_amount")
        batch_op.drop_column("amount_spent")

    op.drop_index("ix_vcc_transactions_card_id", table_name="vcc_transactions")
    op.drop_table("vcc_transactions")

    op.drop_index("ix_vcc_cards_remark", table_name="vcc_cards")
    op.drop_index("ix_vcc_cards_status", table_name="vcc_cards")
    op.drop_index("ix_vcc_cards_last_four", table_name="vcc_cards")
    op.drop_table("vcc_cards")
