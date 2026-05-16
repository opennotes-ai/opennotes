from __future__ import annotations

import base64
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from dbos import DBOS, Queue, SetEnqueueOptions, SetWorkflowID
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select, update

from src.batch_jobs.schemas import BatchJobStatus
from src.database import get_session_maker
from src.dbos_workflows.content_monitoring_workflows import _get_llm_service
from src.dbos_workflows.enqueue_utils import safe_enqueue, safe_enqueue_sync
from src.dbos_workflows.token_bucket.config import WorkflowWeight
from src.dbos_workflows.token_bucket.gate import TokenGate
from src.fact_checking.embedding_service import EmbeddingService
from src.services.firecrawl_client import (
    FirecrawlBlocked,
    FirecrawlClient,
    FirecrawlError,
    ScrapeResult,
)
from src.url_content_scan.analyses.claims import run_claims_dedup, run_known_misinfo
from src.url_content_scan.analyses.claims.known_misinfo import EmbeddingServiceKnownMisinfoAdapter
from src.url_content_scan.analyses.opinions import run_sentiment, run_subjective
from src.url_content_scan.analyses.safety import (
    run_image_moderation,
    run_safety_moderation,
    run_safety_recommendation,
    run_video_moderation,
    run_web_risk,
)
from src.url_content_scan.analyses.tone import run_flashpoint, run_scd
from src.url_content_scan.claims_schemas import ClaimsReport, FactCheckMatch
from src.url_content_scan.models import (
    UrlScanSectionSlot,
    UrlScanSidebarCache,
    UrlScanState,
    UrlScanUtterance,
)
from src.url_content_scan.normalize import canonical_cache_key
from src.url_content_scan.opinions_schemas import SentimentStatsReport, SubjectiveClaim
from src.url_content_scan.safety_schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.url_content_scan.schemas import (
    ErrorCode,
    FactsClaimsSection,
    ImageModerationSection,
    OpinionsSection,
    PageKind,
    SafetySection,
    SectionSlug,
    SidebarPayload,
    ToneDynamicsSection,
    UtteranceAnchor,
    VideoModerationSection,
    WebRiskSection,
)
from src.url_content_scan.scrape_cache import ScrapeCache
from src.url_content_scan.screenshot_store import ScreenshotStore
from src.url_content_scan.tone_schemas import FlashpointMatch, SCDReport
from src.url_content_scan.utterances.extractor import extract_utterances
from src.url_content_scan.utterances.schema import Utterance, UtterancesPayload
from src.utils.async_compat import run_sync
from src.utils.url_security import InvalidURL, validate_public_http_url

from .batch_job_helpers import start_batch_job_sync

url_scan_queue = Queue(
    name="url_scan",
    worker_concurrency=4,
    concurrency=8,
)
url_scan_section_queue = Queue(
    name="url_scan_section",
    worker_concurrency=10,
    concurrency=20,
)

_SCRAPE_FORMATS = ["markdown", "html", "screenshot@fullPage"]
_SIDEBAR_CACHE_TTL = timedelta(hours=24)
_SLOT_JOIN_POLL_SECONDS = 1
_MAX_SLOT_JOIN_POLLS = 300
_REQUIRED_SIDEBAR_SLOTS = frozenset(
    {
        SectionSlug.SAFETY_MODERATION.value,
        SectionSlug.TONE_DYNAMICS_SCD.value,
        SectionSlug.FACTS_CLAIMS_DEDUP.value,
        SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT.value,
    }
)


