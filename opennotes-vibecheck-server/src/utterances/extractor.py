"""Shape-agnostic utterance extractor with pydantic-ai tool surface.

The extractor fetches a page's markdown + sanitized HTML + full-page
screenshot in a single Firecrawl `/v2/scrape` call, persists the bundle in
`SupabaseScrapeCache` (72h TTL), and hands the markdown to a Gemini agent
for structured utterance extraction. The agent may call `get_html()` or
`get_screenshot()` as tools when markdown alone is ambiguous.

Cache ladder (scrape tier):
    1. scrape_cache.get(url)           -> hit reuses (returns CachedScrape)
    2. client.scrape(url, all formats) -> miss fetches, persists via cache.put
                                         (put() returns CachedScrape with
                                         Supabase storage_key for the PNG)
    3. Gemini extracts utterances      -> payload returned

Both the hit and miss branches produce a `CachedScrape`: a `ScrapeResult`
subclass carrying the Supabase `storage_key` snapshotted at cache read or
write time. The agent's `get_screenshot()` tool signs off that snapshotted
key rather than re-querying the row — immune to a concurrent `put()` that
would otherwise TOCTOU-race the signature against a replaced row.

Returned payload has `scraped_at` unconditionally overwritten to
`datetime.now(UTC)` after the agent returns. This closes TASK-1471.23 at
source: cached payloads now always reflect fresh capture time.

Screenshot tool behavior: `signed_screenshot_url()` is re-awaited on every
call so Supabase's 15-minute signed-URL TTL can't surface as a stale link
inside a long-running agent run. When no screenshot was persisted the tool
returns None; callers in the agent's tool surface receive that None and
proceed from markdown alone.
"""

from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import logfire
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ImageUrl

from src.analyses.schemas import PageKind, UtteranceStreamType
from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings, get_settings
from src.firecrawl_client import FirecrawlClient
from src.services.gemini_agent import (
    build_agent,
    google_vertex_model_name,
    run_vertex_agent_with_retry,
)
from src.services.vertex_limiter import vertex_slot
from src.utils.html_sanitize import strip_for_llm
from src.utterances.errors import (
    TransientExtractionError,
    UtteranceExtractionError,
    ZeroUtterancesError,
    classify_firecrawl_error,
    classify_pydantic_ai_error,
)

from .media_extraction import attribute_media
from .schema import UtterancesPayload

EXTRACTOR_SYSTEM_PROMPT = f"""\
You extract structured utterances from a scraped webpage's markdown.

Output a `UtterancesPayload` matching the schema. Leave `utterance_id`,
`timestamp`, and `parent_id` as null unless the markdown explicitly encodes
them. The caller overwrites `source_url` and `scraped_at`.

page_kind values (pick exactly one) and their extraction rules:

- `{PageKind.BLOG_POST.value}`: a single post with a comments section below.
  First utterance is the post body (kind='post', author=byline or null,
  comments removed from text). Each comment becomes its own utterance
  (kind='comment' for top-level, kind='reply' for nested replies). Preserve
  every comment — never summarize or skip.

- `{PageKind.FORUM_THREAD.value}`: a linear thread (opening post + flat
  replies). First utterance kind='post' for the opening; each subsequent
  reply kind='reply' with parent_id pointing at the opening post's
  utterance_id (fill utterance_id on the root to make this link possible).

- `{PageKind.HIERARCHICAL_THREAD.value}`: a threaded tree (Reddit / HN
  style). Emit kind='post' for the root and kind='reply' for every nested
  comment. Populate utterance_id and parent_id so the tree structure is
  recoverable.

- `{PageKind.BLOG_INDEX.value}`: a list / index page of multiple posts with
  no single 'root'. Emit one kind='post' utterance per listed entry; parent
  linkage is not meaningful here, so leave parent_id null.

- `{PageKind.ARTICLE.value}`: a standalone article with no comments. Emit a
  single kind='post' utterance containing the article body.

- `{PageKind.OTHER.value}`: anything that doesn't match the above. Do your
  best to emit at least one kind='post' utterance covering the main content
  and leave the rest empty.

utterance_stream_type values (pick exactly one):

- `{UtteranceStreamType.DIALOGUE.value}`: a direct back-and-forth exchange,
  interview, debate, transcript, or chat-style conversation.
- `{UtteranceStreamType.COMMENT_SECTION.value}`: one root post/article plus
  user comments or replies reacting to it.
- `{UtteranceStreamType.ARTICLE_OR_MONOLOGUE.value}`: one author or source
  mostly speaking alone, including articles, essays, statements, and speeches.
- `{UtteranceStreamType.MIXED.value}`: multiple shapes are materially present
  (for example, an article with an embedded transcript and comments).
- `{UtteranceStreamType.UNKNOWN.value}`: use only when the scrape is too
  ambiguous or sparse to infer the stream shape.

Tool usage (markdown-first):
- You have two tools: `get_html()` and `get_screenshot()`. Prefer markdown.
- Call `get_html()` only when markdown looks truncated or is missing a
  utterance stream you can see markers for (e.g. the text ends in
  "[comments truncated]" or a comment block header appears with no bodies
  beneath it). The HTML is pre-sanitized (scripts/styles stripped).
- Call `get_screenshot()` only when the page is image-heavy and markdown
  loses critical structure (e.g. a screenshot of a forum post is the entire
  content). The screenshot URL is short-lived; use it in the same turn.
- Call each tool at most once per run. Do not loop.
"""

