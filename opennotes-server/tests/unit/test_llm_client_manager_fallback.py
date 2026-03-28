"""
Tests for LLMClientManager global API key fallback functionality.

Ensures that LLMClientManager properly falls back to global API keys
when no community-specific configuration exists.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.llm_config.constants import ADC_SENTINEL
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.providers import DirectProvider


@pytest.fixture
def encryption_service():
    service = MagicMock(spec=EncryptionService)
    service.decrypt_api_key.return_value = "community-api-key"
    return service


@pytest.fixture
def client_manager(encryption_service):
    return LLMClientManager(encryption_service)


@pytest.mark.asyncio
async def test_get_client_uses_global_openai_key(client_manager):
    """Test that global OPENAI_API_KEY is used."""
    with patch.object(client_manager, "_get_global_api_key", return_value="global-openai-key"):
        client = await client_manager.get_client("openai")

        assert client is not None
        assert isinstance(client, DirectProvider)
        assert client.api_key == "global-openai-key"
        assert client.default_model == "openai:gpt-5.1"


@pytest.mark.asyncio
async def test_get_client_returns_none_when_no_global_key(client_manager):
    """Test that None is returned when no global key is configured."""
    with patch.object(client_manager, "_get_global_api_key", return_value=None):
        client = await client_manager.get_client("openai")

        assert client is None


@pytest.mark.asyncio
async def test_get_client_caches_global_client(client_manager):
    """Test that clients are cached properly."""
    with patch.object(client_manager, "_get_global_api_key", return_value="global-openai-key"):
        client1 = await client_manager.get_client("openai")
        client2 = await client_manager.get_client("openai")

        assert client1 is client2


@pytest.mark.asyncio
async def test_invalidate_cache_clears_cached_clients(client_manager):
    """Test that cache invalidation works."""
    with patch.object(client_manager, "_get_global_api_key", return_value="global-openai-key"):
        client1 = await client_manager.get_client("openai")

        client_manager.invalidate_cache(uuid4(), "openai")

        client2 = await client_manager.get_client("openai")

        assert client1 is not client2


class TestVertexAIFallback:
    """Tests for Vertex AI / Gemini global fallback behavior."""

    def test_get_global_api_key_returns_adc_for_vertex_ai_when_project_set(self, client_manager):
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = "my-gcp-project"
            key = client_manager._get_global_api_key("vertex_ai")
            assert key == ADC_SENTINEL

    def test_get_global_api_key_returns_none_for_vertex_ai_when_project_missing(
        self, client_manager
    ):
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = None
            key = client_manager._get_global_api_key("vertex_ai")
            assert key is None

    def test_get_global_api_key_returns_adc_for_gemini_when_project_set(self, client_manager):
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = "my-gcp-project"
            key = client_manager._get_global_api_key("gemini")
            assert key == ADC_SENTINEL

    def test_get_global_api_key_returns_none_for_gemini_when_project_missing(self, client_manager):
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = None
            key = client_manager._get_global_api_key("gemini")
            assert key is None

    def test_get_default_model_returns_pydantic_ai_format_for_vertex_ai(self, client_manager):
        model = client_manager._get_default_model("vertex_ai")
        assert model == "google-vertex:gemini-2.5-pro"

    def test_get_default_model_returns_pydantic_ai_format_for_gemini_provider(self, client_manager):
        model = client_manager._get_default_model("gemini")
        assert model == "google-gla:gemini-2.5-pro"

    @pytest.mark.asyncio
    async def test_vertex_ai_client_created_via_global_adc(self, client_manager):
        """vertex_ai client should be created via global ADC."""
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = "my-gcp-project"
            mock_settings.DEFAULT_FULL_MODEL = "openai:gpt-5.1"
            client = await client_manager.get_client("vertex_ai")

        assert client is not None
        assert isinstance(client, DirectProvider)
        assert client.api_key == ADC_SENTINEL
        assert client.default_model == "google-vertex:gemini-2.5-pro"
        assert client._provider_name == "vertex_ai"

    @pytest.mark.asyncio
    async def test_vertex_ai_returns_none_when_project_missing(self, client_manager):
        """vertex_ai client returns None when VERTEXAI_PROJECT is not configured."""
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = None
            client = await client_manager.get_client("vertex_ai")

        assert client is None
