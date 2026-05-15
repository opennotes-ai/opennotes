"""Tests for extract_utterances_dispatched dispatcher."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.analyses.schemas import PageKind, UtteranceStreamType
from src.cache.scrape_cache import CachedScrape
from src.config import Settings
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.utterances.batched.dispatcher import extract_utterances_dispatched
from src.utterances.errors import ZeroUtterancesError
from src.utterances.schema import (
    BatchedUtteranceRedirectionResponse,
    Utterance,
    UtterancesPayload,
)

TARGET_URL = "https://example.com/page"

_SMALL_SCRAPE = CachedScrape(
    markdown="# Small\n\nShort content.",
    html="<html><body><p>Short content.</p></body></html>",
    raw_html=None,
    screenshot=None,
    links=[],
    metadata=ScrapeMetadata(source_url=TARGET_URL),
    warning=None,
    storage_key=None,
)

_REDIRECT = BatchedUtteranceRedirectionResponse(
    page_kind=PageKind.FORUM_THREAD,
    utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
    page_title="Big Forum",
    boundary_instructions="Split by comment headers.",
    section_hints=[],
)

_SINGLE_UTTERANCE_PAYLOAD = UtterancesPayload(
    source_url="",
    scraped_at=datetime(2020, 1, 1, tzinfo=UTC),
    page_title="Page",
    page_kind=PageKind.ARTICLE,
    utterances=[Utterance(utterance_id=None, kind="post", text="Hello world.")],
)


class _FakeFirecrawlClient:
    async def scrape(
        self, url: str, formats: list[str], *, only_main_content: bool = False
    ) -> ScrapeResult:
        return ScrapeResult(
            markdown=_SMALL_SCRAPE.markdown,
            html=_SMALL_SCRAPE.html,
            metadata=ScrapeMetadata(source_url=url),
        )


class _FakeScrapeCache:
    async def get(self, url: str, *, tier: str = "scrape") -> CachedScrape | None:
        return None

    async def put(self, url: str, scrape: ScrapeResult, *, tier: str = "scrape") -> CachedScrape:
        return _SMALL_SCRAPE

    async def signed_screenshot_url(self, scrape: Any) -> str | None:
        return None


@pytest.mark.asyncio
async def test_single_pass_payload_returned_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """When _extract_or_redirect returns UtterancesPayload, it is returned as-is.
    partition_html and run_all_sections must never be called."""
    partition_called = False
    runner_called = False

    def _fake_partition(*a: Any, **kw: Any) -> list[Any]:
        nonlocal partition_called
        partition_called = True
        return []

    async def _fake_run_all(*a: Any, **kw: Any) -> list[Any]:
        nonlocal runner_called
        runner_called = True
        return []

    monkeypatch.setattr(
        "src.utterances.batched.dispatcher._extract_or_redirect",
        AsyncMock(return_value=_SINGLE_UTTERANCE_PAYLOAD),
    )
    monkeypatch.setattr("src.utterances.batched.dispatcher._sanitize_html", lambda h: h)
    monkeypatch.setattr("src.utterances.batched.dispatcher.partition_html", _fake_partition)
    monkeypatch.setattr("src.utterances.batched.dispatcher.run_all_sections", _fake_run_all)

    settings = Settings()
    result = await extract_utterances_dispatched(
        TARGET_URL,
        _FakeFirecrawlClient(),
        _FakeScrapeCache(),
        settings=settings,
        scrape=_SMALL_SCRAPE,
    )

    assert result is _SINGLE_UTTERANCE_PAYLOAD
    assert not partition_called
    assert not runner_called


@pytest.mark.asyncio
async def test_batched_path_calls_pipeline_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """When _extract_or_redirect returns BatchedUtteranceRedirectionResponse,
    partition_html, run_all_sections, and assemble_sections are called in order.
    The same sanitized_html string is threaded into partition_html and assemble_sections."""
    call_order: list[str] = []
    sentinel_html = "SANITIZED_SENTINEL"
    seen_html_in_partition: list[str] = []
    seen_html_in_assemble: list[str] = []

    fake_section = object()
    fake_section_result = object()

    def _fake_sanitize(html: str) -> str:
        return sentinel_html

    def _fake_partition(sanitized_html: str, redirect: Any, settings: Any) -> list[Any]:
        call_order.append("partition")
        seen_html_in_partition.append(sanitized_html)
        return [fake_section]

    async def _fake_run_all(
        sections: Any, redirect: Any, *, settings: Any, scrape: Any, scrape_cache: Any
    ) -> list[Any]:
        call_order.append("runner")
        return [fake_section_result]

    async def _fake_assemble(
        section_results: Any, redirect: Any, sanitized_html: str, source_url: str
    ) -> UtterancesPayload:
        call_order.append("assemble")
        seen_html_in_assemble.append(sanitized_html)
        return UtterancesPayload(
            source_url=source_url,
            scraped_at=datetime(2020, 1, 1, tzinfo=UTC),
            page_title="Merged",
            page_kind=PageKind.FORUM_THREAD,
            utterances=[Utterance(utterance_id=None, kind="reply", text="Reply 1.")],
        )

    monkeypatch.setattr(
        "src.utterances.batched.dispatcher._extract_or_redirect",
        AsyncMock(return_value=_REDIRECT),
    )
    monkeypatch.setattr("src.utterances.batched.dispatcher._sanitize_html", _fake_sanitize)
    monkeypatch.setattr("src.utterances.batched.dispatcher.partition_html", _fake_partition)
    monkeypatch.setattr("src.utterances.batched.dispatcher.run_all_sections", _fake_run_all)
    monkeypatch.setattr("src.utterances.batched.dispatcher.assemble_sections", _fake_assemble)

    settings = Settings()
    result = await extract_utterances_dispatched(
        TARGET_URL,
        _FakeFirecrawlClient(),
        _FakeScrapeCache(),
        settings=settings,
        scrape=_SMALL_SCRAPE,
    )

    assert call_order == ["partition", "runner", "assemble"]
    assert seen_html_in_partition[0] == sentinel_html
    assert seen_html_in_assemble[0] == sentinel_html
    assert result.source_url == TARGET_URL


@pytest.mark.asyncio
async def test_sanitization_uses_asyncio_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """sanitized_html is computed via asyncio.to_thread, not called synchronously.
    Verify by patching asyncio.to_thread and confirming _sanitize_html is only
    called through it, not directly."""
    sanitize_calls_via_thread: list[str] = []
    original_to_thread = asyncio.to_thread

    async def _fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
        if func.__name__ == "_sanitize_html":
            sanitize_calls_via_thread.append("called")
        return await original_to_thread(func, *args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", _fake_to_thread)
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher._extract_or_redirect",
        AsyncMock(return_value=_SINGLE_UTTERANCE_PAYLOAD),
    )

    settings = Settings()
    await extract_utterances_dispatched(
        TARGET_URL,
        _FakeFirecrawlClient(),
        _FakeScrapeCache(),
        settings=settings,
        scrape=_SMALL_SCRAPE,
    )

    assert len(sanitize_calls_via_thread) >= 1, (
        "_sanitize_html must be called via asyncio.to_thread, not synchronously"
    )


@pytest.mark.asyncio
async def test_zero_utterances_after_assembly_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If assemble_sections returns a payload with zero utterances, ZeroUtterancesError is raised."""
    empty_payload = UtterancesPayload(
        source_url=TARGET_URL,
        scraped_at=datetime(2020, 1, 1, tzinfo=UTC),
        page_title="Empty",
        page_kind=PageKind.OTHER,
        utterances=[],
    )

    monkeypatch.setattr(
        "src.utterances.batched.dispatcher._extract_or_redirect",
        AsyncMock(return_value=_REDIRECT),
    )
    monkeypatch.setattr("src.utterances.batched.dispatcher._sanitize_html", lambda h: h)
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher.partition_html", lambda *a, **kw: [object()]
    )
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher.run_all_sections", AsyncMock(return_value=[object()])
    )
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher.assemble_sections", AsyncMock(return_value=empty_payload)
    )

    settings = Settings()
    with pytest.raises(ZeroUtterancesError):
        await extract_utterances_dispatched(
            TARGET_URL,
            _FakeFirecrawlClient(),
            _FakeScrapeCache(),
            settings=settings,
            scrape=_SMALL_SCRAPE,
        )


