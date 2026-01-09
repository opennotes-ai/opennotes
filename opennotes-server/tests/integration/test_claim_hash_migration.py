"""Tests for claim_hash migration backfill logic.

Verifies that the migration correctly handles NULL claim values by generating
unique placeholder hashes using the row UUID, preventing collisions.
"""

import sys
from pathlib import Path

import xxhash

alembic_versions_dir = Path(__file__).parents[2] / "alembic" / "versions"
if str(alembic_versions_dir) not in sys.path:
    sys.path.insert(0, str(alembic_versions_dir))

from task_984_add_claim_hash_column import compute_claim_hash  # noqa: E402


class TestClaimHashMigration:
    """Tests for the claim_hash migration compute function."""

    def test_compute_claim_hash_with_claim_text(self):
        """Valid claim text produces deterministic hash."""
        claim = "The earth is flat"
        expected = xxhash.xxh3_64(claim.encode()).hexdigest()

        result = compute_claim_hash(claim)

        assert result == expected
        assert len(result) == 16

    def test_compute_claim_hash_with_null_claim_uses_row_id(self):
        """NULL claim with row_id produces unique placeholder hash."""
        row_id = "550e8400-e29b-41d4-a716-446655440000"
        expected = xxhash.xxh3_64(f"__NULL_CLAIM__{row_id}".encode()).hexdigest()

        result = compute_claim_hash(None, row_id)

        assert result == expected
        assert len(result) == 16

    def test_compute_claim_hash_null_claims_different_rows_produce_different_hashes(
        self,
    ):
        """Multiple NULL claims with different row IDs produce unique hashes."""
        row_id_1 = "550e8400-e29b-41d4-a716-446655440001"
        row_id_2 = "550e8400-e29b-41d4-a716-446655440002"

        hash_1 = compute_claim_hash(None, row_id_1)
        hash_2 = compute_claim_hash(None, row_id_2)

        assert hash_1 != hash_2

    def test_compute_claim_hash_empty_string_treated_as_valid_claim(self):
        """Empty string claim is hashed directly, not as NULL."""
        row_id = "550e8400-e29b-41d4-a716-446655440000"
        expected_empty = xxhash.xxh3_64(b"").hexdigest()

        result = compute_claim_hash("", row_id)

        assert result == expected_empty

    def test_compute_claim_hash_no_row_id_falls_back_to_empty_hash(self):
        """NULL claim without row_id produces empty string hash."""
        expected = xxhash.xxh3_64(b"").hexdigest()

        result = compute_claim_hash(None)

        assert result == expected
