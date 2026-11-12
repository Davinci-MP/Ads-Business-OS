import hashlib
import os
import secrets
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    JSON,
    func,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from .base import Base


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-SHA256 with 256k iterations + salt."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 256000
    )
    return f"{salt}:{dk.hex()}"


_hash_password = hash_password


def verify_password(stored: str, candidate: str) -> bool:
    """Verify a candidate password against a stored hash 'salt:hexdigest'."""
    try:
        stored_salt, stored_hash = stored.split(":", 1)
        dk = hashlib.pbkdf2_hmac(
            "sha256", candidate.encode("utf-8"), stored_salt.encode("utf-8"), 256000
        )
        return dk.hex() == stored_hash
    except Exception:
        return False


class StaffUser(Base):
    __tablename__ = "staff_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(120), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=True)
    email = Column(String(200), nullable=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(
        String(30),
        nullable=False,
        default="STAFF_SUPPORT",
        comment="OWNER | STAFF_OPS | STAFF_SUPPORT | ACCOUNTANT",
    )
    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    assigned_customer_ids = Column(
        JSON,
        nullable=True,
        default=None,
        comment="List of customer IDs assigned to STAFF_SUPPORT",
    )

    # Relationships
    audit_logs = relationship(
        "StaffAuditLog", back_populates="staff", cascade="all, delete-orphan"
    )


class StaffAuditLog(Base):
    __tablename__ = "staff_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(
        Integer, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    username = Column(String(120), nullable=True)
    role = Column(String(30), nullable=True)
    action_type = Column(
        String(50),
        nullable=False,
        comment="LOGIN | SHARE_BM | ASSIGN_TKQC | SHARE_PIXEL | REMOVE_ADMIN | UPDATE_ACCOUNT | STAFF_CRUD",
    )
    target_bm_id = Column(String(50), nullable=True)
    target_account_ids = Column(
        JSON, nullable=True, comment="JSON list of account IDs affected"
    )
    recipient_info = Column(String(255), nullable=True)
    # S: SUCCESS, F: FAILED, B: BLOCKED
    status = Column(String(10), nullable=False, default="SUCCESS")
    detail = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    staff = relationship("StaffUser", back_populates="audit_logs")