@pytest.mark.asyncio
async def test_zero_utterances_from_section_runner_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher._extract_or_redirect",
        AsyncMock(return_value=_REDIRECT),
    )
    monkeypatch.setattr("src.utterances.batched.dispatcher._sanitize_html", lambda h: h)
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher.partition_html", lambda *a, **kw: [object(), object()]
    )
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher.run_all_sections",
        AsyncMock(side_effect=ZeroUtterancesError("section 1 produced zero utterances")),
    )

    settings = Settings()
    with pytest.raises(ZeroUtterancesError):
        await extract_utterances_dispatched(
            TARGET_URL,
            _FakeFirecrawlClient(),
            _FakeScrapeCache(),
            settings=settings,
            scrape=_SMALL_SCRAPE,
        )


@pytest.mark.asyncio
async def test_section_count_span_attr_set_on_batched_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """section_count logfire span attr is set on the batched path with the correct value."""
    fake_sections = [object(), object(), object()]
    captured_attrs: dict[str, Any] = {}

    class _FakeSpan:
        def __enter__(self) -> _FakeSpan:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def set_attribute(self, key: str, value: Any) -> None:
            captured_attrs[key] = value

    monkeypatch.setattr("logfire.span", lambda name, **kwargs: _FakeSpan())
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher._extract_or_redirect",
        AsyncMock(return_value=_REDIRECT),
    )
    monkeypatch.setattr("src.utterances.batched.dispatcher._sanitize_html", lambda h: h)
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher.partition_html", lambda *a, **kw: fake_sections
    )
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher.run_all_sections", AsyncMock(return_value=[object()])
    )
    monkeypatch.setattr(
        "src.utterances.batched.dispatcher.assemble_sections",
        AsyncMock(
            return_value=UtterancesPayload(
                source_url=TARGET_URL,
                scraped_at=datetime(2020, 1, 1, tzinfo=UTC),
                page_title="Ok",
                page_kind=PageKind.ARTICLE,
                utterances=[Utterance(utterance_id=None, kind="post", text="text")],
            )
        ),
    )

    settings = Settings()
    await extract_utterances_dispatched(
        TARGET_URL,
        _FakeFirecrawlClient(),
        _FakeScrapeCache(),
        settings=settings,
        scrape=_SMALL_SCRAPE,
    )

    assert captured_attrs.get("section_count") == 3


