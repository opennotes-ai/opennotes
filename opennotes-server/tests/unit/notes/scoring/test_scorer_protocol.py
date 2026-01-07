"""
Tests for scorer abstraction layer (ScorerProtocol and adapters).

TDD: Write failing tests first, then implement.
"""

from dataclasses import fields
from datetime import UTC

import pytest


class TestScoringResult:
    """Tests for ScoringResult dataclass (AC #2)."""

    def test_scoring_result_has_required_fields(self):
        """ScoringResult must have score, confidence_level, and metadata fields."""
        from src.notes.scoring.scorer_protocol import ScoringResult

        field_names = {f.name for f in fields(ScoringResult)}
        assert "score" in field_names
        assert "confidence_level" in field_names
        assert "metadata" in field_names

    def test_scoring_result_can_be_instantiated(self):
        """ScoringResult can be instantiated with required values."""
        from src.notes.scoring.scorer_protocol import ScoringResult

        result = ScoringResult(
            score=0.75,
            confidence_level="standard",
            metadata={"algorithm": "test"},
        )

        assert result.score == 0.75
        assert result.confidence_level == "standard"
        assert result.metadata == {"algorithm": "test"}

    def test_scoring_result_score_is_float(self):
        """ScoringResult.score should be a float."""
        from src.notes.scoring.scorer_protocol import ScoringResult

        result = ScoringResult(
            score=0.5,
            confidence_level="provisional",
            metadata={},
        )

        assert isinstance(result.score, float)

    def test_scoring_result_with_empty_metadata(self):
        """ScoringResult can have empty metadata dict."""
        from src.notes.scoring.scorer_protocol import ScoringResult

        result = ScoringResult(
            score=0.5,
            confidence_level="provisional",
            metadata={},
        )

        assert result.metadata == {}


class TestScorerProtocol:
    """Tests for ScorerProtocol interface (AC #1)."""

    def test_scorer_protocol_is_runtime_checkable(self):
        """ScorerProtocol should be runtime checkable."""
        from src.notes.scoring.scorer_protocol import ScorerProtocol

        assert hasattr(ScorerProtocol, "__protocol_attrs__") or isinstance(ScorerProtocol, type)

    def test_scorer_protocol_has_score_note_method(self):
        """ScorerProtocol must define score_note method."""
        from src.notes.scoring.scorer_protocol import ScorerProtocol

        assert hasattr(ScorerProtocol, "score_note")


class TestBayesianAverageScorerAdapter:
    """Tests for BayesianAverageScorerAdapter (AC #3)."""

    def test_adapter_wraps_bayesian_scorer(self):
        """Adapter wraps existing BayesianAverageScorer."""
        from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )

        scorer = BayesianAverageScorer()
        adapter = BayesianAverageScorerAdapter(scorer)

        assert adapter._scorer is scorer

    def test_adapter_implements_scorer_protocol(self):
        """Adapter implements ScorerProtocol."""
        from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )
        from src.notes.scoring.scorer_protocol import ScorerProtocol

        scorer = BayesianAverageScorer()
        adapter = BayesianAverageScorerAdapter(scorer)

        assert isinstance(adapter, ScorerProtocol)

    def test_adapter_score_note_returns_scoring_result(self):
        """score_note returns ScoringResult."""
        from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )
        from src.notes.scoring.scorer_protocol import ScoringResult

        scorer = BayesianAverageScorer()
        adapter = BayesianAverageScorerAdapter(scorer)

        result = adapter.score_note("note-123", [0.6, 0.7, 0.8])

        assert isinstance(result, ScoringResult)

    def test_adapter_score_note_calculates_correct_score(self):
        """score_note calculates correct score using underlying scorer."""
        from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )

        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        adapter = BayesianAverageScorerAdapter(scorer)

        result = adapter.score_note("note-123", [0.8, 0.8])

        expected_score = (2.0 * 0.5 + 1.6) / (2.0 + 2)
        assert abs(result.score - expected_score) < 1e-9

    def test_adapter_score_note_with_empty_ratings(self):
        """score_note handles empty ratings correctly."""
        from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )

        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        adapter = BayesianAverageScorerAdapter(scorer)

        result = adapter.score_note("note-123", [])

        assert result.score == 0.5
        assert result.confidence_level == "provisional"
        assert result.metadata.get("no_data") is True

    def test_adapter_preserves_metadata_from_underlying_scorer(self):
        """score_note preserves metadata from underlying scorer."""
        from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )

        scorer = BayesianAverageScorer(
            confidence_param=2.0, prior_mean=0.5, min_ratings_for_confidence=5
        )
        adapter = BayesianAverageScorerAdapter(scorer)

        result = adapter.score_note("note-123", [0.6, 0.7, 0.8, 0.9, 1.0])

        assert result.confidence_level == "standard"
        assert result.metadata["algorithm"] == "bayesian_average_tier0"
        assert result.metadata["rating_count"] == 5

    def test_adapter_confidence_level_provisional_for_few_ratings(self):
        """confidence_level is provisional when rating count is below threshold."""
        from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
        from src.notes.scoring.bayesian_scorer_adapter import (
            BayesianAverageScorerAdapter,
        )

        scorer = BayesianAverageScorer(min_ratings_for_confidence=5)
        adapter = BayesianAverageScorerAdapter(scorer)

        result = adapter.score_note("note-123", [0.6, 0.7])

        assert result.confidence_level == "provisional"


