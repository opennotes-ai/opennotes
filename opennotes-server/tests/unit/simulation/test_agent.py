import inspect
import logging
from dataclasses import fields
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic_ai import Agent, WebSearchTool
from pydantic_ai.models.test import TestModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.llm_config.model_id import ModelId
from src.simulation.agent import (
    MAX_CONTEXT_NOTES,
    MAX_CONTEXT_REQUESTS,
    MAX_PERSONALITY_CHARS,
    MAX_RATE_NOTES_BATCH,
    WEBSEARCH_SUPPORTED_PROVIDERS,
    OpenNotesSimAgent,
    SimAgentDeps,
    _is_research_available,
    _truncate_personality,
    action_selector,
    build_action_selector_instructions,
    build_instructions,
    estimate_tokens,
    list_requests,
    pass_turn,
    rate_notes,
    sim_agent,
    write_note,
)
from src.simulation.schemas import RatedNoteEntry, SimActionType, SimAgentAction

_TEST_MODEL_ID = ModelId.from_pydantic_ai("openai:gpt-4o-mini")
_GENERIC_MODEL_ID = ModelId.from_pydantic_ai("test:model")


def _make_nested_ctx():
    nested = AsyncMock()
    nested.__aenter__ = AsyncMock(return_value=None)
    nested.__aexit__ = AsyncMock(return_value=False)
    return nested


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one.return_value = 0
    db.execute = AsyncMock(return_value=mock_result)
    db.begin_nested = MagicMock(side_effect=lambda: _make_nested_ctx())
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
                "id": str(uuid4()),
                "request_id": "playground-wf001-0",
                "content": "The earth is flat",
                "status": "PENDING",
            },
            {
                "id": str(uuid4()),
                "request_id": "playground-wf002-0",
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
        model_name=_TEST_MODEL_ID,
        tool_config=None,
        simulation_run_id=uuid4(),
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
        model = ModelId.from_pydantic_ai("anthropic:claude-3-haiku-20240307")
        agent = OpenNotesSimAgent(model=model)
        assert agent._model == model

    def test_agent_default_model(self):
        agent = OpenNotesSimAgent()
        assert agent._model == _TEST_MODEL_ID


class TestToolsRegistered:
    def _get_tool_names(self):
        return list(sim_agent._function_toolset.tools.keys())

    def test_write_note_tool_registered(self):
        assert "write_note" in self._get_tool_names()

    def test_rate_notes_tool_registered(self):
        assert "rate_notes" in self._get_tool_names()

    def test_react_to_note_tool_not_registered(self):
        assert "react_to_note" not in self._get_tool_names()

    def test_pass_turn_tool_registered(self):
        assert "pass_turn" in self._get_tool_names()

    def test_six_tools_total(self):
        assert len(sim_agent._function_toolset.tools) == 6


class TestWriteNoteTool:
    @pytest.mark.asyncio
    async def test_write_note_creates_note(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        req_id = sample_deps.available_requests[0]["id"]
        result = await write_note(
            ctx,
            request_id=req_id,
            summary="The earth is actually round",
            classification="NOT_MISLEADING",
        )

        sample_deps.db.add.assert_called_once()
        sample_deps.db.flush.assert_awaited_once()
        note = sample_deps.db.add.call_args[0][0]
        assert note.request_id == UUID(req_id)
        assert note.summary == "The earth is actually round"
        assert note.classification == "NOT_MISLEADING"
        assert note.ai_generated is True
        assert note.ai_provider == "openai"
        assert note.ai_model == "gpt-4o-mini"
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

        req_id = sample_deps.available_requests[0]["id"]
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
                {
                    "id": req_uuid,
                    "request_id": "provenance-str",
                    "content": "test",
                    "status": "PENDING",
                },
            ],
            available_notes=[],
            agent_personality="test",
            model_name=_GENERIC_MODEL_ID,
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
        note = mock_db.add.call_args[0][0]
        assert note.request_id == req_uuid

    @pytest.mark.asyncio
    async def test_write_note_handles_integrity_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        sample_deps.db.flush = AsyncMock(side_effect=IntegrityError("duplicate", {}, None))

        req_id = sample_deps.available_requests[0]["id"]
        result = await write_note(
            ctx,
            request_id=req_id,
            summary="test",
            classification="NOT_MISLEADING",
        )

        assert result == "Error: could not create note due to a constraint violation."

    @pytest.mark.asyncio
    async def test_write_note_handles_sqlalchemy_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        sample_deps.db.flush = AsyncMock(side_effect=SQLAlchemyError("connection lost"))

        req_id = sample_deps.available_requests[0]["id"]
        result = await write_note(
            ctx,
            request_id=req_id,
            summary="test",
            classification="NOT_MISLEADING",
        )

        assert result == "Error: could not create note due to a database error."

    @pytest.mark.asyncio
    async def test_write_note_integrity_error_does_not_leak_details(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        sample_deps.db.flush = AsyncMock(
            side_effect=IntegrityError("ix_notes_author_request", {}, None)
        )

        req_id = sample_deps.available_requests[0]["id"]
        result = await write_note(
            ctx,
            request_id=req_id,
            summary="test",
            classification="NOT_MISLEADING",
        )

        assert "ix_notes_author_request" not in result

    @pytest.mark.asyncio
    async def test_write_note_rolls_back_on_integrity_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        sample_deps.db.flush = AsyncMock(side_effect=IntegrityError("duplicate", {}, None))
        sample_deps.db.rollback = AsyncMock()

        req_id = sample_deps.available_requests[0]["id"]
        await write_note(ctx, request_id=req_id, summary="test", classification="NOT_MISLEADING")

        sample_deps.db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_note_rolls_back_on_sqlalchemy_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        sample_deps.db.flush = AsyncMock(side_effect=SQLAlchemyError("connection lost"))
        sample_deps.db.rollback = AsyncMock()

        req_id = sample_deps.available_requests[0]["id"]
        await write_note(ctx, request_id=req_id, summary="test", classification="NOT_MISLEADING")

        sample_deps.db.rollback.assert_awaited_once()


class TestRateNotesTool:
    @pytest.mark.asyncio
    async def test_rate_notes_single_rating(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        note_id = sample_deps.available_notes[0]["note_id"]
        result = await rate_notes(
            ctx,
            ratings=[{"note_id": note_id, "helpfulness_level": "HELPFUL"}],
        )

        sample_deps.db.execute.assert_awaited_once()
        sample_deps.db.flush.assert_awaited_once()
        assert "Rated note" in result
        assert "HELPFUL" in result

    @pytest.mark.asyncio
    async def test_rate_notes_batch_of_five(self, mock_db):
        note_ids = [str(uuid4()) for _ in range(5)]
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[
                {
                    "note_id": nid,
                    "summary": f"Note {i}",
                    "classification": "NOT_MISLEADING",
                    "status": "NEEDS_MORE_RATINGS",
                }
                for i, nid in enumerate(note_ids)
            ],
            agent_personality="test",
            model_name=_GENERIC_MODEL_ID,
        )
        ctx = MagicMock()
        ctx.deps = deps

        ratings_input = [{"note_id": nid, "helpfulness_level": "HELPFUL"} for nid in note_ids]
        result = await rate_notes(ctx, ratings=ratings_input)

        assert mock_db.execute.await_count == 5
        assert mock_db.flush.await_count == 5
        for nid in note_ids:
            assert nid in result

    @pytest.mark.asyncio
    async def test_rate_notes_batch_over_five_rejected(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        ratings_input = [
            {"note_id": str(uuid4()), "helpfulness_level": "HELPFUL"} for _ in range(6)
        ]
        result = await rate_notes(ctx, ratings=ratings_input)

        assert "Error" in result
        assert str(MAX_RATE_NOTES_BATCH) in result
        sample_deps.db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rate_notes_empty_batch_rejected(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await rate_notes(ctx, ratings=[])

        assert "Error" in result
        sample_deps.db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rate_notes_mixed_valid_invalid(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        valid_note_id = sample_deps.available_notes[0]["note_id"]
        invalid_note_id = "nonexistent"

        result = await rate_notes(
            ctx,
            ratings=[
                {"note_id": valid_note_id, "helpfulness_level": "HELPFUL"},
                {"note_id": invalid_note_id, "helpfulness_level": "HELPFUL"},
            ],
        )

        assert "Rated note" in result
        assert valid_note_id in result
        assert "Error" in result
        assert "nonexistent" in result
        sample_deps.db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rate_notes_invalid_helpfulness_level(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        note_id = sample_deps.available_notes[0]["note_id"]
        result = await rate_notes(
            ctx,
            ratings=[{"note_id": note_id, "helpfulness_level": "INVALID"}],
        )

        assert "Error" in result
        assert "INVALID" in result
        sample_deps.db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rate_notes_duplicate_note_ids(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        note_id = sample_deps.available_notes[0]["note_id"]
        result = await rate_notes(
            ctx,
            ratings=[
                {"note_id": note_id, "helpfulness_level": "HELPFUL"},
                {"note_id": note_id, "helpfulness_level": "NOT_HELPFUL"},
            ],
        )

        assert sample_deps.db.execute.await_count == 2
        assert result.count("Rated note") == 2

    @pytest.mark.asyncio
    async def test_rate_notes_validates_uuid_format(self, sample_deps):
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

        result = await rate_notes(
            ctx,
            ratings=[{"note_id": "not-a-uuid", "helpfulness_level": "HELPFUL"}],
        )

        assert "Error" in result
        assert "not a valid UUID" in result
        sample_deps.db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rate_notes_handles_integrity_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        nested_ctx = AsyncMock()
        nested_ctx.__aenter__ = AsyncMock(side_effect=IntegrityError("fk violation", {}, None))
        nested_ctx.__aexit__ = AsyncMock(return_value=False)
        sample_deps.db.begin_nested = MagicMock(return_value=nested_ctx)

        note_id = sample_deps.available_notes[0]["note_id"]
        result = await rate_notes(
            ctx,
            ratings=[{"note_id": note_id, "helpfulness_level": "HELPFUL"}],
        )

        assert "constraint violation" in result

    @pytest.mark.asyncio
    async def test_rate_notes_handles_sqlalchemy_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        nested_ctx = AsyncMock()
        nested_ctx.__aenter__ = AsyncMock(side_effect=SQLAlchemyError("connection lost"))
        nested_ctx.__aexit__ = AsyncMock(return_value=False)
        sample_deps.db.begin_nested = MagicMock(return_value=nested_ctx)

        note_id = sample_deps.available_notes[0]["note_id"]
        result = await rate_notes(
            ctx,
            ratings=[{"note_id": note_id, "helpfulness_level": "HELPFUL"}],
        )

        assert "database error" in result

    @pytest.mark.asyncio
    async def test_rate_notes_mid_batch_error_preserves_earlier_ratings(self, mock_db):
        note_ids = [str(uuid4()) for _ in range(3)]
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[
                {
                    "note_id": nid,
                    "summary": f"Note {i}",
                    "classification": "NOT_MISLEADING",
                    "status": "NEEDS_MORE_RATINGS",
                }
                for i, nid in enumerate(note_ids)
            ],
            agent_personality="test",
            model_name=_GENERIC_MODEL_ID,
        )
        ctx = MagicMock()
        ctx.deps = deps

        call_count = 0

        def _begin_nested_side_effect():
            nonlocal call_count
            call_count += 1
            nested = AsyncMock()
            if call_count == 2:
                nested.__aenter__ = AsyncMock(side_effect=IntegrityError("fk violation", {}, None))
            else:
                nested.__aenter__ = AsyncMock()
            nested.__aexit__ = AsyncMock(return_value=False)
            return nested

        mock_db.begin_nested = MagicMock(side_effect=_begin_nested_side_effect)

        result = await rate_notes(
            ctx,
            ratings=[
                {"note_id": note_ids[0], "helpfulness_level": "HELPFUL"},
                {"note_id": note_ids[1], "helpfulness_level": "HELPFUL"},
                {"note_id": note_ids[2], "helpfulness_level": "HELPFUL"},
            ],
        )

        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert "Rated note" in lines[0]
        assert note_ids[0] in lines[0]
        assert "constraint violation" in lines[1]
        assert note_ids[1] in lines[1]
        assert "Rated note" in lines[2]
        assert note_ids[2] in lines[2]


class TestRateNotesFullTurn:
    @pytest.mark.asyncio
    async def test_full_rate_notes_turn_multiple_notes(self, mock_db):
        note_ids = [str(uuid4()) for _ in range(3)]
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[
                {
                    "note_id": nid,
                    "summary": f"Note {i}",
                    "classification": "NOT_MISLEADING",
                    "status": "NEEDS_MORE_RATINGS",
                }
                for i, nid in enumerate(note_ids)
            ],
            agent_personality="You rate notes carefully.",
            model_name=_GENERIC_MODEL_ID,
        )
        ctx = MagicMock()
        ctx.deps = deps

        levels = ["HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL"]
        ratings_input = [
            {"note_id": nid, "helpfulness_level": levels[i]} for i, nid in enumerate(note_ids)
        ]
        result = await rate_notes(ctx, ratings=ratings_input)

        assert mock_db.execute.await_count == 3
        assert mock_db.flush.await_count == 3
        for nid in note_ids:
            assert nid in result
        for level in levels:
            assert level in result
        assert result.count("Rated note") == 3


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
            model_name=_TEST_MODEL_ID,
        )
        deps_b = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality="You are a harsh critic who demands rigorous evidence.",
            model_name=_TEST_MODEL_ID,
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

    def test_instructions_include_channel_tools_when_simulation_run_id_set(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        instructions = build_instructions(ctx)

        assert "post_to_channel" in instructions
        assert "read_channel" in instructions

    def test_instructions_omit_channel_tools_when_no_simulation_run_id(self, mock_db):
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality="test",
            model_name=_TEST_MODEL_ID,
            simulation_run_id=None,
        )
        ctx = MagicMock()
        ctx.deps = deps

        instructions = build_instructions(ctx)

        assert "post_to_channel" not in instructions
        assert "read_channel" not in instructions


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
        assert "simulation_run_id" in field_names

    def test_deps_model_name_is_model_id(self, sample_deps):
        assert isinstance(sample_deps.model_name, ModelId)

    def test_deps_available_requests_accessible(self, sample_deps):
        assert len(sample_deps.available_requests) == 2

    def test_deps_available_notes_accessible(self, sample_deps):
        assert len(sample_deps.available_notes) == 1
        assert "summary" in sample_deps.available_notes[0]


class TestOutput:
    def test_sim_agent_action_schema(self):
        test_uuid = UUID("01936b43-8b5a-7000-8000-000000000001")
        action = SimAgentAction(
            action_type=SimActionType.WRITE_NOTE,
            request_id=test_uuid,
            summary="Test note",
            classification="NOT_MISLEADING",
            reasoning="Testing the schema",
        )
        assert action.action_type == SimActionType.WRITE_NOTE
        assert action.request_id == test_uuid
        assert action.reasoning == "Testing the schema"

    def test_action_type_enum_values(self):
        assert SimActionType.WRITE_NOTE == "write_note"
        assert SimActionType.RATE_NOTE == "rate_note"
        assert SimActionType.PASS_TURN == "pass_turn"

    def test_agent_result_type_is_sim_agent_action(self):
        assert sim_agent.output_type == SimAgentAction

    def test_pass_turn_action(self):
        action = SimAgentAction(
            action_type=SimActionType.PASS_TURN,
            reasoning="Nothing to do",
        )
        assert action.action_type == SimActionType.PASS_TURN
        assert action.request_id is None
        assert action.rated_notes == []

    def test_rate_note_action(self):
        action = SimAgentAction(
            action_type=SimActionType.RATE_NOTE,
            rated_notes=[RatedNoteEntry(note_id="some-note-id", helpfulness_level="HELPFUL")],
            reasoning="The note is accurate",
        )
        assert action.rated_notes[0].helpfulness_level == "HELPFUL"


class TestBuildTurnPrompt:
    def test_prompt_includes_requests(self, sample_deps):
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(sample_deps)

        req_id = sample_deps.available_requests[0]["id"]
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
            model_name=_GENERIC_MODEL_ID,
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps)

        assert "No requests available" in prompt
        assert "No notes available" in prompt


class TestBuildTurnPromptWithLinkedNotes:
    def test_prompt_shows_linked_notes_under_request(self, mock_db):
        req_id = str(uuid4())
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {
                    "id": req_id,
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
        req_id = str(uuid4())
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {
                    "id": req_id,
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
        assert req_id in prompt

    def test_prompt_truncates_long_note_summaries(self, mock_db):
        long_summary = "word " * 50
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {
                    "id": str(uuid4()),
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
        req_id = str(uuid4())
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {
                    "id": req_id,
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

        assert req_id in prompt
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
        agent = OpenNotesSimAgent(model=_GENERIC_MODEL_ID)
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
            model_name=_TEST_MODEL_ID,
        )
        ctx = MagicMock()
        ctx.deps = deps

        instructions = build_instructions(ctx)

        assert long_personality not in instructions
        assert "..." in instructions


class TestBuildTurnPromptTokenBudget:
    def test_limits_requests_to_max(self, mock_db):
        many_requests = [
            {
                "id": str(uuid4()),
                "request_id": f"prov-{i}",
                "content": f"Content {i}",
                "status": "PENDING",
            }
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
            model_name=_GENERIC_MODEL_ID,
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
            model_name=_GENERIC_MODEL_ID,
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps)

        note_count = prompt.count("Note ID:")
        assert note_count <= MAX_CONTEXT_NOTES

    def test_trims_when_over_token_budget(self, mock_db):
        huge_requests = [
            {
                "id": str(uuid4()),
                "request_id": f"prov-{i}",
                "content": "x" * 5000,
                "status": "PENDING",
            }
            for i in range(5)
        ]
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=huge_requests,
            available_notes=[],
            agent_personality="test",
            model_name=_GENERIC_MODEL_ID,
        )
        agent = OpenNotesSimAgent()
        prompt = agent._build_turn_prompt(deps, token_budget=1000)

        assert estimate_tokens(prompt) <= 1000

    def test_fresh_turn_under_5000_tokens(self, mock_db):
        requests = [
            {
                "id": str(uuid4()),
                "request_id": f"prov-{i}",
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
            model_name=_TEST_MODEL_ID,
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
            {
                "id": str(uuid4()),
                "request_id": f"prov-{i}",
                "content": f"Content {i}",
                "status": "PENDING",
            }
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
            model_name=_GENERIC_MODEL_ID,
        )
        agent = OpenNotesSimAgent()

        prompts = set()
        for _ in range(10):
            prompt = agent._build_turn_prompt(deps)
            prompts.add(prompt)

        assert len(prompts) > 1


class TestWebSearchToolGating:
    def test_sim_agent_has_no_builtin_tools(self):
        assert len(sim_agent._builtin_tools) == 0

    def test_sim_agent_has_no_prepare_tools(self):
        assert sim_agent._prepare_tools is None

    def test_websearch_supported_providers_is_frozenset(self):
        assert isinstance(WEBSEARCH_SUPPORTED_PROVIDERS, frozenset)
        assert "anthropic" in WEBSEARCH_SUPPORTED_PROVIDERS
        assert "google" in WEBSEARCH_SUPPORTED_PROVIDERS
        assert "groq" in WEBSEARCH_SUPPORTED_PROVIDERS
        assert "openai" not in WEBSEARCH_SUPPORTED_PROVIDERS

    @pytest.mark.asyncio
    async def test_run_turn_passes_websearch_when_enabled_and_supported(self, mock_db):
        from unittest.mock import patch

        supported_model = ModelId.from_pydantic_ai("anthropic:claude-3-haiku-20240307")
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {"id": str(uuid4()), "request_id": "prov-0", "content": "test", "status": "PENDING"}
            ],
            available_notes=[],
            agent_personality="test",
            model_name=supported_model,
            tool_config={"research_enabled": True},
        )

        mock_action = SimAgentAction(action_type=SimActionType.PASS_TURN, reasoning="test")
        mock_result = MagicMock()
        mock_result.output = mock_action
        mock_result.all_messages.return_value = []

        captured_kwargs: dict = {}

        async def capture_run(prompt, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_result

        agent = OpenNotesSimAgent(model=supported_model)
        with patch.object(agent._agent, "run", side_effect=capture_run):
            await agent.run_turn(deps)

        assert "builtin_tools" in captured_kwargs
        assert any(isinstance(t, WebSearchTool) for t in captured_kwargs["builtin_tools"])

    @pytest.mark.asyncio
    async def test_run_turn_skips_websearch_when_disabled(self, mock_db):
        from unittest.mock import patch

        supported_model = ModelId.from_pydantic_ai("anthropic:claude-3-haiku-20240307")
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {"id": str(uuid4()), "request_id": "prov-0", "content": "test", "status": "PENDING"}
            ],
            available_notes=[],
            agent_personality="test",
            model_name=supported_model,
            tool_config=None,
        )

        mock_action = SimAgentAction(action_type=SimActionType.PASS_TURN, reasoning="test")
        mock_result = MagicMock()
        mock_result.output = mock_action
        mock_result.all_messages.return_value = []

        captured_kwargs: dict = {}

        async def capture_run(prompt, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_result

        agent = OpenNotesSimAgent(model=supported_model)
        with patch.object(agent._agent, "run", side_effect=capture_run):
            await agent.run_turn(deps)

        assert "builtin_tools" not in captured_kwargs

    @pytest.mark.asyncio
    async def test_run_turn_skips_websearch_for_unsupported_provider_and_logs(
        self, mock_db, caplog
    ):
        from unittest.mock import patch

        unsupported_model = ModelId.from_pydantic_ai("openai:gpt-4o-mini")
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[
                {"id": str(uuid4()), "request_id": "prov-0", "content": "test", "status": "PENDING"}
            ],
            available_notes=[],
            agent_personality="test",
            model_name=unsupported_model,
            tool_config={"research_enabled": True},
        )

        mock_action = SimAgentAction(action_type=SimActionType.PASS_TURN, reasoning="test")
        mock_result = MagicMock()
        mock_result.output = mock_action
        mock_result.all_messages.return_value = []

        captured_kwargs: dict = {}

        async def capture_run(prompt, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_result

        agent = OpenNotesSimAgent(model=unsupported_model)
        with (
            caplog.at_level(logging.WARNING, logger="src.simulation.agent"),
            patch.object(agent._agent, "run", side_effect=capture_run),
        ):
            await agent.run_turn(deps)

        assert "builtin_tools" not in captured_kwargs
        assert any("not supported" in r.message for r in caplog.records)


class TestResearchPrompts:
    _SUPPORTED_MODEL_ID = ModelId.from_pydantic_ai("anthropic:claude-3-haiku-20240307")

    def _make_ctx(self, tool_config=None):
        deps = SimAgentDeps(
            db=MagicMock(),
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality="Test personality",
            model_name=self._SUPPORTED_MODEL_ID,
            tool_config=tool_config,
        )
        ctx = MagicMock()
        ctx.deps = deps
        return ctx

    def test_instructions_include_research_when_enabled(self):
        ctx = self._make_ctx(tool_config={"research_enabled": True})
        result = build_instructions(ctx)
        assert "web search" in result.lower()
        assert "research" in result.lower()

    def test_instructions_omit_research_when_disabled(self):
        ctx = self._make_ctx(tool_config=None)
        result = build_instructions(ctx)
        assert "web search" not in result.lower()

    def test_instructions_omit_research_when_false(self):
        ctx = self._make_ctx(tool_config={"research_enabled": False})
        result = build_instructions(ctx)
        assert "web search" not in result.lower()

    def test_instructions_mention_memory_persistence(self):
        ctx = self._make_ctx(tool_config={"research_enabled": True})
        result = build_instructions(ctx)
        assert "future turns" in result.lower() or "memory" in result.lower()

    def test_action_selector_includes_research_when_enabled(self):
        ctx = self._make_ctx(tool_config={"research_enabled": True})
        result = build_action_selector_instructions(ctx)
        assert "web search" in result.lower() or "research" in result.lower()

    def test_action_selector_omits_research_when_disabled(self):
        ctx = self._make_ctx(tool_config=None)
        result = build_action_selector_instructions(ctx)
        assert "web search" not in result.lower()

    def test_existing_prompt_unchanged_without_research(self):
        ctx = self._make_ctx(tool_config=None)
        result = build_instructions(ctx)
        assert "Community Notes participant" in result
        assert "write_note" in result
        assert "rate_note" in result
        assert "pass_turn" in result


class TestIsResearchAvailable:
    def _make_deps(self, provider: str, tool_config=None):
        return SimAgentDeps(
            db=MagicMock(),
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality="Test",
            model_name=ModelId.from_pydantic_ai(f"{provider}:test-model"),
            tool_config=tool_config,
        )

    def test_true_for_supported_provider_with_research_enabled(self):
        deps = self._make_deps("anthropic", tool_config={"research_enabled": True})
        assert _is_research_available(deps) is True

    def test_false_for_unsupported_provider_with_research_enabled(self):
        deps = self._make_deps("openai", tool_config={"research_enabled": True})
        assert _is_research_available(deps) is False

    def test_false_when_research_disabled(self):
        deps = self._make_deps("anthropic", tool_config={"research_enabled": False})
        assert _is_research_available(deps) is False

    def test_false_when_tool_config_none(self):
        deps = self._make_deps("anthropic", tool_config=None)
        assert _is_research_available(deps) is False

    def test_all_supported_providers(self):
        for provider in ("anthropic", "google", "groq"):
            deps = self._make_deps(provider, tool_config={"research_enabled": True})
            assert _is_research_available(deps) is True


class TestResearchPromptsUnsupportedProvider:
    def _make_ctx(self, provider: str, tool_config=None):
        deps = SimAgentDeps(
            db=MagicMock(),
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality="Test personality",
            model_name=ModelId.from_pydantic_ai(f"{provider}:test-model"),
            tool_config=tool_config,
        )
        ctx = MagicMock()
        ctx.deps = deps
        return ctx

    def test_instructions_omit_research_for_unsupported_provider(self):
        ctx = self._make_ctx("openai", tool_config={"research_enabled": True})
        result = build_instructions(ctx)
        assert "web search" not in result.lower()

    def test_action_selector_omits_research_for_unsupported_provider(self):
        ctx = self._make_ctx("openai", tool_config={"research_enabled": True})
        result = build_action_selector_instructions(ctx)
        assert "web search" not in result.lower()

    def test_instructions_include_research_for_supported_provider(self):
        ctx = self._make_ctx("anthropic", tool_config={"research_enabled": True})
        result = build_instructions(ctx)
        assert "web search" in result.lower()

    def test_action_selector_includes_research_for_supported_provider(self):
        ctx = self._make_ctx("anthropic", tool_config={"research_enabled": True})
        result = build_action_selector_instructions(ctx)
        assert "web search" in result.lower()


class TestAgentRetryConfiguration:
    def test_sim_agent_has_retries_3(self):
        assert sim_agent._max_result_retries == 3

    def test_action_selector_has_retries_3(self):
        assert action_selector._max_result_retries == 3


class TestListRequestsTool:
    @staticmethod
    def _make_mock_request(*, req_id=None, request_id="prov-str", content="Test", status="PENDING"):
        req = MagicMock()
        req.id = req_id or uuid4()
        req.request_id = request_id
        req.content = content
        req.status = status
        return req

    @pytest.mark.asyncio
    async def test_list_requests_returns_pending_requests(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        req = self._make_mock_request(content="Is the earth flat?")
        mock_result = MagicMock()
        mock_result.all.return_value = [(req, 2)]
        sample_deps.db.execute = AsyncMock(return_value=mock_result)

        result = await list_requests(ctx)

        assert "1 PENDING request(s)" in result
        assert str(req.id) in result
        assert "Is the earth flat?" in result
        assert "Notes: 2" in result

    @pytest.mark.asyncio
    async def test_list_requests_no_results(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        mock_result = MagicMock()
        mock_result.all.return_value = []
        sample_deps.db.execute = AsyncMock(return_value=mock_result)

        result = await list_requests(ctx)

        assert "No PENDING requests found" in result

    @pytest.mark.asyncio
    async def test_list_requests_filters_by_status(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        mock_result = MagicMock()
        mock_result.all.return_value = []
        sample_deps.db.execute = AsyncMock(return_value=mock_result)

        result = await list_requests(ctx, status="COMPLETED")

        assert "No COMPLETED requests found" in result

    @pytest.mark.asyncio
    async def test_list_requests_rejects_invalid_status(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await list_requests(ctx, status="BOGUS")

        assert "Error" in result
        assert "BOGUS" in result

    @pytest.mark.asyncio
    async def test_list_requests_truncates_long_content(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        req = self._make_mock_request(content="A " * 80)
        mock_result = MagicMock()
        mock_result.all.return_value = [(req, 0)]
        sample_deps.db.execute = AsyncMock(return_value=mock_result)

        result = await list_requests(ctx)

        assert "..." in result

    @pytest.mark.asyncio
    async def test_list_requests_handles_db_error(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        sample_deps.db.execute = AsyncMock(side_effect=SQLAlchemyError("db down"))
        sample_deps.db.rollback = AsyncMock()

        result = await list_requests(ctx)

        assert "Error" in result
        sample_deps.db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_requests_id_usable_in_write_note(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        req = self._make_mock_request(content="Test content")
        mock_result = MagicMock()
        mock_result.all.return_value = [(req, 0)]
        sample_deps.db.execute = AsyncMock(return_value=mock_result)

        result = await list_requests(ctx)

        returned_id = str(req.id)
        assert returned_id in result

        sample_deps.available_requests = [
            {"id": returned_id, "request_id": "prov-str", "content": "Test", "status": "PENDING"},
        ]
        sample_deps.db.flush = AsyncMock()
        sample_deps.db.add = MagicMock()
        write_result = await write_note(
            ctx,
            request_id=returned_id,
            summary="Test note",
            classification="NOT_MISLEADING",
        )
        assert "Note created" in write_result