CORAL_COMMENTS_PROMPT_ADDENDUM = """\

Coral comment extraction:
- The scrape contains a `[data-coral-comments]` marker copied from an embedded
  Coral comment widget.
- Treat each `article.comment` inside that marker as a separate top-level
  `kind='comment'` utterance.
- Use `get_html()` if markdown does not preserve the marker's `article.comment`
  structure clearly.
"""

CORAL_COMMENTS_IGNORE_ADDENDUM = """\

Coral comment extraction:
- The scrape contains only Coral comment widget shell/chrome, not loaded user
  comments.
- Do not emit `kind='comment'` utterances from moderation guidelines, counters,
  sort controls, or placeholder `Commenter` rows.
"""

_CORAL_MARKER_RE = re.compile(
    r"<(?P<tag>section|div)\b(?P<attrs>[^>]*)\bdata-coral-comments\b(?P<attrs_after>[^>]*)>"
    r"(?P<body>.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_CORAL_ARTICLE_RE = re.compile(
    r"<article\b(?=[^>]*\bclass=[\"'][^\"']*\bcomment\b)[^>]*>"
    r"(?P<body>.*?)</article>",
    re.IGNORECASE | re.DOTALL,
)
_CORAL_HEADER_RE = re.compile(
    r"<header\b[^>]*>(?P<value>.*?)</header>", re.IGNORECASE | re.DOTALL
)
_CORAL_PARAGRAPH_RE = re.compile(
    r"<p\b[^>]*>(?P<value>.*?)</p>", re.IGNORECASE | re.DOTALL
)

@dataclass
class ExtractorDeps:
    """Dependencies passed to the pydantic-ai agent via `RunContext.deps`.

    `scrape` is the bundle the agent's tools read from (html, markdown,
    source URL) — a `CachedScrape` carrying the snapshotted Supabase
    `storage_key`, so the screenshot tool can sign the exact object this
    scrape references even when a concurrent `put()` has since replaced
    the row. `scrape_cache` is the signer — the screenshot tool re-mints
    a signed URL on each call so the 15-minute Supabase TTL never leaks
    into agent output.
    """

    scrape: CachedScrape
    scrape_cache: SupabaseScrapeCache


async def extract_utterances(
    url: str,
    client: FirecrawlClient,
    scrape_cache: SupabaseScrapeCache,
    *,
    settings: Settings | None = None,
    scrape: CachedScrape | None = None,
) -> UtterancesPayload:
    """Scrape + persist + agent-extract utterances for a URL.

    Returns a fully validated `UtterancesPayload` with freshly-assigned
    `source_url`, `scraped_at = now(UTC)`, and deduplicated `utterance_id`s.

    When the caller already fetched a `CachedScrape` (e.g. the orchestrator's
    Tier 1/Tier 2 ladder), pass it as `scrape=` so the extractor reuses that
    bundle instead of re-reading `tier="scrape"` from cache. Without this
    pass-through the extractor's `_get_or_scrape` would silently overwrite
    a fresh Tier 2 escalation with a cached Tier 1 INTERSTITIAL bundle.

    Wrapped in a `vibecheck.extract_utterances` Logfire span. Transient
    upstream failures (Vertex 429/503/504, Firecrawl 429/5xx, network
    timeouts/transport errors) at either call site surface as
    `TransientExtractionError` with neutral `upstream_*` span attrs (plus
    Vertex-arm legacy `vertex_*` attrs for backward-compat); non-transient
    failures surface as the terminal `UtteranceExtractionError`.
    """
    settings = settings or get_settings()

    with logfire.span("vibecheck.extract_utterances", url=url) as span:
        if scrape is None:
            scrape = await _get_or_scrape(url, client, scrape_cache, span=span)
        markdown = scrape.markdown
        if not markdown or not markdown.strip():
            raise UtteranceExtractionError("firecrawl scrape returned no markdown")
        user_prompt = _agent_user_prompt(markdown, scrape)

        agent = build_agent(
            settings,
            output_type=UtterancesPayload,
            system_prompt=EXTRACTOR_SYSTEM_PROMPT,
            name="vibecheck.utterance_extractor",
        )
        _register_tools(agent)
        deps = ExtractorDeps(scrape=scrape, scrape_cache=scrape_cache)

        model_name = google_vertex_model_name(
            settings.VERTEXAI_FAST_MODEL,
            setting_name="VERTEXAI_FAST_MODEL",
        )
        try:
            async with vertex_slot(settings):
                result = await run_vertex_agent_with_retry(agent, user_prompt, deps=deps)  # pyright: ignore[reportArgumentType]
        except Exception as exc:
            transient = classify_pydantic_ai_error(exc, model_name=model_name)
            if transient is not None:
                _set_upstream_span_attrs(span, transient)
                raise transient from exc
            raise UtteranceExtractionError(f"Gemini extraction failed: {exc}") from exc

        payload = cast(UtterancesPayload, cast(object, result.output))
        if not payload.utterances:
            raise ZeroUtterancesError(
                "Gemini returned 0 utterances despite passing pre-Gemini quality checks"
            )
        payload.source_url = url
        payload.scraped_at = datetime.now(UTC)
        _assign_stable_ids(payload)
        sanitized_html = await asyncio.to_thread(_sanitize_html, scrape.html or "")
        await asyncio.to_thread(attribute_media, sanitized_html, payload.utterances)
        return payload


