from unittest.mock import MagicMock, patch

import pytest

from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
from src.scoring_adapter import ScoringAdapter

SAMPLE_NOTES = [
    {
        "noteId": "1",
        "noteAuthorParticipantId": "a",
        "createdAtMillis": 0,
        "tweetId": "t1",
        "summary": "s",
        "classification": "NOT_MISLEADING",
    }
]

SAMPLE_RATINGS = [
    {
        "raterParticipantId": "a",
        "noteId": "1",
        "createdAtMillis": 0,
        "helpfulnessLevel": "HELPFUL",
        "helpfulNum": 1.0,
    }
]

SAMPLE_ENROLLMENT = [
    {
        "participantId": "a",
        "enrollmentState": "newUser",
        "successfulRatingNeededToEarnIn": 3,
        "timestampOfLastStateChange": 0,
    }
]


class TestScoringAdapterAssertionError:
    @pytest.mark.asyncio
    async def test_assertion_error_caught_and_reraised_as_runtime(self):
        adapter = ScoringAdapter()

        with (
            patch.object(
                adapter,
                "_run_scoring_sync",
                side_effect=AssertionError("empty ratingsForTraining"),
            ),
            pytest.raises(RuntimeError, match="Scoring failed due to assertion"),
        ):
            await adapter.score_notes(SAMPLE_NOTES, SAMPLE_RATINGS, SAMPLE_ENROLLMENT)

    @pytest.mark.asyncio
    async def test_assertion_error_logged_with_context(self):
        adapter = ScoringAdapter()

        with (
            patch.object(
                adapter,
                "_run_scoring_sync",
                side_effect=AssertionError("empty ratingsForTraining"),
            ),
            patch("src.scoring_adapter.logger") as mock_logger,
        ):
            with pytest.raises(RuntimeError):
                await adapter.score_notes(SAMPLE_NOTES, SAMPLE_RATINGS, SAMPLE_ENROLLMENT)
            mock_logger.warning.assert_called()
            call_kwargs = mock_logger.warning.call_args
            extra = call_kwargs.kwargs.get("extra") or call_kwargs[1].get("extra", {})
            assert extra["note_count"] == 1
            assert extra["rating_count"] == 1
            assert "error" in extra

    @pytest.mark.asyncio
    async def test_assertion_error_preserves_original_as_cause(self):
        adapter = ScoringAdapter()
        original = AssertionError("empty ratingsForTraining")

        with patch.object(adapter, "_run_scoring_sync", side_effect=original):
            with pytest.raises(RuntimeError) as exc_info:
                await adapter.score_notes(SAMPLE_NOTES, SAMPLE_RATINGS, SAMPLE_ENROLLMENT)
            assert exc_info.value.__cause__ is original


class TestMFCoreScorerAdapterBatchFailFlag:
    def test_batch_fail_flag_initialized_false(self):
        adapter = MFCoreScorerAdapter(data_provider=None)
        assert adapter._batch_scoring_failed is False

    def test_batch_fail_flag_set_on_exception(self):
        mock_provider = MagicMock()
        adapter = MFCoreScorerAdapter(data_provider=None)
        adapter._data_provider = mock_provider

        with patch.object(
            adapter,
            "_execute_batch_scoring",
            side_effect=AssertionError("empty ratings"),
        ):
            result = adapter.score_note("note-1", [0.5, 0.8])

        assert adapter._batch_scoring_failed is True
        assert result.metadata.get("degraded") is True

    def test_second_note_skips_batch_after_failure(self):
        mock_provider = MagicMock()
        adapter = MFCoreScorerAdapter(data_provider=None)
        adapter._data_provider = mock_provider

        with patch.object(
            adapter,
            "_execute_batch_scoring",
            side_effect=AssertionError("empty ratings"),
        ):
            adapter.score_note("note-1", [0.5, 0.8])

        with patch.object(
            adapter,
            "_execute_batch_scoring",
            side_effect=AssertionError("should not be called"),
        ) as mock_batch:
            result2 = adapter.score_note("note-2", [0.5])
            mock_batch.assert_not_called()
            assert result2.metadata.get("source") == "batch_stub"
