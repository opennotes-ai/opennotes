"""Unit tests for fact-check import pipeline.

Tests rating normalization, schema validation, and candidate transformation.
"""

from datetime import datetime

import pytest

from src.fact_checking.import_pipeline.rating_normalizer import normalize_rating
from src.fact_checking.import_pipeline.schemas import ClaimReviewRow, NormalizedCandidate


class TestRatingNormalizer:
    """Tests for rating normalization."""

    @pytest.mark.parametrize(
        ("input_rating", "expected"),
        [
            ("False", "false"),
            ("false", "false"),
            ("FALSE", "false"),
            ("True", "true"),
            ("true", "true"),
            ("TRUE", "true"),
            ("Mostly False", "mostly_false"),
            ("mostly true", "mostly_true"),
            ("Mixture", "mixture"),
            ("mixed", "mixture"),
            ("Half True", "mixture"),
            ("Pants on Fire", "false"),
            ("pants on fire", "false"),
            ("Four Pinocchios", "false"),
            ("Unproven", "unproven"),
            ("unverified", "unproven"),
            ("Misleading", "misleading"),
            ("Satire", "satire"),
            ("Outdated", "outdated"),
        ],
    )
    def test_known_ratings(self, input_rating: str, expected: str) -> None:
        """Test normalization of known rating values."""
        assert normalize_rating(input_rating) == expected

    def test_none_input(self) -> None:
        """Test None input returns None."""
        assert normalize_rating(None) is None

    def test_empty_string(self) -> None:
        """Test empty string returns None."""
        assert normalize_rating("") is None
        assert normalize_rating("   ") is None

    def test_unknown_rating_normalized(self) -> None:
        """Test unknown ratings are converted to lowercase snake_case."""
        result = normalize_rating("Some Unknown Rating")
        assert result == "some_unknown_rating"

    def test_whitespace_stripped(self) -> None:
        """Test whitespace is stripped from ratings."""
        assert normalize_rating("  False  ") == "false"
        assert normalize_rating("\tTrue\n") == "true"


class TestClaimReviewRow:
    """Tests for ClaimReviewRow Pydantic model."""

    def test_valid_row(self) -> None:
        """Test parsing a valid CSV row."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test claim",
            url="https://example.com/article",
            title="Test Article",
            publisher_name="Test Publisher",
            publisher_site="example.com",
        )
        assert row.id == 1
        assert row.claim == "Test claim"
        assert row.url == "https://example.com/article"

    def test_optional_fields(self) -> None:
        """Test optional fields default to None."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="Test",
            publisher_site="example.com",
        )
        assert row.claimant is None
        assert row.claim_date is None
        assert row.rating is None
        assert row.tweet_ids is None

    def test_whitespace_stripping(self) -> None:
        """Test that string fields are stripped."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="  Test claim  ",
            url="  https://example.com  ",
            title="  Test Title  ",
            publisher_name="Publisher",
            publisher_site="example.com",
        )
        assert row.claim == "Test claim"
        assert row.url == "https://example.com"
        assert row.title == "Test Title"


class TestNormalizedCandidate:
    """Tests for NormalizedCandidate transformation."""

    def test_from_claim_review_row(self) -> None:
        """Test conversion from ClaimReviewRow to NormalizedCandidate."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="This is a test claim",
            claimant="John Doe",
            url="https://snopes.com/fact-check/test",
            title="Fact Check: Test Claim",
            publisher_name="Snopes",
            publisher_site="www.snopes.com",
            rating="False",
            review_date="2024-01-15",
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)

        assert candidate.source_url == "https://snopes.com/fact-check/test"
        assert candidate.title == "Fact Check: Test Claim"
        assert candidate.rating == "false"
        assert candidate.dataset_name == "snopes.com"
        assert candidate.dataset_tags == ["Snopes"]
        assert candidate.original_id == "200"
        assert candidate.extracted_data["claim"] == "This is a test claim"
        assert candidate.extracted_data["claimant"] == "John Doe"

    def test_date_parsing_iso(self) -> None:
        """Test ISO date format parsing."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="Test",
            publisher_site="example.com",
            review_date="2024-01-15T10:30:00",
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        assert candidate.published_date is not None
        assert candidate.published_date.year == 2024
        assert candidate.published_date.month == 1
        assert candidate.published_date.day == 15

    def test_date_parsing_ymd(self) -> None:
        """Test Y-M-D date format parsing."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="Test",
            publisher_site="example.com",
            review_date="2024-01-15",
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        assert candidate.published_date is not None
        assert isinstance(candidate.published_date, datetime)

    def test_tweet_ids_json_parsing(self) -> None:
        """Test tweet_ids JSON array parsing."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="Test",
            publisher_site="example.com",
            tweet_ids='["123456", "789012"]',
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        assert candidate.extracted_data["tweet_ids"] == ["123456", "789012"]

    def test_tweet_ids_comma_parsing(self) -> None:
        """Test tweet_ids comma-separated parsing."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="Test",
            publisher_site="example.com",
            tweet_ids="123456, 789012",
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        assert candidate.extracted_data["tweet_ids"] == ["123456", "789012"]

    def test_languages_extraction(self) -> None:
        """Test language fields are extracted correctly."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="Test",
            publisher_site="example.com",
            claim_lang="en",
            fc_lang="es",
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        assert candidate.extracted_data["languages"] == ["en", "es"]

    def test_dataset_name_extraction(self) -> None:
        """Test dataset_name is extracted from publisher_site."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="Test",
            publisher_site="www.politifact.com/factchecks",
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        assert candidate.dataset_name == "politifact.com"

    def test_empty_publisher_name_uses_dataset_name(self) -> None:
        """Test that empty publisher_name falls back to dataset_name for tags."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="",
            publisher_site="snopes.com",
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        assert candidate.dataset_tags == ["snopes.com"]
