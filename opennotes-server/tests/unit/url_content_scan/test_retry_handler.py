from __future__ import annotations

import types
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from src.batch_jobs.models import BatchJob

HANDLER_PATH = Path(__file__).resolve().parents[3] / "src" / "url_content_scan" / "retry_handler.py"
MODELS_PATH = Path(__file__).resolve().parents[3] / "src" / "url_content_scan" / "models.py"


class SectionSlug(StrEnum):
    SAFETY_MODERATION = "safety__moderation"


class PageKind(StrEnum):
    FORUM_THREAD = "forum_thread"
    OTHER = "other"


class RetryResponse(BaseModel):
    job_id: UUID
    slug: SectionSlug
    attempt_id: UUID


class Utterance(BaseModel):
    utterance_id: str | None = None
    kind: str
    text: str
    mentioned_urls: list[str] = []
    mentioned_images: list[str] = []
    mentioned_videos: list[str] = []


@dataclass(slots=True)
class UrlScanWorkflowInputs:
    utterances: list[Utterance] = field(default_factory=list)
    page_url: str | None = None
    mentioned_urls: list[str] = field(default_factory=list)
    media_urls: list[str] = field(default_factory=list)
    mentioned_images: list[str] = field(default_factory=list)
    mentioned_videos: list[str] = field(default_factory=list)
    page_kind: PageKind = PageKind.OTHER
    community_server_id: str | None = None
    community_server_uuid: str | None = None
    dataset_tags: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _load_retry_handler():
    return __import__("src.url_content_scan.retry_handler", fromlist=["prepare_section_retry"])


@pytest.fixture(autouse=True)
def bypass_startup_gate():
    return None


def _batch_job(job_id: UUID, *, status: str) -> BatchJob:
    job = BatchJob(
        id=job_id,
        job_type="url_scan",
        status=status,
        total_tasks=10,
        completed_tasks=0,
        failed_tasks=0,
        metadata_={
            "community_server_id": 42,
            "community_server_uuid": "7f0f1d0c-812c-4fd8-84c2-e48cfc227d07",
            "dataset_tags": ["alpha", "beta"],
        },
    )
    now = datetime.now(UTC)
    job.created_at = now
    job.updated_at = now
    return job


def _scan_state(job_id: UUID) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        job_id=job_id,
        source_url="https://example.com/thread",
        normalized_url="https://example.com/thread",
        host="example.com",
        attempt_id=uuid4(),
        page_kind="forum_thread",
        utterance_count=2,
    )


def _slot(job_id: UUID, *, slug: SectionSlug, state: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        job_id=job_id,
        slug=slug.value,
        state=state,
        attempt_id=uuid4(),
        error_code="timeout" if state == "FAILED" else None,
        error_message="slot failed" if state == "FAILED" else None,
    )


class _FakeScalarResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def scalars(self) -> _FakeScalarResult:
        return self

    def all(self) -> list[object]:
        return self._values


