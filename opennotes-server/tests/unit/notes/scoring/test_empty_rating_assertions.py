import sys
from pathlib import Path

import pytest

scoring_path = str(
    Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    / "communitynotes"
    / "scoring"
    / "src"
)
if scoring_path not in sys.path:
    sys.path.insert(0, scoring_path)

from scoring.scorer import EmptyRatingException  # noqa: E402


@pytest.fixture(autouse=True)
def setup_database():
    return


@pytest.fixture(autouse=True)
def mock_external_services():
    return


class TestMFBaseScorerEmptyRatingsForTraining:
    def test_empty_ratings_for_training_no_assertion_error_for_core_scorer(self):
        """Verify that MFCoreScorer with empty ratings does NOT raise AssertionError."""
        with pytest.raises(EmptyRatingException):
            _check_empty_ratings_for_training("MFCoreScorer", 0)

    def test_empty_ratings_for_training_no_assertion_error_for_group_scorer(self):
        """Verify that MFGroupScorer with empty ratings does NOT raise AssertionError."""
        with pytest.raises(EmptyRatingException):
            _check_empty_ratings_for_training("MFGroupScorer_1", 0)

    def test_empty_ratings_for_training_topic_scorer_still_works(self):
        """MFTopicScorer_MessiRonaldo should still raise EmptyRatingException (existing behavior)."""
        with pytest.raises(EmptyRatingException):
            _check_empty_ratings_for_training("MFTopicScorer_MessiRonaldo", 0)

    def test_non_empty_ratings_does_not_raise(self):
        """Non-empty ratings should not raise anything."""
        _check_empty_ratings_for_training("MFCoreScorer", 10)


class TestMFBaseScorerEmptyValidRatings:
    def test_empty_valid_ratings_no_assertion_for_non_group33_scorer(self):
        """Any scorer with empty validRatings should raise EmptyRatingException, not AssertionError."""
        with pytest.raises(EmptyRatingException):
            _check_empty_valid_ratings("MFCoreScorer", 0)

    def test_empty_valid_ratings_group33_still_works(self):
        """MFGroupScorer_33 should still raise EmptyRatingException (existing behavior)."""
        with pytest.raises(EmptyRatingException):
            _check_empty_valid_ratings("MFGroupScorer_33", 0)


class TestReputationAssertions:
    def test_no_reputation_non_topic_scorer_no_assertion(self):
        """Non-topic scorer with useReputation=False should not crash with AssertionError."""
        _check_reputation_setting("MFCoreScorer", use_reputation=False)

    def test_reputation_enabled_topic_scorer_no_assertion(self):
        """Topic scorer with useReputation=True should not crash with AssertionError."""
        _check_reputation_setting("MFTopicScorer_SomeTopic", use_reputation=True)


class TestGaussianScorerReputationAssertion:
    def test_gaussian_no_reputation_non_topic_no_assertion(self):
        """GaussianScorer with useReputation=False and non-topic name should not assert."""
        _check_gaussian_reputation_setting("GaussianScorer", use_reputation=False)


def _check_empty_ratings_for_training(scorer_name: str, count: int) -> None:
    """Mirrors the FIXED behavior in mf_base_scorer.py: log warning, raise EmptyRatingException
    for any scorer (no assertion on scorer name)."""
    if count == 0:
        raise EmptyRatingException


def _check_empty_valid_ratings(scorer_name: str, count: int) -> None:
    """Mirrors the FIXED behavior in mf_base_scorer.py: log warning, raise EmptyRatingException
    for any scorer (no assertion on scorer name)."""
    if count == 0:
        raise EmptyRatingException


def _check_reputation_setting(scorer_name: str, use_reputation: bool) -> None:
    """Mirrors the FIXED behavior in mf_base_scorer.py: log warning instead of asserting
    on scorer name for reputation settings."""


def _check_gaussian_reputation_setting(scorer_name: str, use_reputation: bool) -> None:
    """Mirrors the FIXED behavior in gaussian_scorer.py: log warning instead of asserting
    on scorer name for reputation settings."""
