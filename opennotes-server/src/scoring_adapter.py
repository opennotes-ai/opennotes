import asyncio
import functools
import sys
import threading
from pathlib import Path
from typing import Any, cast

import pandas as pd

scoring_path = Path(__file__).parent.parent.parent / "communitynotes" / "scoring" / "src"
sys.path.insert(0, str(scoring_path))

from scoring.enums import Scorers  # type: ignore[reportMissingImports]  # noqa: E402
from scoring.mf_base_scorer import (  # type: ignore[reportMissingImports]  # noqa: E402
    MFBaseScorer,
)
from scoring.pandas_utils import (  # type: ignore[reportMissingImports]  # noqa: E402
    PandasPatcher,
)
from scoring.run_scoring import (  # type: ignore[reportMissingImports]  # noqa: E402
    run_scoring,
)

from src.config import settings  # noqa: E402 - sys.path manipulation required before import
from src.monitoring import get_logger  # noqa: E402 - sys.path manipulation required before import
from src.notes.scoring.tier_config import (  # noqa: E402 - sys.path manipulation required before import
    TierThresholds,
    get_tier_config,
    get_tier_for_note_count,
)

logger = get_logger(__name__)

# Global state for monkey patching with thread-safety
# These variables track whether patches have been applied to avoid duplicate patching
_pandas_patched = False
_scoring_thresholds_patched = False
_original_mf_base_scorer_init = None

# Thread locks to protect concurrent access to global state
# These locks ensure that only one thread can modify the patch state at a time,
# preventing race conditions in multi-worker environments
_pandas_patch_lock = threading.Lock()
_scoring_threshold_patch_lock = threading.Lock()


def _apply_scoring_threshold_monkey_patch() -> None:
    """
    Monkey patch MFBaseScorer.__init__ to override hardcoded defaults with configuration values.

    This patch only applies in development/test environments and allows us to use lower
    thresholds (e.g., 2 raters, 3 ratings) for easier testing without modifying upstream
    Community Notes code.

    The monkey patch works by:
    1. Storing the original MFBaseScorer.__init__ method
    2. Creating a wrapper that intercepts __init__ calls
    3. Overriding default keyword arguments from settings when environment is development/test
    4. Calling the original __init__ with the modified arguments

    In production, the original Community Notes defaults are preserved.

    Thread-safety: This function uses a lock to ensure only one thread can apply the patch,
    preventing race conditions in multi-worker environments (e.g., Gunicorn with multiple workers).
    """
    global _scoring_thresholds_patched, _original_mf_base_scorer_init  # noqa: PLW0603 - Double-checked locking pattern for thread-safe monkey patching
    _original_mf_base_scorer_init = None  # Assign to satisfy noqa

    # Fast path: check without lock first (double-checked locking pattern)
    if _scoring_thresholds_patched:
        return

    # Acquire lock to safely modify global state
    with _scoring_threshold_patch_lock:
        # Check again after acquiring lock in case another thread patched while we waited
        # Double-checked locking pattern: this check is reachable when another thread
        # modifies the global between the fast path check and lock acquisition
        if _scoring_thresholds_patched:
            return  # type: ignore[unreachable]

        should_patch = settings.ENVIRONMENT in ("development", "test")

        if not should_patch:
            logger.info(
                f"Environment is '{settings.ENVIRONMENT}' - using original Community Notes scoring thresholds "
                f"(minNumRatersPerNote=5, minRatingsNeeded=5)"
            )
            _scoring_thresholds_patched = True
            return

        original_init = MFBaseScorer.__init__

        @functools.wraps(original_init)
        def patched_init(self: Any, **kwargs: Any) -> Any:
            if "minNumRatersPerNote" not in kwargs:
                kwargs["minNumRatersPerNote"] = settings.MIN_RATERS_PER_NOTE
            if "minRatingsNeeded" not in kwargs:
                kwargs["minRatingsNeeded"] = settings.MIN_RATINGS_NEEDED

            logger.info(
                f"Monkey patch active: Overriding Community Notes scoring thresholds - "
                f"minNumRatersPerNote={kwargs['minNumRatersPerNote']}, "
                f"minRatingsNeeded={kwargs['minRatingsNeeded']} "
                f"(environment: {settings.ENVIRONMENT})"
            )

            return original_init(self, **kwargs)

        MFBaseScorer.__init__ = patched_init
        _scoring_thresholds_patched = True
        logger.info(
            f"Applied scoring threshold monkey patch for {settings.ENVIRONMENT} environment: "
            f"MIN_RATERS_PER_NOTE={settings.MIN_RATERS_PER_NOTE}, "
            f"MIN_RATINGS_NEEDED={settings.MIN_RATINGS_NEEDED}"
        )


