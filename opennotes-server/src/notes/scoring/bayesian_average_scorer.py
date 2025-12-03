import logging
import time
from typing import Any

from src.monitoring import metrics
from src.monitoring.instance import InstanceMetadata

logger = logging.getLogger(__name__)


class BayesianAverageScorer:
    def __init__(
        self,
        confidence_param: float = 2.0,
        prior_mean: float = 0.5,
        min_ratings_for_confidence: int = 5,
    ):
        self.C = confidence_param
        self.m = prior_mean
        self.min_ratings_for_confidence = min_ratings_for_confidence

        self._clamping_count = 0
        self._zero_rating_count = 0

        instance_id = InstanceMetadata.get_instance_id()
        metrics.bayesian_prior_value.labels(instance_id=instance_id).set(self.m)

        logger.info(
            "BayesianAverageScorer initialized",
            extra={
                "scorer_type": "bayesian_average",
                "tier_level": 0,
                "confidence_param": self.C,
                "prior_mean": self.m,
                "min_ratings_for_confidence": self.min_ratings_for_confidence,
            },
        )

    def calculate_score(self, ratings: list[float], note_id: str | None = None) -> float:
        start_time = time.perf_counter()
        instance_id = InstanceMetadata.get_instance_id()
        metrics.bayesian_scorer_invocations_total.labels(instance_id=instance_id).inc()

        try:
            if not ratings:
                self._zero_rating_count += 1
                metrics.bayesian_no_data_scores_total.labels(instance_id=instance_id).inc()
                metrics.bayesian_rating_count_distribution.labels(instance_id=instance_id).observe(
                    0
                )

                duration = time.perf_counter() - start_time
                metrics.bayesian_scoring_duration_seconds.labels(instance_id=instance_id).observe(
                    duration
                )

                logger.info(
                    "No ratings provided, returning prior mean",
                    extra={
                        "scorer_type": "bayesian_average",
                        "note_id": note_id,
                        "prior_mean": self.m,
                        "zero_rating_count": self._zero_rating_count,
                        "duration_seconds": duration,
                    },
                )
                return self.m

            clamped_ratings = self._clamp_ratings(ratings)

            n = len(clamped_ratings)
            ratings_sum = sum(clamped_ratings)

            score = (self.C * self.m + ratings_sum) / (self.C + n)

            metrics.bayesian_rating_count_distribution.labels(instance_id=instance_id).observe(n)

            score_deviation = abs(score - self.m)
            metrics.bayesian_score_deviation_from_prior.labels(instance_id=instance_id).observe(
                score_deviation
            )

            if n < self.min_ratings_for_confidence:
                metrics.bayesian_provisional_scores_total.labels(instance_id=instance_id).inc()
                confidence_level = "provisional"
            else:
                confidence_level = "standard"

            duration = time.perf_counter() - start_time
            metrics.bayesian_scoring_duration_seconds.labels(instance_id=instance_id).observe(
                duration
            )

            logger.info(
                "Calculated Bayesian Average score",
                extra={
                    "scorer_type": "bayesian_average",
                    "note_id": note_id,
                    "rating_count": n,
                    "ratings_sum": ratings_sum,
                    "score": score,
                    "score_deviation_from_prior": score_deviation,
                    "confidence_level": confidence_level,
                    "C": self.C,
                    "m": self.m,
                    "duration_seconds": duration,
                },
            )

            return score

        except Exception as e:
            error_type = type(e).__name__
            metrics.bayesian_fallback_activations_total.labels(
                error_type=error_type, instance_id=instance_id
            ).inc()

            duration = time.perf_counter() - start_time
            metrics.bayesian_scoring_duration_seconds.labels(instance_id=instance_id).observe(
                duration
            )

            logger.error(
                "Error calculating Bayesian Average score, returning prior mean",
                extra={
                    "scorer_type": "bayesian_average",
                    "note_id": note_id,
                    "error": str(e),
                    "error_type": error_type,
                    "prior_mean": self.m,
                    "rating_count": len(ratings) if ratings else 0,
                    "duration_seconds": duration,
                    "fallback_to_prior": True,
                },
                exc_info=True,
            )
            return self.m

    def _clamp_ratings(self, ratings: list[float]) -> list[float]:
        clamped = []
        instance_id = InstanceMetadata.get_instance_id()
        for rating in ratings:
            if rating < 0.0 or rating > 1.0:
                clamped_value = max(0.0, min(1.0, rating))
                self._clamping_count += 1
                metrics.bayesian_rating_clamp_events_total.labels(instance_id=instance_id).inc()

                logger.warning(
                    "Rating value outside valid range [0, 1], clamping",
                    extra={
                        "scorer_type": "bayesian_average",
                        "original_value": rating,
                        "clamped_value": clamped_value,
                        "total_clamping_count": self._clamping_count,
                    },
                )
                clamped.append(clamped_value)
            else:
                clamped.append(rating)

        return clamped

    def get_score_metadata(
        self,
        ratings: list[float],
        score: float | None = None,
        note_id: str | None = None,
    ) -> dict[str, Any]:
        n = len(ratings) if ratings else 0

        if score is None:
            score = self.calculate_score(ratings, note_id=note_id)

        confidence_level = "standard" if n >= self.min_ratings_for_confidence else "provisional"

        metadata: dict[str, Any] = {
            "algorithm": "bayesian_average_tier0",
            "confidence_level": confidence_level,
            "rating_count": n,
            "prior_values": {
                "C": self.C,
                "m": self.m,
            },
        }

        if n == 0:
            metadata["no_data"] = True
            logger.debug(
                "No data flag set in metadata",
                extra={
                    "scorer_type": "bayesian_average",
                    "note_id": note_id,
                    "metadata": metadata,
                },
            )

        if self._clamping_count > 0:
            metadata["clamped_ratings"] = self._clamping_count

        logger.debug(
            "Generated score metadata",
            extra={
                "scorer_type": "bayesian_average",
                "note_id": note_id,
                "confidence_level": confidence_level,
                "rating_count": n,
                "metadata": metadata,
            },
        )

        return metadata

    def update_prior_from_system_average(self, system_average: float) -> None:
        old_prior = self.m

        clamped_avg = max(0.0, min(1.0, system_average))
        if clamped_avg != system_average:
            logger.warning(
                "System average outside valid range [0, 1], clamping",
                extra={
                    "scorer_type": "bayesian_average",
                    "original_average": system_average,
                    "clamped_average": clamped_avg,
                },
            )

        self.m = clamped_avg
        instance_id = InstanceMetadata.get_instance_id()
        metrics.bayesian_prior_updates_total.labels(instance_id=instance_id).inc()
        metrics.bayesian_prior_value.labels(instance_id=instance_id).set(self.m)

        prior_change = abs(self.m - old_prior)

        logger.info(
            "Prior mean updated from system average",
            extra={
                "scorer_type": "bayesian_average",
                "old_prior": old_prior,
                "new_prior": self.m,
                "system_average": system_average,
                "prior_change": prior_change,
            },
        )

    def get_clamping_statistics(self) -> dict[str, int]:
        return {
            "clamping_count": self._clamping_count,
            "zero_rating_count": self._zero_rating_count,
        }

    def reset_statistics(self) -> None:
        self._clamping_count = 0
        self._zero_rating_count = 0
        logger.debug("Statistics reset")
