"""
Batch Scoring Trigger for MFCoreScorer integration.

Determines when a community has enough notes to trigger MFCoreScorer
batch scoring (threshold: 200 notes, from Community Notes minNumNotesForProdData).
"""

from typing import Any

DEFAULT_BATCH_THRESHOLD = 200


class BatchScoringTrigger:
    """
    Trigger for determining when to run MFCoreScorer batch scoring.

    The Community Notes MFCoreScorer requires a minimum number of notes
    (minNumNotesForProdData = 200) to produce reliable scores using
    matrix factorization. This class helps determine when a community
    has crossed that threshold.
    """

    def __init__(self, threshold: int = DEFAULT_BATCH_THRESHOLD):
        """
        Initialize the trigger with a threshold.

        Args:
            threshold: Minimum number of notes required for batch scoring.
                      Defaults to 200 (Community Notes minNumNotesForProdData).
        """
        self.threshold = threshold

    def should_trigger(self, note_count: int) -> bool:
        """
        Check if batch scoring should be triggered based on current note count.

        Args:
            note_count: Current number of notes in the community

        Returns:
            True if note_count >= threshold, False otherwise
        """
        return note_count >= self.threshold

    def check_transition(self, previous_count: int, current_count: int) -> bool:
        """
        Check if the threshold was just crossed (first time transition).

        This is useful for triggering one-time events when a community
        first becomes eligible for batch scoring.

        Args:
            previous_count: Previous note count
            current_count: Current note count

        Returns:
            True if threshold was just crossed (was below, now at or above)
        """
        was_below = previous_count < self.threshold
        now_at_or_above = current_count >= self.threshold
        return was_below and now_at_or_above

    def get_status(self, note_count: int) -> dict[str, Any]:
        """
        Get the current batch scoring status for a community.

        Args:
            note_count: Current number of notes in the community

        Returns:
            Dictionary with status information:
                - threshold: The batch scoring threshold
                - note_count: Current number of notes
                - ready_for_batch_scoring: Whether batch scoring can be triggered
                - notes_until_batch: Notes needed to reach threshold (0 if already there)
        """
        ready = self.should_trigger(note_count)
        notes_until = max(0, self.threshold - note_count)

        return {
            "threshold": self.threshold,
            "note_count": note_count,
            "ready_for_batch_scoring": ready,
            "notes_until_batch": notes_until,
        }
