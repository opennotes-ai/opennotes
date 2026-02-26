import pytest
from pydantic import ValidationError

from src.simulation.agent import OpenNotesSimAgent, action_selector
from src.simulation.schemas import ActionSelectionResult, SimActionType


class TestActionSelectionResult:
    def test_schema_fields(self):
        result = ActionSelectionResult(action_type=SimActionType.WRITE_NOTE, reasoning="test")
        assert result.action_type == SimActionType.WRITE_NOTE
        assert result.reasoning == "test"

    def test_accepts_write_note(self):
        result = ActionSelectionResult(
            action_type=SimActionType.WRITE_NOTE, reasoning="needs a note"
        )
        assert result.action_type == SimActionType.WRITE_NOTE

    def test_accepts_rate_note(self):
        result = ActionSelectionResult(action_type=SimActionType.RATE_NOTE, reasoning="should rate")
        assert result.action_type == SimActionType.RATE_NOTE

    def test_accepts_pass_turn(self):
        result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing to do"
        )
        assert result.action_type == SimActionType.PASS_TURN

    def test_rejects_react_to_note(self):
        with pytest.raises(ValidationError, match="Phase 1 only allows"):
            ActionSelectionResult(action_type=SimActionType.REACT_TO_NOTE, reasoning="test")

    def test_reasoning_required(self):
        with pytest.raises(ValidationError):
            ActionSelectionResult(action_type=SimActionType.WRITE_NOTE)


class TestBuildPhase1Prompt:
    def test_includes_recent_actions(self):
        agent = OpenNotesSimAgent()
        recent_actions = [
            "write_note",
            "write_note",
            "rate_note",
            "write_note",
            "pass_turn",
        ]
        queue_summary = (
            "2 requests\n  - Content A\n  - Content B\n3 notes\n  - Note X\n  - Note Y\n  - Note Z"
        )
        prompt = agent._build_phase1_prompt(recent_actions, queue_summary)
        assert "write_note" in prompt
        assert "rate_note" in prompt
        assert "pass_turn" in prompt

    def test_includes_queue_summary(self):
        agent = OpenNotesSimAgent()
        recent_actions = ["write_note"]
        queue_summary = "5 requests\n  - Test content\n3 notes\n  - Test note"
        prompt = agent._build_phase1_prompt(recent_actions, queue_summary)
        assert "5 requests" in prompt
        assert "3 notes" in prompt

    def test_encourages_diversity_when_repetitive(self):
        agent = OpenNotesSimAgent()
        recent_actions = [
            "write_note",
            "write_note",
            "write_note",
            "write_note",
            "write_note",
        ]
        queue_summary = "2 requests\n3 notes"
        prompt = agent._build_phase1_prompt(recent_actions, queue_summary)
        lower = prompt.lower()
        assert any(
            word in lower for word in ["divers", "different", "vary", "repetit", "same action"]
        )

    def test_no_diversity_warning_when_varied(self):
        agent = OpenNotesSimAgent()
        recent_actions = ["write_note", "rate_note", "write_note"]
        queue_summary = "2 requests\n3 notes"
        prompt = agent._build_phase1_prompt(recent_actions, queue_summary)
        lower = prompt.lower()
        assert "same action" not in lower
        assert "diversif" not in lower

    def test_no_diversity_warning_for_pass_turn_repeats(self):
        agent = OpenNotesSimAgent()
        recent_actions = ["pass_turn", "pass_turn", "pass_turn"]
        queue_summary = "0 requests\n0 notes"
        prompt = agent._build_phase1_prompt(recent_actions, queue_summary)
        lower = prompt.lower()
        assert "same action" not in lower

    def test_empty_recent_actions(self):
        agent = OpenNotesSimAgent()
        prompt = agent._build_phase1_prompt([], "2 requests\n3 notes")
        assert "2 requests" in prompt
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "recent actions" not in prompt.lower()

    def test_shows_action_count(self):
        agent = OpenNotesSimAgent()
        recent_actions = ["write_note", "rate_note"]
        prompt = agent._build_phase1_prompt(recent_actions, "1 request\n1 note")
        assert "last 2 turns" in prompt

    def test_includes_action_choice_instruction(self):
        agent = OpenNotesSimAgent()
        prompt = agent._build_phase1_prompt([], "1 request\n0 notes")
        assert "write_note" in prompt
        assert "rate_note" in prompt
        assert "pass_turn" in prompt


class TestActionSelectorAgent:
    def test_has_no_function_tools(self):
        agent = OpenNotesSimAgent()
        selector = agent._action_selector
        assert len(selector._function_tools) == 0

    def test_result_type_is_action_selection_result(self):
        assert action_selector.result_type == ActionSelectionResult

    def test_module_level_agent_has_no_tools(self):
        assert len(action_selector._function_tools) == 0

    def test_action_selector_is_stored_on_instance(self):
        agent = OpenNotesSimAgent()
        assert agent._action_selector is action_selector
