"""
Lightweight integration tests for MFCoreScorerAdapter.

Tests that run real matrix factorization (OOM-risk) have been moved to
tests/heavy/test_mf_scorer_integration.py (TASK-1135).

This file retains:
- MockCommunityDataProvider protocol tests (no scoring)
- Error handling tests (patched scorer, no real MF computation)
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.notes.scoring.data_provider import CommunityDataProvider
from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter


class MockCommunityDataProvider:
    """
    Mock CommunityDataProvider with realistic rating data for MFCoreScorer.

    MFCoreScorer requires:
    - Minimum 10 ratings per rater
    - Minimum 5 raters per note

    To meet these requirements, defaults are:
    - 15 raters (so each note can have up to 14 raters, excluding author)
    - 20 notes (so each rater can rate up to 19 notes, excluding their own)

    The rating patterns create meaningful structure for matrix factorization:
    - Notes 0-6: Consensus helpful (most raters rate HELPFUL)
    - Notes 7-13: Consensus not helpful (most raters rate NOT_HELPFUL)
    - Notes 14-19: Controversial (mixed ratings)
    """

    def __init__(self, num_raters: int = 15, num_notes: int = 20) -> None:
        self._num_raters = num_raters
        self._num_notes = num_notes
        self._raters = [f"rater-{i}" for i in range(num_raters)]
        self._note_ids = [uuid4() for _ in range(num_notes)]
        self._notes = self._generate_notes()
        self._ratings = self._generate_ratings()

    def _generate_notes(self) -> list[dict[str, Any]]:
        notes = []
        for i, note_id in enumerate(self._note_ids):
            author_idx = i % len(self._raters)
            notes.append(
                {
                    "id": note_id,
                    "author_id": self._raters[author_idx],
                    "classification": "NOT_MISLEADING"
                    if i < 10
                    else "MISINFORMED_OR_POTENTIALLY_MISLEADING",
                    "status": "NEEDS_MORE_RATINGS",
                    "created_at": datetime.now(UTC),
                }
            )
        return notes

    def _generate_ratings(self) -> list[dict[str, Any]]:
        ratings = []
        for note_idx, note_id in enumerate(self._note_ids):
            for rater_idx, rater_id in enumerate(self._raters):
                if self._notes[note_idx]["author_id"] == rater_id:
                    continue

                helpfulness = self._determine_helpfulness(note_idx, rater_idx)

                ratings.append(
                    {
                        "id": uuid4(),
                        "note_id": note_id,
                        "rater_id": rater_id,
                        "helpfulness_level": helpfulness,
                        "created_at": datetime.now(UTC),
                    }
                )
        return ratings

    def _determine_helpfulness(self, note_idx: int, rater_idx: int) -> str:
        third = self._num_notes // 3
        if note_idx < third:
            return "HELPFUL" if rater_idx % 4 != 0 else "SOMEWHAT_HELPFUL"
        if note_idx < 2 * third:
            return "NOT_HELPFUL" if rater_idx % 4 != 0 else "SOMEWHAT_HELPFUL"
        if rater_idx % 2 == 0:
            return "HELPFUL"
        return "NOT_HELPFUL"

    def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
        return self._ratings

    def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
        return self._notes

    def get_all_participants(self, community_id: str) -> list[str]:
        return self._raters

    def get_note_id(self, index: int) -> str:
        return str(self._note_ids[index])


class TestMockCommunityDataProvider:
    """Tests to verify MockCommunityDataProvider implements protocol correctly."""

    def test_mock_provider_implements_protocol(self):
        """MockCommunityDataProvider implements CommunityDataProvider protocol."""
        provider = MockCommunityDataProvider()

        assert isinstance(provider, CommunityDataProvider)

    def test_mock_provider_generates_correct_number_of_raters(self):
        """MockCommunityDataProvider generates correct number of raters."""
        provider = MockCommunityDataProvider(num_raters=20, num_notes=25)

        participants = provider.get_all_participants("test")

        assert len(participants) == 20

    def test_mock_provider_generates_correct_number_of_notes(self):
        """MockCommunityDataProvider generates correct number of notes."""
        provider = MockCommunityDataProvider(num_raters=15, num_notes=25)

        notes = provider.get_all_notes("test")

        assert len(notes) == 25

    def test_mock_provider_generates_dense_rating_matrix(self):
        """MockCommunityDataProvider generates ratings for most note-rater pairs."""
        provider = MockCommunityDataProvider()

        ratings = provider.get_all_ratings("test")

        assert len(ratings) >= 250


@pytest.mark.integration
class TestMFCoreScorerErrorHandling:
    """Integration tests for error handling and graceful degradation."""

    def test_score_note_graceful_degradation_on_scorer_failure(self):
        """
        When MFCoreScorer raises an exception, adapter falls back to stub.

        AC #8: Test error handling with mock scorer that raises.
        """
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        with patch.object(adapter._scorer, "prescore", side_effect=RuntimeError("Scorer failed")):
            note_id = provider.get_note_id(0)
            result = adapter.score_note(note_id, [0.5, 0.6])

        assert result is not None
        assert result.metadata.get("source") == "batch_stub"
        assert result.metadata.get("degraded") is True

    def test_score_note_degradation_still_returns_valid_result(self):
        """Degraded results still contain valid score and confidence level."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        with patch.object(adapter._scorer, "prescore", side_effect=ValueError("Invalid input")):
            note_id = provider.get_note_id(0)
            result = adapter.score_note(note_id, [0.5, 0.6, 0.7])

        assert 0.0 <= result.score <= 1.0
        assert result.confidence_level in {"high", "standard", "provisional"}

    def test_score_note_degradation_caches_result(self):
        """Degraded results are cached to avoid repeated failures."""
        provider = MockCommunityDataProvider()
        adapter = MFCoreScorerAdapter(
            data_provider=provider,
            community_id="test-community",
        )

        call_count = 0

        def failing_prescore(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Scorer unavailable")

        with patch.object(adapter._scorer, "prescore", side_effect=failing_prescore):
            note_id = provider.get_note_id(0)
            adapter.score_note(note_id, [0.5])
            adapter.score_note(note_id, [0.5])

        assert call_count == 1
