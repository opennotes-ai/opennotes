import inspect
from dataclasses import fields
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.simulation.agent import (
    MAX_CONTEXT_NOTES,
    MAX_CONTEXT_REQUESTS,
    MAX_PERSONALITY_CHARS,
    OpenNotesSimAgent,
    SimAgentDeps,
    _truncate_personality,
    build_instructions,
    estimate_tokens,
    pass_turn,
    rate_note,
    sim_agent,
    write_note,
)
from src.simulation.schemas import SimActionType, SimAgentAction


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_deps(mock_db):
    return SimAgentDeps(
        db=mock_db,
        community_server_id=uuid4(),
        agent_instance_id=uuid4(),
        user_profile_id=uuid4(),
        available_requests=[
            {
                "request_id": str(uuid4()),
                "content": "The earth is flat",
                "status": "PENDING",
            },
            {
                "request_id": str(uuid4()),
                "content": "Vaccines cause autism",
                "status": "PENDING",
            },
        ],
        available_notes=[
            {
                "note_id": str(uuid4()),
                "summary": "The earth is an oblate spheroid",
                "classification": "NOT_MISLEADING",
                "status": "NEEDS_MORE_RATINGS",
            },
        ],
        agent_personality="You are a skeptical fact-checker who values evidence.",
        model_name="openai:gpt-4o-mini",
    )


class TestAgentClassExists:
    def test_agent_class_exists(self):
        agent = OpenNotesSimAgent()
        assert agent is not None

    def test_agent_has_run_turn_method(self):
        agent = OpenNotesSimAgent()
        assert hasattr(agent, "run_turn")
        assert inspect.iscoroutinefunction(agent.run_turn)

    def test_agent_uses_pydantic_ai(self):
        agent = OpenNotesSimAgent()
        assert isinstance(agent._agent, Agent)

    def test_agent_accepts_custom_model(self):
        agent = OpenNotesSimAgent(model="anthropic:claude-3-haiku-20240307")
        assert agent._model == "anthropic:claude-3-haiku-20240307"

    def test_agent_default_model(self):
        agent = OpenNotesSimAgent()
        assert agent._model == "openai:gpt-4o-mini"


class TestToolsRegistered:
    def _get_tool_names(self):
        return list(sim_agent._function_tools.keys())

    def test_write_note_tool_registered(self):
        assert "write_note" in self._get_tool_names()

    def test_rate_note_tool_registered(self):
        assert "rate_note" in self._get_tool_names()

    def test_react_to_note_tool_not_registered(self):
        assert "react_to_note" not in self._get_tool_names()

    def test_pass_turn_tool_registered(self):
        assert "pass_turn" in self._get_tool_names()

    def test_three_tools_total(self):
        assert len(sim_agent._function_tools) == 3


