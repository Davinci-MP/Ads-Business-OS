"""Hardening hàng đợi lệnh Extension và Telegram.

Revision ID: s4b5c6d7e8f9
Revises: q3a4b5c6d7e8
Create Date: 2026-11-10 18:00:00.000000
"""

from __future__ import annotations

import json
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "s4b5c6d7e8f9"
down_revision = "q3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("remote_via_commands") as batch:
        batch.add_column(sa.Column("public_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("ad_account_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("payload", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("result_log", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, act_id, payload_json FROM remote_via_commands")
    ).mappings()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            payload = {}
        bind.execute(
            sa.text(
                "UPDATE remote_via_commands "
                "SET public_id = :public_id, ad_account_id = :act_id, payload = :payload "
                "WHERE id = :id"
            ),
            {
                "public_id": str(uuid4()),
                "act_id": row["act_id"],
                "payload": json.dumps(payload, ensure_ascii=False),
                "id": row["id"],
            },
        )
    op.create_index(
        "ix_remote_via_commands_public_id",
        "remote_via_commands",
        ["public_id"],
        unique=True,
    )

    with op.batch_alter_table("telegram_activity_logs") as batch:
        batch.add_column(sa.Column("update_id", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_telegram_activity_logs_update_id",
        "telegram_activity_logs",
        ["update_id"],
        unique=True,
    )

    with op.batch_alter_table("telegram_outbox") as batch:
        batch.add_column(sa.Column("chat_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("telegram_outbox") as batch:
        batch.drop_column("chat_id")

    op.drop_index("ix_telegram_activity_logs_update_id", table_name="telegram_activity_logs")
    with op.batch_alter_table("telegram_activity_logs") as batch:
        batch.drop_column("update_id")

    op.drop_index("ix_remote_via_commands_public_id", table_name="remote_via_commands")
    with op.batch_alter_table("remote_via_commands") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("result_log")
        batch.drop_column("payload")
        batch.drop_column("ad_account_id")
        batch.drop_column("public_id")
