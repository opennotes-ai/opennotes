from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from src.url_content_scan.coral.graphql import (
    CoralFetchError,
    CoralUnsupportedError,
    fetch_coral_comments,
)

pytestmark = pytest.mark.unit

CORAL_ORIGIN = "https://example.com"
STORY_URL = "https://www.npr.org/2026/04/29/example"
GRAPHQL_URL = f"{CORAL_ORIGIN}/api/graphql"


def _comment_edge(
    *,
    comment_id: str,
    body: str,
    created_at: str,
    author: str | None = "alice",
    parent_id: str | None = None,
) -> dict[str, Any]:
    return {
        "node": {
            "id": comment_id,
            "body": body,
            "createdAt": created_at,
            "author": {"username": author} if author is not None else None,
            "parent": {"id": parent_id} if parent_id is not None else None,
        }
    }


def _comments_envelope(
    edges: list[dict[str, Any]],
    *,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict[str, Any]:
    return {
        "data": {
            "stream": {
                "comments": {
                    "pageInfo": {"endCursor": end_cursor, "hasNextPage": has_next_page},
                    "edges": edges,
                }
            }
        }
    }


@dataclass
class _ResponseSpec:
    status_code: int = 200
    json_data: Any | None = None
    text: str | None = None
    exception: Exception | None = None

    def build(self, method: str, url: str, body: dict[str, Any] | None) -> httpx.Response:
        if self.exception is not None:
            raise self.exception
        request = httpx.Request(method, url, json=body)
        if self.json_data is not None:
            return httpx.Response(self.status_code, json=self.json_data, request=request)
        return httpx.Response(self.status_code, text=self.text or "", request=request)


@pytest.fixture
def graphql_http_stub():
    requests: list[dict[str, Any]] = []
    response_specs: list[_ResponseSpec] = []

    class _StubAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self) -> _StubAsyncClient:
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            json: dict[str, Any] | None = None,
        ) -> httpx.Response:
            requests.append({"url": url, "json": json})
            if not response_specs:
                raise AssertionError("No stubbed Coral GraphQL response left")
            return response_specs.pop(0).build("POST", url, json)

    def add_response(
        *,
        status_code: int = 200,
        json_data: Any | None = None,
        text: str | None = None,
        exception: Exception | None = None,
    ) -> None:
        response_specs.append(
            _ResponseSpec(
                status_code=status_code,
                json_data=json_data,
                text=text,
                exception=exception,
            )
        )

    with patch("src.url_content_scan.coral.graphql.httpx.AsyncClient", _StubAsyncClient):
        yield {"requests": requests, "add_response": add_response}


async def test_fetch_coral_comments_renders_graphql_response(
    graphql_http_stub: dict[str, Any],
) -> None:
    graphql_http_stub["add_response"](
        json_data=_comments_envelope(
            [
                _comment_edge(
                    comment_id="comment-1",
                    body="<p>Great discussion!</p>",
                    created_at="2026-04-29T10:00:00Z",
                    author="alice",
                ),
                _comment_edge(
                    comment_id="comment-2",
                    body="<p>I agree.</p>",
                    created_at="2026-04-29T10:05:00Z",
                    author="bob",
                    parent_id="comment-1",
                ),
            ]
        )
    )

    result = await fetch_coral_comments(CORAL_ORIGIN, STORY_URL, timeout=10.0, max_attempts=2)

    assert result.raw_count == 2
    assert isinstance(result.fetched_at, datetime)
    assert "[comment-1] author=alice" in result.comments_markdown
    assert "[comment-2] author=bob" in result.comments_markdown
    assert "Great discussion!" in result.comments_markdown
    assert "I agree." in result.comments_markdown


