"""TDD coverage for Coral GraphQL comment extraction.

The new fetcher must be defensive and classify failures into retryable
vs terminal buckets so the caller can make the right retry/escalation choice.
"""
from __future__ import annotations

from datetime import datetime

import httpx
import pytest
from pytest_httpx import HTTPXMock

from src.coral.graphql import (
    CoralFetchError,
    CoralUnsupportedError,
    fetch_coral_comments,
)

CORAL_ORIGIN = "https://coral.example.com"
STORY_URL = "https://www.npr.org/2026/04/29/example"
GRAPHQL_URL = f"{CORAL_ORIGIN}/api/graphql"


async def test_fetch_coral_comments_renders_graphql_response(httpx_mock: HTTPXMock) -> None:
    """A realistic GraphQL envelope returns parsed nodes and markdown."""
    envelope = {
        "data": {
            "stream": {
                "comments": {
                    "edges": [
                        {
                            "node": {
                                "id": "comment-1",
                                "body": "<p>Great discussion!</p>",
                                "createdAt": "2026-04-29T10:00:00Z",
                                "author": {"username": "alice"},
                                "parent": None,
                            }
                        },
                        {
                            "node": {
                                "id": "comment-2",
                                "body": "<p>I agree.</p>",
                                "createdAt": "2026-04-29T10:05:00Z",
                                "author": {"username": "bob"},
                                "parent": {"id": "comment-1"},
                            }
                        },
                    ]
                }
            }
        }
    }

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
    envelope = {
        "data": {
            "stream": {
                "comments": {
                    "edges": [
                        {
                            "node": {
                                "id": "comment-1",
                                "body": "<p>Missing createdAt</p>",
                                "author": {"username": "alice"},
                                "parent": None,
                            }
                        }
                    ]
                }
            }
        }
    }
    httpx_mock.add_response(url=GRAPHQL_URL, method="POST", json=envelope)

    with pytest.raises(CoralUnsupportedError):
        await fetch_coral_comments(CORAL_ORIGIN, STORY_URL, timeout=10.0, max_attempts=2)
