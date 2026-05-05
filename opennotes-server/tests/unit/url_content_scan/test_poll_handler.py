from __future__ import annotations

import importlib.util
import sys
import types
from datetime import UTC, datetime
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, Field

from src.batch_jobs.models import BatchJob

HANDLER_PATH = Path(__file__).resolve().parents[3] / "src" / "url_content_scan" / "poll_handler.py"
MODELS_PATH = Path(__file__).resolve().parents[3] / "src" / "url_content_scan" / "models.py"


class SectionSlug(StrEnum):
    SAFETY_MODERATION = "safety__moderation"
    SAFETY_WEB_RISK = "safety__web_risk"


class SectionState(StrEnum):
    DONE = "done"
    FAILED = "failed"


class JobStatus(StrEnum):
    ANALYZING = "analyzing"
    DONE = "done"
    PARTIAL = "partial"
    FAILED = "failed"


class PageKind(StrEnum):
    ARTICLE = "article"
    OTHER = "other"


class SectionSlot(BaseModel):
    state: SectionState
    attempt_id: UUID
    data: dict[str, object] | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SidebarPayload(BaseModel):
    source_url: str
    scraped_at: datetime
    page_kind: PageKind
    safety: dict[str, object]
    tone_dynamics: dict[str, object]
    facts_claims: dict[str, object]
    opinions_sentiments: dict[str, object]
    utterances: list[dict[str, object]] = Field(default_factory=list)


class JobState(BaseModel):
    job_id: UUID
    url: str
    status: JobStatus
    attempt_id: UUID
    error_code: str | None = None
    error_message: str | None = None
    error_host: str | None = None
    created_at: datetime
    updated_at: datetime
    sections: dict[SectionSlug, SectionSlot] = Field(default_factory=dict)
    sidebar_payload: SidebarPayload | None = None
    sidebar_payload_complete: bool = False
    activity_at: datetime | None = None
    activity_label: str | None = None
    cached: bool = False
    next_poll_ms: int = 1500
    page_title: str | None = None
    page_kind: PageKind | None = None
    utterance_count: int = 0


@lru_cache(maxsize=1)
def _load_poll_handler():
    fake_schemas = types.ModuleType("src.url_content_scan.schemas")
    fake_schemas.SectionSlug = SectionSlug
    fake_schemas.SectionState = SectionState
    fake_schemas.JobStatus = JobStatus
    fake_schemas.PageKind = PageKind
    fake_schemas.SectionSlot = SectionSlot
    fake_schemas.SidebarPayload = SidebarPayload
    fake_schemas.JobState = JobState
    sys.modules["src.url_content_scan.schemas"] = fake_schemas

    models_spec = importlib.util.spec_from_file_location(
        "task1487_poll_models_runtime", MODELS_PATH
    )
    assert models_spec is not None
    assert models_spec.loader is not None
    models_module = importlib.util.module_from_spec(models_spec)
    sys.modules["task1487_poll_models_runtime"] = models_module
    models_spec.loader.exec_module(models_module)
    sys.modules["src.url_content_scan.models"] = models_module

    module_name = "task1487_test_poll_handler_runtime"
    spec = importlib.util.spec_from_file_location(module_name, HANDLER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def bypass_startup_gate():
    return None


def _sidebar_payload(now: datetime) -> dict[str, object]:
    return {
        "source_url": "https://example.com/article",
        "scraped_at": now.isoformat(),
        "page_kind": "article",
        "safety": {"harmful_content_matches": []},
        "tone_dynamics": {
            "scd": {
                "narrative": "",
                "speaker_arcs": [],
                "summary": "",
                "tone_labels": [],
                "per_speaker_notes": {},
                "insufficient_conversation": True,
            },
            "flashpoint_matches": [],
        },
        "facts_claims": {
            "claims_report": {
                "deduped_claims": [],
                "total_claims": 0,
                "total_unique": 0,
            },
            "known_misinformation": [],
        },
        "opinions_sentiments": {
            "opinions_report": {
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0.0,
                    "negative_pct": 0.0,
                    "neutral_pct": 0.0,
                    "mean_valence": 0.0,
                },
                "subjective_claims": [],
            }
        },
        "utterances": [],
    }


