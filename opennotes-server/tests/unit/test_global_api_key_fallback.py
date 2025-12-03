from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import AsyncOpenAI

from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.service import LLMService
from src.services.vision_service import VisionService


@pytest.fixture
def mock_encryption_service():
    encryption_service = MagicMock(spec=EncryptionService)
    encryption_service.decrypt_api_key.return_value = "community-api-key"
    return encryption_service


@pytest.fixture
def mock_client_manager(mock_encryption_service):
    client_manager = MagicMock(spec=LLMClientManager)
    client_manager.encryption_service = mock_encryption_service
    return client_manager


@pytest.fixture
def mock_llm_service(mock_client_manager):
    llm_service = MagicMock(spec=LLMService)
    llm_service.client_manager = mock_client_manager
    return llm_service


@pytest.fixture
def vision_service(mock_llm_service):
    return VisionService(mock_llm_service)


@pytest.mark.asyncio
async def test_vision_service_uses_global_key_when_no_community_config(vision_service, db_session):
    community_server_id = "test-guild-123"

    with (
        patch("src.services.vision_service.settings.OPENAI_API_KEY", "global-api-key"),
        patch.object(AsyncOpenAI, "__init__", return_value=None) as mock_client_init,
    ):
        mock_db_execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_execute.return_value = mock_result
        db_session.execute = mock_db_execute

        await vision_service._get_openai_client(db_session, community_server_id)

        mock_client_init.assert_called_once()
        call_kwargs = mock_client_init.call_args[1]
        assert call_kwargs["api_key"] == "global-api-key"
        assert call_kwargs["timeout"] == 30.0

        assert vision_service.api_key_source_cache[community_server_id] == "global"


@pytest.mark.asyncio
async def test_vision_service_uses_community_key_when_config_exists(
    vision_service, db_session, mock_encryption_service
):
    community_server_id = "test-guild-123"

    mock_config = MagicMock()
    mock_config.api_key_encrypted = b"encrypted-key"
    mock_config.encryption_key_id = "key-id"

    with (
        patch("src.services.vision_service.settings.OPENAI_API_KEY", "global-api-key"),
        patch.object(AsyncOpenAI, "__init__", return_value=None) as mock_client_init,
    ):
        mock_db_execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db_execute.return_value = mock_result
        db_session.execute = mock_db_execute

        await vision_service._get_openai_client(db_session, community_server_id)

        mock_client_init.assert_called_once()
        call_kwargs = mock_client_init.call_args[1]
        assert call_kwargs["api_key"] == "community-api-key"

        assert vision_service.api_key_source_cache[community_server_id] == "community"


@pytest.mark.asyncio
async def test_vision_service_raises_error_when_no_config_and_no_global_key(
    vision_service, db_session
):
    community_server_id = "test-guild-123"

    with patch("src.services.vision_service.settings.OPENAI_API_KEY", None):
        mock_db_execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_execute.return_value = mock_result
        db_session.execute = mock_db_execute

        with pytest.raises(
            ValueError,
            match=f"No OpenAI configuration found for community server {community_server_id}",
        ):
            await vision_service._get_openai_client(db_session, community_server_id)


@pytest.mark.asyncio
async def test_vision_service_clears_api_key_source_cache_on_invalidate(vision_service):
    vision_service.api_key_source_cache["guild-1"] = "global"
    vision_service.api_key_source_cache["guild-2"] = "community"

    vision_service.invalidate_cache("guild-1")

    assert "guild-1" not in vision_service.api_key_source_cache
    assert "guild-2" in vision_service.api_key_source_cache

    vision_service.invalidate_cache(None)

    assert len(vision_service.api_key_source_cache) == 0


@pytest.mark.asyncio
async def test_vision_service_tracks_api_key_source_in_logs(vision_service, db_session):
    community_server_id = "test-guild-123"

    with (
        patch("src.services.vision_service.settings.OPENAI_API_KEY", "global-api-key"),
        patch.object(AsyncOpenAI, "__init__", return_value=None),
        patch("src.services.vision_service.logger") as mock_logger,
    ):
        mock_db_execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_execute.return_value = mock_result
        db_session.execute = mock_db_execute

        await vision_service._get_openai_client(db_session, community_server_id)

        log_calls = list(mock_logger.info.call_args_list)
        client_init_log = [
            call for call in log_calls if "Using global OpenAI API key as fallback" in str(call)
        ]
        assert len(client_init_log) == 1

        extra_data = client_init_log[0][1]["extra"]
        assert extra_data["api_key_source"] == "global"
        assert extra_data["community_server_id"] == community_server_id
