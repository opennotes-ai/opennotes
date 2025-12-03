"""
Tests for ScoringDataValidator.

TDD: Write failing tests first, then implement.
"""

import pandas as pd
import pytest


class TestScoringDataValidator:
    """Tests for ScoringDataValidator (AC #6)."""

    def test_can_import_scoring_data_validator(self):
        """ScoringDataValidator can be imported."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        assert ScoringDataValidator is not None

    def test_can_import_validation_result(self):
        """ValidationResult can be imported."""
        from src.notes.scoring.scoring_data_validator import ValidationResult

        assert ValidationResult is not None

    def test_validator_can_be_instantiated(self):
        """ScoringDataValidator can be instantiated."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        validator = ScoringDataValidator()
        assert validator is not None

    def test_validator_has_default_min_raters_per_note(self):
        """ScoringDataValidator has default min_raters_per_note=5."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        validator = ScoringDataValidator()
        assert validator.min_raters_per_note == 5

    def test_validator_has_default_min_ratings_per_rater(self):
        """ScoringDataValidator has default min_ratings_per_rater=10."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        validator = ScoringDataValidator()
        assert validator.min_ratings_per_rater == 10

    def test_validator_custom_thresholds(self):
        """ScoringDataValidator can be initialized with custom thresholds."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        validator = ScoringDataValidator(min_raters_per_note=3, min_ratings_per_rater=5)
        assert validator.min_raters_per_note == 3
        assert validator.min_ratings_per_rater == 5


class TestScoringDataValidatorValidate:
    """Tests for ScoringDataValidator.validate() method."""

    @pytest.fixture
    def validator(self):
        """Create a validator with lower thresholds for testing."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        return ScoringDataValidator(min_raters_per_note=2, min_ratings_per_rater=3)

    @pytest.fixture
    def empty_ratings_df(self):
        """Create an empty ratings DataFrame."""
        return pd.DataFrame(
            columns=["noteId", "raterParticipantId", "helpfulNum", "createdAtMillis"]
        )

    def test_validate_returns_validation_result(self, validator, empty_ratings_df):
        """validate() returns a ValidationResult."""
        from src.notes.scoring.scoring_data_validator import ValidationResult

        result = validator.validate(empty_ratings_df)

        assert isinstance(result, ValidationResult)

    def test_validate_empty_dataframe_is_invalid(self, validator, empty_ratings_df):
        """validate() marks empty DataFrame as invalid."""
        result = validator.validate(empty_ratings_df)

        assert result.is_valid is False

    def test_validation_result_has_is_valid(self, validator, empty_ratings_df):
        """ValidationResult has is_valid attribute."""
        result = validator.validate(empty_ratings_df)

        assert hasattr(result, "is_valid")

    def test_validation_result_has_notes_with_insufficient_ratings(
        self, validator, empty_ratings_df
    ):
        """ValidationResult has notes_with_insufficient_ratings attribute."""
        result = validator.validate(empty_ratings_df)

        assert hasattr(result, "notes_with_insufficient_ratings")

    def test_validation_result_has_raters_with_insufficient_ratings(
        self, validator, empty_ratings_df
    ):
        """ValidationResult has raters_with_insufficient_ratings attribute."""
        result = validator.validate(empty_ratings_df)

        assert hasattr(result, "raters_with_insufficient_ratings")