class TestWriteNoteTool:
    @pytest.mark.asyncio
    async def test_write_note_creates_note(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        req_id = sample_deps.available_requests[0]["request_id"]
        result = await write_note(
            ctx,
            request_id=req_id,
            summary="The earth is actually round",
            classification="NOT_MISLEADING",
        )

        sample_deps.db.add.assert_called_once()
        sample_deps.db.flush.assert_awaited_once()
        note = sample_deps.db.add.call_args[0][0]
        assert note.request_id == req_id
        assert note.summary == "The earth is actually round"
        assert note.classification == "NOT_MISLEADING"
        assert note.ai_generated is True
        assert note.ai_provider == "openai:gpt-4o-mini"
        assert note.author_id == sample_deps.user_profile_id
        assert note.community_server_id == sample_deps.community_server_id
        assert "Note created" in result

    @pytest.mark.asyncio
    async def test_write_note_validates_request_id(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await write_note(
            ctx,
            request_id="nonexistent",
            summary="test",
            classification="NOT_MISLEADING",
        )

        assert "Error" in result
        assert "nonexistent" in result
        sample_deps.db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_note_validates_classification(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        req_id = sample_deps.available_requests[0]["request_id"]
        result = await write_note(
            ctx,
            request_id=req_id,
            summary="test",
            classification="INVALID",
        )

        assert "Error" in result
        assert "INVALID" in result
        sample_deps.db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_note_str_conversion_matches_uuid_request_ids(self, mock_db):
        req_uuid = uuid4()
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {"request_id": req_uuid, "content": "test", "status": "PENDING"},
            ],
            available_notes=[],
            agent_personality="test",
            model_name="test",
        )
        ctx = MagicMock()
        ctx.deps = deps

        result = await write_note(
            ctx,
            request_id=str(req_uuid),
            summary="test note",
            classification="NOT_MISLEADING",
        )

        assert "Note created" in result
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_note_handles_integrity_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        sample_deps.db.flush = AsyncMock(side_effect=IntegrityError("duplicate", {}, None))

        req_id = sample_deps.available_requests[0]["request_id"]
        result = await write_note(
            ctx,
            request_id=req_id,
            summary="test",
            classification="NOT_MISLEADING",
        )

        assert "Error" in result
        assert "integrity error" in result

    @pytest.mark.asyncio
    async def test_write_note_handles_sqlalchemy_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        sample_deps.db.flush = AsyncMock(side_effect=SQLAlchemyError("connection lost"))

        req_id = sample_deps.available_requests[0]["request_id"]
        result = await write_note(
            ctx,
            request_id=req_id,
            summary="test",
            classification="NOT_MISLEADING",
        )

        assert "Error" in result
        assert "database error" in result


class TestRateNoteTool:
    @pytest.mark.asyncio
    async def test_rate_note_creates_rating(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        note_id = sample_deps.available_notes[0]["note_id"]
        result = await rate_note(
            ctx,
            note_id=note_id,
            helpfulness_level="HELPFUL",
        )

        sample_deps.db.execute.assert_awaited_once()
        sample_deps.db.flush.assert_awaited_once()
        assert "Rated note" in result
        assert "HELPFUL" in result

    @pytest.mark.asyncio
    async def test_rate_note_validates_note_id(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await rate_note(
            ctx,
            note_id="nonexistent",
            helpfulness_level="HELPFUL",
        )

        assert "Error" in result
        assert "nonexistent" in result
        sample_deps.db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rate_note_validates_helpfulness_level(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        note_id = sample_deps.available_notes[0]["note_id"]
        result = await rate_note(
            ctx,
            note_id=note_id,
            helpfulness_level="INVALID",
        )

        assert "Error" in result
        assert "INVALID" in result
        sample_deps.db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rate_note_validates_uuid_format(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        sample_deps.available_notes.append(
            {
                "note_id": "not-a-uuid",
                "summary": "test",
                "classification": "NOT_MISLEADING",
                "status": "NEEDS_MORE_RATINGS",
            }
        )

        result = await rate_note(
            ctx,
            note_id="not-a-uuid",
            helpfulness_level="HELPFUL",
        )

        assert "Error" in result
        assert "not a valid UUID" in result
        sample_deps.db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rate_note_str_conversion_matches_uuid_note_ids(self, mock_db):
        note_uuid = uuid4()
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[
                {
                    "note_id": note_uuid,
                    "summary": "test",
                    "classification": "NOT_MISLEADING",
                    "status": "NEEDS_MORE_RATINGS",
                },
            ],
            agent_personality="test",
            model_name="test",
        )
        ctx = MagicMock()
        ctx.deps = deps

        result = await rate_note(
            ctx,
            note_id=str(note_uuid),
            helpfulness_level="HELPFUL",
        )

        assert "Rated note" in result
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rate_note_handles_integrity_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        sample_deps.db.execute = AsyncMock(side_effect=IntegrityError("fk violation", {}, None))

        note_id = sample_deps.available_notes[0]["note_id"]
        result = await rate_note(
            ctx,
            note_id=note_id,
            helpfulness_level="HELPFUL",
        )

        assert "Error" in result
        assert "integrity error" in result

    @pytest.mark.asyncio
    async def test_rate_note_handles_sqlalchemy_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        sample_deps.db.execute = AsyncMock(side_effect=SQLAlchemyError("connection lost"))

        note_id = sample_deps.available_notes[0]["note_id"]
        result = await rate_note(
            ctx,
            note_id=note_id,
            helpfulness_level="HELPFUL",
        )

        assert "Error" in result
        assert "database error" in result


class TestPassTurnTool:
    def test_pass_turn_returns_message(self):
        result = pass_turn()
        assert "Turn passed" in result
        assert "No action taken" in result


class TestInstructions:
    def test_instructions_from_personality(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        instructions = build_instructions(ctx)

        assert "skeptical fact-checker" in instructions
        assert "values evidence" in instructions

    def test_instructions_do_not_mention_react(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        instructions = build_instructions(ctx)

        assert "react_to_note" not in instructions
        assert "react to a note" not in instructions.lower()

    def test_different_personalities_different_prompts(self, mock_db):
        deps_a = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality="You are an optimistic contributor who sees the best in people.",
            model_name="openai:gpt-4o-mini",
        )
        deps_b = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality="You are a harsh critic who demands rigorous evidence.",
            model_name="openai:gpt-4o-mini",
        )

        ctx_a = MagicMock()
        ctx_a.deps = deps_a
        ctx_b = MagicMock()
        ctx_b.deps = deps_b

        instructions_a = build_instructions(ctx_a)
        instructions_b = build_instructions(ctx_b)

        assert instructions_a != instructions_b
        assert "optimistic contributor" in instructions_a
        assert "harsh critic" in instructions_b


class TestDeps:
    def test_deps_dataclass_fields(self):
        field_names = {f.name for f in fields(SimAgentDeps)}
        assert "db" in field_names
        assert "community_server_id" in field_names
        assert "agent_instance_id" in field_names
        assert "user_profile_id" in field_names
        assert "available_requests" in field_names
        assert "available_notes" in field_names
        assert "agent_personality" in field_names
        assert "model_name" in field_names

    def test_deps_available_requests_accessible(self, sample_deps):
        assert len(sample_deps.available_requests) == 2

    def test_deps_available_notes_accessible(self, sample_deps):
        assert len(sample_deps.available_notes) == 1
        assert "summary" in sample_deps.available_notes[0]


class TestOutput:
    def test_sim_agent_action_schema(self):
        action = SimAgentAction(
            action_type=SimActionType.WRITE_NOTE,
            request_id="req-001",
            summary="Test note",
            classification="NOT_MISLEADING",
            reasoning="Testing the schema",
        )
        assert action.action_type == SimActionType.WRITE_NOTE
        assert action.request_id == "req-001"
        assert action.reasoning == "Testing the schema"

    def test_action_type_enum_values(self):
        assert SimActionType.WRITE_NOTE == "write_note"
        assert SimActionType.RATE_NOTE == "rate_note"
        assert SimActionType.PASS_TURN == "pass_turn"

    def test_agent_result_type_is_sim_agent_action(self):
        assert sim_agent.result_type == SimAgentAction

    def test_pass_turn_action(self):
        action = SimAgentAction(
            action_type=SimActionType.PASS_TURN,
            reasoning="Nothing to do",
        )
        assert action.action_type == SimActionType.PASS_TURN
        assert action.request_id is None
        assert action.note_id is None

    def test_rate_note_action(self):
        action = SimAgentAction(
            action_type=SimActionType.RATE_NOTE,
            note_id="some-note-id",
            helpfulness_level="HELPFUL",
            reasoning="The note is accurate",
        )
        assert action.helpfulness_level == "HELPFUL"


class TestBuildTurnPrompt:
    def test_prompt_includes_requests(self, sample_deps):
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(sample_deps)

        req_id = sample_deps.available_requests[0]["request_id"]
        assert req_id in prompt
        assert "The earth is flat" in prompt

    def test_prompt_includes_notes(self, sample_deps):
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(sample_deps)

        assert "oblate spheroid" in prompt
        assert "NOT_MISLEADING" in prompt

    def test_prompt_does_not_mention_react(self, sample_deps):
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(sample_deps)

        assert "react to a note" not in prompt

    def test_prompt_empty_requests(self, mock_db):
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality="test",
            model_name="test",
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps)

        assert "No requests available" in prompt
        assert "No notes available" in prompt


class TestBuildTurnPromptWithLinkedNotes:
    def test_prompt_shows_linked_notes_under_request(self, mock_db):
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {
                    "request_id": "req-100",
                    "content": "Earth is flat",
                    "status": "PENDING",
                    "notes": [
                        {
                            "note_id": str(uuid4()),
                            "summary": "Earth is an oblate spheroid",
                            "classification": "MISINFORMED_OR_POTENTIALLY_MISLEADING",
                            "status": "NEEDS_MORE_RATINGS",
                        },
                        {
                            "note_id": str(uuid4()),
                            "summary": "This is not misleading",
                            "classification": "NOT_MISLEADING",
                            "status": "NEEDS_MORE_RATINGS",
                        },
                    ],
                },
            ],
            available_notes=[],
            agent_personality="test",
            model_name="test",
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps)

        assert "Existing notes (2):" in prompt
        assert "[MISINFORMED_OR_POTENTIALLY_MISLEADING] Earth is an oblate spheroid" in prompt
        assert "[NOT_MISLEADING] This is not misleading" in prompt

    def test_prompt_omits_notes_section_when_request_has_none(self, mock_db):
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {
                    "request_id": "req-200",
                    "content": "Some claim",
                    "status": "PENDING",
                    "notes": [],
                },
            ],
            available_notes=[],
            agent_personality="test",
            model_name="test",
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps)

        assert "Existing notes" not in prompt
        assert "req-200" in prompt

    def test_prompt_truncates_long_note_summaries(self, mock_db):
        long_summary = "word " * 50
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {
                    "request_id": "req-300",
                    "content": "A claim",
                    "status": "PENDING",
                    "notes": [
                        {
                            "note_id": str(uuid4()),
                            "summary": long_summary,
                            "classification": "NOT_MISLEADING",
                            "status": "NEEDS_MORE_RATINGS",
                        },
                    ],
                },
            ],
            available_notes=[],
            agent_personality="test",
            model_name="test",
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps)

        assert "Existing notes (1):" in prompt
        assert long_summary not in prompt
        assert "..." in prompt

    def test_format_sections_handles_missing_notes_key(self, mock_db):
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {
                    "request_id": "req-400",
                    "content": "Old format request",
                    "status": "PENDING",
                },
            ],
            available_notes=[],
            agent_personality="test",
            model_name="test",
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps)

        assert "req-400" in prompt
        assert "Existing notes" not in prompt


