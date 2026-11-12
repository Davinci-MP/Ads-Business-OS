"""add_encrypted_webhook_secret_to_telegram_bot_configs

Revision ID: 7502200ab430
Revises: i6d7e8f9a0b1
Create Date: 2026-11-01 22:48:31.381886
"""
from alembic import op
import sqlalchemy as sa


revision = '7502200ab430'
down_revision = 'i6d7e8f9a0b1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("telegram_bot_configs") as batch_op:
        batch_op.add_column(sa.Column("encrypted_webhook_secret", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("telegram_bot_configs") as batch_op:
        batch_op.drop_column("encrypted_webhook_secret")
