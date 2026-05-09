"""Anthropic (Claude) HTTP client with multi-key fallback.

The support chat feature in child bots relies on this client. Multiple API
keys can be configured — when one is rate-limited or out of credit, the
client transparently rotates to the next one and retries the request.

Only a single endpoint is used: ``POST {base_url}/v1/messages`` with the
standard Anthropic Messages API payload.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


# Default cooldown applied to a key after it returns a quota / rate-limit
# error. While the cooldown is active the key is skipped during rotation.
_DEFAULT_KEY_COOLDOWN_SECONDS = 60.0

# HTTP statuses that mean "this specific key is exhausted, try another one".
# 401 / 403 — invalid or revoked key.
# 429       — rate limited.
# 402       — payment required (credit balance too low).
_KEY_EXHAUSTED_STATUSES = frozenset({401, 402, 403, 429})


class ClaudeError(Exception):
    """Base error raised by :class:`ClaudeClient`."""


class ClaudeNoKeysError(ClaudeError):
    """Raised when no API keys are configured at all."""


class ClaudeAllKeysExhaustedError(ClaudeError):
    """Raised when every configured key failed for the current request."""


class ClaudeAPIError(ClaudeError):
    """Raised on a non-key-specific API failure (e.g. malformed request)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Claude API error {status}: {message}")
        self.status = status
        self.api_message = message


@dataclass
class _KeyState:
    """Per-key bookkeeping used for fair rotation and cooldowns."""

    key: str
    cooldown_until: float = 0.0
    consecutive_failures: int = 0
    last_error: str | None = None


@dataclass
class ChatMessage:
    """A single message in the support-chat history."""

    role: str  # "user" | "assistant"
    content: str

    def to_api(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ClaudeClient:
    """Async Anthropic client that rotates between multiple API keys.

    The client itself is stateless across requests except for the per-key
    cooldowns kept in :pyattr:`_keys`. It is safe to share between handlers
    in the same event loop.
    """

    api_keys: Sequence[str]
    model: str
    max_tokens: int = 1024
    base_url: str = "https://api.anthropic.com"
    anthropic_version: str = "2023-06-01"
    timeout_seconds: float = 60.0
    key_cooldown_seconds: float = _DEFAULT_KEY_COOLDOWN_SECONDS
    _keys: list[_KeyState] = field(init=False)
    _session: aiohttp.ClientSession | None = field(init=False, default=None)
    _start_index: int = field(init=False, default=0)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        if not self.api_keys:
            raise ClaudeNoKeysError("ClaudeClient requires at least one API key")
        self._keys = [_KeyState(key=k) for k in self.api_keys]

    # --------------------------------------------------------------- public

    async def send(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str | None = None,
    ) -> str:
        """Send ``messages`` to Claude and return the assistant's text reply.

        Raises :class:`ClaudeAllKeysExhaustedError` when every configured key
        has been rejected by the API for this request, or
        :class:`ClaudeAPIError` for a non-key-specific failure.
        """
        if not messages:
            raise ValueError("messages must not be empty")

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [m.to_api() for m in messages],
        }
        if system:
            body["system"] = system

        session = await self._get_session()
        url = self.base_url.rstrip("/") + "/v1/messages"

        last_key_errors: list[str] = []

        # Iterate over all keys, starting at the round-robin offset so we
        # don't hammer the first key on every call.
        async with self._lock:
            start = self._start_index
        order = list(range(len(self._keys)))
        order = order[start:] + order[:start]

        for idx in order:
            state = self._keys[idx]
            if not self._is_available(state):
                last_key_errors.append(
                    f"key#{idx} cooling down: {state.last_error or 'rate-limited'}"
                )
                continue

            headers = {
                "x-api-key": state.key,
                "anthropic-version": self.anthropic_version,
                "content-type": "application/json",
            }

            try:
                async with session.post(url, json=body, headers=headers) as resp:
                    status = resp.status
                    payload_text = await resp.text()
            except (TimeoutError, aiohttp.ClientError) as exc:
                logger.warning(
                    "Claude request failed for key#%d: %s", idx, exc
                )
                self._mark_failure(state, str(exc), cooldown=False)
                last_key_errors.append(f"key#{idx} network error: {exc}")
                continue

            if status == 200:
                self._mark_success(state)
                async with self._lock:
                    # Round-robin: next call should start at the next key.
                    self._start_index = (idx + 1) % len(self._keys)
                return self._extract_text(payload_text)

            # Non-success: parse the error message from the body if we can.
            api_message = self._extract_error(payload_text)

            if status in _KEY_EXHAUSTED_STATUSES:
                logger.warning(
                    "Claude API rejected key#%d (status=%d): %s",
                    idx,
                    status,
                    api_message,
                )
                self._mark_failure(state, api_message, cooldown=True)
                last_key_errors.append(
                    f"key#{idx} status={status}: {api_message}"
                )
                continue

            # Anything else (400 bad request, 500, 529 overloaded, ...) is not
            # the key's fault — surface it directly.
            self._mark_failure(state, api_message, cooldown=False)
            raise ClaudeAPIError(status, api_message)

        raise ClaudeAllKeysExhaustedError(
            "All Claude API keys are unavailable: " + "; ".join(last_key_errors)
            if last_key_errors
            else "All Claude API keys are unavailable"
        )

    async def aclose(self) -> None:
        """Close the underlying aiohttp session, if any."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    # ------------------------------------------------------------- internals

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    def _is_available(self, state: _KeyState) -> bool:
        return time.monotonic() >= state.cooldown_until

    def _mark_success(self, state: _KeyState) -> None:
        state.cooldown_until = 0.0
        state.consecutive_failures = 0
        state.last_error = None

    def _mark_failure(
        self, state: _KeyState, message: str, *, cooldown: bool
    ) -> None:
        state.consecutive_failures += 1
        state.last_error = message
        if cooldown:
            state.cooldown_until = time.monotonic() + self.key_cooldown_seconds

    @staticmethod
    def _extract_text(payload_text: str) -> str:
        """Parse a successful ``/v1/messages`` response and return the text."""
        import json

        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise ClaudeAPIError(200, f"invalid JSON in response: {exc}") from exc

        content = payload.get("content")
        if not isinstance(content, list):
            raise ClaudeAPIError(200, "missing `content` array in response")

        chunks: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        text = "".join(chunks).strip()
        if not text:
            raise ClaudeAPIError(200, "empty text in response")
        return text

    @staticmethod
    def _extract_error(payload_text: str) -> str:
        """Best-effort extraction of an error message from the API body."""
        import json

        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return payload_text[:500] or "unknown error"

        err = payload.get("error")
        if isinstance(err, dict):
            message = err.get("message")
            if isinstance(message, str):
                return message
        message = payload.get("message")
        if isinstance(message, str):
            return message
        return payload_text[:500] or "unknown error"
