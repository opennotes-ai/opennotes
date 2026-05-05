from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.batch_jobs.models import BatchJob
from src.batch_jobs.schemas import BatchJobStatus
from src.url_content_scan.analyze_handler import AnalyzeSubmissionError, submit_url_scan
from src.url_content_scan.models import (
    UrlScanSectionSlot,
    UrlScanSidebarCache,
    UrlScanState,
    UrlScanWebRiskLookup,
)
from src.url_content_scan.safety_schemas import WebRiskFinding
from src.url_content_scan.schemas import AnalyzeRequest, JobStatus, SectionSlug


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value

    def first(self):
        return self._value


class _FakeTransaction(AbstractAsyncContextManager["_FakeTransaction"]):
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeTransaction:
        self._session.begin_calls += 1
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._session.transaction_commits += 1
        else:
            self._session.rollbacks += 1


class _FakeSession:
    def __init__(self, *, advisory_lock_results: list[bool] | None = None) -> None:
        self.advisory_lock_results = advisory_lock_results or [True]
        self.begin_calls = 0
        self.transaction_commits = 0
        self.rollbacks = 0
        self.jobs: dict[UUID, BatchJob] = {}
        self.states: dict[UUID, UrlScanState] = {}
        self.sidebar_cache: dict[str, UrlScanSidebarCache] = {}
        self.web_risk_lookups: dict[str, UrlScanWebRiskLookup] = {}
        self.section_slots: list[UrlScanSectionSlot] = []

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def add(self, obj) -> None:
        now = datetime.now(UTC)
        if isinstance(obj, BatchJob):
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()
            obj.created_at = getattr(obj, "created_at", None) or now
            obj.updated_at = getattr(obj, "updated_at", None) or now
            self.jobs[obj.id] = obj
            return
        if isinstance(obj, UrlScanState):
            self.states[obj.job_id] = obj
            return
        if isinstance(obj, UrlScanSectionSlot):
            self.section_slots.append(obj)
            return
        raise TypeError(f"unsupported add: {type(obj)!r}")

    async def flush(self) -> None:
        return None

    async def merge(self, obj):
        if isinstance(obj, UrlScanWebRiskLookup):
            self.web_risk_lookups[obj.normalized_url] = obj
            return obj
        raise TypeError(f"unsupported merge: {type(obj)!r}")

    async def get(self, model, key):
        if model is UrlScanSidebarCache:
            return self.sidebar_cache.get(key)
        if model is UrlScanState:
            return self.states.get(key)
        if model is BatchJob:
            return self.jobs.get(key)
        if model is UrlScanWebRiskLookup:
            return self.web_risk_lookups.get(key)
        raise TypeError(f"unsupported get: {model!r}")

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "pg_try_advisory_xact_lock" in sql:
            value = self.advisory_lock_results.pop(0)
            return _FakeResult(value)
        if "url_scan_state.error_code" in sql:
            matches = [
                (job.id,)
                for job in self.jobs.values()
                if job.status == BatchJobStatus.FAILED.value
                and (state := self.states.get(job.id)) is not None
                and state.normalized_url == params_or_normalized(statement, params)
                and state.error_code == "unsafe_url"
            ]
            matches.sort(key=lambda row: self.jobs[row[0]].created_at, reverse=True)
            return _FakeResult(matches[0] if matches else None)
        if "batch_jobs.status IN" in sql:
            normalized_url = params_or_normalized(statement, params)
            matches = [
                (job.id, job.status)
                for job in self.jobs.values()
                if job.status
                in {
                    BatchJobStatus.PENDING.value,
                    BatchJobStatus.IN_PROGRESS.value,
                    BatchJobStatus.EXTRACTING.value,
                    BatchJobStatus.ANALYZING.value,
                }
                and (state := self.states.get(job.id)) is not None
                and state.normalized_url == normalized_url
                and state.finished_at is None
            ]
            matches.sort(key=lambda row: self.jobs[row[0]].created_at, reverse=True)
            return _FakeResult(matches[0] if matches else None)
        raise AssertionError(f"unexpected statement: {sql}")