class TestRunTurnWithTestModel:
    @pytest.mark.asyncio
    async def test_run_turn_returns_action_and_messages(self, sample_deps):
        agent = OpenNotesSimAgent()
        m = TestModel()
        with sim_agent.override(model=m):
            action, messages = await agent.run_turn(sample_deps)

        assert isinstance(action, SimAgentAction)
        assert isinstance(messages, list)
        assert len(messages) > 0

    @pytest.mark.asyncio
    async def test_run_turn_respects_model_override(self, sample_deps):
        agent = OpenNotesSimAgent(model="test")
        m = TestModel()
        with sim_agent.override(model=m):
            action, _messages = await agent.run_turn(sample_deps)

        assert isinstance(action, SimAgentAction)


class TestEstimateTokens:
    def test_short_text(self):
        assert estimate_tokens("hello") == 2

    def test_empty_text(self):
        assert estimate_tokens("") == 1

    def test_longer_text(self):
        text = "a" * 400
        assert estimate_tokens(text) == 101


class TestTruncatePersonality:
    def test_short_personality_unchanged(self):
        short = "You are a fact-checker."
        assert _truncate_personality(short) == short

    def test_long_personality_truncated(self):
        long_text = "word " * 200
        result = _truncate_personality(long_text)
        assert len(result) <= MAX_PERSONALITY_CHARS + 3
        assert result.endswith("...")

    def test_truncates_at_word_boundary(self):
        text = "a" * 498 + " longword"
        result = _truncate_personality(text)
        assert result.endswith("...")
        assert "longword" not in result

    def test_exact_limit_unchanged(self):
        text = "x" * MAX_PERSONALITY_CHARS
        assert _truncate_personality(text) == text


