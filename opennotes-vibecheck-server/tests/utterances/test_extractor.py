from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from src.analyses.schemas import PageKind
from src.config import Settings
from src.firecrawl_client import FIRECRAWL_API_BASE, FirecrawlClient
from src.utterances import (
    UtteranceExtractionError,
    UtterancesPayload,
    extract_utterances,
)
from src.utterances.schema import Utterance

SCRAPE_URL = f"{FIRECRAWL_API_BASE}/v2/scrape"
BLOG_URL = "https://quizlet.com/blog/groups-are-now-classes/"


@pytest.fixture
def client() -> FirecrawlClient:
    return FirecrawlClient(api_key="test-key")


@pytest.fixture
def settings() -> Settings:
    return Settings()


class _FakeRunResult:
    def __init__(self, output: UtterancesPayload) -> None:
        self.output = output


class _FakeAgent:
    def __init__(self, payload: UtterancesPayload) -> None:
        self._payload = payload
        self.calls: list[str] = []

    async def run(self, user_prompt: str) -> _FakeRunResult:
        self.calls.append(user_prompt)
        return _FakeRunResult(self._payload)


def _stub_agent(monkeypatch: pytest.MonkeyPatch, payload: UtterancesPayload) -> _FakeAgent:
    fake = _FakeAgent(payload)
    monkeypatch.setattr(
        "src.utterances.extractor.build_agent",
        lambda settings, output_type=None, system_prompt=None: fake,
    )
    return fake


def _scrape_envelope(markdown: str) -> dict[str, Any]:
    return {"success": True, "data": {"markdown": markdown}}


def _sample_payload() -> UtterancesPayload:
    return UtterancesPayload(
        source_url="",
        scraped_at=datetime(2024, 9, 1, 12, 0, tzinfo=UTC),
        page_title="Groups are now Classes",
        page_kind=PageKind.BLOG_POST,
        utterances=[
            Utterance(utterance_id=None, kind="post", text="Post body with Classes."),
            Utterance(utterance_id=None, kind="comment", text="first comment", author="a"),
            Utterance(utterance_id=None, kind="comment", text="second comment", author="b"),
            Utterance(utterance_id=None, kind="reply", text="a reply", author="c", parent_id=None),
        ],
    )


async def test_extract_utterances_returns_post_and_comments(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=_scrape_envelope("# Title\nbody\n### Comments\n[alice]..."))
    fake = _stub_agent(monkeypatch, _sample_payload())

    payload = await extract_utterances(BLOG_URL, client, settings=settings)

    assert isinstance(payload, UtterancesPayload)
    assert payload.source_url == BLOG_URL
    assert payload.page_kind == "blog_post"
    assert payload.page_title == "Groups are now Classes"
    kinds = [u.kind for u in payload.utterances]
    assert "post" in kinds
    assert kinds.count("comment") == 2
    assert "reply" in kinds
    assert len(fake.calls) == 1
    assert "Classes" in fake.calls[0] or "Title" in fake.calls[0]


async def test_extract_utterances_raises_when_scrape_has_no_markdown(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
    settings: Settings,
) -> None:
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json={"success": True, "data": {}})
    with pytest.raises(UtteranceExtractionError, match="no markdown"):
        await extract_utterances(BLOG_URL, client, settings=settings)


async def test_extract_utterances_raises_on_scrape_5xx(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
    settings: Settings,
) -> None:
    httpx_mock.add_response(
        url=SCRAPE_URL, method="POST", status_code=500, json={"error": "boom"}, is_reusable=True
    )
    with pytest.raises(UtteranceExtractionError, match="firecrawl scrape failed"):
        await extract_utterances(BLOG_URL, client, settings=settings)


async def test_extract_utterances_regenerates_duplicate_ids(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    payload = UtterancesPayload(
        source_url="",
        scraped_at=datetime(2024, 9, 1, tzinfo=UTC),
        page_title="Dup",
        page_kind=PageKind.BLOG_POST,
        utterances=[
            Utterance(utterance_id="dup", kind="post", text="original post"),
            Utterance(utterance_id="dup", kind="comment", text="first", author="b"),
            Utterance(utterance_id=None, kind="comment", text="second", author="c"),
            Utterance(utterance_id="", kind="reply", text="reply!", author="d"),
        ],
    )
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=_scrape_envelope("hi"))
    _stub_agent(monkeypatch, payload.model_copy(deep=True))

    result = await extract_utterances(BLOG_URL, client, settings=settings)
    ids = [u.utterance_id for u in result.utterances]
    assert len(ids) == len(set(ids))
    assert all(uid for uid in ids)

    # Determinism: re-running with identical input yields identical ids.
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=_scrape_envelope("hi"))
    _stub_agent(monkeypatch, payload.model_copy(deep=True))
    result2 = await extract_utterances(BLOG_URL, client, settings=settings)
    ids2 = [u.utterance_id for u in result2.utterances]
    assert ids == ids2


async def test_extract_utterances_retries_scrape_on_429(
    client: FirecrawlClient,
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", status_code=429, json={"error": "rate limited"})
    httpx_mock.add_response(url=SCRAPE_URL, method="POST", json=_scrape_envelope("# body\n### Comments"))
    _stub_agent(monkeypatch, _sample_payload())

    payload = await extract_utterances(BLOG_URL, client, settings=settings)

    assert isinstance(payload, UtterancesPayload)
    requests = httpx_mock.get_requests(url=SCRAPE_URL)
    assert len(requests) == 2
