"""Behavior contracts for the async-pipeline schemas (TASK-1473.03)."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.analyses.schemas import (
    ErrorCode,
    JobState,
    JobStatus,
    PageKind,
    SectionSlot,
    SectionSlug,
    SectionState,
    SidebarPayload,
)


def _empty_sidebar_payload(
    scraped_at: datetime,
    *,
    page_kind: PageKind = PageKind.OTHER,
    source_url: str = "https://example.com",
) -> SidebarPayload:
    return SidebarPayload.model_validate(
        {
            "source_url": source_url,
            "scraped_at": scraped_at.isoformat(),
            "page_kind": page_kind.value,
            "safety": {"harmful_content_matches": []},
            "tone_dynamics": {
                "scd": {
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
        }
    )


class TestSectionSlug:
    def test_covers_all_seven_sidebar_slots(self) -> None:
        assert {slug.value for slug in SectionSlug} == {
            "safety__moderation",
            "tone_dynamics__flashpoint",
            "tone_dynamics__scd",
            "facts_claims__dedup",
            "facts_claims__known_misinfo",
            "opinions_sentiments__sentiment",
            "opinions_sentiments__subjective",
        }

    def test_round_trip_through_string(self) -> None:
        assert SectionSlug("safety__moderation") is SectionSlug.SAFETY_MODERATION


class TestErrorCode:
    def test_covers_seven_error_categories(self) -> None:
        assert {code.value for code in ErrorCode} == {
            "invalid_url",
            "unsupported_site",
            "upstream_error",
            "extraction_failed",
            "timeout",
            "rate_limited",
            "internal",
        }


class TestJobStatus:
    def test_covers_five_lifecycle_states(self) -> None:
        assert {status.value for status in JobStatus} == {
            "pending",
            "extracting",
            "analyzing",
            "done",
            "failed",
        }


class TestSectionState:
    def test_covers_four_slot_states(self) -> None:
        assert {state.value for state in SectionState} == {
            "pending",
            "running",
            "done",
            "failed",
        }


class TestPageKind:
    def test_includes_hierarchical_thread_and_blog_index(self) -> None:
        values = {kind.value for kind in PageKind}
        assert "hierarchical_thread" in values
        assert "blog_index" in values
        assert "blog_post" in values
        assert "forum_thread" in values


class TestSectionSlot:
    def test_minimal_pending_slot(self) -> None:
        slot = SectionSlot(state=SectionState.PENDING, attempt_id=uuid4())
        assert slot.data is None
        assert slot.error is None
        assert slot.started_at is None
        assert slot.finished_at is None

    def test_done_slot_carries_data_and_finished_at(self) -> None:
        finished = datetime.now(UTC)
        slot = SectionSlot(
            state=SectionState.DONE,
            attempt_id=uuid4(),
            data={"summary": "ok"},
            started_at=finished,
            finished_at=finished,
        )
        assert slot.data == {"summary": "ok"}

    def test_failed_slot_carries_error_message(self) -> None:
        slot = SectionSlot(
            state=SectionState.FAILED,
            attempt_id=uuid4(),
            error="upstream returned 500",
        )
        assert slot.error == "upstream returned 500"


class TestJobState:
    def _now(self) -> datetime:
        return datetime.now(UTC)

    def test_minimal_pending_job_round_trips_via_dict(self) -> None:
        now = self._now()
        payload = {
            "job_id": str(uuid4()),
            "url": "https://example.com",
            "status": "pending",
            "attempt_id": str(uuid4()),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "sections": {},
            "next_poll_ms": 500,
        }
        job = JobState.model_validate(payload)
        assert job.status is JobStatus.PENDING
        assert job.cached is False
        assert job.next_poll_ms == 500

    def test_failed_job_with_unsupported_site_carries_host(self) -> None:
        job = JobState(
            job_id=uuid4(),
            url="https://forbidden.example.com/x",
            status=JobStatus.FAILED,
            attempt_id=uuid4(),
            error_code=ErrorCode.UNSUPPORTED_SITE,
            error_message="host not on allowlist",
            error_host="forbidden.example.com",
            created_at=self._now(),
            updated_at=self._now(),
        )
        assert job.error_code is ErrorCode.UNSUPPORTED_SITE
        assert job.error_host == "forbidden.example.com"

    def test_done_job_carries_sidebar_payload_and_section_map(self) -> None:
        slot = SectionSlot(state=SectionState.DONE, attempt_id=uuid4())
        sidebar = _empty_sidebar_payload(self._now())
        job = JobState(
            job_id=uuid4(),
            url="https://example.com",
            status=JobStatus.DONE,
            attempt_id=uuid4(),
            created_at=self._now(),
            updated_at=self._now(),
            sections={SectionSlug.SAFETY_MODERATION: slot},
            sidebar_payload=sidebar,
            cached=True,
        )
        assert SectionSlug.SAFETY_MODERATION in job.sections
        assert job.sidebar_payload is not None
        assert job.cached is True

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValueError, match="status"):
            JobState.model_validate(
                {
                    "job_id": str(uuid4()),
                    "url": "x",
                    "status": "bogus",
                    "attempt_id": str(uuid4()),
                    "created_at": self._now().isoformat(),
                    "updated_at": self._now().isoformat(),
                }
            )


class TestSidebarPayloadPageKindUpgrade:
    """SidebarPayload now accepts the expanded PageKind set."""

    def test_accepts_hierarchical_thread(self) -> None:
        sidebar = _empty_sidebar_payload(
            datetime.now(UTC),
            page_kind=PageKind.HIERARCHICAL_THREAD,
            source_url="https://forum.example.com/t/x",
        )
        assert sidebar.page_kind is PageKind.HIERARCHICAL_THREAD
