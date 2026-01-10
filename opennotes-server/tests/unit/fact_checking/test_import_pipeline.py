"""Unit tests for fact-check import pipeline.

Tests rating normalization, schema validation, and candidate transformation.
"""

from datetime import datetime

import pytest

from src.fact_checking.candidate_models import compute_claim_hash
from src.fact_checking.import_pipeline.rating_normalizer import normalize_rating
from src.fact_checking.import_pipeline.schemas import ClaimReviewRow, NormalizedCandidate


class TestComputeClaimHash:
    """Tests for claim hash computation."""

    def test_deterministic_hash(self) -> None:
        """Test that the same input always produces the same hash."""
        claim = "This is a test claim"
        hash1 = compute_claim_hash(claim)
        hash2 = compute_claim_hash(claim)
        assert hash1 == hash2

    def test_hash_is_16_chars(self) -> None:
        """Test that hash is exactly 16 characters (64-bit xxh3 hex)."""
        hash_result = compute_claim_hash("test claim")
        assert len(hash_result) == 16
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_different_claims_different_hashes(self) -> None:
        """Test that different claims produce different hashes."""
        hash1 = compute_claim_hash("Claim about 558,000 migrants")
        hash2 = compute_claim_hash("Claim about one million migrants")
        assert hash1 != hash2

    def test_none_input(self) -> None:
        """Test that None produces a consistent hash (empty string hash)."""
        hash1 = compute_claim_hash(None)
        hash2 = compute_claim_hash(None)
        hash3 = compute_claim_hash("")
        assert hash1 == hash2
        assert hash1 == hash3  # None and empty string should hash the same

    def test_empty_string(self) -> None:
        """Test that empty string produces a valid hash."""
        hash_result = compute_claim_hash("")
        assert len(hash_result) == 16

    def test_unicode_claim(self) -> None:
        """Test that unicode claims are hashed correctly."""
        claim = "Test claim with unicode: "
        hash_result = compute_claim_hash(claim)
        assert len(hash_result) == 16

    def test_whitespace_variations_different_hashes(self) -> None:
        """Test that claims with different whitespace produce different hashes."""
        hash1 = compute_claim_hash("test claim")
        hash2 = compute_claim_hash("test  claim")  # Extra space
        hash3 = compute_claim_hash(" test claim ")  # Leading/trailing spaces
        # All should be different (no normalization in hash)
        assert len({hash1, hash2, hash3}) == 3


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
        assert candidate.claim_hash == compute_claim_hash("This is a test claim")
        assert candidate.title == "Fact Check: Test Claim"
        # Rating goes to predicted_ratings (trusted source at 1.0 probability)
        assert candidate.predicted_ratings == {"false": 1.0}
        assert candidate.dataset_name == "snopes.com"
        assert candidate.dataset_tags == ["Snopes"]
        assert candidate.original_id == "200"
        assert candidate.extracted_data["claim"] == "This is a test claim"
        assert candidate.extracted_data["claimant"] == "John Doe"

    def test_claim_hash_computed_from_claim_text(self) -> None:
        """Test that claim_hash is correctly computed from claim text."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="558,000 migrants entered the UK illegally",
            url="https://example.com/article",
            title="Test",
            publisher_name="Test",
            publisher_site="example.com",
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        expected_hash = compute_claim_hash("558,000 migrants entered the UK illegally")
        assert candidate.claim_hash == expected_hash
        assert len(candidate.claim_hash) == 16

    def test_different_claims_same_url_different_hash(self) -> None:
        """Test that same URL with different claims produces different hashes.

        This is the core deduplication scenario: one fact-check article (URL)
        can check multiple distinct claims. Each should have a unique hash.
        """
        url = "https://fullfact.org/immigration/migration-numbers"

        row1 = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="558,000 migrants entered the UK illegally",
            url=url,
            title="Full Fact Check: UK Migration",
            publisher_name="Full Fact",
            publisher_site="fullfact.org",
        )

        row2 = ClaimReviewRow(
            id=2,
            claim_id=101,
            fact_check_id=200,  # Same fact_check_id = same article
            claim="One million migrants arrived in 2023",
            url=url,  # Same URL
            title="Full Fact Check: UK Migration",
            publisher_name="Full Fact",
            publisher_site="fullfact.org",
        )

        candidate1 = NormalizedCandidate.from_claim_review_row(row1)
        candidate2 = NormalizedCandidate.from_claim_review_row(row2)

        # Same URL, but different claim_hash values
        assert candidate1.source_url == candidate2.source_url
        assert candidate1.claim_hash != candidate2.claim_hash

    def test_no_rating_yields_none_predicted_ratings(self) -> None:
        """Test that missing rating results in None predicted_ratings."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="Test",
            publisher_site="example.com",
            rating=None,
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        assert candidate.predicted_ratings is None

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

    def test_claim_hash_pattern_validation(self) -> None:
        """Test that claim_hash field validates 16 hex character pattern."""
        from pydantic import ValidationError

        valid_hash = "a1b2c3d4e5f6a7b8"  # 16 hex chars
        candidate = NormalizedCandidate(
            source_url="https://example.com",
            claim_hash=valid_hash,
            title="Test",
            dataset_name="test",
            original_id="1",
        )
        assert candidate.claim_hash == valid_hash

        invalid_hashes = [
            "abc123",  # Too short
            "a1b2c3d4e5f6a7b8a9",  # Too long
            "ghijklmnopqrstuv",  # Not hex
            "A1B2C3D4E5F6A7B8",  # Uppercase (not lowercase hex)
        ]
        for invalid_hash in invalid_hashes:
            with pytest.raises(ValidationError):
                NormalizedCandidate(
                    source_url="https://example.com",
                    claim_hash=invalid_hash,
                    title="Test",
                    dataset_name="test",
                    original_id="1",
                )
