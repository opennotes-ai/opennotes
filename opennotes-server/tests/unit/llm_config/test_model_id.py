import pytest
from pydantic import ValidationError

from src.llm_config.constants import DEFAULT_MODELS_BY_PROVIDER, get_default_model_for_provider
from src.llm_config.model_id import ModelFlavor, ModelId


class TestModelFlavor:
    def test_litellm_value(self):
        assert ModelFlavor.LITELLM == "litellm"

    def test_pydantic_ai_value(self):
        assert ModelFlavor.PYDANTIC_AI == "pydantic_ai"

    def test_is_str_enum(self):
        assert isinstance(ModelFlavor.LITELLM, str)


class TestModelIdFromLitellm:
    def test_simple_slash_format(self):
        m = ModelId.from_litellm("openai/gpt-5.1")
        assert m.provider == "openai"
        assert m.model == "gpt-5.1"
        assert m.flavor == ModelFlavor.LITELLM

    def test_region_segment_in_model(self):
        m = ModelId.from_litellm("vertex_ai/global/gemini-2.5-pro")
        assert m.provider == "vertex_ai"
        assert m.model == "global/gemini-2.5-pro"

    def test_multiple_slashes_in_model(self):
        m = ModelId.from_litellm("openrouter/google/gemini-3-pro")
        assert m.provider == "openrouter"
        assert m.model == "google/gemini-3-pro"

    def test_anthropic(self):
        m = ModelId.from_litellm("anthropic/claude-3-5-sonnet-latest")
        assert m.provider == "anthropic"
        assert m.model == "claude-3-5-sonnet-latest"

    def test_bare_name_raises(self):
        with pytest.raises(ValueError, match="explicit provider"):
            ModelId.from_litellm("gpt-5.1")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="explicit provider"):
            ModelId.from_litellm("")

    def test_slash_only_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            ModelId.from_litellm("/")

    def test_empty_provider_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            ModelId.from_litellm("/gpt-5.1")

    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            ModelId.from_litellm("openai/")


class TestModelIdFromPydanticAi:
    def test_simple_colon_format(self):
        m = ModelId.from_pydantic_ai("openai:gpt-5.1")
        assert m.provider == "openai"
        assert m.model == "gpt-5.1"
        assert m.flavor == ModelFlavor.PYDANTIC_AI

    def test_slash_in_model_name(self):
        m = ModelId.from_pydantic_ai("openrouter:google/gemini-3-pro")
        assert m.provider == "openrouter"
        assert m.model == "google/gemini-3-pro"

    def test_anthropic(self):
        m = ModelId.from_pydantic_ai("anthropic:claude-3-5-sonnet-latest")
        assert m.provider == "anthropic"
        assert m.model == "claude-3-5-sonnet-latest"

    def test_bare_name_raises(self):
        with pytest.raises(ValueError, match="explicit provider"):
            ModelId.from_pydantic_ai("gpt-5.1")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="explicit provider"):
            ModelId.from_pydantic_ai("")

    def test_colon_only_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            ModelId.from_pydantic_ai(":")

    def test_empty_provider_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            ModelId.from_pydantic_ai(":gpt-5.1")

    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            ModelId.from_pydantic_ai("openai:")


class TestModelIdRendering:
    def test_to_litellm_simple(self):
        m = ModelId(provider="openai", model="gpt-5.1", flavor=ModelFlavor.LITELLM)
        assert m.to_litellm() == "openai/gpt-5.1"

    def test_to_litellm_with_region(self):
        m = ModelId(provider="vertex_ai", model="global/gemini-2.5-pro", flavor=ModelFlavor.LITELLM)
        assert m.to_litellm() == "vertex_ai/global/gemini-2.5-pro"

    def test_to_pydantic_ai_simple(self):
        m = ModelId(provider="openai", model="gpt-5.1", flavor=ModelFlavor.LITELLM)
        assert m.to_pydantic_ai() == "openai:gpt-5.1"

    def test_to_pydantic_ai_with_slash_in_model(self):
        m = ModelId(
            provider="openrouter", model="google/gemini-3-pro", flavor=ModelFlavor.PYDANTIC_AI
        )
        assert m.to_pydantic_ai() == "openrouter:google/gemini-3-pro"


class TestCrossFlavorTranslation:
    def test_vertex_ai_to_pydantic_ai(self):
        m = ModelId(provider="vertex_ai", model="global/gemini-2.5-pro", flavor=ModelFlavor.LITELLM)
        assert m.to_pydantic_ai() == "google-vertex:global/gemini-2.5-pro"

    def test_google_vertex_to_litellm(self):
        m = ModelId(
            provider="google-vertex", model="gemini-2.5-pro", flavor=ModelFlavor.PYDANTIC_AI
        )
        assert m.to_litellm() == "vertex_ai/gemini-2.5-pro"

    def test_gemini_to_pydantic_ai(self):
        m = ModelId(provider="gemini", model="gemini-2.5-flash", flavor=ModelFlavor.LITELLM)
        assert m.to_pydantic_ai() == "google-gla:gemini-2.5-flash"

    def test_google_gla_to_litellm(self):
        m = ModelId(provider="google-gla", model="gemini-2.5-flash", flavor=ModelFlavor.PYDANTIC_AI)
        assert m.to_litellm() == "gemini/gemini-2.5-flash"

    def test_no_mapping_passthrough(self):
        m = ModelId(provider="openai", model="gpt-5.1", flavor=ModelFlavor.LITELLM)
        assert m.to_pydantic_ai() == "openai:gpt-5.1"

    def test_unknown_provider_passthrough(self):
        m = ModelId(provider="custom-provider", model="my-model", flavor=ModelFlavor.LITELLM)
        assert m.to_pydantic_ai() == "custom-provider:my-model"
        assert m.to_litellm() == "custom-provider/my-model"


