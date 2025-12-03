"""
Tests for BatchScoringTrigger.

TDD: Write failing tests first, then implement.
"""


class TestBatchScoringTrigger:
    """Tests for BatchScoringTrigger (AC #5)."""

    def test_can_import_batch_scoring_trigger(self):
        """BatchScoringTrigger can be imported."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        assert BatchScoringTrigger is not None

    def test_trigger_can_be_instantiated(self):
        """BatchScoringTrigger can be instantiated."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger()
        assert trigger is not None

    def test_has_default_threshold_of_200(self):
        """BatchScoringTrigger has default threshold of 200 notes."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger()
        assert trigger.threshold == 200

    def test_custom_threshold(self):
        """BatchScoringTrigger can be initialized with custom threshold."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=100)
        assert trigger.threshold == 100


class TestBatchScoringTriggerShouldTrigger:
    """Tests for BatchScoringTrigger.should_trigger() method."""

    def test_should_not_trigger_below_threshold(self):
        """should_trigger() returns False when note count is below threshold."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        result = trigger.should_trigger(note_count=199)

        assert result is False

    def test_should_trigger_at_threshold(self):
        """should_trigger() returns True when note count equals threshold."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        result = trigger.should_trigger(note_count=200)

        assert result is True

    def test_should_trigger_above_threshold(self):
        """should_trigger() returns True when note count exceeds threshold."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        result = trigger.should_trigger(note_count=500)

        assert result is True

    def test_should_not_trigger_at_zero(self):
        """should_trigger() returns False when note count is zero."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        result = trigger.should_trigger(note_count=0)

        assert result is False


class TestBatchScoringTriggerCheckTransition:
    """Tests for checking threshold transition (first time crossing)."""

    def test_check_transition_returns_true_on_first_crossing(self):
        """check_transition() returns True when crossing threshold for first time."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        result = trigger.check_transition(previous_count=199, current_count=200)

        assert result is True

    def test_check_transition_returns_false_when_already_above(self):
        """check_transition() returns False when already above threshold."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        result = trigger.check_transition(previous_count=200, current_count=201)

        assert result is False

    def test_check_transition_returns_false_when_still_below(self):
        """check_transition() returns False when still below threshold."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        result = trigger.check_transition(previous_count=100, current_count=150)

        assert result is False

    def test_check_transition_returns_true_when_jumping_above(self):
        """check_transition() returns True when jumping from below to above threshold."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        result = trigger.check_transition(previous_count=100, current_count=250)

        assert result is True


class TestBatchScoringTriggerGetStatus:
    """Tests for BatchScoringTrigger.get_status() method."""

    def test_get_status_returns_dict(self):
        """get_status() returns a dictionary."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        status = trigger.get_status(note_count=150)

        assert isinstance(status, dict)

    def test_get_status_includes_threshold(self):
        """get_status() includes threshold in response."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        status = trigger.get_status(note_count=150)

        assert status["threshold"] == 200

    def test_get_status_includes_note_count(self):
        """get_status() includes note_count in response."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        status = trigger.get_status(note_count=150)

        assert status["note_count"] == 150

    def test_get_status_includes_ready_for_batch_scoring(self):
        """get_status() includes ready_for_batch_scoring in response."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        status_below = trigger.get_status(note_count=150)
        status_above = trigger.get_status(note_count=250)

        assert status_below["ready_for_batch_scoring"] is False
        assert status_above["ready_for_batch_scoring"] is True

    def test_get_status_includes_notes_until_batch(self):
        """get_status() includes notes_until_batch when below threshold."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        status = trigger.get_status(note_count=150)

        assert status["notes_until_batch"] == 50

    def test_get_status_notes_until_batch_is_zero_when_above(self):
        """get_status() shows notes_until_batch as 0 when above threshold."""
        from src.notes.scoring.batch_scoring_trigger import BatchScoringTrigger

        trigger = BatchScoringTrigger(threshold=200)

        status = trigger.get_status(note_count=250)

        assert status["notes_until_batch"] == 0
