import inspect
from uuid import uuid4

import pytest

from src.simulation.agent import OpenNotesSimAgent, estimate_tokens
from src.simulation.schemas import SimActionType


@pytest.fixture
def sample_requests():
    return [
        {
            "request_id": str(uuid4()),
            "content": "Earth is flat claim",
            "status": "PENDING",
            "notes": [],
        },
        {
            "request_id": str(uuid4()),
            "content": "Vaccine myths",
            "status": "PENDING",
            "notes": [],
        },
    ]


@pytest.fixture
def sample_notes():
    return [
        {
            "note_id": str(uuid4()),
            "summary": "Earth is round per NASA",
            "classification": "NOT_MISLEADING",
            "status": "NEEDS_MORE_RATINGS",
        },
        {
            "note_id": str(uuid4()),
            "summary": "Vaccines are safe per WHO",
            "classification": "NOT_MISLEADING",
            "status": "NEEDS_MORE_RATINGS",
        },
    ]


class TestPhase2PromptFiltering:
    def test_write_note_prompt_shows_only_requests(self, sample_requests, sample_notes):
        agent = OpenNotesSimAgent()
        prompt = agent._build_phase2_prompt(SimActionType.WRITE_NOTE, sample_requests, sample_notes)
        assert "Earth is flat" in prompt
        assert "Vaccine myths" in prompt
        assert "Earth is round per NASA" not in prompt
        assert "Vaccines are safe per WHO" not in prompt

    def test_rate_note_prompt_shows_only_notes(self, sample_requests, sample_notes):
        agent = OpenNotesSimAgent()
        prompt = agent._build_phase2_prompt(SimActionType.RATE_NOTE, sample_requests, sample_notes)
        assert "Earth is round per NASA" in prompt
        assert "Vaccines are safe per WHO" in prompt
        assert "Earth is flat" not in prompt
        assert "Vaccine myths" not in prompt

    def test_pass_turn_returns_simple_message(self, sample_requests, sample_notes):
        agent = OpenNotesSimAgent()
        prompt = agent._build_phase2_prompt(SimActionType.PASS_TURN, sample_requests, sample_notes)
        assert "pass" in prompt.lower()

    def test_write_note_with_empty_requests_still_works(self, sample_notes):
        agent = OpenNotesSimAgent()
        prompt = agent._build_phase2_prompt(SimActionType.WRITE_NOTE, [], sample_notes)
        assert "No requests available" in prompt

    def test_rate_note_with_empty_notes_still_works(self, sample_requests):
        agent = OpenNotesSimAgent()
        prompt = agent._build_phase2_prompt(SimActionType.RATE_NOTE, sample_requests, [])
        assert "No notes available" in prompt

    def test_write_note_prompt_has_action_specific_instruction(self, sample_requests, sample_notes):
        agent = OpenNotesSimAgent()
        prompt = agent._build_phase2_prompt(SimActionType.WRITE_NOTE, sample_requests, sample_notes)
        assert "write" in prompt.lower()

    def test_rate_note_prompt_has_action_specific_instruction(self, sample_requests, sample_notes):
        agent = OpenNotesSimAgent()
        prompt = agent._build_phase2_prompt(SimActionType.RATE_NOTE, sample_requests, sample_notes)
        assert "rate" in prompt.lower()


class TestPhase2PromptTokenBudget:
    def test_trims_requests_when_over_budget(self):
        agent = OpenNotesSimAgent()
        huge_requests = [
            {
                "request_id": str(uuid4()),
                "content": "x" * 5000,
                "status": "PENDING",
                "notes": [],
            }
            for _ in range(5)
        ]
        prompt = agent._build_phase2_prompt(
            SimActionType.WRITE_NOTE, huge_requests, [], token_budget=1000
        )
        assert estimate_tokens(prompt) <= 1000

    def test_trims_notes_when_over_budget(self):
        agent = OpenNotesSimAgent()
        huge_notes = [
            {
                "note_id": str(uuid4()),
                "summary": "x" * 5000,
                "classification": "NOT_MISLEADING",
                "status": "NEEDS_MORE_RATINGS",
            }
            for _ in range(5)
        ]
        prompt = agent._build_phase2_prompt(
            SimActionType.RATE_NOTE, [], huge_notes, token_budget=1000
        )
        assert estimate_tokens(prompt) <= 1000

    def test_samples_requests_when_many_available(self):
        agent = OpenNotesSimAgent()
        many_requests = [
            {
                "request_id": str(uuid4()),
                "content": f"Content {i}",
                "status": "PENDING",
                "notes": [],
            }
            for i in range(50)
        ]
        prompt = agent._build_phase2_prompt(SimActionType.WRITE_NOTE, many_requests, [])
        request_count = prompt.count("Request ID:")
        from src.simulation.agent import MAX_CONTEXT_REQUESTS

        assert request_count <= MAX_CONTEXT_REQUESTS

    def test_samples_notes_when_many_available(self):
        agent = OpenNotesSimAgent()
        many_notes = [
            {
                "note_id": str(uuid4()),
                "summary": f"Summary {i}",
                "classification": "NOT_MISLEADING",
                "status": "NEEDS_MORE_RATINGS",
            }
            for i in range(50)
        ]
        prompt = agent._build_phase2_prompt(SimActionType.RATE_NOTE, [], many_notes)
        note_count = prompt.count("Note ID:")
        from src.simulation.agent import MAX_CONTEXT_NOTES

        assert note_count <= MAX_CONTEXT_NOTES


class TestRunTurnWithActionType:
    def test_run_turn_accepts_chosen_action_type(self):
        agent = OpenNotesSimAgent()
        sig = inspect.signature(agent.run_turn)
        assert "chosen_action_type" in sig.parameters

    def test_run_turn_without_action_type_uses_full_prompt(self):
        agent = OpenNotesSimAgent()
        sig = inspect.signature(agent.run_turn)
        param = sig.parameters["chosen_action_type"]
        assert param.default is None
