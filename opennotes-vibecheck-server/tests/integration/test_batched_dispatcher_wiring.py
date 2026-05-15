"""Wiring smoke tests: orchestrator and pdf_extract route through extract_utterances_dispatched.

Asserts that both production call sites invoke the dispatcher, not the old
extract_utterances. Does NOT exercise orchestrator logic end-to-end — stubs
everything except the import-name assertion.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.jobs import orchestrator, pdf_extract


def _stub_all_pre_and_post_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "_build_scrape_cache", lambda s: MagicMock())
    monkeypatch.setattr(orchestrator, "_build_firecrawl_client", lambda s: MagicMock())
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_tier1_client", lambda s: MagicMock()
    )

    async def noop(*args: Any, **kwargs: Any) -> None:
        return None

    async def noop_bool(*args: Any, **kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(orchestrator, "_scrape_step", AsyncMock(return_value=MagicMock(metadata=None)))
    monkeypatch.setattr(orchestrator, "_revalidate_final_url", noop)
    monkeypatch.setattr(orchestrator, "_set_last_stage", noop)
    monkeypatch.setattr(orchestrator, "persist_utterances", noop)
    monkeypatch.setattr(orchestrator, "_set_analyzing", noop)
    monkeypatch.setattr(orchestrator, "_run_all_sections", noop)
    monkeypatch.setattr(orchestrator, "_run_safety_recommendation_step", noop)
    monkeypatch.setattr(orchestrator, "_run_headline_summary_step", noop)
    monkeypatch.setattr(orchestrator, "maybe_finalize_job", noop_bool)


@pytest.mark.asyncio
async def test_orchestrator_url_path_calls_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_run_pipeline for a 'url' source type calls extract_utterances_dispatched."""
    _stub_all_pre_and_post_gemini(monkeypatch)

    spy = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(orchestrator, "extract_utterances_dispatched", spy)

    url = "https://example.com/article"
    await orchestrator._run_pipeline(
        MagicMock(), uuid4(), uuid4(), url, MagicMock(), source_type="url"
    )

    spy.assert_awaited_once()
    assert spy.call_args.args[0] == url


@pytest.mark.asyncio
async def test_orchestrator_url_path_escalates_tier2_on_zero_utterances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ZeroUtterancesError on first call triggers Tier 2 escalation and second dispatcher call."""
    from src.utterances.extractor import ZeroUtterancesError

    _stub_all_pre_and_post_gemini(monkeypatch)

    call_count = 0

    async def flaky_dispatcher(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ZeroUtterancesError("first pass empty")
        return MagicMock()

    monkeypatch.setattr(orchestrator, "extract_utterances_dispatched", flaky_dispatcher)

    await orchestrator._run_pipeline(
        MagicMock(), uuid4(), uuid4(), "https://example.com/article", MagicMock(), source_type="url"
    )

    assert call_count == 2


@pytest.mark.asyncio
async def test_pdf_extract_step_calls_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pdf_extract_step calls extract_utterances_dispatched exactly once."""
    spy = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(pdf_extract, "extract_utterances_dispatched", spy)

    monkeypatch.setattr(pdf_extract, "get_pdf_upload_store", lambda bucket: MagicMock(
        signed_read_url=MagicMock(return_value="https://storage.example.com/signed-url")
    ))

    scrape_result = MagicMock()
    scrape_result.html = "<article>Some substantive content about the topic.</article>"
    scrape_result.raw_html = "<article>Some substantive content about the topic.</article>"
    scrape_result.markdown = "Some substantive content about the topic."
    scrape_result.metadata = MagicMock(source_url="https://storage.example.com/signed-url")

    fake_client = MagicMock()
    fake_client.scrape = AsyncMock(return_value=scrape_result)

    monkeypatch.setattr(pdf_extract, "_store_pdf_archive", AsyncMock(return_value=None))

    fake_settings = MagicMock()
    fake_settings.VIBECHECK_PDF_UPLOAD_BUCKET = "test-bucket"
    fake_scrape_cache = MagicMock()
    fake_scrape_cache.put = AsyncMock(return_value=MagicMock())

    from src.jobs.scrape_quality import ScrapeQuality
    monkeypatch.setattr(pdf_extract, "classify_scrape", lambda s: ScrapeQuality.OK)

    await pdf_extract.pdf_extract_step(
        MagicMock(),
        uuid4(),
        "gs://test-bucket/some-doc.pdf",
        settings=fake_settings,
        client=fake_client,
        scrape_cache=fake_scrape_cache,
    )

    spy.assert_awaited_once()


@pytest.mark.asyncio
async def test_pdf_extract_step_zero_utterances_raises_pdf_extraction_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ZeroUtterancesError from dispatcher propagates as PDFExtractionError."""
    from src.utterances.extractor import ZeroUtterancesError

    async def raise_zero(*args: Any, **kwargs: Any) -> None:
        raise ZeroUtterancesError("no utterances in PDF")

    monkeypatch.setattr(pdf_extract, "extract_utterances_dispatched", raise_zero)

    monkeypatch.setattr(pdf_extract, "get_pdf_upload_store", lambda bucket: MagicMock(
        signed_read_url=MagicMock(return_value="https://storage.example.com/signed-url")
    ))

    scrape_result = MagicMock()
    scrape_result.html = "<article>Some substantive content about the topic.</article>"
    scrape_result.raw_html = "<article>Some substantive content about the topic.</article>"
    scrape_result.markdown = "Some substantive content about the topic."
    scrape_result.metadata = MagicMock(source_url="https://storage.example.com/signed-url")

    fake_client = MagicMock()
    fake_client.scrape = AsyncMock(return_value=scrape_result)

    monkeypatch.setattr(pdf_extract, "_store_pdf_archive", AsyncMock(return_value=None))

    fake_settings = MagicMock()
    fake_settings.VIBECHECK_PDF_UPLOAD_BUCKET = "test-bucket"
    fake_scrape_cache = MagicMock()
    fake_scrape_cache.put = AsyncMock(return_value=MagicMock())

    from src.jobs.scrape_quality import ScrapeQuality
    monkeypatch.setattr(pdf_extract, "classify_scrape", lambda s: ScrapeQuality.OK)

    with pytest.raises(pdf_extract.PDFExtractionError, match="zero utterances"):
        await pdf_extract.pdf_extract_step(
            MagicMock(),
            uuid4(),
            "gs://test-bucket/some-doc.pdf",
            settings=fake_settings,
            client=fake_client,
            scrape_cache=fake_scrape_cache,
        )
