from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID, uuid4

from dbos import DBOS
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, update

from src.database import get_session_maker
from src.dbos_workflows.token_bucket.config import WorkflowWeight
from src.dbos_workflows.token_bucket.gate import TokenGate
from src.url_content_scan.analyses.claims import run_claims_dedup, run_known_misinfo
from src.url_content_scan.analyses.opinions import run_sentiment, run_subjective
from src.url_content_scan.analyses.safety import (
    run_image_moderation,
    run_safety_moderation,
    run_video_moderation,
    run_web_risk,
)
from src.url_content_scan.analyses.tone import run_flashpoint, run_scd
from src.url_content_scan.claims_schemas import ClaimsReport
from src.url_content_scan.models import UrlScanSectionSlot
from src.url_content_scan.opinions_schemas import SentimentStatsReport
from src.url_content_scan.schemas import PageKind, SectionSlug
from src.utils.async_compat import run_sync


@dataclass(slots=True)
class UrlScanWorkflowInputs:
    utterances: list[Any] = field(default_factory=list)
    page_url: str | None = None
    mentioned_urls: list[str] = field(default_factory=list)
    media_urls: list[str] = field(default_factory=list)
    mentioned_images: list[Any] = field(default_factory=list)
    mentioned_videos: list[Any] = field(default_factory=list)
    page_kind: PageKind = PageKind.OTHER
    moderation_service: Any | None = None
    web_risk_session: Any | None = None
    web_risk_client: Any | None = None
    web_risk_lookup_cache: dict[str, Any] | None = None
    image_fetch_bytes: Any | None = None
    image_safe_search: Any | None = None
    image_content_cache: dict[str, Any] | None = None
    video_sample_video: Any | None = None
    video_safe_search: Any | None = None
    video_frame_cache: dict[str, Any] | None = None
    flashpoint_service: Any | None = None
    flashpoint_max_context: int | None = None
    flashpoint_score_threshold: int | None = None
    flashpoint_max_concurrency: int = 8
    claims_extract_claims: Any | None = None
    claims_embed_texts: Any | None = None
    claims_similarity_threshold: float = 0.85
    claims_max_concurrency: int = 8
    known_misinfo_lookup: Any | None = None
    sentiment_classify_sentiment: Any | None = None
    sentiment_max_concurrency: int = 8
    subjective_extract_subjective_claims: Any | None = None
    subjective_max_concurrency: int = 8
    claims_report: ClaimsReport | None = None
    sentiment_stats: SentimentStatsReport | None = None


async def _run_safety_moderation_section(inputs: UrlScanWorkflowInputs) -> Any:
    return await run_safety_moderation(
        inputs.utterances,
        moderation_service=inputs.moderation_service,
    )


async def _run_web_risk_section(inputs: UrlScanWorkflowInputs) -> Any:
    if not inputs.page_url:
        raise ValueError("page_url is required for safety__web_risk")
    return await run_web_risk(
        page_url=inputs.page_url,
        mentioned_urls=inputs.mentioned_urls,
        media_urls=inputs.media_urls,
        session=inputs.web_risk_session,
        web_risk_client=inputs.web_risk_client,
        lookup_cache=inputs.web_risk_lookup_cache,
    )


async def _run_image_moderation_section(inputs: UrlScanWorkflowInputs) -> Any:
    return await run_image_moderation(
        inputs.mentioned_images,
        fetch_bytes=inputs.image_fetch_bytes,
        safe_search=inputs.image_safe_search,
        content_cache=inputs.image_content_cache,
    )


async def _run_video_moderation_section(inputs: UrlScanWorkflowInputs) -> Any:
    return await run_video_moderation(
        inputs.mentioned_videos,
        sample_video=inputs.video_sample_video,
        safe_search=inputs.video_safe_search,
        frame_cache=inputs.video_frame_cache,
    )


async def _run_flashpoint_section(inputs: UrlScanWorkflowInputs) -> Any:
    return await run_flashpoint(
        inputs.utterances,
        service=inputs.flashpoint_service,
        max_context=inputs.flashpoint_max_context,
        score_threshold=inputs.flashpoint_score_threshold,
        max_concurrency=inputs.flashpoint_max_concurrency,
        page_kind=inputs.page_kind,
    )


async def _run_scd_section(inputs: UrlScanWorkflowInputs) -> Any:
    return await run_scd(inputs.utterances)


async def _run_claims_dedup_section(inputs: UrlScanWorkflowInputs) -> Any:
    if inputs.claims_embed_texts is None:
        raise ValueError("claims_embed_texts is required for facts_claims__dedup")
    return await run_claims_dedup(
        inputs.utterances,
        extract_claims=inputs.claims_extract_claims,
        embed_texts=inputs.claims_embed_texts,
        similarity_threshold=inputs.claims_similarity_threshold,
        max_concurrency=inputs.claims_max_concurrency,
    )


