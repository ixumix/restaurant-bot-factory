"""Application configuration loaded from environment variables / `.env`."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for the constructor bot and its child bots."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    factory_bot_token: str = Field(
        ...,
        description="Telegram bot token of the constructor bot (the one users talk to).",
    )
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/factory.db",
        description="SQLAlchemy async URL.",
    )
    allowed_owner_ids: str = Field(
        default="",
        description="Comma-separated Telegram user IDs allowed to register as venue owners. Empty = everyone.",
    )
    log_level: str = Field(default="INFO")
    telegram_proxy_url: str = Field(
        default="",
        description="Optional proxy URL for Telegram API requests.",
    )

    @property
    def telegram_proxy_url_value(self) -> str | None:
        raw = self.telegram_proxy_url.strip()
        return raw or None

    @property
    def allowed_owner_id_set(self) -> set[int]:
        """Parse :pyattr:`allowed_owner_ids` into a set of integers."""
        raw = self.allowed_owner_ids.strip()
        if not raw:
            return set()
        return {int(part) for part in raw.split(",") if part.strip()}


def load_settings() -> Settings:
    """Load settings from env / `.env`. Separate function so tests can patch it."""
    return Settings()
