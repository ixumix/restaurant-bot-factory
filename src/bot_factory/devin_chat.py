"""Devin (api.devin.ai) chat backend with multi-key fallback.

The Devin API is session-based: a session is created with an initial prompt
and then the agent works on it asynchronously. Follow-up messages are sent
to the same session. To use it as a chat backend we:

* Open one Devin session per Telegram user the first time they speak.
* Send each subsequent user turn as a session message.
* Poll the session until ``status_enum`` becomes ``blocked``/``finished``,
  meaning the agent has produced its reply and is waiting for the user.

This is fundamentally slower (seconds-to-minutes per reply) and more expensive
than a direct chat-completion API like Anthropic's. Use Claude when possible.

Multi-key rotation is only meaningful when *opening* a new session — once a
session exists it is bound to the key (and the org/user behind it) that
created it. Follow-up messages therefore always re-use the original key.
If that specific key is rate-limited / revoked, the bot will see an error
and may decide to drop the session and start a fresh one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


_DEFAULT_KEY_COOLDOWN_SECONDS = 60.0
_KEY_EXHAUSTED_STATUSES = frozenset({401, 402, 403, 429})

# Status values that indicate the agent has finished producing output and is
# now waiting for further user input (or is fully done).
_AGENT_DONE_STATUSES = frozenset({"blocked", "finished"})

# Status values that indicate the session is dead.
_AGENT_TERMINAL_STATUSES = frozenset({"expired", "finished"})


class DevinError(Exception):
    """Base error raised by :class:`DevinChatClient`."""


class DevinNoKeysError(DevinError):
    """Raised when no API keys are configured at all."""


class DevinAllKeysExhaustedError(DevinError):
    """Raised when every configured key was rejected for a new session."""


class DevinAPIError(DevinError):
    """Non-key-specific API failure (e.g. malformed request, 5xx)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Devin API error {status}: {message}")
        self.status = status
        self.api_message = message


class DevinSessionExpiredError(DevinError):
    """Raised when an existing session is no longer usable (expired/finished)."""

    def __init__(self, session_id: str, status: str | None) -> None:
        super().__init__(
            f"Devin session {session_id} is no longer usable (status={status!r})"
        )
        self.session_id = session_id
        self.status = status


class DevinTimeoutError(DevinError):
    """Raised when the agent didn't produce a reply within the allowed window."""


@dataclass
class _KeyState:
    """Per-key bookkeeping used for fair rotation and cooldowns."""

    key: str
    cooldown_until: float = 0.0
    consecutive_failures: int = 0
    last_error: str | None = None


@dataclass
class DevinReply:
    """Result of a successful chat turn."""

    session_id: str
    text: str
    key_index: int
    last_event_id: str | None


