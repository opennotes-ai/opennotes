from __future__ import annotations

from datetime import UTC, datetime

from src.config import Settings, get_settings
from src.firecrawl_client import FirecrawlClient
from src.services.gemini_agent import build_agent

from .schema import UtterancesPayload


UTTERANCE_EXTRACTION_PROMPT = """\
You are extracting structured utterances from a scraped webpage's markdown.

Rules:
- The FIRST utterance is the blog post / article / thread root. kind='post', \
author=null unless a byline is clearly present, text=the full prose body with \
the comments section REMOVED.
- Each reader comment after the comments heading becomes its own utterance. \
kind='comment' for top-level comments, 'reply' for nested replies. author=the \
commenter's username (the bracketed link text, e.g. "[alice](...)" -> author="alice"). \
text=the comment body only, WITHOUT the author link line.
- Preserve every comment. Do not summarize. Do not skip any.
- Leave utterance_id, timestamp, parent_id as null; they get assigned downstream.
- page_title = the page's main heading. page_kind = 'blog_post' for blog posts \
with comments, 'forum_thread' for forum threads, 'article' for articles without \
comments, 'other' for anything else.
- source_url and scraped_at will be overwritten by the caller; set them to the \
given URL and current UTC time if you have to fill them.
"""


class UtteranceExtractionError(Exception):
    """Raised when scrape-based utterance extraction fails."""


async def extract_utterances(
    url: str,
    client: FirecrawlClient,
    *,
    settings: Settings | None = None,
) -> UtterancesPayload:
    """Scrape the URL to markdown, then use Gemini to extract structured utterances.

    Rationale: Firecrawl's /v2/extract LLM gave zero utterances for our reference
    target. /v2/scrape with onlyMainContent=true gives a clean markdown body +
    comments; we feed that to Vertex Gemini via pydantic-ai for structured output.
    """
    settings = settings or get_settings()

    try:
        scrape = await client.scrape(url, formats=["markdown"], only_main_content=True)
    except Exception as exc:
        raise UtteranceExtractionError(f"firecrawl scrape failed: {exc}") from exc

    markdown = scrape.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise UtteranceExtractionError("firecrawl scrape returned no markdown")

    agent = build_agent(
        settings,
        output_type=UtterancesPayload,
        system_prompt=UTTERANCE_EXTRACTION_PROMPT,
    )
    try:
        result = await agent.run(markdown)
    except Exception as exc:
        raise UtteranceExtractionError(f"Gemini extraction failed: {exc}") from exc

    payload: UtterancesPayload = result.output
    payload.source_url = url
    payload.scraped_at = payload.scraped_at or datetime.now(UTC)

    seen: set[str] = set()
    for i, utterance in enumerate(payload.utterances):
        uid = utterance.utterance_id
        if not uid or uid in seen:
            utterance.utterance_id = (
                f"{utterance.kind}-{i}-{hash(utterance.text) & 0xFFFFFFFF:08x}"
            )
        seen.add(utterance.utterance_id or "")

    return payload
