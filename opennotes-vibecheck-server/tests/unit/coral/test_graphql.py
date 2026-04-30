"""TDD coverage for Coral GraphQL comment extraction.

The new fetcher must be defensive and classify failures into retryable
vs terminal buckets so the caller can make the right retry/escalation choice.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock

from src.coral.graphql import (
    CoralFetchError,
    CoralUnsupportedError,
    fetch_coral_comments,
)

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
                    "pageInfo": {
                        "endCursor": end_cursor,
                        "hasNextPage": has_next_page,
                    },
                    "edges": edges,
                }
            }
        }
    }


async def test_fetch_coral_comments_renders_graphql_response(httpx_mock: HTTPXMock) -> None:
    """A realistic GraphQL envelope returns parsed nodes and markdown."""
    envelope = _comments_envelope(
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

    httpx_mock.add_response(url=GRAPHQL_URL, method="POST", json=envelope)

    result = await fetch_coral_comments(CORAL_ORIGIN, STORY_URL, timeout=10.0, max_attempts=2)

    assert result.raw_count == 2
    assert isinstance(result.fetched_at, datetime)
    assert "[comment-1] author=alice" in result.comments_markdown
    assert "[comment-2] author=bob" in result.comments_markdown
    assert "parent=null" in result.comments_markdown
    assert "parent=comment-1" in result.comments_markdown
    assert "Great discussion!" in result.comments_markdown
    assert "I agree." in result.comments_markdown


async def test_fetch_coral_comments_paginates_until_final_page(
    httpx_mock: HTTPXMock,
) -> None:
    """Relay pageInfo is followed so comments after the first page render."""
    first_page = _comments_envelope(
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
    second_page = _comments_envelope(
        [
            _comment_edge(
                comment_id="comment-2",
                body="<p>Second page comment.</p>",
                created_at="2026-04-29T10:05:00Z",
                author="bob",
            )
        ],
        has_next_page=False,
    )
    httpx_mock.add_response(url=GRAPHQL_URL, method="POST", json=first_page)
    httpx_mock.add_response(url=GRAPHQL_URL, method="POST", json=second_page)

    result = await fetch_coral_comments(
        CORAL_ORIGIN,
        STORY_URL,
        timeout=10.0,
        max_attempts=2,
        page_size=1,
    )

    assert result.raw_count == 2
    assert "First page comment." in result.comments_markdown
    assert "Second page comment." in result.comments_markdown
    assert result.comments_markdown.index("comment-1") < result.comments_markdown.index(
        "comment-2"
    )

    requests = httpx_mock.get_requests(url=GRAPHQL_URL, method="POST")
    assert len(requests) == 2
    first_payload = json.loads(requests[0].content)
    second_payload = json.loads(requests[1].content)
    assert "pageInfo" in first_payload["query"]
    assert first_payload["variables"]["first"] == 1
    assert first_payload["variables"]["after"] is None
    assert second_payload["variables"]["after"] == "cursor-1"


async def test_fetch_coral_comments_marks_truncated_when_comment_cap_reached(
    httpx_mock: HTTPXMock,
) -> None:
    """A capped Coral stream returns partial markdown with an explicit marker."""
    first_page = _comments_envelope(
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
    second_page = _comments_envelope(
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
    httpx_mock.add_response(url=GRAPHQL_URL, method="POST", json=first_page)
    httpx_mock.add_response(url=GRAPHQL_URL, method="POST", json=second_page)

    result = await fetch_coral_comments(
        CORAL_ORIGIN,
        STORY_URL,
        timeout=10.0,
        max_attempts=2,
        page_size=1,
        max_comments=2,
    )

    assert result.raw_count == 2
    assert "First capped comment." in result.comments_markdown
    assert "Second capped comment." in result.comments_markdown
    assert "[comments truncated]" in result.comments_markdown
    assert len(httpx_mock.get_requests(url=GRAPHQL_URL, method="POST")) == 2


async def test_fetch_coral_comments_retries_timeout_as_fetch_error(
    httpx_mock: HTTPXMock,
) -> None:
    """Transient timeouts are retried up to `max_attempts`, then terminal.

    This test asserts retry count via public HTTP request behavior, not private
    internals.
    """
    httpx_mock.add_exception(
        exception=httpx.TimeoutException("timed out"),
        url=GRAPHQL_URL,
        method="POST",
    )
    httpx_mock.add_exception(
        exception=httpx.TimeoutException("timed out again"),
        url=GRAPHQL_URL,
        method="POST",
    )

    with pytest.raises(CoralFetchError):
        await fetch_coral_comments(CORAL_ORIGIN, STORY_URL, timeout=0.1, max_attempts=2)

    requests = httpx_mock.get_requests(url=GRAPHQL_URL, method="POST")
    assert len(requests) == 2


async def test_fetch_coral_comments_raises_unsupported_on_4xx(httpx_mock: HTTPXMock) -> None:
    """4xx responses are terminal and should be classified as unsupported."""
    httpx_mock.add_response(
        url=GRAPHQL_URL,
        method="POST",
        status_code=403,
        json={"error": "forbidden"},
    )

    with pytest.raises(CoralUnsupportedError):
        await fetch_coral_comments(CORAL_ORIGIN, STORY_URL, timeout=10.0, max_attempts=2)


async def test_fetch_coral_comments_schema_mismatch_is_unsupported(httpx_mock: HTTPXMock) -> None:
    """Schema mismatch (missing required node fields) is terminal and non-retryable."""
    envelope = _comments_envelope(
        [
            {
                "node": {
                    "id": "comment-1",
                    "body": "<p>Missing createdAt</p>",
                    "author": {"username": "alice"},
                    "parent": None,
                }
            }
        ]
    )
    httpx_mock.add_response(url=GRAPHQL_URL, method="POST", json=envelope)

    with pytest.raises(CoralUnsupportedError):
        await fetch_coral_comments(CORAL_ORIGIN, STORY_URL, timeout=10.0, max_attempts=2)


async def test_fetch_coral_comments_rejects_private_graphql_origin(
    httpx_mock: HTTPXMock,
) -> None:
    """Coral origins parsed from page HTML are untrusted and must not SSRF."""
    with pytest.raises(CoralUnsupportedError, match="unsafe endpoint"):
        await fetch_coral_comments(
            "http://127.0.0.1:8080",
            STORY_URL,
            timeout=10.0,
            max_attempts=2,
        )

    assert httpx_mock.get_requests() == []
