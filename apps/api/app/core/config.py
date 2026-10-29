from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADSOS_", extra="ignore")

    app_env: str = "local"
    database_url: str = "sqlite:///./adsos.db"
    meta_access_token: str = ""
    meta_token_map: str = ""
    # Phiên bản Marketing API mặc định — S16 (v21.0 đã hết hạn hỗ trợ; v26.0 đang hỗ trợ)
    meta_api_version: str = "v26.0"
    google_sheets_spreadsheet_id: str = ""
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""
    tron_wallet_address: str = ""
    # API key TrongGrid tùy chọn (server-side, không truyền ra frontend/log)
    tron_api_key: str = ""
    # Tự đồng bộ số dư ví (mặc định TẮT); tần suất tick + backoff
    usdt_scheduler_enabled: bool = True
    usdt_scheduler_lock_port: int = 8911
    usdt_sync_interval_minutes: int = 30
    scheduler_enabled: bool = True
    scheduler_lock_port: int = 8909
    sheets_scheduler_enabled: bool = True
    sheets_scheduler_lock_port: int = 8910
    checkpoint_grace_minutes: int = 15
    # Exchange connections (D-056): Fernet master key (bắt buộc khi lưu credentials);
    # scheduler auto-sync exchange mặc định TẮT
    exchange_master_key: str = ""
    exchange_admin_token: str = ""
    exchange_ui_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    exchange_scheduler_enabled: bool = False
    exchange_scheduler_lock_port: int = 8912
    exchange_sync_interval_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
