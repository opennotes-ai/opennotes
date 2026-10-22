"""TDD tests for TASK-1657.15: batched utterance extraction for oversized HTML.

Tests cover:
- HTML under threshold → unbatched extractor path (current behavior)
- HTML over threshold → batched path
- Batched extractor splits at safe boundaries (not in middle of an utterance)
- Merger reconstructs ordered utterances across batches without dupes
- Batch count capped at MAX_BATCHES (oldest dropped)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.services.firecrawl_client import ScrapeResult
from src.url_content_scan.schemas import PageKind
from src.url_content_scan.utterances.batched.merger import merge_section_payloads
from src.url_content_scan.utterances.batched.partition import (
    partition_html,
)
from src.url_content_scan.utterances.extractor import extract_utterances
from src.url_content_scan.utterances.schema import Utterance, UtterancesPayload

SOURCE_URL = "https://example.com/article"


def _make_scrape(html: str) -> ScrapeResult:
    return ScrapeResult.model_validate(
        {
            "html": html,
            "markdown": "# Article\n\nContent.",
            "metadata": {"title": "Article", "sourceURL": SOURCE_URL},
        }
    )


def _make_utterances_payload(utterances: list[Utterance]) -> UtterancesPayload:
    return UtterancesPayload(
        source_url=SOURCE_URL,
        scraped_at=datetime.now(UTC),
        utterances=utterances,
        page_kind=PageKind.OTHER,
    )


def _make_utterance(
    uid: str, text: str, kind: str = "post", parent_id: str | None = None
) -> Utterance:
    return Utterance(
        utterance_id=uid,
        kind=kind,  # type: ignore[arg-type]
        text=text,
        author=None,
        parent_id=parent_id,
    )


@pytest.mark.unit
class TestPartitionHtml:
    def test_empty_html_returns_empty(self) -> None:
        sections = partition_html("", target_bytes=1000, overlap_bytes=50, max_batches=10)
        assert sections == []

    def test_small_html_returns_single_section(self) -> None:
        html = "<html><body><p>Hello world</p></body></html>"
        sections = partition_html(html, target_bytes=10_000, overlap_bytes=50, max_batches=10)
        assert len(sections) == 1
        assert sections[0].index == 0
        assert sections[0].html_slice == html
        assert sections[0].global_start == 0
        assert sections[0].global_end == len(html.encode("utf-8"))
        assert sections[0].overlap_with_prev_bytes == 0

    def test_large_html_splits_into_multiple_sections(self) -> None:
        paragraph = "<p>" + "x" * 200 + "</p>"
        html = "<html><body>" + paragraph * 20 + "</body></html>"
        sections = partition_html(html, target_bytes=1000, overlap_bytes=50, max_batches=20)
        assert len(sections) > 1

    def test_sections_cover_full_html_end_to_end(self) -> None:
        paragraph = "<p>" + "a" * 100 + "</p>"
        html = "<html><body>" + paragraph * 10 + "</body></html>"
        raw = html.encode("utf-8")
        sections = partition_html(html, target_bytes=400, overlap_bytes=20, max_batches=20)
        assert sections[0].global_start == 0
        assert sections[-1].global_end == len(raw)

    def test_splits_do_not_occur_mid_utf8_char(self) -> None:
        content = "中" * 500
        html = f"<p>{content}</p>"
        raw = html.encode("utf-8")
        sections = partition_html(html, target_bytes=300, overlap_bytes=10, max_batches=20)
        for section in sections:
            raw[section.global_start : section.global_end].decode("utf-8")

    def test_max_batches_caps_section_count(self) -> None:
        paragraph = "<p>" + "x" * 200 + "</p>"
        html = "<html><body>" + paragraph * 50 + "</body></html>"
        max_batches = 3
        sections = partition_html(html, target_bytes=500, overlap_bytes=20, max_batches=max_batches)
        assert len(sections) <= max_batches

    def test_section_indices_are_sequential(self) -> None:
        paragraph = "<p>" + "x" * 100 + "</p>"
        html = "<html><body>" + paragraph * 15 + "</body></html>"
        sections = partition_html(html, target_bytes=400, overlap_bytes=20, max_batches=20)
        for i, section in enumerate(sections):
            assert section.index == i

    def test_first_section_has_no_overlap(self) -> None:
        paragraph = "<p>" + "x" * 200 + "</p>"
        html = "<html><body>" + paragraph * 10 + "</body></html>"
        sections = partition_html(html, target_bytes=600, overlap_bytes=50, max_batches=20)
        assert sections[0].overlap_with_prev_bytes == 0

    def test_subsequent_sections_have_overlap(self) -> None:
        paragraph = "<p>" + "x" * 200 + "</p>"
        html = "<html><body>" + paragraph * 10 + "</body></html>"
        sections = partition_html(html, target_bytes=600, overlap_bytes=50, max_batches=20)
        if len(sections) > 1:
            for section in sections[1:]:
                assert section.overlap_with_prev_bytes > 0

    def test_section_html_slice_starts_before_cut_due_to_overlap(self) -> None:
        paragraph = "<p>" + "x" * 200 + "</p>"
        html = "<html><body>" + paragraph * 10 + "</body></html>"
        sections = partition_html(html, target_bytes=600, overlap_bytes=50, max_batches=20)
        if len(sections) > 1:
            s1 = sections[1]
            assert len(s1.html_slice.encode("utf-8")) > s1.global_end - (
                s1.global_start + s1.overlap_with_prev_bytes
            )


@pytest.mark.unit
class TestMergeSectionPayloads:
    def test_single_section_returned_as_is(self) -> None:
        u = _make_utterance("post-1", "Hello world")
        payload = _make_utterances_payload([u])
        merged = merge_section_payloads([payload], source_url=SOURCE_URL)
        assert len(merged.utterances) == 1
        assert merged.utterances[0].utterance_id == "post-1"

    def test_multiple_sections_concatenated(self) -> None:
        u1 = _make_utterance("post-1", "First utterance")
        u2 = _make_utterance("post-2", "Second utterance")
        p1 = _make_utterances_payload([u1])
        p2 = _make_utterances_payload([u2])
        merged = merge_section_payloads([p1, p2], source_url=SOURCE_URL)
        assert len(merged.utterances) == 2
        assert merged.utterances[0].utterance_id == "post-1"
        assert merged.utterances[1].utterance_id == "post-2"

    def test_exact_duplicate_utterances_are_deduped(self) -> None:
        u = _make_utterance("post-dup", "Overlap text that appears in both sections")
        p1 = _make_utterances_payload([u])
        p2 = _make_utterances_payload([u])
        merged = merge_section_payloads([p1, p2], source_url=SOURCE_URL)
        assert len(merged.utterances) == 1

    def test_near_duplicate_utterances_whitespace_normalized_are_deduped(self) -> None:
        u1 = _make_utterance("id-1", "Hello   world")
        u2 = _make_utterance("id-2", "Hello world")
        p1 = _make_utterances_payload([u1])
        p2 = _make_utterances_payload([u2])
        merged = merge_section_payloads([p1, p2], source_url=SOURCE_URL)
        assert len(merged.utterances) == 1

    def test_unique_utterances_across_sections_all_preserved(self) -> None:
        utterances = [_make_utterance(f"u-{i}", f"Unique text {i}") for i in range(10)]
        payloads = [_make_utterances_payload([u]) for u in utterances]
        merged = merge_section_payloads(payloads, source_url=SOURCE_URL)
        assert len(merged.utterances) == 10

    def test_empty_sections_are_skipped(self) -> None:
        u = _make_utterance("post-1", "Only utterance")
        p1 = _make_utterances_payload([])
        p2 = _make_utterances_payload([u])
        p3 = _make_utterances_payload([])
        merged = merge_section_payloads([p1, p2, p3], source_url=SOURCE_URL)
        assert len(merged.utterances) == 1

    def test_source_url_set_on_merged_payload(self) -> None:
        u = _make_utterance("post-1", "Text")
        p = _make_utterances_payload([u])
        merged = merge_section_payloads([p], source_url="https://custom.example.com/")
        assert merged.source_url == "https://custom.example.com/"

    def test_empty_section_list_returns_empty_payload(self) -> None:
        merged = merge_section_payloads([], source_url=SOURCE_URL)
        assert merged.utterances == []
        assert merged.source_url == SOURCE_URL

    def test_order_preserved_across_sections(self) -> None:
        utterances = [_make_utterance(f"u-{i}", f"Text item {i}") for i in range(5)]
        payloads = [_make_utterances_payload([u]) for u in utterances]
        merged = merge_section_payloads(payloads, source_url=SOURCE_URL)
        ids = [u.utterance_id for u in merged.utterances]
        assert ids == [f"u-{i}" for i in range(5)]


@pytest.mark.unit
class TestExtractorRouting:
    def test_html_under_threshold_does_not_call_batched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def _spy_batched(
            scrape: ScrapeResult,
            source_url: str,
            *,
            settings: object,
        ) -> UtterancesPayload:
            calls.append("batched")
            return _make_utterances_payload([])

        monkeypatch.setattr(
            "src.url_content_scan.utterances.extractor._extract_batched",
            _spy_batched,
        )

        small_html = "<html><body><article data-role='post'><p>Short</p></article></body></html>"
        scrape = _make_scrape(small_html)

        from src.config import Settings

        settings = Settings()
        monkeypatch.setattr(settings, "URL_SCAN_UTTERANCE_BATCH_THRESHOLD_BYTES", 100_000)

        extract_utterances(scrape, SOURCE_URL, settings=settings)
        assert "batched" not in calls

    def test_html_over_threshold_calls_batched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def _spy_batched(
            scrape: ScrapeResult,
            source_url: str,
            *,
            settings: object,
        ) -> UtterancesPayload:
            calls.append("batched")
            return _make_utterances_payload([_make_utterance("post-1", "Batched result")])

        monkeypatch.setattr(
            "src.url_content_scan.utterances.extractor._extract_batched",
            _spy_batched,
        )

        large_html = "<html><body>" + "<p>" + "x" * 1000 + "</p>" * 10 + "</body></html>"
        scrape = _make_scrape(large_html)

        from src.config import Settings

        settings = Settings()
        monkeypatch.setattr(settings, "URL_SCAN_UTTERANCE_BATCH_THRESHOLD_BYTES", 100)

        result = extract_utterances(scrape, SOURCE_URL, settings=settings)
        assert "batched" in calls
        assert len(result.utterances) == 1

    def test_html_exactly_at_threshold_does_not_call_batched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def _spy_batched(*args: object, **kwargs: object) -> UtterancesPayload:
            calls.append("batched")
            return _make_utterances_payload([])

        monkeypatch.setattr(
            "src.url_content_scan.utterances.extractor._extract_batched",
            _spy_batched,
        )

        html = "<html><body><p>x</p></body></html>"
        threshold = len(html.encode("utf-8"))
        scrape = _make_scrape(html)

        from src.config import Settings

        settings = Settings()
        monkeypatch.setattr(settings, "URL_SCAN_UTTERANCE_BATCH_THRESHOLD_BYTES", threshold)

        extract_utterances(scrape, SOURCE_URL, settings=settings)
        assert "batched" not in calls

    def test_batched_extraction_end_to_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "src.utils.url_security._resolve",
            lambda hostname: ["93.184.216.34"],
        )

        html = (
            "<html><body>"
            '<article data-role="post"><h1>First</h1><p>First section content here.</p></article>'
            '<article data-role="post"><h1>Second</h1><p>Second section content here.</p></article>'
            "</body></html>"
        )
        scrape = _make_scrape(html)

        from src.config import Settings

        settings = Settings()
        monkeypatch.setattr(settings, "URL_SCAN_UTTERANCE_BATCH_THRESHOLD_BYTES", 50)
        monkeypatch.setattr(settings, "URL_SCAN_UTTERANCE_BATCH_SECTION_TARGET_BYTES", 200)
        monkeypatch.setattr(settings, "URL_SCAN_UTTERANCE_BATCH_OVERLAP_BYTES", 20)
        monkeypatch.setattr(settings, "URL_SCAN_UTTERANCE_BATCH_MAX_BATCHES", 10)

        result = extract_utterances(scrape, SOURCE_URL, settings=settings)
        assert result.source_url == SOURCE_URL
        assert len(result.utterances) > 0
