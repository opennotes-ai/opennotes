"""Integration tests for slot write-contract helpers (TASK-1473.09).

These tests run against a real Postgres instance (via testcontainers) because
the contracts under test — optimistic CAS updates, concurrent claim arbitration,
advisory-lock-guarded finalization — are inherently database-level behaviors
that cannot be faithfully simulated with mocks.
"""
from __future__ import annotations

import asyncio
import json
import socket
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.schemas import SectionSlot, SectionSlug, SectionState
from src.jobs.finalize import maybe_finalize_job
from src.jobs.slots import (
    claim_slot,
    mark_slot_done,
    mark_slot_failed,
    write_slot,
)
from tests.conftest import VIBECHECK_JOBS_DDL

# Capture the real resolver before the suite-wide autouse `_stub_dns` fixture
# in tests/conftest.py patches it at test setup time.
_REAL_GETADDRINFO = socket.getaddrinfo


# --- Container + schema bootstrapping --------------------------------------

# src/cache/schema.sql depends on pg_cron / uuid-ossp which aren't both
# present in vanilla Postgres images. For unit tests we install just the core
# DDL we exercise. The `vibecheck_jobs` block lives in tests/conftest.py as
# `VIBECHECK_JOBS_DDL` so column additions stay a one-line change.
_MINIMAL_DDL = (
    """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
"""
    + VIBECHECK_JOBS_DDL
    + """
CREATE TABLE vibecheck_job_utterances (
    utterance_pk UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES vibecheck_jobs(job_id) ON DELETE CASCADE,
    utterance_id TEXT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    author TEXT,
    timestamp_at TIMESTAMPTZ,
    parent_id TEXT,
    position INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
)


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    # The suite-wide autouse `_stub_dns` fixture in tests/conftest.py pins
    # every hostname lookup to 8.8.8.8 for SSRF tests. Testcontainers needs
    # real localhost resolution to reach the Postgres it just booted, so we
    # undo the stub for this module.
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container) -> Any:
    # Build asyncpg DSN from the container's driver-shaped URL.
    raw = _postgres_container.get_connection_url()
    # testcontainers returns e.g. postgresql+psycopg2://... — strip driver suffix.
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8)
    assert pool is not None

    async with pool.acquire() as conn:
        # Fresh schema per test keeps behavior checks independent.
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_job_utterances CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)

    try:
        yield pool
    finally:
        await pool.close()


async def _insert_job(
    pool: Any,
    attempt_id: UUID,
    url: str = "https://example.com/a",
    normalized_url: str | None = None,
    source_type: str = "url",
) -> UUID:
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, attempt_id, source_type
            )
            VALUES ($1, $2, $3, 'analyzing', $4, $5)
            RETURNING job_id
            """,
            url,
            normalized_url if normalized_url is not None else url,
            "example.com",
            attempt_id,
            source_type,
        )
    assert isinstance(job_id, UUID)
    return job_id


async def _read_sections(pool: Any, job_id: UUID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT sections FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    return json.loads(row) if isinstance(row, str) else dict(row)


# --- claim_slot ------------------------------------------------------------


async def test_claim_slot_returns_attempt_id_for_fresh_slot(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    slot_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.SAFETY_MODERATION
    )

    assert isinstance(slot_attempt, UUID)
    sections = await _read_sections(db_pool, job_id)
    assert sections[SectionSlug.SAFETY_MODERATION.value]["state"] == "running"
    assert sections[SectionSlug.SAFETY_MODERATION.value]["attempt_id"] == str(slot_attempt)


async def test_claim_slot_rejects_stale_task_attempt(db_pool) -> None:
    current_attempt = uuid4()
    stale_attempt = uuid4()
    job_id = await _insert_job(db_pool, current_attempt)

    slot_attempt = await claim_slot(
        db_pool, job_id, stale_attempt, SectionSlug.SAFETY_MODERATION
    )

    assert slot_attempt is None
    sections = await _read_sections(db_pool, job_id)
    assert SectionSlug.SAFETY_MODERATION.value not in sections


async def test_claim_slot_returns_none_if_already_running(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    first = await claim_slot(db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD)
    second = await claim_slot(db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD)

    assert first is not None
    assert second is None


async def test_claim_slot_is_atomic_under_concurrency(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    # Two concurrent claimers on the same slot, each using its own connection.
    results = await asyncio.gather(
        claim_slot(db_pool, job_id, task_attempt, SectionSlug.FACTS_CLAIMS_DEDUP),
        claim_slot(db_pool, job_id, task_attempt, SectionSlug.FACTS_CLAIMS_DEDUP),
    )

    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1
    assert len(losers) == 1


async def test_claim_slot_permits_reclaim_after_failed(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    first_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE
    )
    assert first_attempt is not None
    rows = await mark_slot_failed(
        db_pool,
        job_id,
        SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE,
        first_attempt,
        "boom",
        expected_task_attempt=task_attempt,
    )
    assert rows == 1

    second_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE
    )

    assert isinstance(second_attempt, UUID)
    assert second_attempt != first_attempt


# --- Fix B (codex W3 P1-4): claim_slot requires active job status ---------
#
# Terminal jobs (done/failed) must not accept new slot claims. The sweeper
# flips job.status to 'failed' on heartbeat expiry without rotating
# attempt_id, so a stale Cloud Tasks redelivery with the matching
# task_attempt could otherwise re-flip a slot back to 'running' on a
# finalized job. The guard closes that hole.


async def test_claim_slot_rejected_when_job_status_is_failed(db_pool) -> None:
    """A terminal (failed) job must not accept new slot claims even when
    task_attempt still matches.
    """
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    # Fail the job in place — attempt_id is NOT rotated (simulates the
    # heartbeat-expiry path: sweeper flips status without bumping attempt).
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET status = 'failed', finished_at = now() "
            "WHERE job_id = $1",
            job_id,
        )

    slot_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.SAFETY_MODERATION
    )

    assert slot_attempt is None
    sections = await _read_sections(db_pool, job_id)
    assert SectionSlug.SAFETY_MODERATION.value not in sections