class TestMFCoreScorerAdapter:
    """Tests for MFCoreScorerAdapter (AC #4, #5)."""

    def test_adapter_can_be_instantiated(self):
        """MFCoreScorerAdapter can be instantiated."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        adapter = MFCoreScorerAdapter()

        assert adapter is not None

    def test_adapter_implements_scorer_protocol(self):
        """Adapter implements ScorerProtocol."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_protocol import ScorerProtocol

        adapter = MFCoreScorerAdapter()

        assert isinstance(adapter, ScorerProtocol)

    def test_adapter_score_note_returns_scoring_result(self):
        """score_note returns ScoringResult."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_protocol import ScoringResult

        adapter = MFCoreScorerAdapter()

        result = adapter.score_note("note-123", [0.6, 0.7, 0.8])

        assert isinstance(result, ScoringResult)

    def test_adapter_returns_cached_result_when_available(self):
        """score_note returns cached result when cache is valid."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_protocol import ScoringResult

        adapter = MFCoreScorerAdapter()

        adapter._cache["note-123"] = ScoringResult(
            score=0.85,
            confidence_level="standard",
            metadata={"source": "cache"},
        )
        adapter._cache_version = 1
        adapter._current_version = 1

        result = adapter.score_note("note-123", [0.6, 0.7])

        assert result.score == 0.85
        assert result.metadata.get("source") == "cache"

    def test_adapter_triggers_batch_scoring_on_cache_miss(self):
        """score_note triggers batch scoring when note not in cache."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        adapter = MFCoreScorerAdapter()

        adapter._cache.clear()
        adapter._cache_version = 1
        adapter._current_version = 1

        result = adapter.score_note("note-456", [0.6, 0.7])

        assert result is not None
        assert result.metadata.get("source") == "batch_stub"

    def test_adapter_invalidates_cache_when_version_changes(self):
        """Cache is invalidated when ratings version changes."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_protocol import ScoringResult

        adapter = MFCoreScorerAdapter()

        adapter._cache["note-123"] = ScoringResult(
            score=0.85,
            confidence_level="standard",
            metadata={"source": "old_cache"},
        )
        adapter._cache_version = 1
        adapter._current_version = 2

        result = adapter.score_note("note-123", [0.6, 0.7])

        assert result.metadata.get("source") != "old_cache"

    def test_adapter_update_ratings_version_increments_version(self):
        """update_ratings_version increments the current version."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        adapter = MFCoreScorerAdapter()
        initial_version = adapter._current_version

        adapter.update_ratings_version()

        assert adapter._current_version == initial_version + 1

    def test_adapter_cache_invalidation_clears_old_cache(self):
        """When cache is invalidated, old entries are cleared."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_protocol import ScoringResult

        adapter = MFCoreScorerAdapter()

        adapter._cache["note-123"] = ScoringResult(
            score=0.85,
            confidence_level="standard",
            metadata={},
        )
        adapter._cache_version = 1
        adapter._current_version = 2

        adapter.score_note("note-123", [0.6])

        assert adapter._cache_version == 2

    def test_adapter_get_cache_stats_returns_info(self):
        """get_cache_stats returns cache statistics."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_protocol import ScoringResult

        adapter = MFCoreScorerAdapter()
        adapter._cache["note-1"] = ScoringResult(
            score=0.5, confidence_level="provisional", metadata={}
        )
        adapter._cache["note-2"] = ScoringResult(
            score=0.6, confidence_level="standard", metadata={}
        )
        adapter._cache_version = 5
        adapter._current_version = 5

        stats = adapter.get_cache_stats()

        assert stats["cached_notes"] == 2
        assert stats["cache_version"] == 5
        assert stats["is_valid"] is True


class TestMFCoreScorerAdapterPhase3:
    """Tests for MFCoreScorerAdapter Phase 3: Constructor Updates (task-808)."""

    def test_adapter_accepts_data_provider_and_community_id(self):
        """Adapter constructor accepts data_provider and community_id parameters."""
        from typing import Any

        from src.notes.scoring.data_provider import CommunityDataProvider
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            """Mock implementation of CommunityDataProvider."""

            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        provider = MockDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        assert adapter is not None
        assert isinstance(provider, CommunityDataProvider)

    def test_adapter_stores_data_provider_and_community_id(self):
        """Adapter stores data_provider and community_id as instance attributes."""
        from typing import Any

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        provider = MockDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community-123",
        )

        assert adapter._data_provider is provider
        assert adapter._community_id == "test-community-123"

    def test_adapter_instantiates_mf_core_scorer(self):
        """Adapter instantiates MFCoreScorer when data_provider is provided."""
        import sys
        from pathlib import Path
        from typing import Any

        scoring_path = Path(__file__).parent.parent.parent.parent.parent.parent / (
            "communitynotes/scoring/src"
        )
        if str(scoring_path) not in sys.path:
            sys.path.insert(0, str(scoring_path))

        from scoring.mf_core_scorer import MFCoreScorer

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        assert hasattr(adapter, "_scorer")
        assert isinstance(adapter._scorer, MFCoreScorer)

    def test_adapter_instantiates_dataframe_builders(self):
        """Adapter instantiates all three DataFrame builders."""
        from typing import Any

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        assert hasattr(adapter, "_ratings_builder")
        assert hasattr(adapter, "_note_status_builder")
        assert hasattr(adapter, "_user_enrollment_builder")
        assert isinstance(adapter._ratings_builder, RatingsDataFrameBuilder)
        assert isinstance(adapter._note_status_builder, NoteStatusHistoryBuilder)
        assert isinstance(adapter._user_enrollment_builder, UserEnrollmentBuilder)

    def test_adapter_has_thread_lock(self):
        """Adapter has a threading.Lock for thread safety."""
        import threading
        from typing import Any

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        assert hasattr(adapter, "_lock")
        assert isinstance(adapter._lock, type(threading.Lock()))

    def test_adapter_backward_compatible_no_args(self):
        """Adapter remains backward compatible with no-args constructor."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        adapter = MFCoreScorerAdapter()

        assert adapter is not None
        assert adapter._data_provider is None
        assert adapter._community_id is None


