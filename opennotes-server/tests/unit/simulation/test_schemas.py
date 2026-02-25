from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


class TestSimAgentCreateModelNameValidation:
    def test_rejects_slash_separated_model_name(self) -> None:
        from pydantic_ai.exceptions import UserError

        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        with (
            patch(
                "src.simulation.sim_agents_jsonapi_router.infer_model",
                side_effect=UserError("Unknown model: openai/gpt-5-mini"),
            ),
            pytest.raises(ValidationError, match="model_name"),
        ):
            SimAgentCreateAttributes(
                name="TestAgent",
                personality="A test agent",
                model_name="openai/gpt-5-mini",
            )

    def test_rejects_vertex_ai_slash_model_name(self) -> None:
        from pydantic_ai.exceptions import UserError

        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        with (
            patch(
                "src.simulation.sim_agents_jsonapi_router.infer_model",
                side_effect=UserError("Unknown model: vertex_ai/gemini-2.5-flash"),
            ),
            pytest.raises(ValidationError, match="model_name"),
        ):
            SimAgentCreateAttributes(
                name="TestAgent",
                personality="A test agent",
                model_name="vertex_ai/gemini-2.5-flash",
            )

    def test_accepts_valid_colon_separated_model_name(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        mock_model = MagicMock()
        with patch("src.simulation.sim_agents_jsonapi_router.infer_model", return_value=mock_model):
            agent = SimAgentCreateAttributes(
                name="TestAgent",
                personality="A test agent",
                model_name="openai:gpt-4o-mini",
            )
        assert agent.model_name == "openai:gpt-4o-mini"

    def test_accepts_valid_model_even_when_api_key_missing(self) -> None:
        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        with patch(
            "src.simulation.sim_agents_jsonapi_router.infer_model",
            side_effect=Exception("The api_key client option must be set"),
        ):
            agent = SimAgentCreateAttributes(
                name="TestAgent",
                personality="A test agent",
                model_name="openai:gpt-4o-mini",
            )
        assert agent.model_name == "openai:gpt-4o-mini"

    def test_rejects_completely_unknown_provider(self) -> None:
        from pydantic_ai.exceptions import UserError

        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        with (
            patch(
                "src.simulation.sim_agents_jsonapi_router.infer_model",
                side_effect=UserError("Unknown model: bogus-provider:model"),
            ),
            pytest.raises(ValidationError, match="model_name"),
        ):
            SimAgentCreateAttributes(
                name="TestAgent",
                personality="A test agent",
                model_name="bogus-provider:model",
            )

    def test_error_message_includes_model_name(self) -> None:
        from pydantic_ai.exceptions import UserError

        from src.simulation.sim_agents_jsonapi_router import SimAgentCreateAttributes

        with (
            patch(
                "src.simulation.sim_agents_jsonapi_router.infer_model",
                side_effect=UserError("Unknown model: openai/gpt-5-mini"),
            ),
            pytest.raises(ValidationError) as exc_info,
        ):
            SimAgentCreateAttributes(
                name="TestAgent",
                personality="A test agent",
                model_name="openai/gpt-5-mini",
            )
        error_str = str(exc_info.value)
        assert "openai/gpt-5-mini" in error_str


class TestSimAgentUpdateModelNameValidation:
    def test_rejects_invalid_model_name(self) -> None:
        from pydantic_ai.exceptions import UserError

        from src.simulation.sim_agents_jsonapi_router import SimAgentUpdateAttributes

        with (
            patch(
                "src.simulation.sim_agents_jsonapi_router.infer_model",
                side_effect=UserError("Unknown model: openai/gpt-5-mini"),
            ),
            pytest.raises(ValidationError, match="model_name"),
        ):
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

        mock_model = MagicMock()
        with patch("src.simulation.sim_agents_jsonapi_router.infer_model", return_value=mock_model):
            update = SimAgentUpdateAttributes(model_name="openai:gpt-4o-mini")
        assert update.model_name == "openai:gpt-4o-mini"
