"""Unit tests for flashpoint_utils.parse_bool and parse_derailment_score."""

import logging

import pytest

from src.bulk_content_scan.flashpoint_utils import parse_bool, parse_derailment_score


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
        "value",
        [
            "maybe",
            "uncertain",
            "something",
            "The conversation might derail",
            "I think so",
            "possibly",
        ],
    )
    def test_unrecognized_strings_return_false(self, value: str, caplog):
        with caplog.at_level(logging.WARNING, logger="src.bulk_content_scan.flashpoint_utils"):
            result = parse_bool(value)
        assert result is False
        assert "unrecognized string" in caplog.text

    def test_empty_string_returns_false(self):
        assert parse_bool("") is False

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


class TestParseDerailmentScore:
    """Tests for parse_derailment_score covering int, float, string, clamping."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, 0),
            (50, 50),
            (100, 100),
            (42, 42),
        ],
    )
    def test_int_passthrough(self, value: int, expected: int):
        assert parse_derailment_score(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (-10, 0),
            (150, 100),
            (-1, 0),
            (101, 100),
        ],
    )
    def test_int_clamping(self, value: int, expected: int):
        assert parse_derailment_score(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (49.5, 50),
            (0.0, 0),
            (100.0, 100),
            (99.9, 100),
            (0.4, 0),
        ],
    )
    def test_float_rounding(self, value: float, expected: int):
        assert parse_derailment_score(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("0", 0),
            ("50", 50),
            ("100", 100),
            ("42", 42),
            (" 75 ", 75),
            ("33.7", 33),
        ],
    )
    def test_string_parsing(self, value: str, expected: int):
        assert parse_derailment_score(value) == expected

    def test_string_clamping(self):
        assert parse_derailment_score("-5") == 0
        assert parse_derailment_score("200") == 100

    def test_unrecognized_string_returns_zero(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.bulk_content_scan.flashpoint_utils"):
            result = parse_derailment_score("high risk")
        assert result == 0
        assert "unrecognized string" in caplog.text

    def test_none_returns_zero(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.bulk_content_scan.flashpoint_utils"):
            result = parse_derailment_score(None)
        assert result == 0