async def test_claim_slot_rejected_when_job_status_is_done(db_pool) -> None:
    """A terminal (done) job must not accept new slot claims."""
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET status = 'done', finished_at = now() "
            "WHERE job_id = $1",
            job_id,
        )

    slot_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD
    )

    assert slot_attempt is None
    sections = await _read_sections(db_pool, job_id)
    assert SectionSlug.TONE_DYNAMICS_SCD.value not in sections


async def test_claim_slot_permitted_when_job_is_analyzing(db_pool) -> None:
    """Active statuses (extracting, analyzing) must still permit new claims."""
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    # _insert_job seeds 'analyzing' by default — assert and exercise.
    slot_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO
    )

    assert isinstance(slot_attempt, UUID)


def test_retry_claim_sql_clears_weather_report() -> None:
    from src.jobs.slots import _RETRY_CLAIM_SQL

    assert "weather_report = NULL" in _RETRY_CLAIM_SQL
    assert "headline_summary = NULL" in _RETRY_CLAIM_SQL
    assert "sidebar_payload = NULL" in _RETRY_CLAIM_SQL


# --- mark_slot_done / mark_slot_failed CAS ---------------------------------


async def test_mark_slot_done_fails_on_stale_slot_attempt(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    live_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_FLASHPOINT
    )
    assert live_attempt is not None

    stale_attempt = uuid4()
    rows = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.TONE_DYNAMICS_FLASHPOINT,
        stale_attempt,
        {"flashpoint_matches": []},
        expected_task_attempt=task_attempt,
    )

    assert rows == 0
    sections = await _read_sections(db_pool, job_id)
    assert sections[SectionSlug.TONE_DYNAMICS_FLASHPOINT.value]["state"] == "running"


async def test_mark_slot_done_writes_payload_when_attempt_matches(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    slot_attempt = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.SAFETY_MODERATION
    )
    assert slot_attempt is not None

    rows = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.SAFETY_MODERATION,
        slot_attempt,
        {"harmful_content_matches": []},
        expected_task_attempt=task_attempt,
    )

    assert rows == 1
    sections = await _read_sections(db_pool, job_id)
    entry = sections[SectionSlug.SAFETY_MODERATION.value]
    assert entry["state"] == "done"
    assert entry["data"] == {"harmful_content_matches": []}
    assert entry["finished_at"] is not None


# --- Terminal CAS guards (P1.3): task_attempt + status + prior slot state --


async def test_mark_slot_done_fails_when_job_task_attempt_has_rotated(db_pool) -> None:
    """A superseded job attempt must not accept terminal slot writes.

    Scenario: worker A claims the slot; before A finishes, the job was
    retried, rotating `attempt_id`. A's late `mark_slot_done` must no-op
    even though A still holds the matching `slot_attempt_id` — otherwise a
    stale worker can mutate a fresh attempt's cache.
    """
    initial_attempt = uuid4()
    job_id = await _insert_job(db_pool, initial_attempt)
    live_slot = await claim_slot(
        db_pool, job_id, initial_attempt, SectionSlug.TONE_DYNAMICS_FLASHPOINT
    )
    assert live_slot is not None

    # Simulate a retry rotating the job-level attempt_id.
    rotated_attempt = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET attempt_id = $2 WHERE job_id = $1",
            job_id,
            rotated_attempt,
        )

    rows = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.TONE_DYNAMICS_FLASHPOINT,
        live_slot,
        {"flashpoint_matches": []},
        expected_task_attempt=initial_attempt,
    )

    assert rows == 0
    sections = await _read_sections(db_pool, job_id)
    # Slot must still be running — the stale worker did not clobber it.
    assert sections[SectionSlug.TONE_DYNAMICS_FLASHPOINT.value]["state"] == "running"