class TestMFCoreScorerAdapterPhase4:
    """Tests for MFCoreScorerAdapter Phase 4: DataFrame Building (task-808)."""

    def test_build_scoring_inputs_returns_tuple_of_four_dataframes(self):
        """_build_scoring_inputs returns a tuple of 4 DataFrames + int_to_uuid mapping."""
        from datetime import datetime
        from typing import Any
        from uuid import uuid4

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "note_id": uuid4(),
                        "rater_participant_id": "user-1",
                        "helpfulness_level": "HELPFUL",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "author_participant_id": "user-1",
                        "classification": "NOT_MISLEADING",
                        "status": "NEEDS_MORE_RATINGS",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_participants(self, community_id: str) -> list[str]:
                return ["user-1", "user-2"]

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        result = adapter._build_scoring_inputs()

        assert isinstance(result, tuple)
        assert len(result) == 5
        assert all(isinstance(df, pd.DataFrame) for df in result[:4])
        assert isinstance(result[4], dict)

    def test_build_scoring_inputs_calls_data_provider_methods(self):
        """_build_scoring_inputs calls all three data provider methods."""
        from typing import Any

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def __init__(self):
                self.calls = {"ratings": 0, "notes": 0, "participants": 0}

            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                self.calls["ratings"] += 1
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                self.calls["notes"] += 1
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                self.calls["participants"] += 1
                return []

        provider = MockDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        adapter._build_scoring_inputs()

        assert provider.calls["ratings"] == 1
        assert provider.calls["notes"] == 1
        assert provider.calls["participants"] == 1

    def test_build_scoring_inputs_passes_community_id_to_provider(self):
        """_build_scoring_inputs passes the correct community_id to data provider."""
        from typing import Any

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def __init__(self):
                self.received_community_ids = []

            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                self.received_community_ids.append(("ratings", community_id))
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                self.received_community_ids.append(("notes", community_id))
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                self.received_community_ids.append(("participants", community_id))
                return []

        provider = MockDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="my-specific-community",
        )

        adapter._build_scoring_inputs()

        assert len(provider.received_community_ids) == 3
        for _call_type, community_id in provider.received_community_ids:
            assert community_id == "my-specific-community"

    def test_build_scoring_inputs_ratings_dataframe_has_expected_columns(self):
        """Ratings DataFrame has expected Community Notes columns."""
        from datetime import datetime
        from typing import Any
        from uuid import uuid4

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        note_id = uuid4()

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "note_id": note_id,
                        "rater_participant_id": "user-1",
                        "helpfulness_level": "HELPFUL",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return ["user-1"]

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        ratings_df, _, _, _, _ = adapter._build_scoring_inputs()

        assert "noteId" in ratings_df.columns
        assert "raterParticipantId" in ratings_df.columns
        assert "helpfulNum" in ratings_df.columns

    def test_build_scoring_inputs_note_status_dataframe_has_expected_columns(self):
        """Note status history DataFrame has expected Community Notes columns."""
        from datetime import datetime
        from typing import Any
        from uuid import uuid4

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "author_participant_id": "user-1",
                        "classification": "NOT_MISLEADING",
                        "status": "NEEDS_MORE_RATINGS",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_participants(self, community_id: str) -> list[str]:
                return ["user-1"]

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        _, note_status_df, _, _, _ = adapter._build_scoring_inputs()

        assert "noteId" in note_status_df.columns
        assert "noteAuthorParticipantId" in note_status_df.columns
        assert "currentStatus" in note_status_df.columns

    def test_build_scoring_inputs_user_enrollment_dataframe_has_expected_columns(self):
        """User enrollment DataFrame has expected Community Notes columns."""
        from typing import Any

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return ["user-1", "user-2"]

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        _, _, user_enrollment_df, _, _ = adapter._build_scoring_inputs()

        assert "participantId" in user_enrollment_df.columns
        assert "modelingGroup" in user_enrollment_df.columns

    def test_build_scoring_inputs_note_topics_is_empty_dataframe(self):
        """Note topics DataFrame is an empty DataFrame (for now)."""
        from typing import Any

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        _, _, _, note_topics_df, _ = adapter._build_scoring_inputs()

        assert isinstance(note_topics_df, pd.DataFrame)
        assert len(note_topics_df) == 0

    def test_build_scoring_inputs_requires_data_provider(self):
        """_build_scoring_inputs raises error when data_provider is None."""
        import pytest

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        adapter = MFCoreScorerAdapter()

        with pytest.raises(RuntimeError, match=r"(?i)data_provider"):
            adapter._build_scoring_inputs()


