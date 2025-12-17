"""Unit tests for cache module."""

import hashlib

import xxhash

from src.cache.cache import CacheManager


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_short_key_not_hashed(self) -> None:
        """Short keys (<=100 chars) should not be hashed."""
        manager = CacheManager.__new__(CacheManager)
        key = manager._generate_key("prefix", "short", "key")
        assert key == "prefix:short:key"

    def test_long_key_is_hashed(self) -> None:
        """Long keys (>100 chars) should be hashed."""
        manager = CacheManager.__new__(CacheManager)
        long_arg = "x" * 150
        key = manager._generate_key("prefix", long_arg)
        assert key.startswith("prefix:")
        assert len(key) < len(f"prefix:{long_arg}")

    def test_long_key_uses_xxhash3_not_md5(self) -> None:
        """Long keys should use xxhash3, not MD5, for performance."""
        manager = CacheManager.__new__(CacheManager)
        long_arg = "x" * 150
        key = manager._generate_key("prefix", long_arg)

        key_string = long_arg
        expected_xxhash = xxhash.xxh3_64(key_string.encode()).hexdigest()
        wrong_md5 = hashlib.md5(key_string.encode()).hexdigest()

        assert key == f"prefix:{expected_xxhash}", (
            f"Expected xxhash3 hash but got: {key}. If using MD5, would be prefix:{wrong_md5}"
        )

    def test_kwargs_included_in_key(self) -> None:
        """Keyword arguments should be included in the key."""
        manager = CacheManager.__new__(CacheManager)
        key = manager._generate_key("prefix", "arg1", foo="bar", baz="qux")
        assert "foo=bar" in key
        assert "baz=qux" in key

    def test_kwargs_sorted_for_consistency(self) -> None:
        """Kwargs should be sorted for consistent key generation."""
        manager = CacheManager.__new__(CacheManager)
        key1 = manager._generate_key("prefix", foo="1", bar="2", zeta="3")
        key2 = manager._generate_key("prefix", zeta="3", foo="1", bar="2")
        assert key1 == key2

    def test_empty_args_returns_prefix_only(self) -> None:
        """Empty args should return just the prefix."""
        manager = CacheManager.__new__(CacheManager)
        key = manager._generate_key("prefix")
        assert key == "prefix"

    def test_long_key_with_kwargs_uses_xxhash3(self) -> None:
        """Long keys with kwargs should also use xxhash3."""
        manager = CacheManager.__new__(CacheManager)
        long_arg = "y" * 50
        key = manager._generate_key("prefix", long_arg, extra="z" * 60)

        key_parts = [long_arg, "extra=" + "z" * 60]
        key_string = ":".join(key_parts)
        assert len(key_string) > 100

        expected_xxhash = xxhash.xxh3_64(key_string.encode()).hexdigest()
        assert key == f"prefix:{expected_xxhash}"
