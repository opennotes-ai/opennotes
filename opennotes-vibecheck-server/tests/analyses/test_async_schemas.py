"""Behavior contracts for the async-pipeline schemas (TASK-1473.03, TASK-1474.02)."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.analyses.schemas import (
    ErrorCode,
    HeadlineSummary,
    ImageModerationSection,
    JobState,
    JobStatus,
    PageKind,
    RecentAnalysis,
    SectionSlot,
    SectionSlug,
    SectionState,
    SidebarPayload,
    VideoModerationSection,
    WebRiskSection,
)
from src.utterances.schema import Utterance


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
    def test_covers_all_sidebar_slots(self) -> None:
        assert {slug.value for slug in SectionSlug} == {
            "safety__moderation",
            "safety__web_risk",
            "safety__image_moderation",
            "safety__video_moderation",
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
    def test_covers_error_categories(self) -> None:
        assert {code.value for code in ErrorCode} == {
            "invalid_url",
            "unsafe_url",
            "unsupported_site",
            "upstream_error",
            "extraction_failed",
            "timeout",
            "rate_limited",
            "section_failure",
            "internal",
        }


class TestJobStatus:
    def test_covers_lifecycle_states(self) -> None:
        assert {status.value for status in JobStatus} == {
            "pending",
            "extracting",
            "analyzing",
            "done",
            "partial",
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

    def test_partial_job_carries_section_failure_and_sidebar_payload(self) -> None:
        sidebar = _empty_sidebar_payload(self._now())
        job = JobState(
            job_id=uuid4(),
            url="https://example.com",
            status=JobStatus.PARTIAL,
            attempt_id=uuid4(),
            error_code=ErrorCode.SECTION_FAILURE,
            error_message="Sections failed: safety__web_risk",
            created_at=self._now(),
            updated_at=self._now(),
            sidebar_payload=sidebar,
        )
        assert job.status is JobStatus.PARTIAL
        assert job.error_code is ErrorCode.SECTION_FAILURE
        assert job.sidebar_payload is not None

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

    def test_sidebar_payload_complete_defaults_to_false(self) -> None:
        job = JobState(
            job_id=uuid4(),
            url="https://example.com",
            status=JobStatus.ANALYZING,
            attempt_id=uuid4(),
            created_at=self._now(),
            updated_at=self._now(),
        )
        assert job.sidebar_payload_complete is False

    def test_terminal_job_may_set_sidebar_payload_complete_true(self) -> None:
        sidebar = _empty_sidebar_payload(self._now())
        job = JobState(
            job_id=uuid4(),
            url="https://example.com",
            status=JobStatus.DONE,
            attempt_id=uuid4(),
            created_at=self._now(),
            updated_at=self._now(),
            sidebar_payload=sidebar,
            sidebar_payload_complete=True,
        )
        assert job.sidebar_payload_complete is True
        assert job.sidebar_payload is not None

    def test_activity_fields_default_to_none(self) -> None:
        job = JobState(
            job_id=uuid4(),
            url="https://example.com",
            status=JobStatus.PENDING,
            attempt_id=uuid4(),
            created_at=self._now(),
            updated_at=self._now(),
        )
        assert job.activity_at is None
        assert job.activity_label is None

    def test_activity_fields_may_be_populated(self) -> None:
        now = self._now()
        job = JobState(
            job_id=uuid4(),
            url="https://example.com",
            status=JobStatus.ANALYZING,
            attempt_id=uuid4(),
            created_at=now,
            updated_at=now,
            activity_at=now,
            activity_label="Scoring safety section",
        )
        assert job.activity_at == now
        assert job.activity_label == "Scoring safety section"


class TestSidebarPayloadPageKindUpgrade:
    """SidebarPayload now accepts the expanded PageKind set."""

    def test_accepts_hierarchical_thread(self) -> None:
        sidebar = _empty_sidebar_payload(
            datetime.now(UTC),
            page_kind=PageKind.HIERARCHICAL_THREAD,
            source_url="https://forum.example.com/t/x",
        )
        assert sidebar.page_kind is PageKind.HIERARCHICAL_THREAD


class TestSectionSlugNewMembers:
    def test_section_slug_has_new_web_risk_member(self) -> None:
        assert SectionSlug("safety__web_risk") is SectionSlug.SAFETY_WEB_RISK

    def test_section_slug_has_new_image_moderation_member(self) -> None:
        assert SectionSlug("safety__image_moderation") is SectionSlug.SAFETY_IMAGE_MODERATION

    def test_section_slug_has_new_video_moderation_member(self) -> None:
        assert SectionSlug("safety__video_moderation") is SectionSlug.SAFETY_VIDEO_MODERATION


class TestErrorCodeNewMembers:
    def test_error_code_has_unsafe_url(self) -> None:
        assert ErrorCode("unsafe_url") is ErrorCode.UNSAFE_URL


class TestSidebarPayloadNewSections:
    def test_sidebar_payload_round_trips_new_sections_with_defaults(self) -> None:
        sidebar = _empty_sidebar_payload(datetime.now(UTC))
        assert sidebar.web_risk == WebRiskSection()
        assert sidebar.image_moderation == ImageModerationSection()
        assert sidebar.video_moderation == VideoModerationSection()

    def test_sidebar_payload_web_risk_defaults_to_empty_findings(self) -> None:
        sidebar = _empty_sidebar_payload(datetime.now(UTC))
        assert sidebar.web_risk.findings == []

    def test_sidebar_payload_image_moderation_defaults_to_empty_matches(self) -> None:
        sidebar = _empty_sidebar_payload(datetime.now(UTC))
        assert sidebar.image_moderation.matches == []

    def test_sidebar_payload_video_moderation_defaults_to_empty_matches(self) -> None:
        sidebar = _empty_sidebar_payload(datetime.now(UTC))
        assert sidebar.video_moderation.matches == []


class TestRecentAnalysis:
    """Behavior contracts for the gallery card response shape (TASK-1485.01)."""

    def _full_payload(self) -> dict[str, object]:
        return {
            "job_id": str(uuid4()),
            "source_url": "https://example.com/post",
            "page_title": "Example Post",
            "screenshot_url": "https://signed.example.com/blob.png?token=abc",
            "preview_description": "Top safety hit: hate speech, 0.92 confidence.",
            "completed_at": datetime.now(UTC).isoformat(),
        }

    def test_full_payload_validates_and_round_trips(self) -> None:
        payload = self._full_payload()
        analysis = RecentAnalysis.model_validate(payload)
        round_tripped = RecentAnalysis.model_validate(analysis.model_dump(mode="json"))
        assert round_tripped.source_url == payload["source_url"]
        assert round_tripped.preview_description == payload["preview_description"]

    def test_page_title_optional_defaults_to_none(self) -> None:
        payload = self._full_payload()
        del payload["page_title"]
        analysis = RecentAnalysis.model_validate(payload)
        assert analysis.page_title is None

    def test_missing_job_id_raises(self) -> None:
        payload = self._full_payload()
        del payload["job_id"]
        with pytest.raises(ValidationError, match="job_id"):
            RecentAnalysis.model_validate(payload)

    def test_missing_source_url_raises(self) -> None:
        payload = self._full_payload()
        del payload["source_url"]
        with pytest.raises(ValidationError, match="source_url"):
            RecentAnalysis.model_validate(payload)

    def test_missing_screenshot_url_raises(self) -> None:
        payload = self._full_payload()
        del payload["screenshot_url"]
        with pytest.raises(ValidationError, match="screenshot_url"):
            RecentAnalysis.model_validate(payload)

    def test_missing_completed_at_raises(self) -> None:
        payload = self._full_payload()
        del payload["completed_at"]
        with pytest.raises(ValidationError, match="completed_at"):
            RecentAnalysis.model_validate(payload)

    def test_preview_description_non_null_at_api_boundary(self) -> None:
        """Display contract: every card has preview text. None must reject."""
        payload = self._full_payload()
        payload["preview_description"] = None
        with pytest.raises(ValidationError, match="preview_description"):
            RecentAnalysis.model_validate(payload)

    def test_long_preview_description_validates(self) -> None:
        """Soft 140-char cap is enforced at the write side, not in the schema."""
        payload = self._full_payload()
        payload["preview_description"] = "x" * 500
        analysis = RecentAnalysis.model_validate(payload)
        assert len(analysis.preview_description) == 500


class TestHeadlineSummary:
    """Schema spine for the synthesized headline summation (TASK-1508.04.01)."""

    def test_synthesized_headline_round_trips(self) -> None:
        headline = HeadlineSummary(
            text="A clever synthesis sentence.",
            kind="synthesized",
            unavailable_inputs=[],
        )
        round_tripped = HeadlineSummary.model_validate_json(headline.model_dump_json())
        assert round_tripped == headline

    def test_stock_headline_round_trips(self) -> None:
        headline = HeadlineSummary(
            text="Nothing of note in this content.",
            kind="stock",
            unavailable_inputs=["scd"],
        )
        round_tripped = HeadlineSummary.model_validate_json(headline.model_dump_json())
        assert round_tripped == headline
        assert round_tripped.unavailable_inputs == ["scd"]

    def test_unavailable_inputs_default_is_empty(self) -> None:
        headline = HeadlineSummary(text="x", kind="stock")
        assert headline.unavailable_inputs == []

    def test_invalid_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HeadlineSummary.model_validate(
                {"text": "x", "kind": "freeform", "unavailable_inputs": []}
            )

    def test_sidebar_payload_headline_defaults_to_none(self) -> None:
        sidebar = _empty_sidebar_payload(datetime.now(UTC))
        assert sidebar.headline is None

    def test_sidebar_payload_with_headline_round_trips(self) -> None:
        base = _empty_sidebar_payload(datetime.now(UTC))
        with_headline = base.model_copy(
            update={
                "headline": HeadlineSummary(
                    text="Clever opening line.",
                    kind="synthesized",
                    unavailable_inputs=[],
                )
            }
        )
        round_tripped = SidebarPayload.model_validate_json(with_headline.model_dump_json())
        assert round_tripped.headline is not None
        assert round_tripped.headline.text == "Clever opening line."
        assert round_tripped.headline.kind == "synthesized"

    def test_sidebar_payload_legacy_blob_without_headline_validates(self) -> None:
        # Existing cached SidebarPayload blobs predate the headline field; they
        # must keep deserializing with headline defaulting to None.
        base = _empty_sidebar_payload(datetime.now(UTC))
        legacy_blob = base.model_dump(mode="json")
        legacy_blob.pop("headline", None)
        assert "headline" not in legacy_blob
        round_tripped = SidebarPayload.model_validate(legacy_blob)
        assert round_tripped.headline is None


class TestUtteranceNewMediaFields:
    def test_utterance_defaults_mentioned_lists_to_empty(self) -> None:
        utterance = Utterance(kind="post", text="hello world")
        assert utterance.mentioned_urls == []
        assert utterance.mentioned_images == []
        assert utterance.mentioned_videos == []

    def test_utterance_accepts_mentioned_urls(self) -> None:
        utterance = Utterance(
            kind="post",
            text="check this out",
            mentioned_urls=["https://example.com"],
        )
        assert utterance.mentioned_urls == ["https://example.com"]

    def test_utterance_accepts_mentioned_images(self) -> None:
        utterance = Utterance(
            kind="post",
            text="see image",
            mentioned_images=["https://example.com/img.jpg"],
        )
        assert utterance.mentioned_images == ["https://example.com/img.jpg"]

    def test_utterance_accepts_mentioned_videos(self) -> None:
        utterance = Utterance(
            kind="post",
            text="watch video",
            mentioned_videos=["https://example.com/video.mp4"],
        )
        assert utterance.mentioned_videos == ["https://example.com/video.mp4"]
