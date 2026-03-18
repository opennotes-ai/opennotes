import pytest
from pydantic_ai.providers import Provider, infer_provider_class


@pytest.mark.parametrize(
    "provider_name",
    ["openai", "anthropic", "google-gla", "google-vertex", "groq"],
)
def test_provider_sdk_importable(provider_name: str):
    cls = infer_provider_class(provider_name)
    assert issubclass(cls, Provider)
