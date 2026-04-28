"""Unit tests for the shared pydantic-ai Agent factory.

Covers the `name=` plumbing — every vibecheck call site passes a stable
identifier so each Agent surfaces as a distinct span attribute in Logfire,
making post-Gemini traces correlatable per analysis.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from src.config import Settings
from src.services.gemini_agent import build_agent, google_vertex_model_name


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

    assert agent.model.model_name == "gemini-3-flash-preview"


def test_build_agent_synthesis_tier_uses_pro_model(settings: Settings) -> None:
    agent = build_agent(
        settings,
        output_type=_Out,
        system_prompt="ignored",
        tier="synthesis",
    )

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
