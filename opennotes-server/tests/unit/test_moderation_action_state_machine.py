"""Unit tests for ModerationAction state machine transition validation."""

import pytest

from src.moderation_actions.models import ActionState
from src.moderation_actions.schemas import VALID_TRANSITIONS

pytestmark = pytest.mark.unit


class TestValidTransitionsMap:
    def test_all_states_have_entries(self):
        for state in ActionState:
            assert state in VALID_TRANSITIONS, f"State {state} missing from VALID_TRANSITIONS"

    def test_proposed_can_transition_to_applied(self):
        assert ActionState.APPLIED in VALID_TRANSITIONS[ActionState.PROPOSED]

    def test_proposed_can_transition_to_under_review(self):
        assert ActionState.UNDER_REVIEW in VALID_TRANSITIONS[ActionState.PROPOSED]

    def test_proposed_can_transition_to_dismissed(self):
        assert ActionState.DISMISSED in VALID_TRANSITIONS[ActionState.PROPOSED]

    def test_applied_can_transition_to_retro_review(self):
        assert ActionState.RETRO_REVIEW in VALID_TRANSITIONS[ActionState.APPLIED]

    def test_applied_can_transition_to_overturned(self):
        assert ActionState.OVERTURNED in VALID_TRANSITIONS[ActionState.APPLIED]

    def test_retro_review_can_transition_to_confirmed(self):
        assert ActionState.CONFIRMED in VALID_TRANSITIONS[ActionState.RETRO_REVIEW]

    def test_retro_review_can_transition_to_overturned(self):
        assert ActionState.OVERTURNED in VALID_TRANSITIONS[ActionState.RETRO_REVIEW]

    def test_confirmed_is_terminal(self):
        assert VALID_TRANSITIONS[ActionState.CONFIRMED] == set()

    def test_dismissed_is_terminal(self):
        assert VALID_TRANSITIONS[ActionState.DISMISSED] == set()

    def test_overturned_can_transition_to_scan_exempt(self):
        assert ActionState.SCAN_EXEMPT in VALID_TRANSITIONS[ActionState.OVERTURNED]

    def test_scan_exempt_can_transition_to_proposed(self):
        assert ActionState.PROPOSED in VALID_TRANSITIONS[ActionState.SCAN_EXEMPT]

    def test_under_review_can_transition_to_applied(self):
        assert ActionState.APPLIED in VALID_TRANSITIONS[ActionState.UNDER_REVIEW]

    def test_under_review_can_transition_to_dismissed(self):
        assert ActionState.DISMISSED in VALID_TRANSITIONS[ActionState.UNDER_REVIEW]


class TestInvalidTransitions:
    def test_proposed_cannot_transition_to_confirmed(self):
        assert ActionState.CONFIRMED not in VALID_TRANSITIONS[ActionState.PROPOSED]

    def test_proposed_cannot_transition_to_retro_review(self):
        assert ActionState.RETRO_REVIEW not in VALID_TRANSITIONS[ActionState.PROPOSED]

    def test_proposed_cannot_transition_to_overturned(self):
        assert ActionState.OVERTURNED not in VALID_TRANSITIONS[ActionState.PROPOSED]

    def test_proposed_cannot_transition_to_scan_exempt(self):
        assert ActionState.SCAN_EXEMPT not in VALID_TRANSITIONS[ActionState.PROPOSED]

    def test_applied_cannot_transition_to_proposed(self):
        assert ActionState.PROPOSED not in VALID_TRANSITIONS[ActionState.APPLIED]

    def test_applied_cannot_transition_to_dismissed(self):
        assert ActionState.DISMISSED not in VALID_TRANSITIONS[ActionState.APPLIED]

    def test_applied_cannot_transition_to_confirmed(self):
        assert ActionState.CONFIRMED not in VALID_TRANSITIONS[ActionState.APPLIED]

    def test_confirmed_cannot_transition_to_anything(self):
        assert len(VALID_TRANSITIONS[ActionState.CONFIRMED]) == 0

    def test_dismissed_cannot_transition_to_anything(self):
        assert len(VALID_TRANSITIONS[ActionState.DISMISSED]) == 0

    def test_overturned_cannot_transition_to_proposed_directly(self):
        assert ActionState.PROPOSED not in VALID_TRANSITIONS[ActionState.OVERTURNED]

    def test_scan_exempt_cannot_transition_to_confirmed(self):
        assert ActionState.CONFIRMED not in VALID_TRANSITIONS[ActionState.SCAN_EXEMPT]

    def test_under_review_cannot_transition_to_overturned(self):
        assert ActionState.OVERTURNED not in VALID_TRANSITIONS[ActionState.UNDER_REVIEW]

    def test_retro_review_cannot_transition_to_proposed(self):
        assert ActionState.PROPOSED not in VALID_TRANSITIONS[ActionState.RETRO_REVIEW]


class TestTransitionValidationFunction:
    """Test the is_valid_transition helper (exported from schemas)."""

    def test_valid_transition_returns_true(self):
        from src.moderation_actions.schemas import is_valid_transition

        assert is_valid_transition(ActionState.PROPOSED, ActionState.APPLIED) is True

    def test_invalid_transition_returns_false(self):
        from src.moderation_actions.schemas import is_valid_transition

        assert is_valid_transition(ActionState.CONFIRMED, ActionState.PROPOSED) is False

    def test_self_transition_is_invalid(self):
        from src.moderation_actions.schemas import is_valid_transition

        assert is_valid_transition(ActionState.PROPOSED, ActionState.PROPOSED) is False

    def test_all_valid_transitions_pass(self):
        from src.moderation_actions.schemas import is_valid_transition

        for from_state, to_states in VALID_TRANSITIONS.items():
            for to_state in to_states:
                assert is_valid_transition(from_state, to_state) is True, (
                    f"Expected valid: {from_state} -> {to_state}"
                )

    def test_all_invalid_transitions_fail(self):
        from src.moderation_actions.schemas import is_valid_transition

        for from_state in ActionState:
            valid_targets = VALID_TRANSITIONS[from_state]
            for to_state in ActionState:
                if to_state not in valid_targets:
                    assert is_valid_transition(from_state, to_state) is False, (
                        f"Expected invalid: {from_state} -> {to_state}"
                    )
