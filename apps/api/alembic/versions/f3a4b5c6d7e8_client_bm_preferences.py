"""Tạo bảng client_bm_preferences ghi nhớ phân quyền và định tuyến Multi-BM cho khách hàng.

Reversible migration:
- upgrade: tạo bảng client_bm_preferences và index client_id.
- downgrade: drop index và drop table client_bm_preferences.
"""
from alembic import op
import sqlalchemy as sa

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_bm_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, unique=True),
        sa.Column("preferred_bm_id", sa.String(64), nullable=False, server_default="BM_01"),
        sa.Column("bm_role", sa.String(32), nullable=False, server_default="EMPLOYEE"),
        sa.Column("ad_account_access_type", sa.String(32), nullable=False, server_default="FULL"),
        sa.Column("partial_permissions", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_client_bm_preferences_client_id", "client_bm_preferences", ["client_id"], unique=True)


def downgrade():
    op.drop_index("ix_client_bm_preferences_client_id", table_name="client_bm_preferences")
    op.drop_table("client_bm_preferences")