async def test_mark_slot_done_fails_when_slot_state_is_not_running(db_pool) -> None:
    """Once a slot reaches a terminal state, re-delivered done writes no-op."""
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    live_slot = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.SAFETY_MODERATION
    )
    assert live_slot is not None

    first = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.SAFETY_MODERATION,
        live_slot,
        {"harmful_content_matches": []},
        expected_task_attempt=task_attempt,
    )
    assert first == 1

    second = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.SAFETY_MODERATION,
        live_slot,
        {"harmful_content_matches": [{"spurious": "write"}]},
        expected_task_attempt=task_attempt,
    )

    assert second == 0
    sections = await _read_sections(db_pool, job_id)
    # Original done payload wins — the second (stale) write did not clobber.
    assert sections[SectionSlug.SAFETY_MODERATION.value]["data"] == {
        "harmful_content_matches": []
    }


async def test_mark_slot_done_fails_when_job_status_is_terminal(db_pool) -> None:
    """A job that flipped to failed/done must reject further slot terminal writes."""
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    live_slot = await claim_slot(
        db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD
    )
    assert live_slot is not None

    # Sweeper (or explicit error path) transitions the job to failed.
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET status = 'failed', finished_at = now() "
            "WHERE job_id = $1",
            job_id,
        )

    rows = await mark_slot_done(
        db_pool,
        job_id,
        SectionSlug.TONE_DYNAMICS_SCD,
        live_slot,
        {"scd": {"summary": "late"}},
        expected_task_attempt=task_attempt,
    )

    assert rows == 0
    sections = await _read_sections(db_pool, job_id)
    assert sections[SectionSlug.TONE_DYNAMICS_SCD.value]["state"] == "running"


async def test_mark_slot_failed_fails_when_job_task_attempt_has_rotated(db_pool) -> None:
    """mark_slot_failed must enforce the same CAS envelope as mark_slot_done."""
    initial_attempt = uuid4()
    job_id = await _insert_job(db_pool, initial_attempt)
    live_slot = await claim_slot(
        db_pool, job_id, initial_attempt, SectionSlug.FACTS_CLAIMS_DEDUP
    )
    assert live_slot is not None

    rotated_attempt = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET attempt_id = $2 WHERE job_id = $1",
            job_id,
            rotated_attempt,
        )

    rows = await mark_slot_failed(
        db_pool,
        job_id,
        SectionSlug.FACTS_CLAIMS_DEDUP,
        live_slot,
        "boom",
        expected_task_attempt=initial_attempt,
    )

    assert rows == 0
    sections = await _read_sections(db_pool, job_id)
    assert sections[SectionSlug.FACTS_CLAIMS_DEDUP.value]["state"] == "running"


# --- write_slot (generic contract) -----------------------------------------


async def test_write_slot_merges_sections_without_clobbering_siblings(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)

    slot_a = SectionSlot(
        state=SectionState.DONE,
        attempt_id=uuid4(),
        data={"a": 1},
    )
    slot_b = SectionSlot(
        state=SectionState.DONE,
        attempt_id=uuid4(),
        data={"b": 2},
    )

    rows_a = await write_slot(
        db_pool, job_id, task_attempt, SectionSlug.SAFETY_MODERATION, slot_a
    )
    rows_b = await write_slot(
        db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD, slot_b
    )

    assert rows_a == 1
    assert rows_b == 1
    sections = await _read_sections(db_pool, job_id)
    assert sections[SectionSlug.SAFETY_MODERATION.value]["data"] == {"a": 1}
    assert sections[SectionSlug.TONE_DYNAMICS_SCD.value]["data"] == {"b": 2}