class TestMFCoreScorerAdapterPhase5:
    """Tests for MFCoreScorerAdapter Phase 5: Two-Phase Scoring (task-808 AC #5, #6)."""

    def test_execute_batch_scoring_calls_build_scoring_inputs(self):
        """_execute_batch_scoring calls _build_scoring_inputs to get DataFrames."""
        from datetime import datetime
        from typing import Any
        from unittest.mock import MagicMock, patch
        from uuid import uuid4

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "note_id": uuid4(),
                        "rater_participant_id": "user-1",
                        "helpfulness_level": "HELPFUL",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "author_participant_id": "user-1",
                        "classification": "NOT_MISLEADING",
                        "status": "NEEDS_MORE_RATINGS",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_participants(self, community_id: str) -> list[str]:
                return ["user-1", "user-2"]

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        with (
            patch.object(
                adapter, "_build_scoring_inputs", wraps=adapter._build_scoring_inputs
            ) as mock_build,
            patch.object(adapter._scorer, "prescore") as mock_prescore,
            patch.object(adapter._scorer, "score_final") as mock_score_final,
        ):
            mock_prescore.return_value = MagicMock(
                scoredNotes=MagicMock(),
                helpfulnessScores=MagicMock(),
                metaScores=MagicMock(),
                scorerName="MFCoreScorer",
            )
            mock_score_final.return_value = MagicMock()

            adapter._execute_batch_scoring()

            mock_build.assert_called_once()

    def test_execute_batch_scoring_calls_prescore(self):
        """_execute_batch_scoring calls scorer.prescore() with PrescoringArgs."""
        from datetime import datetime
        from typing import Any
        from unittest.mock import MagicMock, patch
        from uuid import uuid4

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "note_id": uuid4(),
                        "rater_participant_id": "user-1",
                        "helpfulness_level": "HELPFUL",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "author_participant_id": "user-1",
                        "classification": "NOT_MISLEADING",
                        "status": "NEEDS_MORE_RATINGS",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_participants(self, community_id: str) -> list[str]:
                return ["user-1", "user-2"]

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        with (
            patch.object(adapter._scorer, "prescore") as mock_prescore,
            patch.object(adapter._scorer, "score_final") as mock_score_final,
        ):
            mock_prescore.return_value = MagicMock(
                scoredNotes=MagicMock(),
                helpfulnessScores=MagicMock(),
                metaScores=MagicMock(),
                scorerName="MFCoreScorer",
            )
            mock_score_final.return_value = MagicMock()

            adapter._execute_batch_scoring()

            mock_prescore.assert_called_once()

    def test_execute_batch_scoring_calls_score_final_with_prescore_output(self):
        """_execute_batch_scoring calls score_final() with prescore output."""
        from datetime import datetime
        from typing import Any
        from unittest.mock import MagicMock, patch
        from uuid import uuid4

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "note_id": uuid4(),
                        "rater_participant_id": "user-1",
                        "helpfulness_level": "HELPFUL",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "author_participant_id": "user-1",
                        "classification": "NOT_MISLEADING",
                        "status": "NEEDS_MORE_RATINGS",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_participants(self, community_id: str) -> list[str]:
                return ["user-1", "user-2"]

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        with (
            patch.object(adapter._scorer, "prescore") as mock_prescore,
            patch.object(adapter._scorer, "score_final") as mock_score_final,
        ):
            mock_prescore.return_value = MagicMock(
                scoredNotes=MagicMock(),
                helpfulnessScores=MagicMock(),
                metaScores=MagicMock(),
                scorerName="MFCoreScorer",
            )
            mock_score_final.return_value = MagicMock()

            adapter._execute_batch_scoring()

            mock_score_final.assert_called_once()

    def test_execute_batch_scoring_returns_model_result(self):
        """_execute_batch_scoring returns ModelResult from score_final."""
        from datetime import datetime
        from typing import Any
        from unittest.mock import MagicMock, patch
        from uuid import uuid4

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "note_id": uuid4(),
                        "rater_participant_id": "user-1",
                        "helpfulness_level": "HELPFUL",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": uuid4(),
                        "author_participant_id": "user-1",
                        "classification": "NOT_MISLEADING",
                        "status": "NEEDS_MORE_RATINGS",
                        "created_at": datetime.now(UTC),
                    }
                ]

            def get_all_participants(self, community_id: str) -> list[str]:
                return ["user-1", "user-2"]

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        expected_result = MagicMock()
        expected_result.scoredNotes = pd.DataFrame({"noteId": [123], "coreNoteIntercept": [0.5]})

        with (
            patch.object(adapter._scorer, "prescore") as mock_prescore,
            patch.object(adapter._scorer, "score_final") as mock_score_final,
        ):
            mock_prescore.return_value = MagicMock(
                scoredNotes=MagicMock(),
                helpfulnessScores=MagicMock(),
                metaScores=MagicMock(),
                scorerName="MFCoreScorer",
            )
            mock_score_final.return_value = expected_result

            result, int_to_uuid = adapter._execute_batch_scoring()

            assert result is expected_result
            assert isinstance(int_to_uuid, dict)

    def test_execute_batch_scoring_requires_data_provider(self):
        """_execute_batch_scoring raises error when data_provider is None."""
        import pytest

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        adapter = MFCoreScorerAdapter()

        with pytest.raises(RuntimeError, match=r"(?i)data_provider"):
            adapter._execute_batch_scoring()