@dataclass
class DevinChatClient:
    """Minimal Devin /v1/sessions client tailored to chat use cases."""

    api_keys: Sequence[str]
    base_url: str = "https://api.devin.ai"
    timeout_seconds: float = 30.0
    poll_interval_seconds: float = 5.0
    response_timeout_seconds: float = 180.0
    key_cooldown_seconds: float = _DEFAULT_KEY_COOLDOWN_SECONDS
    max_acu_limit: int | None = None
    _keys: list[_KeyState] = field(init=False)
    _session: aiohttp.ClientSession | None = field(init=False, default=None)
    _start_index: int = field(init=False, default=0)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        if not self.api_keys:
            raise DevinNoKeysError("DevinChatClient requires at least one API key")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self.response_timeout_seconds <= 0:
            raise ValueError("response_timeout_seconds must be positive")
        self._keys = [_KeyState(key=k) for k in self.api_keys]

    # --------------------------------------------------------------- public

    async def start_session(self, *, prompt: str) -> DevinReply:
        """Open a new Devin session with ``prompt`` and wait for the first reply.

        Tries every configured key in round-robin order until one accepts the
        session-creation request. The chosen key is recorded in the returned
        :class:`DevinReply` so the caller can re-use it for follow-up turns.
        """
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        body: dict[str, Any] = {"prompt": prompt}
        if self.max_acu_limit is not None:
            body["max_acu_limit"] = self.max_acu_limit

        last_key_errors: list[str] = []

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

            try:
                payload = await self._post_json(
                    state.key,
                    "/v1/sessions",
                    body,
                )
            except _KeySpecificError as exc:
                self._mark_failure(state, exc.message, cooldown=True)
                last_key_errors.append(
                    f"key#{idx} status={exc.status}: {exc.message}"
                )
                continue
            except _NetworkError as exc:
                self._mark_failure(state, exc.message, cooldown=False)
                last_key_errors.append(f"key#{idx} network error: {exc.message}")
                continue

            self._mark_success(state)
            async with self._lock:
                self._start_index = (idx + 1) % len(self._keys)

            session_id = payload.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                raise DevinAPIError(200, "session_id missing in response")

            text, last_event = await self._await_reply(
                state.key,
                session_id,
                last_event_id=None,
            )
            return DevinReply(
                session_id=session_id,
                text=text,
                key_index=idx,
                last_event_id=last_event,
            )

        raise DevinAllKeysExhaustedError(
            "All Devin API keys are unavailable: " + "; ".join(last_key_errors)
            if last_key_errors
            else "All Devin API keys are unavailable"
        )

    async def send_message(
        self,
        *,
        session_id: str,
        message: str,
        key_index: int,
        last_event_id: str | None = None,
    ) -> DevinReply:
        """Send a follow-up ``message`` to an existing session and wait for reply.

        Uses the same key that created the session (``key_index``); only that
        key has visibility into the session.
        """
        if not message.strip():
            raise ValueError("message must not be empty")
        if key_index < 0 or key_index >= len(self._keys):
            raise ValueError(f"invalid key_index {key_index}")

        state = self._keys[key_index]
        try:
            await self._post_json(
                state.key,
                f"/v1/sessions/{session_id}/message",
                {"message": message},
            )
        except _KeySpecificError as exc:
            self._mark_failure(state, exc.message, cooldown=True)
            raise DevinAllKeysExhaustedError(
                f"key#{key_index} status={exc.status}: {exc.message}"
            ) from exc
        except _NetworkError as exc:
            self._mark_failure(state, exc.message, cooldown=False)
            raise DevinAPIError(0, exc.message) from exc

        self._mark_success(state)
        text, last_event = await self._await_reply(
            state.key,
            session_id,
            last_event_id=last_event_id,
        )
        return DevinReply(
            session_id=session_id,
            text=text,
            key_index=key_index,
            last_event_id=last_event,
        )

    async def aclose(self) -> None:
        """Close the underlying aiohttp session, if any."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    # ------------------------------------------------------------- internals

    async def _await_reply(
        self,
        key: str,
        session_id: str,
        *,
        last_event_id: str | None,
    ) -> tuple[str, str | None]:
        """Poll the session until the agent finishes a turn, return its text."""
        deadline = time.monotonic() + self.response_timeout_seconds
        while True:
            try:
                payload = await self._get_json(
                    key, f"/v1/sessions/{session_id}"
                )
            except _KeySpecificError as exc:
                raise DevinAllKeysExhaustedError(
                    f"polling failed: status={exc.status}: {exc.message}"
                ) from exc
            except _NetworkError as exc:
                raise DevinAPIError(0, exc.message) from exc

            status_enum = payload.get("status_enum")
            messages = payload.get("messages") or []

            new_text, new_last_event = self._extract_new_assistant_text(
                messages,
                after_event_id=last_event_id,
            )

            if status_enum in _AGENT_DONE_STATUSES:
                if new_text:
                    return new_text, new_last_event
                if status_enum in _AGENT_TERMINAL_STATUSES:
                    raise DevinSessionExpiredError(session_id, status_enum)
                # blocked but no new agent message — surface a friendly error.
                raise DevinAPIError(
                    200,
                    f"session ended in status={status_enum!r} with no reply",
                )

            if time.monotonic() >= deadline:
                raise DevinTimeoutError(
                    f"Devin session {session_id} did not respond within "
                    f"{self.response_timeout_seconds:.0f}s"
                )

            await asyncio.sleep(self.poll_interval_seconds)

    @staticmethod
    def _extract_new_assistant_text(
        messages: list[Any],
        *,
        after_event_id: str | None,
    ) -> tuple[str, str | None]:
        """Concatenate new agent messages that arrived after ``after_event_id``.

        We accept anything that doesn't look like a user-authored message.
        Empirically Devin emits ``type`` like ``devin_message`` for the agent
        and ``user_message`` for the human, but we stay tolerant in case the
        wire shape evolves.
        """
        skipping = after_event_id is not None
        chunks: list[str] = []
        last_event: str | None = after_event_id
        for raw in messages:
            if not isinstance(raw, dict):
                continue
            event_id = raw.get("event_id")
            if isinstance(event_id, str):
                last_event = event_id
            if skipping:
                if event_id == after_event_id:
                    skipping = False
                continue
            if not _is_assistant_message(raw):
                continue
            text = raw.get("message")
            if isinstance(text, str) and text.strip():
                chunks.append(text)
        return "\n\n".join(chunks).strip(), last_event

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _post_json(
        self, key: str, path: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request("POST", key, path, body=body)

    async def _get_json(self, key: str, path: str) -> dict[str, Any]:
        return await self._request("GET", key, path)

    async def _request(
        self,
        method: str,
        key: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = await self._get_session()
        url = self.base_url.rstrip("/") + path
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        try:
            if method == "POST":
                ctx = session.post(url, json=body, headers=headers)
            else:
                ctx = session.get(url, headers=headers)
            async with ctx as resp:
                status = resp.status
                payload_text = await resp.text()
        except (TimeoutError, aiohttp.ClientError) as exc:
            raise _NetworkError(str(exc)) from exc

        if 200 <= status < 300:
            return _parse_json(payload_text)

        api_message = _extract_error(payload_text)
        if status in _KEY_EXHAUSTED_STATUSES:
            raise _KeySpecificError(status, api_message)
        raise DevinAPIError(status, api_message)

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


# --- private helpers --------------------------------------------------------


class _KeySpecificError(Exception):
    """Internal: this specific key was rejected; rotate."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class _NetworkError(Exception):
    """Internal: transient network/timeout failure."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _is_assistant_message(raw: dict[str, Any]) -> bool:
    """Decide whether a session message was authored by the Devin agent."""
    msg_type = raw.get("type")
    origin = raw.get("origin")
    if isinstance(msg_type, str):
        lowered = msg_type.lower()
        # Anything explicitly tagged as user input is not assistant text.
        if "user" in lowered:
            return False
        if "devin" in lowered or "agent" in lowered or "assistant" in lowered:
            return True
    if isinstance(origin, str):
        lowered = origin.lower()
        if lowered == "devin" or lowered == "agent" or lowered == "assistant":
            return True
    # Fall back to "anything that isn't tagged as user". Devin emits various
    # internal events (tool calls, plan updates, ...) that we'd rather skip,
    # so we err on the side of *not* treating unknown types as assistant text.
    return False


def _parse_json(payload_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(payload_text or "{}")
    except json.JSONDecodeError as exc:
        raise DevinAPIError(200, f"invalid JSON in response: {exc}") from exc
    if not isinstance(payload, dict):
        raise DevinAPIError(200, "expected a JSON object response")
    return payload


def _extract_error(payload_text: str) -> str:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return payload_text[:500] or "unknown error"
    if isinstance(payload, dict):
        for key in ("detail", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                inner = value.get("message")
                if isinstance(inner, str) and inner:
                    return inner
    return payload_text[:500] or "unknown error"
