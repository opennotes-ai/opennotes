"""Comprehensive tests for password hashing module.

Tests cover:
- Argon2id hash generation for long tokens (>= 72 bytes)
- Bcrypt hash generation for short passwords (< 72 bytes)
- Legacy SHA256 verification with needs_rehash flag
- Argon2id configuration parameters (OWASP 2025)
- Edge cases (wrong password, None password, boundary conditions)
"""

import base64
import hashlib
import os

import pytest

from src.auth.password import _argon2_hasher, get_password_hash, verify_password


class TestArgon2idHashGeneration:
    """Tests for Argon2id hash generation with long tokens (>= 72 bytes)."""

    def test_long_token_produces_argon2_prefix(self):
        """Long tokens (>= 72 bytes) should produce 'argon2$' prefixed hashes."""
        long_token = "a" * 100
        hashed = get_password_hash(long_token)

        assert hashed.startswith("argon2$"), "Long token should produce argon2$ prefix"
        assert len(hashed) > len("argon2$"), "Hash should contain actual Argon2 hash after prefix"

    def test_argon2_hash_verification_works(self):
        """Argon2id hashes should verify correctly."""
        long_token = "a" * 100
        hashed = get_password_hash(long_token)

        is_valid, needs_rehash = verify_password(long_token, hashed)

        assert is_valid is True, "Correct token should verify"
        assert needs_rehash is False, "Argon2id hash should not need rehash"

    def test_argon2_needs_rehash_false(self):
        """Argon2id hashes should return needs_rehash=False."""
        long_token = "x" * 72
        hashed = get_password_hash(long_token)

        _, needs_rehash = verify_password(long_token, hashed)

        assert needs_rehash is False

    def test_argon2_hash_is_unique_per_call(self):
        """Each call to hash should produce a unique hash (due to salt)."""
        token = "a" * 100
        hash1 = get_password_hash(token)
        hash2 = get_password_hash(token)

        assert hash1 != hash2, "Argon2id should produce different hashes due to random salt"

    def test_argon2_hash_format(self):
        """Argon2id hash should have correct format after prefix."""
        token = "a" * 100
        hashed = get_password_hash(token)

        argon2_part = hashed[7:]
        assert argon2_part.startswith("$argon2id$"), (
            "Argon2 hash portion should be proper argon2id format"
        )


class TestBcryptHashGeneration:
    """Tests for bcrypt hash generation with short passwords (< 72 bytes)."""

    def test_short_password_produces_no_prefix(self):
        """Short passwords (< 72 bytes) should produce bcrypt hashes without prefix."""
        short_password = "mypassword123"
        hashed = get_password_hash(short_password)

        assert not hashed.startswith("argon2$"), "Short password should not have argon2$ prefix"
        assert not hashed.startswith("sha256$"), "Should not produce legacy sha256$ prefix"
        assert hashed.startswith("$2b$"), "Bcrypt hash should start with $2b$"

    def test_bcrypt_hash_verification_works(self):
        """Bcrypt hashes should verify correctly."""
        password = "securepassword"
        hashed = get_password_hash(password)

        is_valid, needs_rehash = verify_password(password, hashed)

        assert is_valid is True, "Correct password should verify"
        assert needs_rehash is False, "Bcrypt hash should not need rehash"

    def test_bcrypt_needs_rehash_false(self):
        """Bcrypt hashes should return needs_rehash=False."""
        password = "testpass"
        hashed = get_password_hash(password)

        _, needs_rehash = verify_password(password, hashed)

        assert needs_rehash is False

    def test_bcrypt_hash_is_unique_per_call(self):
        """Each call to hash should produce a unique hash (due to salt)."""
        password = "testpass"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2, "Bcrypt should produce different hashes due to random salt"

    def test_bcrypt_various_password_lengths(self):
        """Test bcrypt with various password lengths under 72 bytes."""
        test_passwords = [
            "a",
            "ab",
            "password",
            "a" * 50,
            "a" * 71,
        ]

        for password in test_passwords:
            hashed = get_password_hash(password)
            assert hashed.startswith("$2b$"), (
                f"Password of length {len(password)} should use bcrypt"
            )
            is_valid, _ = verify_password(password, hashed)
            assert is_valid is True, f"Password of length {len(password)} should verify"


class TestLegacySHA256Verification:
    """Tests for legacy SHA256 hash verification with needs_rehash flag."""

    def _create_legacy_sha256_hash(self, password: str) -> str:
        """Create a legacy SHA256 hash to simulate legacy data."""
        salt = os.urandom(16)
        password_bytes = password.encode("utf-8")
        salted = salt + password_bytes
        hash_digest = hashlib.sha256(salted).digest()
        combined = salt + hash_digest
        encoded = base64.b64encode(combined).decode("utf-8")
        return f"sha256${encoded}"

    def test_legacy_sha256_verification_works(self):
        """Legacy SHA256 hashes should verify correctly."""
        password = "old_password"
        legacy_hash = self._create_legacy_sha256_hash(password)

        is_valid, _needs_rehash = verify_password(password, legacy_hash)

        assert is_valid is True, "Legacy SHA256 hash should verify"

    def test_legacy_sha256_needs_rehash_true(self):
        """Legacy SHA256 hashes should return needs_rehash=True when valid."""
        password = "old_password"
        legacy_hash = self._create_legacy_sha256_hash(password)

        _, needs_rehash = verify_password(password, legacy_hash)

        assert needs_rehash is True, "Legacy SHA256 hash should indicate rehash needed"

    def test_legacy_sha256_wrong_password(self):
        """Wrong password against legacy SHA256 should return (False, False)."""
        password = "correct_password"
        legacy_hash = self._create_legacy_sha256_hash(password)

        is_valid, needs_rehash = verify_password("wrong_password", legacy_hash)

        assert is_valid is False, "Wrong password should not verify"
        assert needs_rehash is False, "No rehash needed for invalid password"

    def test_legacy_sha256_hash_format(self):
        """Verify the legacy SHA256 hash format is correct."""
        password = "test"
        legacy_hash = self._create_legacy_sha256_hash(password)

        assert legacy_hash.startswith("sha256$")
        decoded = base64.b64decode(legacy_hash[7:])
        assert len(decoded) == 16 + 32, "Should be 16 bytes salt + 32 bytes SHA256 hash"


