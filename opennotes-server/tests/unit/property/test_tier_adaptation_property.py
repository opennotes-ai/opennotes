"""
Property-based tests for tier adaptation, clamping idempotency,
and scoring-tier integration invariants.

Covers:
- Tier boundary consistency (N triggers tier T implies N-1 does not)
- Fallback chain always terminates at MINIMAL
- Confidence monotonicity (higher tiers yield higher confidence)
- Clamping idempotency (clamp(clamp(x)) == clamp(x))
- Bayesian score envelope (score stays within [prior_mean - envelope, prior_mean + envelope])
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
from src.notes.scoring.tier_config import (
    ScoringTier,
    get_tier_config,
    get_tier_for_note_count,
)
from src.notes.scoring_schemas import DataConfidence
from src.notes.scoring_utils import (
    TIER_ORDER,
    get_tier_data_confidence,
    get_tier_level,
)

TIER_BOUNDARIES = [200, 1000, 5000, 10000, 50000]

EXPECTED_TIER_AT_BOUNDARY = [
    ScoringTier.LIMITED,
    ScoringTier.BASIC,
    ScoringTier.INTERMEDIATE,
    ScoringTier.ADVANCED,
    ScoringTier.FULL,
]

CONFIDENCE_ORDER = [
    DataConfidence.NONE,
    DataConfidence.LOW,
    DataConfidence.MEDIUM,
    DataConfidence.HIGH,
    DataConfidence.VERY_HIGH,
]


def confidence_rank(dc: DataConfidence) -> int:
    return CONFIDENCE_ORDER.index(dc)


def _get_fallback_tier(current_tier: ScoringTier) -> ScoringTier | None:
    tier_hierarchy = [
        ScoringTier.MINIMAL,
        ScoringTier.LIMITED,
        ScoringTier.BASIC,
        ScoringTier.INTERMEDIATE,
        ScoringTier.ADVANCED,
        ScoringTier.FULL,
    ]
    try:
        idx = tier_hierarchy.index(current_tier)
        if idx > 0:
            return tier_hierarchy[idx - 1]
    except ValueError:
        pass
    return None


class TestTierBoundaryConsistency:
    """Tier boundaries must be strict: crossing a boundary changes the tier."""

    @given(boundary_idx=st.integers(min_value=0, max_value=len(TIER_BOUNDARIES) - 1))
    def test_boundary_crossing_changes_tier(self, boundary_idx: int):
        """N at a boundary triggers the next tier; N-1 stays in the previous tier."""
        boundary = TIER_BOUNDARIES[boundary_idx]
        tier_at = get_tier_for_note_count(boundary)
        tier_below = get_tier_for_note_count(boundary - 1)

        assert tier_at == EXPECTED_TIER_AT_BOUNDARY[boundary_idx], (
            f"At boundary {boundary}, expected {EXPECTED_TIER_AT_BOUNDARY[boundary_idx]}, "
            f"got {tier_at}"
        )
        assert tier_at != tier_below, (
            f"Boundary {boundary}: tier should change but "
            f"tier_at={tier_at} == tier_below={tier_below}"
        )

    @given(
        note_count=st.integers(min_value=0, max_value=200_000),
    )
    def test_tier_is_always_valid_enum(self, note_count: int):
        """get_tier_for_note_count always returns a valid ScoringTier."""
        tier = get_tier_for_note_count(note_count)
        assert tier in ScoringTier, f"Invalid tier {tier} for note_count={note_count}"

    @given(
        note_count=st.integers(min_value=0, max_value=200_000),
    )
    def test_tier_config_matches_note_count(self, note_count: int):
        """The detected tier's config range must contain the note_count."""
        tier = get_tier_for_note_count(note_count)
        config = get_tier_config(tier)
        assert note_count >= config.min_notes, (
            f"note_count {note_count} below tier {tier} min_notes {config.min_notes}"
        )
        if config.max_notes is not None:
            assert note_count < config.max_notes, (
                f"note_count {note_count} >= tier {tier} max_notes {config.max_notes}"
            )

    @given(
        note_count=st.integers(min_value=0, max_value=200_000),
    )
    def test_tier_level_is_monotonic_with_note_count(self, note_count: int):
        """Adding one note should never decrease the tier level."""
        tier = get_tier_for_note_count(note_count)
        tier_plus = get_tier_for_note_count(note_count + 1)
        assert get_tier_level(tier_plus) >= get_tier_level(tier), (
            f"Tier decreased from {tier} to {tier_plus} when adding one note "
            f"(count {note_count} -> {note_count + 1})"
        )