async def test_slot_data_roundtrips_uuid_and_datetime(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    slot_attempt = uuid4()
    started = datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 4, 22, 12, 0, 5, tzinfo=UTC)
    slot = SectionSlot(
        state=SectionState.DONE,
        attempt_id=slot_attempt,
        data={"scd": {"id": str(uuid4()), "ts": started.isoformat()}},
        started_at=started,
        finished_at=finished,
    )

    rows = await write_slot(
        db_pool, job_id, task_attempt, SectionSlug.TONE_DYNAMICS_SCD, slot
    )

    assert rows == 1
    sections = await _read_sections(db_pool, job_id)
    entry = sections[SectionSlug.TONE_DYNAMICS_SCD.value]
    assert entry["attempt_id"] == str(slot_attempt)
    assert entry["started_at"] == started.isoformat().replace("+00:00", "Z") or entry[
        "started_at"
    ] == started.isoformat()
    # Crucially, we can re-parse back into SectionSlot without a type error.
    rebuilt = SectionSlot.model_validate(entry)
    assert rebuilt.attempt_id == slot_attempt
    assert rebuilt.started_at == started
    assert rebuilt.finished_at == finished


# --- maybe_finalize_job ----------------------------------------------------


_ALL_SLUGS = list(SectionSlug)


def _done_slot(data: dict[str, Any]) -> SectionSlot:
    return SectionSlot(
        state=SectionState.DONE,
        attempt_id=uuid4(),
        data=data,
        started_at=datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 4, 22, 12, 0, 1, tzinfo=UTC),
    )


def _failed_slot(error: str) -> SectionSlot:
    return SectionSlot(
        state=SectionState.FAILED,
        attempt_id=uuid4(),
        error=error,
        started_at=datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 4, 22, 12, 0, 1, tzinfo=UTC),
    )


def _minimal_slot_payloads() -> dict[SectionSlug, dict[str, Any]]:
    # Each payload matches the slot-level contract `maybe_finalize_job` expects:
    # slot.data is the fragment that contributes to its destination section in
    # `SidebarPayload`. Every slot below carries at least one slot-unique
    # sentinel value so the reassembly tests can prove that finalize routes
    # each fragment to its correct nested location in `SidebarPayload`
    # (and never leaks one slot's content into another section).
    return {
        SectionSlug.SAFETY_MODERATION: {
            "harmful_content_matches": [
                {
                    "utterance_id": "utt-safety-001",
                    "utterance_text": "sentinel safety text",
                    "max_score": 0.91,
                    "categories": {"hate": True, "violence": False},
                    "scores": {"hate": 0.91, "violence": 0.04},
                    "flagged_categories": ["sentinel-safety-flag"],
                }
            ]
        },
        SectionSlug.SAFETY_WEB_RISK: {
            "findings": [
                {
                    "url": "https://sentinel-web-risk.example.test/attack",
                    "threat_types": ["SOCIAL_ENGINEERING"],
                }
            ]
        },
        SectionSlug.SAFETY_IMAGE_MODERATION: {
            "matches": [
                {
                    "utterance_id": "utt-img-sentinel-001",
                    "image_url": "https://sentinel-image-mod.example.test/img.png",
                    "adult": 0.11,
                    "violence": 0.22,
                    "racy": 0.33,
                    "medical": 0.44,
                    "spoof": 0.55,
                    "flagged": True,
                    "max_likelihood": 0.55,
                }
            ]
        },
        SectionSlug.SAFETY_VIDEO_MODERATION: {
            "matches": [
                {
                    "utterance_id": "utt-vid-sentinel-001",
                    "video_url": "https://sentinel-video-mod.example.test/vid.mp4",
                    "segment_findings": [],
                    "flagged": True,
                    "max_likelihood": 0.77,
                }
            ]
        },
        SectionSlug.TONE_DYNAMICS_FLASHPOINT: {
            "flashpoint_matches": [
                {
                    "scan_type": "conversation_flashpoint",
                    "utterance_id": "utt-flashpoint-007",
                    "derailment_score": 73,
                    "risk_level": "Heated",
                    "reasoning": "sentinel-flashpoint-reasoning",
                    "context_messages": 4,
                }
            ]
        },
        SectionSlug.TONE_DYNAMICS_SCD: {
            "scd": {
                "summary": "sentinel-scd-summary-narrative",
                "tone_labels": ["sentinel-tone-label", "combative"],
                "per_speaker_notes": {"alice": "sentinel-speaker-note-alice"},
                "insufficient_conversation": False,
            }
        },
        SectionSlug.FACTS_CLAIMS_DEDUP: {
            "claims_report": {
                "deduped_claims": [
                    {
                        "canonical_text": "sentinel-claim-canonical",
                        "occurrence_count": 3,
                        "author_count": 2,
                        "utterance_ids": ["utt-claim-101", "utt-claim-102"],
                        "representative_authors": ["sentinel-author-bob"],
                    }
                ],
                "total_claims": 5,
                "total_unique": 1,
            }
        },
        SectionSlug.FACTS_CLAIMS_EVIDENCE: {
            "claims_report": {
                "deduped_claims": [
                    {
                        "canonical_text": "sentinel-claim-evidence-canonical",
                        "occurrence_count": 1,
                        "author_count": 1,
                        "utterance_ids": ["utt-claim-evidence-201"],
                        "representative_authors": ["sentinel-author-evidence"],
                        "supporting_facts": [
                            {
                                "statement": "sentinel-evidence-stmt",
                                "source_kind": "utterance",
                                "source_ref": "utt-claim-evidence-201",
                            }
                        ],
                    }
                ],
                "total_claims": 1,
                "total_unique": 1,
            }
        },
        SectionSlug.FACTS_CLAIMS_PREMISES: {
            "claims_report": {
                "deduped_claims": [
                    {
                        "canonical_text": "sentinel-claim-premises-canonical",
                        "occurrence_count": 1,
                        "author_count": 1,
                        "utterance_ids": ["utt-claim-premises-301"],
                        "representative_authors": ["sentinel-author-premises"],
                        "premise_ids": ["sentinel-premise-id-001"],
                    }
                ],
                "total_claims": 1,
                "total_unique": 1,
                "premises": {
                    "premises": {
                        "sentinel-premise-id-001": {
                            "premise_id": "sentinel-premise-id-001",
                            "statement": "sentinel-premise-statement",
                        }
                    }
                },
            }
        },
        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO: {
            "known_misinformation": [
                {
                    "claim_text": "sentinel-misinfo-claim",
                    "publisher": "sentinel-publisher",
                    "review_title": "sentinel-review-title",
                    "review_url": "https://example.org/factcheck/sentinel",
                    "textual_rating": "False",
                }
            ]
        },
        SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT: {
            "sentiment_stats": {
                "per_utterance": [
                    {
                        "utterance_id": "utt-sentiment-002",
                        "label": "negative",
                        "valence": -0.42,
                    }
                ],
                "positive_pct": 10.0,
                "negative_pct": 60.0,
                "neutral_pct": 30.0,
                "mean_valence": -0.21,
            }
        },
        SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE: {
            "subjective_claims": [
                {
                    "claim_text": "sentinel-subjective-claim",
                    "utterance_id": "utt-subjective-003",
                    "stance": "opposes",
                }
            ]
        },
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS: {
            "trends_oppositions_report": {
                "trends": [],
                "oppositions": [],
                "input_cluster_count": 0,
                "skipped_for_cap": 0,
            }
        },
        SectionSlug.OPINIONS_SENTIMENTS_HIGHLIGHTS: {
            "highlights_report": {
                "highlights": [],
                "threshold": {
                    "total_authors": 0,
                    "total_utterances": 0,
                    "min_authors_required": 2,
                    "min_occurrences_required": 3,
                },
                "fallback_engaged": False,
                "floor_eligible_count": 0,
                "total_input_count": 0,
            }
        },
    }


