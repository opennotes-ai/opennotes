from __future__ import annotations

import pytest
from pydantic_ai.models import Model

from src.llm_config.local_models import OpenNotesGoogleModel
from src.llm_config.model_factory import infer_model_with_overrides
from src.llm_config.model_id import ModelFlavor, ModelId


@pytest.fixture(autouse=True)
def _stub_provider_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


class TestInferModelWithOverrides:
    def test_returns_opennotes_google_model_for_google_vertex(self):
        model = infer_model_with_overrides("google-vertex:gemini-3.1-pro-preview")
        assert isinstance(model, OpenNotesGoogleModel)
        assert model.model_name == "gemini-3.1-pro-preview"

    def test_returns_upstream_model_for_openai(self):
        model = infer_model_with_overrides("openai:gpt-4o-mini")
        assert isinstance(model, Model)
        assert not isinstance(model, OpenNotesGoogleModel)

    def test_returns_upstream_model_for_anthropic(self):
        model = infer_model_with_overrides("anthropic:claude-3-5-sonnet-latest")
        assert isinstance(model, Model)
        assert not isinstance(model, OpenNotesGoogleModel)


class TestToPydanticAiModelRoundTrip:
    def test_to_pydantic_ai_model_round_trips_via_helper(self):
        m = ModelId(
            provider="google-vertex",
            model="gemini-3.1-pro-preview",
            flavor=ModelFlavor.PYDANTIC_AI,
        )
        result = m.to_pydantic_ai_model()
        assert isinstance(result, OpenNotesGoogleModel)
        assert result.model_name == "gemini-3.1-pro-preview"

    def test_to_pydantic_ai_model_for_openai_returns_non_opennotes(self):
        m = ModelId(provider="openai", model="gpt-4o-mini", flavor=ModelFlavor.PYDANTIC_AI)
        result = m.to_pydantic_ai_model()
        assert isinstance(result, Model)
        assert not isinstance(result, OpenNotesGoogleModel)
