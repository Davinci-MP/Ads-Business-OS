"""Liên kết VIA với tài khoản Facebook qua app-scoped user ID (OAuth).

/me của Graph API v2.0+ trả app-scoped user ID, không phải UID thật, nên không so
được với via_profiles.uid. Lưu ID này (unique) + tên hiển thị khi cấp quyền lần đầu;
các lần sau bắt buộc trùng. Reversible.

Revision ID: y9z0a1b2c3d4
Revises: x8y9z0a1b2c3
Create Date: 2026-11-28 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "y9z0a1b2c3d4"
down_revision = "x8y9z0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("via_profiles") as batch:
        batch.add_column(sa.Column("meta_app_user_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("meta_user_name", sa.String(length=255), nullable=True))
        batch.create_index("ix_via_profiles_meta_app_user_id", ["meta_app_user_id"], unique=True)


def downgrade():
    with op.batch_alter_table("via_profiles") as batch:
        batch.drop_index("ix_via_profiles_meta_app_user_id")
        batch.drop_column("meta_user_name")
        batch.drop_column("meta_app_user_id")
