from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import logfire

from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings, get_settings
from src.firecrawl_client import FirecrawlClient
from src.utterances.batched.assembler import assemble_sections
from src.utterances.batched.partition import partition_html
from src.utterances.batched.section_runner import run_all_sections
from src.utterances.errors import ZeroUtterancesError
from src.utterances.extractor import _extract_or_redirect, _sanitize_html
from src.utterances.schema import BatchedUtteranceRedirectionResponse, UtterancesPayload


async def extract_utterances_dispatched(
    url: str,
    client: FirecrawlClient,
    scrape_cache: SupabaseScrapeCache,
    *,
    settings: Settings | None = None,
    scrape: CachedScrape | None = None,
) -> UtterancesPayload:
    settings = settings or get_settings()

    with logfire.span("vibecheck.extract_utterances_dispatched", url=url) as span:
        if scrape is None:
            from src.utterances.extractor import _get_or_scrape
            scrape = await _get_or_scrape(url, client, scrape_cache)

        sanitized_html = await asyncio.to_thread(_sanitize_html, scrape.html or "")

        result = await _extract_or_redirect(
            url,
            client,
            scrape_cache,
            settings=settings,
            scrape=scrape,
            sanitized_html=sanitized_html,
        )

        if isinstance(result, UtterancesPayload):
            return result

        redirect: BatchedUtteranceRedirectionResponse = result
        sections = partition_html(sanitized_html, redirect, settings)
        span.set_attribute("section_count", len(sections))
        section_results = await run_all_sections(
            sections, redirect, settings=settings, scrape=scrape, scrape_cache=scrape_cache
        )
        merged = assemble_sections(section_results, redirect, sanitized_html, url)
        merged.scraped_at = datetime.now(UTC)

        if not merged.utterances:
            raise ZeroUtterancesError(
                "assembled section results produced zero utterances"
            )

        return merged
