"""API router for LLM configuration management."""

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_admin_by_uuid
from src.config import settings
from src.database import get_db
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.models import CommunityServer, CommunityServerLLMConfig
from src.llm_config.providers.factory import LLMProviderFactory
from src.llm_config.schemas import (
    LLMConfigCreate,
    LLMConfigResponse,
    LLMConfigTestRequest,
    LLMConfigTestResponse,
    LLMConfigUpdate,
    LLMUsageStatsResponse,
)
from src.llm_config.usage_tracker import LLMUsageTracker
from src.monitoring import get_logger
from src.users.profile_models import CommunityMember

router = APIRouter(prefix="/community-servers", tags=["llm-config"])
logger = get_logger(__name__)

# Safe error messages for API key validation failures
# These prevent leaking sensitive information from provider error messages
SAFE_ERROR_MESSAGES = {
    "invalid_key": "The provided API key is invalid",
    "rate_limit": "API key validation failed due to rate limiting",
    "network": "Unable to validate API key due to network error",
    "permission": "API key lacks required permissions",
    "generic": "API key validation failed. Please check your key and try again.",
}


def _get_default_model_for_provider(provider: str) -> str:
    """Get the default model for a provider from settings.

    Extracts the model name from DEFAULT_FULL_MODEL for OpenAI,
    otherwise returns provider-specific defaults.
    """
    if provider == "openai":
        full_model = settings.DEFAULT_FULL_MODEL
        return full_model.split("/")[-1] if "/" in full_model else full_model
    return "claude-3-opus-20240229" if provider == "anthropic" else "unknown"


@lru_cache
def get_encryption_service() -> EncryptionService:
    """Get thread-safe encryption service singleton dependency."""
    return EncryptionService(settings.ENCRYPTION_MASTER_KEY)


def get_llm_client_manager(
    encryption_service: Annotated[EncryptionService, Depends(get_encryption_service)],
) -> LLMClientManager:
    """Get LLM client manager dependency."""
    return LLMClientManager(encryption_service)


