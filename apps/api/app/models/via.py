"""Model Quản lý Dàn VIA (100+ VIA Profiles), Business Manager (BM), TKQC & Fanpage đồng bộ SMIT-Style."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.customer import utcnow
from app.models.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.client_bm_preference import ClientBMPreference
    from app.models.customer import Customer


class ViaProfile(Base):
    """Hồ sơ VIA Farm hỗ trợ hàng trăm tài khoản với profile trình duyệt và proxy riêng biệt."""

    __tablename__ = "via_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    profile_name: Mapped[str] = mapped_column(String(255), nullable=False)

    @property
    def fb_uid(self) -> str:
        """Alias cho uid Facebook của VIA."""
        return self.uid

    @fb_uid.setter
    def fb_uid(self, val: str) -> None:
        self.uid = val

    @property
    def fb_password(self) -> Optional[str]:
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("password")
        except Exception:
            return None

    @fb_password.setter
    def fb_password(self, val: Optional[str]) -> None:
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["password"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def two_fa_secret(self) -> Optional[str]:
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("two_fa_secret")
        except Exception:
            return None

    @two_fa_secret.setter
    def two_fa_secret(self, val: Optional[str]) -> None:
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["two_fa_secret"] = (val or "").replace(" ", "").strip().upper()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def email(self) -> Optional[str]:
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("email")
        except Exception:
            return None

    @email.setter
    def email(self, val: Optional[str]) -> None:
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["email"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def email_password(self) -> Optional[str]:
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("email_password")
        except Exception:
            return None

    @email_password.setter
    def email_password(self, val: Optional[str]) -> None:
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["email_password"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def backup_email(self) -> Optional[str]:
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("backup_email")
        except Exception:
            return None

    @backup_email.setter
    def backup_email(self, val: Optional[str]) -> None:
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["backup_email"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def backup_email_password(self) -> Optional[str]:
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("backup_email_password")
        except Exception:
            return None

    @backup_email_password.setter
    def backup_email_password(self, val: Optional[str]) -> None:
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["backup_email_password"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def raw_line(self) -> Optional[str]:
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("raw_line")
        except Exception:
            return None

    @raw_line.setter
    def raw_line(self, val: Optional[str]) -> None:
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["raw_line"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def eaag_token(self) -> Optional[str]:
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("eaag_token")
        except Exception:
            return None

    @eaag_token.setter
    def eaag_token(self, val: Optional[str]) -> None:
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["eaag_token"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def eaab_token(self) -> Optional[str]:
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("eaab_token")
        except Exception:
            return None

    @eaab_token.setter
    def eaab_token(self, val: Optional[str]) -> None:
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["eaab_token"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def fb_dtsg(self) -> Optional[str]:
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("fb_dtsg")
        except Exception:
            return None

    @fb_dtsg.setter
    def fb_dtsg(self, val: Optional[str]) -> None:
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["fb_dtsg"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def access_token(self) -> Optional[str]:
        """Lấy access_token giải mã từ encrypted_credentials."""
        if not self.encrypted_credentials:
            return None
        try:
            from app.services.via_manager import decrypt_via_credentials
            return decrypt_via_credentials(self.encrypted_credentials).get("access_token")
        except Exception:
            return None

    @access_token.setter
    def access_token(self, val: Optional[str]) -> None:
        """Lưu access_token mã hóa vào encrypted_credentials."""
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["access_token"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def cookies(self) -> str:
        """Lấy cookies giải mã từ encrypted_credentials."""
        if not self.encrypted_credentials:
            return ""
        try:
            from app.services.via_manager import decrypt_via_credentials
            creds = decrypt_via_credentials(self.encrypted_credentials)
            return creds.get("cookie", "")
        except Exception:
            return ""

    @cookies.setter
    def cookies(self, val: Optional[str]) -> None:
        """Lưu cookies mã hóa vào encrypted_credentials."""
        from app.services.via_manager import decrypt_via_credentials, encrypt_via_credentials
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        creds["cookie"] = (val or "").strip()
        self.encrypted_credentials = encrypt_via_credentials(creds)

    @property
    def cookie(self) -> str:
        """Alias số ít cho cookies."""
        return self.cookies

    @cookie.setter
    def cookie(self, val: Optional[str]) -> None:
        self.cookies = val

    @property
    def status(self) -> str:
        return self.uid_live_status

    @status.setter
    def status(self, val: str) -> None:
        self.uid_live_status = val

    def to_safe_dict(self, role: str = "STAFF") -> dict[str, Any]:
        """Trả về dữ liệu an toàn theo vai trò RBAC."""
        from app.services.via_manager import decrypt_via_credentials, generate_totp_code
        creds = decrypt_via_credentials(self.encrypted_credentials) if self.encrypted_credentials else {}
        two_fa = creds.get("two_fa_secret", "")
        totp_code, rem_secs = generate_totp_code(two_fa) if two_fa else ("", 0)

        is_owner = (role or "").upper() == "OWNER"
        base_data: dict[str, Any] = {
            "id": self.id,
            "uid": self.uid,
            "fb_uid": self.uid,
            "profile_name": self.profile_name,
            "profile_dir": self.profile_dir,
            "user_agent": self.user_agent,
            "login_status": self.login_status or "READY",
            "last_login_error": self.last_login_error,
            "uid_live_status": self.uid_live_status,
            "token_status": self.token_status,
            "bm_count": self.bm_count,
            "ad_account_count": self.ad_account_count,
            "page_count": self.page_count,
            "has_2fa": bool(two_fa),
            "has_mail": bool(creds.get("email")),
            "has_cookie": bool(creds.get("cookie")),
            "has_eaag": bool(creds.get("eaag_token")),
            "has_eaab": bool(creds.get("eaab_token")),
            "live_2fa": {
                "code": totp_code,
                "remaining_seconds": rem_secs,
            },
            "last_live_check_at": self.last_live_check_at.isoformat() if self.last_live_check_at else None,
            "last_token_refresh": self.last_token_refresh.isoformat() if self.last_token_refresh else None,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "email": creds.get("email", ""),
            "backup_email": creds.get("backup_email", ""),
        }

        if is_owner:
            base_data.update({
                "fb_password": creds.get("password", ""),
                "two_fa_secret": two_fa,
                "email_password": creds.get("email_password", ""),
                "backup_email_password": creds.get("backup_email_password", ""),
                "cookie": creds.get("cookie", ""),
                "eaag_token": creds.get("eaag_token", ""),
                "eaab_token": creds.get("eaab_token", ""),
                "fb_dtsg": creds.get("fb_dtsg", ""),
                "access_token": creds.get("access_token", ""),
                "raw_line": creds.get("raw_line", ""),
            })

        return base_data
    profile_dir: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False)

    # Fernet-encrypted JSON: {password, two_fa_secret, email, email_password, backup_email, cookie, access_token}
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)

    # Proxy config: host:port:user:pass hoặc URL, kèm trạng thái
    proxy_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proxy_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")  # LIVE, DIE, UNKNOWN, UNCHECKED

    # Trạng thái UID: LIVE, DIE, UNKNOWN
    uid_live_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN", index=True)

    # Trạng thái Token: ACTIVE, EXPIRED, CHECKPOINT, NONE
    token_status: Mapped[str] = mapped_column(String(32), default="NONE", index=True)

    # Trạng thái Login tự động: READY, LOGGING_IN, CHECKPOINT, WRONG_PASS, PENDING
    login_status: Mapped[str] = mapped_column(String(32), default="READY", index=True)
    last_login_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Số lượng tài sản phát hiện
    bm_count: Mapped[int] = mapped_column(Integer, default=0)
    ad_account_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)

    # MaxCare: phân loại VIA theo danh mục (FARM, DAILY, STO...)
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("via_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    device_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    friends_count: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    groups_count: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    gender: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    birthday: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    last_live_check_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    # Thời điểm token được Graph API xác thực thành công gần nhất.
    last_token_refresh: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    # Chỉ được điền từ metadata OAuth chính thức; /me không tự cung cấp thời hạn token.
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    # Relationships
    bms: Mapped[list[SyncedBM]] = relationship(
        "SyncedBM",
        back_populates="via_profile",
        cascade="all, delete-orphan",
    )
    ad_accounts: Mapped[list[SyncedAdAccount]] = relationship(
        "SyncedAdAccount",
        back_populates="via_profile",
        cascade="all, delete-orphan",
    )
    pages: Mapped[list[SyncedPage]] = relationship(
        "SyncedPage",
        back_populates="via_profile",
        cascade="all, delete-orphan",
    )
    category: Mapped[Optional["ViaCategory"]] = relationship("ViaCategory", back_populates="vias")
    activity_logs: Mapped[list["MaxcareActivityLog"]] = relationship(
        "MaxcareActivityLog",
        back_populates="via_profile",
        cascade="all, delete-orphan",
    )


class ViaCategory(Base):
    """Danh mục VIA kiểu MaxCare: Farm, Daily, Sto, Scan ctv, Scan ck..."""

    __tablename__ = "via_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    vias: Mapped[list[ViaProfile]] = relationship(
        "ViaProfile",
        back_populates="category",
        foreign_keys=lambda: [ViaProfile.category_id],
    )


class SyncedBM(Base):
    """Business Manager (BM) được đồng bộ từ dàn VIA, hỗ trợ gắn cờ BM Chính Cho Thuê."""

    __tablename__ = "synced_bms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bm_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    via_profile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("via_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Cờ đánh dấu BM Chính Cho Thuê (ưu tiên cấp phát cho khách hàng)
    is_primary_rental: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ad_account_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    bm_level: Mapped[str] = mapped_column(String(32), default="NOLIMIT")  # BM50, BM250, BM350, BM2500, NOLIMIT
    verified_status: Mapped[str] = mapped_column(String(32), default="VERIFIED")  # VERIFIED, UNVERIFIED
    created_year: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, default="2022")
    admin_count: Mapped[int] = mapped_column(Integer, default=1)
    hidden_admin_count: Mapped[int] = mapped_column(Integer, default=0)
    can_create_ad_account: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    @property
    def verification_status(self) -> str:
        return self.verified_status

    @verification_status.setter
    def verification_status(self, val: str) -> None:
        self.verified_status = val

    # Relationships
    via_profile: Mapped[Optional[ViaProfile]] = relationship("ViaProfile", back_populates="bms")


class SyncedAdAccount(Base):
    """Tài khoản quảng cáo (TK Cá nhân hoặc TK BM) phục vụ bảng Ads Check kiểu SMIT."""

    __tablename__ = "synced_ad_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    via_profile_id: Mapped[int] = mapped_column(
        ForeignKey("via_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    service_fee_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    bm_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    account_type: Mapped[str] = mapped_column(String(32), default="PERSONAL", index=True)  # PERSONAL, BM
    act_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status_dot: Mapped[str] = mapped_column(String(32), default="LIVE", index=True)  # LIVE, DIE, WARNING
    account_status: Mapped[int] = mapped_column(Integer, default=1)  # 1=ACTIVE, 2=DISABLED, 3=UNSETTLED...
    balance: Mapped[float] = mapped_column(Float, default=0.0)  # Số dư
    threshold: Mapped[float] = mapped_column(Float, default=0.0)  # Ngưỡng thanh toán
    ad_trust_dsl: Mapped[float] = mapped_column(Float, default=0.0)  # Limit chi tiêu ngày
    daily_budget: Mapped[float] = mapped_column(Float, default=0.0)  # Ngân sách ngày (MaxCare sync)
    total_spend: Mapped[float] = mapped_column(Float, default=0.0)  # Tổng tiền đã chi tiêu
    currency: Mapped[str] = mapped_column(String(16), default="VND")
    payment_card_brand: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # VISA, MASTERCARD
    payment_card_last4: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # 2555 -> VISA - 2555
    funding_source_last_four: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    amount_spent: Mapped[float] = mapped_column(Float, default=0.0)
    threshold_amount: Mapped[float] = mapped_column(Float, default=0.0)
    disable_reason: Mapped[str] = mapped_column(String(64), default="NONE")  # NONE, POLICY, RISK_PAYMENT, UNSETTLED, VERIFY_IDENTITY
    user_role: Mapped[str] = mapped_column(String(32), default="ADMIN")  # ADMIN, ADVERTISER, ANALYST
    timezone_name: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh | GMT+7")
    country_code: Mapped[str] = mapped_column(String(16), default="VN")
    tax_status: Mapped[str] = mapped_column(String(64), default="MIỄN THUẾ")
    admin_count: Mapped[int] = mapped_column(Integer, default=1)
    hidden_admin_count: Mapped[int] = mapped_column(Integer, default=0)
    hidden_limit: Mapped[float] = mapped_column(Float, default=0.0)  # DSL / limit ẩn
    funding_source_summary: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    card_bin: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    location_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    appeal_status: Mapped[str] = mapped_column(String(64), default="NONE")  # NONE, IN_REVIEW, APPROVED, REJECTED
    pixel_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    pixel_list: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    last_billed_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # 23-12-2022
    next_bill_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # 23-12-2022
    last_report_synced_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    # Relationships
    via_profile: Mapped[ViaProfile] = relationship("ViaProfile", back_populates="ad_accounts")
    customer: Mapped[Optional["Customer"]] = relationship("Customer")
    snapshots: Mapped[list["AdAccountSnapshot"]] = relationship(
        "AdAccountSnapshot",
        back_populates="ad_account",
        cascade="all, delete-orphan",
    )


class SyncedPage(Base):
    """Fanpage đồng bộ từ dàn VIA phục vụ quản lý & chia sẻ tài sản."""

    __tablename__ = "synced_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    via_profile_id: Mapped[int] = mapped_column(
        ForeignKey("via_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    likes_count: Mapped[int] = mapped_column(Integer, default=0)
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    appeal_status: Mapped[str] = mapped_column(String(64), default="NONE")  # NONE, IN_REVIEW, APPROVED, REJECTED
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    # Relationships
    via_profile: Mapped[ViaProfile] = relationship("ViaProfile", back_populates="pages")


class AdAccountSnapshot(Base):
    """Snapshot báo cáo TKQC append-only (unique act_id + snapshot_at), phục vụ dashboard & portal."""

    __tablename__ = "ad_account_snapshots"
    __table_args__ = (UniqueConstraint("act_id", "snapshot_at", name="uq_snapshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ad_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("synced_ad_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    act_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status_dot: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # LIVE, DIE, WARNING
    account_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    threshold: Mapped[float] = mapped_column(Float, default=0.0)
    ad_trust_dsl: Mapped[float] = mapped_column(Float, default=0.0)
    daily_budget: Mapped[float] = mapped_column(Float, default=0.0)
    total_spend: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(16), default="VND")
    snapshot_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="MAXCARE_REPORT_SYNC")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    ad_account: Mapped[Optional[SyncedAdAccount]] = relationship(
        "SyncedAdAccount", back_populates="snapshots"
    )


class MaxcareActivityLog(Base):
    """Nhật ký hoạt động MaxCare: BULK_LOGIN, CHECK_LIVE, UPDATE_INFO, SEEDING, REPORT_SYNC."""

    __tablename__ = "maxcare_activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    via_profile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("via_profiles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING, DONE, FAILED, PLANNED
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)

    via_profile: Mapped[Optional[ViaProfile]] = relationship("ViaProfile", back_populates="activity_logs")


# Model Aliases for flexible naming
SyncedBusinessManager = SyncedBM
SyncedFanpage = SyncedPage
ViaAccount = ViaProfile