def _set_upstream_span_attrs(
    span: logfire.LogfireSpan, transient: TransientExtractionError
) -> None:
    """Set neutral `upstream_*` attrs plus Vertex-arm legacy attrs.

    Saved Logfire searches keyed on `vertex_status_code` / `vertex_status`
    (from the original Vertex-only span shape) keep working for the Vertex
    arm; the Firecrawl arm only carries the neutral `upstream_*` keys.
    """
    span.set_attribute("upstream_provider", transient.provider)
    if transient.status_code is not None:
        span.set_attribute("upstream_status_code", transient.status_code)
    if transient.status is not None:
        span.set_attribute("upstream_status", transient.status)
    if transient.model_name is not None:
        span.set_attribute("model_name", transient.model_name)
    if transient.provider == "vertex":
        if transient.status_code is not None:
            span.set_attribute("vertex_status_code", transient.status_code)
        if transient.status is not None:
            span.set_attribute("vertex_status", transient.status)


def _sanitize_html(html: str) -> str:
    cleaned = strip_for_llm(html)
    return cleaned or ""


def _strip_markup(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value)).replace("\xa0", " ").strip()


def _is_coral_boilerplate_text(value: str) -> bool:
    text = re.sub(r"\s+", " ", value).strip()
    return (
        not text
        or re.fullmatch(r"All Comments?\(\d+\)", text, flags=re.IGNORECASE) is not None
        or text.lower() == "commenter"
        or "our comments are moderated" in text.lower()
        or "let's have a nice conversation" in text.lower()
        or "advocating violence" in text.lower()
    )


def _extract_attr_value(attrs: str, attr_name: str) -> str | None:
    match = re.search(
        rf"\b{re.escape(attr_name)}\s*=\s*[\"'](?P<value>[^\"']+)[\"']",
        attrs,
        flags=re.IGNORECASE,
    )
    return match.group("value").strip().lower() if match else None


def _has_real_coral_comment_article(marker_body: str) -> bool:
    for article_match in _CORAL_ARTICLE_RE.finditer(marker_body):
        article = article_match.group("body")
        header_match = _CORAL_HEADER_RE.search(article)
        paragraph_match = _CORAL_PARAGRAPH_RE.search(article)
        author = _strip_markup(header_match.group("value")) if header_match else ""
        text = _strip_markup(paragraph_match.group("value")) if paragraph_match else ""
        if not _is_coral_boilerplate_text(author) and not _is_coral_boilerplate_text(text):
            return True
    return False


def _coral_comments_prompt_addendum(scrape: CachedScrape) -> str | None:
    html_text = scrape.html or ""
    saw_marker = "data-coral-comments" in html_text or "data-coral-comments" in (
        scrape.markdown or ""
    )
    saw_shell_marker = False
    for match in _CORAL_MARKER_RE.finditer(html_text):
        attrs = f"{match.group('attrs')} {match.group('attrs_after')}"
        status = _extract_attr_value(attrs, "data-coral-status")
        body = match.group("body")
        if status == "copied":
            if _has_real_coral_comment_article(body):
                return CORAL_COMMENTS_PROMPT_ADDENDUM
            saw_shell_marker = True
        elif status in {"shell_only", "shadow_empty", "timeout", "clicked_no_match"}:
            saw_shell_marker = True
        elif status is None:
            return CORAL_COMMENTS_PROMPT_ADDENDUM

    if saw_shell_marker:
        return CORAL_COMMENTS_IGNORE_ADDENDUM
    if saw_marker:
        return CORAL_COMMENTS_PROMPT_ADDENDUM
    return None