@router.post(
    "/{community_server_id}/llm-config",
    response_model=LLMConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_llm_config(
    community_server_id: UUID,
    config: LLMConfigCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    encryption_service: Annotated[EncryptionService, Depends(get_encryption_service)],
    _membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],
) -> LLMConfigResponse:
    """
    Create a new LLM configuration for a community server.

    Requires admin or moderator access to the community server.
    """
    result = await db.execute(
        select(CommunityServer).where(CommunityServer.id == community_server_id)
    )
    community_server = result.scalar_one_or_none()
    if not community_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server {community_server_id} not found",
        )

    result = await db.execute(
        select(CommunityServerLLMConfig).where(
            CommunityServerLLMConfig.community_server_id == community_server_id,
            CommunityServerLLMConfig.provider == config.provider,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Configuration for provider '{config.provider}' already exists",
        )

    provider = None
    try:
        default_model = config.settings.get(
            "default_model", _get_default_model_for_provider(config.provider)
        )
        provider = LLMProviderFactory.create(
            config.provider,
            config.api_key,
            default_model,
            config.settings,
        )
        is_valid = await provider.validate_api_key()
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=SAFE_ERROR_MESSAGES["invalid_key"],
            )
    except HTTPException:
        # Re-raise HTTPExceptions (these are already safe)
        raise
    except ValueError as e:
        # ValueError usually indicates invalid key format
        logger.warning(
            f"Invalid API key format for provider {config.provider}",
            extra={"provider": config.provider, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=SAFE_ERROR_MESSAGES["invalid_key"],
        )
    except ConnectionError as e:
        # Network-related errors
        logger.error(
            f"Network error validating API key for provider {config.provider}",
            extra={"provider": config.provider, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=SAFE_ERROR_MESSAGES["network"],
        )
    except Exception as e:
        # Catch-all for unexpected errors - log details but return generic message
        logger.error(
            f"API key validation failed for provider {config.provider}",
            exc_info=True,
            extra={"provider": config.provider, "error_type": type(e).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=SAFE_ERROR_MESSAGES["generic"],
        )
    finally:
        if provider:
            await provider.close()

    encrypted_key, key_id, preview = encryption_service.encrypt_api_key(config.api_key)

    db_config = CommunityServerLLMConfig(
        community_server_id=community_server_id,
        provider=config.provider,
        api_key_encrypted=encrypted_key,
        encryption_key_id=key_id,
        api_key_preview=preview,
        enabled=config.enabled,
        settings=config.settings,
        daily_request_limit=config.daily_request_limit,
        monthly_request_limit=config.monthly_request_limit,
        daily_token_limit=config.daily_token_limit,
        monthly_token_limit=config.monthly_token_limit,
    )
    db.add(db_config)
    await db.commit()
    await db.refresh(db_config)

    return _to_response(db_config)


@router.get(
    "/{community_server_id}/llm-config",
    response_model=list[LLMConfigResponse],
)
async def list_llm_configs(
    community_server_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],
) -> list[LLMConfigResponse]:
    """
    List all LLM configurations for a community server.

    Requires admin or moderator access to the community server.
    """
    result = await db.execute(
        select(CommunityServerLLMConfig).where(
            CommunityServerLLMConfig.community_server_id == community_server_id
        )
    )
    configs = result.scalars().all()
    return [_to_response(c) for c in configs]


@router.get(
    "/{community_server_id}/llm-config/{provider}",
    response_model=LLMConfigResponse,
)
async def get_llm_config(
    community_server_id: UUID,
    provider: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],
) -> LLMConfigResponse:
    """
    Get a specific LLM configuration.

    Requires admin or moderator access to the community server.
    """
    config = await _get_config_or_404(db, community_server_id, provider)
    return _to_response(config)


@router.patch(
    "/{community_server_id}/llm-config/{provider}",
    response_model=LLMConfigResponse,
)
async def update_llm_config(
    community_server_id: UUID,
    provider: str,
    update: LLMConfigUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    encryption_service: Annotated[EncryptionService, Depends(get_encryption_service)],
    client_manager: Annotated[LLMClientManager, Depends(get_llm_client_manager)],
    _membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],
) -> LLMConfigResponse:
    """
    Update an existing LLM configuration.

    Requires admin or moderator access to the community server.
    """
    config = await _get_config_or_404(db, community_server_id, provider)

    if update.api_key is not None:
        encrypted_key, key_id, preview = encryption_service.encrypt_api_key(update.api_key)
        config.api_key_encrypted = encrypted_key
        config.encryption_key_id = key_id
        config.api_key_preview = preview

    if update.enabled is not None:
        config.enabled = update.enabled
    if update.settings is not None:
        config.settings = update.settings
    if update.daily_request_limit is not None:
        config.daily_request_limit = update.daily_request_limit
    if update.monthly_request_limit is not None:
        config.monthly_request_limit = update.monthly_request_limit
    if update.daily_token_limit is not None:
        config.daily_token_limit = update.daily_token_limit
    if update.monthly_token_limit is not None:
        config.monthly_token_limit = update.monthly_token_limit

    await db.commit()
    await db.refresh(config)

    client_manager.invalidate_cache(community_server_id, provider)

    return _to_response(config)


@router.delete(
    "/{community_server_id}/llm-config/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_llm_config(
    community_server_id: UUID,
    provider: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    client_manager: Annotated[LLMClientManager, Depends(get_llm_client_manager)],
    _membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],
) -> None:
    """
    Delete an LLM configuration.

    Requires admin or moderator access to the community server.
    """
    config = await _get_config_or_404(db, community_server_id, provider)
    await db.delete(config)
    await db.commit()

    client_manager.invalidate_cache(community_server_id, provider)


