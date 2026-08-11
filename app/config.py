from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "API Aggregation Platform"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    secret_key: str = "change-me-in-production-use-a-long-random-string"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    database_url: str = "sqlite+aiosqlite:///./aggregator.db"

    default_timeout_seconds: float = 30.0
    default_max_retries: int = 2
    default_retry_backoff_seconds: float = 0.5
    aggregation_timeout_seconds: float = 45.0

    admin_username: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"

    # United Solutions SOAP (BookingAPI Group) — synced into us-* providers on startup
    us_endpoint: str = "http://dev.usbooking.org/us/UnitedSolutions"
    us_user_id: str = ""
    us_password: str = ""
    us_agency_id: str = ""
    us_client_ip: str = ""
    us_timeout_seconds: float = 90.0
    us_auto_enable: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
