"""Tests for :mod:`bot_factory.claude` — multi-key fallback logic.

The tests stub out ``aiohttp.ClientSession`` with a fake that returns a
queued list of responses, so we can verify how the client behaves when keys
are rate-limited, exhausted or successful — without making real HTTP calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from bot_factory.claude import (
    ChatMessage,
    ClaudeAllKeysExhaustedError,
    ClaudeAPIError,
    ClaudeClient,
    ClaudeNoKeysError,
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
    """Minimal aiohttp.ClientSession stand-in.

    Keeps a queue of (status, body) tuples and returns them in order. Records
    every call so tests can assert which key was used.
    """

    responses: list[tuple[int, str]]
    calls: list[dict[str, Any]]
    closed: bool = False

    def post(
        self, url: str, *, json: dict[str, Any], headers: dict[str, str]
    ) -> _FakeResponse:
        if not self.responses:
            raise AssertionError("FakeSession ran out of queued responses")
        status, body = self.responses.pop(0)
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": dict(headers),
            }
        )
        return _FakeResponse(status=status, body=body)

    async def close(self) -> None:
        self.closed = True


def _ok_body(text: str = "hi") -> str:
    return json.dumps(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        }
    )


def _err_body(message: str, type_: str = "rate_limit_error") -> str:
    return json.dumps({"type": "error", "error": {"type": type_, "message": message}})


def _make_client(
    keys: list[str],
    responses: list[tuple[int, str]],
) -> tuple[ClaudeClient, list[dict[str, Any]]]:
    client = ClaudeClient(api_keys=keys, model="claude-test")
    calls: list[dict[str, Any]] = []
    session = _FakeSession(responses=responses, calls=calls)
    # Inject the fake session.
    client._session = session  # type: ignore[assignment]
    return client, calls


def test_no_keys_raises() -> None:
    with pytest.raises(ClaudeNoKeysError):
        ClaudeClient(api_keys=[], model="claude-test")


async def test_first_key_success() -> None:
    client, calls = _make_client(["k1", "k2"], [(200, _ok_body("hello"))])
    reply = await client.send([ChatMessage(role="user", content="hi")])
    assert reply == "hello"
    assert len(calls) == 1
    assert calls[0]["headers"]["x-api-key"] == "k1"
    assert calls[0]["json"]["model"] == "claude-test"
    assert calls[0]["json"]["messages"] == [{"role": "user", "content": "hi"}]


async def test_rotates_on_429() -> None:
    client, calls = _make_client(
        ["k1", "k2", "k3"],
        [
            (429, _err_body("rate limited")),
            (200, _ok_body("ok")),
        ],
    )
    reply = await client.send([ChatMessage(role="user", content="hi")])
    assert reply == "ok"
    assert [c["headers"]["x-api-key"] for c in calls] == ["k1", "k2"]


async def test_rotates_on_402_credit() -> None:
    client, calls = _make_client(
        ["k1", "k2"],
        [
            (402, _err_body("credit balance too low", type_="invalid_request_error")),
            (200, _ok_body("ok")),
        ],
    )
    reply = await client.send([ChatMessage(role="user", content="hi")])
    assert reply == "ok"
    assert [c["headers"]["x-api-key"] for c in calls] == ["k1", "k2"]


async def test_rotates_on_401_invalid_key() -> None:
    client, calls = _make_client(
        ["k1", "k2"],
        [
            (401, _err_body("invalid key", type_="authentication_error")),
            (200, _ok_body("ok")),
        ],
    )
    reply = await client.send([ChatMessage(role="user", content="hi")])
    assert reply == "ok"
    assert [c["headers"]["x-api-key"] for c in calls] == ["k1", "k2"]


async def test_all_keys_exhausted_raises() -> None:
    client, calls = _make_client(
        ["k1", "k2"],
        [
            (429, _err_body("rate limited")),
            (429, _err_body("rate limited")),
        ],
    )
    with pytest.raises(ClaudeAllKeysExhaustedError):
        await client.send([ChatMessage(role="user", content="hi")])
    assert [c["headers"]["x-api-key"] for c in calls] == ["k1", "k2"]


async def test_non_key_error_surfaces_as_api_error() -> None:
    client, calls = _make_client(
        ["k1", "k2"],
        [(400, _err_body("bad request", type_="invalid_request_error"))],
    )
    with pytest.raises(ClaudeAPIError) as info:
        await client.send([ChatMessage(role="user", content="hi")])
    assert info.value.status == 400
    # The 400 is not key-specific, so we should not have rotated.
    assert [c["headers"]["x-api-key"] for c in calls] == ["k1"]


async def test_round_robin_starts_from_next_key_after_success() -> None:
    """After a successful call on key#0 the next request should start at key#1."""
    client, calls = _make_client(
        ["k1", "k2"],
        [
            (200, _ok_body("first")),
            (200, _ok_body("second")),
        ],
    )
    r1 = await client.send([ChatMessage(role="user", content="a")])
    r2 = await client.send([ChatMessage(role="user", content="b")])
    assert r1 == "first"
    assert r2 == "second"
    assert [c["headers"]["x-api-key"] for c in calls] == ["k1", "k2"]


async def test_cooldown_skips_recently_failed_key() -> None:
    """A key that returned 429 should be skipped on the next request."""
    client, calls = _make_client(
        ["k1", "k2"],
        [
            # First call: k1 is rate-limited, k2 succeeds.
            (429, _err_body("rate limited")),
            (200, _ok_body("first")),
            # Second call: round-robin would start from k1 again, but k1 is
            # cooling down, so k2 must be tried first.
            (200, _ok_body("second")),
        ],
    )
    r1 = await client.send([ChatMessage(role="user", content="a")])
    assert r1 == "first"

    r2 = await client.send([ChatMessage(role="user", content="b")])
    assert r2 == "second"
    assert [c["headers"]["x-api-key"] for c in calls] == ["k1", "k2", "k2"]


async def test_send_includes_system_prompt_when_provided() -> None:
    client, calls = _make_client(["k1"], [(200, _ok_body("ok"))])
    await client.send(
        [ChatMessage(role="user", content="hi")],
        system="Be terse.",
    )
    assert calls[0]["json"]["system"] == "Be terse."


async def test_send_omits_system_when_not_provided() -> None:
    client, calls = _make_client(["k1"], [(200, _ok_body("ok"))])
    await client.send([ChatMessage(role="user", content="hi")])
    assert "system" not in calls[0]["json"]


async def test_send_rejects_empty_messages() -> None:
    client, _ = _make_client(["k1"], [])
    with pytest.raises(ValueError):
        await client.send([])


async def test_response_with_empty_text_raises() -> None:
    client, _ = _make_client(
        ["k1"],
        [
            (
                200,
                json.dumps(
                    {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "text", "text": ""}],
                    }
                ),
            )
        ],
    )
    with pytest.raises(ClaudeAPIError):
        await client.send([ChatMessage(role="user", content="hi")])


async def test_extract_text_concatenates_text_blocks() -> None:
    client, _ = _make_client(
        ["k1"],
        [
            (
                200,
                json.dumps(
                    {
                        "id": "m",
                        "content": [
                            {"type": "text", "text": "Hello, "},
                            {"type": "text", "text": "world!"},
                        ],
                    }
                ),
            )
        ],
    )
    reply = await client.send([ChatMessage(role="user", content="hi")])
    assert reply == "Hello, world!"
