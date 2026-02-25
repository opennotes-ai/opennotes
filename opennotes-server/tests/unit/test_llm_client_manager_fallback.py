"""
Tests for LLMClientManager global API key fallback functionality.

Ensures that LLMClientManager properly falls back to global API keys
when no community-specific configuration exists.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.llm_config.constants import ADC_SENTINEL
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.providers import LiteLLMProvider


@pytest.fixture
def encryption_service():
    """Create mock encryption service."""
    service = MagicMock(spec=EncryptionService)
    service.decrypt_api_key.return_value = "community-api-key"
    return service


@pytest.fixture
def client_manager(encryption_service):
    """Create LLMClientManager instance."""
    return LLMClientManager(encryption_service)


@pytest.mark.asyncio
async def test_get_client_uses_community_config_when_exists(client_manager, db_session):
    """Test that community-specific config is used when it exists."""
    community_server_id = uuid4()

    mock_config = MagicMock()
    mock_config.provider = "openai"
    mock_config.enabled = True
    mock_config.api_key_encrypted = b"encrypted-key"
    mock_config.encryption_key_id = "key-id"
    mock_config.settings = {}

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_config

    db_session.execute = AsyncMock(return_value=mock_result)

    client = await client_manager.get_client(db_session, community_server_id, "openai")

    assert client is not None
    assert isinstance(client, LiteLLMProvider)
    assert client.api_key == "community-api-key"
    assert client.default_model == "openai/gpt-5.1"


@pytest.mark.asyncio
async def test_get_client_falls_back_to_global_openai_key(client_manager, db_session):
    """Test that global OPENAI_API_KEY is used when no community config exists."""
    community_server_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    db_session.execute = AsyncMock(return_value=mock_result)

    with patch.object(client_manager, "_get_global_api_key", return_value="global-openai-key"):
        client = await client_manager.get_client(db_session, community_server_id, "openai")

        assert client is not None
        assert isinstance(client, LiteLLMProvider)
        assert client.api_key == "global-openai-key"
        assert client.default_model == "openai/gpt-5.1"


@pytest.mark.asyncio
async def test_get_client_returns_none_when_no_config_and_no_global_key(client_manager, db_session):
    """Test that None is returned when no community config and no global key."""
    community_server_id = uuid4()

    # Mock database to return None (no config)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    db_session.execute = AsyncMock(return_value=mock_result)

    with patch.object(client_manager, "_get_global_api_key", return_value=None):
        client = await client_manager.get_client(db_session, community_server_id, "openai")

        assert client is None


@pytest.mark.asyncio
async def test_get_client_caches_global_fallback_client(client_manager, db_session):
    """Test that clients using global fallback are cached properly."""
    community_server_id = uuid4()

    # Mock database to return None (no config)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    db_session.execute = AsyncMock(return_value=mock_result)

    with patch.object(client_manager, "_get_global_api_key", return_value="global-openai-key"):
        # First call - should create client
        client1 = await client_manager.get_client(db_session, community_server_id, "openai")

        # Second call - should return cached client
        client2 = await client_manager.get_client(db_session, community_server_id, "openai")

        assert client1 is client2  # Same instance from cache


@pytest.mark.asyncio
async def test_invalidate_cache_clears_global_fallback_clients(client_manager, db_session):
    """Test that cache invalidation works for global fallback clients."""
    community_server_id = uuid4()

    # Mock database to return None (no config)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    db_session.execute = AsyncMock(return_value=mock_result)

    with patch.object(client_manager, "_get_global_api_key", return_value="global-openai-key"):
        # Create cached client
        client1 = await client_manager.get_client(db_session, community_server_id, "openai")

        # Invalidate cache
        client_manager.invalidate_cache(community_server_id, "openai")

        # Next call should create new client
        client2 = await client_manager.get_client(db_session, community_server_id, "openai")

        assert client1 is not client2  # Different instances


class TestVertexAIFallback:
    """Tests for Vertex AI / Gemini global fallback behavior."""

    def test_get_global_api_key_returns_adc_for_vertex_ai_when_project_set(self, client_manager):
        """_get_global_api_key('vertex_ai') returns 'ADC' when VERTEXAI_PROJECT is configured."""
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = "my-gcp-project"
            key = client_manager._get_global_api_key("vertex_ai")
            assert key == ADC_SENTINEL

    def test_get_global_api_key_returns_none_for_vertex_ai_when_project_missing(
        self, client_manager
    ):
        """_get_global_api_key('vertex_ai') returns None when VERTEXAI_PROJECT is not set."""
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = None
            key = client_manager._get_global_api_key("vertex_ai")
            assert key is None

    def test_get_global_api_key_returns_adc_for_gemini_when_project_set(self, client_manager):
        """_get_global_api_key('gemini') returns 'ADC' when VERTEXAI_PROJECT is configured."""
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = "my-gcp-project"
            key = client_manager._get_global_api_key("gemini")
            assert key == ADC_SENTINEL

    def test_get_global_api_key_returns_none_for_gemini_when_project_missing(self, client_manager):
        """_get_global_api_key('gemini') returns None when VERTEXAI_PROJECT is not set."""
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = None
            key = client_manager._get_global_api_key("gemini")
            assert key is None

    def test_get_default_model_returns_prefixed_gemini_for_vertex_ai(self, client_manager):
        """_get_default_model('vertex_ai') should return 'vertex_ai/gemini-2.5-pro'."""
        model = client_manager._get_default_model("vertex_ai")
        assert model == "vertex_ai/gemini-2.5-pro"

    def test_get_default_model_returns_prefixed_gemini_for_gemini_provider(self, client_manager):
        """_get_default_model('gemini') should return 'gemini/gemini-2.5-pro'."""
        model = client_manager._get_default_model("gemini")
        assert model == "gemini/gemini-2.5-pro"

    @pytest.mark.asyncio
    async def test_vertex_ai_client_created_without_db_key(self, client_manager, db_session):
        """vertex_ai client should be created via global ADC when no DB config exists."""
        community_server_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = "my-gcp-project"
            mock_settings.DEFAULT_FULL_MODEL = "openai/gpt-5.1"
            client = await client_manager.get_client(db_session, community_server_id, "vertex_ai")

        assert client is not None
        assert isinstance(client, LiteLLMProvider)
        assert client.api_key == ADC_SENTINEL
        assert client.default_model == "vertex_ai/gemini-2.5-pro"
        assert client._provider_name == "vertex_ai"

    @pytest.mark.asyncio
    async def test_vertex_ai_global_client_no_community(self, client_manager, db_session):
        """vertex_ai client should be created when community_server_id is None."""
        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = "my-gcp-project"
            mock_settings.DEFAULT_FULL_MODEL = "openai/gpt-5.1"
            client = await client_manager.get_client(db_session, None, "vertex_ai")

        assert client is not None
        assert isinstance(client, LiteLLMProvider)
        assert client.api_key == ADC_SENTINEL
        assert client.default_model == "vertex_ai/gemini-2.5-pro"

    @pytest.mark.asyncio
    async def test_vertex_ai_returns_none_when_project_missing(self, client_manager, db_session):
        """vertex_ai client returns None when VERTEXAI_PROJECT is not configured."""
        community_server_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        with patch("src.llm_config.manager.settings") as mock_settings:
            mock_settings.VERTEXAI_PROJECT = None
            client = await client_manager.get_client(db_session, community_server_id, "vertex_ai")

        assert client is None