async def _run_known_misinfo_section(inputs: UrlScanWorkflowInputs) -> Any:
    if inputs.claims_report is None:
        raise ValueError("claims_report is required for facts_claims__known_misinfo")
    if inputs.known_misinfo_lookup is None:
        raise ValueError("known_misinfo_lookup is required for facts_claims__known_misinfo")
    return await run_known_misinfo(
        inputs.claims_report,
        lookup=inputs.known_misinfo_lookup,
    )


async def _run_sentiment_section(inputs: UrlScanWorkflowInputs) -> Any:
    return await run_sentiment(
        inputs.utterances,
        classify_sentiment=inputs.sentiment_classify_sentiment,
        max_concurrency=inputs.sentiment_max_concurrency,
    )


async def _run_subjective_section(inputs: UrlScanWorkflowInputs) -> Any:
    return await run_subjective(
        inputs.utterances,
        extract_subjective_claims=inputs.subjective_extract_subjective_claims,
        max_concurrency=inputs.subjective_max_concurrency,
        sentiment_stats=inputs.sentiment_stats,
    )


_SECTION_RUNNERS = {
    SectionSlug.SAFETY_MODERATION: _run_safety_moderation_section,
    SectionSlug.SAFETY_WEB_RISK: _run_web_risk_section,
    SectionSlug.SAFETY_IMAGE_MODERATION: _run_image_moderation_section,
    SectionSlug.SAFETY_VIDEO_MODERATION: _run_video_moderation_section,
    SectionSlug.TONE_DYNAMICS_FLASHPOINT: _run_flashpoint_section,
    SectionSlug.TONE_DYNAMICS_SCD: _run_scd_section,
    SectionSlug.FACTS_CLAIMS_DEDUP: _run_claims_dedup_section,
    SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO: _run_known_misinfo_section,
    SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT: _run_sentiment_section,
    SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE: _run_subjective_section,
}


async def _load_section_payload_async(job_id: UUID, slug: SectionSlug) -> Any:
    async with get_session_maker()() as session:
        result = await session.execute(
            select(UrlScanSectionSlot.data).where(
                UrlScanSectionSlot.job_id == job_id,
                UrlScanSectionSlot.slug == slug.value,
            )
        )
        return result.scalar_one_or_none()


async def _update_slot_running_async(job_id: UUID, slug: SectionSlug, attempt_id: UUID) -> bool:
    async with get_session_maker()() as session:
        result = await session.execute(
            update(UrlScanSectionSlot)
            .where(
                UrlScanSectionSlot.job_id == job_id,
                UrlScanSectionSlot.slug == slug.value,
                UrlScanSectionSlot.attempt_id == attempt_id,
            )
            .values(
                state="RUNNING",
                data=None,
                error_code=None,
                error_message=None,
                started_at=func.now(),
                finished_at=None,
            )
        )
        await session.commit()
        return bool(result.rowcount)


async def _update_slot_done_async(
    job_id: UUID,
    slug: SectionSlug,
    attempt_id: UUID,
    payload: Any,
) -> bool:
    async with get_session_maker()() as session:
        result = await session.execute(
            update(UrlScanSectionSlot)
            .where(
                UrlScanSectionSlot.job_id == job_id,
                UrlScanSectionSlot.slug == slug.value,
                UrlScanSectionSlot.attempt_id == attempt_id,
            )
            .values(
                state="DONE",
                data=payload,
                error_code=None,
                error_message=None,
                finished_at=func.now(),
            )
        )
        await session.commit()
        return bool(result.rowcount)


async def _update_slot_failed_async(
    job_id: UUID,
    slug: SectionSlug,
    attempt_id: UUID,
    error_message: str,
    *,
    error_code: str = "section_failure",
) -> bool:
    async with get_session_maker()() as session:
        result = await session.execute(
            update(UrlScanSectionSlot)
            .where(
                UrlScanSectionSlot.job_id == job_id,
                UrlScanSectionSlot.slug == slug.value,
                UrlScanSectionSlot.attempt_id == attempt_id,
            )
            .values(
                state="FAILED",
                error_code=error_code,
                error_message=error_message,
                finished_at=func.now(),
            )
        )
        await session.commit()
        return bool(result.rowcount)