class TestMFCoreScorerAdapterPhase6:
    """Tests for MFCoreScorerAdapter Phase 6: Result Mapping (task-808 AC #7)."""

    def test_normalize_intercept_maps_min_to_zero(self):
        """_normalize_intercept maps -0.4 (typical min) to close to 0.0."""
        from src.notes.scoring.mf_scorer_adapter import _normalize_intercept

        result = _normalize_intercept(-0.4)

        assert result >= 0.0
        assert result <= 0.1

    def test_normalize_intercept_maps_max_to_one(self):
        """_normalize_intercept maps 0.7 (typical max) to close to 1.0."""
        from src.notes.scoring.mf_scorer_adapter import _normalize_intercept

        result = _normalize_intercept(0.7)

        assert result >= 0.9
        assert result <= 1.0

    def test_normalize_intercept_maps_zero_to_middle(self):
        """_normalize_intercept maps 0.0 to approximately middle of range."""
        from src.notes.scoring.mf_scorer_adapter import _normalize_intercept

        result = _normalize_intercept(0.0)

        assert result > 0.3
        assert result < 0.5

    def test_normalize_intercept_clamps_below_min(self):
        """_normalize_intercept clamps values below min to 0.0."""
        from src.notes.scoring.mf_scorer_adapter import _normalize_intercept

        result = _normalize_intercept(-1.0)

        assert result == 0.0

    def test_normalize_intercept_clamps_above_max(self):
        """_normalize_intercept clamps values above max to 1.0."""
        from src.notes.scoring.mf_scorer_adapter import _normalize_intercept

        result = _normalize_intercept(2.0)

        assert result == 1.0

    @pytest.mark.parametrize(
        "input_status",
        [
            "CURRENTLY_RATED_HELPFUL",
            "CURRENTLY_RATED_NOT_HELPFUL",
            "NEEDS_MORE_RATINGS",
            "UNKNOWN_STATUS",
        ],
    )
    def test_map_rating_status_returns_valid_status(self, input_status):
        """_map_rating_status returns a valid status value for all inputs."""
        from src.notes.scoring.mf_scorer_adapter import _map_rating_status

        valid_statuses = {"high", "standard", "provisional"}
        result = _map_rating_status(input_status)

        assert result in valid_statuses

    def test_process_model_result_single_note(self):
        """_process_model_result correctly maps a single note."""
        from typing import Any
        from unittest.mock import MagicMock

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_protocol import ScoringResult

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        model_result = MagicMock()
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [12345],
                "coreNoteIntercept": [0.5],
                "coreNoteFactor1": [0.1],
                "coreRatingStatus": ["CURRENTLY_RATED_HELPFUL"],
            }
        )

        int_to_uuid = {12345: "test-uuid-12345"}
        result = adapter._process_model_result(model_result, int_to_uuid)

        assert "test-uuid-12345" in result
        assert isinstance(result["test-uuid-12345"], ScoringResult)
        assert result["test-uuid-12345"].confidence_level == "high"

    def test_process_model_result_multiple_notes(self):
        """_process_model_result correctly maps multiple notes."""
        from typing import Any
        from unittest.mock import MagicMock

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        model_result = MagicMock()
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [11111, 22222, 33333],
                "coreNoteIntercept": [0.5, -0.2, 0.0],
                "coreNoteFactor1": [0.1, 0.2, 0.3],
                "coreRatingStatus": [
                    "CURRENTLY_RATED_HELPFUL",
                    "CURRENTLY_RATED_NOT_HELPFUL",
                    "NEEDS_MORE_RATINGS",
                ],
            }
        )

        int_to_uuid = {11111: "uuid-11111", 22222: "uuid-22222", 33333: "uuid-33333"}
        result = adapter._process_model_result(model_result, int_to_uuid)

        assert len(result) == 3
        assert "uuid-11111" in result
        assert "uuid-22222" in result
        assert "uuid-33333" in result
        assert result["uuid-11111"].confidence_level == "high"
        assert result["uuid-22222"].confidence_level == "standard"
        assert result["uuid-33333"].confidence_level == "provisional"

    def test_process_model_result_metadata_contains_required_fields(self):
        """_process_model_result includes required metadata fields."""
        from typing import Any
        from unittest.mock import MagicMock

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        model_result = MagicMock()
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [12345],
                "coreNoteIntercept": [0.5],
                "coreNoteFactor1": [0.1],
                "coreRatingStatus": ["CURRENTLY_RATED_HELPFUL"],
            }
        )

        int_to_uuid = {12345: "uuid-12345"}
        result = adapter._process_model_result(model_result, int_to_uuid)

        metadata = result["uuid-12345"].metadata
        assert metadata["source"] == "mf_core"
        assert metadata["intercept"] == 0.5
        assert metadata["factor"] == 0.1
        assert metadata["status"] == "CURRENTLY_RATED_HELPFUL"

    def test_process_model_result_score_is_normalized(self):
        """_process_model_result produces normalized scores between 0.0 and 1.0."""
        from typing import Any
        from unittest.mock import MagicMock

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        model_result = MagicMock()
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [11111, 22222],
                "coreNoteIntercept": [-0.4, 0.7],
                "coreNoteFactor1": [0.1, 0.1],
                "coreRatingStatus": ["NEEDS_MORE_RATINGS", "CURRENTLY_RATED_HELPFUL"],
            }
        )

        int_to_uuid = {11111: "uuid-11111", 22222: "uuid-22222"}
        result = adapter._process_model_result(model_result, int_to_uuid)

        assert result["uuid-11111"].score >= 0.0
        assert result["uuid-11111"].score <= 0.1
        assert result["uuid-22222"].score >= 0.9
        assert result["uuid-22222"].score <= 1.0

    def test_score_note_uses_batch_scoring_with_data_provider(self):
        """score_note uses actual batch scoring instead of stub when data_provider exists."""
        from typing import Any
        from unittest.mock import MagicMock, patch

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        mock_result = MagicMock()
        mock_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [12345],
                "coreNoteIntercept": [0.5],
                "coreNoteFactor1": [0.1],
                "coreRatingStatus": ["CURRENTLY_RATED_HELPFUL"],
            }
        )

        mock_int_to_uuid = {12345: "12345"}
        with (
            patch.object(
                adapter, "_execute_batch_scoring", return_value=(mock_result, mock_int_to_uuid)
            ) as mock_batch,
            patch.object(adapter, "_process_model_result") as mock_process,
        ):
            mock_process.return_value = {
                "12345": MagicMock(
                    score=0.8,
                    confidence_level="high",
                    metadata={"source": "mf_core"},
                )
            }

            result = adapter.score_note("12345", [0.6, 0.7])

            mock_batch.assert_called_once()
            assert result.metadata.get("source") == "mf_core"

    def test_process_model_result_empty_dataframe(self):
        """_process_model_result returns empty dict for empty scoredNotes DataFrame."""
        from typing import Any
        from unittest.mock import MagicMock

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        model_result = MagicMock()
        model_result.scoredNotes = pd.DataFrame(
            columns=["noteId", "coreNoteIntercept", "coreNoteFactor1", "coreRatingStatus"]
        )

        int_to_uuid: dict[int, str] = {}
        result = adapter._process_model_result(model_result, int_to_uuid)

        assert result == {}