class TestRoundTrip:
    def test_litellm_round_trip_simple(self):
        original = "openai/gpt-5.1"
        assert ModelId.from_litellm(original).to_litellm() == original

    def test_litellm_round_trip_region(self):
        original = "vertex_ai/global/gemini-2.5-pro"
        assert ModelId.from_litellm(original).to_litellm() == original

    def test_pydantic_ai_round_trip_simple(self):
        original = "openai:gpt-5.1"
        assert ModelId.from_pydantic_ai(original).to_pydantic_ai() == original

    def test_pydantic_ai_round_trip_slash_in_model(self):
        original = "openrouter:google/gemini-3-pro"
        assert ModelId.from_pydantic_ai(original).to_pydantic_ai() == original

    def test_cross_flavor_round_trip(self):
        litellm_str = "vertex_ai/global/gemini-2.5-pro"
        m = ModelId.from_litellm(litellm_str)
        pydantic_ai_str = m.to_pydantic_ai()
        assert pydantic_ai_str == "google-vertex:global/gemini-2.5-pro"
        m2 = ModelId.from_pydantic_ai(pydantic_ai_str)
        assert m2.to_litellm() == litellm_str

    def test_gemini_google_gla_cross_flavor_round_trip(self):
        litellm_str = "gemini/gemini-2.5-flash"
        m = ModelId.from_litellm(litellm_str)
        pydantic_ai_str = m.to_pydantic_ai()
        assert pydantic_ai_str == "google-gla:gemini-2.5-flash"
        m2 = ModelId.from_pydantic_ai(pydantic_ai_str)
        assert m2.to_litellm() == litellm_str


class TestStr:
    def test_str_litellm_flavor(self):
        m = ModelId.from_litellm("openai/gpt-5.1")
        assert str(m) == "openai/gpt-5.1"

    def test_str_pydantic_ai_flavor(self):
        m = ModelId.from_pydantic_ai("openai:gpt-5.1")
        assert str(m) == "openai:gpt-5.1"

    def test_str_vertex_litellm(self):
        m = ModelId.from_litellm("vertex_ai/global/gemini-2.5-pro")
        assert str(m) == "vertex_ai/global/gemini-2.5-pro"

    def test_str_vertex_pydantic_ai(self):
        m = ModelId.from_pydantic_ai("google-vertex:global/gemini-2.5-pro")
        assert str(m) == "google-vertex:global/gemini-2.5-pro"


class TestFrozen:
    def test_immutable_provider(self):
        m = ModelId.from_litellm("openai/gpt-5.1")
        with pytest.raises(ValidationError, match="frozen"):
            m.provider = "anthropic"  # type: ignore[misc]

    def test_immutable_model(self):
        m = ModelId.from_litellm("openai/gpt-5.1")
        with pytest.raises(ValidationError, match="frozen"):
            m.model = "gpt-4"  # type: ignore[misc]

    def test_immutable_flavor(self):
        m = ModelId.from_litellm("openai/gpt-5.1")
        with pytest.raises(ValidationError, match="frozen"):
            m.flavor = ModelFlavor.PYDANTIC_AI  # type: ignore[misc]

    def test_hashable(self):
        m1 = ModelId.from_litellm("openai/gpt-5.1")
        m2 = ModelId.from_litellm("openai/gpt-5.1")
        assert hash(m1) == hash(m2)
        assert m1 == m2
        assert len({m1, m2}) == 1


class TestEquality:
    def test_equal_same_construction(self):
        m1 = ModelId.from_litellm("openai/gpt-5.1")
        m2 = ModelId.from_litellm("openai/gpt-5.1")
        assert m1 == m2

    def test_not_equal_different_model(self):
        m1 = ModelId.from_litellm("openai/gpt-5.1")
        m2 = ModelId.from_litellm("openai/gpt-4")
        assert m1 != m2

    def test_not_equal_different_flavor(self):
        m1 = ModelId(provider="openai", model="gpt-5.1", flavor=ModelFlavor.LITELLM)
        m2 = ModelId(provider="openai", model="gpt-5.1", flavor=ModelFlavor.PYDANTIC_AI)
        assert m1 != m2


class TestGetDefaultModelForProvider:
    def test_openai_returns_str(self):
        result = get_default_model_for_provider("openai")
        assert isinstance(result, str)
        assert not isinstance(result, ModelId)
        assert "/" in result

    def test_all_providers_return_str(self):
        for provider in [*DEFAULT_MODELS_BY_PROVIDER, "openai"]:
            result = get_default_model_for_provider(provider)
            assert isinstance(result, str), f"{provider} returned {type(result)}"
            assert not isinstance(result, ModelId), f"{provider} returned ModelId"

    def test_unknown_provider_returns_str(self):
        result = get_default_model_for_provider("nonexistent")
        assert result == "unknown"
        assert isinstance(result, str)
