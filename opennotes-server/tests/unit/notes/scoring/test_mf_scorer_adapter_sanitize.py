from __future__ import annotations

import math
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

_SCORING_MODULES = [
    "scoring",
    "scoring.constants",
    "scoring.mf_core_scorer",
    "scoring.pandas_utils",
    "scoring.matrix_factorization",
    "scoring.matrix_factorization.matrix_factorization",
    "scoring.matrix_factorization.model",
    "torch",
]

_mock_modules = {mod: MagicMock() for mod in _SCORING_MODULES}
with patch.dict(sys.modules, _mock_modules):
    from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter


@pytest.fixture
def adapter_with_nan_inf():
    adapter = MFCoreScorerAdapter.__new__(MFCoreScorerAdapter)

    scored_notes = pd.DataFrame(
        {
            "noteId": [1, 2, 3],
            "coreNoteIntercept": [float("nan"), float("inf"), float("-inf")],
            "coreNoteFactor1": [float("inf"), 0.5, float("nan")],
            "coreRatingStatus": ["NEEDS_MORE_RATINGS", "CURRENTLY_RATED_HELPFUL", ""],
        }
    )

    helpfulness_scores = pd.DataFrame(
        {
            "raterParticipantId": ["rater_1", "rater_2"],
            "coreRaterIntercept": [float("nan"), float("inf")],
            "coreRaterFactor1": [float("-inf"), 0.3],
        }
    )

    model_result = SimpleNamespace(
        scoredNotes=scored_notes,
        helpfulnessScores=helpfulness_scores,
    )

    adapter._last_model_result = model_result
    adapter._last_int_to_uuid = {1: "uuid-1", 2: "uuid-2", 3: "uuid-3"}

    return adapter


class TestGetLastScoringFactorsSanitize:
    def test_nan_inf_rater_intercept_sanitized(self, adapter_with_nan_inf):
        result = adapter_with_nan_inf.get_last_scoring_factors()
        assert result is not None
        rater_factors = result["rater_factors"]
        assert rater_factors[0]["intercept"] is None
        assert rater_factors[1]["intercept"] is None

    def test_nan_inf_rater_factor1_sanitized(self, adapter_with_nan_inf):
        result = adapter_with_nan_inf.get_last_scoring_factors()
        assert result is not None
        rater_factors = result["rater_factors"]
        assert rater_factors[0]["factor1"] is None
        assert rater_factors[1]["factor1"] == pytest.approx(0.3)

    def test_nan_inf_note_intercept_sanitized(self, adapter_with_nan_inf):
        result = adapter_with_nan_inf.get_last_scoring_factors()
        assert result is not None
        note_factors = result["note_factors"]
        assert note_factors[0]["intercept"] is None
        assert note_factors[1]["intercept"] is None
        assert note_factors[2]["intercept"] is None

    def test_nan_inf_note_factor1_sanitized(self, adapter_with_nan_inf):
        result = adapter_with_nan_inf.get_last_scoring_factors()
        assert result is not None
        note_factors = result["note_factors"]
        assert note_factors[0]["factor1"] is None
        assert note_factors[1]["factor1"] == pytest.approx(0.5)
        assert note_factors[2]["factor1"] is None

    def test_nan_inf_global_intercept_sanitized(self, adapter_with_nan_inf):
        result = adapter_with_nan_inf.get_last_scoring_factors()
        assert result is not None
        assert result["global_intercept"] is None

    def test_no_nan_values_in_any_float_field(self, adapter_with_nan_inf):
        result = adapter_with_nan_inf.get_last_scoring_factors()
        assert result is not None

        for rf in result["rater_factors"]:
            for key in ("intercept", "factor1"):
                val = rf[key]
                if val is not None:
                    assert not math.isnan(val), f"rater {rf['rater_id']} {key} is NaN"
                    assert not math.isinf(val), f"rater {rf['rater_id']} {key} is Inf"

        for nf in result["note_factors"]:
            for key in ("intercept", "factor1"):
                val = nf[key]
                if val is not None:
                    assert not math.isnan(val), f"note {nf['note_id']} {key} is NaN"
                    assert not math.isinf(val), f"note {nf['note_id']} {key} is Inf"

        gi = result["global_intercept"]
        if gi is not None:
            assert not math.isnan(gi), "global_intercept is NaN"
            assert not math.isinf(gi), "global_intercept is Inf"


class TestProcessModelResultNaNHandling:
    def test_nan_intercept_produces_default_score(self):
        adapter = MFCoreScorerAdapter.__new__(MFCoreScorerAdapter)

        scored_notes = pd.DataFrame(
            {
                "noteId": [1],
                "coreNoteIntercept": [float("nan")],
                "coreNoteFactor1": [float("nan")],
                "coreRatingStatus": ["NEEDS_MORE_RATINGS"],
            }
        )

        model_result = SimpleNamespace(scoredNotes=scored_notes, helpfulnessScores=None)
        int_to_uuid = {1: "uuid-1"}

        results = adapter._process_model_result(model_result, int_to_uuid)

        assert "uuid-1" in results
        score = results["uuid-1"].score
        assert not math.isnan(score), "NaN intercept should produce a valid score, not NaN"
        assert 0.0 <= score <= 1.0

    def test_valid_intercept_still_normalized(self):
        adapter = MFCoreScorerAdapter.__new__(MFCoreScorerAdapter)

        scored_notes = pd.DataFrame(
            {
                "noteId": [1],
                "coreNoteIntercept": [0.4],
                "coreNoteFactor1": [0.3],
                "coreRatingStatus": ["CURRENTLY_RATED_HELPFUL"],
            }
        )

        model_result = SimpleNamespace(scoredNotes=scored_notes, helpfulnessScores=None)
        int_to_uuid = {1: "uuid-1"}

        results = adapter._process_model_result(model_result, int_to_uuid)

        score = results["uuid-1"].score
        assert not math.isnan(score)
        assert 0.0 <= score <= 1.0
        assert score != 0.5
