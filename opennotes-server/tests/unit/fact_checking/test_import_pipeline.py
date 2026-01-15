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
    """Tests for rating normalization.

    normalize_rating() returns a tuple of (canonical_rating, rating_details).
    rating_details is set when the original rating differs from the canonical.
    """

    @pytest.mark.parametrize(
        ("input_rating", "expected_canonical", "expected_details"),
        [
            ("False", "false", None),
            ("false", "false", None),
            ("FALSE", "false", None),
            ("True", "true", None),
            ("true", "true", None),
            ("TRUE", "true", None),
            ("Mostly False", "mostly_false", None),
            ("mostly true", "mostly_true", None),
            ("Mixture", "mixture", None),
            ("mixed", "mixture", None),
            ("Half True", "mixture", None),
            ("Pants on Fire", "false", None),
            ("pants on fire", "false", None),
            ("Four Pinocchios", "false", None),
            ("Unproven", "unproven", None),
            ("unverified", "unproven", None),
            ("Misleading", "misleading", None),
            ("Satire", "satire", None),
            ("Outdated", "outdated", None),
        ],
    )
    def test_known_ratings(
        self, input_rating: str, expected_canonical: str, expected_details: str | None
    ) -> None:
        """Test normalization of known rating values."""
        canonical, details = normalize_rating(input_rating)
        assert canonical == expected_canonical
        assert details == expected_details

    @pytest.mark.parametrize(
        ("input_rating", "expected_canonical", "expected_details"),
        [
            ("Faux", "false", None),
            ("faux", "false", None),
            ("FAUX", "false", None),
            ("Vrai", "true", None),
            ("vrai", "true", None),
            ("Trompeur", "misleading", None),
            ("Plutôt Vrai", "mostly_true", None),
            ("Plutôt Faux", "mostly_false", None),
            ("C'est plus compliqué", "mixture", None),
            ("Partiellement faux", "mixture", None),
            ("Contexte manquant", "misleading", "missing_context"),
            ("Infondé", "unproven", None),
            ("Montage", "false", "altered"),
            ("Photomontage", "false", "altered"),
            ("Détourné", "misleading", "out_of_context"),
            ("Exagéré", "misleading", "exaggerated"),
            ("Arnaque", "false", "scam"),
        ],
    )
    def test_french_ratings(
        self, input_rating: str, expected_canonical: str, expected_details: str | None
    ) -> None:
        """Test normalization of French rating values."""
        canonical, details = normalize_rating(input_rating)
        assert canonical == expected_canonical
        assert details == expected_details

    @pytest.mark.parametrize(
        ("input_rating", "expected_canonical", "expected_details"),
        [
            ("Falso", "false", None),
            ("Verdadero", "true", None),
            ("Engañoso", "misleading", None),
            ("Parcialmente falso", "mostly_false", None),
            ("Parcialmente verdadero", "mostly_true", None),
            ("Sin contexto", "misleading", "missing_context"),
            ("Sin pruebas", "unproven", None),
            ("Sátira", "satire", None),
            ("Estafa", "false", "scam"),
        ],
    )
    def test_spanish_ratings(
        self, input_rating: str, expected_canonical: str, expected_details: str | None
    ) -> None:
        """Test normalization of Spanish rating values."""
        canonical, details = normalize_rating(input_rating)
        assert canonical == expected_canonical
        assert details == expected_details

    @pytest.mark.parametrize(
        ("input_rating", "expected_canonical", "expected_details"),
        [
            ("Falsch", "false", None),
            ("Wahr", "true", None),
            ("Irreführend", "misleading", None),
            ("Teilweise falsch", "mostly_false", None),
            ("Teilweise wahr", "mostly_true", None),
            ("Unbelegt", "unproven", None),
            ("Manipuliert", "false", "altered"),
            ("Fehlender Kontext", "misleading", "missing_context"),
        ],
    )
    def test_german_ratings(
        self, input_rating: str, expected_canonical: str, expected_details: str | None
    ) -> None:
        """Test normalization of German rating values."""
        canonical, details = normalize_rating(input_rating)
        assert canonical == expected_canonical
        assert details == expected_details

    @pytest.mark.parametrize(
        ("input_rating", "expected_canonical", "expected_details"),
        [
            ("Verdadeiro", "true", None),
            ("Enganoso", "misleading", None),
            ("Parcialmente verdadeiro", "mostly_true", None),
            ("Sem provas", "unproven", None),
            ("Fora de contexto", "misleading", "out_of_context"),
        ],
    )
    def test_portuguese_ratings(
        self, input_rating: str, expected_canonical: str, expected_details: str | None
    ) -> None:
        """Test normalization of Portuguese rating values."""
        canonical, details = normalize_rating(input_rating)
        assert canonical == expected_canonical
        assert details == expected_details

    @pytest.mark.parametrize(
        ("input_rating", "expected_canonical", "expected_details"),
        [
            ("Vero", "true", None),
            ("Fuorviante", "misleading", None),
            ("Parzialmente falso", "mostly_false", None),
            ("Parzialmente vero", "mostly_true", None),
            ("Senza prove", "unproven", None),
            ("Satira", "satire", None),
        ],
    )
    def test_italian_ratings(
        self, input_rating: str, expected_canonical: str, expected_details: str | None
    ) -> None:
        """Test normalization of Italian rating values."""
        canonical, details = normalize_rating(input_rating)
        assert canonical == expected_canonical
        assert details == expected_details

    @pytest.mark.parametrize(
        ("input_rating", "expected_canonical", "expected_details"),
        [
            ("Vals", "false", None),
            ("Waar", "true", None),
            ("Misleidend", "misleading", None),
            ("Onbewezen", "unproven", None),
        ],
    )
    def test_dutch_ratings(
        self, input_rating: str, expected_canonical: str, expected_details: str | None
    ) -> None:
        """Test normalization of Dutch rating values."""
        canonical, details = normalize_rating(input_rating)
        assert canonical == expected_canonical
        assert details == expected_details

    @pytest.mark.parametrize(
        ("input_rating", "expected_canonical", "expected_details"),
        [
            ("Missing Context", "misleading", "missing_context"),
            ("Needs Context", "misleading", "missing_context"),
            ("Altered", "false", "altered"),
            ("Digitally Altered", "false", "altered"),
            ("Manipulated", "false", "altered"),
            ("Doctored", "false", "altered"),
            ("Miscaptioned", "false", "miscaptioned"),
            ("Wrong Caption", "false", "miscaptioned"),
            ("Misattributed", "false", "misattributed"),
            ("Wrong Attribution", "false", "misattributed"),
            ("Correct Attribution", "true", "correct_attribution"),
            ("Labeled Satire", "satire", None),
            ("Originated as Satire", "satire", None),
            ("Scam", "false", "scam"),
            ("Fraud", "false", "scam"),
            ("Out of Context", "misleading", "out_of_context"),
            ("Taken Out of Context", "misleading", "out_of_context"),
            ("Exaggerated", "misleading", "exaggerated"),
            ("Exaggeration", "misleading", "exaggerated"),
            ("In Progress", None, "in_progress"),
            ("Under Review", None, "in_progress"),
            ("Explainer", None, "explainer"),
            ("Full Flop", None, "flip"),
            ("Half Flip", None, "flip"),
            ("Recall", None, "recall"),
            ("Fake", "false", None),
            ("Fabricated", "false", None),
            ("Unfounded", "unproven", None),
            ("No Evidence", "unproven", None),
        ],
    )
    def test_content_type_ratings(
        self, input_rating: str, expected_canonical: str | None, expected_details: str | None
    ) -> None:
        """Test normalization of English content type ratings."""
        canonical, details = normalize_rating(input_rating)
        assert canonical == expected_canonical
        assert details == expected_details

    def test_none_input(self) -> None:
        """Test None input returns (None, None)."""
        assert normalize_rating(None) == (None, None)

    def test_empty_string(self) -> None:
        """Test empty string returns (None, None)."""
        assert normalize_rating("") == (None, None)
        assert normalize_rating("   ") == (None, None)

    def test_unknown_rating_normalized(self) -> None:
        """Test unknown ratings are converted to lowercase snake_case with original as details."""
        canonical, details = normalize_rating("Some Unknown Rating")
        assert canonical == "some_unknown_rating"
        assert details == "Some Unknown Rating"

    def test_whitespace_stripped(self) -> None:
        """Test whitespace is stripped from ratings."""
        assert normalize_rating("  False  ") == ("false", None)
        assert normalize_rating("\tTrue\n") == ("true", None)


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
        assert candidate.predicted_ratings == {"false": 1.0}
        assert candidate.rating_details is None
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
        assert candidate.rating_details is None

    def test_intermediate_rating_produces_rating_details(self) -> None:
        """Test that intermediate ratings map to canonical with rating_details."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="Test",
            publisher_site="example.com",
            rating="Missing Context",
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        assert candidate.predicted_ratings == {"misleading": 1.0}
        assert candidate.rating_details == "missing_context"

    def test_skipped_rating_yields_none_predicted_ratings(self) -> None:
        """Test that skipped ratings (in_progress, explainer, etc.) produce None canonical."""
        row = ClaimReviewRow(
            id=1,
            claim_id=100,
            fact_check_id=200,
            claim="Test",
            url="https://example.com",
            title="Test",
            publisher_name="Test",
            publisher_site="example.com",
            rating="In Progress",
        )

        candidate = NormalizedCandidate.from_claim_review_row(row)
        assert candidate.predicted_ratings is None
        assert candidate.rating_details == "in_progress"

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


class TestBatchedFunction:
    """Tests for the batched() helper function."""

    def test_batched_exact_multiple(self) -> None:
        """Test batching when items are exact multiple of batch size."""
        from src.fact_checking.import_pipeline.importer import batched

        items = list(range(10))
        batches = list(batched(iter(items), 5))

        assert len(batches) == 2
        assert batches[0] == [0, 1, 2, 3, 4]
        assert batches[1] == [5, 6, 7, 8, 9]
        assert sum(len(b) for b in batches) == 10

    def test_batched_partial_final_batch(self) -> None:
        """Test batching with partial final batch."""
        from src.fact_checking.import_pipeline.importer import batched

        items = list(range(12))
        batches = list(batched(iter(items), 5))

        assert len(batches) == 3
        assert batches[0] == [0, 1, 2, 3, 4]
        assert batches[1] == [5, 6, 7, 8, 9]
        assert batches[2] == [10, 11]
        assert sum(len(b) for b in batches) == 12

    def test_batched_empty_iterator(self) -> None:
        """Test batching empty iterator."""
        from src.fact_checking.import_pipeline.importer import batched

        batches = list(batched(iter([]), 5))
        assert batches == []

    def test_batched_single_item(self) -> None:
        """Test batching single item."""
        from src.fact_checking.import_pipeline.importer import batched

        batches = list(batched(iter([1]), 5))
        assert len(batches) == 1
        assert batches[0] == [1]

    def test_batched_preserves_all_items(self) -> None:
        """Test that batching preserves all items without loss."""
        from src.fact_checking.import_pipeline.importer import batched

        original = list(range(43954))
        batch_size = 1000
        batches = list(batched(iter(original), batch_size))

        total_items = sum(len(b) for b in batches)
        assert total_items == 43954

        reconstructed = [item for batch in batches for item in batch]
        assert reconstructed == original


class TestValidateAndNormalizeBatchRowAccounting:
    """Tests for row accounting in validate_and_normalize_batch."""

    def test_all_valid_rows_counted(self) -> None:
        """Test that all valid rows are counted correctly."""
        from src.fact_checking.import_pipeline.importer import validate_and_normalize_batch

        rows = [
            {
                "id": i,
                "claim_id": 100 + i,
                "fact_check_id": 200 + i,
                "claim": f"Test claim {i}",
                "url": f"https://example.com/{i}",
                "title": f"Test {i}",
                "publisher_name": "Publisher",
                "publisher_site": "example.com",
            }
            for i in range(10)
        ]

        candidates, errors = validate_and_normalize_batch(rows)

        assert len(candidates) + len(errors) == len(rows)
        assert len(candidates) == 10
        assert len(errors) == 0

    def test_all_invalid_rows_counted(self) -> None:
        """Test that all invalid rows are counted as errors."""
        from src.fact_checking.import_pipeline.importer import validate_and_normalize_batch

        rows = [{"id": i, "incomplete": "row"} for i in range(10)]

        candidates, errors = validate_and_normalize_batch(rows)

        assert len(candidates) + len(errors) == len(rows)
        assert len(candidates) == 0
        assert len(errors) == 10

    def test_mixed_valid_invalid_rows_counted(self) -> None:
        """Test that mixed valid/invalid rows are all accounted for."""
        from src.fact_checking.import_pipeline.importer import validate_and_normalize_batch

        valid_row = {
            "id": 1,
            "claim_id": 100,
            "fact_check_id": 200,
            "claim": "Test claim",
            "url": "https://example.com",
            "title": "Test",
            "publisher_name": "Publisher",
            "publisher_site": "example.com",
        }
        invalid_row = {"id": 2, "incomplete": "row"}

        rows = [valid_row, invalid_row, valid_row.copy(), invalid_row.copy()]
        rows[2]["id"] = 3
        rows[3]["id"] = 4

        candidates, errors = validate_and_normalize_batch(rows)

        assert len(candidates) + len(errors) == len(rows)
        assert len(candidates) == 2
        assert len(errors) == 2

    def test_row_accounting_with_batch_num_logging(self) -> None:
        """Test that batch_num parameter is passed for diagnostic logging."""
        from src.fact_checking.import_pipeline.importer import validate_and_normalize_batch

        rows = [
            {
                "id": 1,
                "claim_id": 100,
                "fact_check_id": 200,
                "claim": "Test claim",
                "url": "https://example.com",
                "title": "Test",
                "publisher_name": "Publisher",
                "publisher_site": "example.com",
            }
        ]

        candidates, errors = validate_and_normalize_batch(rows, batch_num=42)

        assert len(candidates) + len(errors) == 1

    def test_error_messages_include_batch_num(self) -> None:
        """Test that error messages include batch_num when provided."""
        from src.fact_checking.import_pipeline.importer import validate_and_normalize_batch

        rows = [{"id": "bad_row"}]
        _, errors = validate_and_normalize_batch(rows, batch_num=5)

        assert len(errors) == 1
        assert "Batch 5, " in errors[0]
        assert "Row bad_row" in errors[0]

    def test_error_messages_without_batch_num(self) -> None:
        """Test that error messages work without batch_num."""
        from src.fact_checking.import_pipeline.importer import validate_and_normalize_batch

        rows = [{"id": "bad_row"}]
        _, errors = validate_and_normalize_batch(rows, batch_num=None)

        assert len(errors) == 1
        assert "Batch" not in errors[0]
        assert "Row bad_row" in errors[0]
