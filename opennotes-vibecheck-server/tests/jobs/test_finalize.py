"""Tests for finalize.py — back-compat legacy dict rehydration.

Covers TASK-1474.12 AC5: HarmfulContentMatch rehydration from stored dicts
that were written before TASK-1474.02 (missing `source` field) defaults
source to "openai".
"""
from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.safety._schemas import HarmfulContentMatch
from src.analyses.schemas import SectionSlot, SectionSlug, SectionState
from src.jobs.finalize import maybe_finalize_job
from tests.conftest import VIBECHECK_JOBS_DDL

_REAL_GETADDRINFO = socket.getaddrinfo

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    page_title TEXT,
    page_kind TEXT,
    utterance_stream_type TEXT
);
"""
)


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container) -> Any:
    dsn = _postgres_container.get_connection_url().replace(
        "postgresql+psycopg2://", "postgresql://"
    )
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)

    async with pool.acquire() as conn:
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


def _done_slot(data: dict[str, Any]) -> SectionSlot:
    return SectionSlot(state=SectionState.DONE, attempt_id=uuid4(), data=data)


def _minimal_done_sections() -> dict[SectionSlug, SectionSlot]:
    return {
        SectionSlug.SAFETY_MODERATION: _done_slot({"harmful_content_matches": []}),
        SectionSlug.SAFETY_WEB_RISK: _done_slot({"findings": []}),
        SectionSlug.SAFETY_IMAGE_MODERATION: _done_slot({"matches": []}),
        SectionSlug.SAFETY_VIDEO_MODERATION: _done_slot({"matches": []}),
        SectionSlug.TONE_DYNAMICS_FLASHPOINT: _done_slot({"flashpoint_matches": []}),
        SectionSlug.TONE_DYNAMICS_SCD: _done_slot(
            {
                "scd": {
                    "summary": "",
                    "tone_labels": [],
                    "per_speaker_notes": {},
                    "insufficient_conversation": True,
                }
            }
        ),
        SectionSlug.FACTS_CLAIMS_DEDUP: _done_slot(
            {
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                }
            }
        ),
        SectionSlug.FACTS_CLAIMS_EVIDENCE: _done_slot(
            {
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                }
            }
        ),
        SectionSlug.FACTS_CLAIMS_PREMISES: _done_slot(
            {
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                }
            }
        ),
        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO: _done_slot({"known_misinformation": []}),
        SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT: _done_slot(
            {
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0.0,
                    "negative_pct": 0.0,
                    "neutral_pct": 0.0,
                    "mean_valence": 0.0,
                }
            }
        ),
        SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE: _done_slot({"subjective_claims": []}),
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS: _done_slot(
            {
                "trends_oppositions_report": {
                    "trends": [],
                    "oppositions": [],
                    "input_cluster_count": 0,
                    "skipped_for_cap": 0,
                }
            }
        ),
    }


async def _insert_job(pool: Any, *, attempt_id: UUID, url: str) -> UUID:
    sections = {
        slug.value: slot.model_dump(mode="json")
        for slug, slot in _minimal_done_sections().items()
    }
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, attempt_id, source_type, sections
            )
            VALUES ($1, $1, 'example.com', 'analyzing', $2, 'url', $3::jsonb)
            RETURNING job_id
            """,
            url,
            attempt_id,
            json.dumps(sections),
        )
    assert isinstance(job_id, UUID)
    return job_id


class TestLegacyDictRehydration:
    def test_harmful_content_match_rehydrates_legacy_dict_without_source_field(self):
        legacy_dict = {
            "utterance_id": "utt_legacy",
            "utterance_text": "legacy text",
            "max_score": 0.8,
            "categories": {"violence": True},
            "scores": {"violence": 0.8},
            "flagged_categories": ["violence"],
        }

        match = HarmfulContentMatch.model_validate(legacy_dict)

        assert match.source == "openai"

    def test_harmful_content_match_with_source_injected_validates_as_openai(self):
        legacy_dict = {
            "utterance_id": "utt_legacy",
            "utterance_text": "legacy text",
            "max_score": 0.8,
            "categories": {"violence": True},
            "scores": {"violence": 0.8},
            "flagged_categories": ["violence"],
        }

        m = {**legacy_dict, "source": "openai"} if "source" not in legacy_dict else legacy_dict
        match = HarmfulContentMatch.model_validate(m)

        assert match.utterance_id == "utt_legacy"
        assert match.source == "openai"
        assert match.max_score == 0.8

    def test_harmful_content_match_with_explicit_source_gcp_preserved(self):
        modern_dict = {
            "utterance_id": "utt_modern",
            "utterance_text": "modern text",
            "max_score": 0.7,
            "categories": {"hate": True},
            "scores": {"hate": 0.7},
            "flagged_categories": ["hate"],
            "source": "gcp",
        }

        m = {**modern_dict, "source": "openai"} if "source" not in modern_dict else modern_dict
        match = HarmfulContentMatch.model_validate(m)

        assert match.source == "gcp"

    def test_finalize_safety_guard_handles_legacy_dict(self):
        """Verify that _assemble_payload defaults legacy safety matches to openai."""
        from src.jobs.finalize import _assemble_payload

        sections = TestAssemblePayloadWiresNewSafetySections()._sections_with_new_safety()
        sections[SectionSlug.SAFETY_MODERATION].data = {
            "harmful_content_matches": [
                {
                    "utterance_id": "utt_legacy",
                    "utterance_text": "legacy text",
                    "max_score": 0.8,
                    "categories": {"violence": True},
                    "scores": {"violence": 0.8},
                    "flagged_categories": ["violence"],
                }
            ]
        }

        sidebar = _assemble_payload("https://test", sections)

        assert sidebar.safety.harmful_content_matches[0].source == "openai"


