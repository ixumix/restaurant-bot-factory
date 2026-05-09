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

    # ---- Devin (api.devin.ai) chat backend -------------------------------
    devin_api_keys: str = Field(
        default="",
        description=(
            "Comma-separated Devin API keys (apk_* or cog_*). When set, the "
            "support chat opens a Devin session per Telegram user instead of "
            "calling Claude directly. Devin sessions are slower (seconds-to-"
            "minutes per reply) and cost ACUs — prefer Claude when possible."
        ),
    )
    devin_base_url: str = Field(
        default="https://api.devin.ai",
        description="Base URL of the Devin API.",
    )
    devin_poll_interval_seconds: float = Field(
        default=5.0,
        description="How often to poll a Devin session while waiting for a reply.",
    )
    devin_response_timeout_seconds: float = Field(
        default=180.0,
        description=(
            "Maximum time (seconds) to wait for a single Devin reply before "
            "giving up. Devin sessions can be slow; bump this for very long "
            "agentic answers."
        ),
    )
    devin_max_acu_limit: int = Field(
        default=0,
        description=(
            "Optional ACU cap for each Devin support session. 0 disables the "
            "cap (uses the org's default)."
        ),
    )
    support_backend: str = Field(
        default="auto",
        description=(
            "Which chat backend powers the support chat: `claude`, `devin`, "
            "or `auto` (prefer Claude, fall back to Devin if only Devin keys "
            "are configured)."
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

    @property
    def devin_api_key_list(self) -> list[str]:
        """Parse :pyattr:`devin_api_keys` into a list of non-empty keys."""
        raw = self.devin_api_keys.strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def devin_max_acu_limit_value(self) -> int | None:
        """``None`` when ``devin_max_acu_limit`` is 0/unset."""
        return self.devin_max_acu_limit if self.devin_max_acu_limit > 0 else None

    @property
    def resolved_support_backend(self) -> str:
        """Pick the actually-active chat backend based on configured keys.

        Returns one of ``"claude"``, ``"devin"`` or ``"none"``.
        """
        choice = self.support_backend.strip().lower() or "auto"
        has_claude = bool(self.claude_api_key_list)
        has_devin = bool(self.devin_api_key_list)
        if choice == "claude":
            return "claude" if has_claude else "none"
        if choice == "devin":
            return "devin" if has_devin else "none"
        # auto: prefer Claude, fall back to Devin.
        if has_claude:
            return "claude"
        if has_devin:
            return "devin"
        return "none"


def load_settings() -> Settings:
    """Load settings from env / `.env`. Separate function so tests can patch it."""
    return Settings()
