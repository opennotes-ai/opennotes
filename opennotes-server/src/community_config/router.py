import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request as HTTPRequest
from pydantic import Field, ValidationInfo, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    get_community_server_by_platform_id,
    verify_community_admin,
    verify_community_membership,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema
from src.community_config.models import CommunityConfig
from src.database import get_db
from src.monitoring import get_logger
from src.users.models import User
from src.users.profile_models import CommunityMember

logger = get_logger(__name__)

router = APIRouter(tags=["community-config"])


CONFIG_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MAX_KEY_LENGTH = 128
MAX_VALUE_LENGTH = 10240

# Valid configuration keys and their expected value formats
# This serves as documentation and can be used for future allowlist implementation
VALID_CONFIG_KEYS = {
    # Feature flags (boolean: true/false, 1/0, yes/no)
    "notes_enabled": "boolean",
    "ratings_enabled": "boolean",
    "moderation_enabled": "boolean",
    # Rate limiting (numeric: 0-1000000)
    "rate_limit_per_hour": "numeric",
    "rate_limit_per_day": "numeric",
    "max_notes_per_user": "numeric",
    # Thresholds and limits (numeric: 0-1000000)
    "min_rating_threshold": "numeric",
    "max_note_length": "numeric",
    "session_timeout": "numeric",
    # Webhooks and URLs (must start with http:// or https://)
    "webhook_url": "url",
    "notification_endpoint": "url",
    # Note: Additional keys are allowed beyond this list for extensibility
}