class _FakeSession:
    def __init__(
        self,
        *,
        batch_job: BatchJob,
        scan_state: types.SimpleNamespace,
        slots: list[types.SimpleNamespace],
        utterance_payloads: list[dict[str, object]],
    ) -> None:
        self._batch_job = batch_job
        self._scan_state = scan_state
        self._slots = slots
        self._utterance_rows = [
            types.SimpleNamespace(payload=payload, utterance_id=payload.get("utterance_id"))
            for payload in utterance_payloads
        ]
        self.execute_calls = 0

    async def get(self, model: type[object], _key: UUID) -> object | None:
        if model is BatchJob:
            return self._batch_job
        if getattr(model, "__name__", None) == "UrlScanState":
            return self._scan_state
        raise AssertionError(f"unexpected get({model!r})")

    async def execute(self, _statement: object) -> _FakeScalarResult:
        self.execute_calls += 1
        if self.execute_calls == 1:
            return _FakeScalarResult(self._slots)
        if self.execute_calls == 2:
            return _FakeScalarResult(self._utterance_rows)
        raise AssertionError("unexpected execute call")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prepare_section_retry_accepts_analyzing_and_dispatches_inputs() -> None:
    prepare_section_retry = _load_retry_handler().prepare_section_retry

    job_id = uuid4()
    session = _FakeSession(
        batch_job=_batch_job(job_id, status="analyzing"),
        scan_state=_scan_state(job_id),
        slots=[_slot(job_id, slug=SectionSlug.SAFETY_MODERATION, state="FAILED")],
        utterance_payloads=[
            {
                "utterance_id": "utt-1",
                "kind": "post",
                "text": "Primary post",
                "mentioned_urls": ["https://a.example.com"],
                "mentioned_images": ["https://img.example.com/1.png"],
                "mentioned_videos": [],
            },
            {
                "utterance_id": "utt-2",
                "kind": "reply",
                "text": "Reply",
                "mentioned_urls": ["https://b.example.com"],
                "mentioned_images": [],
                "mentioned_videos": ["https://video.example.com/1.mp4"],
            },
        ],
    )
    calls: list[tuple[UUID, SectionSlug, UUID, object]] = []

    async def _dispatch(job_id_arg, slug_arg, attempt_id_arg, section_inputs_arg) -> None:
        calls.append((job_id_arg, slug_arg, attempt_id_arg, section_inputs_arg))

    response = await prepare_section_retry(
        session,
        job_id,
        SectionSlug.SAFETY_MODERATION,
        dispatch_workflow=_dispatch,
    )

    assert response.job_id == job_id
    assert response.slug.value == SectionSlug.SAFETY_MODERATION.value
    assert len(calls) == 1
    dispatched_job_id, dispatched_slug, dispatched_attempt_id, section_inputs = calls[0]
    assert dispatched_job_id == job_id
    assert dispatched_slug is SectionSlug.SAFETY_MODERATION
    assert dispatched_attempt_id == response.attempt_id
    assert section_inputs.page_url == "https://example.com/thread"
    assert section_inputs.page_kind.value == "forum_thread"
    assert section_inputs.community_server_id == "42"
    assert section_inputs.community_server_uuid == "7f0f1d0c-812c-4fd8-84c2-e48cfc227d07"
    assert section_inputs.dataset_tags == ["alpha", "beta"]
    assert [item.utterance_id for item in section_inputs.utterances] == ["utt-1", "utt-2"]
    assert section_inputs.mentioned_urls == [
        "https://a.example.com",
        "https://b.example.com",
    ]
    assert section_inputs.media_urls == [
        "https://img.example.com/1.png",
        "https://video.example.com/1.mp4",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prepare_section_retry_rejects_non_retryable_job_status() -> None:
    prepare_section_retry = _load_retry_handler().prepare_section_retry

    job_id = uuid4()
    session = _FakeSession(
        batch_job=_batch_job(job_id, status="pending"),
        scan_state=_scan_state(job_id),
        slots=[_slot(job_id, slug=SectionSlug.SAFETY_MODERATION, state="FAILED")],
        utterance_payloads=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await prepare_section_retry(session, job_id, SectionSlug.SAFETY_MODERATION)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error_code"] == "job_not_retryable"
    assert "pending" in exc_info.value.detail["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prepare_section_retry_rejects_slot_not_in_failed_state() -> None:
    prepare_section_retry = _load_retry_handler().prepare_section_retry

    job_id = uuid4()
    session = _FakeSession(
        batch_job=_batch_job(job_id, status="failed"),
        scan_state=_scan_state(job_id),
        slots=[_slot(job_id, slug=SectionSlug.SAFETY_MODERATION, state="DONE")],
        utterance_payloads=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await prepare_section_retry(session, job_id, SectionSlug.SAFETY_MODERATION)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error_code"] == "slot_not_in_retryable_state"
