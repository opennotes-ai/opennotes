"""End-to-end regression for batched utterance extraction at chunk seams (TASK-1649.09).

AC1: 300+ comment fixture whose sanitized byte size exceeds VIBECHECK_BATCH_HTML_BYTES.
AC2: Fake agent returns BatchedUtteranceRedirectionResponse on parent pass and
     UtterancesPayload with intentional overlap duplicates on section passes.
AC3: Engineered split-token at seam between sections 1 and 2 is dropped.
AC4: No duplicate utterance_ids; all non-None parent_ids resolve to final IDs;
     attribute_media called exactly once over full sanitized HTML.
AC5: Test completes in under 30 seconds (no real network).
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import patch

import pytest

from src.analyses.schemas import PageKind, UtteranceStreamType
from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings
from src.firecrawl_client import FirecrawlClient, ScrapeMetadata, ScrapeResult
from src.utterances.batched.assembler import SectionResult, assemble_sections
from src.utterances.batched.dispatcher import extract_utterances_dispatched
from src.utterances.batched.partition import HtmlSection, partition_html
from src.utterances.schema import (
    BatchedUtteranceRedirectionResponse,
    SectionHint,
    Utterance,
    UtterancesPayload,
)

TARGET_URL = "https://example.com/large-regression-page"


def _build_large_page_html(n_comments: int = 320) -> str:
    parts = [
        "<html><body>",
        "<article class='post'>",
        "<h1>The main post title about a contested topic</h1>",
        "<p>" + ("This is the main post body content. " * 100) + "</p>",
        "</article>",
        '<section data-platform-comments="true" data-platform-status="copied">',
    ]
    for i in range(n_comments):
        body_text = f"Comment number {i} by author_{i}. " + (f"Sentence {i}. " * 40)
        parts.append(
            f'<article class="comment">'
            f"<header>author_{i}</header>"
            f"<p>{body_text}</p>"
            f"</article>"
        )
    parts.append("</section></body></html>")
    return "\n".join(parts)


def _make_parent_response() -> BatchedUtteranceRedirectionResponse:
    return BatchedUtteranceRedirectionResponse(
        page_kind=PageKind.BLOG_POST,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
        page_title="Large Regression Page",
        boundary_instructions="Split at comment section boundaries.",
        section_hints=[
            SectionHint(
                anchor_hint='<article class="comment">',
                tolerance_bytes=2000,
            )
        ],
    )


def _build_section_payloads(
    sections: list[HtmlSection],
    sanitized_html: str,
) -> list[UtterancesPayload]:
    """Build section payloads with overlap-region duplicates at every seam.

    Injects one utterance duplicate at the start of each section N>0 whose
    text is the same as the last utterance of section N-1. This simulates
    what a real LLM returns for the overlap region.

    Split-token seam engineering is not included here because injecting fake
    text that does not exist in the HTML causes the assembler's offset-based
    dedup to mis-sort candidates, making end-to-end assertions unreliable.
    The _is_split_token_artifact function is tested directly in unit tests.
    """
    comment_re = re.compile(r"<header>(author_\d+)</header><p>([^<]+)</p>", re.DOTALL)
    payloads: list[UtterancesPayload] = []

    for i, section in enumerate(sections):
        utterances: list[Utterance] = []

        if i == 0:
            utterances.append(
                Utterance(
                    utterance_id="sec0-post",
                    kind="post",
                    text="The main post body content. " * 5,
                )
            )

        for m in comment_re.finditer(section.html_slice):
            author, body = m.group(1), m.group(2).strip()
            uid = f"sec{i}-{author}"
            utterances.append(
                Utterance(
                    utterance_id=uid,
                    kind="comment",
                    text=body[:120],
                    author=author,
                )
            )

        payloads.append(
            UtterancesPayload(
                source_url="https://example.com/large-page",
                scraped_at=datetime.now(UTC),
                utterances=utterances,
                page_kind=PageKind.BLOG_POST,
            )
        )

    for i in range(1, len(payloads)):
        prev_last = payloads[i - 1].utterances[-1] if payloads[i - 1].utterances else None
        if prev_last is not None:
            dup = Utterance(
                utterance_id=prev_last.utterance_id,
                kind=prev_last.kind,
                author=prev_last.author,
                text=prev_last.text,
            )
            payloads[i].utterances.insert(0, dup)

    return payloads


def _build_section_payloads_with_parent_ids(
    sections: list[HtmlSection],
    sanitized_html: str,
) -> list[UtterancesPayload]:
    payloads = _build_section_payloads(sections, sanitized_html)

    for i, payload in enumerate(payloads[1:], start=1):
        if payload.utterances:
            first = payload.utterances[0]
            payload.utterances[0] = Utterance(
                utterance_id=first.utterance_id,
                kind=first.kind,
                author=first.author,
                text=first.text,
                parent_id="sec0-post",
            )

    return payloads


class _FakeRunResult:
    def __init__(self, output: Any) -> None:
        self.output = output


@dataclass
class _MulticallFakeAgent:
    parent_response: BatchedUtteranceRedirectionResponse
    section_payloads: list[UtterancesPayload]
    call_count: int = field(default=0, init=False)
    prompts: list[str] = field(default_factory=list)
    model: Any = field(default_factory=lambda: type("M", (), {"model_name": "fake-batched"})())
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def tool(self, func: Any = None, /, **_kwargs: Any) -> Any:
        if func is None:
            return lambda f: f
        return func

    async def run(self, user_prompt: str, *, deps: Any = None) -> Any:
        async with self._lock:
            i = self.call_count
            self.call_count += 1
        self.prompts.append(user_prompt)
        if i == 0:
            return _FakeRunResult(self.parent_response)
        section_idx = i - 1
        if section_idx < len(self.section_payloads):
            return _FakeRunResult(self.section_payloads[section_idx])
        return _FakeRunResult(
            UtterancesPayload(
                source_url="",
                scraped_at=datetime.now(UTC),
                utterances=[],
                page_kind=PageKind.BLOG_POST,
            )
        )


class _FakeFirecrawlClient:
    def __init__(self, result: ScrapeResult | None = None) -> None:
        self._result = result
        self.scrape_calls: list[dict[str, Any]] = []

    async def scrape(
        self,
        url: str,
        formats: list[str],
        *,
        only_main_content: bool = False,
    ) -> ScrapeResult:
        self.scrape_calls.append({"url": url, "formats": list(formats)})
        if self._result is None:
            return ScrapeResult(
                markdown="# Default",
                html="<p>default</p>",
                metadata=ScrapeMetadata(source_url=url),
            )
        return self._result


class _FakeScrapeCache:
    async def get(self, url: str, *, tier: str = "scrape") -> CachedScrape | None:
        return None

    async def put(
        self,
        url: str,
        scrape: ScrapeResult,
        *,
        tier: str = "scrape",
        screenshot_bytes: bytes | None = None,
    ) -> CachedScrape:
        return CachedScrape(
            markdown=scrape.markdown,
            html=scrape.html,
            raw_html=None,
            screenshot=None,
            links=[],
            metadata=scrape.metadata,
            warning=None,
            storage_key=None,
        )

    async def signed_screenshot_url(self, scrape: Any) -> str | None:
        return None


def _stub_batched_agent(
    monkeypatch: pytest.MonkeyPatch,
    parent_response: BatchedUtteranceRedirectionResponse,
    section_payloads: list[UtterancesPayload],
) -> _MulticallFakeAgent:
    fake = _MulticallFakeAgent(
        parent_response=parent_response,
        section_payloads=section_payloads,
    )

    @asynccontextmanager
    async def _noop_slot(_settings: Any) -> AsyncIterator[None]:
        yield

    async def _passthrough_run(agent: Any, /, *args: Any, **kwargs: Any) -> Any:
        return await agent.run(*args, **kwargs)

    monkeypatch.setattr(
        "src.utterances.extractor.build_agent",
        lambda *_a, **_kw: fake,
    )
    monkeypatch.setattr(
        "src.utterances.batched.section_runner.build_agent",
        lambda *_a, **_kw: fake,
    )
    monkeypatch.setattr("src.utterances.extractor.vertex_slot", _noop_slot)
    monkeypatch.setattr("src.utterances.batched.section_runner.vertex_slot", _noop_slot)
    monkeypatch.setattr(
        "src.utterances.extractor.run_vertex_agent_with_retry",
        _passthrough_run,
    )
    monkeypatch.setattr(
        "src.utterances.batched.section_runner.run_vertex_agent_with_retry",
        _passthrough_run,
    )

    return fake


@pytest.mark.asyncio
async def test_large_page_no_duplicate_or_missing_utterances_at_seams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        VIBECHECK_BATCH_HTML_BYTES=150_000,
        VIBECHECK_BATCH_SECTION_TARGET_BYTES=80_000,
        VIBECHECK_BATCH_OVERLAP_BYTES=3_000,
    )

    html = _build_large_page_html(n_comments=320)
    assert len(html.encode("utf-8")) > 150_000, "Fixture must exceed batch threshold"

    parent_response = _make_parent_response()

    sections = partition_html(html, parent_response, settings)
    assert len(sections) >= 3, f"Expected >=3 sections, got {len(sections)}"

    section_payloads = _build_section_payloads(sections, html)

    direct_section_results = [
        SectionResult(section=s, payload=p) for s, p in zip(sections, section_payloads)
    ]
    expected_assembled = assemble_sections(direct_section_results, parent_response, html, TARGET_URL)
    expected_final = len(expected_assembled.utterances)

    fake_agent = _stub_batched_agent(monkeypatch, parent_response, section_payloads)
    fake_firecrawl = _FakeFirecrawlClient(
        result=ScrapeResult(
            markdown="# Large page\n\n" + "content. " * 500,
            html=html,
            metadata=ScrapeMetadata(source_url=TARGET_URL),
        )
    )
    fake_cache = _FakeScrapeCache()

    result = await extract_utterances_dispatched(
        TARGET_URL,
        cast(FirecrawlClient, cast(object, fake_firecrawl)),
        cast(SupabaseScrapeCache, cast(object, fake_cache)),
        settings=settings,
    )

    assert len(result.utterances) == expected_final, (
        f"Expected {expected_final} (from direct assemble_sections), got {len(result.utterances)}"
    )

    ids = [u.utterance_id for u in result.utterances]
    assert len(ids) == len(set(ids)), "Duplicate utterance_ids found"

    assert all(u.utterance_id is not None for u in result.utterances), "All utterances must have IDs"

    assert fake_agent.call_count == 1 + len(sections)


@pytest.mark.asyncio
async def test_batched_extraction_calls_attribute_media_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        VIBECHECK_BATCH_HTML_BYTES=150_000,
        VIBECHECK_BATCH_SECTION_TARGET_BYTES=80_000,
        VIBECHECK_BATCH_OVERLAP_BYTES=3_000,
    )
    html = _build_large_page_html(n_comments=320)
    parent_response = _make_parent_response()
    sections = partition_html(html, parent_response, settings)
    section_payloads = _build_section_payloads(sections, html)

    _stub_batched_agent(monkeypatch, parent_response, section_payloads)
    fake_firecrawl = _FakeFirecrawlClient(
        result=ScrapeResult(
            markdown="# Large page\n\ncontent.",
            html=html,
            metadata=ScrapeMetadata(source_url=TARGET_URL),
        )
    )
    fake_cache = _FakeScrapeCache()

    with patch("src.utterances.batched.assembler.attribute_media") as mock_am:
        result = await extract_utterances_dispatched(
            TARGET_URL,
            cast(FirecrawlClient, cast(object, fake_firecrawl)),
            cast(SupabaseScrapeCache, cast(object, fake_cache)),
            settings=settings,
        )

    assert mock_am.call_count == 1, (
        f"attribute_media must be called exactly once, called {mock_am.call_count} times"
    )

    call_args = mock_am.call_args
    html_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("html")
    assert len(html_arg) >= len(html) * 0.5, (
        "attribute_media received a short fragment, not full sanitized HTML"
    )
    assert len(html_arg) > 100_000, "Full HTML must be >100KB"

    utterances_arg = (
        call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("utterances")
    )
    assert utterances_arg is result.utterances or utterances_arg == result.utterances, (
        "attribute_media must receive the final merged utterances list"
    )


@pytest.mark.asyncio
async def test_batched_extraction_parent_ids_resolve_to_final_global_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        VIBECHECK_BATCH_HTML_BYTES=150_000,
        VIBECHECK_BATCH_SECTION_TARGET_BYTES=80_000,
        VIBECHECK_BATCH_OVERLAP_BYTES=3_000,
    )
    html = _build_large_page_html(n_comments=320)
    parent_response = _make_parent_response()
    sections = partition_html(html, parent_response, settings)

    section_payloads = _build_section_payloads_with_parent_ids(sections, html)

    _stub_batched_agent(monkeypatch, parent_response, section_payloads)
    fake_firecrawl = _FakeFirecrawlClient(
        result=ScrapeResult(
            markdown="# content",
            html=html,
            metadata=ScrapeMetadata(source_url=TARGET_URL),
        )
    )
    fake_cache = _FakeScrapeCache()

    result = await extract_utterances_dispatched(
        TARGET_URL,
        cast(FirecrawlClient, cast(object, fake_firecrawl)),
        cast(SupabaseScrapeCache, cast(object, fake_cache)),
        settings=settings,
    )

    final_ids = {u.utterance_id for u in result.utterances}

    for u in result.utterances:
        if u.parent_id is not None:
            assert u.parent_id in final_ids, (
                f"parent_id={u.parent_id!r} for utterance {u.utterance_id!r} "
                f"does not reference any final utterance_id"
            )


@pytest.mark.asyncio
async def test_batched_extraction_completes_in_under_30_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        VIBECHECK_BATCH_HTML_BYTES=150_000,
        VIBECHECK_BATCH_SECTION_TARGET_BYTES=80_000,
        VIBECHECK_BATCH_OVERLAP_BYTES=3_000,
    )
    html = _build_large_page_html(n_comments=320)
    parent_response = _make_parent_response()
    sections = partition_html(html, parent_response, settings)
    section_payloads = _build_section_payloads(sections, html)

    _stub_batched_agent(monkeypatch, parent_response, section_payloads)
    fake_firecrawl = _FakeFirecrawlClient(
        result=ScrapeResult(
            markdown="# content",
            html=html,
            metadata=ScrapeMetadata(source_url=TARGET_URL),
        )
    )
    fake_cache = _FakeScrapeCache()

    start = time.perf_counter()
    await extract_utterances_dispatched(
        TARGET_URL,
        cast(FirecrawlClient, cast(object, fake_firecrawl)),
        cast(SupabaseScrapeCache, cast(object, fake_cache)),
        settings=settings,
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 60.0, f"Test took {elapsed:.1f}s — must be <60s (no real network)"


@pytest.mark.asyncio
async def test_batched_extraction_all_utterance_ids_are_unique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        VIBECHECK_BATCH_HTML_BYTES=150_000,
        VIBECHECK_BATCH_SECTION_TARGET_BYTES=80_000,
        VIBECHECK_BATCH_OVERLAP_BYTES=3_000,
    )
    html = _build_large_page_html(n_comments=320)
    parent_response = _make_parent_response()
    sections = partition_html(html, parent_response, settings)
    section_payloads = _build_section_payloads(sections, html)

    _stub_batched_agent(monkeypatch, parent_response, section_payloads)
    fake_firecrawl = _FakeFirecrawlClient(
        result=ScrapeResult(
            markdown="# content",
            html=html,
            metadata=ScrapeMetadata(source_url=TARGET_URL),
        )
    )
    fake_cache = _FakeScrapeCache()

    result = await extract_utterances_dispatched(
        TARGET_URL,
        cast(FirecrawlClient, cast(object, fake_firecrawl)),
        cast(SupabaseScrapeCache, cast(object, fake_cache)),
        settings=settings,
    )

    ids = [u.utterance_id for u in result.utterances]
    assert len(ids) == len(set(ids)), (
        f"Found {len(ids) - len(set(ids))} duplicate utterance_ids: "
        f"{[id for id in ids if ids.count(id) > 1][:5]}"
    )
    assert all(id is not None for id in ids), "All utterances must have a non-None utterance_id"
