from unittest.mock import MagicMock

import pandas as pd

from src.notes.scoring.snapshot_persistence import extract_factors_from_model_result


class TestSanitizeNanInf:
    def test_nan_values_replaced_with_none(self):
        model_result = MagicMock()
        model_result.helpfulnessScores = pd.DataFrame(
            {
                "raterParticipantId": ["r1"],
                "coreRaterIntercept": [float("nan")],
                "coreRaterFactor1": [float("nan")],
            }
        )
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [1],
                "coreNoteIntercept": [float("nan")],
                "coreNoteFactor1": [float("nan")],
                "coreRatingStatus": ["CRH"],
            }
        )

        result = extract_factors_from_model_result(model_result, {1: "uuid-1"})

        assert result["rater_factors"][0]["intercept"] is None
        assert result["rater_factors"][0]["factor1"] is None
        assert result["note_factors"][0]["intercept"] is None
        assert result["note_factors"][0]["factor1"] is None
        assert result["global_intercept"] is None

    def test_inf_values_replaced_with_none(self):
        model_result = MagicMock()
        model_result.helpfulnessScores = pd.DataFrame(
            {
                "raterParticipantId": ["r1"],
                "coreRaterIntercept": [float("inf")],
                "coreRaterFactor1": [float("-inf")],
            }
        )
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [1],
                "coreNoteIntercept": [float("inf")],
                "coreNoteFactor1": [float("-inf")],
                "coreRatingStatus": ["CRH"],
            }
        )

        result = extract_factors_from_model_result(model_result, {1: "uuid-1"})

        assert result["rater_factors"][0]["intercept"] is None
        assert result["rater_factors"][0]["factor1"] is None
        assert result["note_factors"][0]["intercept"] is None
        assert result["note_factors"][0]["factor1"] is None
        assert result["global_intercept"] is None

    def test_normal_values_unchanged(self):
        model_result = MagicMock()
        model_result.helpfulnessScores = pd.DataFrame(
            {
                "raterParticipantId": ["r1"],
                "coreRaterIntercept": [0.5],
                "coreRaterFactor1": [-0.3],
            }
        )
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [1],
                "coreNoteIntercept": [0.7],
                "coreNoteFactor1": [0.2],
                "coreRatingStatus": ["CRH"],
            }
        )

        result = extract_factors_from_model_result(model_result, {1: "uuid-1"})

        assert result["rater_factors"][0]["intercept"] == 0.5
        assert result["rater_factors"][0]["factor1"] == -0.3
        assert result["note_factors"][0]["intercept"] == 0.7
        assert result["note_factors"][0]["factor1"] == 0.2
        assert result["global_intercept"] == 0.7
