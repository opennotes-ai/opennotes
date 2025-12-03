"""Tests for VisionService."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import RateLimitError
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm_config.models import CommunityServer, CommunityServerLLMConfig
from src.llm_config.service import LLMService
from src.services.vision_service import VisionService


@pytest.fixture
def mock_llm_service():
    """Create LLM service mock."""
    service = MagicMock(spec=LLMService)
    service.describe_image = AsyncMock(return_value="A cat sitting on a table")
    return service


@pytest.fixture
def vision_service(mock_llm_service):
    """Create VisionService instance."""
    return VisionService(mock_llm_service)


@pytest.fixture
async def setup_community_config(db_session: AsyncSession):
    """Set up test community server with OpenAI config."""
    community_server = CommunityServer(
        platform="discord",
        platform_id="test-guild-123",
        name="Test Community",
    )
    db_session.add(community_server)
    await db_session.flush()

    llm_config = CommunityServerLLMConfig(
        community_server_id=community_server.id,
        provider="openai",
        enabled=True,
        api_key_encrypted=b"encrypted_key",
        encryption_key_id="test_key_id",
        api_key_preview="...xxxx",
        settings={"default_model": "gpt-5.1"},
    )
    db_session.add(llm_config)
    await db_session.flush()
    await db_session.commit()

    return community_server, llm_config


@pytest.mark.asyncio
async def test_describe_image_success(
    vision_service: VisionService,
    db_session: AsyncSession,
    setup_community_config,
    mock_llm_service,
):
    """Test successful image description generation."""
    community_server, _ = setup_community_config

    mock_llm_service.describe_image.return_value = "A cat sitting on a table"

    description = await vision_service.describe_image(
        db=db_session,
        image_url="https://example.com/cat.jpg",
        community_server_id=community_server.platform_id,
    )

    assert description == "A cat sitting on a table"
    mock_llm_service.describe_image.assert_called_once()

    # Verify correct parameters were passed to LLMService
    call_args = mock_llm_service.describe_image.call_args
    assert call_args[0][0] == db_session
    assert call_args[0][1] == "https://example.com/cat.jpg"
    assert call_args[0][2] == community_server.id  # UUID, not platform_id
    assert call_args[0][3] == "auto"  # detail
    assert call_args[0][4] == 300  # max_tokens


@pytest.mark.asyncio
async def test_describe_image_with_custom_params(
    vision_service: VisionService,
    db_session: AsyncSession,
    setup_community_config,
    mock_llm_service,
):
    """Test image description with custom detail and max_tokens."""
    community_server, _ = setup_community_config

    mock_llm_service.describe_image.return_value = "Detailed description of the image"

    description = await vision_service.describe_image(
        db=db_session,
        image_url="https://example.com/detailed.jpg",
        community_server_id=community_server.platform_id,
        detail="high",
        max_tokens=500,
    )

    assert description == "Detailed description of the image"

    # Verify custom parameters were passed
    call_args = mock_llm_service.describe_image.call_args
    assert call_args[0][3] == "high"  # detail
    assert call_args[0][4] == 500  # max_tokens


@pytest.mark.asyncio
async def test_describe_image_caching(
    vision_service: VisionService,
    db_session: AsyncSession,
    setup_community_config,
    mock_llm_service,
):
    """Test that vision descriptions are cached."""
    community_server, _ = setup_community_config

    mock_llm_service.describe_image.return_value = "Cached description"

    description1 = await vision_service.describe_image(
        db=db_session,
        image_url="https://example.com/cached.jpg",
        community_server_id=community_server.platform_id,
    )

    description2 = await vision_service.describe_image(
        db=db_session,
        image_url="https://example.com/cached.jpg",
        community_server_id=community_server.platform_id,
    )

    assert description1 == description2 == "Cached description"
    # LLMService should only be called once; second call uses VisionService cache
    assert mock_llm_service.describe_image.call_count == 1


@pytest.mark.asyncio
async def test_describe_image_rate_limit_retry(
    vision_service: VisionService,
    db_session: AsyncSession,
    setup_community_config,
    mock_llm_service,
):
    """Test that errors from LLMService propagate correctly."""
    community_server, _ = setup_community_config

    rate_limit_error = RateLimitError(
        "Rate limit exceeded",
        response=MagicMock(status_code=429),
        body={"error": {"message": "Rate limit exceeded"}},
    )

    # LLMService handles retries internally; VisionService just passes through errors
    mock_llm_service.describe_image = AsyncMock(side_effect=rate_limit_error)

    with pytest.raises(RateLimitError):
        await vision_service.describe_image(
            db=db_session,
            image_url="https://example.com/retry.jpg",
            community_server_id=community_server.platform_id,
        )

    # VisionService calls LLMService once (no retry logic in VisionService)
    assert mock_llm_service.describe_image.call_count == 1


@pytest.mark.asyncio
async def test_describe_image_no_config_error(
    vision_service: VisionService, db_session: AsyncSession
):
    """Test error when community server doesn't exist."""
    with pytest.raises(ValueError, match="Community server not found"):
        await vision_service.describe_image(
            db=db_session,
            image_url="https://example.com/test.jpg",
            community_server_id="nonexistent-guild",
        )


@pytest.mark.asyncio
async def test_describe_image_api_error(
    vision_service: VisionService,
    db_session: AsyncSession,
    setup_community_config,
    mock_llm_service,
):
    """Test handling of API errors."""
    community_server, _ = setup_community_config

    mock_llm_service.describe_image = AsyncMock(side_effect=Exception("API connection failed"))

    with pytest.raises(Exception, match="API connection failed"):
        await vision_service.describe_image(
            db=db_session,
            image_url="https://example.com/error.jpg",
            community_server_id=community_server.platform_id,
        )


@pytest.mark.asyncio
async def test_invalidate_cache(vision_service: VisionService):
    """Test cache invalidation (description cache only)."""
    vision_service.description_cache["test-hash"] = "test description"

    assert len(vision_service.description_cache) == 1

    vision_service.invalidate_cache()

    assert len(vision_service.description_cache) == 0


@pytest.mark.asyncio
async def test_cache_key_generation(vision_service: VisionService):
    """Test cache key generation with different parameters."""
    key1 = vision_service._get_cache_key("https://example.com/image.jpg", "auto", 300)
    key2 = vision_service._get_cache_key("https://example.com/image.jpg", "auto", 300)
    key3 = vision_service._get_cache_key("https://example.com/image.jpg", "high", 300)
    key4 = vision_service._get_cache_key("https://example.com/other.jpg", "auto", 300)

    assert key1 == key2
    assert key1 != key3
    assert key1 != key4
    assert len(key1) == 64
