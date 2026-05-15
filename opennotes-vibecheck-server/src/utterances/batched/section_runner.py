from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from typing import cast

import logfire
from pydantic_ai.models.instrumented import InstrumentationSettings

from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings
from src.monitoring import _PYDANTIC_AI_INSTRUMENTATION_VERSION
from src.services.gemini_agent import (
    build_agent,
    google_vertex_model_name,
    run_vertex_agent_with_retry,
)
from src.services.vertex_limiter import VertexLimiterBackendUnavailableError, vertex_slot
from src.utterances.batched.assembler import SectionResult
from src.utterances.batched.partition import HtmlSection
from src.utterances.errors import (
    TransientExtractionError,
    UtteranceExtractionError,
    ZeroUtterancesError,
    classify_pydantic_ai_error,
)
from src.utterances.extractor import (
    EXTRACTOR_SYSTEM_PROMPT,
    ExtractorDeps,
    _register_tools,
    _set_upstream_span_attrs,
)
from src.utterances.schema import BatchedUtteranceRedirectionResponse, UtterancesPayload


async def run_section(
    section: HtmlSection,
    parent: BatchedUtteranceRedirectionResponse,
    *,
    settings: Settings,
    scrape: CachedScrape,
    scrape_cache: SupabaseScrapeCache,
) -> SectionResult:
    with logfire.span(
        "vibecheck.extract_section",
        index=section.index,
        global_start=section.global_start,
        global_end=section.global_end,
    ) as span:
        agent = build_agent(
            settings,
            output_type=UtterancesPayload,
            system_prompt=EXTRACTOR_SYSTEM_PROMPT,
            name="vibecheck.utterance_extractor.section",
            tier="extractor",
            instrument=InstrumentationSettings(
                include_content=(
                    random.random() < settings.LOGFIRE_EXTRACTOR_CONTENT_SAMPLE_RATE
                ),
                include_binary_content=False,
                version=_PYDANTIC_AI_INSTRUMENTATION_VERSION,
            ),
        )
        _register_tools(agent)

        deps = ExtractorDeps(
            scrape=scrape,
            scrape_cache=scrape_cache,
            section_mode=True,
            section_html=section.html_slice,
            parent_page_kind=parent.page_kind,
            parent_utterance_stream_type=parent.utterance_stream_type,
            parent_page_title=parent.page_title,
        )

        user_prompt = _build_section_prompt(section, parent)

        model_name = google_vertex_model_name(
            settings.VERTEXAI_EXTRACTOR_MODEL,
            setting_name="VERTEXAI_EXTRACTOR_MODEL",
        )

        try:
            async with vertex_slot(settings):
                result = await run_vertex_agent_with_retry(agent, user_prompt, deps=deps)
        except ZeroUtterancesError:
            empty_payload = UtterancesPayload(
                utterances=[],
                page_kind=parent.page_kind,
                utterance_stream_type=parent.utterance_stream_type,
                page_title=parent.page_title,
                source_url=(scrape.metadata.source_url or "") if scrape.metadata else "",
                scraped_at=datetime.now(UTC),
            )
            return SectionResult(
                section=section,
                payload=empty_payload,
                per_section_page_kind_guess=None,
            )
        except TransientExtractionError:
            raise
        except VertexLimiterBackendUnavailableError as exc:
            transient = TransientExtractionError(
                provider="vertex_limiter",
                status=type(exc).__name__,
                model_name=model_name,
                fallback_message=f"Vertex limiter backend unavailable: {exc}",
            )
            _set_upstream_span_attrs(span, transient)
            raise transient from exc
        except Exception as exc:
            transient = classify_pydantic_ai_error(exc, model_name=model_name)
            if transient is not None:
                _set_upstream_span_attrs(span, transient)
                raise transient from exc
            raise UtteranceExtractionError(f"Section extraction failed: {exc}") from exc

        payload = cast(UtterancesPayload, cast(object, result.output))
        if not payload.utterances:
            empty_payload = UtterancesPayload(
                utterances=[],
                page_kind=parent.page_kind,
                utterance_stream_type=parent.utterance_stream_type,
                page_title=parent.page_title,
                source_url=(scrape.metadata.source_url or "") if scrape.metadata else "",
                scraped_at=datetime.now(UTC),
            )
            return SectionResult(
                section=section,
                payload=empty_payload,
                per_section_page_kind_guess=None,
            )

        per_section_page_kind_guess = payload.page_kind

        payload.page_kind = parent.page_kind
        payload.utterance_stream_type = parent.utterance_stream_type
        payload.page_title = parent.page_title
        payload.scraped_at = datetime.now(UTC)

        return SectionResult(
            section=section,
            payload=payload,
            per_section_page_kind_guess=per_section_page_kind_guess,
        )


async def run_all_sections(
    sections: list[HtmlSection],
    parent: BatchedUtteranceRedirectionResponse,
    *,
    settings: Settings,
    scrape: CachedScrape,
    scrape_cache: SupabaseScrapeCache,
) -> list[SectionResult]:
    semaphore = asyncio.Semaphore(settings.VIBECHECK_BATCH_PARALLEL)

    async def _run_one(section: HtmlSection) -> SectionResult:
        async with semaphore:
            return await run_section(
                section,
                parent,
                settings=settings,
                scrape=scrape,
                scrape_cache=scrape_cache,
            )

    return list(await asyncio.gather(*(_run_one(s) for s in sections)))


def _build_section_prompt(
    section: HtmlSection,
    parent: BatchedUtteranceRedirectionResponse,
) -> str:
    parts: list[str] = []
    if parent.boundary_instructions:
        parts.append(parent.boundary_instructions)
    parts.append(f"Page kind context from parent pass: {parent.page_kind}")
    if section.parent_context_text:
        parts.append(f"Preceding context:\n{section.parent_context_text}")
    parts.append(f"Section HTML to extract:\n{section.html_slice}")
    return "\n\n".join(parts)
