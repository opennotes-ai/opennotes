"""
Adapter for MFCoreScorer to implement ScorerProtocol.

This adapter wraps the MFCoreScorer with a caching layer to support
single-note scoring operations. Since MFCoreScorer operates in batch mode,
this adapter caches batch results and serves individual note scores from cache.
"""

import logging
import sys
import threading
import traceback
from collections import OrderedDict
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder
from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder
from src.notes.scoring.scorer_protocol import ScoringResult
from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

if TYPE_CHECKING:
    from src.notes.scoring.data_provider import CommunityDataProvider

scoring_path = (
    Path(__file__).parent.parent.parent.parent.parent / "communitynotes" / "scoring" / "src"
)
if str(scoring_path) not in sys.path:
    sys.path.insert(0, str(scoring_path))

from scoring.constants import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    FinalScoringArgs,
    ModelResult,
    PrescoringArgs,
    PrescoringMetaOutput,
    scorerNameKey,
)
from scoring.mf_core_scorer import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    MFCoreScorer,
)
from scoring.pandas_utils import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    PandasPatcher,
)

logger = logging.getLogger(__name__)


class _PandasPatchState:
    """Track whether pandas has been patched for MFCoreScorer compatibility."""

    patched: bool = False

    @classmethod
    def ensure_patched(cls) -> None:
        """
        Apply PandasPatcher to enable MFCoreScorer's custom pandas extensions.

        MFCoreScorer uses custom pandas operations (unsafeAllowed parameter in merge/join/concat)
        that require patching pandas. This method applies the patches once at module level.

        The patches:
        - Add unsafeAllowed parameter support to DataFrame.merge, DataFrame.join, pd.concat
        - Enable type safety checking that MFCoreScorer relies on
        - Are applied with fail=False, silent=True to avoid disrupting other pandas usage
        """
        if cls.patched:
            return

        patcher = PandasPatcher(fail=False, silent=True)
        pd.DataFrame.merge = patcher.safe_merge()
        pd.DataFrame.join = patcher.safe_join()
        pd.concat = patcher.safe_concat()
        cls.patched = True
        logger.debug("Applied PandasPatcher for MFCoreScorer compatibility")


INTERCEPT_MIN = -0.4
INTERCEPT_MAX = 0.7
INTERCEPT_RANGE = INTERCEPT_MAX - INTERCEPT_MIN


def _normalize_intercept(intercept: float) -> float:
    """
    Normalize a coreNoteIntercept value to a 0.0-1.0 range.

    The typical range for coreNoteIntercept is approximately -0.4 to 0.7.
    This function performs a linear transformation and clamps the result.

    Args:
        intercept: The raw intercept value from MFCoreScorer.

    Returns:
        A normalized score between 0.0 and 1.0.
    """
    normalized = (intercept - INTERCEPT_MIN) / INTERCEPT_RANGE
    return max(0.0, min(1.0, normalized))


def _map_rating_status(status: str) -> str:
    """
    Map MFCoreScorer rating status to confidence level.

    Args:
        status: The coreRatingStatus from MFCoreScorer output.

    Returns:
        A confidence level string: "high", "standard", or "provisional".
    """
    status_mapping = {
        "CURRENTLY_RATED_HELPFUL": "high",
        "CURRENTLY_RATED_NOT_HELPFUL": "standard",
        "NEEDS_MORE_RATINGS": "provisional",
    }
    return status_mapping.get(status, "provisional")