class TestFallbackChain:
    """Fallback chain must always terminate at MINIMAL."""

    @given(
        tier=st.sampled_from(list(ScoringTier)),
    )
    def test_fallback_terminates_at_minimal(self, tier: ScoringTier):
        """Repeatedly falling back from any tier must reach MINIMAL then return None."""
        current = tier
        visited: set[ScoringTier] = set()

        while current is not None:
            assert current not in visited, f"Cycle detected in fallback chain at tier {current}"
            visited.add(current)
            current = _get_fallback_tier(current)

        assert ScoringTier.MINIMAL in visited, (
            f"Fallback chain from {tier} never reached MINIMAL. Visited: {visited}"
        )

    @given(
        tier=st.sampled_from(list(ScoringTier)),
    )
    def test_fallback_chain_length_bounded(self, tier: ScoringTier):
        """Fallback chain length must equal the tier's index in the hierarchy."""
        steps = 0
        current: ScoringTier | None = tier
        while _get_fallback_tier(current) is not None:
            current = _get_fallback_tier(current)
            steps += 1

        expected_steps = get_tier_level(tier)
        assert steps == expected_steps, (
            f"From {tier} expected {expected_steps} fallback steps, got {steps}"
        )

    def test_minimal_has_no_fallback(self):
        """MINIMAL tier must have no fallback (it is the last resort)."""
        assert _get_fallback_tier(ScoringTier.MINIMAL) is None

    @given(
        tier=st.sampled_from([t for t in ScoringTier if t != ScoringTier.MINIMAL]),
    )
    def test_non_minimal_tiers_have_fallback(self, tier: ScoringTier):
        """Every tier except MINIMAL must have a fallback."""
        fallback = _get_fallback_tier(tier)
        assert fallback is not None, f"Tier {tier} has no fallback but is not MINIMAL"

    @given(
        tier=st.sampled_from([t for t in ScoringTier if t != ScoringTier.MINIMAL]),
    )
    def test_fallback_is_strictly_lower(self, tier: ScoringTier):
        """Fallback tier must be strictly one level lower."""
        fallback = _get_fallback_tier(tier)
        assert fallback is not None
        assert get_tier_level(fallback) == get_tier_level(tier) - 1, (
            f"Fallback from {tier} (level {get_tier_level(tier)}) "
            f"is {fallback} (level {get_tier_level(fallback)}), expected level {get_tier_level(tier) - 1}"
        )


class TestConfidenceMonotonicity:
    """Higher tiers must yield equal or higher data confidence."""

    def test_confidence_non_decreasing_across_all_tiers(self):
        """Walking TIER_ORDER from MINIMAL to FULL, confidence must never decrease."""
        prev_rank = -1
        for tier in TIER_ORDER:
            conf = get_tier_data_confidence(tier)
            rank = confidence_rank(conf)
            assert rank >= prev_rank, (
                f"Confidence decreased at tier {tier}: "
                f"{CONFIDENCE_ORDER[prev_rank] if prev_rank >= 0 else 'N/A'} -> {conf}"
            )
            prev_rank = rank

    @given(
        i=st.integers(min_value=0, max_value=len(TIER_ORDER) - 2),
    )
    def test_adjacent_tier_confidence_non_decreasing(self, i: int):
        """For any adjacent tier pair, the higher tier's confidence >= the lower's."""
        lower_tier = TIER_ORDER[i]
        upper_tier = TIER_ORDER[i + 1]
        lower_conf = confidence_rank(get_tier_data_confidence(lower_tier))
        upper_conf = confidence_rank(get_tier_data_confidence(upper_tier))
        assert upper_conf >= lower_conf, (
            f"Confidence for {upper_tier} ({get_tier_data_confidence(upper_tier)}) "
            f"< {lower_tier} ({get_tier_data_confidence(lower_tier)})"
        )

    def test_minimal_has_lowest_confidence(self):
        """MINIMAL tier must have NONE confidence."""
        assert get_tier_data_confidence(ScoringTier.MINIMAL) == DataConfidence.NONE

    def test_full_has_highest_confidence(self):
        """FULL tier must have VERY_HIGH confidence."""
        assert get_tier_data_confidence(ScoringTier.FULL) == DataConfidence.VERY_HIGH


