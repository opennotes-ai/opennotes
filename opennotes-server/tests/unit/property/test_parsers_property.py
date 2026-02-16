"""Property-based tests for LLM output parsers in flashpoint_utils."""

from __future__ import annotations

from typing import ClassVar

from hypothesis import given
from hypothesis import strategies as st

from src.bulk_content_scan.flashpoint_utils import (
    DERAILMENT_SCORE_MAX,
    DERAILMENT_SCORE_MIN,
    RISK_LEVEL_MAPPING,
    parse_bool,
    parse_derailment_score,
    parse_risk_level,
)
from src.bulk_content_scan.schemas import RiskLevel

int_strategy = st.integers(min_value=-(10**18), max_value=10**18)
float_strategy = st.floats(allow_nan=True, allow_infinity=True)
text_strategy = st.text()
bool_strategy = st.booleans()

any_primitive = st.one_of(int_strategy, float_strategy, text_strategy, bool_strategy, st.none())


class TestParseDerailmentScoreProperty:
    @given(value=any_primitive)
    def test_always_returns_int_in_range(self, value):
        result = parse_derailment_score(value)
        assert isinstance(result, int)
        assert DERAILMENT_SCORE_MIN <= result <= DERAILMENT_SCORE_MAX

    @given(value=any_primitive)
    def test_clamping_is_idempotent(self, value):
        first = parse_derailment_score(value)
        second = parse_derailment_score(first)
        assert first == second

    @given(n=st.integers(min_value=DERAILMENT_SCORE_MIN, max_value=DERAILMENT_SCORE_MAX))
    def test_in_range_ints_preserved(self, n):
        assert parse_derailment_score(n) == n

    @given(n=st.integers(min_value=DERAILMENT_SCORE_MAX + 1, max_value=10**18))
    def test_overflow_ints_clamped_to_max(self, n):
        assert parse_derailment_score(n) == DERAILMENT_SCORE_MAX

    @given(n=st.integers(min_value=-(10**18), max_value=DERAILMENT_SCORE_MIN - 1))
    def test_underflow_ints_clamped_to_min(self, n):
        assert parse_derailment_score(n) == DERAILMENT_SCORE_MIN

    @given(f=st.floats(allow_nan=True, allow_infinity=True))
    def test_adversarial_floats(self, f):
        result = parse_derailment_score(f)
        assert isinstance(result, int)
        assert DERAILMENT_SCORE_MIN <= result <= DERAILMENT_SCORE_MAX

    @given(s=st.text())
    def test_arbitrary_strings_never_crash(self, s):
        result = parse_derailment_score(s)
        assert isinstance(result, int)
        assert DERAILMENT_SCORE_MIN <= result <= DERAILMENT_SCORE_MAX

    @given(n=st.integers(min_value=DERAILMENT_SCORE_MIN, max_value=DERAILMENT_SCORE_MAX))
    def test_string_roundtrip_for_valid_ints(self, n):
        assert parse_derailment_score(str(n)) == n

    @given(f=st.floats(min_value=-1e15, max_value=1e15, allow_nan=False, allow_infinity=False))
    def test_string_float_produces_valid_result(self, f):
        result = parse_derailment_score(str(f))
        assert isinstance(result, int)
        assert DERAILMENT_SCORE_MIN <= result <= DERAILMENT_SCORE_MAX

    def test_nan_string(self):
        assert parse_derailment_score("NaN") == 0

    def test_inf_string(self):
        result = parse_derailment_score("Infinity")
        assert DERAILMENT_SCORE_MIN <= result <= DERAILMENT_SCORE_MAX

    def test_negative_inf_string(self):
        result = parse_derailment_score("-Infinity")
        assert DERAILMENT_SCORE_MIN <= result <= DERAILMENT_SCORE_MAX

    def test_nan_float(self):
        result = parse_derailment_score(float("nan"))
        assert isinstance(result, int)
        assert DERAILMENT_SCORE_MIN <= result <= DERAILMENT_SCORE_MAX

    def test_inf_float(self):
        result = parse_derailment_score(float("inf"))
        assert isinstance(result, int)
        assert DERAILMENT_SCORE_MIN <= result <= DERAILMENT_SCORE_MAX

    def test_none_returns_valid(self):
        result = parse_derailment_score(None)
        assert isinstance(result, int)
        assert DERAILMENT_SCORE_MIN <= result <= DERAILMENT_SCORE_MAX

    @given(s=st.text(alphabet=st.characters(categories=("L", "M", "N", "P", "S", "Z"))))
    def test_unicode_strings_never_crash(self, s):
        result = parse_derailment_score(s)
        assert isinstance(result, int)
        assert DERAILMENT_SCORE_MIN <= result <= DERAILMENT_SCORE_MAX