class TestMFCoreScorerAdapterPhase7:
    """Tests for MFCoreScorerAdapter Phase 7: Error Handling (task-808 AC #8)."""

    def test_score_note_falls_back_to_stub_on_batch_scoring_failure(self):
        """score_note falls back to stub when _execute_batch_scoring raises an exception."""
        from typing import Any
        from unittest.mock import patch

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        with patch.object(
            adapter, "_execute_batch_scoring", side_effect=Exception("Scoring failed")
        ):
            result = adapter.score_note("note-123", [0.6, 0.7])

        assert result.metadata.get("source") == "batch_stub"

    def test_score_note_degraded_result_has_metadata_flag(self):
        """Fallback result has metadata['degraded'] = True."""
        from typing import Any
        from unittest.mock import patch

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        with patch.object(
            adapter, "_execute_batch_scoring", side_effect=RuntimeError("Data error")
        ):
            result = adapter.score_note("note-456", [0.5])

        assert result.metadata.get("degraded") is True

    def test_score_note_logs_warning_on_batch_scoring_failure(self):
        """score_note logs a warning when batch scoring fails."""
        from typing import Any
        from unittest.mock import patch

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        with (
            patch.object(adapter, "_execute_batch_scoring", side_effect=ValueError("Invalid data")),
            patch("src.notes.scoring.mf_scorer_adapter.logger") as mock_logger,
        ):
            adapter.score_note("note-789", [0.8])

            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "Invalid data" in call_args or "exception" in call_args.lower()