class UrlScanWorkflowError(RuntimeError):
    def __init__(
        self,
        error_code: ErrorCode | str,
        message: str,
        *,
        error_host: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code.value if isinstance(error_code, ErrorCode) else error_code
        self.error_host = error_host


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
    community_server_id: str | None = None
    community_server_uuid: str | None = None
    dataset_tags: list[str] = field(default_factory=list)


class _NoopScreenshotStore:
    async def upload(self, storage_key: str, _screenshot_bytes: bytes) -> str:
        return storage_key

    async def delete(self, _storage_key: str) -> None:
        return None

    async def sign_url(self, _storage_key: str, *, _ttl: timedelta) -> str | None:
        return None


def _community_server_uuid(inputs: UrlScanWorkflowInputs) -> UUID | None:
    if not inputs.community_server_uuid:
        return None
    return UUID(inputs.community_server_uuid)


async def _default_claims_embed_texts(
    texts: list[str],
    inputs: UrlScanWorkflowInputs,
) -> list[list[float]]:
    if not inputs.community_server_id:
        raise ValueError("community_server_id is required for facts_claims__dedup")

    llm_service = _get_llm_service()
    embedding_service = EmbeddingService(llm_service)
    community_server_uuid = _community_server_uuid(inputs)

    async with get_session_maker()() as session:
        embeddings: list[list[float]] = []
        for text in texts:
            embeddings.append(
                await embedding_service.generate_embedding(
                    session,
                    text,
                    community_server_id=inputs.community_server_id,
                    community_server_uuid=community_server_uuid,
                    input_type="document",
                )
            )
        return embeddings


def _screenshot_store_from_settings() -> ScreenshotStore | _NoopScreenshotStore:
    from src.config import get_settings

    settings = get_settings()
    if not settings.URL_SCAN_SCREENSHOT_BUCKET:
        return _NoopScreenshotStore()
    return ScreenshotStore.from_settings()


def _decode_screenshot_bytes(screenshot: str | None) -> bytes | None:
    if not screenshot or not screenshot.startswith("data:image/"):
        return None
    _header, _sep, payload = screenshot.partition(",")
    if not payload:
        return None
    return base64.b64decode(payload)


def _workflow_handle_id(handle: Any) -> str:
    workflow_id = getattr(handle, "workflow_id", None)
    if isinstance(workflow_id, str):
        return workflow_id
    get_workflow_id = getattr(handle, "get_workflow_id", None)
    if callable(get_workflow_id):
        return str(get_workflow_id())
    if isinstance(handle, str):
        return handle
    raise TypeError("DBOS enqueue handle did not expose a workflow id")


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
    embed_texts = inputs.claims_embed_texts
    if embed_texts is None:

        async def embed_texts(texts: list[str]) -> list[list[float]]:
            return await _default_claims_embed_texts(texts, inputs)

    return await run_claims_dedup(
        inputs.utterances,
        extract_claims=inputs.claims_extract_claims,
        embed_texts=embed_texts,
        similarity_threshold=inputs.claims_similarity_threshold,
        max_concurrency=inputs.claims_max_concurrency,
    )


async def _run_known_misinfo_section(inputs: UrlScanWorkflowInputs) -> Any:
    if inputs.claims_report is None:
        raise ValueError("claims_report is required for facts_claims__known_misinfo")
    lookup = inputs.known_misinfo_lookup
    if lookup is None:
        if not inputs.community_server_id:
            raise ValueError("community_server_id is required for facts_claims__known_misinfo")
        llm_service = _get_llm_service()
        embedding_service = EmbeddingService(llm_service)
        lookup = EmbeddingServiceKnownMisinfoAdapter(
            embedding_service=embedding_service,
            db=None,
            community_server_id=inputs.community_server_id,
            community_server_uuid=_community_server_uuid(inputs),
            dataset_tags=list(inputs.dataset_tags),
        )
        async with get_session_maker()() as session:
            lookup.db = session
            return await run_known_misinfo(
                inputs.claims_report,
                lookup=lookup,
            )
    return await run_known_misinfo(
        inputs.claims_report,
        lookup=lookup,
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


async def _rotate_slot_attempt_async(
    job_id: UUID,
    slug: SectionSlug,
    attempt_id: UUID | None = None,
) -> UUID:
    new_attempt_id = attempt_id or uuid4()
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


async def _touch_heartbeat_async(job_id: UUID, attempt_id: UUID) -> bool:
    async with get_session_maker()() as session:
        result = await session.execute(
            update(UrlScanState)
            .where(
                UrlScanState.job_id == job_id,
                UrlScanState.attempt_id == attempt_id,
            )
            .values(heartbeat_at=func.now())
        )
        await session.commit()
        return bool(result.rowcount)


async def _set_workflow_id_async(job_id: UUID, workflow_id: str) -> bool:
    from src.batch_jobs.service import BatchJobService

    async with get_session_maker()() as session:
        service = BatchJobService(session)
        job = await service.get_job(job_id)
        if job is None:
            return False
        job.workflow_id = workflow_id
        await session.commit()
        return True


async def _transition_batch_job_async(
    job_id: UUID,
    status: BatchJobStatus,
    *,
    total_tasks: int | None = None,
) -> bool:
    from src.batch_jobs.service import BatchJobService

    async with get_session_maker()() as session:
        service = BatchJobService(session)
        job = await service.get_job(job_id)
        if job is None:
            return False
        if total_tasks is not None:
            job.total_tasks = total_tasks
        if job.status == status.value:
            await session.commit()
            return True
        await service.transition_job_status(job_id, status)
        await session.commit()
        return True


async def _load_batch_job_context_async(job_id: UUID) -> dict[str, Any]:
    from src.batch_jobs.models import BatchJob

    async with get_session_maker()() as session:
        result = await session.execute(select(BatchJob.metadata_).where(BatchJob.id == job_id))
        metadata = result.scalar_one_or_none() or {}
        if not isinstance(metadata, dict):
            return {}
        return metadata


async def _upsert_utterances_async(
    job_id: UUID,
    attempt_id: UUID,
    payload: UtterancesPayload,
) -> bool:
    async with get_session_maker()() as session:
        state_result = await session.execute(
            select(UrlScanState.attempt_id).where(UrlScanState.job_id == job_id)
        )
        current_attempt = state_result.scalar_one_or_none()
        if current_attempt != attempt_id:
            await session.rollback()
            return False

        await session.execute(delete(UrlScanUtterance).where(UrlScanUtterance.job_id == job_id))
        for index, utterance in enumerate(payload.utterances):
            utterance_id = utterance.utterance_id or f"utt-{index}"
            session.add(
                UrlScanUtterance(
                    job_id=job_id,
                    utterance_id=utterance_id,
                    payload=jsonable_encoder(
                        utterance.model_copy(update={"utterance_id": utterance_id})
                    ),
                )
            )

        await session.execute(
            update(UrlScanState)
            .where(
                UrlScanState.job_id == job_id,
                UrlScanState.attempt_id == attempt_id,
            )
            .values(
                page_title=payload.page_title,
                page_kind=payload.page_kind.value,
                utterance_count=len(payload.utterances),
                heartbeat_at=func.now(),
            )
        )
        await session.commit()
        return True


async def _load_slot_attempts_async(job_id: UUID) -> dict[str, str]:
    async with get_session_maker()() as session:
        result = await session.execute(
            select(UrlScanSectionSlot.slug, UrlScanSectionSlot.attempt_id).where(
                UrlScanSectionSlot.job_id == job_id
            )
        )
        return {slug: str(attempt_id) for slug, attempt_id in result.all()}


async def _load_slot_results_async(job_id: UUID) -> dict[str, Any]:
    async with get_session_maker()() as session:
        result = await session.execute(
            select(
                UrlScanSectionSlot.slug,
                UrlScanSectionSlot.state,
                UrlScanSectionSlot.attempt_id,
                UrlScanSectionSlot.data,
                UrlScanSectionSlot.error_code,
                UrlScanSectionSlot.error_message,
                UrlScanSectionSlot.started_at,
                UrlScanSectionSlot.finished_at,
            ).where(UrlScanSectionSlot.job_id == job_id)
        )
        slots: dict[str, Any] = {}
        done_count = 0
        failed_count = 0
        for row in result.all():
            state = row.state.upper()
            if state == "DONE":
                done_count += 1
            elif state == "FAILED":
                failed_count += 1
            slots[row.slug] = {
                "state": state,
                "attempt_id": str(row.attempt_id),
                "data": row.data,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
        all_terminal = bool(slots) and all(
            slot["state"] in {"DONE", "FAILED"} for slot in slots.values()
        )
        return {
            "slots": slots,
            "done_count": done_count,
            "failed_count": failed_count,
            "all_terminal": all_terminal,
        }


async def _validate_url_scan_rows_async(job_id: UUID, attempt_id: UUID) -> bool:
    async with get_session_maker()() as session:
        state = await session.get(UrlScanState, job_id)
        if state is None or state.attempt_id != attempt_id or state.finished_at is not None:
            return False
        result = await session.execute(
            select(UrlScanSectionSlot.slug).where(UrlScanSectionSlot.job_id == job_id)
        )
        existing_slugs = {slug for (slug,) in result.all()}
        return existing_slugs == {slug.value for slug in SectionSlug}


async def _fail_nonterminal_slots_async(job_id: UUID, attempt_id: UUID, error_message: str) -> int:
    async with get_session_maker()() as session:
        result = await session.execute(
            update(UrlScanSectionSlot)
            .where(
                UrlScanSectionSlot.job_id == job_id,
                UrlScanSectionSlot.attempt_id == attempt_id,
                UrlScanSectionSlot.state.not_in(("DONE", "FAILED")),
            )
            .values(
                state="FAILED",
                error_code=ErrorCode.TIMEOUT.value,
                error_message=error_message,
                finished_at=func.now(),
            )
        )
        await session.commit()
        return int(result.rowcount or 0)


async def _load_state_async(job_id: UUID) -> UrlScanState | None:
    async with get_session_maker()() as session:
        return await session.get(UrlScanState, job_id)


def _slot_unavailable_inputs(slot_results: dict[str, Any], slugs: list[SectionSlug]) -> list[str]:
    unavailable: list[str] = []
    slots = slot_results.get("slots", {})
    for slug in slugs:
        slot = slots.get(slug.value)
        if slot is None or slot.get("state") != "DONE":
            unavailable.append(slug.value)
    return unavailable


def _build_sidebar_payload(
    *,
    source_url: str,
    page_title: str | None,
    page_kind: PageKind,
    utterances: list[Utterance],
    scraped_at: str,
    slot_payloads: dict[str, Any],
    recommendation_payload: dict[str, Any] | None,
    headline_payload: dict[str, Any] | None,
) -> SidebarPayload | None:
    if any(slug not in slot_payloads for slug in _REQUIRED_SIDEBAR_SLOTS):
        return None

    safety_matches = [
        HarmfulContentMatch.model_validate(item)
        for item in slot_payloads[SectionSlug.SAFETY_MODERATION.value].get(
            "harmful_content_matches", []
        )
    ]
    recommendation = (
        SafetyRecommendation.model_validate(recommendation_payload)
        if recommendation_payload is not None
        else None
    )
    flashpoint_matches = [
        FlashpointMatch.model_validate(item)
        for item in slot_payloads.get(SectionSlug.TONE_DYNAMICS_FLASHPOINT.value, [])
    ]
    scd = SCDReport.model_validate(slot_payloads[SectionSlug.TONE_DYNAMICS_SCD.value])
    claims_report = ClaimsReport.model_validate(slot_payloads[SectionSlug.FACTS_CLAIMS_DEDUP.value])
    known_misinformation = slot_payloads.get(SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO.value, [])
    sentiment_stats = SentimentStatsReport.model_validate(
        slot_payloads[SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT.value]
    )
    subjective_claims = slot_payloads.get(SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE.value, [])

    return SidebarPayload(
        source_url=source_url,
        page_title=page_title,
        page_kind=page_kind,
        scraped_at=datetime.fromisoformat(scraped_at),
        safety=SafetySection(
            harmful_content_matches=safety_matches,
            recommendation=recommendation,
        ),
        tone_dynamics=ToneDynamicsSection(
            scd=scd,
            flashpoint_matches=flashpoint_matches,
        ),
        facts_claims=FactsClaimsSection(
            claims_report=claims_report,
            known_misinformation=known_misinformation,
        ),
        opinions_sentiments=OpinionsSection(
            opinions_report={
                "sentiment_stats": sentiment_stats,
                "subjective_claims": subjective_claims,
            }
        ),
        web_risk=WebRiskSection(
            findings=[
                WebRiskFinding.model_validate(item)
                for item in slot_payloads.get(SectionSlug.SAFETY_WEB_RISK.value, {}).get(
                    "findings", []
                )
            ]
        ),
        image_moderation=ImageModerationSection(
            matches=[
                ImageModerationMatch.model_validate(item)
                for item in slot_payloads.get(SectionSlug.SAFETY_IMAGE_MODERATION.value, {}).get(
                    "matches", []
                )
            ]
        ),
        video_moderation=VideoModerationSection(
            matches=[
                VideoModerationMatch.model_validate(item)
                for item in slot_payloads.get(SectionSlug.SAFETY_VIDEO_MODERATION.value, {}).get(
                    "matches", []
                )
            ]
        ),
        headline=headline_payload,
        utterances=[
            UtteranceAnchor(
                position=index + 1,
                utterance_id=utterance.utterance_id or f"utt-{index}",
            )
            for index, utterance in enumerate(utterances)
        ],
    )


def _terminal_batch_status_for_results(
    *,
    done_count: int,
    failed_count: int,
    total_slots: int,
    fatal_error_code: str | None,
) -> str:
    if fatal_error_code is not None:
        return BatchJobStatus.FAILED.value
    if failed_count == 0 and done_count == total_slots:
        return BatchJobStatus.COMPLETED.value
    if done_count > 0:
        return BatchJobStatus.PARTIAL.value
    return BatchJobStatus.FAILED.value


def _needs_error_summary(
    *,
    failed_slots: dict[str, Any],
    fatal_error_code: str | None,
    safety_result: dict[str, Any] | None,
    headline_result: dict[str, Any] | None,
) -> bool:
    return bool(
        failed_slots
        or fatal_error_code
        or (safety_result or {}).get("error")
        or (headline_result or {}).get("error")
    )


def _build_error_summary(
    *,
    slot_results: dict[str, Any],
    fatal_error_code: str | None,
    fatal_error_message: str | None,
    safety_result: dict[str, Any] | None,
    headline_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    failed_slots = {
        slug: {
            "error_code": slot.get("error_code"),
            "error_message": slot.get("error_message"),
        }
        for slug, slot in slot_results.get("slots", {}).items()
        if slot.get("state") == "FAILED"
    }
    if not _needs_error_summary(
        failed_slots=failed_slots,
        fatal_error_code=fatal_error_code,
        safety_result=safety_result,
        headline_result=headline_result,
    ):
        return None

    error_summary: dict[str, Any] = {}
    if fatal_error_code:
        error_summary["error_code"] = fatal_error_code
        error_summary["error_message"] = fatal_error_message or fatal_error_code
    if failed_slots:
        error_summary["failed_slots"] = failed_slots
    if (safety_result or {}).get("error"):
        error_summary["safety_recommendation_error"] = safety_result["error"]  # type: ignore[index]
    if (headline_result or {}).get("error"):
        error_summary["headline_error"] = headline_result["error"]  # type: ignore[index]
    return error_summary


async def _finalize_async(
    *,
    job_id: UUID,
    attempt_id: UUID,
    slot_results: dict[str, Any],
    safety_result: dict[str, Any] | None,
    headline_result: dict[str, Any] | None,
    extracted_payload: dict[str, Any] | None,
    fatal_error_code: str | None,
    fatal_error_message: str | None,
    fatal_error_host: str | None,
) -> dict[str, Any]:
    from src.batch_jobs.service import BatchJobService

    async with get_session_maker()() as session:
        state = await session.get(UrlScanState, job_id)
        if state is None:
            raise ValueError(f"url scan state not found: {job_id}")
        if state.attempt_id != attempt_id:
            return {
                "status": "superseded",
                "job_id": str(job_id),
                "sidebar_payload_complete": False,
                "done_count": slot_results.get("done_count", 0),
                "failed_count": slot_results.get("failed_count", 0),
            }

        utterances = [
            Utterance.model_validate(item)
            for item in (extracted_payload or {}).get("utterances", [])
        ]
        slot_payloads = {
            slug: slot["data"]
            for slug, slot in slot_results.get("slots", {}).items()
            if slot.get("state") == "DONE" and slot.get("data") is not None
        }
        sidebar_payload = None
        if extracted_payload is not None:
            sidebar_payload = _build_sidebar_payload(
                source_url=state.source_url,
                page_title=(extracted_payload.get("page_title") or state.page_title),
                page_kind=PageKind(
                    extracted_payload.get("page_kind") or state.page_kind or "other"
                ),
                utterances=utterances,
                scraped_at=extracted_payload["scraped_at"],
                slot_payloads=slot_payloads,
                recommendation_payload=(safety_result or {}).get("recommendation"),
                headline_payload=(headline_result or {}).get("headline"),
            )

        fatal_or_slot_error = fatal_error_code or None
        status = _terminal_batch_status_for_results(
            done_count=slot_results.get("done_count", 0),
            failed_count=slot_results.get("failed_count", 0),
            total_slots=len(SectionSlug),
            fatal_error_code=fatal_or_slot_error,
        )

        error_summary = _build_error_summary(
            slot_results=slot_results,
            fatal_error_code=fatal_error_code,
            fatal_error_message=fatal_error_message,
            safety_result=safety_result,
            headline_result=headline_result,
        )

        if sidebar_payload is not None:
            encoded_payload = jsonable_encoder(sidebar_payload)
            state.sidebar_payload = encoded_payload
            if status == BatchJobStatus.COMPLETED.value:
                expires_at = datetime.now(UTC) + _SIDEBAR_CACHE_TTL
                await session.merge(
                    UrlScanSidebarCache(
                        normalized_url=state.normalized_url,
                        sidebar_payload=encoded_payload,
                        expires_at=expires_at,
                    )
                )
        else:
            state.sidebar_payload = None

        state.finished_at = datetime.now(UTC)
        state.heartbeat_at = None
        state.error_code = fatal_error_code or None
        state.error_message = fatal_error_message or None
        state.error_host = fatal_error_host or None

        service = BatchJobService(session)
        if status == BatchJobStatus.COMPLETED.value:
            job = await service.complete_job(
                job_id,
                completed_tasks=slot_results.get("done_count", 0),
                failed_tasks=slot_results.get("failed_count", 0),
            )
            if job is not None and error_summary is not None:
                job.error_summary = error_summary
                await session.commit()
        elif status == BatchJobStatus.PARTIAL.value:
            await service.partial_job(
                job_id,
                completed_tasks=slot_results.get("done_count", 0),
                failed_tasks=slot_results.get("failed_count", 0),
                error_summary=error_summary,
            )
        else:
            await service.fail_job(
                job_id,
                error_summary=error_summary,
                completed_tasks=slot_results.get("done_count", 0),
                failed_tasks=slot_results.get("failed_count", 0),
            )

        await session.commit()
        return {
            "status": status,
            "job_id": str(job_id),
            "sidebar_payload_complete": sidebar_payload is not None,
            "done_count": slot_results.get("done_count", 0),
            "failed_count": slot_results.get("failed_count", 0),
        }


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
def rotate_url_scan_section_attempt_step(
    job_id: str,
    slug: str,
    attempt_id: str | None = None,
) -> str:
    return str(
        run_sync(
            _rotate_slot_attempt_async(
                UUID(job_id),
                SectionSlug(slug),
                UUID(attempt_id) if attempt_id is not None else None,
            )
        )
    )


@DBOS.step()
def touch_url_scan_heartbeat_step(job_id: str, attempt_id: str) -> bool:
    return run_sync(_touch_heartbeat_async(UUID(job_id), UUID(attempt_id)))


@DBOS.step()
def set_url_scan_workflow_id_step(job_id: str, workflow_id: str) -> bool:
    return run_sync(_set_workflow_id_async(UUID(job_id), workflow_id))


@DBOS.step()
def load_url_scan_slot_attempts_step(job_id: str) -> dict[str, str]:
    return run_sync(_load_slot_attempts_async(UUID(job_id)))


@DBOS.step()
def load_url_scan_slot_results_step(job_id: str) -> dict[str, Any]:
    return run_sync(_load_slot_results_async(UUID(job_id)))


@DBOS.step()
def validate_url_scan_rows_step(job_id: str, attempt_id: str) -> bool:
    return run_sync(_validate_url_scan_rows_async(UUID(job_id), UUID(attempt_id)))


@DBOS.step()
def fail_nonterminal_url_scan_slots_step(job_id: str, attempt_id: str, error_message: str) -> int:
    return run_sync(_fail_nonterminal_slots_async(UUID(job_id), UUID(attempt_id), error_message))


def _validate_scrape_source_url(raw: str, *, fallback_host: str) -> str:
    try:
        return validate_public_http_url(raw)
    except InvalidURL as exc:
        raise UrlScanWorkflowError(
            ErrorCode.UNSAFE_URL,
            str(exc),
            error_host=urlparse(raw).netloc or fallback_host,
        ) from exc


@DBOS.step()
def _validate_url(
    job_id: str, source_url: str, normalized_url: str, attempt_id: str
) -> dict[str, Any]:
    safe_url = validate_public_http_url(source_url)
    canonical = canonical_cache_key(safe_url)
    if canonical != normalized_url:
        raise UrlScanWorkflowError(
            ErrorCode.INVALID_URL,
            "normalized_url did not match canonical URL",
        )
    if not touch_url_scan_heartbeat_step(job_id, attempt_id):
        return {"status": "superseded"}
    start_batch_job_sync(UUID(job_id), total_tasks=len(SectionSlug))
    run_sync(
        _transition_batch_job_async(
            UUID(job_id),
            BatchJobStatus.EXTRACTING,
            total_tasks=len(SectionSlug),
        )
    )
    return {"normalized_url": canonical, "host": urlparse(canonical).netloc}


@DBOS.step()
def _scrape(job_id: str, source_url: str, normalized_url: str, attempt_id: str) -> dict[str, Any]:
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings

    async def _async_impl() -> dict[str, Any]:
        settings = get_settings()
        redis_client = await get_shared_redis_client(settings.REDIS_URL)
        cache = ScrapeCache(
            redis_client=redis_client,
            session_factory=get_session_maker(),
            screenshot_store=_screenshot_store_from_settings(),
        )
        cached = await cache.get(normalized_url)
        if cached is not None:
            final_source_url = cached.metadata.source_url if cached.metadata else None
            effective_source_url = _validate_scrape_source_url(
                final_source_url or source_url,
                fallback_host=urlparse(normalized_url).netloc,
            )
            return {
                "cached": True,
                "scraped_at": datetime.now(UTC).isoformat(),
                "scrape": cached.model_dump(mode="json"),
                "effective_source_url": effective_source_url,
            }
        client = FirecrawlClient(settings.FIRECRAWL_API_KEY)
        scrape = await client.scrape(source_url, _SCRAPE_FORMATS)
        final_source_url = scrape.metadata.source_url if scrape.metadata else None
        effective_source_url = _validate_scrape_source_url(
            final_source_url or source_url,
            fallback_host=urlparse(normalized_url).netloc,
        )
        stored = await cache.put(
            normalized_url,
            scrape,
            _decode_screenshot_bytes(scrape.screenshot),
            tier="scrape",
        )
        return {
            "cached": False,
            "scraped_at": datetime.now(UTC).isoformat(),
            "scrape": stored.model_dump(mode="json"),
            "effective_source_url": effective_source_url,
        }

    if not touch_url_scan_heartbeat_step(job_id, attempt_id):
        return {"status": "superseded"}
    try:
        return run_sync(_async_impl())
    except FirecrawlBlocked as exc:
        raise UrlScanWorkflowError(
            ErrorCode.UNSUPPORTED_SITE,
            str(exc),
            error_host=urlparse(normalized_url).netloc,
        ) from exc
    except FirecrawlError as exc:
        raise UrlScanWorkflowError(ErrorCode.UPSTREAM_ERROR, str(exc)) from exc


@DBOS.step()
def _extract_utterances(
    job_id: str,
    source_url: str,
    attempt_id: str,
    scrape_result: dict[str, Any],
) -> dict[str, Any]:
    if not touch_url_scan_heartbeat_step(job_id, attempt_id):
        return {"status": "superseded"}

    try:
        scrape_payload = scrape_result["scrape"]
        effective_source_url = scrape_result.get("effective_source_url") or source_url
        utterances_payload = extract_utterances(
            scrape=ScrapeResult.model_validate(scrape_payload),
            source_url=effective_source_url,
        )
    except Exception as exc:
        raise UrlScanWorkflowError(ErrorCode.EXTRACTION_FAILED, str(exc)) from exc

    if not run_sync(_upsert_utterances_async(UUID(job_id), UUID(attempt_id), utterances_payload)):
        return {"status": "superseded"}

    metadata = run_sync(_load_batch_job_context_async(UUID(job_id)))
    run_sync(_transition_batch_job_async(UUID(job_id), BatchJobStatus.ANALYZING))

    utterances = [
        utterance.model_copy(update={"utterance_id": utterance.utterance_id or f"utt-{index}"})
        for index, utterance in enumerate(utterances_payload.utterances)
    ]
    mentioned_urls = sorted({url for item in utterances for url in item.mentioned_urls})
    mentioned_images = sorted({url for item in utterances for url in item.mentioned_images})
    mentioned_videos = sorted({url for item in utterances for url in item.mentioned_videos})

    section_inputs = UrlScanWorkflowInputs(
        utterances=utterances,
        page_url=effective_source_url,
        mentioned_urls=mentioned_urls,
        media_urls=sorted(set(mentioned_images + mentioned_videos)),
        mentioned_images=mentioned_images,
        mentioned_videos=mentioned_videos,
        page_kind=utterances_payload.page_kind,
        community_server_id=str(metadata.get("community_server_id") or "") or None,
        community_server_uuid=str(metadata.get("community_server_uuid") or "") or None,
        dataset_tags=list(metadata.get("dataset_tags") or []),
    )
    return {
        "page_title": utterances_payload.page_title,
        "page_kind": utterances_payload.page_kind.value,
        "utterances": [item.model_dump(mode="json") for item in utterances],
        "section_inputs": section_inputs,
        "scraped_at": scrape_result["scraped_at"],
    }


@DBOS.step()
def _fan_out_slots(job_id: str, section_inputs: UrlScanWorkflowInputs) -> dict[str, Any]:
    attempt_ids = load_url_scan_slot_attempts_step(job_id)
    missing_slugs = [slug.value for slug in SectionSlug if slug.value not in attempt_ids]
    if missing_slugs:
        raise UrlScanWorkflowError(
            ErrorCode.INTERNAL,
            f"url scan section slots missing: {', '.join(missing_slugs)}",
        )
    dispatched: dict[str, str] = {}
    for slug in SectionSlug:
        attempt_id = attempt_ids[slug.value]
        workflow_id = f"url-scan-section-{job_id}-{slug.value}-{attempt_id}"

        def _enqueue(
            *,
            workflow_id: str = workflow_id,
            slug: SectionSlug = slug,
            attempt_id: str = attempt_id,
        ) -> str:
            with SetWorkflowID(workflow_id), SetEnqueueOptions(deduplication_id=workflow_id):
                handle = url_scan_section_queue.enqueue(
                    url_scan_section_workflow,
                    job_id,
                    slug.value,
                    attempt_id,
                    section_inputs,
                    parent_holds_token=True,
                )
                return _workflow_handle_id(handle)

        try:
            dispatched[slug.value] = safe_enqueue_sync(_enqueue)
        except Exception as exc:
            fail_url_scan_section_step(
                job_id,
                slug.value,
                attempt_id,
                str(exc),
                error_code="dispatch_failure",
            )
    return {"enqueued": len(dispatched), "workflow_ids": dispatched}


@DBOS.step()
def _run_safety_recommendation(job_id: str, slot_results: dict[str, Any]) -> dict[str, Any]:
    slots = slot_results.get("slots", {})
    unavailable_inputs = _slot_unavailable_inputs(
        slot_results,
        [
            SectionSlug.SAFETY_MODERATION,
            SectionSlug.SAFETY_WEB_RISK,
            SectionSlug.SAFETY_IMAGE_MODERATION,
            SectionSlug.SAFETY_VIDEO_MODERATION,
        ],
    )
    try:
        recommendation = run_sync(
            run_safety_recommendation(
                import_module(
                    "src.url_content_scan.analyses.safety.recommendation"
                ).SafetyRecommendationInputs(
                    harmful_content_matches=[
                        HarmfulContentMatch.model_validate(item)
                        for item in slots.get(SectionSlug.SAFETY_MODERATION.value, {})
                        .get("data", {})
                        .get("harmful_content_matches", [])
                    ],
                    web_risk_findings=[
                        WebRiskFinding.model_validate(item)
                        for item in slots.get(SectionSlug.SAFETY_WEB_RISK.value, {})
                        .get("data", {})
                        .get("findings", [])
                    ],
                    image_moderation_matches=[
                        ImageModerationMatch.model_validate(item)
                        for item in slots.get(SectionSlug.SAFETY_IMAGE_MODERATION.value, {})
                        .get("data", {})
                        .get("matches", [])
                    ],
                    video_moderation_matches=[
                        VideoModerationMatch.model_validate(item)
                        for item in slots.get(SectionSlug.SAFETY_VIDEO_MODERATION.value, {})
                        .get("data", {})
                        .get("matches", [])
                    ],
                    unavailable_inputs=unavailable_inputs,
                )
            )
        )
        return {"recommendation": recommendation.model_dump(mode="json")}
    except Exception as exc:
        return {"recommendation": None, "error": str(exc), "job_id": job_id}


def _maybe_run_headline_summary(
    *,
    job_id: str,
    extracted_payload: dict[str, Any],
    slot_results: dict[str, Any],
    safety_result: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        synthesis_module = import_module("src.url_content_scan.analyses.synthesis")
    except Exception as exc:
        return {"headline": None, "error": str(exc)}

    run_headline_summary = getattr(synthesis_module, "run_headline_summary", None)
    headline_inputs_type = getattr(synthesis_module, "HeadlineSummaryInputs", None)
    if run_headline_summary is None or headline_inputs_type is None:
        return {"headline": None, "error": "headline synthesis entrypoint missing"}

    slots = slot_results.get("slots", {})
    unavailable_inputs = _slot_unavailable_inputs(slot_results, list(SectionSlug))
    try:
        headline = run_sync(
            run_headline_summary(
                headline_inputs_type(
                    safety_recommendation=(
                        SafetyRecommendation.model_validate(
                            (safety_result or {}).get("recommendation")
                        )
                        if (safety_result or {}).get("recommendation") is not None
                        else None
                    ),
                    harmful_content_matches=[
                        HarmfulContentMatch.model_validate(item)
                        for item in slots.get(SectionSlug.SAFETY_MODERATION.value, {})
                        .get("data", {})
                        .get("harmful_content_matches", [])
                    ],
                    web_risk_findings=[
                        WebRiskFinding.model_validate(item)
                        for item in slots.get(SectionSlug.SAFETY_WEB_RISK.value, {})
                        .get("data", {})
                        .get("findings", [])
                    ],
                    image_moderation_matches=[
                        ImageModerationMatch.model_validate(item)
                        for item in slots.get(SectionSlug.SAFETY_IMAGE_MODERATION.value, {})
                        .get("data", {})
                        .get("matches", [])
                    ],
                    video_moderation_matches=[
                        VideoModerationMatch.model_validate(item)
                        for item in slots.get(SectionSlug.SAFETY_VIDEO_MODERATION.value, {})
                        .get("data", {})
                        .get("matches", [])
                    ],
                    flashpoint_matches=[
                        FlashpointMatch.model_validate(item)
                        for item in slots.get(SectionSlug.TONE_DYNAMICS_FLASHPOINT.value, {}).get(
                            "data", []
                        )
                    ],
                    scd=(
                        SCDReport.model_validate(slots[SectionSlug.TONE_DYNAMICS_SCD.value]["data"])
                        if slots.get(SectionSlug.TONE_DYNAMICS_SCD.value, {}).get("data")
                        is not None
                        else None
                    ),
                    claims_report=(
                        ClaimsReport.model_validate(
                            slots[SectionSlug.FACTS_CLAIMS_DEDUP.value]["data"]
                        )
                        if slots.get(SectionSlug.FACTS_CLAIMS_DEDUP.value, {}).get("data")
                        is not None
                        else None
                    ),
                    known_misinformation=[
                        FactCheckMatch.model_validate(item)
                        for item in slots.get(SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO.value, {}).get(
                            "data", []
                        )
                    ],
                    sentiment_stats=(
                        SentimentStatsReport.model_validate(
                            slots[SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT.value]["data"]
                        )
                        if slots.get(SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT.value, {}).get(
                            "data"
                        )
                        is not None
                        else None
                    ),
                    subjective_claims=[
                        SubjectiveClaim.model_validate(item)
                        for item in slots.get(
                            SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE.value, {}
                        ).get("data", [])
                    ],
                    page_title=extracted_payload.get("page_title"),
                    page_kind=PageKind(extracted_payload.get("page_kind", PageKind.OTHER.value)),
                    unavailable_inputs=unavailable_inputs,
                ),
                settings=import_module("src.config").get_settings(),
                job_id=UUID(job_id),
            )
        )
        return {"headline": headline.model_dump(mode="json")}
    except Exception as exc:
        return {"headline": None, "error": str(exc)}


@DBOS.step()
def _finalize(
    job_id: str,
    attempt_id: str,
    *,
    slot_results: dict[str, Any],
    safety_result: dict[str, Any] | None,
    headline_result: dict[str, Any] | None,
    extracted_payload: dict[str, Any] | None,
    fatal_error_code: str | None = None,
    fatal_error_message: str | None = None,
    fatal_error_host: str | None = None,
) -> dict[str, Any]:
    return run_sync(
        _finalize_async(
            job_id=UUID(job_id),
            attempt_id=UUID(attempt_id),
            slot_results=slot_results,
            safety_result=safety_result,
            headline_result=headline_result,
            extracted_payload=extracted_payload,
            fatal_error_code=fatal_error_code,
            fatal_error_message=fatal_error_message,
            fatal_error_host=fatal_error_host,
        )
    )


@DBOS.workflow()
def url_scan_orchestration_workflow(
    job_id: str,
    source_url: str,
    normalized_url: str,
    attempt_id: str,
) -> dict[str, Any]:
    gate = TokenGate(
        pool="default",
        weight=WorkflowWeight.URL_SCAN,
        parent_holds_token=False,
    )
    gate.acquire()
    extracted_payload: dict[str, Any] | None = None
    slot_results: dict[str, Any] = {
        "slots": {},
        "done_count": 0,
        "failed_count": 0,
        "all_terminal": False,
    }
    safety_result: dict[str, Any] | None = None
    headline_result: dict[str, Any] | None = None
    fatal_error_code: str | None = None
    fatal_error_message: str | None = None
    fatal_error_host: str | None = None
    try:
        validation = _validate_url(job_id, source_url, normalized_url, attempt_id)
        if validation.get("status") == "superseded":
            return {"status": "superseded", "job_id": job_id}

        scrape_result = _scrape(job_id, source_url, normalized_url, attempt_id)
        if scrape_result.get("status") == "superseded":
            return {"status": "superseded", "job_id": job_id}

        extracted_payload = _extract_utterances(job_id, source_url, attempt_id, scrape_result)
        if extracted_payload.get("status") == "superseded":
            return {"status": "superseded", "job_id": job_id}

        _fan_out_slots(job_id, extracted_payload["section_inputs"])
        for _poll in range(_MAX_SLOT_JOIN_POLLS):
            slot_results = load_url_scan_slot_results_step(job_id)
            if slot_results.get("all_terminal"):
                break
            if not touch_url_scan_heartbeat_step(job_id, attempt_id):
                return {"status": "superseded", "job_id": job_id}
            DBOS.sleep(_SLOT_JOIN_POLL_SECONDS)
        else:
            fatal_error_code = ErrorCode.TIMEOUT.value
            fatal_error_message = "timed out waiting for URL scan section slots"
            if not touch_url_scan_heartbeat_step(job_id, attempt_id):
                return {"status": "superseded", "job_id": job_id}
            fail_nonterminal_url_scan_slots_step(job_id, attempt_id, fatal_error_message)
            slot_results = load_url_scan_slot_results_step(job_id)

        safety_result = _run_safety_recommendation(job_id, slot_results)
        headline_result = _maybe_run_headline_summary(
            job_id=job_id,
            extracted_payload=extracted_payload,
            slot_results=slot_results,
            safety_result=safety_result,
        )
    except UrlScanWorkflowError as exc:
        fatal_error_code = exc.error_code
        fatal_error_message = str(exc)
        fatal_error_host = exc.error_host
        slot_results = load_url_scan_slot_results_step(job_id)
    except Exception as exc:
        fatal_error_code = ErrorCode.INTERNAL.value
        fatal_error_message = str(exc)
        slot_results = load_url_scan_slot_results_step(job_id)
    finally:
        gate.release()

    return _finalize(
        job_id,
        attempt_id,
        slot_results=slot_results,
        safety_result=safety_result,
        headline_result=headline_result,
        extracted_payload=extracted_payload,
        fatal_error_code=fatal_error_code,
        fatal_error_message=fatal_error_message,
        fatal_error_host=fatal_error_host,
    )


async def dispatch_url_scan_workflow(
    job_id: UUID,
    source_url: str,
    normalized_url: str,
    attempt_id: UUID,
) -> str | None:
    safe_url = validate_public_http_url(source_url)
    if canonical_cache_key(safe_url) != normalized_url:
        raise ValueError("normalized_url did not match canonical URL")

    workflow_id = f"url-scan-{job_id}-attempt-{attempt_id}"
    if not validate_url_scan_rows_step(str(job_id), str(attempt_id)):
        return None

    def _enqueue() -> Any:
        with SetWorkflowID(workflow_id), SetEnqueueOptions(deduplication_id=workflow_id):
            return url_scan_queue.enqueue(
                url_scan_orchestration_workflow,
                str(job_id),
                safe_url,
                normalized_url,
                str(attempt_id),
            )

    handle = await safe_enqueue(_enqueue)
    dispatched_workflow_id = _workflow_handle_id(handle)
    if not set_url_scan_workflow_id_step(str(job_id), dispatched_workflow_id):
        return None
    return dispatched_workflow_id


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
