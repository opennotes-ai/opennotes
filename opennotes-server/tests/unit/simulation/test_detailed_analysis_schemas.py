from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.simulation.schemas import (
    AgentBehaviorData,
    DetailedAnalysisMeta,
    DetailedAnalysisResponse,
    DetailedNoteData,
    DetailedNoteResource,
    DetailedRatingData,
    DetailedRequestData,
    RequestVarianceMeta,
)


@pytest.mark.unit
class TestDetailedRatingData:
    def test_valid_rating_data(self):
        rating = DetailedRatingData(
            rater_agent_name="Agent Alpha",
            rater_agent_instance_id="inst-001",
            helpfulness_level="HELPFUL",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert rating.rater_agent_name == "Agent Alpha"
        assert rating.rater_agent_instance_id == "inst-001"
        assert rating.helpfulness_level == "HELPFUL"
        assert rating.created_at is not None

    def test_rating_data_without_created_at(self):
        rating = DetailedRatingData(
            rater_agent_name="Agent Beta",
            rater_agent_instance_id="inst-002",
            helpfulness_level="NOT_HELPFUL",
        )
        assert rating.created_at is None

    def test_rating_data_serialization(self):
        rating = DetailedRatingData(
            rater_agent_name="Agent Alpha",
            rater_agent_instance_id="inst-001",
            helpfulness_level="SOMEWHAT_HELPFUL",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        dumped = rating.model_dump(mode="json")
        assert dumped["rater_agent_name"] == "Agent Alpha"
        assert dumped["helpfulness_level"] == "SOMEWHAT_HELPFUL"


@pytest.mark.unit
class TestDetailedNoteData:
    def test_valid_note_data(self):
        note = DetailedNoteData(
            note_id="note-001",
            summary="This claim is misleading",
            classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
            status="CURRENTLY_RATED_HELPFUL",
            helpfulness_score=75,
            author_agent_name="Agent Alpha",
            author_agent_instance_id="inst-001",
            request_id="req-001",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            ratings=[
                DetailedRatingData(
                    rater_agent_name="Agent Beta",
                    rater_agent_instance_id="inst-002",
                    helpfulness_level="HELPFUL",
                )
            ],
        )
        assert note.note_id == "note-001"
        assert note.classification == "MISINFORMED_OR_POTENTIALLY_MISLEADING"
        assert note.helpfulness_score == 75
        assert note.author_agent_name == "Agent Alpha"
        assert note.request_id == "req-001"
        assert len(note.ratings) == 1

    def test_note_data_defaults(self):
        note = DetailedNoteData(
            note_id="note-002",
            summary="Fact check",
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            helpfulness_score=0,
            author_agent_name="Agent Beta",
            author_agent_instance_id="inst-002",
        )
        assert note.request_id is None
        assert note.created_at is None
        assert note.ratings == []

    def test_note_data_serialization(self):
        note = DetailedNoteData(
            note_id="note-003",
            summary="Test note",
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            helpfulness_score=50,
            author_agent_name="Agent Gamma",
            author_agent_instance_id="inst-003",
            request_id="req-003",
        )
        dumped = note.model_dump(mode="json")
        assert dumped["note_id"] == "note-003"
        assert dumped["helpfulness_score"] == 50
        assert dumped["author_agent_name"] == "Agent Gamma"
        assert dumped["ratings"] == []

    def test_helpfulness_score_accepts_float(self):
        note = DetailedNoteData(
            note_id="note-float",
            summary="Float score note",
            classification="NOT_MISLEADING",
            status="CURRENTLY_RATED_HELPFUL",
            helpfulness_score=3.75,
            author_agent_name="Agent",
            author_agent_instance_id="inst-001",
        )
        assert note.helpfulness_score == 3.75
        dumped = note.model_dump(mode="json")
        assert dumped["helpfulness_score"] == 3.75

    def test_helpfulness_score_accepts_int_as_float(self):
        note = DetailedNoteData(
            note_id="note-int",
            summary="Int score note",
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            helpfulness_score=0,
            author_agent_name="Agent",
            author_agent_instance_id="inst-001",
        )
        assert isinstance(note.helpfulness_score, float)

    def test_message_metadata_with_source_url(self):
        metadata = {"source_url": "https://example.com/article", "platform": "discord"}
        note = DetailedNoteData(
            note_id="note-meta",
            summary="Note with metadata",
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            helpfulness_score=0,
            author_agent_name="Agent",
            author_agent_instance_id="inst-001",
            message_metadata=metadata,
        )
        assert note.message_metadata == metadata
        assert note.message_metadata["source_url"] == "https://example.com/article"
        dumped = note.model_dump(mode="json")
        assert dumped["message_metadata"]["source_url"] == "https://example.com/article"

    def test_message_metadata_defaults_to_none(self):
        note = DetailedNoteData(
            note_id="note-no-meta",
            summary="Note without metadata",
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            helpfulness_score=0,
            author_agent_name="Agent",
            author_agent_instance_id="inst-001",
        )
        assert note.message_metadata is None


@pytest.mark.unit
class TestDetailedRequestData:
    def test_valid_request_data(self):
        req = DetailedRequestData(
            request_id="req-001",
            content="https://example.com/article",
            content_type="image",
            note_count=3,
            variance_score=0.75,
        )
        assert req.request_id == "req-001"
        assert req.content == "https://example.com/article"
        assert req.content_type == "image"
        assert req.note_count == 3
        assert req.variance_score == 0.75

    def test_request_data_defaults(self):
        req = DetailedRequestData(request_id="req-002")
        assert req.content is None
        assert req.content_type is None
        assert req.note_count == 0
        assert req.variance_score == 0.0

    def test_request_data_text_content(self):
        req = DetailedRequestData(
            request_id="req-003",
            content="Breaking news: important claim about climate",
            content_type="text",
            note_count=5,
            variance_score=0.42,
        )
        assert req.content_type == "text"
        assert req.note_count == 5


@pytest.mark.unit
class TestDetailedNoteResource:
    def test_valid_resource(self):
        resource = DetailedNoteResource(
            id="note-001",
            attributes=DetailedNoteData(
                note_id="note-001",
                summary="Test note",
                classification="NOT_MISLEADING",
                status="NEEDS_MORE_RATINGS",
                helpfulness_score=0,
                author_agent_name="Agent Alpha",
                author_agent_instance_id="inst-001",
            ),
        )
        assert resource.type == "simulation-detailed-notes"
        assert resource.id == "note-001"
        assert resource.attributes.note_id == "note-001"

    def test_resource_serialization(self):
        resource = DetailedNoteResource(
            id="note-002",
            attributes=DetailedNoteData(
                note_id="note-002",
                summary="Another note",
                classification="NOT_MISLEADING",
                status="NEEDS_MORE_RATINGS",
                helpfulness_score=10,
                author_agent_name="Agent Beta",
                author_agent_instance_id="inst-002",
            ),
        )
        dumped = resource.model_dump(mode="json")
        assert dumped["type"] == "simulation-detailed-notes"
        assert dumped["id"] == "note-002"
        assert dumped["attributes"]["helpfulness_score"] == 10


@pytest.mark.unit
class TestRequestVarianceMeta:
    def test_valid_meta(self):
        meta = RequestVarianceMeta(
            requests=[
                DetailedRequestData(
                    request_id="req-001",
                    content="test",
                    content_type="text",
                    note_count=2,
                    variance_score=0.5,
                )
            ],
            total_requests=1,
        )
        assert len(meta.requests) == 1
        assert meta.total_requests == 1

    def test_empty_meta(self):
        meta = RequestVarianceMeta()
        assert meta.requests == []
        assert meta.total_requests == 0


@pytest.mark.unit
class TestDetailedAnalysisMeta:
    def test_typed_meta_with_variance(self):
        meta = DetailedAnalysisMeta(
            count=5,
            request_variance=RequestVarianceMeta(
                requests=[
                    DetailedRequestData(
                        request_id="req-001",
                        note_count=2,
                        variance_score=0.5,
                    )
                ],
                total_requests=1,
            ),
        )
        assert meta.count == 5
        assert meta.request_variance.total_requests == 1
        assert len(meta.request_variance.requests) == 1

    def test_typed_meta_defaults(self):
        meta = DetailedAnalysisMeta()
        assert meta.count == 0
        assert meta.request_variance.total_requests == 0
        assert meta.request_variance.requests == []

    def test_typed_meta_serialization(self):
        meta = DetailedAnalysisMeta(
            count=10,
            request_variance=RequestVarianceMeta(total_requests=3),
        )
        dumped = meta.model_dump(mode="json")
        assert dumped["count"] == 10
        assert dumped["request_variance"]["total_requests"] == 3


@pytest.mark.unit
class TestDetailedAnalysisResponse:
    def test_valid_response(self):
        response = DetailedAnalysisResponse(
            data=[
                DetailedNoteResource(
                    id="note-001",
                    attributes=DetailedNoteData(
                        note_id="note-001",
                        summary="Test note",
                        classification="NOT_MISLEADING",
                        status="NEEDS_MORE_RATINGS",
                        helpfulness_score=0,
                        author_agent_name="Agent Alpha",
                        author_agent_instance_id="inst-001",
                    ),
                )
            ],
            meta=DetailedAnalysisMeta(
                count=1,
                request_variance=RequestVarianceMeta(
                    requests=[
                        DetailedRequestData(
                            request_id="req-001",
                            note_count=1,
                            variance_score=0.0,
                        )
                    ],
                    total_requests=1,
                ),
            ),
        )
        assert response.jsonapi == {"version": "1.1"}
        assert len(response.data) == 1
        assert response.meta.request_variance.total_requests == 1

    def test_empty_response(self):
        response = DetailedAnalysisResponse(
            data=[],
            meta=DetailedAnalysisMeta(),
        )
        assert len(response.data) == 0
        assert response.meta.request_variance.total_requests == 0
        assert response.links is None

    def test_response_serialization(self):
        response = DetailedAnalysisResponse(
            data=[
                DetailedNoteResource(
                    id="note-001",
                    attributes=DetailedNoteData(
                        note_id="note-001",
                        summary="A test note",
                        classification="NOT_MISLEADING",
                        status="CURRENTLY_RATED_HELPFUL",
                        helpfulness_score=80,
                        author_agent_name="Agent Alpha",
                        author_agent_instance_id="inst-001",
                        request_id="req-001",
                        ratings=[
                            DetailedRatingData(
                                rater_agent_name="Agent Beta",
                                rater_agent_instance_id="inst-002",
                                helpfulness_level="HELPFUL",
                            )
                        ],
                    ),
                )
            ],
        )
        dumped = response.model_dump(by_alias=True, mode="json")
        assert dumped["jsonapi"]["version"] == "1.1"
        assert len(dumped["data"]) == 1
        assert dumped["data"][0]["type"] == "simulation-detailed-notes"
        assert dumped["data"][0]["attributes"]["ratings"][0]["rater_agent_name"] == "Agent Beta"


@pytest.mark.unit
class TestAgentBehaviorDataPersonality:
    def test_personality_field(self):
        behavior = AgentBehaviorData(
            agent_instance_id="inst-001",
            agent_name="Skeptic Agent",
            notes_written=5,
            ratings_given=3,
            turn_count=10,
            state="active",
            helpfulness_trend=["HELPFUL", "NOT_HELPFUL"],
            action_distribution={"write_note": 5, "rate_note": 3},
            personality="A skeptical fact-checker.",
        )
        assert behavior.personality == "A skeptical fact-checker."
        dumped = behavior.model_dump(mode="json")
        assert dumped["personality"] == "A skeptical fact-checker."

    def test_personality_defaults_to_empty_string(self):
        behavior = AgentBehaviorData(
            agent_instance_id="inst-002",
            agent_name="Agent",
            notes_written=0,
            ratings_given=0,
            turn_count=0,
            state="active",
            helpfulness_trend=[],
            action_distribution={},
        )
        assert behavior.personality == ""
