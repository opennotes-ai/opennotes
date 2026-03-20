import math

import numpy as np
import pyarrow as pa

from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
from src.notes.scoring.bayesian_scorer_adapter import BayesianAverageScorerAdapter
from src.notes.scoring.rater_diversity_scorer import (
    RaterDiversityScorer,
    RaterDiversityScorerAdapter,
)
from src.notes.scoring.scorer_protocol import ScorerProtocol, ScoringResult


class TestBuildRaterProfiles:
    def test_builds_profiles_from_rating_triples(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_a", "note_2", 0.0),
            ("rater_b", "note_1", 0.5),
            ("rater_b", "note_2", 1.0),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)

        assert "rater_a" in profiles
        assert "rater_b" in profiles
        assert set(note_ids) == {"note_1", "note_2"}
        assert len(profiles["rater_a"]) == 2
        assert len(profiles["rater_b"]) == 2

    def test_mean_centers_vectors(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_a", "note_2", 0.0),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)

        rater_mean = (1.0 + 0.0) / 2.0
        idx1 = note_ids.index("note_1")
        idx2 = note_ids.index("note_2")
        assert math.isclose(profiles["rater_a"][idx1], 1.0 - rater_mean, rel_tol=1e-9)
        assert math.isclose(profiles["rater_a"][idx2], 0.0 - rater_mean, rel_tol=1e-9)

    def test_unrated_positions_are_zero_after_centering(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_b", "note_1", 0.5),
            ("rater_b", "note_2", 0.5),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)

        idx2 = note_ids.index("note_2")
        assert profiles["rater_a"][idx2] == 0.0


class TestComputeDiversity:
    def test_identical_profiles_diversity_near_zero(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_a", "note_2", 0.0),
            ("rater_b", "note_1", 1.0),
            ("rater_b", "note_2", 0.0),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)
        diversity, metadata = scorer.compute_diversity(["rater_a", "rater_b"], profiles, note_ids)

        assert math.isclose(diversity, 0.0, abs_tol=1e-9)
        assert metadata["valid_pair_count"] == 1
        assert metadata["supporter_count"] == 2

    def test_orthogonal_profiles_diversity_near_one(self):
        scorer = RaterDiversityScorer()

        note_ids = [f"note_{i}" for i in range(4)]
        profiles = {
            "rater_a": np.array([1.0, 0.0, 0.0, 0.0]),
            "rater_b": np.array([0.0, 1.0, 0.0, 0.0]),
        }

        diversity, metadata = scorer.compute_diversity(["rater_a", "rater_b"], profiles, note_ids)

        assert math.isclose(diversity, 1.0, abs_tol=1e-9)
        assert metadata["diversity_signal"] == "strong"

    def test_fewer_than_two_supporters_returns_zero(self):
        scorer = RaterDiversityScorer()
        profiles = {"rater_a": np.array([1.0, 0.0])}
        note_ids = ["note_1", "note_2"]

        diversity, metadata = scorer.compute_diversity(["rater_a"], profiles, note_ids)

        assert diversity == 0.0
        assert metadata["diversity_signal"] == "insufficient"

    def test_zero_vector_raters_excluded(self):
        scorer = RaterDiversityScorer()
        note_ids = [f"note_{i}" for i in range(4)]
        profiles = {
            "rater_a": np.array([1.0, 0.0, 0.0, 0.0]),
            "rater_b": np.array([0.0, 0.0, 0.0, 0.0]),
            "rater_c": np.array([0.0, 1.0, 0.0, 0.0]),
        }

        diversity, metadata = scorer.compute_diversity(
            ["rater_a", "rater_b", "rater_c"], profiles, note_ids
        )

        assert metadata["supporter_count"] == 2
        assert metadata["valid_pair_count"] == 1
        assert math.isclose(diversity, 1.0, abs_tol=1e-9)

    def test_unknown_supporter_ids_ignored(self):
        scorer = RaterDiversityScorer()
        profiles = {"rater_a": np.array([1.0, 0.0])}
        note_ids = ["note_1", "note_2"]

        diversity, metadata = scorer.compute_diversity(
            ["rater_a", "rater_unknown"], profiles, note_ids
        )

        assert diversity == 0.0
        assert metadata["supporter_count"] == 1

    def test_metadata_keys_present(self):
        scorer = RaterDiversityScorer()
        note_ids = ["note_1", "note_2"]
        profiles = {
            "rater_a": np.array([1.0, -1.0]),
            "rater_b": np.array([-1.0, 1.0]),
        }

        _, metadata = scorer.compute_diversity(["rater_a", "rater_b"], profiles, note_ids)

        expected_keys = {
            "valid_pair_count",
            "total_pair_count",
            "pair_coverage_ratio",
            "supporter_count",
            "mean_pairwise_distance",
            "diversity_signal",
        }
        assert expected_keys == set(metadata.keys())


class TestScoreNoteDiversity:
    def test_score_note_diversity_filters_supporters(self):
        scorer = RaterDiversityScorer(supporter_threshold=0.6)
        note_ids = ["target_note", "note_2"]
        profiles = {
            "rater_a": np.array([0.5, -0.5]),
            "rater_b": np.array([-0.5, 0.5]),
            "rater_c": np.array([0.5, -0.5]),
        }

        note_rater_ratings = [
            ("rater_a", 1.0),
            ("rater_b", 0.0),
            ("rater_c", 0.8),
        ]

        diversity, metadata = scorer.score_note_diversity(
            "target_note", note_rater_ratings, profiles, note_ids
        )

        assert metadata["supporter_count"] == 2
        assert diversity >= 0.0

    def test_score_note_diversity_no_supporters(self):
        scorer = RaterDiversityScorer(supporter_threshold=0.6)
        note_ids = ["target_note"]
        profiles = {"rater_a": np.array([0.5])}

        note_rater_ratings = [("rater_a", 0.0)]

        diversity, metadata = scorer.score_note_diversity(
            "target_note", note_rater_ratings, profiles, note_ids
        )

        assert diversity == 0.0
        assert metadata["diversity_signal"] == "insufficient"


def _make_ratings_table(
    rater_ids: list[str],
    note_ids: list[str],
    helpfulness_levels: list[str],
) -> pa.Table:
    n = len(rater_ids)
    timestamps = pa.array([1735689600000000] * n, type=pa.int64()).cast(
        pa.timestamp("us", tz="UTC")
    )
    return pa.table(
        {
            "rater_id": pa.array(rater_ids, type=pa.string()),
            "note_id": pa.array(note_ids, type=pa.string()),
            "helpfulness_level": pa.array(helpfulness_levels, type=pa.string()),
            "created_at": timestamps,
        }
    )


class FakeDataProvider:
    def __init__(self, ratings_table: pa.Table) -> None:
        self._ratings = ratings_table

    def get_all_ratings(self, community_id: str) -> pa.Table:
        return self._ratings

    def get_all_notes(self, community_id: str) -> pa.Table:
        return pa.table({})

    def get_all_participants(self, community_id: str) -> pa.Array:
        return pa.array([])


class TestRaterDiversityScorerAdapterProtocol:
    def test_satisfies_scorer_protocol(self):
        table = _make_ratings_table(
            ["r1", "r2"],
            ["n1", "n1"],
            ["HELPFUL", "NOT_HELPFUL"],
        )
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "community_1")

        assert isinstance(adapter, ScorerProtocol)

    def test_score_note_returns_scoring_result(self):
        table = _make_ratings_table(
            ["r1", "r2"],
            ["n1", "n1"],
            ["HELPFUL", "NOT_HELPFUL"],
        )
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "community_1")

        result = adapter.score_note("n1", [1.0, 0.0])

        assert isinstance(result, ScoringResult)
        assert 0.0 <= result.score <= 1.0