async def _rotate_slot_attempt_async(job_id: UUID, slug: SectionSlug) -> UUID:
    new_attempt_id = uuid4()
    async with get_session_maker()() as session:
        result = await session.execute(
            update(UrlScanSectionSlot)
            .where(
                UrlScanSectionSlot.job_id == job_id,
                UrlScanSectionSlot.slug == slug.value,
            )
            .values(
                attempt_id=new_attempt_id,
                state="PENDING",
                data=None,
                error_code=None,
                error_message=None,
                started_at=None,
                finished_at=None,
            )
        )
        if result.rowcount != 1:
            await session.rollback()
            raise ValueError(f"expected exactly one slot row for {job_id}:{slug.value}")
        await session.commit()
    return new_attempt_id


@DBOS.step()
def load_url_scan_section_payload_step(job_id: str, slug: str) -> Any:
    return run_sync(_load_section_payload_async(UUID(job_id), SectionSlug(slug)))


@DBOS.step()
def mark_url_scan_section_running_step(job_id: str, slug: str, attempt_id: str) -> bool:
    return run_sync(_update_slot_running_async(UUID(job_id), SectionSlug(slug), UUID(attempt_id)))


@DBOS.step()
def complete_url_scan_section_step(job_id: str, slug: str, attempt_id: str, payload: Any) -> bool:
    return run_sync(
        _update_slot_done_async(UUID(job_id), SectionSlug(slug), UUID(attempt_id), payload)
    )


@DBOS.step()
def fail_url_scan_section_step(
    job_id: str,
    slug: str,
    attempt_id: str,
    error_message: str,
    *,
    error_code: str = "section_failure",
) -> bool:
    return run_sync(
        _update_slot_failed_async(
            UUID(job_id),
            SectionSlug(slug),
            UUID(attempt_id),
            error_message,
            error_code=error_code,
        )
    )


@DBOS.step()
def rotate_url_scan_section_attempt_step(job_id: str, slug: str) -> str:
    return str(run_sync(_rotate_slot_attempt_async(UUID(job_id), SectionSlug(slug))))


def _hydrate_section_inputs(
    job_id: str,
    slug: SectionSlug,
    section_inputs: UrlScanWorkflowInputs,
) -> UrlScanWorkflowInputs:
    hydrated = section_inputs
    if slug is SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO and hydrated.claims_report is None:
        payload = load_url_scan_section_payload_step(job_id, SectionSlug.FACTS_CLAIMS_DEDUP.value)
        if payload is None:
            raise ValueError("facts_claims__dedup payload is required for known-misinfo retries")
        hydrated = replace(hydrated, claims_report=ClaimsReport.model_validate(payload))
    if slug is SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE and hydrated.sentiment_stats is None:
        payload = load_url_scan_section_payload_step(
            job_id, SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT.value
        )
        if payload is None:
            raise ValueError(
                "opinions_sentiments__sentiment payload is required for subjective retries"
            )
        hydrated = replace(
            hydrated,
            sentiment_stats=SentimentStatsReport.model_validate(payload),
        )
    return hydrated


async def _execute_url_scan_section(
    slug: SectionSlug,
    section_inputs: UrlScanWorkflowInputs,
) -> Any:
    try:
        runner = _SECTION_RUNNERS[slug]
    except KeyError as exc:
        raise ValueError(f"unsupported url scan section slug: {slug.value}") from exc
    return await runner(section_inputs)


def _serialize_section_payload(payload: Any) -> Any:
    return jsonable_encoder(payload)


@DBOS.workflow()
def url_scan_section_workflow(
    job_id: str,
    section_slug: str,
    attempt_id: str,
    section_inputs: UrlScanWorkflowInputs,
    *,
    parent_holds_token: bool = False,
) -> dict[str, Any]:
    slug = SectionSlug(section_slug)
    gate = TokenGate(
        pool="default",
        weight=WorkflowWeight.URL_SCAN,
        parent_holds_token=parent_holds_token,
    )
    gate.acquire()
    try:
        if not mark_url_scan_section_running_step(job_id, slug.value, attempt_id):
            return {"status": "superseded", "job_id": job_id, "slug": slug.value}

        hydrated_inputs = _hydrate_section_inputs(job_id, slug, section_inputs)
        try:
            result = run_sync(_execute_url_scan_section(slug, hydrated_inputs))
        except Exception as exc:
            fail_url_scan_section_step(job_id, slug.value, attempt_id, str(exc))
            raise

        serialized = _serialize_section_payload(result)
        if not complete_url_scan_section_step(job_id, slug.value, attempt_id, serialized):
            return {"status": "superseded", "job_id": job_id, "slug": slug.value}

        return {
            "status": "done",
            "job_id": job_id,
            "slug": slug.value,
            "attempt_id": attempt_id,
        }
    finally:
        gate.release()