async def _seed_slots(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    slugs: list[SectionSlug],
) -> None:
    payloads = _minimal_slot_payloads()
    for slug in slugs:
        slot = _done_slot(payloads[slug])
        rows = await write_slot(pool, job_id, task_attempt, slug, slot)
        assert rows == 1


async def test_maybe_finalize_job_waits_for_all_seven_slots(db_pool) -> None:
    task_attempt = uuid4()
    job_id = await _insert_job(db_pool, task_attempt)
    # 6 of 7 done.
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS[:-1])

    finalized = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )

    assert finalized is False
    async with db_pool.acquire() as conn:
        rowcount = await conn.fetchval("SELECT COUNT(*) FROM vibecheck_analyses")
    assert rowcount == 0


async def test_maybe_finalize_job_upserts_cache_when_all_slots_done(db_pool) -> None:
    task_attempt = uuid4()
    url = "https://example.com/full"
    job_id = await _insert_job(db_pool, task_attempt, url=url)
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS)

    finalized = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )

    assert finalized is True
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT url, sidebar_payload, expires_at FROM vibecheck_analyses WHERE url = $1",
            url,
        )
    assert row is not None
    assert row["url"] == url
    payload = json.loads(row["sidebar_payload"]) if isinstance(
        row["sidebar_payload"], str
    ) else dict(row["sidebar_payload"])
    assert payload["source_url"] == url
    assert "safety" in payload
    assert "tone_dynamics" in payload
    assert "facts_claims" in payload
    assert "opinions_sentiments" in payload

    # Reassembly correctness: each slot's distinctive sentinel must land in
    # exactly one nested location in the assembled SidebarPayload, proving
    # `_assemble_payload` routes fragments to the correct destination
    # section without cross-contamination.
    safety_matches = payload["safety"]["harmful_content_matches"]
    assert len(safety_matches) == 1
    assert safety_matches[0]["utterance_id"] == "utt-safety-001"
    assert safety_matches[0]["flagged_categories"] == ["sentinel-safety-flag"]

    tone = payload["tone_dynamics"]
    assert tone["scd"]["summary"] == "sentinel-scd-summary-narrative"
    assert "sentinel-tone-label" in tone["scd"]["tone_labels"]
    assert tone["scd"]["per_speaker_notes"] == {
        "alice": "sentinel-speaker-note-alice"
    }
    assert tone["scd"]["insufficient_conversation"] is False
    assert len(tone["flashpoint_matches"]) == 1
    assert tone["flashpoint_matches"][0]["utterance_id"] == "utt-flashpoint-007"
    assert tone["flashpoint_matches"][0]["reasoning"] == "sentinel-flashpoint-reasoning"
    assert tone["flashpoint_matches"][0]["risk_level"] == "Heated"

    facts = payload["facts_claims"]
    assert facts["claims_report"]["total_claims"] == 5
    assert facts["claims_report"]["total_unique"] == 1
    deduped = facts["claims_report"]["deduped_claims"]
    assert len(deduped) == 1
    assert deduped[0]["canonical_text"] == "sentinel-claim-canonical"
    assert deduped[0]["utterance_ids"] == ["utt-claim-101", "utt-claim-102"]
    assert len(facts["known_misinformation"]) == 1
    assert facts["known_misinformation"][0]["publisher"] == "sentinel-publisher"
    assert facts["known_misinformation"][0]["review_title"] == "sentinel-review-title"

    opinions = payload["opinions_sentiments"]["opinions_report"]
    assert opinions["sentiment_stats"]["per_utterance"][0]["utterance_id"] == (
        "utt-sentiment-002"
    )
    assert opinions["sentiment_stats"]["per_utterance"][0]["valence"] == -0.42
    assert opinions["sentiment_stats"]["mean_valence"] == -0.21
    assert len(opinions["subjective_claims"]) == 1
    assert opinions["subjective_claims"][0]["claim_text"] == "sentinel-subjective-claim"
    assert opinions["subjective_claims"][0]["stance"] == "opposes"

    web_risk_findings = payload["web_risk"]["findings"]
    assert len(web_risk_findings) == 1
    assert web_risk_findings[0]["url"] == "https://sentinel-web-risk.example.test/attack"
    assert web_risk_findings[0]["threat_types"] == ["SOCIAL_ENGINEERING"]

    image_mod_matches = payload["image_moderation"]["matches"]
    assert len(image_mod_matches) == 1
    assert image_mod_matches[0]["image_url"] == "https://sentinel-image-mod.example.test/img.png"
    assert image_mod_matches[0]["utterance_id"] == "utt-img-sentinel-001"

    video_mod_matches = payload["video_moderation"]["matches"]
    assert len(video_mod_matches) == 1
    assert video_mod_matches[0]["video_url"] == "https://sentinel-video-mod.example.test/vid.mp4"
    assert video_mod_matches[0]["utterance_id"] == "utt-vid-sentinel-001"

    # Cross-contamination guard: each per-slot sentinel string must appear
    # in exactly one section's serialized form, never bleed into a sibling.
    serialized = json.dumps(payload)
    for sentinel in (
        "sentinel-safety-flag",
        "sentinel-flashpoint-reasoning",
        "sentinel-scd-summary-narrative",
        "sentinel-claim-canonical",
        "sentinel-publisher",
        "sentinel-subjective-claim",
        "sentinel-web-risk.example.test",
        "sentinel-image-mod.example.test",
        "sentinel-video-mod.example.test",
    ):
        assert serialized.count(sentinel) == 1, (
            f"sentinel {sentinel!r} appeared "
            f"{serialized.count(sentinel)} times — expected exactly 1"
        )


