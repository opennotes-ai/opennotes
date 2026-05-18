from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from src.x.api import (
    XApiAuthError,
    XApiNotFoundError,
    XApiRateLimitError,
    fetch_x_conversation,
)


def _root_response() -> dict[str, object]:
    return {
        "data": {
            "id": "100",
            "text": "Root post",
            "author_id": "1",
            "created_at": "2026-05-18T12:00:00Z",
            "conversation_id": "100",
        },
        "includes": {"users": [{"id": "1", "username": "alice", "name": "Alice"}]},
    }


def _search_response(*, next_token: str | None = None) -> dict[str, object]:
    meta: dict[str, object] = {"result_count": 1}
    if next_token is not None:
        meta["next_token"] = next_token
    return {
        "data": [
            {
                "id": "101",
                "text": "Reply one",
                "author_id": "2",
                "created_at": "2026-05-18T12:01:00Z",
                "referenced_tweets": [{"type": "replied_to", "id": "100"}],
            }
        ],
        "includes": {"users": [{"id": "2", "username": "bob", "name": "Bob"}]},
        "meta": meta,
    }


async def test_fetch_x_conversation_returns_root_and_replies() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token"
        if request.url.path == "/2/tweets/100":
            return httpx.Response(200, json=_root_response())
        if request.url.path == "/2/tweets/search/recent":
            assert request.url.params["query"] == "conversation_id:100"
            return httpx.Response(200, json=_search_response())
        raise AssertionError(f"unexpected request {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        conversation = await fetch_x_conversation("100", bearer="token", http=http)

    assert conversation.root.id == "100"
    assert conversation.root.author_handle == "alice"
    assert conversation.root.created_at == datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    assert len(conversation.replies) == 1
    assert conversation.replies[0].in_reply_to_status_id == "100"
    assert conversation.raw_count == 1
    assert conversation.truncated is False


async def test_fetch_x_conversation_follows_pagination_until_cap() -> None:
    search_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal search_calls
        if request.url.path == "/2/tweets/100":
            return httpx.Response(200, json=_root_response())
        search_calls += 1
        if search_calls == 1:
            return httpx.Response(200, json=_search_response(next_token="page-2"))
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "102",
                        "text": "Reply two",
                        "author_id": "2",
                        "created_at": "2026-05-18T12:02:00Z",
                    }
                ],
                "includes": {"users": [{"id": "2", "username": "bob", "name": "Bob"}]},
                "meta": {"result_count": 1},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        conversation = await fetch_x_conversation("100", bearer="token", http=http, max_replies=1)

    assert len(conversation.replies) == 1
    assert conversation.truncated is True
    assert search_calls == 1


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(401, XApiAuthError), (403, XApiAuthError), (404, XApiNotFoundError)],
)
async def test_fetch_x_conversation_raises_typed_root_errors(
    status_code: int,
    expected: type[Exception],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": "no"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(expected):
            await fetch_x_conversation("100", bearer="token", http=http)


async def test_fetch_x_conversation_raises_rate_limit_with_retry_after() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"x-rate-limit-reset": "1770000000"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(XApiRateLimitError) as exc_info:
            await fetch_x_conversation("100", bearer="token", http=http)

    assert exc_info.value.retry_after == 1770000000
