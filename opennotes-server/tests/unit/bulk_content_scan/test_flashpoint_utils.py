"""Unit tests for flashpoint_utils.parse_bool."""

import pytest

from src.bulk_content_scan.flashpoint_utils import parse_bool


class TestParseBool:
    """Tests for parse_bool covering bool passthrough, positive/negative strings,
    unrecognized strings, and non-string types."""

    @pytest.mark.parametrize("value", [True, False])
    def test_bool_passthrough(self, value: bool):
        assert parse_bool(value) is value

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "yes", "Yes", "1", "y", "Y"])
    def test_positive_strings(self, value: str):
        assert parse_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "no", "No", "0", "n", "N"])
    def test_negative_strings(self, value: str):
        assert parse_bool(value) is False

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("something", True),
            ("", False),
        ],
    )
    def test_unrecognized_strings_fall_through_to_bool(self, value: str, expected: bool):
        assert parse_bool(value) is expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1, True),
            (0, False),
            (42, True),
            (0.0, False),
            (3.14, True),
            (None, False),
            ([], False),
            ([1], True),
        ],
    )
    def test_non_string_types(self, value, expected: bool):
        assert parse_bool(value) is expected
