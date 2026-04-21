import json
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from src.firecrawl_client import FIRECRAWL_API_BASE, FirecrawlClient
from src.utterances import (
    UtteranceExtractionError,
    UtterancesPayload,
    extract_utterances,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
EXTRACT_URL = f"{FIRECRAWL_API_BASE}/v2/extract"
BLOG_URL = "https://quizlet.com/blog/groups-are-now-classes/"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def client() -> FirecrawlClient:
    return FirecrawlClient(api_key="test-key")


async def test_extract_utterances_returns_blog_post_and_comments(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=EXTRACT_URL,
        method="POST",
        json=_load_fixture("quizlet_blog.json"),
    )

    payload = await extract_utterances(BLOG_URL, client)

    assert isinstance(payload, UtterancesPayload)
    assert payload.source_url == BLOG_URL
    assert payload.page_kind == "blog_post"
    assert payload.page_title == "Groups are now Classes"

    kinds = [u.kind for u in payload.utterances]
    assert "post" in kinds
    assert kinds.count("comment") >= 2
    assert "reply" in kinds

    post = next(u for u in payload.utterances if u.kind == "post")
    assert post.parent_id is None
    assert "Classes" in post.text

    reply = next(u for u in payload.utterances if u.kind == "reply")
    assert reply.parent_id is not None
    parent_ids = {u.utterance_id for u in payload.utterances}
    assert reply.parent_id in parent_ids


async def test_extract_utterances_raises_on_firecrawl_5xx(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=EXTRACT_URL,
        method="POST",
        status_code=500,
        json={"success": False, "error": "internal server error"},
        is_reusable=True,
    )

    with pytest.raises(UtteranceExtractionError):
        await extract_utterances(BLOG_URL, client)


async def test_extract_utterances_regenerates_duplicate_ids(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    response = {
        "success": True,
        "status": "completed",
        "data": {
            "source_url": BLOG_URL,
            "scraped_at": "2024-09-01T12:00:00Z",
            "page_title": "Dup test",
            "page_kind": "blog_post",
            "utterances": [
                {
                    "utterance_id": "dup",
                    "kind": "post",
                    "text": "original post",
                    "author": "a",
                    "timestamp": None,
                    "parent_id": None,
                },
                {
                    "utterance_id": "dup",
                    "kind": "comment",
                    "text": "first comment body",
                    "author": "b",
                    "timestamp": None,
                    "parent_id": "dup",
                },
                {
                    "utterance_id": None,
                    "kind": "comment",
                    "text": "second comment body",
                    "author": "c",
                    "timestamp": None,
                    "parent_id": "dup",
                },
                {
                    "utterance_id": "",
                    "kind": "reply",
                    "text": "a reply",
                    "author": "d",
                    "timestamp": None,
                    "parent_id": "dup",
                },
            ],
        },
    }
    httpx_mock.add_response(url=EXTRACT_URL, method="POST", json=response)

    payload = await extract_utterances(BLOG_URL, client)

    ids = [u.utterance_id for u in payload.utterances]
    assert len(ids) == len(set(ids)), f"ids should be unique: {ids}"
    for uid in ids:
        assert uid, "utterance_id should be non-empty"

    # Determinism: second call with identical response yields identical ids.
    httpx_mock.add_response(url=EXTRACT_URL, method="POST", json=response)
    payload2 = await extract_utterances(BLOG_URL, client)
    ids2 = [u.utterance_id for u in payload2.utterances]
    assert ids == ids2


async def test_extract_utterances_retries_on_429_then_succeeds(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(url=EXTRACT_URL, method="POST", status_code=429, json={"error": "rate limited"})
    httpx_mock.add_response(url=EXTRACT_URL, method="POST", json=_load_fixture("quizlet_blog.json"))

    payload = await extract_utterances(BLOG_URL, client)

    assert isinstance(payload, UtterancesPayload)
    assert len(payload.utterances) >= 3
    requests = httpx_mock.get_requests(url=EXTRACT_URL)
    assert len(requests) == 2
