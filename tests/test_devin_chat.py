"""Tests for :mod:`bot_factory.devin_chat` — Devin sessions chat backend.

We stub out ``aiohttp.ClientSession`` with a fake that returns a queue of
responses keyed on (method, path), and patch ``asyncio.sleep`` so that the
polling loop doesn't actually wait between iterations.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

import bot_factory.devin_chat as devin_chat
from bot_factory.devin_chat import (
    DevinAllKeysExhaustedError,
    DevinAPIError,
    DevinChatClient,
    DevinNoKeysError,
    DevinReply,
    DevinSessionExpiredError,
    DevinTimeoutError,
)


@dataclass
class _FakeResponse:
    status: int
    body: str

    async def text(self) -> str:
        return self.body

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


@dataclass
class _FakeSession:
    """Stand-in for aiohttp.ClientSession.

    Pops responses off ``responses`` in order. Each call is recorded.
    """

    responses: list[tuple[int, str]]
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    def post(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str],
    ) -> _FakeResponse:
        return self._next("POST", url, json, headers)

    def get(self, url: str, *, headers: dict[str, str]) -> _FakeResponse:
        return self._next("GET", url, None, headers)

    def _next(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> _FakeResponse:
        if not self.responses:
            raise AssertionError(
                f"FakeSession ran out of queued responses on {method} {url}"
            )
        status, payload = self.responses.pop(0)
        self.calls.append(
            {
                "method": method,
                "url": url,
                "json": body,
                "headers": dict(headers),
            }
        )
        return _FakeResponse(status=status, body=payload)

    async def close(self) -> None:
        self.closed = True


def _make_client(
    keys: list[str],
    responses: list[tuple[int, str]],
    *,
    poll: float = 0.01,
    timeout: float = 5.0,
) -> tuple[DevinChatClient, list[dict[str, Any]]]:
    client = DevinChatClient(
        api_keys=keys,
        poll_interval_seconds=poll,
        response_timeout_seconds=timeout,
    )
    session = _FakeSession(responses=responses)
    client._session = session  # type: ignore[assignment]
    return client, session.calls


def _patch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(devin_chat.asyncio, "sleep", _no_sleep)


def _create_session_body(session_id: str = "devin-1") -> str:
    return json.dumps({"session_id": session_id, "url": "https://app.devin.ai/x"})


def _session_status_body(
    *,
    status_enum: str | None,
    messages: list[dict[str, Any]] | None = None,
    session_id: str = "devin-1",
) -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "status": status_enum or "working",
            "status_enum": status_enum,
            "messages": messages or [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:01",
        }
    )


def _agent_msg(text: str, event_id: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "type": "devin_message",
        "message": text,
        "timestamp": "2026-01-01T00:00:01",
    }


def _user_msg(text: str, event_id: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "type": "user_message",
        "message": text,
        "timestamp": "2026-01-01T00:00:00",
    }


def test_no_keys_raises() -> None:
    with pytest.raises(DevinNoKeysError):
        DevinChatClient(api_keys=[])


async def test_start_session_first_key_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, calls = _make_client(
        ["k1", "k2"],
        [
            (200, _create_session_body("devin-1")),
            (
                200,
                _session_status_body(
                    status_enum="blocked",
                    messages=[
                        _user_msg("hi", "ev0"),
                        _agent_msg("hello there", "ev1"),
                    ],
                ),
            ),
        ],
    )
    reply = await client.start_session(prompt="hi")
    assert isinstance(reply, DevinReply)
    assert reply.session_id == "devin-1"
    assert reply.text == "hello there"
    assert reply.key_index == 0
    assert reply.last_event_id == "ev1"
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"].endswith("/v1/sessions")
    assert calls[0]["headers"]["Authorization"] == "Bearer k1"
    assert calls[1]["method"] == "GET"
    assert calls[1]["url"].endswith("/v1/sessions/devin-1")


async def test_start_session_rotates_on_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, calls = _make_client(
        ["k1", "k2"],
        [
            (429, json.dumps({"detail": "rate limited"})),
            (200, _create_session_body("devin-2")),
            (
                200,
                _session_status_body(
                    status_enum="blocked",
                    messages=[_agent_msg("ok", "ev1")],
                    session_id="devin-2",
                ),
            ),
        ],
    )
    reply = await client.start_session(prompt="hi")
    assert reply.session_id == "devin-2"
    assert reply.key_index == 1
    assert [c["headers"]["Authorization"] for c in calls] == [
        "Bearer k1",
        "Bearer k2",
        "Bearer k2",
    ]


async def test_start_session_rotates_on_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, calls = _make_client(
        ["k1", "k2"],
        [
            (401, json.dumps({"detail": "invalid key"})),
            (200, _create_session_body("devin-2")),
            (
                200,
                _session_status_body(
                    status_enum="blocked",
                    messages=[_agent_msg("ok", "ev1")],
                    session_id="devin-2",
                ),
            ),
        ],
    )
    reply = await client.start_session(prompt="hi")
    assert reply.key_index == 1
    assert [c["headers"]["Authorization"] for c in calls[:2]] == [
        "Bearer k1",
        "Bearer k2",
    ]


async def test_start_session_all_keys_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, calls = _make_client(
        ["k1", "k2"],
        [
            (429, json.dumps({"detail": "rate limited"})),
            (402, json.dumps({"detail": "no credit"})),
        ],
    )
    with pytest.raises(DevinAllKeysExhaustedError):
        await client.start_session(prompt="hi")
    assert [c["headers"]["Authorization"] for c in calls] == [
        "Bearer k1",
        "Bearer k2",
    ]


async def test_start_session_non_key_error_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, calls = _make_client(
        ["k1", "k2"],
        [(400, json.dumps({"detail": "bad request"}))],
    )
    with pytest.raises(DevinAPIError) as info:
        await client.start_session(prompt="hi")
    assert info.value.status == 400
    # 400 is not key-specific — we should not have rotated.
    assert [c["headers"]["Authorization"] for c in calls] == ["Bearer k1"]


async def test_send_message_uses_specified_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, calls = _make_client(
        ["k1", "k2"],
        [
            (200, "{}"),
            (
                200,
                _session_status_body(
                    status_enum="blocked",
                    messages=[
                        _agent_msg("first", "ev1"),
                        _user_msg("hi again", "ev2"),
                        _agent_msg("second", "ev3"),
                    ],
                ),
            ),
        ],
    )
    reply = await client.send_message(
        session_id="devin-1",
        message="hi again",
        key_index=1,
        last_event_id="ev1",
    )
    assert reply.text == "second"
    assert reply.last_event_id == "ev3"
    assert reply.key_index == 1
    # Both POST + GET went out with the explicit key.
    assert [c["headers"]["Authorization"] for c in calls] == [
        "Bearer k2",
        "Bearer k2",
    ]
    assert calls[0]["url"].endswith("/v1/sessions/devin-1/message")
    assert calls[0]["json"] == {"message": "hi again"}


async def test_send_message_raises_on_key_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, _ = _make_client(
        ["k1", "k2"],
        [(401, json.dumps({"detail": "invalid"}))],
    )
    with pytest.raises(DevinAllKeysExhaustedError):
        await client.send_message(
            session_id="devin-1",
            message="hi",
            key_index=0,
        )


async def test_polling_waits_for_blocked_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, _ = _make_client(
        ["k1"],
        [
            (200, _create_session_body("devin-1")),
            # First poll: still working, no agent reply yet.
            (200, _session_status_body(status_enum="working", messages=[])),
            # Second poll: still working, partial messages.
            (
                200,
                _session_status_body(
                    status_enum="working",
                    messages=[_agent_msg("thinking…", "ev1")],
                ),
            ),
            # Third poll: blocked + final agent message.
            (
                200,
                _session_status_body(
                    status_enum="blocked",
                    messages=[
                        _agent_msg("thinking…", "ev1"),
                        _agent_msg("done!", "ev2"),
                    ],
                ),
            ),
        ],
    )
    reply = await client.start_session(prompt="hi")
    # Both agent messages get concatenated.
    assert "thinking" in reply.text
    assert "done!" in reply.text
    assert reply.last_event_id == "ev2"


async def test_polling_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    # Generate enough "still working" responses to exceed the timeout.
    responses: list[tuple[int, str]] = [
        (200, _create_session_body("devin-1")),
    ]
    for _ in range(20):
        responses.append(
            (200, _session_status_body(status_enum="working", messages=[]))
        )

    # Each call to monotonic returns a value 100s in the future, so the
    # deadline (now + 1.0s) is exceeded on the very first poll iteration.
    counter = {"n": 0}

    def _fake_monotonic() -> float:
        counter["n"] += 1
        return float(counter["n"]) * 100.0

    monkeypatch.setattr(devin_chat.time, "monotonic", _fake_monotonic)

    client, _ = _make_client(
        ["k1"], responses, poll=0.01, timeout=1.0
    )
    with pytest.raises(DevinTimeoutError):
        await client.start_session(prompt="hi")


async def test_session_finished_without_reply_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, _ = _make_client(
        ["k1"],
        [
            (200, "{}"),
            (
                200,
                _session_status_body(
                    status_enum="finished",
                    messages=[_user_msg("hi", "ev0")],
                ),
            ),
        ],
    )
    with pytest.raises(DevinSessionExpiredError):
        await client.send_message(
            session_id="devin-1", message="hi", key_index=0
        )


async def test_extract_filters_user_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, _ = _make_client(
        ["k1"],
        [
            (200, _create_session_body("devin-1")),
            (
                200,
                _session_status_body(
                    status_enum="blocked",
                    messages=[
                        _user_msg("hi", "ev0"),
                        _agent_msg("only this", "ev1"),
                        _user_msg("ignore this", "ev2"),
                    ],
                ),
            ),
        ],
    )
    reply = await client.start_session(prompt="hi")
    assert reply.text == "only this"


async def test_send_message_skips_old_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Messages on or before ``last_event_id`` must be ignored."""
    _patch_sleep(monkeypatch)
    client, _ = _make_client(
        ["k1"],
        [
            (200, "{}"),
            (
                200,
                _session_status_body(
                    status_enum="blocked",
                    messages=[
                        _agent_msg("old reply", "ev1"),
                        _user_msg("follow up", "ev2"),
                        _agent_msg("new reply", "ev3"),
                    ],
                ),
            ),
        ],
    )
    reply = await client.send_message(
        session_id="devin-1",
        message="follow up",
        key_index=0,
        last_event_id="ev1",
    )
    assert reply.text == "new reply"
    assert reply.last_event_id == "ev3"