class TestScoringDataValidatorNoteValidation:
    """Tests for note-level validation (min_raters_per_note)."""

    @pytest.fixture
    def validator(self):
        """Create a validator with min_raters_per_note=3."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        return ScoringDataValidator(min_raters_per_note=3, min_ratings_per_rater=1)

    def test_note_with_sufficient_ratings_is_valid(self, validator):
        """Note with enough ratings is valid."""
        ratings_df = pd.DataFrame(
            {
                "noteId": ["note_1", "note_1", "note_1"],
                "raterParticipantId": ["rater_1", "rater_2", "rater_3"],
                "helpfulNum": [1.0, 1.0, 0.0],
                "createdAtMillis": [1000, 2000, 3000],
            }
        )

        result = validator.validate(ratings_df)

        assert "note_1" not in result.notes_with_insufficient_ratings

    def test_note_with_insufficient_ratings_identified(self, validator):
        """Note with too few ratings is identified."""
        ratings_df = pd.DataFrame(
            {
                "noteId": ["note_1", "note_1"],
                "raterParticipantId": ["rater_1", "rater_2"],
                "helpfulNum": [1.0, 0.0],
                "createdAtMillis": [1000, 2000],
            }
        )

        result = validator.validate(ratings_df)

        assert "note_1" in result.notes_with_insufficient_ratings

    def test_multiple_notes_with_insufficient_ratings(self, validator):
        """Multiple notes with insufficient ratings are all identified."""
        ratings_df = pd.DataFrame(
            {
                "noteId": ["note_1", "note_2", "note_2"],
                "raterParticipantId": ["rater_1", "rater_1", "rater_2"],
                "helpfulNum": [1.0, 1.0, 0.0],
                "createdAtMillis": [1000, 2000, 3000],
            }
        )

        result = validator.validate(ratings_df)

        assert "note_1" in result.notes_with_insufficient_ratings
        assert "note_2" in result.notes_with_insufficient_ratings


class TestScoringDataValidatorRaterValidation:
    """Tests for rater-level validation (min_ratings_per_rater)."""

    @pytest.fixture
    def validator(self):
        """Create a validator with min_ratings_per_rater=3."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        return ScoringDataValidator(min_raters_per_note=1, min_ratings_per_rater=3)

    def test_rater_with_sufficient_ratings_is_valid(self, validator):
        """Rater with enough ratings is valid."""
        ratings_df = pd.DataFrame(
            {
                "noteId": ["note_1", "note_2", "note_3"],
                "raterParticipantId": ["rater_1", "rater_1", "rater_1"],
                "helpfulNum": [1.0, 1.0, 0.0],
                "createdAtMillis": [1000, 2000, 3000],
            }
        )

        result = validator.validate(ratings_df)

        assert "rater_1" not in result.raters_with_insufficient_ratings

    def test_rater_with_insufficient_ratings_identified(self, validator):
        """Rater with too few ratings is identified."""
        ratings_df = pd.DataFrame(
            {
                "noteId": ["note_1", "note_2"],
                "raterParticipantId": ["rater_1", "rater_1"],
                "helpfulNum": [1.0, 0.0],
                "createdAtMillis": [1000, 2000],
            }
        )

        result = validator.validate(ratings_df)

        assert "rater_1" in result.raters_with_insufficient_ratings

    def test_multiple_raters_with_insufficient_ratings(self, validator):
        """Multiple raters with insufficient ratings are all identified."""
        ratings_df = pd.DataFrame(
            {
                "noteId": ["note_1", "note_2", "note_3"],
                "raterParticipantId": ["rater_1", "rater_2", "rater_2"],
                "helpfulNum": [1.0, 1.0, 0.0],
                "createdAtMillis": [1000, 2000, 3000],
            }
        )

        result = validator.validate(ratings_df)

        assert "rater_1" in result.raters_with_insufficient_ratings
        assert "rater_2" in result.raters_with_insufficient_ratings


class TestScoringDataValidatorOverallValidation:
    """Tests for overall validation logic."""

    def test_valid_data_returns_is_valid_true(self):
        """Valid data returns is_valid=True."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        validator = ScoringDataValidator(min_raters_per_note=2, min_ratings_per_rater=2)

        ratings_df = pd.DataFrame(
            {
                "noteId": ["note_1", "note_1", "note_2", "note_2"],
                "raterParticipantId": ["rater_1", "rater_2", "rater_1", "rater_2"],
                "helpfulNum": [1.0, 1.0, 0.0, 0.0],
                "createdAtMillis": [1000, 2000, 3000, 4000],
            }
        )

        result = validator.validate(ratings_df)

        assert result.is_valid is True
        assert len(result.notes_with_insufficient_ratings) == 0
        assert len(result.raters_with_insufficient_ratings) == 0

    def test_invalid_notes_makes_overall_invalid(self):
        """Having notes with insufficient ratings makes overall validation invalid."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        validator = ScoringDataValidator(min_raters_per_note=3, min_ratings_per_rater=1)

        ratings_df = pd.DataFrame(
            {
                "noteId": ["note_1", "note_1"],
                "raterParticipantId": ["rater_1", "rater_2"],
                "helpfulNum": [1.0, 1.0],
                "createdAtMillis": [1000, 2000],
            }
        )

        result = validator.validate(ratings_df)

        assert result.is_valid is False

    def test_invalid_raters_makes_overall_invalid(self):
        """Having raters with insufficient ratings makes overall validation invalid."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        validator = ScoringDataValidator(min_raters_per_note=1, min_ratings_per_rater=3)

        ratings_df = pd.DataFrame(
            {
                "noteId": ["note_1", "note_2"],
                "raterParticipantId": ["rater_1", "rater_1"],
                "helpfulNum": [1.0, 0.0],
                "createdAtMillis": [1000, 2000],
            }
        )

        result = validator.validate(ratings_df)

        assert result.is_valid is False


class TestValidationResultSummary:
    """Tests for ValidationResult summary methods."""

    def test_validation_result_has_summary(self):
        """ValidationResult has a summary method."""
        from src.notes.scoring.scoring_data_validator import (
            ScoringDataValidator,
        )

        validator = ScoringDataValidator(min_raters_per_note=2, min_ratings_per_rater=2)
        ratings_df = pd.DataFrame(
            columns=["noteId", "raterParticipantId", "helpfulNum", "createdAtMillis"]
        )

        result = validator.validate(ratings_df)

        assert hasattr(result, "summary")
        summary = result.summary()
        assert isinstance(summary, dict)

    def test_summary_includes_counts(self):
        """Summary includes count information."""
        from src.notes.scoring.scoring_data_validator import ScoringDataValidator

        validator = ScoringDataValidator(min_raters_per_note=3, min_ratings_per_rater=3)
        ratings_df = pd.DataFrame(
            {
                "noteId": ["note_1", "note_1"],
                "raterParticipantId": ["rater_1", "rater_2"],
                "helpfulNum": [1.0, 0.0],
                "createdAtMillis": [1000, 2000],
            }
        )

        result = validator.validate(ratings_df)
        summary = result.summary()

        assert "notes_below_threshold" in summary
        assert "raters_below_threshold" in summary
