"""Thêm portal_token cho khách hàng và tạo bảng kho tài nguyên inventory_items.

Reversible migration:
- upgrade: thêm cột portal_token vào customers, tạo bảng inventory_items.
- downgrade: xoá bảng inventory_items, xoá cột portal_token.
"""
from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "prepaid_20261030"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Thêm portal_token vào customers
    with op.batch_alter_table("customers") as batch:
        batch.add_column(sa.Column("portal_token", sa.String(64), nullable=True))
        batch.create_index("ix_customers_portal_token", ["portal_token"], unique=True)

    # 2. Tạo bảng inventory_items
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="AVAILABLE"),
        sa.Column("assigned_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("assigned_ad_account_id", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_inventory_items_item_type", "inventory_items", ["item_type"])
    op.create_index("ix_inventory_items_status", "inventory_items", ["status"])


def downgrade():
    op.drop_index("ix_inventory_items_status", table_name="inventory_items")
    op.drop_index("ix_inventory_items_item_type", table_name="inventory_items")
    op.drop_table("inventory_items")
    with op.batch_alter_table("customers") as batch:
        batch.drop_index("ix_customers_portal_token")
        batch.drop_column("portal_token")
