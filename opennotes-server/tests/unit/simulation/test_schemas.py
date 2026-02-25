from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestSimAgentCreateModelNameValidation:
    def test_rejects_slash_separated_model_name(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        with pytest.raises(ValidationError, match="model_name"):
            SimAgentCreateAttributes(
                name="TestAgent",
                personality="A test agent",
                model_name="openai/gpt-5-mini",
            )

    def test_rejects_vertex_ai_slash_model_name(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        with pytest.raises(ValidationError, match="model_name"):
            SimAgentCreateAttributes(
                name="TestAgent",
                personality="A test agent",
                model_name="vertex_ai/gemini-2.5-flash",
            )

    def test_accepts_valid_colon_separated_model_name(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        agent = SimAgentCreateAttributes(
            name="TestAgent",
            personality="A test agent",
            model_name="openai:gpt-4o-mini",
        )
        assert agent.model_name == "openai:gpt-4o-mini"

    def test_rejects_model_name_without_separator(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        with pytest.raises(ValidationError, match="model_name"):
            SimAgentCreateAttributes(
                name="TestAgent",
                personality="A test agent",
                model_name="gpt-4o-mini",
            )

    def test_error_message_includes_model_name(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        with pytest.raises(ValidationError) as exc_info:
            SimAgentCreateAttributes(
                name="TestAgent",
                personality="A test agent",
                model_name="openai/gpt-5-mini",
            )
        error_str = str(exc_info.value)
        assert "openai/gpt-5-mini" in error_str


class TestSimAgentUpdateModelNameValidation:
    def test_rejects_invalid_model_name(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentUpdateAttributes

        with pytest.raises(ValidationError, match="model_name"):
            SimAgentUpdateAttributes(model_name="openai/gpt-5-mini")

    def test_accepts_none_model_name(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentUpdateAttributes

        update = SimAgentUpdateAttributes(model_name=None)
        assert update.model_name is None

    def test_accepts_omitted_model_name(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentUpdateAttributes

        update = SimAgentUpdateAttributes(name="Updated Name")
        assert update.model_name is None

    def test_accepts_valid_model_name(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentUpdateAttributes

        update = SimAgentUpdateAttributes(model_name="openai:gpt-4o-mini")
        assert update.model_name == "openai:gpt-4o-mini"


class TestSimAgentAttributesModelSerialization:
    def test_model_name_serialized_as_structured_object(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentAttributes

        attrs = SimAgentAttributes(
            name="TestAgent",
            personality="A test agent",
            model_name="openai:gpt-4o-mini",
            memory_compaction_strategy="sliding_window",
        )
        assert attrs.model_name == {"provider": "openai", "model": "gpt-4o-mini"}

    def test_model_name_accepts_dict_input(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentAttributes

        attrs = SimAgentAttributes(
            name="TestAgent",
            personality="A test agent",
            model_name={"provider": "anthropic", "model": "claude-3-haiku"},
            memory_compaction_strategy="sliding_window",
        )
        assert attrs.model_name == {"provider": "anthropic", "model": "claude-3-haiku"}
