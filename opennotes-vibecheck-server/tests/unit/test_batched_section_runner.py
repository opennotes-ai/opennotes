"""Unit tests for src/utterances/batched/section_runner.py (TASK-1649.05).

Covers:
- AC1: parent page_kind / utterance_stream_type / page_title are forced onto
  every returned payload regardless of what the agent returned.
- AC2: run_all_sections bounds concurrency to VIBECHECK_BATCH_PARALLEL.
- AC3: ZeroUtterancesError for content-bearing sections aborts the batch.
- AC4: TransientExtractionError propagates and aborts run_all_sections.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.analyses.schemas import PageKind, UtteranceStreamType
from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings
from src.firecrawl_client import ScrapeMetadata
from src.utterances.batched.assembler import SectionResult
from src.utterances.batched.partition import HtmlSection
from src.utterances.batched.section_runner import run_all_sections, run_section
from src.utterances.errors import TransientExtractionError, ZeroUtterancesError
from src.utterances.schema import BatchedUtteranceRedirectionResponse, Utterance, UtterancesPayload


def _make_section(index: int = 0) -> HtmlSection:
    return HtmlSection(
        index=index,
        html_slice=f"<p>section {index}</p>",
        global_start=index * 100,
        global_end=index * 100 + 50,
        overlap_with_prev_bytes=0,
        parent_context_text=None,
    )


def _make_parent(
    page_kind: PageKind = PageKind.FORUM_THREAD,
    utterance_stream_type: UtteranceStreamType = UtteranceStreamType.COMMENT_SECTION,
    page_title: str | None = "Parent Title",
) -> BatchedUtteranceRedirectionResponse:
    return BatchedUtteranceRedirectionResponse(
        page_kind=page_kind,
        utterance_stream_type=utterance_stream_type,
        page_title=page_title,
        boundary_instructions="Extract each post separately.",
    )


def _make_payload(
    page_kind: PageKind = PageKind.ARTICLE,
    utterance_stream_type: UtteranceStreamType = UtteranceStreamType.ARTICLE_OR_MONOLOGUE,
    page_title: str | None = "agent guess",
    utterances: list[Utterance] | None = None,
) -> UtterancesPayload:
    if utterances is None:
        utterances = [Utterance(kind="post", text="Hello world", utterance_id="u1")]
    return UtterancesPayload(
        source_url="https://example.com/",
        scraped_at=datetime.now(UTC),
        utterances=utterances,
        page_kind=page_kind,
        utterance_stream_type=utterance_stream_type,
        page_title=page_title,
    )


@dataclass
class _FakeRunResult:
    output: UtterancesPayload


@pytest.fixture
def settings() -> Settings:
    return Settings(VIBECHECK_BATCH_PARALLEL=2)


@pytest.fixture
def mock_scrape() -> MagicMock:
    scrape = MagicMock(spec=CachedScrape)
    scrape.metadata = ScrapeMetadata(source_url="https://example.com/")
    return scrape


@pytest.fixture
def mock_scrape_cache() -> MagicMock:
    return MagicMock(spec=SupabaseScrapeCache)


def _patch_vertex_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _noop_slot(_settings: Any) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr(
        "src.utterances.batched.section_runner.vertex_slot",
        _noop_slot,
    )


def _patch_build_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeAgent:
        def tool(self, func: Any = None, /, **_kwargs: Any) -> Any:
            if func is None:

                def _wrap(f: Any) -> Any:
                    return f

                return _wrap
            return func

    monkeypatch.setattr(
        "src.utterances.batched.section_runner.build_agent",
        lambda *_args, **_kwargs: _FakeAgent(),
    )


@pytest.mark.asyncio
async def test_run_section_forces_parent_meta(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    mock_scrape: MagicMock,
    mock_scrape_cache: MagicMock,
) -> None:
    """AC1: parent page_kind/utterance_stream_type/page_title overwrite agent output."""
    agent_payload = _make_payload(
        page_kind=PageKind.ARTICLE,
        utterance_stream_type=UtteranceStreamType.ARTICLE_OR_MONOLOGUE,
        page_title="agent guess",
    )

    async def _fake_run(agent: Any, prompt: Any, *, deps: Any = None) -> _FakeRunResult:
        return _FakeRunResult(output=agent_payload)

    _patch_vertex_slot(monkeypatch)
    _patch_build_agent(monkeypatch)
    monkeypatch.setattr(
        "src.utterances.batched.section_runner.run_vertex_agent_with_retry",
        _fake_run,
    )

    parent = _make_parent(
        page_kind=PageKind.FORUM_THREAD,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
        page_title="Parent Title",
    )
    section = _make_section(index=0)

    result = await run_section(
        section,
        parent,
        settings=settings,
        scrape=mock_scrape,
        scrape_cache=mock_scrape_cache,
    )

    assert isinstance(result, SectionResult)
    assert result.payload.page_kind == PageKind.FORUM_THREAD
    assert result.payload.utterance_stream_type == UtteranceStreamType.COMMENT_SECTION
    assert result.payload.page_title == "Parent Title"
    assert result.per_section_page_kind_guess == PageKind.ARTICLE


@pytest.mark.asyncio
async def test_run_section_prompt_includes_parent_context(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    mock_scrape: MagicMock,
    mock_scrape_cache: MagicMock,
) -> None:
    captured_prompt = ""

    async def _fake_run(agent: Any, prompt: str, *, deps: Any = None) -> _FakeRunResult:
        nonlocal captured_prompt
        captured_prompt = prompt
        return _FakeRunResult(output=_make_payload())

    _patch_vertex_slot(monkeypatch)
    _patch_build_agent(monkeypatch)
    monkeypatch.setattr(
        "src.utterances.batched.section_runner.run_vertex_agent_with_retry",
        _fake_run,
    )

    parent = _make_parent(
        page_kind=PageKind.FORUM_THREAD,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
        page_title="Parent Title",
    )
    section = _make_section(index=0)

    await run_section(
        section,
        parent,
        settings=settings,
        scrape=mock_scrape,
        scrape_cache=mock_scrape_cache,
    )

    assert "Page kind context from parent pass: forum_thread" in captured_prompt
    assert "Utterance stream type from parent pass: comment_section" in captured_prompt
    assert "Page title from parent pass: Parent Title" in captured_prompt


@pytest.mark.asyncio
async def test_run_all_sections_respects_semaphore(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    mock_scrape: MagicMock,
    mock_scrape_cache: MagicMock,
) -> None:
    """AC2: run_all_sections limits concurrent sections to VIBECHECK_BATCH_PARALLEL=2."""
    counter = 0
    max_concurrent = 0
    gate = asyncio.Event()
    entered = 0
    num_sections = 4

    async def _counting_run(agent: Any, prompt: Any, *, deps: Any = None) -> _FakeRunResult:
        nonlocal counter, max_concurrent, entered

        counter += 1
        max_concurrent = max(max_concurrent, counter)

        entered += 1
        if entered == settings.VIBECHECK_BATCH_PARALLEL:
            gate.set()

        await asyncio.sleep(0)

        counter -= 1
        return _FakeRunResult(
            output=_make_payload(
                page_kind=PageKind.FORUM_THREAD,
                utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
            )
        )

    _patch_vertex_slot(monkeypatch)
    _patch_build_agent(monkeypatch)
    monkeypatch.setattr(
        "src.utterances.batched.section_runner.run_vertex_agent_with_retry",
        _counting_run,
    )

    parent = _make_parent()
    sections = [_make_section(i) for i in range(num_sections)]

    results = await run_all_sections(
        sections,
        parent,
        settings=settings,
        scrape=mock_scrape,
        scrape_cache=mock_scrape_cache,
    )

    assert len(results) == num_sections
    assert max_concurrent <= settings.VIBECHECK_BATCH_PARALLEL


@pytest.mark.asyncio
async def test_zero_utterances_error_from_content_section_raises(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    mock_scrape: MagicMock,
    mock_scrape_cache: MagicMock,
) -> None:
    """AC3: ZeroUtterancesError from a content section propagates for retry/escalation."""

    async def _raising_run(agent: Any, prompt: Any, *, deps: Any = None) -> Any:
        raise ZeroUtterancesError("no utterances found")

    _patch_vertex_slot(monkeypatch)
    _patch_build_agent(monkeypatch)
    monkeypatch.setattr(
        "src.utterances.batched.section_runner.run_vertex_agent_with_retry",
        _raising_run,
    )

    parent = _make_parent(
        page_kind=PageKind.FORUM_THREAD,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
    )
    section = _make_section(index=0)

    with pytest.raises(ZeroUtterancesError):
        await run_section(
            section,
            parent,
            settings=settings,
            scrape=mock_scrape,
            scrape_cache=mock_scrape_cache,
        )


@pytest.mark.asyncio
async def test_empty_html_section_can_yield_empty_result(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    mock_scrape: MagicMock,
    mock_scrape_cache: MagicMock,
) -> None:
    async def _raising_run(agent: Any, prompt: Any, *, deps: Any = None) -> Any:
        raise ZeroUtterancesError("no utterances found")

    _patch_vertex_slot(monkeypatch)
    _patch_build_agent(monkeypatch)
    monkeypatch.setattr(
        "src.utterances.batched.section_runner.run_vertex_agent_with_retry",
        _raising_run,
    )

    parent = _make_parent()
    section = HtmlSection(
        index=0,
        html_slice="<div>   </div>",
        global_start=0,
        global_end=13,
        overlap_with_prev_bytes=0,
        parent_context_text=None,
    )

    result = await run_section(
        section,
        parent,
        settings=settings,
        scrape=mock_scrape,
        scrape_cache=mock_scrape_cache,
    )

    assert result.payload.utterances == []
    assert result.per_section_page_kind_guess is None


@pytest.mark.asyncio
async def test_overlap_only_section_can_yield_empty_result(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    mock_scrape: MagicMock,
    mock_scrape_cache: MagicMock,
) -> None:
    async def _raising_run(agent: Any, prompt: Any, *, deps: Any = None) -> Any:
        raise ZeroUtterancesError("no utterances found")

    _patch_vertex_slot(monkeypatch)
    _patch_build_agent(monkeypatch)
    monkeypatch.setattr(
        "src.utterances.batched.section_runner.run_vertex_agent_with_retry",
        _raising_run,
    )

    parent = _make_parent()
    html_slice = "<p>already covered by the previous section</p>"
    section = HtmlSection(
        index=1,
        html_slice=html_slice,
        global_start=0,
        global_end=len(html_slice),
        overlap_with_prev_bytes=len(html_slice.encode("utf-8")),
        parent_context_text=None,
    )

    result = await run_section(
        section,
        parent,
        settings=settings,
        scrape=mock_scrape,
        scrape_cache=mock_scrape_cache,
    )

    assert result.payload.utterances == []
    assert result.per_section_page_kind_guess is None


@pytest.mark.asyncio
async def test_run_all_sections_aborts_when_middle_content_section_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    mock_scrape: MagicMock,
    mock_scrape_cache: MagicMock,
) -> None:
    call_count = 0

    async def _mixed_run(agent: Any, prompt: Any, *, deps: Any = None) -> _FakeRunResult:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return _FakeRunResult(output=_make_payload(utterances=[]))
        return _FakeRunResult(output=_make_payload())

    _patch_vertex_slot(monkeypatch)
    _patch_build_agent(monkeypatch)
    monkeypatch.setattr(
        "src.utterances.batched.section_runner.run_vertex_agent_with_retry",
        _mixed_run,
    )

    parent = _make_parent()
    sections = [_make_section(i) for i in range(3)]

    with pytest.raises(ZeroUtterancesError):
        await run_all_sections(
            sections,
            parent,
            settings=settings,
            scrape=mock_scrape,
            scrape_cache=mock_scrape_cache,
        )


@pytest.mark.asyncio
async def test_transient_error_bubbles_from_section(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    mock_scrape: MagicMock,
    mock_scrape_cache: MagicMock,
) -> None:
    """AC4: TransientExtractionError propagates out of run_section and run_all_sections."""
    transient = TransientExtractionError(
        provider="vertex",
        status_code=503,
        status="UNAVAILABLE",
        model_name="gemini-test",
        fallback_message="upstream 503",
    )

    async def _raising_run(agent: Any, prompt: Any, *, deps: Any = None) -> Any:
        raise transient

    _patch_vertex_slot(monkeypatch)
    _patch_build_agent(monkeypatch)
    monkeypatch.setattr(
        "src.utterances.batched.section_runner.run_vertex_agent_with_retry",
        _raising_run,
    )

    parent = _make_parent()
    section = _make_section(index=0)

    with pytest.raises(TransientExtractionError):
        await run_section(
            section,
            parent,
            settings=settings,
            scrape=mock_scrape,
            scrape_cache=mock_scrape_cache,
        )

    call_count = 0

    async def _mixed_run(agent: Any, prompt: Any, *, deps: Any = None) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _FakeRunResult(
                output=_make_payload(
                    page_kind=PageKind.FORUM_THREAD,
                    utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
                )
            )
        raise TransientExtractionError(
            provider="vertex",
            status_code=503,
            status="UNAVAILABLE",
            model_name="gemini-test",
            fallback_message="upstream 503",
        )

    monkeypatch.setattr(
        "src.utterances.batched.section_runner.run_vertex_agent_with_retry",
        _mixed_run,
    )

    sections = [_make_section(i) for i in range(2)]
    with pytest.raises(TransientExtractionError):
        await run_all_sections(
            sections,
            parent,
            settings=settings,
            scrape=mock_scrape,
            scrape_cache=mock_scrape_cache,
        )