def _agent_user_prompt(markdown: str, scrape: CachedScrape) -> str:
    addendum = _coral_comments_prompt_addendum(scrape)
    if addendum is None:
        return markdown
    return f"{addendum}\n\n{markdown}"


def _get_html_impl(deps: ExtractorDeps) -> str:
    """Return the scraped page's HTML with scripts/styles/links/comments stripped.

    Empty string (not None) when no HTML was captured so the agent always
    receives a string per the tool's declared return type.
    """
    html = deps.scrape.html or ""
    if not html:
        return ""
    return _sanitize_html(html)


async def _get_screenshot_impl(deps: ExtractorDeps) -> ImageUrl | None:
    """Return a freshly-signed 15-minute screenshot URL as an `ImageUrl`.

    Returns None when no screenshot was persisted. The agent's prompt tells
    it to proceed from markdown when the tool returns None; this is
    documented in the module docstring and the EXTRACTOR_SYSTEM_PROMPT.
    Re-signs on every call so stale URLs can't leak between tool
    invocations inside a single agent run.
    """
    signed = await deps.scrape_cache.signed_screenshot_url(deps.scrape)
    if not signed:
        return None
    return ImageUrl(url=signed)


def _register_tools(agent: Agent[None, UtterancesPayload]) -> None:
    """Attach `get_html` and `get_screenshot` tools to a built agent.

    Uses `agent.tool` decorator at construction time; tests swap in a fake
    agent that mirrors the decorator surface. The agent is typed with
    `AgentDepsT=None`, so the decorator sees `RunContext[None]` at the type
    level — the per-run `deps=` kwarg injects the real `ExtractorDeps`
    instance at call time.
    """

    @agent.tool  # pyright: ignore[reportArgumentType]
    async def get_html(ctx: RunContext[ExtractorDeps]) -> str:
        """Return the page's sanitized HTML. Prefer markdown; call at most once."""
        return await asyncio.to_thread(_get_html_impl, ctx.deps)

    @agent.tool  # pyright: ignore[reportArgumentType]
    async def get_screenshot(ctx: RunContext[ExtractorDeps]) -> ImageUrl | None:
        """Return a 15-minute signed screenshot URL. Call at most once."""
        return await _get_screenshot_impl(ctx.deps)

    _ = (get_html, get_screenshot)


async def _get_or_scrape(
    url: str,
    client: FirecrawlClient,
    scrape_cache: SupabaseScrapeCache,
    *,
    span: logfire.LogfireSpan | None = None,
) -> CachedScrape:
    """Cache-hit → return cached. Miss → Firecrawl multi-format + persist.

    Returns a `CachedScrape` in both branches so the caller (and downstream
    agent tools) always sees the Supabase `storage_key` attached at cache
    write or cache read time. On cache miss, the `put()` return value
    carries the newly minted key; when `put()` raises we fall back to a
    keyless `CachedScrape` wrapper over the fresh `ScrapeResult` so the
    agent tools at least observe the markdown/html payload — the screenshot
    tool will return None because there is no key to sign against.

    Firecrawl errors are classified via `classify_firecrawl_error`: a
    retriable status (429/5xx) or transport/timeout escape surfaces as
    `TransientExtractionError(provider="firecrawl")`; everything else
    becomes the terminal `UtteranceExtractionError`.
    """
    cached = await scrape_cache.get(url, tier="scrape")
    if cached is not None:
        return cached

    try:
        fresh = await client.scrape(
            url,
            formats=["markdown", "html", "screenshot@fullPage"],
            only_main_content=True,
        )
    except Exception as exc:
        transient = classify_firecrawl_error(exc)
        if transient is not None:
            if span is not None:
                _set_upstream_span_attrs(span, transient)
            raise transient from exc
        raise UtteranceExtractionError(f"firecrawl scrape failed: {exc}") from exc

    try:
        return await scrape_cache.put(url, fresh, tier="scrape")
    except Exception:
        # Best-effort: persistence failed (e.g. DB down) but we still have
        # the fresh bundle. Wrap it as a CachedScrape with no storage_key
        # so the type contract holds and get_screenshot() returns None.
        return CachedScrape(
            markdown=fresh.markdown,
            html=fresh.html,
            raw_html=fresh.raw_html,
            screenshot=fresh.screenshot,
            links=fresh.links,
            metadata=fresh.metadata,
            warning=fresh.warning,
            storage_key=None,
        )


def _assign_stable_ids(payload: UtterancesPayload) -> None:
    """Fill in missing/duplicate utterance_ids deterministically."""
    seen: set[str] = set()
    for i, utterance in enumerate(payload.utterances):
        uid = utterance.utterance_id
        if not uid or uid in seen:
            utterance.utterance_id = f"{utterance.kind}-{i}-{hash(utterance.text) & 0xFFFFFFFF:08x}"
        seen.add(utterance.utterance_id or "")
