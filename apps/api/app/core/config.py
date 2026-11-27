from functools import lru_cache
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ADSOS_",
        extra="ignore",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
    )

    app_env: str = Field(
        default="local",
        validation_alias=AliasChoices("APP_ENV", "ADSOS_APP_ENV", "ENV"),
    )
    database_url: str = "sqlite:///./adsos.db"
    staff_auth_secret: str = ""
    staff_access_token_expires_minutes: int = 480
    staff_seed_default_owner: bool = True
    meta_access_token: str = ""
    meta_token_map: str = ""
    # Phiên bản Marketing API mặc định — S16 (v21.0 đã hết hạn hỗ trợ; v26.0 đang hỗ trợ)
    meta_api_version: str = "v26.0"
    # OAuth Meta chính thức. App secret chỉ được đọc ở backend và không bao giờ trả về frontend.
    facebook_app_id: str = Field(
        default="",
        validation_alias=AliasChoices("FACEBOOK_APP_ID", "ADSOS_FACEBOOK_APP_ID"),
    )
    facebook_app_secret: str = Field(
        default="",
        validation_alias=AliasChoices("FACEBOOK_APP_SECRET", "ADSOS_FACEBOOK_APP_SECRET"),
    )
    facebook_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/api/v1/oauth/facebook/callback",
        validation_alias=AliasChoices("FACEBOOK_REDIRECT_URI", "ADSOS_FACEBOOK_REDIRECT_URI"),
    )
    google_sheets_spreadsheet_id: str = ""
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""
    telegram_allowed_chat_ids: str = ""
    telegram_webhook_secret: str = ""
    # Hạn mức ngân sách ngày tối đa cho campaign tạo mới qua bot/pipeline (VND hoặc tương đương)
    meta_max_daily_budget: float = 50_000_000.0
    meta_writes_enabled: bool = False
    tron_wallet_address: str = ""
    # API key TrongGrid tùy chọn (server-side, không truyền ra frontend/log)
    tron_api_key: str = ""
    # Tự đồng bộ số dư ví (mặc định TẮT); tần suất tick + backoff
    usdt_scheduler_enabled: bool = True
    usdt_scheduler_lock_port: int = 8911
    usdt_sync_interval_minutes: int = 30
    scheduler_enabled: bool = True
    scheduler_lock_port: int = 8909
    # Tác vụ nền VIA: chỉ kiểm tra token qua Graph API chính thức, không trích token từ cookie/CDP.
    via_token_keepalive_enabled: bool = True
    via_token_keepalive_interval_hours: int = 6
    via_token_jitter_min_seconds: float = 2.0
    via_token_jitter_max_seconds: float = 5.0
    via_asset_sync_enabled: bool = True
    via_asset_sync_interval_hours: int = 2
    sheets_scheduler_enabled: bool = True
    sheets_scheduler_lock_port: int = 8910
    customer_sheets_writes_enabled: bool = False
    checkpoint_grace_minutes: int = 15
    # Exchange connections (D-056): Fernet master key (bắt buộc khi lưu credentials);
    # scheduler auto-sync exchange mặc định TẮT
    exchange_master_key: str = ""
    exchange_admin_token: str = ""
    exchange_ui_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    exchange_scheduler_enabled: bool = False
    exchange_scheduler_lock_port: int = 8912
    exchange_sync_interval_minutes: int = 30
    # metaOs Extension compatibility server. Public base may be HTTPS in staging/production;
    # local defaults to the request origin so tests and localhost need no extra config.
    extension_public_base_url: str = ""
    ai_api_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    # Cấu hình AI Copilot & LLM Orchestrator (D-066)
    llm_provider: str = Field(
        default="gemini",
        validation_alias=AliasChoices("LLM_PROVIDER", "ADSOS_LLM_PROVIDER"),
    )
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "ADSOS_GEMINI_API_KEY", "AI_API_KEY", "ADSOS_AI_API_KEY"),
    )
    gemini_model: str = Field(
        default="gemini-3-flash-preview",
        validation_alias=AliasChoices("GEMINI_MODEL", "ADSOS_GEMINI_MODEL", "AI_MODEL", "ADSOS_AI_MODEL"),
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "ADSOS_OLLAMA_BASE_URL"),
    )
    ollama_model: str = Field(
        default="llama3",
        validation_alias=AliasChoices("OLLAMA_MODEL", "ADSOS_OLLAMA_MODEL"),
    )
    # Telegram Bot Polling (ENV=development/local) vs Webhook (ENV=production)
    telegram_polling_enabled: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_POLLING_ENABLED", "ADSOS_TELEGRAM_POLLING_ENABLED"),
    )
    telegram_polling_lock_port: int = 8913
    telegram_polling_interval_seconds: float = 1.0
    zalo_notify_url: str = ""
    zalo_notify_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
