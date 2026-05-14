"""Unit tests for the shared pydantic-ai Agent factory.

Covers the `name=` plumbing — every vibecheck call site passes a stable
identifier so each Agent surfaces as a distinct span attribute in Logfire,
making post-Gemini traces correlatable per analysis.
"""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.instrumented import InstrumentationSettings

from src.config import Settings
from src.services.gemini_agent import (
    OUTPUT_VALIDATION_RETRIES,
    build_agent,
    google_vertex_model_name,
)


class _Out(BaseModel):
    text: str


@pytest.fixture
def settings() -> Settings:
    return Settings()


def test_build_agent_propagates_name_to_pydantic_ai_agent(settings: Settings) -> None:
    agent = build_agent(
        settings,
        output_type=_Out,
        system_prompt="ignored",
        name="vibecheck.unit_test",
    )
    assert agent.name == "vibecheck.unit_test"


def test_build_agent_omits_name_when_unspecified(settings: Settings) -> None:
    """Backwards compatible: no `name` arg leaves the agent unnamed
    (pydantic-ai surfaces this as `Agent.name is None` at construction time)."""
    agent = build_agent(settings, output_type=_Out, system_prompt="ignored")
    assert agent.name is None


def test_build_agent_defaults_to_fast_model(settings: Settings) -> None:
    agent = build_agent(settings, output_type=_Out, system_prompt="ignored")

    assert isinstance(agent.model, GoogleModel)
    assert agent.model.model_name == "gemini-3-flash-preview"


def test_build_agent_synthesis_tier_uses_pro_model(settings: Settings) -> None:
    agent = build_agent(
        settings,
        output_type=_Out,
        system_prompt="ignored",
        tier="synthesis",
    )

    assert isinstance(agent.model, GoogleModel)
    assert agent.model.model_name == "gemini-3.1-pro-preview"


def test_google_vertex_model_name_strips_vertex_prefix() -> None:
    assert (
        google_vertex_model_name(
            "google-vertex:gemini-3-flash-preview",
            setting_name="VERTEXAI_FAST_MODEL",
        )
        == "gemini-3-flash-preview"
    )


def test_google_vertex_model_name_rejects_malformed_setting() -> None:
    with pytest.raises(ValueError, match="VERTEXAI_FAST_MODEL"):
        google_vertex_model_name(
            "gemini-3-flash-preview",
            setting_name="VERTEXAI_FAST_MODEL",
        )


def test_output_validation_retries_constant_is_three() -> None:
    assert OUTPUT_VALIDATION_RETRIES == 3


def test_build_agent_passes_output_retries_to_agent_constructor(settings: Settings) -> None:
    with patch("src.services.gemini_agent.Agent") as mock_agent_cls:
        mock_agent_cls.return_value = MagicMock()
        build_agent(settings, output_type=_Out, system_prompt="test")
        _, kwargs = mock_agent_cls.call_args
        assert kwargs.get("output_retries") == 3
        assert "retries" not in kwargs


def test_build_agent_converts_instrument_settings_to_capability(settings: Settings) -> None:
    instrument = InstrumentationSettings(include_content=True, version=3)
    with patch("src.services.gemini_agent.Agent") as mock_agent_cls:
        mock_agent_cls.return_value = MagicMock()
        build_agent(
            settings,
            output_type=_Out,
            system_prompt="test",
            instrument=instrument,
        )
        _, kwargs = mock_agent_cls.call_args
        assert "instrument" not in kwargs
        capabilities = kwargs.get("capabilities")
        assert len(capabilities) == 1
        capability = capabilities[0]
        assert isinstance(capability, Instrumentation)
        assert capability.settings is instrument


def test_build_agent_converts_instrument_true_to_capability(settings: Settings) -> None:
    with patch("src.services.gemini_agent.Agent") as mock_agent_cls:
        mock_agent_cls.return_value = MagicMock()
        build_agent(settings, output_type=_Out, system_prompt="test", instrument=True)
        _, kwargs = mock_agent_cls.call_args
        assert "instrument" not in kwargs
        capabilities = kwargs.get("capabilities")
        assert len(capabilities) == 1
        assert isinstance(capabilities[0], Instrumentation)


def test_build_agent_omits_instrument_when_unspecified(settings: Settings) -> None:
    with patch("src.services.gemini_agent.Agent") as mock_agent_cls:
        mock_agent_cls.return_value = MagicMock()
        build_agent(settings, output_type=_Out, system_prompt="test")
        _, kwargs = mock_agent_cls.call_args
        assert "instrument" not in kwargs


def test_build_agent_does_not_emit_deprecation_warnings(settings: Settings) -> None:
    instrument = InstrumentationSettings(include_content=True, version=3)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        agent = build_agent(
            settings,
            output_type=_Out,
            system_prompt="test",
            name="vibecheck.unit_test",
            instrument=instrument,
        )
    assert agent.name == "vibecheck.unit_test"
