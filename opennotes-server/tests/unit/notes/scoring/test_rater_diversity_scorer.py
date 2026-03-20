import math

import numpy as np

from src.notes.scoring.rater_diversity_scorer import RaterDiversityScorer


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