async def test_maybe_finalize_job_writes_preview_description(db_pool) -> None:
    """TASK-1485.02: finalize derives preview_description and persists it
    in the same UPDATE that marks the job done."""
    task_attempt = uuid4()
    url = "https://example.com/with-preview"
    job_id = await _insert_job(db_pool, task_attempt, url=url)
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS)

    finalized = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )

    assert finalized is True
    async with db_pool.acquire() as conn:
        preview = await conn.fetchval(
            "SELECT preview_description FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert preview is not None
    assert isinstance(preview, str)
    assert len(preview) > 0
    assert len(preview) <= 140


async def test_maybe_finalize_job_preview_uses_first_utterance_fallback(db_pool) -> None:
    """When no analysis signals carry a usable string, the first utterance
    text feeds the fallback branch. The LATERAL join in _LOAD_SQL must
    populate first_utterance_text from vibecheck_job_utterances."""
    task_attempt = uuid4()
    url = "https://example.com/utterance-fallback"
    job_id = await _insert_job(db_pool, task_attempt, url=url)
    sentinel = "Sentinel utterance text for preview fallback"
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_job_utterances (job_id, kind, text, position)
            VALUES ($1, 'post', $2, 0)
            """,
            job_id,
            sentinel,
        )
    payloads = _minimal_slot_payloads()
    # Wipe analysis signals so derive_preview_description falls through to ctx.
    payloads[SectionSlug.SAFETY_MODERATION] = {"harmful_content_matches": []}
    payloads[SectionSlug.TONE_DYNAMICS_FLASHPOINT] = {"flashpoint_matches": []}
    payloads[SectionSlug.FACTS_CLAIMS_DEDUP] = {
        "claims_report": {
            "deduped_claims": [],
            "total_claims": 0,
            "total_unique": 0,
        }
    }
    payloads[SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT] = {
        "sentiment_stats": {
            "per_utterance": [],
            "positive_pct": 0.0,
            "negative_pct": 0.0,
            "neutral_pct": 0.0,
            "mean_valence": 0.0,
        }
    }
    for slug in _ALL_SLUGS:
        slot = _done_slot(payloads[slug])
        await write_slot(db_pool, job_id, task_attempt, slug, slot)

    finalized = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )

    assert finalized is True
    async with db_pool.acquire() as conn:
        preview = await conn.fetchval(
            "SELECT preview_description FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert preview is not None
    assert sentinel in preview


async def test_maybe_finalize_job_is_idempotent_on_repeat_call(db_pool) -> None:
    task_attempt = uuid4()
    url = "https://example.com/idempotent"
    job_id = await _insert_job(db_pool, task_attempt, url=url)
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS)

    first = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )
    second = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )

    assert first is True
    assert second is True
    async with db_pool.acquire() as conn:
        rowcount = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_analyses WHERE url = $1", url
        )
    assert rowcount == 1


async def test_maybe_finalize_job_without_task_attempt_raises_typeerror() -> None:
    """expected_task_attempt is a required kwarg. Callers that skip it must
    fail loudly — the previous `expected_task_attempt: UUID | None = None`
    default let callers silently opt out of the CAS guard, defeating the
    purpose of the slot-write contract.
    """
    with pytest.raises(TypeError):
        # Intentionally skip expected_task_attempt to exercise the guard.
        await maybe_finalize_job(object(), uuid4())  # pyright: ignore[reportCallIssue]


# --- Finalize lock consistency (P1.4) --------------------------------------


async def test_finalize_does_not_upsert_when_job_task_attempt_rotated(
    db_pool,
) -> None:
    """A stale finalize (from a superseded task_attempt) must not touch the cache.

    Simulates the race in spec §"Finalize lock consistency": worker A's
    heartbeat expires, the sweeper rotates job.attempt_id for a retry, and
    A's late finalize coroutine fires after the rotation. A must abort
    without UPSERTing into vibecheck_analyses.
    """
    original_attempt = uuid4()
    url = "https://example.com/stale-finalize"
    job_id = await _insert_job(db_pool, original_attempt, url=url)
    await _seed_slots(db_pool, job_id, original_attempt, _ALL_SLUGS)

    # Simulate a retry rotation AFTER the slot writes but before finalize.
    rotated_attempt = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET attempt_id = $2 WHERE job_id = $1",
            job_id,
            rotated_attempt,
        )

    finalized = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=original_attempt
    )

    assert finalized is False
    async with db_pool.acquire() as conn:
        rowcount = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_analyses WHERE url = $1", url
        )
    assert rowcount == 0


async def test_finalize_does_not_upsert_when_job_status_is_terminal(db_pool) -> None:
    """Once a job flipped to failed, finalize must not resurrect the cache row."""
    task_attempt = uuid4()
    url = "https://example.com/failed-job"
    job_id = await _insert_job(db_pool, task_attempt, url=url)
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS)

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET status = 'failed', finished_at = now() "
            "WHERE job_id = $1",
            job_id,
        )

    finalized = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )

    assert finalized is False
    async with db_pool.acquire() as conn:
        rowcount = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_analyses WHERE url = $1", url
        )
    assert rowcount == 0


async def test_finalize_upsert_races_are_serialized(db_pool) -> None:
    """Two concurrent finalize calls on the same job must produce one cache row.

    FOR UPDATE on the vibecheck_jobs row serializes the two finalizers;
    the ON CONFLICT UPSERT keyed on url ensures a single vibecheck_analyses
    row regardless of the observed order. Without the row lock, both
    finalizers could re-assemble and UPSERT in rapid succession — the
    cache would still end up single-rowed, but the second finalizer would
    perform wasted work and observe a half-merged slot snapshot under
    realistic concurrent-slot-write load.
    """
    task_attempt = uuid4()
    url = "https://example.com/race"
    job_id = await _insert_job(db_pool, task_attempt, url=url)
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS)

    results = await asyncio.gather(
        maybe_finalize_job(db_pool, job_id, expected_task_attempt=task_attempt),
        maybe_finalize_job(db_pool, job_id, expected_task_attempt=task_attempt),
    )

    # Both observe a consistent, fully-done slot set and succeed.
    assert all(results)
    async with db_pool.acquire() as conn:
        rowcount = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_analyses WHERE url = $1", url
        )
    assert rowcount == 1


async def test_finalize_upserts_cache_keyed_by_normalized_url_not_original(
    db_pool,
) -> None:
    """Regression guard for TASK-1473.58.

    vibecheck_analyses.url must be keyed by vibecheck_jobs.normalized_url so
    subsequent submits of the same URL with different tracking params hit the
    72h cache. Before the fix, row["url"] (original) was used as the cache key,
    causing a cache miss on resubmit with different query params.
    """
    original_url = "https://example.com/page?utm_source=foo"
    normalized = "https://example.com/page"
    task_attempt = uuid4()
    job_id = await _insert_job(
        db_pool, task_attempt, url=original_url, normalized_url=normalized
    )
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS)

    finalized = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )
    assert finalized is True

    async with db_pool.acquire() as conn:
        cached = await conn.fetchrow(
            "SELECT url, sidebar_payload FROM vibecheck_analyses WHERE url = $1",
            normalized,
        )
        assert cached is not None
        assert cached["url"] == normalized

        sidebar = (
            json.loads(cached["sidebar_payload"])
            if isinstance(cached["sidebar_payload"], str)
            else dict(cached["sidebar_payload"])
        )
        assert sidebar["source_url"] == original_url

        cached_by_original = await conn.fetchrow(
            "SELECT url FROM vibecheck_analyses WHERE url = $1", original_url
        )
        assert cached_by_original is None


async def test_finalize_does_not_write_url_cache_for_browser_html_jobs(
    db_pool,
) -> None:
    url = "https://example.com/private"
    task_attempt = uuid4()
    job_id = await _insert_job(
        db_pool, task_attempt, url=url, source_type="browser_html"
    )
    await _seed_slots(db_pool, job_id, task_attempt, _ALL_SLUGS)

    finalized = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )
    assert finalized is True

    async with db_pool.acquire() as conn:
        cached_count = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_analyses WHERE url = $1", url
        )
        job = await conn.fetchrow(
            "SELECT status, sidebar_payload FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )

    assert cached_count == 0
    assert job["status"] == "done"
    assert job["sidebar_payload"] is not None


async def test_maybe_finalize_job_marks_partial_when_web_risk_slot_failed(
    db_pool,
) -> None:
    task_attempt = uuid4()
    url = "https://example.com/partial-web-risk"
    job_id = await _insert_job(db_pool, task_attempt, url=url)
    done_slugs = [slug for slug in _ALL_SLUGS if slug is not SectionSlug.SAFETY_WEB_RISK]
    await _seed_slots(db_pool, job_id, task_attempt, done_slugs)
    rows = await write_slot(
        db_pool,
        job_id,
        task_attempt,
        SectionSlug.SAFETY_WEB_RISK,
        _failed_slot("Google Web Risk rejected URI mailto:hn@ycombinator.com"),
    )
    assert rows == 1

    finalized = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )

    assert finalized is True
    async with db_pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT status, error_code, error_message, sidebar_payload, finished_at
            FROM vibecheck_jobs
            WHERE job_id = $1
            """,
            job_id,
        )
        cached = await conn.fetchrow(
            "SELECT url, sidebar_payload FROM vibecheck_analyses WHERE url = $1",
            url,
        )
    assert job is not None
    assert job["status"] == "partial"
    assert job["error_code"] == "section_failure"
    assert job["error_message"] == "Sections failed: safety__web_risk"
    assert job["finished_at"] is not None
    assert cached is not None

    payload = json.loads(job["sidebar_payload"]) if isinstance(
        job["sidebar_payload"], str
    ) else dict(job["sidebar_payload"])
    assert payload["source_url"] == url
    assert payload["web_risk"]["findings"] == []
    assert payload["safety"]["harmful_content_matches"][0]["utterance_id"] == (
        "utt-safety-001"
    )
    assert payload["tone_dynamics"]["scd"]["summary"] == (
        "sentinel-scd-summary-narrative"
    )
