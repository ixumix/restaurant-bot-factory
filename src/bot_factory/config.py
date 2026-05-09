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

    # ---- Claude / Anthropic support chat ---------------------------------
    claude_api_keys: str = Field(
        default="",
        description=(
            "Comma-separated Anthropic API keys. The support chat tries them "
            "in order and rotates to the next when one is rate-limited or "
            "out of credit. Empty disables the support chat feature."
        ),
    )
    claude_model: str = Field(
        default="claude-opus-4-5",
        description="Anthropic model name used for the support chat.",
    )
    claude_base_url: str = Field(
        default="https://api.anthropic.com",
        description="Base URL of the Anthropic API. Override for proxies.",
    )
    claude_anthropic_version: str = Field(
        default="2023-06-01",
        description="Value of the `anthropic-version` header.",
    )
    claude_max_tokens: int = Field(
        default=1024,
        description="Maximum tokens to generate in a single Claude reply.",
    )
    claude_history_limit: int = Field(
        default=10,
        description=(
            "How many of the most recent (user, assistant) message pairs are "
            "kept in the support chat context window."
        ),
    )
    claude_timeout_seconds: float = Field(
        default=60.0,
        description="HTTP timeout for a single Claude API call.",
    )
    claude_system_prompt: str = Field(
        default="",
        description=(
            "Optional override for the default support-chat system prompt. "
            "Empty falls back to a built-in restaurant-support prompt."
        ),
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

    @property
    def claude_api_key_list(self) -> list[str]:
        """Parse :pyattr:`claude_api_keys` into a list of non-empty keys."""
        raw = self.claude_api_keys.strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def claude_system_prompt_value(self) -> str | None:
        raw = self.claude_system_prompt.strip()
        return raw or None


def load_settings() -> Settings:
    """Load settings from env / `.env`. Separate function so tests can patch it."""
    return Settings()