def params_or_normalized(statement, params) -> str:
    if params and "normalized_url" in params:
        return params["normalized_url"]
    compiled_params = statement.compile().params
    for key, value in compiled_params.items():
        if "normalized_url" in key:
            return value
    raise AssertionError(f"normalized_url missing from {statement}")


def _request(api_key_id: UUID | None = None):
    return SimpleNamespace(
        state=SimpleNamespace(
            url_scan_api_key=SimpleNamespace(id=api_key_id) if api_key_id is not None else None
        )
    )


def _cache_row(url: str) -> UrlScanSidebarCache:
    now = datetime.now(UTC)
    return UrlScanSidebarCache(
        normalized_url=url,
        sidebar_payload={
            "source_url": url,
            "page_title": "Cached title",
            "page_kind": "article",
            "scraped_at": now.isoformat(),
            "cached": False,
            "cached_at": None,
            "safety": {"harmful_content_matches": [], "recommendation": None},
            "tone_dynamics": {
                "scd": {"summary": "", "insufficient_conversation": True},
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
            "web_risk": {"findings": []},
            "image_moderation": {"matches": []},
            "video_moderation": {"matches": []},
            "utterances": [{"position": 1, "utterance_id": "utt-1"}],
        },
        created_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(hours=1),
    )


async def fake_web_risk_none(_url: str):
    return None


@pytest.mark.asyncio
async def test_submit_url_scan_rejects_invalid_url_without_mutation() -> None:
    session = _FakeSession()

    with pytest.raises(AnalyzeSubmissionError, match="url rejected"):
        await submit_url_scan(
            session,
            _request(),
            AnalyzeRequest(url="javascript:alert(1)"),
            web_risk=fake_web_risk_none,
        )

    assert session.jobs == {}
    assert session.states == {}
    assert session.section_slots == []


@pytest.mark.asyncio
async def test_submit_url_scan_retries_lock_once_then_creates_pending_job_and_dispatches() -> None:
    session = _FakeSession(advisory_lock_results=[False, True])
    sleep_calls: list[float] = []
    dispatch_calls: list[tuple[UUID, str, str, UUID, int]] = []
    api_key_id = uuid4()

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    async def fake_web_risk(_url: str):
        return None

    async def fake_dispatch(job_id: UUID, source_url: str, normalized_url: str, attempt_id: UUID):
        dispatch_calls.append(
            (job_id, source_url, normalized_url, attempt_id, session.transaction_commits)
        )
        return "wf-123"

    response = await submit_url_scan(
        session,
        _request(api_key_id),
        AnalyzeRequest(url="https://Example.com/post/?utm_source=test"),
        dispatch=fake_dispatch,
        web_risk=fake_web_risk,
        sleep=fake_sleep,
    )

    assert response.status == JobStatus.PENDING
    assert response.cached is False
    assert sleep_calls == [1.0]
    assert len(dispatch_calls) == 1
    job_id, source_url, normalized_url, attempt_id, commit_count = dispatch_calls[0]
    assert response.job_id == job_id
    assert source_url == "https://example.com/post/?utm_source=test"
    assert normalized_url == "https://example.com/post"
    assert commit_count == 2

    job = session.jobs[job_id]
    state = session.states[job_id]
    assert job.status == BatchJobStatus.PENDING.value
    assert job.metadata_["api_key_id"] == str(api_key_id)
    assert state.attempt_id == attempt_id
    assert state.normalized_url == "https://example.com/post"
    assert len(session.section_slots) == len(SectionSlug)
    assert {slot.slug for slot in session.section_slots} == {slug.value for slug in SectionSlug}
    assert {slot.attempt_id for slot in session.section_slots} == {attempt_id}


@pytest.mark.asyncio
async def test_submit_url_scan_creates_failed_job_for_unsafe_page_url() -> None:
    session = _FakeSession()

    async def fake_web_risk(_url: str):
        return WebRiskFinding(
            url="https://example.com/post",
            threat_types=["SOCIAL_ENGINEERING"],
        )

    async def fake_dispatch(*_args, **_kwargs):
        return "unused"

    response = await submit_url_scan(
        session,
        _request(),
        AnalyzeRequest(url="https://example.com/post"),
        web_risk=fake_web_risk,
        dispatch=fake_dispatch,
    )

    job = session.jobs[response.job_id]
    state = session.states[response.job_id]
    assert response.status == JobStatus.FAILED
    assert response.cached is False
    assert job.status == BatchJobStatus.FAILED.value
    assert state.error_code == "unsafe_url"
    assert "SOCIAL_ENGINEERING" in state.error_message
    assert state.finished_at is not None
    assert session.web_risk_lookups["https://example.com/post"].findings["threat_types"] == [
        "SOCIAL_ENGINEERING"
    ]
    assert session.section_slots == []


@pytest.mark.asyncio
async def test_submit_url_scan_returns_cached_done_job_when_sidebar_cache_exists() -> None:
    session = _FakeSession()
    normalized_url = "https://example.com/post"
    session.sidebar_cache[normalized_url] = _cache_row(normalized_url)
    dispatch_called = False

    async def fake_dispatch(*_args):
        nonlocal dispatch_called
        dispatch_called = True
        return "wf-should-not-run"

    response = await submit_url_scan(
        session,
        _request(),
        AnalyzeRequest(url="https://example.com/post"),
        web_risk=fake_web_risk_none,
        dispatch=fake_dispatch,
    )

    job = session.jobs[response.job_id]
    state = session.states[response.job_id]
    assert response.status == JobStatus.DONE
    assert response.cached is True
    assert job.status == BatchJobStatus.COMPLETED.value
    assert state.sidebar_payload["cached"] is True
    assert state.page_title == "Cached title"
    assert state.page_kind == "article"
    assert state.utterance_count == 1
    assert state.finished_at is not None
    assert dispatch_called is False


@pytest.mark.asyncio
async def test_submit_url_scan_dedups_to_existing_nonterminal_job() -> None:
    session = _FakeSession()
    job_id = uuid4()
    session.jobs[job_id] = BatchJob(
        id=job_id,
        job_type="url_scan",
        status=BatchJobStatus.EXTRACTING.value,
        total_tasks=len(SectionSlug),
        completed_tasks=0,
        failed_tasks=0,
        metadata_={},
        created_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    session.states[job_id] = UrlScanState(
        job_id=job_id,
        source_url="https://example.com/post",
        normalized_url="https://example.com/post",
        host="example.com",
        attempt_id=uuid4(),
    )

    async def fake_web_risk(_url: str):
        return None

    async def fake_dispatch(*_args, **_kwargs):
        return "unused"

    response = await submit_url_scan(
        session,
        _request(),
        AnalyzeRequest(url="https://example.com/post"),
        web_risk=fake_web_risk,
        dispatch=fake_dispatch,
    )

    assert response.job_id == job_id
    assert response.status == JobStatus.EXTRACTING
    assert response.cached is False
    assert len(session.jobs) == 1
    assert session.section_slots == []


@pytest.mark.asyncio
async def test_submit_url_scan_marks_job_failed_when_post_commit_dispatch_fails() -> None:
    session = _FakeSession()

    async def fake_web_risk(_url: str):
        return None

    async def fake_dispatch(*_args):
        raise RuntimeError("queue offline")

    with pytest.raises(AnalyzeSubmissionError, match="failed to dispatch"):
        await submit_url_scan(
            session,
            _request(),
            AnalyzeRequest(url="https://example.com/post"),
            web_risk=fake_web_risk,
            dispatch=fake_dispatch,
        )

    assert len(session.jobs) == 1
    job = next(iter(session.jobs.values()))
    state = session.states[job.id]
    assert job.status == BatchJobStatus.FAILED.value
    assert job.error_summary["error_code"] == "internal"
    assert state.error_code == "internal"
    assert state.error_message == "dispatch failed"
    assert state.finished_at is not None