@pytest.mark.asyncio
async def test_maybe_finalize_job_round_trips_utterance_timestamps_to_sidebar_payload(
    db_pool: Any,
) -> None:
    task_attempt = uuid4()
    timestamp = datetime(2026, 5, 6, 22, 30, tzinfo=UTC)
    job_id = await _insert_job(
        db_pool,
        attempt_id=task_attempt,
        url="https://example.com/timestamped-thread",
    )

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_job_utterances (
                job_id,
                utterance_id,
                kind,
                text,
                timestamp_at,
                position
            )
            VALUES
                ($1, 'comment-0-aaa', 'post', 'first utterance', $2, 0),
                ($1, 'comment-1-bbb', 'comment', 'second utterance', NULL, 1)
            """,
            job_id,
            timestamp,
        )

    finalized = await maybe_finalize_job(
        db_pool,
        job_id,
        expected_task_attempt=task_attempt,
    )

    assert finalized is True
    async with db_pool.acquire() as conn:
        payload = await conn.fetchval(
            "SELECT sidebar_payload FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )

    payload_dict = json.loads(payload) if isinstance(payload, str) else dict(payload)
    assert [anchor["utterance_id"] for anchor in payload_dict["utterances"]] == [
        "comment-0-aaa",
        "comment-1-bbb",
    ]
    assert datetime.fromisoformat(
        payload_dict["utterances"][0]["timestamp"].replace("Z", "+00:00")
    ) == timestamp
    assert payload_dict["utterances"][1]["timestamp"] is None


class TestAssemblePayloadWiresNewSafetySections:
    """Codex P0.3 regression: the finalize step MUST copy web_risk / image_mod /
    video_mod slot data into the SidebarPayload. Before this fix, those slots
    were silently dropped and never reached the rendered sidebar.
    """

    def _sections_with_new_safety(self) -> dict[Any, Any]:
        from uuid import uuid4

        from src.analyses.schemas import (
            SectionSlot,
            SectionSlug,
            SectionState,
        )

        def slot(data):
            return SectionSlot(state=SectionState.DONE, attempt_id=uuid4(), data=data)

        return {
            SectionSlug.SAFETY_MODERATION: slot({"harmful_content_matches": []}),
            SectionSlug.SAFETY_WEB_RISK: slot({
                "findings": [
                    {"url": "https://example.com/bad", "threat_types": ["MALWARE"]}
                ]
            }),
            SectionSlug.SAFETY_IMAGE_MODERATION: slot({
                "matches": [
                    {
                        "utterance_id": "u1",
                        "image_url": "https://example.com/img.jpg",
                        "adult": 1.0, "violence": 0.0, "racy": 0.0,
                        "medical": 0.0, "spoof": 0.0,
                        "flagged": True, "max_likelihood": 1.0,
                    }
                ]
            }),
            SectionSlug.SAFETY_VIDEO_MODERATION: slot({
                "matches": [
                    {
                        "utterance_id": "u2",
                        "video_url": "https://example.com/vid.mp4",
                        "frame_findings": [],
                        "flagged": True, "max_likelihood": 1.0,
                    }
                ]
            }),
            SectionSlug.TONE_DYNAMICS_FLASHPOINT: slot({"flashpoint_matches": []}),
            SectionSlug.TONE_DYNAMICS_SCD: slot({
                "scd": {
                    "summary": "",
                    "tone_labels": [],
                    "per_speaker_notes": {},
                    "insufficient_conversation": True,
                }
            }),
            SectionSlug.FACTS_CLAIMS_DEDUP: slot({
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                }
            }),
            SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO: slot({"known_misinformation": []}),
            SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT: slot({
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0.0,
                    "negative_pct": 0.0,
                    "neutral_pct": 0.0,
                    "mean_valence": 0.0,
                }
            }),
            SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE: slot({"subjective_claims": []}),
        }

    def test_web_risk_findings_flow_through_to_sidebar_payload(self):
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload("https://test", self._sections_with_new_safety())
        assert len(sidebar.web_risk.findings) == 1
        assert sidebar.web_risk.findings[0].threat_types == ["MALWARE"]

    def test_image_moderation_matches_flow_through_to_sidebar_payload(self):
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload("https://test", self._sections_with_new_safety())
        assert len(sidebar.image_moderation.matches) == 1
        assert sidebar.image_moderation.matches[0].flagged is True

    def test_video_moderation_matches_flow_through_to_sidebar_payload(self):
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload("https://test", self._sections_with_new_safety())
        assert len(sidebar.video_moderation.matches) == 1
        assert sidebar.video_moderation.matches[0].flagged is True

    def test_all_new_sections_empty_by_default(self):
        """Empty slot data → default-empty sections (no spurious findings)."""
        from uuid import uuid4

        from src.analyses.schemas import SectionSlot, SectionSlug, SectionState
        from src.jobs.finalize import _assemble_payload

        empty = self._sections_with_new_safety()
        # Overwrite the three new sections with empty lists
        for slug, empty_data in [
            (SectionSlug.SAFETY_WEB_RISK, {"findings": []}),
            (SectionSlug.SAFETY_IMAGE_MODERATION, {"matches": []}),
            (SectionSlug.SAFETY_VIDEO_MODERATION, {"matches": []}),
        ]:
            empty[slug] = SectionSlot(
                state=SectionState.DONE, attempt_id=uuid4(), data=empty_data
            )

        sidebar = _assemble_payload("https://test", empty)
        assert sidebar.web_risk.findings == []
        assert sidebar.image_moderation.matches == []
        assert sidebar.video_moderation.matches == []

    def test_safety_recommendation_column_flows_into_sidebar_payload(self):
        from src.analyses.safety._schemas import SafetyLevel
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload(
            "https://test",
            self._sections_with_new_safety(),
            {
                "level": "caution",
                "rationale": "Some inputs were unavailable.",
                "top_signals": ["web risk unavailable"],
                "unavailable_inputs": ["web_risk"],
            },
        )

        assert sidebar.safety.recommendation is not None
        assert sidebar.safety.recommendation.level == SafetyLevel.CAUTION
        assert sidebar.safety.recommendation.unavailable_inputs == ["web_risk"]

    def test_null_safety_recommendation_stays_none(self):
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload("https://test", self._sections_with_new_safety(), None)

        assert sidebar.safety.recommendation is None

    def test_headline_summary_column_flows_into_sidebar_payload(self):
        # TASK-1508.04.01: finalize inflates headline_summary onto SidebarPayload.
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload(
            "https://test",
            self._sections_with_new_safety(),
            None,
            {
                "text": "A perceptive opening line.",
                "kind": "synthesized",
                "unavailable_inputs": [],
            },
        )

        assert sidebar.headline is not None
        assert sidebar.headline.text == "A perceptive opening line."
        assert sidebar.headline.kind == "synthesized"

    def test_null_headline_summary_stays_none(self):
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload(
            "https://test", self._sections_with_new_safety(), None, None
        )

        assert sidebar.headline is None

    def test_headline_summary_accepts_json_string(self):
        # asyncpg may return the JSONB column as a raw string depending on codec
        # configuration; finalize must json.loads strings before validating.
        import json as _json

        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload(
            "https://test",
            self._sections_with_new_safety(),
            None,
            _json.dumps(
                {
                    "text": "Stock phrase.",
                    "kind": "stock",
                    "unavailable_inputs": ["scd"],
                }
            ),
        )

        assert sidebar.headline is not None
        assert sidebar.headline.kind == "stock"
        assert sidebar.headline.unavailable_inputs == ["scd"]

    def test_utterance_anchors_flow_into_sidebar_payload(self):
        from src.analyses.schemas import UtteranceAnchor
        from src.jobs.finalize import _assemble_payload

        sidebar = _assemble_payload(
            "https://test",
            self._sections_with_new_safety(),
            utterances=[
                UtteranceAnchor(position=1, utterance_id="comment-0-aaa"),
                UtteranceAnchor(position=2, utterance_id="comment-1-bbb"),
            ],
        )

        assert [anchor.utterance_id for anchor in sidebar.utterances] == [
            "comment-0-aaa",
            "comment-1-bbb",
        ]

    def test_url_cache_payload_drops_job_scoped_utterance_anchors(self):
        from src.analyses.schemas import UtteranceAnchor
        from src.jobs.finalize import _assemble_payload, _payload_for_url_cache

        sidebar = _assemble_payload(
            "https://test",
            self._sections_with_new_safety(),
            utterances=[
                UtteranceAnchor(position=1, utterance_id="comment-0-aaa"),
            ],
        )

        assert sidebar.utterances[0].utterance_id == "comment-0-aaa"
        cached = json.loads(_payload_for_url_cache(sidebar))
        assert cached["utterances"] == []