class TestRaterDiversityScorerAdapterBlending:
    def test_blending_formula_applies_diversity_bonus(self):
        table = _make_ratings_table(
            ["r_a", "r_a", "r_b", "r_b", "r_c", "r_c", "r_d", "r_d"],
            ["n1", "n2", "n1", "n2", "n1", "n2", "n1", "n2"],
            [
                "HELPFUL",
                "NOT_HELPFUL",
                "HELPFUL",
                "HELPFUL",
                "HELPFUL",
                "NOT_HELPFUL",
                "HELPFUL",
                "HELPFUL",
            ],
        )
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "c1", diversity_bonus=0.3)

        result = adapter.score_note("n1", [1.0, 1.0, 1.0, 1.0])

        bayesian_adapter = BayesianAverageScorerAdapter(BayesianAverageScorer())
        bayesian_result = bayesian_adapter.score_note("n1", [1.0, 1.0, 1.0, 1.0])

        assert result.score >= bayesian_result.score
        assert "diversity_score" in result.metadata
        assert "bayesian_base_score" in result.metadata

    def test_zero_diversity_returns_bayesian_score(self):
        table = _make_ratings_table(
            ["r_a", "r_a", "r_b", "r_b"],
            ["n1", "n2", "n1", "n2"],
            ["HELPFUL", "NOT_HELPFUL", "HELPFUL", "NOT_HELPFUL"],
        )
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "c1", diversity_bonus=0.3)

        result = adapter.score_note("n1", [1.0, 1.0])

        bayesian_adapter = BayesianAverageScorerAdapter(BayesianAverageScorer())
        bayesian_result = bayesian_adapter.score_note("n1", [1.0, 1.0])

        assert math.isclose(result.score, bayesian_result.score, rel_tol=1e-6)

    def test_score_clamped_to_one(self):
        table = _make_ratings_table(
            ["r_a", "r_a", "r_b", "r_b"],
            ["n1", "n2", "n1", "n2"],
            ["HELPFUL", "NOT_HELPFUL", "NOT_HELPFUL", "HELPFUL"],
        )
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "c1", diversity_bonus=100.0)

        result = adapter.score_note("n1", [1.0, 1.0])

        assert result.score <= 1.0