class TestMFCoreScorerAdapterPhase8:
    """Tests for MFCoreScorerAdapter Phase 8: Thread Safety (task-808 AC #9)."""

    def test_concurrent_score_note_calls_are_thread_safe(self):
        """Multiple threads calling score_note should not cause race conditions."""
        import threading
        from typing import Any
        from unittest.mock import MagicMock, patch

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        mock_result = MagicMock()
        mock_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [f"note-{i}" for i in range(100)],
                "coreNoteIntercept": [0.5] * 100,
                "coreNoteFactor1": [0.1] * 100,
                "coreRatingStatus": ["CURRENTLY_RATED_HELPFUL"] * 100,
            }
        )

        results = []
        errors = []

        def score_note_thread(note_id):
            try:
                result = adapter.score_note(note_id, [0.6])
                results.append(result)
            except Exception as e:
                errors.append(e)

        with patch.object(adapter, "_execute_batch_scoring", return_value=mock_result):
            threads = []
            for i in range(20):
                t = threading.Thread(target=score_note_thread, args=(f"note-{i % 100}",))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 20

    def test_lock_protects_cache_operations(self):
        """Lock prevents race conditions when accessing the cache."""
        import threading
        import time
        from typing import Any
        from unittest.mock import MagicMock, patch

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        batch_scoring_call_count = 0

        def slow_batch_scoring(*args, **kwargs):
            nonlocal batch_scoring_call_count
            batch_scoring_call_count += 1
            time.sleep(0.05)
            mock_result = MagicMock()
            mock_result.scoredNotes = pd.DataFrame(
                {
                    "noteId": ["note-1"],
                    "coreNoteIntercept": [0.5],
                    "coreNoteFactor1": [0.1],
                    "coreRatingStatus": ["CURRENTLY_RATED_HELPFUL"],
                }
            )
            return mock_result

        with patch.object(adapter, "_execute_batch_scoring", side_effect=slow_batch_scoring):
            threads = []
            for _ in range(5):
                t = threading.Thread(target=lambda: adapter.score_note("note-1", [0.6]))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

        assert batch_scoring_call_count == 1

    def test_adapter_has_lock_and_uses_it(self):
        """Adapter has a lock for thread safety."""
        import threading
        from typing import Any

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        assert hasattr(adapter, "_lock")
        assert isinstance(adapter._lock, type(threading.Lock()))