class TestParseBoolProperty:
    KNOWN_TRUE: ClassVar[list[str]] = ["true", "yes", "1", "y"]
    KNOWN_FALSE: ClassVar[list[str]] = ["false", "no", "0", "n", ""]

    @given(data=st.data())
    def test_deterministic(self, data):
        value = data.draw(any_primitive)
        a = parse_bool(value)
        b = parse_bool(value)
        assert a == b

    @given(s=st.sampled_from(KNOWN_TRUE))
    def test_known_true_case_insensitive(self, s):
        assert parse_bool(s) is True
        assert parse_bool(s.upper()) is True
        assert parse_bool(s.capitalize()) is True

    @given(s=st.sampled_from(KNOWN_FALSE))
    def test_known_false_case_insensitive(self, s):
        assert parse_bool(s) is False
        assert parse_bool(s.upper()) is False
        assert parse_bool(s.capitalize()) is False

    def test_bool_passthrough(self):
        assert parse_bool(True) is True
        assert parse_bool(False) is False

    @given(value=any_primitive)
    def test_always_returns_bool(self, value):
        result = parse_bool(value)
        assert isinstance(result, bool)

    @given(s=st.text())
    def test_arbitrary_string_returns_bool(self, s):
        result = parse_bool(s)
        assert isinstance(result, bool)

    @given(s=st.text(alphabet=st.characters(categories=("L", "M", "N", "P", "S", "Z"))))
    def test_unicode_returns_bool(self, s):
        result = parse_bool(s)
        assert isinstance(result, bool)

    @given(f=st.floats(allow_nan=True, allow_infinity=True))
    def test_float_inputs(self, f):
        result = parse_bool(f)
        assert isinstance(result, bool)

    @given(n=st.integers())
    def test_integer_inputs(self, n):
        result = parse_bool(n)
        assert isinstance(result, bool)
        if n == 0:
            assert result is False
        else:
            assert result is True


class TestParseRiskLevelProperty:
    def test_score_to_level_monotonically_non_decreasing(self):
        scores = list(range(DERAILMENT_SCORE_MIN, DERAILMENT_SCORE_MAX + 1))
        level_order = {
            RiskLevel.LOW_RISK: 0,
            RiskLevel.GUARDED: 1,
            RiskLevel.HEATED: 2,
            RiskLevel.HOSTILE: 3,
            RiskLevel.DANGEROUS: 4,
        }
        prev_rank = -1
        for score in scores:
            level = parse_risk_level("unknown_garbage", derailment_score=score)
            rank = level_order[level]
            assert rank >= prev_rank, (
                f"Monotonicity violated: score {score} mapped to {level} (rank {rank}), "
                f"but previous rank was {prev_rank}"
            )
            prev_rank = rank

    @given(score=st.integers(min_value=0, max_value=100))
    def test_score_fallback_returns_valid_risk_level(self, score):
        result = parse_risk_level("gibberish_not_a_level", derailment_score=score)
        assert isinstance(result, RiskLevel)

    @given(s=st.sampled_from(list(RISK_LEVEL_MAPPING.keys())))
    def test_known_levels_case_insensitive(self, s):
        result_lower = parse_risk_level(s.lower())
        result_upper = parse_risk_level(s.upper())
        result_exact = parse_risk_level(s)
        assert result_exact == result_lower
        assert result_exact == result_upper
        assert isinstance(result_exact, RiskLevel)

    @given(s=st.sampled_from(list(RISK_LEVEL_MAPPING.keys())))
    def test_known_levels_with_whitespace(self, s):
        result = parse_risk_level(f"  {s}  ")
        assert isinstance(result, RiskLevel)
        assert result == parse_risk_level(s)

    @given(s=st.text())
    def test_arbitrary_string_returns_valid_risk_level(self, s):
        result = parse_risk_level(s)
        assert isinstance(result, RiskLevel)

    @given(s=st.text(), score=st.integers(min_value=0, max_value=100))
    def test_always_returns_risk_level_with_score_fallback(self, s, score):
        result = parse_risk_level(s, derailment_score=score)
        assert isinstance(result, RiskLevel)

    def test_mapping_values_match_risk_level_enum(self):
        for level_name in RISK_LEVEL_MAPPING:
            assert RiskLevel(level_name) in RiskLevel

    def test_boundary_scores(self):
        assert parse_risk_level("x", derailment_score=0) == RiskLevel.LOW_RISK
        assert parse_risk_level("x", derailment_score=29) == RiskLevel.LOW_RISK
        assert parse_risk_level("x", derailment_score=30) == RiskLevel.GUARDED
        assert parse_risk_level("x", derailment_score=59) == RiskLevel.GUARDED
        assert parse_risk_level("x", derailment_score=60) == RiskLevel.HEATED
        assert parse_risk_level("x", derailment_score=84) == RiskLevel.HEATED
        assert parse_risk_level("x", derailment_score=85) == RiskLevel.HOSTILE
        assert parse_risk_level("x", derailment_score=99) == RiskLevel.HOSTILE
        assert parse_risk_level("x", derailment_score=100) == RiskLevel.DANGEROUS

    def test_no_score_unknown_string_defaults_to_heated(self):
        result = parse_risk_level("totally_unknown")
        assert result == RiskLevel.HEATED

    @given(s=st.text(alphabet=st.characters(categories=("L", "M", "N", "P", "S", "Z"))))
    def test_unicode_strings_never_crash(self, s):
        result = parse_risk_level(s)
        assert isinstance(result, RiskLevel)
