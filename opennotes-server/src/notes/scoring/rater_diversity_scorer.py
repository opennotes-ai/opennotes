import logging
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np
import pyarrow.compute as pc
from sklearn.metrics import pairwise_distances

from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
from src.notes.scoring.bayesian_scorer_adapter import BayesianAverageScorerAdapter
from src.notes.scoring.data_provider import CommunityDataProvider
from src.notes.scoring.data_transforms import _map_helpfulness
from src.notes.scoring.scorer_protocol import ScoringResult

logger = logging.getLogger(__name__)


class RaterDiversityScorer:
    def __init__(
        self,
        supporter_threshold: float = 0.6,
        min_supporters: int = 2,
    ):
        self.supporter_threshold = supporter_threshold
        self.min_supporters = min_supporters

    def build_rater_profiles(
        self, all_ratings: list[tuple[str, str, float]]
    ) -> tuple[dict[str, np.ndarray], list[str]]:
        note_id_set: dict[str, int] = {}
        rater_ratings: dict[str, dict[int, float]] = defaultdict(dict)

        for rater_id, note_id, rating in all_ratings:
            if note_id not in note_id_set:
                note_id_set[note_id] = len(note_id_set)
            idx = note_id_set[note_id]
            rater_ratings[rater_id][idx] = rating

        note_ids = list(note_id_set.keys())
        num_notes = len(note_ids)

        profiles: dict[str, np.ndarray] = {}
        for rater_id, rating_map in rater_ratings.items():
            rated_values = list(rating_map.values())
            rater_mean = np.mean(rated_values)

            vec = np.zeros(num_notes, dtype=np.float64)
            for idx, value in rating_map.items():
                vec[idx] = value - rater_mean

            profiles[rater_id] = vec

        return profiles, note_ids

    def compute_diversity(
        self,
        supporter_ids: list[str],
        rater_profiles: dict[str, np.ndarray],
        _note_ids: list[str],
    ) -> tuple[float, dict[str, Any]]:
        valid_profiles: list[np.ndarray] = []
        for sid in supporter_ids:
            if sid not in rater_profiles:
                continue
            vec = rater_profiles[sid]
            if np.linalg.norm(vec) < 1e-12:
                continue
            valid_profiles.append(vec)

        num_valid = len(valid_profiles)

        if num_valid < self.min_supporters:
            return 0.0, {
                "valid_pair_count": 0,
                "total_pair_count": 0,
                "pair_coverage_ratio": 0.0,
                "supporter_count": num_valid,
                "mean_pairwise_distance": 0.0,
                "diversity_signal": "insufficient",
            }

        profile_matrix = np.vstack(valid_profiles)
        dist_matrix = pairwise_distances(profile_matrix, metric="cosine")

        triu_indices = np.triu_indices(num_valid, k=1)
        pairwise_dists = dist_matrix[triu_indices]

        total_pairs = len(pairwise_dists)
        valid_pairs = int(np.sum(~np.isnan(pairwise_dists)))
        valid_dists = pairwise_dists[~np.isnan(pairwise_dists)]

        mean_distance = 0.0 if valid_pairs == 0 else float(np.mean(valid_dists))

        diversity = np.clip(mean_distance, 0.0, 1.0)

        if valid_pairs == 0:
            signal = "insufficient"
        elif diversity >= 0.5:
            signal = "strong"
        else:
            signal = "weak"

        return float(diversity), {
            "valid_pair_count": valid_pairs,
            "total_pair_count": total_pairs,
            "pair_coverage_ratio": valid_pairs / total_pairs if total_pairs > 0 else 0.0,
            "supporter_count": num_valid,
            "mean_pairwise_distance": float(mean_distance),
            "diversity_signal": signal,
        }

    def score_note_diversity(
        self,
        _note_id: str,
        note_rater_ratings: list[tuple[str, float]],
        rater_profiles: dict[str, np.ndarray],
        note_ids: list[str],
    ) -> tuple[float, dict[str, Any]]:
        supporter_ids = [
            rater_id
            for rater_id, rating in note_rater_ratings
            if rating >= self.supporter_threshold
        ]

        return self.compute_diversity(supporter_ids, rater_profiles, note_ids)


class RaterDiversityScorerAdapter:
    def __init__(
        self,
        data_provider: CommunityDataProvider,
        community_id: str,
        diversity_bonus: float = 0.3,
    ) -> None:
        self._diversity_bonus = diversity_bonus
        self._diversity = RaterDiversityScorer()
        self._bayesian = BayesianAverageScorerAdapter(BayesianAverageScorer())

        ratings_table = data_provider.get_all_ratings(community_id)

        self._note_ratings_index: dict[str, list[tuple[str, float]]] = defaultdict(list)
        all_rating_triples: list[tuple[str, str, float]] = []

        if ratings_table.num_rows > 0:
            rater_ids = ratings_table.column("rater_id").to_pylist()
            note_ids = ratings_table.column("note_id").to_pylist()
            numeric_ratings = pc.cast(
                _map_helpfulness(ratings_table.column("helpfulness_level")),
                "float64",
            ).to_pylist()

            for rater_id, note_id, rating in zip(rater_ids, note_ids, numeric_ratings, strict=True):
                self._note_ratings_index[note_id].append((rater_id, rating))
                all_rating_triples.append((rater_id, note_id, rating))

        self._rater_profiles, self._note_ids = self._diversity.build_rater_profiles(
            all_rating_triples
        )

    def score_note(self, note_id: str, ratings: Sequence[float]) -> ScoringResult:
        bayesian_result = self._bayesian.score_note(note_id, ratings)

        note_rater_ratings = self._note_ratings_index.get(note_id)

        if not note_rater_ratings:
            metadata = {
                **bayesian_result.metadata,
                "diversity_score": 0.0,
                "supporter_count": 0,
                "mean_pairwise_distance": 0.0,
                "blend_weight": self._diversity_bonus,
                "diversity_signal": "insufficient",
                "valid_pair_count": 0,
                "total_pair_count": 0,
                "pair_coverage_ratio": 0.0,
                "bayesian_base_score": bayesian_result.score,
            }
            return ScoringResult(
                score=bayesian_result.score,
                confidence_level=bayesian_result.confidence_level,
                metadata=metadata,
            )

        diversity_score, diversity_metadata = self._diversity.score_note_diversity(
            note_id, note_rater_ratings, self._rater_profiles, self._note_ids
        )

        raw_score = bayesian_result.score * (1.0 + self._diversity_bonus * diversity_score)
        final_score = min(max(raw_score, 0.0), 1.0)

        metadata = {
            **bayesian_result.metadata,
            "diversity_score": diversity_score,
            "blend_weight": self._diversity_bonus,
            "bayesian_base_score": bayesian_result.score,
            **diversity_metadata,
        }

        return ScoringResult(
            score=final_score,
            confidence_level=bayesian_result.confidence_level,
            metadata=metadata,
        )
