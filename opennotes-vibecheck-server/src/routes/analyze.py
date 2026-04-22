"""POST /api/analyze — vibecheck orchestrator.

Fans out per-utterance and whole-conversation analyses, aggregates them into
a single `SidebarPayload`, caches the result for 72 hours, and returns. Per
the brief, an individual analysis failure populates its section with an empty
default — the whole request never 500s because one analysis raised.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.analyses.claims._claims_schemas import Claim, ClaimsReport
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.claims.dedupe import dedupe_claims
from src.analyses.claims.extract import extract_claims_bulk
from src.analyses.claims.known_misinfo import check_known_misinformation
from src.analyses.opinions._schemas import (
    OpinionsReport,
    SentimentStatsReport,
    SubjectiveClaim,
)
from src.analyses.opinions.sentiment import compute_sentiment_stats
from src.analyses.opinions.subjective import extract_subjective_claims_bulk
from src.analyses.safety._schemas import HarmfulContentMatch
from src.analyses.safety.moderation import check_content_moderation_bulk
from src.analyses.schemas import (
    FactsClaimsSection,
    OpinionsSection,
    SafetySection,
    SidebarPayload,
    ToneDynamicsSection,
)
from src.analyses.tone._flashpoint_schemas import FlashpointMatch
from src.analyses.tone._scd_schemas import SCDReport
from src.analyses.tone.flashpoint import detect_flashpoints_bulk
from src.analyses.tone.scd import analyze_scd
from src.cache.supabase_cache import SupabaseCache, normalize_url
from src.config import Settings, get_settings
from src.firecrawl_client import FirecrawlClient
from src.monitoring import get_logger
from src.services.flashpoint_service import (
    FlashpointDetectionService,
    get_flashpoint_service,
)
from src.services.openai_moderation import OpenAIModerationService
from src.utterances import Utterance, UtterancesPayload, extract_utterances

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["analyze"])


limiter = Limiter(key_func=get_remote_address)


class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="HTTP(S) URL of the page to analyze")


def _empty_scd_report() -> SCDReport:
    return SCDReport(
        summary="",
        tone_labels=[],
        per_speaker_notes={},
        insufficient_conversation=True,
    )


def _empty_sentiment_stats() -> SentimentStatsReport:
    return SentimentStatsReport(
        per_utterance=[],
        positive_pct=0.0,
        negative_pct=0.0,
        neutral_pct=0.0,
        mean_valence=0.0,
    )


async def _safe_moderation_bulk(
    utterances: list[Utterance],
    service: OpenAIModerationService | None,
) -> list[HarmfulContentMatch | None]:
    try:
        return await check_content_moderation_bulk(utterances, service)
    except Exception as exc:
        logger.warning("bulk moderation failed: %s", exc)
        return [None for _ in utterances]


async def _safe_flashpoint_bulk(
    utterances: list[Utterance], settings: Settings
) -> list[FlashpointMatch | None]:
    try:
        return await detect_flashpoints_bulk(utterances, settings)
    except Exception as exc:
        logger.warning("bulk flashpoint detection failed: %s", exc)
        return [None for _ in utterances]


async def _safe_extract_claims_bulk(
    utterances: list[Utterance], settings: Settings
) -> list[list[Claim]]:
    try:
        return await extract_claims_bulk(utterances, settings)
    except Exception as exc:
        logger.warning("bulk claim extraction failed: %s", exc)
        return [[] for _ in utterances]


async def _safe_scd(
    utterances: list[Utterance], settings: Settings
) -> SCDReport:
    try:
        return await analyze_scd(utterances, settings)
    except Exception as exc:
        logger.warning("scd analysis failed: %s", exc)
        return _empty_scd_report()


async def _safe_sentiment(
    utterances: list[Utterance], settings: Settings
) -> SentimentStatsReport:
    try:
        return await compute_sentiment_stats(utterances, settings=settings)
    except Exception as exc:
        logger.warning("sentiment analysis failed: %s", exc)
        return _empty_sentiment_stats()


async def _safe_subjective_bulk(
    utterances: list[Utterance], settings: Settings
) -> list[list[SubjectiveClaim]]:
    try:
        return await extract_subjective_claims_bulk(utterances, settings=settings)
    except Exception as exc:
        logger.warning("bulk subjective extraction failed: %s", exc)
        return [[] for _ in utterances]


async def _safe_known_misinfo(
    claim_text: str,
    *,
    httpx_client: httpx.AsyncClient,
) -> list[FactCheckMatch]:
    try:
        return await check_known_misinformation(claim_text, httpx_client=httpx_client)
    except Exception as exc:
        logger.warning("fact-check lookup failed for claim %r: %s", claim_text[:80], exc)
        return []


def _build_opinions_report(
    sentiment: SentimentStatsReport,
    subjective_lists: list[list[SubjectiveClaim]],
) -> OpinionsReport:
    flattened: list[SubjectiveClaim] = []
    for batch in subjective_lists:
        flattened.extend(batch)
    return OpinionsReport(sentiment_stats=sentiment, subjective_claims=flattened)


def _prior_context(utterances: list[Utterance], idx: int) -> list[Utterance]:
    return utterances[:idx]


def _get_cache(request: Request) -> SupabaseCache | None:
    """Return the configured cache if present.

    Accepts any object that quacks like `SupabaseCache` (async ``get`` +
    ``put``) so tests can substitute an in-memory double without having
    to subclass.
    """
    cache = getattr(request.app.state, "cache", None)
    if cache is None:
        return None
    if hasattr(cache, "get") and hasattr(cache, "put"):
        return cache
    return None


def _get_firecrawl_client(request: Request, settings: Settings) -> FirecrawlClient:
    client = getattr(request.app.state, "firecrawl_client", None)
    if isinstance(client, FirecrawlClient):
        return client
    return FirecrawlClient(api_key=settings.FIRECRAWL_API_KEY)


def _get_moderation_service(
    request: Request, settings: Settings
) -> OpenAIModerationService | None:
    service = getattr(request.app.state, "moderation_service", None)
    if isinstance(service, OpenAIModerationService):
        return service
    if not settings.OPENAI_API_KEY:
        return None
    return OpenAIModerationService(AsyncOpenAI(api_key=settings.OPENAI_API_KEY))


def _get_flashpoint_service(
    request: Request, settings: Settings
) -> FlashpointDetectionService | None:
    service = getattr(request.app.state, "flashpoint_service", None)
    if isinstance(service, FlashpointDetectionService):
        return service
    try:
        return get_flashpoint_service(settings=settings)
    except Exception as exc:
        logger.warning("flashpoint service init failed: %s", exc)
        return None


def _get_httpx_client(request: Request) -> httpx.AsyncClient | None:
    client = getattr(request.app.state, "httpx_client", None)
    if isinstance(client, httpx.AsyncClient):
        return client
    return None


async def _run_pipeline(
    payload: UtterancesPayload,
    *,
    settings: Settings,
    moderation_service: OpenAIModerationService | None,
    flashpoint_service: FlashpointDetectionService | None,
    httpx_client: httpx.AsyncClient | None,
) -> SidebarPayload:
    utterances = payload.utterances

    # Batched analyses: one LLM call each (no per-utterance bursts).
    moderation_task = _safe_moderation_bulk(utterances, moderation_service)
    claims_task = _safe_extract_claims_bulk(utterances, settings)
    subjective_task = _safe_subjective_bulk(utterances, settings)
    sentiment_task = _safe_sentiment(utterances, settings)
    scd_task = _safe_scd(utterances, settings)
    flashpoint_task = _safe_flashpoint_bulk(utterances, settings)

    (
        moderation_results,
        flashpoint_results,
        claims_per_utt,
        subjective_per_utt,
        sentiment_stats,
        scd_report,
    ) = await asyncio.gather(
        moderation_task,
        flashpoint_task,
        claims_task,
        subjective_task,
        sentiment_task,
        scd_task,
    )

    harmful: list[HarmfulContentMatch] = [m for m in moderation_results if m is not None]
    flashpoint_matches: list[FlashpointMatch] = [
        m for m in flashpoint_results if m is not None
    ]

    flat_claims: list[Claim] = []
    for batch in claims_per_utt:
        flat_claims.extend(batch)

    try:
        claims_report = await dedupe_claims(flat_claims, utterances, settings)
    except Exception as exc:
        logger.warning("claim dedupe failed: %s", exc)
        claims_report = ClaimsReport(
            deduped_claims=[],
            total_claims=len(flat_claims),
            total_unique=0,
        )

    known_misinfo: list[FactCheckMatch] = []
    if claims_report.deduped_claims:
        own_httpx = httpx_client is None
        client = httpx_client or httpx.AsyncClient()
        try:
            results = await asyncio.gather(
                *(
                    _safe_known_misinfo(claim.canonical_text, httpx_client=client)
                    for claim in claims_report.deduped_claims
                )
            )
        finally:
            if own_httpx:
                await client.aclose()
        for matches in results:
            known_misinfo.extend(matches)

    opinions_report = _build_opinions_report(sentiment_stats, subjective_per_utt)

    return SidebarPayload(
        source_url=payload.source_url,
        page_title=payload.page_title,
        page_kind=payload.page_kind,
        scraped_at=payload.scraped_at,
        cached=False,
        safety=SafetySection(harmful_content_matches=harmful),
        tone_dynamics=ToneDynamicsSection(
            scd=scd_report,
            flashpoint_matches=flashpoint_matches,
        ),
        facts_claims=FactsClaimsSection(
            claims_report=claims_report,
            known_misinformation=known_misinfo,
        ),
        opinions_sentiments=OpinionsSection(opinions_report=opinions_report),
    )


def _coerce_cached_payload(raw: dict[str, Any]) -> SidebarPayload:
    payload = SidebarPayload.model_validate(raw)
    return payload.model_copy(update={"cached": True})


def _rate_limit_value() -> str:
    return f"{get_settings().RATE_LIMIT_PER_IP_PER_HOUR}/hour"


@router.post("/analyze", response_model=SidebarPayload)
@limiter.limit(_rate_limit_value)
async def analyze(
    request: Request,
    body: AnalyzeRequest,
) -> SidebarPayload:
    settings = get_settings()

    if not body.url:
        raise HTTPException(status_code=400, detail="url is required")

    try:
        normalized = normalize_url(body.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid url: {exc}") from exc

    cache = _get_cache(request)
    if cache is not None:
        cached_raw = await cache.get(normalized)
        if cached_raw is not None:
            try:
                return _coerce_cached_payload(cached_raw)
            except Exception as exc:
                logger.warning(
                    "cached payload failed validation (%s); regenerating", exc
                )

    firecrawl_client = _get_firecrawl_client(request, settings)
    try:
        utterances_payload = await extract_utterances(normalized, firecrawl_client)
    except Exception as exc:
        logger.warning("utterance extraction failed for %s: %s", normalized, exc)
        raise HTTPException(
            status_code=502, detail="Failed to extract utterances from URL"
        ) from exc

    moderation_service = _get_moderation_service(request, settings)
    flashpoint_service = _get_flashpoint_service(request, settings)
    httpx_client = _get_httpx_client(request)

    sidebar = await _run_pipeline(
        utterances_payload,
        settings=settings,
        moderation_service=moderation_service,
        flashpoint_service=flashpoint_service,
        httpx_client=httpx_client,
    )

    if cache is not None:
        try:
            await cache.put(normalized, sidebar.model_dump(mode="json"))
        except Exception as exc:
            logger.warning("cache put failed for %s: %s", normalized, exc)

    return sidebar


__all__ = ["AnalyzeRequest", "limiter", "router"]
