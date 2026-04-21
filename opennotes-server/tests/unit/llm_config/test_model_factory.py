from __future__ import annotations

import pytest

from src.llm_config.local_models import OpenNotesGoogleModel
from src.llm_config.model_factory import infer_model_with_overrides
from src.llm_config.model_id import ModelFlavor, ModelId


@pytest.fixture(autouse=True)
def _stub_provider_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _stub_google_adc(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    import google.auth

    fake_creds = MagicMock()
    monkeypatch.setattr(google.auth, "default", lambda *_, **__: (fake_creds, "test-project"))

    from src.llm_config import model_factory as mf

    monkeypatch.setattr(mf.settings, "VERTEXAI_PROJECT", "test-project", raising=False)
    monkeypatch.setattr(mf.settings, "VERTEXAI_LOCATION", "global", raising=False)

    mf._build_google_vertex_model.cache_clear()
    yield
    mf._build_google_vertex_model.cache_clear()


@pytest.fixture(autouse=True)
def _disable_httpx_env_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    # pydantic-ai's provider __init__ methods build an httpx.AsyncClient via
    # create_async_http_client(), which honors ALL_PROXY / HTTPS_PROXY env
    # vars. Dev shells that forward a SOCKS proxy make httpx raise ImportError
    # at construction time. For unit tests we only care about the kwargs passed
    # to GoogleProvider, so clear all proxy-related env vars.
    for var in (
        "ALL_PROXY",
        "all_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
    ):
        monkeypatch.delenv(var, raising=False)


class TestInferModelWithOverrides:
    def test_returns_opennotes_google_model_for_google_vertex(self):
        model = infer_model_with_overrides("google-vertex:gemini-3.1-pro-preview")
        assert isinstance(model, OpenNotesGoogleModel)
        assert model.model_name == "gemini-3.1-pro-preview"

    def test_infer_model_with_overrides_passes_global_location(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        from pydantic_ai.providers.google import GoogleProvider

        original_init = GoogleProvider.__init__

        def _spy_init(self: GoogleProvider, *args: object, **kwargs: object) -> None:
            captured.update(kwargs)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(GoogleProvider, "__init__", _spy_init)

        from src.llm_config import model_factory as mf

        monkeypatch.setattr(mf.settings, "VERTEXAI_LOCATION", "global")
        monkeypatch.setattr(mf.settings, "VERTEXAI_PROJECT", "test-project")

        model = infer_model_with_overrides("google-vertex:gemini-3-flash")
        assert isinstance(model, OpenNotesGoogleModel)
        assert captured.get("location") == "global"
        assert captured.get("project") == "test-project"

    def test_returns_string_for_openai(self):
        result = infer_model_with_overrides("openai:gpt-4o-mini")
        assert result == "openai:gpt-4o-mini"

    def test_returns_string_for_anthropic(self):
        result = infer_model_with_overrides("anthropic:claude-3-5-sonnet-latest")
        assert result == "anthropic:claude-3-5-sonnet-latest"

    def test_infer_model_with_overrides_rejects_google_gla(self):
        with pytest.raises(ValueError, match="google-gla provider was removed"):
            infer_model_with_overrides("google-gla:gemini-2.0-flash")

    def test_memoizes_google_vertex_model_per_identity(self) -> None:
        first = infer_model_with_overrides("google-vertex:gemini-3.1-pro-preview")
        second = infer_model_with_overrides("google-vertex:gemini-3.1-pro-preview")
        assert isinstance(first, OpenNotesGoogleModel)
        assert first is second

    def test_memoization_distinguishes_by_model_name(self) -> None:
        first = infer_model_with_overrides("google-vertex:gemini-3.1-pro-preview")
        second = infer_model_with_overrides("google-vertex:gemini-3-flash")
        assert isinstance(first, OpenNotesGoogleModel)
        assert isinstance(second, OpenNotesGoogleModel)
        assert first is not second

    def test_fails_fast_when_vertexai_project_is_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.llm_config import model_factory as mf

        monkeypatch.setattr(mf.settings, "VERTEXAI_PROJECT", None, raising=False)
        with pytest.raises(ValueError, match="VERTEXAI_PROJECT is not configured"):
            infer_model_with_overrides("google-vertex:gemini-3.1-pro-preview")

    def test_fails_fast_when_vertexai_project_is_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.llm_config import model_factory as mf

        monkeypatch.setattr(mf.settings, "VERTEXAI_PROJECT", "", raising=False)
        with pytest.raises(ValueError, match="VERTEXAI_PROJECT is not configured"):
            infer_model_with_overrides("google-vertex:gemini-3.1-pro-preview")


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

    def test_to_pydantic_ai_model_for_openai_returns_string(self):
        m = ModelId(provider="openai", model="gpt-4o-mini", flavor=ModelFlavor.PYDANTIC_AI)
        result = m.to_pydantic_ai_model()
        assert result == "openai:gpt-4o-mini"
