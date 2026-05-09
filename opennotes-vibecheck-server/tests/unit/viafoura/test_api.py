"""Viafoura public comments API client tests."""

from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest
from pytest_httpx import HTTPXMock

from src.viafoura import (
    ViafouraFetchError,
    ViafouraSignal,
    ViafouraUnsupportedError,
    fetch_viafoura_comments,
)

STORY_URL = "https://apnews.com/article/redistricting-virginia-congress-democrats-republicans-12a31037f3c9a94d3cb9fbcaaf84d94f"
BOOTSTRAP_URL = "https://api.viafoura.co/v2/apnews.com/bootstrap/v2?session=false"
CONTAINER_URL = (
    "https://livecomments.viafoura.co/v4/livecomments/"
    "00000000-0000-4000-8000-3caf4df03307/contentcontainer/id"
    "?container_id=12a31037f3c9a94d3cb9fbcaaf84d94f"
)
COMMENTS_URL = (
    "https://livecomments.viafoura.co/v4/livecomments/"
    "00000000-0000-4000-8000-3caf4df03307/fe897d9b-8fcf-411a-b9d6-97325116ed98/comments"
    "?limit=5&reply_limit=2&sorted_by=newest"
)


def _signal() -> ViafouraSignal:
    return ViafouraSignal(
        container_id="12a31037f3c9a94d3cb9fbcaaf84d94f",
        site_domain=None,
        embed_origin="https://cdn.viafoura.net",
        iframe_src=None,
        has_conversations_component=True,
    )


def _bootstrap_payload() -> dict[str, object]:
    return {
        "result": {
            "settings": {"site_uuid": "00000000-0000-4000-8000-3caf4df03307"},
            "user": {"user_privilege": "guest"},
            "sectionTree": {"uuid": "00000000-0000-4000-8000-3caf4df03307"},
        }
    }


def _container_payload() -> dict[str, object]:
    return {
        "container_id": "12a31037f3c9a94d3cb9fbcaaf84d94f",
        "content_container_uuid": "fe897d9b-8fcf-411a-b9d6-97325116ed98",
        "total_visible_content": 1173,
        "settings": {"is_hidden": False},
    }


def _comments_payload() -> dict[str, object]:
    return {
        "more_available": True,
        "contents": [
            {
                "content_uuid": "6007f8a1-1c67-4be2-8336-27650bb5d4ff",
                "parent_uuid": "fe897d9b-8fcf-411a-b9d6-97325116ed98",
                "content": "So, they totally ignored what the people voted for.",
                "date_created": 1778282641870,
                "state": "visible",
                "actor": {"name": "apreader"},
                "total_likes": 1,
                "total_replies": 0,
            }
        ],
    }


async def test_fetch_viafoura_comments_fetches_and_renders_public_api(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(url=BOOTSTRAP_URL, method="POST", json=_bootstrap_payload())
    httpx_mock.add_response(url=CONTAINER_URL, method="GET", json=_container_payload())
    httpx_mock.add_response(url=COMMENTS_URL, method="GET", json=_comments_payload())

    async with httpx.AsyncClient() as client:
        result = await fetch_viafoura_comments(
            _signal(),
            STORY_URL,
            client=client,
            limit=5,
            reply_limit=2,
        )

    assert result.raw_count == 1
    assert result.more_available is True
    assert isinstance(result.fetched_at, datetime)
    assert "[6007f8a1-1c67-4be2-8336-27650bb5d4ff] author=apreader" in result.comments_markdown
    assert "So, they totally ignored what the people voted for." in result.comments_markdown
    assert result.comments_markdown.endswith("[comments truncated]")

    bootstrap_request = httpx_mock.get_requests(url=BOOTSTRAP_URL, method="POST")[0]
    assert json.loads(bootstrap_request.content) == {
        "section": "",
        "section_tree": "",
        "session": "false",
    }


async def test_fetch_viafoura_comments_raises_unsupported_for_missing_container(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(url=BOOTSTRAP_URL, method="POST", json=_bootstrap_payload())
    httpx_mock.add_response(url=CONTAINER_URL, method="GET", status_code=404)

    async with httpx.AsyncClient() as client:
        with pytest.raises(ViafouraUnsupportedError):
            await fetch_viafoura_comments(
                _signal(),
                STORY_URL,
                client=client,
                limit=5,
                reply_limit=2,
            )


async def test_fetch_viafoura_comments_rejects_private_story_url(
    httpx_mock: HTTPXMock,
) -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ViafouraUnsupportedError, match="unsafe story URL"):
            await fetch_viafoura_comments(
                _signal(),
                "http://127.0.0.1/story",
                client=client,
            )

    assert httpx_mock.get_requests() == []


async def test_fetch_viafoura_comments_retries_transport_errors(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_exception(
        exception=httpx.TimeoutException("timed out"),
        url=BOOTSTRAP_URL,
        method="POST",
    )
    httpx_mock.add_exception(
        exception=httpx.TimeoutException("timed out again"),
        url=BOOTSTRAP_URL,
        method="POST",
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(ViafouraFetchError):
            await fetch_viafoura_comments(
                _signal(),
                STORY_URL,
                client=client,
                max_attempts=2,
            )