class TestArgon2idConfiguration:
    """Tests for Argon2id configuration parameters (OWASP 2025)."""

    def test_memory_cost_is_19456(self):
        """Verify OWASP 2025 memory cost: 19456 KiB."""
        assert _argon2_hasher.memory_cost == 19456

    def test_time_cost_is_2(self):
        """Verify OWASP 2025 time cost: 2 iterations."""
        assert _argon2_hasher.time_cost == 2

    def test_parallelism_is_1(self):
        """Verify OWASP 2025 parallelism: 1 thread."""
        assert _argon2_hasher.parallelism == 1

    def test_argon2_produces_argon2id_variant(self):
        """Verify the hasher produces argon2id variant (not argon2i or argon2d)."""
        token = "a" * 100
        hashed = get_password_hash(token)
        argon2_part = hashed[7:]

        assert "$argon2id$" in argon2_part, "Should use argon2id variant"


class TestEdgeCases:
    """Tests for edge cases in password hashing."""

    def test_wrong_password_returns_false_false(self):
        """Wrong password should return (False, False) for all hash types."""
        password = "correct"
        hashed_bcrypt = get_password_hash(password)
        hashed_argon2 = get_password_hash("a" * 100)

        is_valid, needs_rehash = verify_password("wrong", hashed_bcrypt)
        assert (is_valid, needs_rehash) == (False, False)

        is_valid, needs_rehash = verify_password("wrong", hashed_argon2)
        assert (is_valid, needs_rehash) == (False, False)

    def test_none_password_raises_value_error(self):
        """None password should raise ValueError."""
        with pytest.raises(ValueError, match="Password cannot be None"):
            get_password_hash(None)

    def test_exactly_72_bytes_triggers_argon2(self):
        """Password of exactly 72 bytes should trigger Argon2id."""
        password_72_bytes = "a" * 72
        assert len(password_72_bytes.encode("utf-8")) == 72

        hashed = get_password_hash(password_72_bytes)

        assert hashed.startswith("argon2$"), "Exactly 72 bytes should use Argon2id"

    def test_71_bytes_uses_bcrypt(self):
        """Password of 71 bytes should use bcrypt."""
        password_71_bytes = "a" * 71
        assert len(password_71_bytes.encode("utf-8")) == 71

        hashed = get_password_hash(password_71_bytes)

        assert hashed.startswith("$2b$"), "71 bytes should use bcrypt"

    def test_empty_string_password(self):
        """Empty string password should use bcrypt and verify."""
        password = ""
        hashed = get_password_hash(password)

        assert hashed.startswith("$2b$"), "Empty string should use bcrypt"

        is_valid, needs_rehash = verify_password("", hashed)
        assert is_valid is True
        assert needs_rehash is False

    def test_unicode_password(self):
        """Unicode passwords should work correctly."""
        password = "p\u00e4ssw\u00f6rd"  # pässwörd
        hashed = get_password_hash(password)

        is_valid, _ = verify_password(password, hashed)
        assert is_valid is True

    def test_unicode_long_token(self):
        """Unicode tokens >= 72 bytes should use Argon2id."""
        unicode_token = "\u4e2d\u6587" * 50
        assert len(unicode_token.encode("utf-8")) >= 72

        hashed = get_password_hash(unicode_token)

        assert hashed.startswith("argon2$"), "Long unicode token should use Argon2id"

        is_valid, needs_rehash = verify_password(unicode_token, hashed)
        assert is_valid is True
        assert needs_rehash is False

    def test_malformed_argon2_hash(self):
        """Malformed Argon2 hash should return (False, False)."""
        malformed_hash = "argon2$not-a-valid-argon2-hash"

        is_valid, needs_rehash = verify_password("anything", malformed_hash)

        assert (is_valid, needs_rehash) == (False, False)

    def test_malformed_sha256_hash(self):
        """Malformed SHA256 hash should return (False, False)."""
        malformed_hash = "sha256$not-valid-base64!!!"

        is_valid, needs_rehash = verify_password("anything", malformed_hash)

        assert (is_valid, needs_rehash) == (False, False)

    def test_malformed_bcrypt_hash(self):
        """Malformed bcrypt hash should return (False, False)."""
        malformed_hash = "$2b$12$not-a-valid-bcrypt-hash"

        is_valid, needs_rehash = verify_password("anything", malformed_hash)

        assert (is_valid, needs_rehash) == (False, False)

    def test_password_with_special_characters(self):
        """Passwords with special characters should work."""
        password = "p@$$w0rd!#%^&*(){}[]|\\:;<>?/"
        hashed = get_password_hash(password)

        is_valid, _ = verify_password(password, hashed)
        assert is_valid is True

    def test_password_with_newlines(self):
        """Passwords with newlines should work."""
        password = "line1\nline2\rline3\r\nline4"
        hashed = get_password_hash(password)

        is_valid, _ = verify_password(password, hashed)
        assert is_valid is True

    def test_password_with_null_bytes(self):
        """Passwords with null bytes should work."""
        password = "before\x00after"
        hashed = get_password_hash(password)

        is_valid, _ = verify_password(password, hashed)
        assert is_valid is True