@pytest.mark.asyncio
async def test_under_threshold_sanitizes_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """On under-threshold pages, _sanitize_html must be called exactly once.
    The pre-computed sanitized_html from the dispatcher is passed through to
    extract_utterances via _extract_or_redirect so it skips internal sanitization."""
    from src.utterances.extractor import _extract_or_redirect

    extract_utterances_calls: list[dict] = []

    async def _fake_extract_utterances(
        url, client, scrape_cache, *, settings=None, scrape=None, sanitized_html=None
    ):
        extract_utterances_calls.append({"sanitized_html": sanitized_html})
        return _SINGLE_UTTERANCE_PAYLOAD

    monkeypatch.setattr(
        "src.utterances.extractor.extract_utterances",
        _fake_extract_utterances,
    )

    settings = Settings()
    settings.VIBECHECK_BATCH_HTML_BYTES = 10_000_000
    settings.VIBECHECK_BATCH_MARKDOWN_BYTES = 10_000_000

    pre_sanitized = "already-sanitized-html"
    result = await _extract_or_redirect(
        TARGET_URL,
        _FakeFirecrawlClient(),
        _FakeScrapeCache(),
        settings=settings,
        scrape=_SMALL_SCRAPE,
        sanitized_html=pre_sanitized,
    )

    assert len(extract_utterances_calls) == 1
    assert extract_utterances_calls[0]["sanitized_html"] == pre_sanitized, (
        "extract_utterances must receive the pre-computed sanitized_html to avoid double-sanitize"
    )
    assert result is _SINGLE_UTTERANCE_PAYLOAD