async def test_start_session_rejects_empty_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, _ = _make_client(["k1"], [])
    with pytest.raises(ValueError):
        await client.start_session(prompt="   ")


async def test_send_message_rejects_invalid_key_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client, _ = _make_client(["k1"], [])
    with pytest.raises(ValueError):
        await client.send_message(
            session_id="devin-1", message="hi", key_index=5
        )


async def test_max_acu_limit_included_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client = DevinChatClient(
        api_keys=["k1"],
        poll_interval_seconds=0.01,
        response_timeout_seconds=5.0,
        max_acu_limit=42,
    )
    session = _FakeSession(
        responses=[
            (200, _create_session_body("devin-1")),
            (
                200,
                _session_status_body(
                    status_enum="blocked",
                    messages=[_agent_msg("ok", "ev1")],
                ),
            ),
        ]
    )
    client._session = session  # type: ignore[assignment]
    await client.start_session(prompt="hi")
    assert session.calls[0]["json"]["max_acu_limit"] == 42


async def test_resolved_backend_via_settings_module() -> None:
    """Sanity-check the small Settings helper that picks the backend."""
    from bot_factory.config import Settings

    s = Settings(factory_bot_token="x", claude_api_keys="k", devin_api_keys="d")
    assert s.resolved_support_backend == "claude"

    s = Settings(
        factory_bot_token="x",
        claude_api_keys="k",
        devin_api_keys="d",
        support_backend="devin",
    )
    assert s.resolved_support_backend == "devin"

    s = Settings(factory_bot_token="x", devin_api_keys="d")
    assert s.resolved_support_backend == "devin"

    s = Settings(factory_bot_token="x", support_backend="claude")
    assert s.resolved_support_backend == "none"


# Make sure pytest treats async tests above as coroutines via asyncio.
@pytest.fixture(autouse=True)
def _aio() -> Callable[[Awaitable[Any]], Any]:
    """Placeholder so pytest-asyncio picks up the module config if needed."""
    return lambda x: x
