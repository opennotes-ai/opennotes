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


class TestUpdateRatingDispatchesScoring:
    """TASK-1321.01: update_rating_jsonapi dispatches DBOS rescore."""

    def test_update_path_calls_dispatch_community_scoring(self):
        import src.notes.ratings_jsonapi_router as mod

        source = inspect.getsource(mod.update_rating_jsonapi)
        assert "dispatch_community_scoring" in source

    def test_update_path_includes_scoring_requested_in_log(self):
        import src.notes.ratings_jsonapi_router as mod

        source = inspect.getsource(mod.update_rating_jsonapi)
        assert "scoring_requested" in source

    def test_update_path_loads_note_for_community_server_id(self):
        import src.notes.ratings_jsonapi_router as mod

        source = inspect.getsource(mod.update_rating_jsonapi)
        assert "note.community_server_id" in source

    def test_update_path_handles_dispatch_failure(self):
        import src.notes.ratings_jsonapi_router as mod

        source = inspect.getsource(mod.update_rating_jsonapi)
        assert "Failed to dispatch DBOS rescore workflow after rating update" in source


class TestCreateRatingMissingCommunityServerWarning:
    """TASK-1321.02: create_rating_jsonapi warns when note has no community_server_id."""

    def test_create_path_has_else_branch_for_missing_community_server(self):
        import src.notes.ratings_jsonapi_router as mod

        source = inspect.getsource(mod.create_rating_jsonapi)
        assert "Skipping scoring dispatch: note has no community_server_id" in source

    def test_update_path_has_else_branch_for_missing_community_server(self):
        import src.notes.ratings_jsonapi_router as mod

        source = inspect.getsource(mod.update_rating_jsonapi)
        assert "Skipping scoring dispatch: note has no community_server_id" in source