async def test_fetch_coral_comments_paginates_until_final_page(
    graphql_http_stub: dict[str, Any],
) -> None:
    graphql_http_stub["add_response"](
        json_data=_comments_envelope(
            [
                _comment_edge(
                    comment_id="comment-1",
                    body="<p>First page comment.</p>",
                    created_at="2026-04-29T10:00:00Z",
                    author="alice",
                )
            ],
            has_next_page=True,
            end_cursor="cursor-1",
        )
    )
    graphql_http_stub["add_response"](
        json_data=_comments_envelope(
            [
                _comment_edge(
                    comment_id="comment-2",
                    body="<p>Second page comment.</p>",
                    created_at="2026-04-29T10:05:00Z",
                    author="bob",
                )
            ]
        )
    )

    result = await fetch_coral_comments(
        CORAL_ORIGIN, STORY_URL, timeout=10.0, max_attempts=2, page_size=1
    )

    assert result.raw_count == 2
    assert "Second page comment." in result.comments_markdown

    requests = graphql_http_stub["requests"]
    assert len(requests) == 2
    first_payload = requests[0]["json"]
    second_payload = requests[1]["json"]
    assert "pageInfo" in first_payload["query"]
    assert first_payload["variables"]["first"] == 1
    assert first_payload["variables"]["after"] is None
    assert second_payload["variables"]["after"] == "cursor-1"


async def test_fetch_coral_comments_marks_truncated_when_comment_cap_reached(
    graphql_http_stub: dict[str, Any],
) -> None:
    graphql_http_stub["add_response"](
        json_data=_comments_envelope(
            [
                _comment_edge(
                    comment_id="comment-1",
                    body="<p>First capped comment.</p>",
                    created_at="2026-04-29T10:00:00Z",
                    author="alice",
                )
            ],
            has_next_page=True,
            end_cursor="cursor-1",
        )
    )
    graphql_http_stub["add_response"](
        json_data=_comments_envelope(
            [
                _comment_edge(
                    comment_id="comment-2",
                    body="<p>Second capped comment.</p>",
                    created_at="2026-04-29T10:05:00Z",
                    author="bob",
                )
            ],
            has_next_page=True,
            end_cursor="cursor-2",
        )
    )

    result = await fetch_coral_comments(
        CORAL_ORIGIN,
        STORY_URL,
        timeout=10.0,
        max_attempts=2,
        page_size=1,
        max_comments=2,
    )

    assert result.raw_count == 2
    assert "[comments truncated]" in result.comments_markdown


async def test_fetch_coral_comments_retries_timeout_as_fetch_error(
    graphql_http_stub: dict[str, Any],
) -> None:
    graphql_http_stub["add_response"](exception=httpx.TimeoutException("timed out"))
    graphql_http_stub["add_response"](exception=httpx.TimeoutException("timed out again"))

    with pytest.raises(CoralFetchError):
        await fetch_coral_comments(CORAL_ORIGIN, STORY_URL, timeout=0.1, max_attempts=2)

    assert len(graphql_http_stub["requests"]) == 2


async def test_fetch_coral_comments_raises_unsupported_on_4xx(
    graphql_http_stub: dict[str, Any],
) -> None:
    graphql_http_stub["add_response"](status_code=403, json_data={"error": "forbidden"})

    with pytest.raises(CoralUnsupportedError):
        await fetch_coral_comments(CORAL_ORIGIN, STORY_URL, timeout=10.0, max_attempts=2)


async def test_fetch_coral_comments_schema_mismatch_is_unsupported(
    graphql_http_stub: dict[str, Any],
) -> None:
    graphql_http_stub["add_response"](
        json_data=_comments_envelope(
            [{"node": {"id": "comment-1", "body": "<p>Missing createdAt</p>", "author": None}}]
        )
    )

    with pytest.raises(CoralUnsupportedError):
        await fetch_coral_comments(CORAL_ORIGIN, STORY_URL, timeout=10.0, max_attempts=2)


async def test_fetch_coral_comments_rejects_unsafe_endpoint() -> None:
    with pytest.raises(CoralUnsupportedError):
        await fetch_coral_comments("http://127.0.0.1:8080", STORY_URL)