class SetConfigRequest(StrictInputSchema):
    key: str = Field(
        ...,
        description="Configuration key to set (snake_case: lowercase letters, numbers, underscores, must start with letter)",
        min_length=1,
        max_length=MAX_KEY_LENGTH,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    value: str = Field(
        ..., description="Configuration value (stringified)", max_length=MAX_VALUE_LENGTH
    )

    @field_validator("key")
    @classmethod
    def validate_key_pattern(cls, v: str) -> str:
        if not v:
            raise ValueError("Configuration key cannot be empty")
        if not CONFIG_KEY_PATTERN.match(v):
            raise ValueError(
                "Configuration key must be snake_case (lowercase letters, numbers, underscores only, "
                "starting with a letter). Examples: 'notes_enabled', 'rate_limit_per_hour'"
            )
        return v

    @field_validator("value")
    @classmethod
    def validate_value_not_empty(cls, v: str, info: ValidationInfo) -> str:
        if v is None:
            raise ValueError("Configuration value cannot be None")

        # Sanitize dangerous characters that could be used for injection attacks
        dangerous_chars = ["<", ">", '"', "'", "`", "$", ";", "|", "&", "\x00"]
        if any(char in v for char in dangerous_chars):
            raise ValueError(
                f"Configuration value contains potentially unsafe characters. "
                f"Prohibited characters: {', '.join(repr(c) for c in dangerous_chars)}"
            )

        # Type-based validation based on config key
        key = info.data.get("key", "")

        # Numeric values (rate limits, counts, thresholds)
        if any(
            keyword in key
            for keyword in ["limit", "count", "max", "min", "threshold", "timeout", "interval"]
        ):
            if not v.isdigit():
                raise ValueError(f"Configuration key '{key}' expects a numeric value, got: {v}")
            # Validate reasonable range for numeric values
            try:
                numeric_value = int(v)
                if numeric_value < 0:
                    raise ValueError(f"Configuration key '{key}' must be a non-negative number")
                if numeric_value > 1_000_000:
                    raise ValueError(f"Configuration key '{key}' value too large (max 1,000,000)")
            except ValueError:
                raise

        # Boolean values (enabled/disabled flags)
        if any(
            keyword in key for keyword in ["enabled", "disabled", "active", "allow"]
        ) and v.lower() not in ["true", "false", "1", "0", "yes", "no"]:
            raise ValueError(
                f"Configuration key '{key}' expects a boolean value (true/false, 1/0, yes/no), got: {v}"
            )

        # URL values (webhooks, endpoints)
        if "url" in key or "webhook" in key or "endpoint" in key:
            if not v.startswith(("http://", "https://")):
                raise ValueError(
                    f"Configuration key '{key}' expects a valid URL (must start with http:// or https://)"
                )
            # Additional URL safety checks
            if any(char in v for char in [" ", "\n", "\r", "\t"]):
                raise ValueError(f"Configuration key '{key}' URL contains whitespace characters")

        return v


class CommunityConfigResponse(SQLAlchemySchema):
    community_server_id: UUID
    config: dict[str, str] = Field(
        default_factory=dict, description="Community server configuration key-value pairs"
    )


@router.get("/community-config/{community_server_id}", response_model=CommunityConfigResponse)
async def get_community_config(
    community_server_id: str,
    request: HTTPRequest,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CommunityConfigResponse:
    """
    Get all configuration settings for a specific community server.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server.

    Returns a dictionary of config_key: config_value pairs for the community server.
    If no configuration exists, returns an empty dictionary.

    Requires: User must be a member of the community server.
    Service accounts can view all configs.
    """
    # Verify community membership (service accounts bypass)
    if not is_service_account(current_user):
        await verify_community_membership(community_server_id, current_user, db, request)

    community_server = await get_community_server_by_platform_id(
        db=db,
        community_server_id=community_server_id,
        platform="discord",
        auto_create=False,
    )
    if not community_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server not found for platform ID: {community_server_id}",
        )

    logger.debug(
        f"User {current_user.id} requested config for community server {community_server.id}"
    )

    result = await db.execute(
        select(CommunityConfig).where(CommunityConfig.community_server_id == community_server.id)
    )
    configs = result.scalars().all()

    config_dict = {config.config_key: config.config_value for config in configs}

    return CommunityConfigResponse(community_server_id=community_server.id, config=config_dict)


@router.put("/community-config/{community_server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_community_config(
    community_server_id: str,
    request_body: SetConfigRequest,
    membership: Annotated[CommunityMember, Depends(verify_community_admin)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """
    Set or update a configuration value for a specific community server.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server. If the key already exists, it will be updated.
    Otherwise, a new entry is created. The updated_by field tracks who made the change
    for audit purposes.

    Requires: User must be an admin or moderator of the community server.
    """
    community_server = await get_community_server_by_platform_id(
        db=db,
        community_server_id=community_server_id,
        platform="discord",
        auto_create=False,
    )
    if not community_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server not found for platform ID: {community_server_id}",
        )

    logger.info(
        f"User {current_user.id} (profile {membership.profile_id}, role {membership.role}) "
        f"setting config for community server {community_server.id}: "
        f"{request_body.key}={request_body.value}"
    )

    # Check if config already exists
    result = await db.execute(
        select(CommunityConfig).where(
            CommunityConfig.community_server_id == community_server.id,
            CommunityConfig.config_key == request_body.key,
        )
    )
    existing_config = result.scalar_one_or_none()

    if existing_config:
        # Update existing config
        existing_config.config_value = request_body.value
        existing_config.updated_by = current_user.id
    else:
        # Create new config
        new_config = CommunityConfig(
            community_server_id=community_server.id,
            config_key=request_body.key,
            config_value=request_body.value,
            updated_by=current_user.id,
        )
        db.add(new_config)

    await db.commit()


@router.delete("/community-config/{community_server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def reset_community_config(
    community_server_id: str,
    membership: Annotated[CommunityMember, Depends(verify_community_admin)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    config_key: str | None = Query(
        None, description="Specific config key to reset (leave empty to reset all)"
    ),
) -> None:
    """
    Reset community server configuration to defaults.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server. If config_key is provided, only that specific
    key is deleted. If config_key is None, all configuration for the community server
    is deleted.

    Requires: User must be an admin or moderator of the community server.
    """
    community_server = await get_community_server_by_platform_id(
        db=db,
        community_server_id=community_server_id,
        platform="discord",
        auto_create=False,
    )
    if not community_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community server not found for platform ID: {community_server_id}",
        )

    if config_key:
        logger.info(
            f"User {current_user.id} (profile {membership.profile_id}, role {membership.role}) "
            f"resetting config key {config_key} for community server {community_server.id}"
        )
        await db.execute(
            delete(CommunityConfig).where(
                CommunityConfig.community_server_id == community_server.id,
                CommunityConfig.config_key == config_key,
            )
        )
    else:
        logger.info(
            f"User {current_user.id} (profile {membership.profile_id}, role {membership.role}) "
            f"resetting all config for community server {community_server.id}"
        )
        await db.execute(
            delete(CommunityConfig).where(
                CommunityConfig.community_server_id == community_server.id
            )
        )

    await db.commit()