class TestRaterDiversityScorerAdapterPyArrow:
    def test_converts_helpfulness_levels_to_numeric(self):
        table = _make_ratings_table(
            ["r1", "r2", "r3"],
            ["n1", "n1", "n1"],
            ["HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL"],
        )
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "c1")

        assert "n1" in adapter._note_ratings_index
        ratings_for_n1 = adapter._note_ratings_index["n1"]
        numeric_values = dict(ratings_for_n1)
        assert math.isclose(numeric_values["r1"], 1.0)
        assert math.isclose(numeric_values["r2"], 0.5)
        assert math.isclose(numeric_values["r3"], 0.0)

    def test_empty_table_produces_empty_index(self):
        table = _make_ratings_table([], [], [])
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "c1")

        assert adapter._note_ratings_index == {}


class TestRaterDiversityScorerAdapterFallback:
    def test_unknown_note_falls_back_to_bayesian_only(self):
        table = _make_ratings_table(
            ["r1", "r2"],
            ["n1", "n1"],
            ["HELPFUL", "NOT_HELPFUL"],
        )
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "c1")

        result = adapter.score_note("unknown_note", [0.8, 0.6])

        bayesian_adapter = BayesianAverageScorerAdapter(BayesianAverageScorer())
        bayesian_result = bayesian_adapter.score_note("unknown_note", [0.8, 0.6])

        assert math.isclose(result.score, bayesian_result.score, rel_tol=1e-6)
        assert result.metadata["diversity_score"] == 0.0

    def test_metadata_contains_all_required_keys(self):
        table = _make_ratings_table(
            ["r_a", "r_a", "r_b", "r_b"],
            ["n1", "n2", "n1", "n2"],
            ["HELPFUL", "NOT_HELPFUL", "NOT_HELPFUL", "HELPFUL"],
        )
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "c1")

        result = adapter.score_note("n1", [1.0, 0.0])

        required_keys = {
            "diversity_score",
            "supporter_count",
            "mean_pairwise_distance",
            "blend_weight",
            "diversity_signal",
            "valid_pair_count",
            "total_pair_count",
            "pair_coverage_ratio",
            "bayesian_base_score",
        }
        assert required_keys.issubset(set(result.metadata.keys()))


class TestThreeRaterDiversity:
    def test_three_identical_raters_diversity_near_zero(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_a", "note_2", 0.0),
            ("rater_b", "note_1", 1.0),
            ("rater_b", "note_2", 0.0),
            ("rater_c", "note_1", 1.0),
            ("rater_c", "note_2", 0.0),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)
        diversity, metadata = scorer.compute_diversity(
            ["rater_a", "rater_b", "rater_c"], profiles, note_ids
        )

        assert math.isclose(diversity, 0.0, abs_tol=1e-9)
        assert metadata["valid_pair_count"] == 3
        assert metadata["supporter_count"] == 3

    def test_three_orthogonal_raters_diversity_near_one(self):
        scorer = RaterDiversityScorer()
        note_ids = [f"note_{i}" for i in range(6)]
        profiles = {
            "rater_a": np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            "rater_b": np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0]),
            "rater_c": np.array([0.0, 0.0, 0.0, 0.0, 1.0, 0.0]),
        }

        diversity, metadata = scorer.compute_diversity(
            ["rater_a", "rater_b", "rater_c"], profiles, note_ids
        )

        assert math.isclose(diversity, 1.0, abs_tol=1e-9)
        assert metadata["diversity_signal"] == "strong"
        assert metadata["valid_pair_count"] == 3


