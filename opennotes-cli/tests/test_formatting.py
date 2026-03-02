from __future__ import annotations

from opennotes_cli.formatting import truncate_uuid


def test_truncate_uuid_standard():
    result = truncate_uuid("019c9757-1234-7abc-8a3c-7f4e")
    assert result == "019\u20268a3c-7f4e"


def test_truncate_uuid_different_values_are_distinguishable():
    u1 = truncate_uuid("019c9757-1234-7abc-8a3c-7f4e")
    u2 = truncate_uuid("019c9757-5678-7def-9b2d-1a5e")
    assert u1 != u2


def test_truncate_uuid_short_string_passthrough():
    assert truncate_uuid("short") == "short"


def test_truncate_uuid_exactly_at_boundary():
    s = "0123456789abc"
    assert truncate_uuid(s) == s


def test_truncate_uuid_one_over_boundary():
    s = "0123456789abcd"
    assert truncate_uuid(s) == "012\u202656789abcd"


def test_truncate_uuid_empty_string():
    assert truncate_uuid("") == ""


def test_truncate_uuid_custom_lengths():
    result = truncate_uuid("019c9757-1234-7abc-8a3c-7f4e", prefix_len=5, tail_len=12)
    assert result == "019c9\u2026bc-8a3c-7f4e"


def test_truncate_uuid_preserves_full_uuid_format_awareness():
    full = "019c9757-1234-7abc-8a3c-7f4e12345678"
    result = truncate_uuid(full)
    assert result.startswith("019")
    assert result.endswith("2345678")
    assert "\u2026" in result