class TestClampingIdempotency:
    """clamp(clamp(x)) == clamp(x) for all inputs."""

    @given(
        ratings=st.lists(
            st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=50,
        ),
    )
    def test_clamping_is_idempotent(self, ratings: list[float]):
        """Applying _clamp_ratings twice yields the same result as once."""
        scorer = BayesianAverageScorer()
        once = scorer._clamp_ratings(ratings)
        twice = scorer._clamp_ratings(once)
        assert once == twice, f"Clamping not idempotent: once={once}, twice={twice}"

    @given(
        rating=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    def test_single_value_clamping_idempotent(self, rating: float):
        """Single-value clamping must be idempotent."""
        scorer = BayesianAverageScorer()
        once = scorer._clamp_ratings([rating])
        twice = scorer._clamp_ratings(once)
        assert once == twice

    @given(
        rating=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_in_range_values_unchanged_by_clamping(self, rating: float):
        """Values already in [0.0, 1.0] must not be changed by clamping."""
        scorer = BayesianAverageScorer()
        result = scorer._clamp_ratings([rating])
        assert result == [rating], f"In-range value {rating} changed to {result[0]} by clamping"

    @given(
        rating=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    def test_clamped_value_always_in_range(self, rating: float):
        """After clamping, value must be in [0.0, 1.0]."""
        scorer = BayesianAverageScorer()
        result = scorer._clamp_ratings([rating])
        assert 0.0 <= result[0] <= 1.0, (
            f"Clamped value {result[0]} outside [0.0, 1.0] for input {rating}"
        )


class TestBayesianScoreEnvelope:
    """Bayesian score must stay within a provable envelope around the prior mean."""

    @given(
        ratings=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=100,
        ),
        confidence_param=st.floats(
            min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_score_within_prior_mean_envelope(
        self, ratings: list[float], confidence_param: float, prior_mean: float
    ):
        """Score must stay within [prior_mean - envelope, prior_mean + envelope].

        The Bayesian average formula is: score = (C*m + sum(r))/(C + n)
        where C=confidence_param, m=prior_mean, n=len(ratings), r in [0,1].

        The maximum deviation from prior_mean occurs when all ratings are 0 or 1:
          score_max = (C*m + n)/(C + n)  -> deviation = n*(1-m)/(C+n)
          score_min = (C*m)/(C + n)      -> deviation = n*m/(C+n)

        So envelope = n / (C + n) which is strictly < 1.
        """
        scorer = BayesianAverageScorer(
            confidence_param=confidence_param,
            prior_mean=prior_mean,
        )
        score = scorer.calculate_score(ratings)

        n = len(ratings)
        if n == 0:
            assert score == prior_mean
            return

        envelope = n / (confidence_param + n)
        assert prior_mean - envelope <= score + 1e-10, (
            f"Score {score} below envelope lower bound "
            f"{prior_mean - envelope} (prior={prior_mean}, C={confidence_param}, n={n})"
        )
        assert score - 1e-10 <= prior_mean + envelope, (
            f"Score {score} above envelope upper bound "
            f"{prior_mean + envelope} (prior={prior_mean}, C={confidence_param}, n={n})"
        )

    @given(
        n=st.integers(min_value=1, max_value=1000),
        confidence_param=st.floats(
            min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False),
    )
    def test_all_ones_maximizes_score(self, n: int, confidence_param: float, prior_mean: float):
        """All-1.0 ratings must produce the maximum possible score for given n and C."""
        scorer = BayesianAverageScorer(
            confidence_param=confidence_param,
            prior_mean=prior_mean,
        )
        score = scorer.calculate_score([1.0] * n)
        expected = (confidence_param * prior_mean + n) / (confidence_param + n)
        assert abs(score - expected) < 1e-9, f"All-ones score {score} != expected {expected}"

    @given(
        n=st.integers(min_value=1, max_value=1000),
        confidence_param=st.floats(
            min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False),
    )
    def test_all_zeros_minimizes_score(self, n: int, confidence_param: float, prior_mean: float):
        """All-0.0 ratings must produce the minimum possible score for given n and C."""
        scorer = BayesianAverageScorer(
            confidence_param=confidence_param,
            prior_mean=prior_mean,
        )
        score = scorer.calculate_score([0.0] * n)
        expected = (confidence_param * prior_mean) / (confidence_param + n)
        assert abs(score - expected) < 1e-9, f"All-zeros score {score} != expected {expected}"

    @given(
        n=st.integers(min_value=1, max_value=200),
        confidence_param=st.floats(
            min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False
        ),
        prior_mean=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50)
    def test_envelope_shrinks_with_higher_confidence_param(
        self, n: int, confidence_param: float, prior_mean: float
    ):
        """Doubling the confidence param must shrink the envelope.

        envelope = n / (C + n). Doubling C gives n / (2C + n) < n / (C + n).
        """
        envelope_low_c = n / (confidence_param + n)
        envelope_high_c = n / (2.0 * confidence_param + n)
        assert envelope_high_c < envelope_low_c, (
            f"Doubling C from {confidence_param} did not shrink envelope: "
            f"{envelope_high_c} >= {envelope_low_c}"
        )


class TestTierConfigIntegrity:
    """Tier configurations must be internally consistent."""

    def test_tiers_cover_all_note_counts(self):
        """The tier boundaries must form a contiguous, non-overlapping partition of [0, inf)."""
        prev_max = 0
        for tier in TIER_ORDER:
            config = get_tier_config(tier)
            assert config.min_notes == prev_max, (
                f"Gap or overlap at tier {tier}: "
                f"min_notes={config.min_notes} but previous max_notes={prev_max}"
            )
            if config.max_notes is not None:
                prev_max = config.max_notes
            else:
                prev_max = None
                break

        assert prev_max is None, "Last tier (FULL) must have max_notes=None"

    def test_tier_scorers_expand_monotonically(self):
        """Higher tiers must have at least as many scorer components as lower tiers."""
        prev_count = 0
        for tier in TIER_ORDER:
            config = get_tier_config(tier)
            assert len(config.scorers) >= prev_count, (
                f"Tier {tier} has fewer scorers ({len(config.scorers)}) "
                f"than a lower tier ({prev_count})"
            )
            prev_count = len(config.scorers)

    def test_requires_full_pipeline_monotonic(self):
        """Once requires_full_pipeline is True, all higher tiers must also be True."""
        seen_full = False
        for tier in TIER_ORDER:
            config = get_tier_config(tier)
            if seen_full:
                assert config.requires_full_pipeline, (
                    f"Tier {tier} has requires_full_pipeline=False but a lower tier was True"
                )
            if config.requires_full_pipeline:
                seen_full = True

    def test_confidence_warnings_only_on_low_tiers(self):
        """confidence_warnings should only be True on MINIMAL and LIMITED."""
        for tier in TIER_ORDER:
            config = get_tier_config(tier)
            if config.confidence_warnings:
                assert tier in (ScoringTier.MINIMAL, ScoringTier.LIMITED), (
                    f"Tier {tier} has confidence_warnings=True but is above LIMITED"
                )