class TestZeroSupporters:
    def test_empty_supporter_list_returns_zero(self):
        scorer = RaterDiversityScorer()
        profiles = {"rater_a": np.array([1.0, -1.0])}
        note_ids = ["note_1", "note_2"]

        diversity, metadata = scorer.compute_diversity([], profiles, note_ids)

        assert diversity == 0.0
        assert metadata["supporter_count"] == 0
        assert metadata["diversity_signal"] == "insufficient"


class TestNoSharedRatedNotes:
    def test_raters_rating_single_disjoint_notes_become_zero_vectors(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_b", "note_2", 0.5),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)

        assert np.linalg.norm(profiles["rater_a"]) < 1e-12
        assert np.linalg.norm(profiles["rater_b"]) < 1e-12

        diversity, metadata = scorer.compute_diversity(["rater_a", "rater_b"], profiles, note_ids)

        assert diversity == 0.0
        assert metadata["supporter_count"] == 0
        assert metadata["diversity_signal"] == "insufficient"

    def test_raters_with_no_overlap_but_multiple_ratings_each(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_a", "note_2", 0.0),
            ("rater_b", "note_3", 1.0),
            ("rater_b", "note_4", 0.0),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)

        assert np.linalg.norm(profiles["rater_a"]) > 1e-12
        assert np.linalg.norm(profiles["rater_b"]) > 1e-12

        diversity, metadata = scorer.compute_diversity(["rater_a", "rater_b"], profiles, note_ids)

        assert 0.0 <= diversity <= 1.0
        assert metadata["supporter_count"] == 2
        assert metadata["valid_pair_count"] == 1


class TestMeanCenteringCorrectness:
    def test_not_helpful_becomes_negative_after_centering(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_a", "note_2", 0.0),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)

        idx_helpful = note_ids.index("note_1")
        idx_not_helpful = note_ids.index("note_2")
        assert profiles["rater_a"][idx_helpful] > 0.0
        assert profiles["rater_a"][idx_not_helpful] < 0.0

    def test_unrated_stays_zero_after_centering(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 0.8),
            ("rater_b", "note_1", 0.4),
            ("rater_b", "note_2", 0.6),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)

        idx2 = note_ids.index("note_2")
        assert profiles["rater_a"][idx2] == 0.0


class TestZeroVectorFromUniformRating:
    def test_rater_with_all_same_ratings_becomes_zero_vector(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_uniform", "note_1", 0.5),
            ("rater_uniform", "note_2", 0.5),
            ("rater_uniform", "note_3", 0.5),
        ]

        profiles, _note_ids = scorer.build_rater_profiles(ratings)

        vec = profiles["rater_uniform"]
        assert np.linalg.norm(vec) < 1e-12

    def test_uniform_rater_excluded_from_diversity(self):
        scorer = RaterDiversityScorer()
        note_ids = ["note_1", "note_2"]
        profiles = {
            "rater_a": np.array([0.5, -0.5]),
            "rater_uniform": np.array([0.0, 0.0]),
            "rater_b": np.array([-0.5, 0.5]),
        }

        diversity, metadata = scorer.compute_diversity(
            ["rater_a", "rater_uniform", "rater_b"], profiles, note_ids
        )

        assert metadata["supporter_count"] == 2
        assert math.isclose(diversity, 1.0, abs_tol=1e-9)


class TestBlendingFormulaExact:
    def test_exact_blending_calculation(self):
        table = _make_ratings_table(
            ["r_a", "r_a", "r_b", "r_b"],
            ["n1", "n2", "n1", "n2"],
            ["HELPFUL", "NOT_HELPFUL", "NOT_HELPFUL", "HELPFUL"],
        )
        provider = FakeDataProvider(table)
        bonus = 0.3
        adapter = RaterDiversityScorerAdapter(provider, "c1", diversity_bonus=bonus)

        result = adapter.score_note("n1", [1.0, 0.0])

        bayesian_base = result.metadata["bayesian_base_score"]
        diversity_score = result.metadata["diversity_score"]
        expected = min(bayesian_base * (1.0 + bonus * diversity_score), 1.0)
        assert math.isclose(result.score, expected, rel_tol=1e-9)

    def test_blending_clamps_lower_bound_to_zero(self):
        table = _make_ratings_table(
            ["r_a", "r_a", "r_b", "r_b"],
            ["n1", "n2", "n1", "n2"],
            ["HELPFUL", "NOT_HELPFUL", "NOT_HELPFUL", "HELPFUL"],
        )
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "c1", diversity_bonus=0.3)

        result = adapter.score_note("n1", [0.0, 0.0])

        assert result.score >= 0.0


