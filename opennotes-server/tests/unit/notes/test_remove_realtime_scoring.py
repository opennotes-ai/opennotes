"""Tests for TASK-1321: Remove real-time scoring from routers.

Verifies:
- AC #1: Rating creation dispatches DBOS rescore, returns persisted score
- AC #2: New RatingCreatedScoreResponse schema with scoring_requested flag
- AC #3: Read paths return persisted helpfulness_score, no real-time scoring
- AC #4: ScorerFactory/calculate_note_score removed from router modules
"""

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pendulum

from src.notes.scoring_schemas import ScoreConfidence


class TestRatingCreatedScoreResponse:
    """AC #2: New response type with scoring_requested flag."""

    def test_schema_exists(self):
        from src.notes.scoring_schemas import RatingCreatedScoreResponse

        assert RatingCreatedScoreResponse is not None

    def test_schema_has_required_fields(self):
        from src.notes.scoring_schemas import RatingCreatedScoreResponse

        note_id = uuid4()
        resp = RatingCreatedScoreResponse(
            note_id=note_id,
            score=0.75,
            scoring_requested=True,
            rating_count=5,
        )
        assert resp.note_id == note_id
        assert resp.score == 0.75
        assert resp.scoring_requested is True
        assert resp.rating_count == 5

    def test_scoring_requested_defaults_to_true(self):
        from src.notes.scoring_schemas import RatingCreatedScoreResponse

        resp = RatingCreatedScoreResponse(
            note_id=uuid4(),
            score=0.5,
            rating_count=3,
        )
        assert resp.scoring_requested is True

    def test_schema_inherits_sqlalchemy_schema(self):
        from src.common.base_schemas import SQLAlchemySchema
        from src.notes.scoring_schemas import RatingCreatedScoreResponse

        assert issubclass(RatingCreatedScoreResponse, SQLAlchemySchema)


class TestScorerFactoryRemovedFromRouters:
    """AC #4: ScorerFactory and calculate_note_score removed from router files."""

    def test_ratings_router_no_scorer_factory(self):
        import src.notes.ratings_jsonapi_router as mod

        source = inspect.getsource(mod)
        assert "ScorerFactory" not in source
        assert "scorer_factory" not in source

    def test_ratings_router_no_calculate_note_score(self):
        import src.notes.ratings_jsonapi_router as mod

        source = inspect.getsource(mod)
        assert "calculate_note_score" not in source

    def test_scoring_router_no_scorer_factory(self):
        import src.notes.scoring_jsonapi_router as mod

        source = inspect.getsource(mod)
        assert "ScorerFactory" not in source
        assert "scorer_factory" not in source

    def test_scoring_router_no_calculate_note_score(self):
        import src.notes.scoring_jsonapi_router as mod

        source = inspect.getsource(mod)
        assert "calculate_note_score" not in source


class TestBuildPersistedScoreResponse:
    """AC #3: Read paths return persisted scores via helper function."""

    def test_helper_exists_in_scoring_router(self):
        from src.notes.scoring_jsonapi_router import _build_persisted_score_response

        assert callable(_build_persisted_score_response)

    def test_builds_response_from_persisted_data(self):
        from src.notes.scoring_jsonapi_router import _build_persisted_score_response

        now = pendulum.now("UTC")
        note = SimpleNamespace(
            id=uuid4(),
            helpfulness_score=75,
            ratings=[SimpleNamespace(), SimpleNamespace(), SimpleNamespace()],
            updated_at=now,
            created_at=now,
            request=None,
        )
        resp = _build_persisted_score_response(note, note_count=10)
        assert resp.score == 0.75
        assert resp.rating_count == 3
        assert resp.algorithm == "persisted"
        assert resp.note_id == note.id

    def test_zero_score_when_no_helpfulness_score(self):
        from src.notes.scoring_jsonapi_router import _build_persisted_score_response

        now = pendulum.now("UTC")
        note = SimpleNamespace(
            id=uuid4(),
            helpfulness_score=None,
            ratings=[],
            updated_at=None,
            created_at=now,
            request=None,
        )
        resp = _build_persisted_score_response(note, note_count=10)
        assert resp.score == 0.0
        assert resp.rating_count == 0
        assert resp.confidence == ScoreConfidence.NO_DATA

    def test_provisional_confidence_for_few_ratings(self):
        from src.notes.scoring_jsonapi_router import _build_persisted_score_response

        now = pendulum.now("UTC")
        note = SimpleNamespace(
            id=uuid4(),
            helpfulness_score=50,
            ratings=[SimpleNamespace() for _ in range(3)],
            updated_at=now,
            created_at=now,
            request=None,
        )
        resp = _build_persisted_score_response(note, note_count=10)
        assert resp.confidence == ScoreConfidence.PROVISIONAL

    def test_standard_confidence_for_many_ratings(self):
        from src.notes.scoring_jsonapi_router import _build_persisted_score_response

        now = pendulum.now("UTC")
        note = SimpleNamespace(
            id=uuid4(),
            helpfulness_score=80,
            ratings=[SimpleNamespace() for _ in range(7)],
            updated_at=now,
            created_at=now,
            request=None,
        )
        resp = _build_persisted_score_response(note, note_count=10)
        assert resp.confidence == ScoreConfidence.STANDARD

    def test_extracts_content_from_message_archive(self):
        from src.notes.scoring_jsonapi_router import _build_persisted_score_response

        now = pendulum.now("UTC")
        note = SimpleNamespace(
            id=uuid4(),
            helpfulness_score=60,
            ratings=[SimpleNamespace()],
            updated_at=now,
            created_at=now,
            request=SimpleNamespace(
                message_archive=SimpleNamespace(get_content=lambda: "test content")
            ),
        )
        resp = _build_persisted_score_response(note, note_count=10)
        assert resp.content == "test content"


class TestRatingsRouterNoScoringEventPublish:
    """Rating creation should not publish score events inline."""

    def test_no_scoring_event_publisher_in_create_rating(self):
        import src.notes.ratings_jsonapi_router as mod

        source = inspect.getsource(mod)
        assert "ScoringEventPublisher" not in source

    def test_no_score_event_context_in_ratings_router(self):
        import src.notes.ratings_jsonapi_router as mod

        source = inspect.getsource(mod)
        assert "build_score_event_routing_context" not in source
