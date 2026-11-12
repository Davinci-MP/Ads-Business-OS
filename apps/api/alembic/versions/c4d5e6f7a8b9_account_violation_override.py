"""Cấu hình đặc cách tài khoản vi phạm, mặc định tắt."""
from alembic import op
import sqlalchemy as sa
revision = "c4d5e6f7a8b9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("ad_accounts", sa.Column("allow_violated_accounts", sa.Boolean(), nullable=False, server_default="0"))

def downgrade():
    op.drop_column("ad_accounts", "allow_violated_accounts")
