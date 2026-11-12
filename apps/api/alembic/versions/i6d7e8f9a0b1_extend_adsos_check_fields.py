"""Bổ sung các trường siêu dữ liệu mở rộng cho ADSOS CHECK trên synced_ad_accounts và synced_bms.

Reversible migration:
- upgrade:
  - synced_ad_accounts: disable_reason, user_role, timezone_name, country_code, tax_status, admin_count, hidden_admin_count, pixel_id.
  - synced_bms: bm_level, verified_status, created_year, admin_count, can_create_ad_account.
- downgrade:
  - drop các cột mới khỏi synced_bms và synced_ad_accounts.
"""

from alembic import op
import sqlalchemy as sa

revision = "i6d7e8f9a0b1"
down_revision = "h5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Bổ sung trường cho synced_ad_accounts
    with op.batch_alter_table("synced_ad_accounts") as batch_op:
        batch_op.add_column(sa.Column("disable_reason", sa.String(64), nullable=False, server_default="NONE"))
        batch_op.add_column(sa.Column("user_role", sa.String(32), nullable=False, server_default="ADMIN"))
        batch_op.add_column(sa.Column("timezone_name", sa.String(64), nullable=False, server_default="Asia/Ho_Chi_Minh | GMT+7"))
        batch_op.add_column(sa.Column("country_code", sa.String(16), nullable=False, server_default="VN"))
        batch_op.add_column(sa.Column("tax_status", sa.String(64), nullable=False, server_default="MIỄN THUẾ"))
        batch_op.add_column(sa.Column("admin_count", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("hidden_admin_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("pixel_id", sa.String(64), nullable=True))

    # 2. Bổ sung trường cho synced_bms
    with op.batch_alter_table("synced_bms") as batch_op:
        batch_op.add_column(sa.Column("bm_level", sa.String(32), nullable=False, server_default="NOLIMIT"))
        batch_op.add_column(sa.Column("verified_status", sa.String(32), nullable=False, server_default="VERIFIED"))
        batch_op.add_column(sa.Column("created_year", sa.String(16), nullable=True, server_default="2022"))
        batch_op.add_column(sa.Column("admin_count", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("can_create_ad_account", sa.Boolean(), nullable=False, server_default="1"))


def downgrade():
    with op.batch_alter_table("synced_bms") as batch_op:
        batch_op.drop_column("can_create_ad_account")
        batch_op.drop_column("admin_count")
        batch_op.drop_column("created_year")
        batch_op.drop_column("verified_status")
        batch_op.drop_column("bm_level")

    with op.batch_alter_table("synced_ad_accounts") as batch_op:
        batch_op.drop_column("pixel_id")
        batch_op.drop_column("hidden_admin_count")
        batch_op.drop_column("admin_count")
        batch_op.drop_column("tax_status")
        batch_op.drop_column("country_code")
        batch_op.drop_column("timezone_name")
        batch_op.drop_column("user_role")
        batch_op.drop_column("disable_reason")