class MFCoreScorerAdapter:
    """
    Adapter that wraps MFCoreScorer to implement ScorerProtocol.

    Since MFCoreScorer scores all notes at once via score_final(),
    this adapter caches batch results and serves individual scores.
    Cache is invalidated when the ratings version changes.

    Thread Safety:
        When initialized with a data_provider, this adapter uses a threading.Lock
        to protect cache operations and batch scoring. Operations that access or
        modify the cache are synchronized to prevent race conditions.
    """

    def __init__(
        self,
        data_provider: "CommunityDataProvider | None" = None,
        community_id: str | None = None,
    ) -> None:
        """
        Initialize the adapter.

        Args:
            data_provider: Optional data provider for fetching community data.
                When provided, enables full MFCoreScorer integration.
            community_id: Optional community ID for which to score notes.
                Required when data_provider is provided.
        """
        self._cache: OrderedDict[str, ScoringResult] = OrderedDict()
        self._cache_version: int = 0
        self._current_version: int = 1

        self._data_provider = data_provider
        self._community_id = community_id
        self._lock = threading.Lock()

        if data_provider is not None:
            _PandasPatchState.ensure_patched()
            self._scorer = MFCoreScorer(
                seed=None,
                pseudoraters=False,
                useStableInitialization=True,
            )
            self._ratings_builder = RatingsDataFrameBuilder()
            self._note_status_builder = NoteStatusHistoryBuilder()
            self._user_enrollment_builder = UserEnrollmentBuilder()
        else:
            self._scorer = None
            self._ratings_builder = None
            self._note_status_builder = None
            self._user_enrollment_builder = None

    def score_note(self, note_id: str, ratings: Sequence[float]) -> ScoringResult:
        """
        Calculate the score for a single note.

        If the cache is valid and contains the note, returns the cached result.
        Otherwise, triggers batch scoring and caches results.

        When a data_provider is configured, uses the full MFCoreScorer algorithm.
        Otherwise, falls back to a stub implementation.

        Thread Safety:
            This method is thread-safe. A lock protects cache operations and
            batch scoring to prevent race conditions during concurrent access.

        Args:
            note_id: The unique identifier for the note being scored.
            ratings: Sequence of rating values for the note.

        Returns:
            ScoringResult containing the score, confidence level, and metadata.
        """
        with self._lock:
            if not self._is_cache_valid():
                self._invalidate_cache()

            if note_id in self._cache:
                logger.debug(
                    "Cache hit for note",
                    extra={"note_id": note_id, "cache_version": self._cache_version},
                )
                self._cache.move_to_end(note_id)
                return self._cache[note_id]

            logger.debug(
                "Cache miss for note, triggering batch scoring",
                extra={"note_id": note_id, "ratings_count": len(ratings)},
            )

            if self._data_provider is not None:
                try:
                    model_result, int_to_uuid = self._execute_batch_scoring()
                    batch_results = self._process_model_result(model_result, int_to_uuid)
                    self._cache.update(batch_results)
                    self._evict_if_needed()

                    if note_id in self._cache:
                        self._cache.move_to_end(note_id)
                        return self._cache[note_id]

                    logger.warning(
                        "Note not found in batch scoring results, using stub",
                        extra={"note_id": note_id},
                    )
                except Exception as e:
                    logger.warning(
                        "Batch scoring failed, falling back to stub",
                        extra={
                            "note_id": note_id,
                            "exception": str(e),
                            "traceback": traceback.format_exc(),
                        },
                    )
                    result = self._score_batch_stub(note_id, ratings)
                    result.metadata["degraded"] = True
                    self._cache[note_id] = result
                    self._evict_if_needed()
                    return result

            result = self._score_batch_stub(note_id, ratings)
            self._cache[note_id] = result
            self._evict_if_needed()

            return result

    def _is_cache_valid(self) -> bool:
        """Check if the cache is still valid based on version."""
        return self._cache_version == self._current_version

    def _invalidate_cache(self) -> None:
        """Invalidate the cache and update cache version."""
        logger.info(
            "Invalidating MFCoreScorer cache",
            extra={
                "old_version": self._cache_version,
                "new_version": self._current_version,
                "cached_notes": len(self._cache),
            },
        )
        self._cache.clear()
        self._cache_version = self._current_version

    def update_ratings_version(self) -> None:
        """
        Increment the ratings version to trigger cache invalidation.

        Call this method when ratings in the community change
        (new ratings added, updated, or deleted).
        """
        self._current_version += 1
        logger.info(
            "Ratings version updated",
            extra={"new_version": self._current_version},
        )

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get statistics about the cache state.

        Returns:
            Dictionary with cache statistics.
        """
        return {
            "cached_notes": len(self._cache),
            "cache_version": self._cache_version,
            "current_version": self._current_version,
            "is_valid": self._is_cache_valid(),
        }

    def _evict_if_needed(self, max_size: int = 10000) -> None:
        """
        Evict oldest cache entries if cache size exceeds max_size.

        Uses LRU (Least Recently Used) eviction strategy. The cache is an
        OrderedDict, and entries are ordered by access time. The oldest
        entries (least recently used) are at the front and evicted first.

        Args:
            max_size: Maximum number of entries to keep in cache. Defaults to 10000.
        """
        while len(self._cache) > max_size:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.debug(
                "Evicted cache entry",
                extra={"evicted_note_id": evicted_key, "cache_size": len(self._cache)},
            )

    def _score_batch_stub(self, note_id: str, ratings: Sequence[float]) -> ScoringResult:
        """
        Stub for batch scoring.

        This will be replaced with actual MFCoreScorer integration in task 805.04.
        For now, returns a placeholder result.

        Args:
            note_id: The note ID being scored.
            ratings: The ratings for the note.

        Returns:
            A stubbed ScoringResult.
        """
        logger.debug(
            "Using batch scoring stub (to be implemented in task 805.04)",
            extra={"note_id": note_id, "ratings_count": len(ratings)},
        )

        rating_count = len(list(ratings))
        confidence_level = "standard" if rating_count >= 5 else "provisional"

        return ScoringResult(
            score=0.5,
            confidence_level=confidence_level,
            metadata={
                "source": "batch_stub",
                "note_id": note_id,
                "rating_count": rating_count,
                "algorithm": "mf_core_stub",
            },
        )

    def _build_note_id_mapping(self, note_ids: list[str]) -> tuple[dict[str, int], dict[int, str]]:
        """
        Build bidirectional mappings between UUID strings and sequential integers.

        Community Notes expects noteId to be np.int64. This method creates mappings
        to convert our UUID strings to integers for scoring and back for results.

        Args:
            note_ids: List of unique note ID strings (UUIDs).

        Returns:
            A tuple of (uuid_to_int, int_to_uuid) dictionaries.
        """
        uuid_to_int = {uuid: idx + 1 for idx, uuid in enumerate(sorted(set(note_ids)))}
        int_to_uuid = {idx: uuid for uuid, idx in uuid_to_int.items()}
        return uuid_to_int, int_to_uuid

    def _apply_note_id_mapping(
        self, df: pd.DataFrame, uuid_to_int: dict[str, int], column: str = "noteId"
    ) -> pd.DataFrame:
        """
        Apply UUID to integer mapping to a DataFrame column.

        Args:
            df: DataFrame with string noteId column.
            uuid_to_int: Mapping from UUID strings to integers.
            column: Name of the column to map (default: "noteId").

        Returns:
            DataFrame with integer noteId column.
        """
        if column in df.columns:
            df = df.copy()
            df[column] = df[column].map(uuid_to_int).astype("int64")
        return df

    def _build_scoring_inputs(
        self,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[int, str]]:
        """
        Build the DataFrames required for MFCoreScorer scoring.

        Fetches all community data from the data_provider and transforms it
        using the DataFrame builders into the format expected by MFCoreScorer.
        Converts UUID noteIds to integers as required by Community Notes.

        Returns:
            A tuple of five items:
            - ratings_df: Ratings in Community Notes format (with int64 noteId)
            - note_status_df: Note status history in Community Notes format (with int64 noteId)
            - user_enrollment_df: User enrollment in Community Notes format
            - note_topics_df: Empty DataFrame (topics not yet implemented)
            - int_to_uuid: Mapping from integer noteIds back to UUID strings

        Raises:
            RuntimeError: If data_provider is None.
        """
        if self._data_provider is None:
            msg = "Cannot build scoring inputs: data_provider is not configured"
            raise RuntimeError(msg)

        community_id = self._community_id or ""

        ratings_data = self._data_provider.get_all_ratings(community_id)
        notes_data = self._data_provider.get_all_notes(community_id)
        participant_ids = self._data_provider.get_all_participants(community_id)

        ratings_df = self._ratings_builder.build(ratings_data)  # pyright: ignore[reportOptionalMemberAccess]
        note_status_df = self._note_status_builder.build(notes_data)  # pyright: ignore[reportOptionalMemberAccess]
        user_enrollment_df = self._user_enrollment_builder.build(participant_ids)  # pyright: ignore[reportOptionalMemberAccess]

        all_note_ids = list(set(ratings_df["noteId"].tolist() + note_status_df["noteId"].tolist()))
        uuid_to_int, int_to_uuid = self._build_note_id_mapping(all_note_ids)

        ratings_df = self._apply_note_id_mapping(ratings_df, uuid_to_int)
        note_status_df = self._apply_note_id_mapping(note_status_df, uuid_to_int)

        note_topics_df = pd.DataFrame(columns=["noteId"])

        logger.debug(
            "Built scoring inputs",
            extra={
                "ratings_count": len(ratings_df),
                "notes_count": len(note_status_df),
                "participants_count": len(user_enrollment_df),
                "community_id": community_id,
                "note_id_mappings": len(uuid_to_int),
            },
        )

        return ratings_df, note_status_df, user_enrollment_df, note_topics_df, int_to_uuid

    def _execute_batch_scoring(self) -> tuple[ModelResult, dict[int, str]]:
        """
        Execute the two-phase MFCoreScorer scoring algorithm.

        This method performs the complete scoring workflow:
        1. Build input DataFrames from community data
        2. Run prescore() to get initial model outputs
        3. Run score_final() with prescore outputs to get final results

        Returns:
            A tuple of:
            - ModelResult containing scored notes and helpfulness scores
            - int_to_uuid mapping to convert integer note IDs back to UUIDs

        Raises:
            RuntimeError: If data_provider is None.
        """
        if self._data_provider is None:
            msg = "Cannot execute batch scoring: data_provider is not configured"
            raise RuntimeError(msg)

        ratings_df, note_status_df, user_enrollment_df, note_topics_df, int_to_uuid = (
            self._build_scoring_inputs()
        )

        prescoring_args = PrescoringArgs(
            noteTopics=note_topics_df,
            ratings=ratings_df,
            noteStatusHistory=note_status_df,
            userEnrollment=user_enrollment_df,
        )

        logger.debug(
            "Running prescore phase",
            extra={
                "ratings_count": len(ratings_df),
                "notes_count": len(note_status_df),
            },
        )

        prescore_result = self._scorer.prescore(prescoring_args)  # pyright: ignore[reportOptionalMemberAccess]

        if prescore_result.scoredNotes is not None:
            prescore_result.scoredNotes[scorerNameKey] = prescore_result.scorerName
        if prescore_result.helpfulnessScores is not None:
            prescore_result.helpfulnessScores[scorerNameKey] = prescore_result.scorerName

        if prescore_result.metaScores is not None and prescore_result.scorerName is not None:
            prescoring_meta_output = PrescoringMetaOutput(
                metaScorerOutput={prescore_result.scorerName: prescore_result.metaScores}
            )
        else:
            prescoring_meta_output = PrescoringMetaOutput(metaScorerOutput={})

        final_scoring_args = FinalScoringArgs(
            noteTopics=note_topics_df,
            ratings=ratings_df,
            noteStatusHistory=note_status_df,
            userEnrollment=user_enrollment_df,
            prescoringNoteModelOutput=prescore_result.scoredNotes,
            prescoringRaterModelOutput=prescore_result.helpfulnessScores,
            prescoringMetaOutput=prescoring_meta_output,
        )

        logger.debug("Running score_final phase")

        final_result = self._scorer.score_final(final_scoring_args)  # pyright: ignore[reportOptionalMemberAccess]

        logger.debug(
            "Batch scoring complete",
            extra={
                "scored_notes_count": (
                    len(final_result.scoredNotes) if final_result.scoredNotes is not None else 0
                ),
            },
        )

        return final_result, int_to_uuid

    def _process_model_result(
        self, model_result: ModelResult, int_to_uuid: dict[int, str]
    ) -> dict[str, ScoringResult]:
        """
        Process MFCoreScorer ModelResult into individual ScoringResults.

        Extracts the scoredNotes DataFrame from the ModelResult and maps each
        note to a ScoringResult with normalized score, confidence level, and metadata.
        Converts integer noteIds back to UUID strings using the provided mapping.

        Args:
            model_result: The ModelResult from score_final().
            int_to_uuid: Mapping from integer noteIds back to UUID strings.

        Returns:
            Dictionary mapping note_id (as UUID string) to ScoringResult.
        """
        results: dict[str, ScoringResult] = {}

        if model_result.scoredNotes is None or len(model_result.scoredNotes) == 0:
            return results

        scored_notes = model_result.scoredNotes

        for _, row in scored_notes.iterrows():
            int_note_id = int(row["noteId"])
            note_id = int_to_uuid.get(int_note_id, str(int_note_id))
            intercept = row.get("coreNoteIntercept", 0.0)
            factor = row.get("coreNoteFactor1", 0.0)
            status = row.get("coreRatingStatus", "NEEDS_MORE_RATINGS")

            score = _normalize_intercept(intercept)
            confidence_level = _map_rating_status(status)

            results[note_id] = ScoringResult(
                score=score,
                confidence_level=confidence_level,
                metadata={
                    "source": "mf_core",
                    "intercept": intercept,
                    "factor": factor,
                    "status": status,
                },
            )

        return results
