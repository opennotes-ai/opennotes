from src.llm_config.model_id import ModelId
from tests._model_fixtures import (
    ANTHROPIC_TEST_MODEL,
    GOOGLE_VERTEX_FLASH_TEST_MODEL,
    GOOGLE_VERTEX_PRO_TEST_MODEL,
    GROQ_TEST_MODEL,
    OPENAI_TEST_MODEL,
)


def test_constants_parse_via_modelid() -> None:
    for model_str in (
        GOOGLE_VERTEX_PRO_TEST_MODEL,
        GOOGLE_VERTEX_FLASH_TEST_MODEL,
        OPENAI_TEST_MODEL,
        ANTHROPIC_TEST_MODEL,
        GROQ_TEST_MODEL,
    ):
        parsed = ModelId.from_pydantic_ai(model_str)
        assert parsed.provider
        assert parsed.model


def test_prod_default_google_model_fixture(prod_default_google_model: str) -> None:
    assert isinstance(prod_default_google_model, str)
    assert prod_default_google_model.startswith("google-vertex:")