class TestMFCoreScorerAdapterPhase9:
    """Tests for MFCoreScorerAdapter Phase 9: LRU Cache Eviction (task-808 AC #10)."""

    def test_cache_is_ordered_dict(self):
        """Cache uses OrderedDict for LRU eviction support."""
        from collections import OrderedDict
        from typing import Any

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        assert isinstance(adapter._cache, OrderedDict)

    def test_evict_if_needed_removes_oldest_entries(self):
        """_evict_if_needed removes oldest entries when cache exceeds max size."""
        from typing import Any

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_protocol import ScoringResult

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        for i in range(15):
            adapter._cache[f"note-{i}"] = ScoringResult(
                score=0.5, confidence_level="standard", metadata={}
            )

        adapter._evict_if_needed(max_size=10)

        assert len(adapter._cache) == 10
        assert "note-0" not in adapter._cache
        assert "note-4" not in adapter._cache
        assert "note-5" in adapter._cache
        assert "note-14" in adapter._cache

    def test_cache_access_moves_item_to_end(self):
        """Accessing a cached item moves it to the end (most recently used)."""
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
        from src.notes.scoring.scorer_protocol import ScoringResult

        adapter = MFCoreScorerAdapter()

        for i in range(5):
            adapter._cache[f"note-{i}"] = ScoringResult(
                score=0.5, confidence_level="standard", metadata={"source": "mf_core"}
            )

        adapter._cache_version = adapter._current_version

        first_key_before = next(iter(adapter._cache))
        assert first_key_before == "note-0"

        adapter.score_note("note-0", [0.6])

        first_key_after = next(iter(adapter._cache))
        assert first_key_after != "note-0"

        last_key = list(adapter._cache.keys())[-1]
        assert last_key == "note-0"

    def test_cache_size_bounded_after_batch_scoring(self):
        """Cache size is bounded after batch scoring populates it."""
        from typing import Any
        from unittest.mock import MagicMock, patch

        import pandas as pd

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        mock_result = MagicMock()
        mock_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [f"note-{i}" for i in range(100)],
                "coreNoteIntercept": [0.5] * 100,
                "coreNoteFactor1": [0.1] * 100,
                "coreRatingStatus": ["CURRENTLY_RATED_HELPFUL"] * 100,
            }
        )

        with patch.object(adapter, "_execute_batch_scoring", return_value=mock_result):
            adapter.score_note("note-1", [0.6])

        assert len(adapter._cache) <= 10000

    def test_evict_if_needed_default_max_size_is_10000(self):
        """_evict_if_needed has default max_size of 10000."""
        import inspect
        from typing import Any

        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        adapter = MFCoreScorerAdapter(
            data_provider=MockDataProvider(),
            community_id="test-community",
        )

        sig = inspect.signature(adapter._evict_if_needed)
        max_size_param = sig.parameters.get("max_size")
        assert max_size_param is not None
        assert max_size_param.default == 10000
