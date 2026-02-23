from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.llm_config.service import LLMService
from src.services.vision_service import VisionService


@pytest.fixture
def mock_llm_service():
    llm_service = MagicMock(spec=LLMService)
    llm_service.describe_image = AsyncMock(return_value="A test image description")
    return llm_service


@pytest.fixture
def vision_service(mock_llm_service):
    return VisionService(mock_llm_service)


@pytest.fixture
def mock_db():
    return AsyncMock()


def _setup_db_community_lookup(mock_db, uuid_value):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = uuid_value
    mock_db.execute.return_value = mock_result


@pytest.mark.asyncio
async def test_describe_image_delegates_to_llm_service(vision_service, mock_llm_service, mock_db):
    community_uuid = uuid4()
    _setup_db_community_lookup(mock_db, community_uuid)

    result = await vision_service.describe_image(
        mock_db, "https://example.com/img.png", "guild-123", detail="high", max_tokens=200
    )

    assert result == "A test image description"
    mock_llm_service.describe_image.assert_called_once_with(
        mock_db, "https://example.com/img.png", community_uuid, "high", 200
    )


@pytest.mark.asyncio
async def test_describe_image_cache_hit_skips_llm_call(vision_service, mock_llm_service, mock_db):
    community_uuid = uuid4()
    _setup_db_community_lookup(mock_db, community_uuid)

    result1 = await vision_service.describe_image(
        mock_db, "https://example.com/img.png", "guild-123"
    )
    result2 = await vision_service.describe_image(
        mock_db, "https://example.com/img.png", "guild-123"
    )

    assert result1 == result2 == "A test image description"
    mock_llm_service.describe_image.assert_called_once()


@pytest.mark.asyncio
async def test_describe_image_raises_when_community_server_not_found(vision_service, mock_db):
    _setup_db_community_lookup(mock_db, None)

    with pytest.raises(
        ValueError,
        match="Community server not found for platform_community_server_id: guild-123",
    ):
        await vision_service.describe_image(mock_db, "https://example.com/img.png", "guild-123")


@pytest.mark.asyncio
async def test_invalidate_cache_clears_description_cache(vision_service, mock_llm_service, mock_db):
    community_uuid = uuid4()
    _setup_db_community_lookup(mock_db, community_uuid)

    await vision_service.describe_image(mock_db, "https://example.com/img.png", "guild-123")
    assert len(vision_service.description_cache) == 1

    vision_service.invalidate_cache("guild-123")

    assert len(vision_service.description_cache) == 0


@pytest.mark.asyncio
async def test_invalidate_cache_with_none_clears_all(vision_service, mock_llm_service, mock_db):
    community_uuid = uuid4()
    _setup_db_community_lookup(mock_db, community_uuid)

    await vision_service.describe_image(mock_db, "https://example.com/img.png", "guild-123")

    mock_llm_service.describe_image.return_value = "Another description"
    await vision_service.describe_image(mock_db, "https://example.com/other.png", "guild-123")
    assert len(vision_service.description_cache) == 2

    vision_service.invalidate_cache(None)

    assert len(vision_service.description_cache) == 0
