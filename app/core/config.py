from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sports"
    openai_api_key: str | None = None
    openai_model: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: int | None = None
    telegram_allowed_user_id: int | None = None
    news_fetch_interval_minutes: int = Field(default=5, ge=1)
    news_initial_lookback_hours: int = Field(default=24, ge=1)
    max_post_length: int = Field(default=260, ge=50, le=1000)
    http_timeout_seconds: float = Field(default=15, gt=0, le=120)
    external_api_max_retries: int = Field(default=3, ge=1, le=10)
    log_level: str = "INFO"
    scheduler_enabled: bool = False
    telegram_enabled: bool = False

    @field_validator("telegram_chat_id", "telegram_allowed_user_id", mode="before")
    @classmethod
    def empty_integer_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_integrations(self) -> "Settings":
        if self.scheduler_enabled and not (self.openai_api_key and self.openai_model):
            raise ValueError(
                "OPENAI_API_KEY and OPENAI_MODEL are required when scheduler is enabled"
            )
        if self.telegram_enabled and not all(
            (
                self.telegram_bot_token,
                self.telegram_chat_id,
                self.telegram_allowed_user_id,
            )
        ):
            raise ValueError(
                "TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID and "
                "TELEGRAM_ALLOWED_USER_ID are required when Telegram is enabled"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