@router.post(
    "/{community_server_id}/llm-config/test",
    response_model=LLMConfigTestResponse,
)
async def test_llm_config(
    community_server_id: UUID,
    test_request: LLMConfigTestRequest,
    _membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],  # noqa: PT019 (permission check, not injected value)
) -> LLMConfigTestResponse:
    """
    Test an LLM configuration without saving it.

    Validates the API key and checks connectivity.
    Requires admin or moderator access to the community server.
    """
    provider = None
    try:
        default_model = test_request.settings.get(
            "default_model", _get_default_model_for_provider(test_request.provider)
        )
        provider = LLMProviderFactory.create(
            test_request.provider,
            test_request.api_key,
            default_model,
            test_request.settings,
        )
        is_valid = await provider.validate_api_key()
        return LLMConfigTestResponse(valid=is_valid)
    except ValueError as e:
        # Invalid key format
        logger.warning(
            f"Invalid API key format for provider {test_request.provider}",
            extra={"provider": test_request.provider, "error": str(e)},
        )
        return LLMConfigTestResponse(valid=False, error_message=SAFE_ERROR_MESSAGES["invalid_key"])
    except ConnectionError as e:
        # Network errors
        logger.error(
            f"Network error testing API key for provider {test_request.provider}",
            extra={"provider": test_request.provider, "error": str(e)},
        )
        return LLMConfigTestResponse(valid=False, error_message=SAFE_ERROR_MESSAGES["network"])
    except Exception as e:
        # Log detailed error for debugging, return generic message to user
        logger.error(
            f"API key test failed for provider {test_request.provider}",
            exc_info=True,
            extra={
                "provider": test_request.provider,
                "error_type": type(e).__name__,
            },
        )
        return LLMConfigTestResponse(valid=False, error_message=SAFE_ERROR_MESSAGES["generic"])
    finally:
        if provider:
            await provider.close()


@router.get(
    "/{community_server_id}/llm-config/{provider}/usage",
    response_model=LLMUsageStatsResponse,
)
async def get_usage_stats(
    community_server_id: UUID,
    provider: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _membership: Annotated[CommunityMember, Depends(verify_community_admin_by_uuid)],
) -> LLMUsageStatsResponse:
    """
    Get usage statistics for an LLM configuration.

    Requires admin or moderator access to the community server.
    """
    tracker = LLMUsageTracker(db)
    stats = await tracker.get_usage_stats(community_server_id, provider)

    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration for provider '{provider}' not found",
        )

    return LLMUsageStatsResponse(**stats)


async def _get_config_or_404(
    db: AsyncSession, community_server_id: UUID, provider: str
) -> CommunityServerLLMConfig:
    """Get configuration or raise 404."""
    result = await db.execute(
        select(CommunityServerLLMConfig).where(
            CommunityServerLLMConfig.community_server_id == community_server_id,
            CommunityServerLLMConfig.provider == provider,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration for provider '{provider}' not found",
        )
    return config


def _to_response(config: CommunityServerLLMConfig) -> LLMConfigResponse:
    """Convert database model to response schema."""
    return LLMConfigResponse(
        id=config.id,
        community_server_id=config.community_server_id,
        provider=config.provider,
        api_key_preview=config.api_key_preview,
        enabled=config.enabled,
        settings=config.settings,
        daily_request_limit=config.daily_request_limit,
        monthly_request_limit=config.monthly_request_limit,
        daily_token_limit=config.daily_token_limit,
        monthly_token_limit=config.monthly_token_limit,
        daily_spend_limit=config.daily_spend_limit,
        monthly_spend_limit=config.monthly_spend_limit,
        current_daily_requests=config.current_daily_requests,
        current_monthly_requests=config.current_monthly_requests,
        current_daily_tokens=config.current_daily_tokens,
        current_monthly_tokens=config.current_monthly_tokens,
        current_daily_spend=config.current_daily_spend,
        current_monthly_spend=config.current_monthly_spend,
        last_daily_reset=config.last_daily_reset,
        last_monthly_reset=config.last_monthly_reset,
        created_at=config.created_at,
        updated_at=config.updated_at,
        created_by=config.created_by,
    )
