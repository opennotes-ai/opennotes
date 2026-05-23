from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from src.url_content_scan.x.api import (
    XApiAuthError,
    XApiNotFoundError,
    XApiRateLimitError,
    XConversation,
    fetch_x_conversation,
)

pytestmark = pytest.mark.unit

_ROOT_TWEET_ID = "1111111111"
_REPLY_TWEET_ID = "2222222222"
_AUTHOR_ID = "999"

_ROOT_PAYLOAD: dict[str, Any] = {
    "data": {
        "id": _ROOT_TWEET_ID,
        "text": "This is the root tweet",
        "author_id": _AUTHOR_ID,
        "created_at": "2026-05-01T10:00:00Z",
        "conversation_id": _ROOT_TWEET_ID,
        "referenced_tweets": [],
    },
    "includes": {
        "users": [
            {"id": _AUTHOR_ID, "username": "testuser", "name": "Test User"},
        ]
    },
}

_SEARCH_PAYLOAD_WITH_REPLY: dict[str, Any] = {
    "data": [
        {
            "id": _REPLY_TWEET_ID,
            "text": "This is a reply",
            "author_id": _AUTHOR_ID,
            "created_at": "2026-05-01T10:05:00Z",
            "conversation_id": _ROOT_TWEET_ID,
            "referenced_tweets": [{"type": "replied_to", "id": _ROOT_TWEET_ID}],
        }
    ],
    "includes": {
        "users": [
            {"id": _AUTHOR_ID, "username": "testuser", "name": "Test User"},
        ]
    },
    "meta": {},
}

_SEARCH_PAYLOAD_EMPTY: dict[str, Any] = {
    "meta": {},
}


def _make_http_client(responses: list[dict[str, Any]]) -> Any:
    call_index = {"i": 0}
    responses_list = list(responses)

    async def _mock_get(url: str, *, headers: Any = None, params: Any = None) -> httpx.Response:
        idx = call_index["i"]
        call_index["i"] += 1
        if idx >= len(responses_list):
            raise AssertionError(f"Unexpected request {idx} to {url}")
        payload = responses_list[idx]
        status = payload.pop("_status", 200)
        response_headers = payload.pop("_headers", {})
        request = httpx.Request("GET", url)
        return httpx.Response(status, json=payload, headers=response_headers, request=request)

    mock_client = MagicMock()
    mock_client.get = _mock_get
    return mock_client


@pytest.mark.asyncio
async def test_fetch_x_conversation_returns_root_and_replies() -> None:
    client = _make_http_client(
        [
            dict(_ROOT_PAYLOAD),
            dict(_SEARCH_PAYLOAD_WITH_REPLY),
            dict(_SEARCH_PAYLOAD_EMPTY),
        ]
    )
    result = await fetch_x_conversation(_ROOT_TWEET_ID, bearer="test-token", http=client)

    assert isinstance(result, XConversation)
    assert result.root.id == _ROOT_TWEET_ID
    assert result.root.author_handle == "testuser"
    assert result.root.text == "This is the root tweet"
    assert len(result.replies) == 1
    assert result.replies[0].id == _REPLY_TWEET_ID
    assert result.replies[0].in_reply_to_status_id == _ROOT_TWEET_ID
    assert result.truncated is False


@pytest.mark.asyncio
async def test_fetch_x_conversation_builds_bearer_auth_header() -> None:
    captured_headers: list[dict[str, Any]] = []

    async def _mock_get(url: str, *, headers: Any = None, params: Any = None) -> httpx.Response:
        captured_headers.append(dict(headers or {}))
        payload = dict(_ROOT_PAYLOAD) if "tweets/" in url else dict(_SEARCH_PAYLOAD_EMPTY)
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=payload, request=request)

    mock_client = MagicMock()
    mock_client.get = _mock_get

    await fetch_x_conversation(_ROOT_TWEET_ID, bearer="my-secret-token", http=mock_client)

    assert captured_headers[0]["Authorization"] == "Bearer my-secret-token"


@pytest.mark.asyncio
async def test_fetch_x_conversation_raises_auth_error_on_401() -> None:
    async def _mock_get(url: str, *, headers: Any = None, params: Any = None) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(401, json={}, request=request)

    mock_client = MagicMock()
    mock_client.get = _mock_get

    with pytest.raises(XApiAuthError):
        await fetch_x_conversation(_ROOT_TWEET_ID, bearer="bad-token", http=mock_client)


@pytest.mark.asyncio
async def test_fetch_x_conversation_raises_not_found_on_404() -> None:
    async def _mock_get(url: str, *, headers: Any = None, params: Any = None) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(404, json={}, request=request)

    mock_client = MagicMock()
    mock_client.get = _mock_get

    with pytest.raises(XApiNotFoundError):
        await fetch_x_conversation(_ROOT_TWEET_ID, bearer="token", http=mock_client)


@pytest.mark.asyncio
async def test_fetch_x_conversation_raises_rate_limit_on_429() -> None:
    async def _mock_get(url: str, *, headers: Any = None, params: Any = None) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(
            429,
            json={},
            headers={"x-rate-limit-reset": "1234567890"},
            request=request,
        )

    mock_client = MagicMock()
    mock_client.get = _mock_get

    with pytest.raises(XApiRateLimitError) as exc_info:
        await fetch_x_conversation(_ROOT_TWEET_ID, bearer="token", http=mock_client)

    assert exc_info.value.retry_after == 1234567890


@pytest.mark.asyncio
async def test_fetch_x_conversation_empty_replies_when_no_search_results() -> None:
    client = _make_http_client(
        [
            dict(_ROOT_PAYLOAD),
            dict(_SEARCH_PAYLOAD_EMPTY),
        ]
    )
    result = await fetch_x_conversation(_ROOT_TWEET_ID, bearer="token", http=client)

    assert result.root.id == _ROOT_TWEET_ID
    assert result.replies == []
    assert result.raw_count == 0
