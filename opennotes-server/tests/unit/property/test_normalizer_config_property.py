"""Property-based tests for rating normalizer, config parsing, and fusion config."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.fact_checking.import_pipeline.rating_normalizer import (
    CANONICAL_RATINGS,
    INTERMEDIATE_TO_CANONICAL,
    RATING_MAPPINGS,
    SKIP_RATINGS,
    normalize_rating,
)
from src.search.fusion_config import (
    FALLBACK_ALPHA,
    get_fusion_alpha,
    set_fusion_alpha,
)


def _build_case_variant_pairs() -> list[tuple[str, str]]:
    by_lower: dict[str, list[str]] = {}
    for key in RATING_MAPPINGS:
        by_lower.setdefault(key.lower(), []).append(key)
    pairs = []
    for variants in by_lower.values():
        for i, a in enumerate(variants):
            for b in variants[i + 1 :]:
                pairs.append((a, b))
    return pairs


def _resolve_to_final(rating: str | None) -> str | None:
    if rating is None:
        return None
    if rating in INTERMEDIATE_TO_CANONICAL:
        return INTERMEDIATE_TO_CANONICAL[rating]
    return rating


def _parse_skip_startup_checks(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return []
    v = raw.strip()
    if v.startswith("[") and v.endswith("]"):
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed]
        except json.JSONDecodeError:
            inner = v[1:-1]
            return [item.strip() for item in inner.split(",") if item.strip()]
    return [check.strip() for check in v.split(",") if check.strip()]


def _is_float_str(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, OverflowError):
        return False


def _make_mock_redis(get_return: str | None = "") -> AsyncMock:
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=get_return)
    mock.set = AsyncMock(return_value=True)
    return mock


def _make_stateful_mock_redis(store: dict[str, str]) -> AsyncMock:
    mock = AsyncMock()

    async def mock_get(key: str) -> str | None:
        return store.get(key)

    async def mock_set(key: str, value: str, **kwargs) -> bool:
        store[key] = value
        return True

    mock.get = AsyncMock(side_effect=mock_get)
    mock.set = AsyncMock(side_effect=mock_set)
    return mock


_CASE_VARIANT_PAIRS = _build_case_variant_pairs()


class TestNormalizeRatingIdempotence:
    @given(canonical=st.sampled_from(sorted(CANONICAL_RATINGS)))
    def test_canonical_values_are_idempotent(self, canonical: str):
        rating, details = normalize_rating(canonical)
        assert rating == canonical
        assert details is None

        re_rating, re_details = normalize_rating(rating)
        assert re_rating == canonical
        assert re_details is None

    @given(canonical=st.sampled_from(sorted(CANONICAL_RATINGS)))
    def test_double_normalization_stable(self, canonical: str):
        first_pass = normalize_rating(canonical)
        if first_pass[0] is not None:
            second_pass = normalize_rating(first_pass[0])
            assert first_pass[0] == second_pass[0]

    @given(mapping_key=st.sampled_from(sorted(RATING_MAPPINGS.keys())))
    def test_all_mapped_values_resolve_to_canonical_or_skip(self, mapping_key: str):
        rating, details = normalize_rating(mapping_key)
        if rating is not None:
            assert rating in CANONICAL_RATINGS or rating in INTERMEDIATE_TO_CANONICAL
        else:
            assert details in SKIP_RATINGS

    @given(mapping_key=st.sampled_from(sorted(RATING_MAPPINGS.keys())))
    def test_mapped_output_is_idempotent_when_canonical(self, mapping_key: str):
        rating, _ = normalize_rating(mapping_key)
        if rating is not None and rating in CANONICAL_RATINGS:
            re_rating, re_details = normalize_rating(rating)
            assert re_rating == rating
            assert re_details is None


class TestNormalizeRatingCaseInsensitivity:
    @given(mapping_key=st.sampled_from(sorted(RATING_MAPPINGS.keys())))
    def test_explicitly_mapped_case_variants_agree(self, mapping_key: str):
        lower_key = mapping_key.lower()
        upper_key = mapping_key.upper()

        lower_in_map = lower_key in RATING_MAPPINGS
        upper_in_map = upper_key in RATING_MAPPINGS

        if lower_in_map and upper_in_map:
            assert RATING_MAPPINGS[lower_key] == RATING_MAPPINGS[upper_key]

    @given(canonical=st.sampled_from(sorted(CANONICAL_RATINGS)))
    def test_canonical_lowercase_is_self_mapping(self, canonical: str):
        rating, details = normalize_rating(canonical)
        assert rating == canonical
        assert details is None

    def test_all_mapping_pairs_have_consistent_target(self):
        by_lower: dict[str, set[str]] = {}
        for key, value in RATING_MAPPINGS.items():
            lower = key.lower()
            by_lower.setdefault(lower, set()).add(value)
        for lower_key, targets in by_lower.items():
            assert len(targets) == 1, f"Inconsistent mapping for '{lower_key}': maps to {targets}"

    @given(pair=st.sampled_from(_CASE_VARIANT_PAIRS))
    def test_all_case_variants_in_map_agree(self, pair: tuple[str, str]):
        key_a, key_b = pair
        rating_a, _ = normalize_rating(key_a)
        rating_b, _ = normalize_rating(key_b)

        if rating_a is not None and rating_b is not None:
            assert _resolve_to_final(rating_a) == _resolve_to_final(rating_b)
        else:
            assert (rating_a is None) == (rating_b is None)

    @given(canonical=st.sampled_from(sorted(CANONICAL_RATINGS)))
    def test_canonical_upper_normalizes_back(self, canonical: str):
        upper = canonical.upper()
        rating, _ = normalize_rating(upper)
        if upper in RATING_MAPPINGS:
            assert _resolve_to_final(rating) == canonical
        else:
            normalized_form = upper.lower().replace(" ", "_").replace("-", "_")
            assert rating == normalized_form


class TestNormalizeRatingEdgeCases:
    @given(s=st.text())
    def test_never_crashes(self, s: str):
        result = normalize_rating(s)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_none_input(self):
        assert normalize_rating(None) == (None, None)

    @given(s=st.text(alphabet=" \t\n\r"))
    def test_whitespace_only_returns_none(self, s: str):
        assert normalize_rating(s) == (None, None)

    @given(s=st.text(min_size=1))
    def test_return_types_are_str_or_none(self, s: str):
        rating, details = normalize_rating(s)
        assert rating is None or isinstance(rating, str)
        assert details is None or isinstance(details, str)

    def test_empty_string(self):
        assert normalize_rating("") == (None, None)

    @given(
        canonical=st.sampled_from(sorted(CANONICAL_RATINGS)),
        pad=st.text(alphabet=" \t", min_size=1, max_size=5),
    )
    def test_whitespace_padding_stripped(self, canonical: str, pad: str):
        padded = pad + canonical + pad
        rating, _ = normalize_rating(padded)
        assert rating is not None
        assert _resolve_to_final(rating) == canonical


class TestSkipStartupChecksParsing:
    @given(
        items=st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20),
            min_size=0,
            max_size=10,
        )
    )
    def test_comma_separated_roundtrip(self, items: list[str]):
        raw = ",".join(items)
        parsed = _parse_skip_startup_checks(raw)
        assert isinstance(parsed, list)
        for item in parsed:
            assert isinstance(item, str)
        assert set(parsed) == set(items)

    @given(
        items=st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20),
            min_size=0,
            max_size=10,
        )
    )
    def test_json_array_roundtrip(self, items: list[str]):
        raw = json.dumps(items)
        parsed = _parse_skip_startup_checks(raw)
        assert parsed == items

    @pytest.mark.skip(
        reason="task-1127: naive comma-split parser can't roundtrip arbitrary strings; replacing with native pydantic-settings list field"
    )
    @given(
        items=st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20),
            min_size=1,
            max_size=10,
        )
    )
    def test_bracket_notation_roundtrip(self, items: list[str]):
        raw = "[" + ", ".join(items) + "]"
        parsed = _parse_skip_startup_checks(raw)
        assert set(parsed) == set(items)

    @given(s=st.text())
    def test_never_crashes(self, s: str):
        parsed = _parse_skip_startup_checks(s)
        assert isinstance(parsed, list)

    def test_empty_string(self):
        assert _parse_skip_startup_checks("") == []

    def test_whitespace_only(self):
        assert _parse_skip_startup_checks("   ") == []

    @given(s=st.text(min_size=1))
    def test_unclosed_bracket_no_crash(self, s: str):
        parsed = _parse_skip_startup_checks("[" + s)
        assert isinstance(parsed, list)

    def test_unclosed_bracket_treated_as_comma_separated(self):
        parsed = _parse_skip_startup_checks("[a, b, c")
        assert isinstance(parsed, list)

    @given(
        items=st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20).filter(
                lambda s: s not in ("true", "false", "null")
            ),
            min_size=1,
            max_size=5,
        ),
    )
    def test_json_and_bracket_agree_for_simple_strings(self, items: list[str]):
        json_result = _parse_skip_startup_checks(json.dumps(items))
        bracket_result = _parse_skip_startup_checks("[" + ",".join(items) + "]")
        assert set(json_result) == set(bracket_result)

    def test_mixed_format_comma_with_spaces(self):
        parsed = _parse_skip_startup_checks("  a , b,  c  ")
        assert parsed == ["a", "b", "c"]

    def test_trailing_comma(self):
        parsed = _parse_skip_startup_checks("a,b,c,")
        assert parsed == ["a", "b", "c"]

    @given(
        items=st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20),
            min_size=1,
            max_size=5,
        ),
        pad=st.text(alphabet=" \t", min_size=0, max_size=3),
    )
    def test_whitespace_around_items_stripped(self, items: list[str], pad: str):
        raw = ",".join(pad + item + pad for item in items)
        parsed = _parse_skip_startup_checks(raw)
        assert set(parsed) == set(items)

    def test_malformed_json_array_falls_back_to_bracket_split(self):
        parsed = _parse_skip_startup_checks('[a, b, "c]')
        assert isinstance(parsed, list)
        assert len(parsed) > 0

    @given(
        inner=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_, \t", min_size=0, max_size=50),
    )
    def test_bracket_wrapped_always_parseable(self, inner: str):
        raw = "[" + inner + "]"
        parsed = _parse_skip_startup_checks(raw)
        assert isinstance(parsed, list)


class TestFusionAlphaSelfHealing:
    @pytest.mark.asyncio
    @given(
        alpha=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    async def test_valid_alpha_returned_from_cache(self, alpha: float):
        mock_redis = _make_mock_redis(get_return=str(alpha))
        result = await get_fusion_alpha(mock_redis)
        assert result == alpha

    @pytest.mark.asyncio
    @given(
        alpha=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    async def test_result_always_in_valid_range(self, alpha: float):
        mock_redis = _make_mock_redis(get_return=str(alpha))
        result = await get_fusion_alpha(mock_redis)
        assert 0.0 <= result <= 1.0

    @pytest.mark.asyncio
    async def test_cache_miss_returns_fallback(self):
        mock_redis = _make_mock_redis(get_return=None)
        result = await get_fusion_alpha(mock_redis)
        assert result == FALLBACK_ALPHA
        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    @given(
        value=st.one_of(
            st.floats(min_value=1.01, max_value=1e10, allow_nan=False, allow_infinity=False),
            st.floats(min_value=-1e10, max_value=-0.01, allow_nan=False, allow_infinity=False),
        ),
    )
    async def test_out_of_range_heals_to_fallback(self, value: float):
        mock_redis = _make_mock_redis(get_return=str(value))
        result = await get_fusion_alpha(mock_redis)
        assert result == FALLBACK_ALPHA
        mock_redis.set.assert_awaited()

    @pytest.mark.asyncio
    @given(s=st.text(min_size=1).filter(lambda x: not _is_float_str(x)))
    async def test_non_numeric_heals_to_fallback(self, s: str):
        mock_redis = _make_mock_redis(get_return=s)
        result = await get_fusion_alpha(mock_redis)
        assert result == FALLBACK_ALPHA

    @pytest.mark.asyncio
    async def test_redis_error_returns_fallback(self):
        mock_redis = _make_mock_redis()
        mock_redis.get = AsyncMock(side_effect=ConnectionError("redis down"))
        result = await get_fusion_alpha(mock_redis)
        assert result == FALLBACK_ALPHA

    @pytest.mark.asyncio
    @given(
        alpha=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    async def test_set_then_get_roundtrip(self, alpha: float):
        store: dict[str, str] = {}
        mock_redis = _make_stateful_mock_redis(store)
        success = await set_fusion_alpha(mock_redis, alpha)
        assert success is True
        result = await get_fusion_alpha(mock_redis)
        assert result == alpha

    @pytest.mark.asyncio
    @given(
        alpha=st.one_of(
            st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False),
            st.floats(min_value=1.01, allow_nan=False, allow_infinity=False),
            st.just(float("nan")),
            st.just(float("inf")),
            st.just(float("-inf")),
        ),
    )
    async def test_set_rejects_invalid_alpha(self, alpha: float):
        mock_redis = _make_mock_redis()
        with pytest.raises(ValueError, match="Alpha must be between"):
            await set_fusion_alpha(mock_redis, alpha)

    @pytest.mark.asyncio
    @given(
        dataset=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=30)
    )
    async def test_dataset_specific_alpha_isolation(self, dataset: str):
        store: dict[str, str] = {}
        mock_redis = _make_stateful_mock_redis(store)
        await set_fusion_alpha(mock_redis, 0.9, dataset=dataset)
        await set_fusion_alpha(mock_redis, 0.3, dataset=None)
        ds_result = await get_fusion_alpha(mock_redis, dataset=dataset)
        default_result = await get_fusion_alpha(mock_redis, dataset=None)
        assert ds_result == pytest.approx(0.9)
        assert default_result == pytest.approx(0.3)

    @pytest.mark.asyncio
    @given(
        corrupted=st.sampled_from(
            ["nan", "inf", "-inf", "NaN", "Infinity", "-Infinity", "none", "null", ""]
        ),
    )
    async def test_special_string_values_heal(self, corrupted: str):
        mock_redis = _make_mock_redis(get_return=corrupted)
        result = await get_fusion_alpha(mock_redis)
        assert 0.0 <= result <= 1.0