class TestSingleNoteMatrix:
    def test_single_note_in_rating_matrix(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_b", "note_1", 0.0),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)

        assert len(note_ids) == 1
        assert profiles["rater_a"][0] == 0.0
        assert profiles["rater_b"][0] == 0.0

    def test_single_note_diversity_is_zero(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_b", "note_1", 0.5),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)
        _diversity, metadata = scorer.compute_diversity(["rater_a", "rater_b"], profiles, note_ids)

        assert metadata["diversity_signal"] == "insufficient"


class TestAllRatersRateOneNote:
    def test_multiple_raters_single_note(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_b", "note_1", 0.5),
            ("rater_c", "note_1", 0.0),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)

        for rater_id in ["rater_a", "rater_b", "rater_c"]:
            assert np.linalg.norm(profiles[rater_id]) < 1e-12

        diversity, metadata = scorer.compute_diversity(
            ["rater_a", "rater_b", "rater_c"], profiles, note_ids
        )

        assert diversity == 0.0
        assert metadata["diversity_signal"] == "insufficient"


class TestVerySparseMatrix:
    def test_each_rater_rates_only_one_different_note(self):
        scorer = RaterDiversityScorer()
        ratings = [
            ("rater_a", "note_1", 1.0),
            ("rater_b", "note_2", 0.5),
            ("rater_c", "note_3", 0.0),
        ]

        profiles, note_ids = scorer.build_rater_profiles(ratings)

        assert len(note_ids) == 3
        for rater_id in ["rater_a", "rater_b", "rater_c"]:
            assert np.linalg.norm(profiles[rater_id]) < 1e-12

        diversity, metadata = scorer.compute_diversity(
            ["rater_a", "rater_b", "rater_c"], profiles, note_ids
        )

        assert diversity == 0.0
        assert metadata["diversity_signal"] == "insufficient"


class TestCustomThresholds:
    def test_custom_supporter_threshold(self):
        scorer = RaterDiversityScorer(supporter_threshold=0.9)
        note_ids = ["target_note", "note_2"]
        profiles = {
            "rater_a": np.array([0.5, -0.5]),
            "rater_b": np.array([-0.5, 0.5]),
            "rater_c": np.array([0.3, -0.3]),
        }

        note_rater_ratings = [
            ("rater_a", 1.0),
            ("rater_b", 0.8),
            ("rater_c", 0.95),
        ]

        _diversity, metadata = scorer.score_note_diversity(
            "target_note", note_rater_ratings, profiles, note_ids
        )

        assert metadata["supporter_count"] == 2

    def test_custom_min_supporters(self):
        scorer = RaterDiversityScorer(min_supporters=3)
        note_ids = ["note_1", "note_2"]
        profiles = {
            "rater_a": np.array([0.5, -0.5]),
            "rater_b": np.array([-0.5, 0.5]),
        }

        diversity, metadata = scorer.compute_diversity(["rater_a", "rater_b"], profiles, note_ids)

        assert diversity == 0.0
        assert metadata["diversity_signal"] == "insufficient"
        assert metadata["supporter_count"] == 2

    def test_custom_min_supporters_met(self):
        scorer = RaterDiversityScorer(min_supporters=3)
        note_ids = ["note_1", "note_2"]
        profiles = {
            "rater_a": np.array([0.5, -0.5]),
            "rater_b": np.array([-0.5, 0.5]),
            "rater_c": np.array([0.3, -0.3]),
        }

        diversity, metadata = scorer.compute_diversity(
            ["rater_a", "rater_b", "rater_c"], profiles, note_ids
        )

        assert diversity > 0.0
        assert metadata["diversity_signal"] in ("weak", "strong")
        assert metadata["supporter_count"] == 3