class TestBuildInstructionsPersonalityCap:
    def test_long_personality_is_truncated_in_instructions(self, mock_db):
        long_personality = "word " * 200
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality=long_personality,
            model_name="openai:gpt-4o-mini",
        )
        ctx = MagicMock()
        ctx.deps = deps

        instructions = build_instructions(ctx)

        assert long_personality not in instructions
        assert "..." in instructions


class TestBuildTurnPromptTokenBudget:
    def test_limits_requests_to_max(self, mock_db):
        many_requests = [
            {"request_id": str(uuid4()), "content": f"Content {i}", "status": "PENDING"}
            for i in range(20)
        ]
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=many_requests,
            available_notes=[],
            agent_personality="test",
            model_name="test",
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps)

        request_count = prompt.count("Request ID:")
        assert request_count <= MAX_CONTEXT_REQUESTS

    def test_limits_notes_to_max(self, mock_db):
        many_notes = [
            {
                "note_id": str(uuid4()),
                "summary": f"Summary {i}",
                "classification": "NOT_MISLEADING",
                "status": "NEEDS_MORE_RATINGS",
            }
            for i in range(20)
        ]
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=many_notes,
            agent_personality="test",
            model_name="test",
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps)

        note_count = prompt.count("Note ID:")
        assert note_count <= MAX_CONTEXT_NOTES

    def test_trims_when_over_token_budget(self, mock_db):
        huge_requests = [
            {"request_id": str(uuid4()), "content": "x" * 5000, "status": "PENDING"}
            for _ in range(5)
        ]
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=huge_requests,
            available_notes=[],
            agent_personality="test",
            model_name="test",
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps, token_budget=1000)

        assert estimate_tokens(prompt) <= 1000

    def test_fresh_turn_under_5000_tokens(self, mock_db):
        requests = [
            {
                "request_id": str(uuid4()),
                "content": f"Some content about topic {i}",
                "status": "PENDING",
            }
            for i in range(5)
        ]
        notes = [
            {
                "note_id": str(uuid4()),
                "summary": f"A note summary about topic {i}",
                "classification": "NOT_MISLEADING",
                "status": "NEEDS_MORE_RATINGS",
            }
            for i in range(5)
        ]
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=requests,
            available_notes=notes,
            agent_personality="You are a skeptical fact-checker who values evidence.",
            model_name="openai:gpt-4o-mini",
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps)

        ctx = MagicMock()
        ctx.deps = deps
        system_prompt = build_instructions(ctx)

        total_tokens = estimate_tokens(prompt) + estimate_tokens(system_prompt)
        assert total_tokens < 5000

    def test_samples_different_items_when_many_available(self, mock_db):
        many_requests = [
            {"request_id": str(uuid4()), "content": f"Content {i}", "status": "PENDING"}
            for i in range(50)
        ]
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=many_requests,
            available_notes=[],
            agent_personality="test",
            model_name="test",
        )
        agent = OpenNotesSimAgent()

        prompts = set()
        for _ in range(10):
            prompt = agent._build_turn_prompt(deps)
            prompts.add(prompt)

        assert len(prompts) > 1