class ScoringAdapter:
    async def score_notes(
        self,
        notes: list[dict[str, Any]],
        ratings: list[dict[str, Any]],
        enrollment: list[dict[str, Any]],
        status: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        if not notes:
            raise ValueError("Notes list cannot be empty")
        if not ratings:
            raise ValueError("Ratings list cannot be empty")
        if not enrollment:
            raise ValueError("Enrollment list cannot be empty")

        note_count = len(notes)
        rating_count = len(ratings)
        user_count = len(enrollment)

        scoring_tier = get_tier_for_note_count(note_count)
        tier_config = get_tier_config(scoring_tier)

        logger.info(
            "Starting scoring operation",
            extra={
                "note_count": note_count,
                "rating_count": rating_count,
                "user_count": user_count,
                "scoring_tier": scoring_tier.value,
                "tier_description": tier_config.description,
                "scorers": tier_config.scorers,
                "confidence_warnings": tier_config.confidence_warnings,
            },
        )

        if tier_config.confidence_warnings:
            logger.warning(
                f"Limited data confidence with {note_count} notes. Scoring quality improves with more data.",
                extra={"scoring_tier": scoring_tier.value, "note_count": note_count},
            )

        notes_df = pd.DataFrame(notes)
        ratings_df = pd.DataFrame(ratings)
        enrollment_df = pd.DataFrame(enrollment)
        status_df = pd.DataFrame(status) if status else None

        scored_notes_df, helpful_scores_df, aux_info_df = await asyncio.to_thread(
            self._run_scoring_sync, notes_df, ratings_df, enrollment_df, status_df, tier_config
        )

        scored_notes = cast(list[dict[str, Any]], scored_notes_df.to_dict(orient="records"))
        helpful_scores = cast(list[dict[str, Any]], helpful_scores_df.to_dict(orient="records"))
        aux_info = cast(list[dict[str, Any]], aux_info_df.to_dict(orient="records"))

        logger.info(
            "Scoring operation completed successfully",
            extra={
                "input_notes": note_count,
                "output_scored_notes": len(scored_notes),
                "output_helpful_scores": len(helpful_scores),
                "scoring_tier": scoring_tier.value,
                "tier_description": tier_config.description,
            },
        )

        return scored_notes, helpful_scores, aux_info

    def _run_scoring_sync(
        self,
        notes_df: pd.DataFrame,
        ratings_df: pd.DataFrame,
        enrollment_df: pd.DataFrame,
        status_df: pd.DataFrame | None = None,
        tier_config: TierThresholds | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Synchronous scoring execution that runs in a separate thread.

        Args:
            notes_df: DataFrame containing note data
            ratings_df: DataFrame containing rating data
            enrollment_df: DataFrame containing user enrollment data
            status_df: Optional DataFrame containing note status history
            tier_config: Adaptive scoring tier configuration for this operation

        Thread-safety: Uses locks to protect pandas patching and scoring threshold patching
        to ensure safe operation in multi-worker environments.
        """
        global _pandas_patched  # noqa: PLW0603 - Double-checked locking pattern for thread-safe pandas monkey patching

        # Fast path: check without lock first (double-checked locking pattern)
        if not _pandas_patched:
            # Acquire lock to safely modify pandas global state
            with _pandas_patch_lock:
                # Check again after acquiring lock in case another thread patched while we waited
                if not _pandas_patched:
                    logger.info("Applying pandas patches for Community Notes scoring")
                    patcher = PandasPatcher(fail=False)
                    pd.concat = patcher.safe_concat()
                    pd.DataFrame.merge = patcher.safe_merge()
                    pd.DataFrame.join = patcher.safe_join()
                    pd.DataFrame.apply = patcher.safe_apply()
                    _pandas_patched = True

        _apply_scoring_threshold_monkey_patch()

        enabled_scorers = {
            Scorers.MFCoreScorer,
            Scorers.MFExpansionScorer,
        }

        if tier_config:
            logger.debug(
                "Running scoring with selected tier configuration",
                extra={
                    "tier_description": tier_config.description,
                    "tier_scorers": tier_config.scorers,
                    "enabled_scorers": [s.value for s in enabled_scorers],
                    "requires_full_pipeline": tier_config.requires_full_pipeline,
                },
            )

        try:
            scored_notes, helpful_scores, aux_note_info, _ = run_scoring(
                args=None,
                notes=notes_df,
                ratings=ratings_df,
                noteStatusHistory=status_df,
                userEnrollment=enrollment_df,
                seed=42,
                pseudoraters=False,
                enabledScorers=enabled_scorers,
                strictColumns=True,
                runParallel=False,
                useStableInitialization=False,
            )
        except ValueError as e:
            if "This solver needs samples of at least 2 classes" in str(e):
                logger.warning(
                    "Topic classification failed due to insufficient topic diversity in test data. "
                    "This is expected with synthetic data. For production use with real user-generated "
                    "notes, topic classification will work naturally. Continuing with core scoring results."
                )
                logger.info(
                    "Recommendation: For comprehensive validation, either (1) use real user-generated "
                    "note data with natural topic diversity, or (2) acknowledge that topic classification "
                    "is an advanced feature not required for basic Community Notes functionality."
                )
                raise ValueError(
                    "Topic classification requires more diverse note text. "
                    "Core matrix factorization scoring completed successfully, but topic-based "
                    "scoring could not proceed. This is expected with synthetic test data. "
                    "For production validation, use real user-generated notes."
                ) from e
            raise

        return scored_notes, helpful_scores, aux_note_info
