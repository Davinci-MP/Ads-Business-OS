"""staff_users and staff_audit_logs migration

Revision ID: u1v2w3x4y5z6
Revises: t5c6d7e8f9a0
Create Date: 2026-11-11 00:00:00.000000

"""
from alembic import op
import os
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import Session

from app.models.staff import StaffUser
from app.core.config import settings


def _hash_password(password: str) -> str:
    import hashlib, secrets
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 256000)
    return f"{salt}:{dk.hex()}"


# Auto-seed default OWNER account if none exists
def _seed_default_owner() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        existing = session.query(StaffUser).filter_by(username="admin").first()
        if not existing:
            pw = os.getenv("ADSOS_DEFAULT_OWNER_PASSWORD", "Admin@123")
            admin = StaffUser(
                username="admin",
                full_name="Administrator",
                role="OWNER",
                password_hash=_hash_password(pw),
                is_active=True,
            )
            session.add(admin)
            session.commit()
            print("[Seed] Default OWNER created: username=admin")
    finally:
        session.close()


# revision identifiers, used by Alembic.
revision = "u1v2w3x4y5z6"
down_revision = "t5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create staff_users table
    op.create_table(
        "staff_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column(
            "role",
            sa.String(length=30),
            nullable=False,
            server_default="STAFF_SUPPORT",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "assigned_customer_ids",
            sa.JSON(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    # Create staff_audit_logs table
    op.create_table(
        "staff_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=120), nullable=True),
        sa.Column("role", sa.String(length=30), nullable=True),
        sa.Column(
            "action_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column("target_bm_id", sa.String(length=50), nullable=True),
        sa.Column(
            "target_account_ids",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "recipient_info",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=10),
            nullable=False,
            server_default="SUCCESS",
        ),
        sa.Column(
            "detail",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(
        op.f("ix_staff_users_username"), "staff_users", ["username"], unique=True
    )
    op.create_index(
        op.f("ix_staff_audit_logs_created_at"), "staff_audit_logs", ["created_at"]
    )

    # Auto-seed default OWNER account
    _seed_default_owner()


def downgrade() -> None:
    # Drop indexes first
    op.drop_index(op.f("ix_staff_audit_logs_created_at"), table_name="staff_audit_logs")
    op.drop_index(op.f("ix_staff_users_username"), table_name="staff_users")

    # Drop tables
    op.drop_table("staff_audit_logs")
    op.drop_table("staff_users")
