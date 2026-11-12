"""Model Quản lý Extension Client Binding Keys, Campaign Templates & Remote Task Queue."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime


class ExtensionClientKey(Base):
    """Mã ràng buộc Extension Chrome của Khách hàng với Hệ thống AdsOS."""

    __tablename__ = "extension_client_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    # Relationship
    client = relationship("Customer", foreign_keys=[client_id])


class CampaignTemplate(Base):
    """Mẫu chiến dịch quảng cáo cấu hình sẵn để Auto Set Camp từ xa."""

    __tablename__ = "campaign_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    objective: Mapped[str] = mapped_column(String(64), default="OUTCOME_ENGAGEMENT", nullable=False)
    daily_budget: Mapped[str] = mapped_column(String(64), default="500000", nullable=False)
    currency: Mapped[str] = mapped_column(String(16), default="VND", nullable=False)
    targeting_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    page_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    post_id_or_creative_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status_on_create: Mapped[str] = mapped_column(String(32), default="PAUSED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    # Relationship
    client = relationship("Customer", foreign_keys=[client_id])


class ExtensionRemoteTask(Base):
    """Hàng đợi tác vụ điều phối tới Extension Chrome trên máy VIA/Khách hàng."""

    __tablename__ = "extension_remote_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    via_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("via_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fb_uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # CREATE_CAMPAIGN, SHARE_AD_ACCOUNT, INVITE_BM, PAUSE_CAMPAIGN, RESUME_CAMPAIGN, SYNC_NOW
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_act_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    # PENDING, RUNNING, COMPLETED, FAILED
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True, nullable=False)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(64), default="WEB_ADMIN", nullable=False)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    # Relationships
    via = relationship("ViaProfile", foreign_keys=[via_id])
    client = relationship("Customer", foreign_keys=[client_id])


class CampaignDraft(Base):
    """Bản nháp chiến dịch quảng cáo chuẩn Meta Ads (Lưu trữ và Tái sử dụng)."""

    __tablename__ = "campaign_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    draft_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_via_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_act_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    objective: Mapped[str] = mapped_column(String(64), default="OUTCOME_ENGAGEMENT", nullable=False)
    buying_type: Mapped[str] = mapped_column(String(32), default="AUCTION", nullable=False)
    daily_budget: Mapped[float] = mapped_column(default=500000.0, nullable=False)
    lifetime_budget: Mapped[Optional[float]] = mapped_column(nullable=True)
    bid_strategy: Mapped[str] = mapped_column(String(64), default="LOWEST_COST_WITHOUT_CAP", nullable=False)
    targeting_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    page_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    pixel_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    post_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ad_creative_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    initial_status: Mapped[str] = mapped_column(String(32), default="PAUSED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class RemoteViaCommand(Base):
    """Hàng đợi lệnh Extension; ``public_id`` là UUID được dùng làm ``id`` trên API."""

    __tablename__ = "remote_via_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[Optional[str]] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid4()), nullable=True
    )
    via_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("via_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    via_uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    act_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    ad_account_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    draft_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("campaign_drafts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    draft_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    command_type: Mapped[str] = mapped_column(String(64), default="SET_CAMP_FROM_DRAFT", nullable=False)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True, nullable=False)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by_telegram: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    # Relationships
    via = relationship("ViaProfile", foreign_keys=[via_id])
    customer = relationship("Customer", foreign_keys=[customer_id])
    draft = relationship("CampaignDraft", foreign_keys=[draft_id])


def _encrypt_node_secret(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    try:
        from app.services.via_manager import _get_fernet
        f = _get_fernet()
        if f:
            return f.encrypt(val.encode("utf-8")).decode("utf-8")
        return f"plain::{val}"
    except Exception:
        return f"plain::{val}"


def _decrypt_node_secret(val: Optional[str]) -> str:
    if not val:
        return ""
    if val.startswith("plain::"):
        return val[7:]
    try:
        from app.services.via_manager import _get_fernet
        f = _get_fernet()
        if f:
            return f.decrypt(val.encode("utf-8")).decode("utf-8")
        return val
    except Exception:
        return val


class BrowserNode(Base):
    """Trình duyệt vệ tinh / Antidetect Browser Profile kết nối Session Cloud Hub (D-065)."""

    __tablename__ = "browser_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    node_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # CHROME, ADSPOWER, GOLOGIN, KIKLOGIN, OTHER
    browser_type: Mapped[str] = mapped_column(String(32), default="CHROME", nullable=False)
    via_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("via_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fb_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    eaag_token_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    eaab_token_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cookie_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fb_dtsg_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ONLINE, OFFLINE, BUSY
    status: Mapped[str] = mapped_column(String(32), default="ONLINE", nullable=False)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    # Relationship
    via = relationship("ViaProfile", foreign_keys=[via_id])

    @property
    def eaag_token(self) -> str:
        return _decrypt_node_secret(self.eaag_token_enc)

    @eaag_token.setter
    def eaag_token(self, val: Optional[str]) -> None:
        self.eaag_token_enc = _encrypt_node_secret((val or "").strip()) if val else None

    @property
    def eaab_token(self) -> str:
        return _decrypt_node_secret(self.eaab_token_enc)

    @eaab_token.setter
    def eaab_token(self, val: Optional[str]) -> None:
        self.eaab_token_enc = _encrypt_node_secret((val or "").strip()) if val else None

    @property
    def cookie(self) -> str:
        return _decrypt_node_secret(self.cookie_enc)

    @cookie.setter
    def cookie(self, val: Optional[str]) -> None:
        self.cookie_enc = _encrypt_node_secret((val or "").strip()) if val else None

    @property
    def fb_dtsg(self) -> str:
        return _decrypt_node_secret(self.fb_dtsg_enc)

    @fb_dtsg.setter
    def fb_dtsg(self, val: Optional[str]) -> None:
        self.fb_dtsg_enc = _encrypt_node_secret((val or "").strip()) if val else None


class WorkflowTemplate(Base):
    """Mẫu quy trình tự động hóa tác nghiệp 4 Trụ Cột (69+ Workflow Presets) (D-065)."""

    __tablename__ = "workflow_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    jitter_min_ms: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    jitter_max_ms: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class SavedAdAsset(Base):
    """Tài sản quảng cáo lưu trữ (Target Audience, Ad Post Creative, Super Target Set) (D-065)."""

    __tablename__ = "saved_ad_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # AUDIENCE, AD_POST, SUPER_TARGET_SET
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_account_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