def _batch_job(job_id: UUID, *, status: str, now: datetime) -> BatchJob:
    job = BatchJob(
        id=job_id,
        job_type="url_scan",
        status=status,
        total_tasks=10,
        completed_tasks=0,
        failed_tasks=0,
        metadata_={},
    )
    job.created_at = now
    job.updated_at = now
    return job


def _scan_state(job_id: UUID, *, attempt_id: UUID, now: datetime) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        job_id=job_id,
        source_url="https://example.com/article",
        normalized_url="https://example.com/article",
        host="example.com",
        attempt_id=attempt_id,
        sidebar_payload=_sidebar_payload(now),
        error_code=None,
        error_message=None,
        error_host=None,
        page_title="Example title",
        page_kind="article",
        utterance_count=3,
        heartbeat_at=now,
        finished_at=None,
    )


def _slot(job_id: UUID, *, slug: str, state: str, attempt_id: UUID) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        job_id=job_id,
        slug=slug,
        state=state,
        attempt_id=attempt_id,
        data={"ok": True} if state == "DONE" else None,
        error_code="timeout" if state == "FAILED" else None,
        error_message="slot blew up" if state == "FAILED" else None,
    )


class _FakeResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[object]:
        return self._rows


class _FakeSession:
    def __init__(
        self,
        *,
        batch_job: BatchJob | None,
        scan_state: types.SimpleNamespace | None,
        slots: list[types.SimpleNamespace],
    ) -> None:
        self._batch_job = batch_job
        self._scan_state = scan_state
        self._slots = slots

    async def get(self, model: type[object], _key: UUID) -> object | None:
        if model is BatchJob:
            return self._batch_job
        if getattr(model, "__name__", None) == "UrlScanState":
            return self._scan_state
        raise AssertionError(f"unexpected get({model!r})")

    async def execute(self, _statement: object) -> _FakeResult:
        return _FakeResult(self._slots)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_job_state_assembles_sections_and_nonterminal_poll_hint() -> None:
    load_job_state = _load_poll_handler().load_job_state

    now = datetime.now(UTC)
    job_id = uuid4()
    attempt_id = uuid4()
    session = _FakeSession(
        batch_job=_batch_job(job_id, status="analyzing", now=now),
        scan_state=_scan_state(job_id, attempt_id=attempt_id, now=now),
        slots=[
            _slot(
                job_id,
                slug=SectionSlug.SAFETY_MODERATION.value,
                state="DONE",
                attempt_id=uuid4(),
            ),
            _slot(
                job_id,
                slug=SectionSlug.SAFETY_WEB_RISK.value,
                state="FAILED",
                attempt_id=uuid4(),
            ),
        ],
    )

    job = await load_job_state(session, job_id)

    assert job is not None
    assert job.status.value == "analyzing"
    assert job.next_poll_ms == 1500
    assert job.sidebar_payload is not None
    assert job.sidebar_payload_complete is False
    assert job.activity_at == now
    assert job.page_title == "Example title"
    assert job.page_kind.value == "article"
    assert job.utterance_count == 3
    assert job.sections[SectionSlug.SAFETY_MODERATION].state.value == "done"
    assert job.sections[SectionSlug.SAFETY_WEB_RISK].state.value == "failed"
    assert job.sections[SectionSlug.SAFETY_WEB_RISK].error == "slot blew up"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_job_state_maps_completed_to_done_and_stops_polling() -> None:
    load_job_state = _load_poll_handler().load_job_state

    now = datetime.now(UTC)
    job_id = uuid4()
    attempt_id = uuid4()
    batch_job = _batch_job(job_id, status="completed", now=now)
    scan_state = _scan_state(job_id, attempt_id=attempt_id, now=now)
    scan_state.finished_at = now
    session = _FakeSession(batch_job=batch_job, scan_state=scan_state, slots=[])

    job = await load_job_state(session, job_id)

    assert job is not None
    assert job.status.value == "done"
    assert job.next_poll_ms == 0
    assert job.sidebar_payload_complete is True
    assert job.activity_at is None
    assert job.activity_label is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_job_state_returns_none_when_header_rows_are_missing() -> None:
    load_job_state = _load_poll_handler().load_job_state

    job_id = uuid4()
    session = _FakeSession(batch_job=None, scan_state=None, slots=[])

    assert await load_job_state(session, job_id) is None
