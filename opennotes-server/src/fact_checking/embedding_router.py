"""API router for embedding generation and similarity search."""

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from openai import RateLimitError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_membership
from src.auth.dependencies import get_current_user_or_api_key
from src.config import settings
from src.database import get_db
from src.fact_checking.embedding_schemas import (
    SimilaritySearchRequest,
    SimilaritySearchResponse,
)
from src.fact_checking.embedding_service import EmbeddingService
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.llm_config.usage_tracker import LLMUsageTracker
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@lru_cache
def get_encryption_service() -> EncryptionService:
    """Get or create thread-safe encryption service singleton."""
    return EncryptionService(settings.ENCRYPTION_MASTER_KEY)


@lru_cache
def get_llm_service(
    encryption_service: Annotated[EncryptionService, Depends(get_encryption_service)],
) -> LLMService:
    """Get or create LLM service singleton."""
    client_manager = LLMClientManager(encryption_service)
    return LLMService(client_manager)


def get_embedding_service(
    llm_service: Annotated[LLMService, Depends(get_llm_service)],
) -> EmbeddingService:
    """Get embedding service with LLM service dependency."""
    return EmbeddingService(llm_service)


def get_usage_tracker(db: Annotated[AsyncSession, Depends(get_db)]) -> LLMUsageTracker:
    """Get LLM usage tracker instance."""
    return LLMUsageTracker(db)


async def get_community_server_uuid(
    db: AsyncSession, platform_id: str, platform: str = "discord"
) -> UUID | None:
    """
    Get community server UUID from platform ID.

    Args:
        db: Database session
        platform_id: Platform-specific identifier (e.g., Discord guild ID)
        platform: Platform type (default: discord)

    Returns:
        Community server UUID, or None if not found
    """
    result = await db.execute(
        select(CommunityServer.id).where(
            CommunityServer.platform == platform,
            CommunityServer.platform_id == platform_id,
            CommunityServer.is_active == True,
        )
    )
    return result.scalar_one_or_none()


@router.post("/similarity-search", response_model=SimilaritySearchResponse)
@limiter.limit("100/hour")
async def similarity_search(
    request: Request,  # Required by SlowAPI rate limiter
    search_request: SimilaritySearchRequest,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
    usage_tracker: Annotated[LLMUsageTracker, Depends(get_usage_tracker)],
) -> SimilaritySearchResponse:
    """
    Search for similar fact-check items using semantic similarity.

    Generates an embedding for the input text using the community server's
    OpenAI API key, then performs cosine similarity search against the
    fact_check_items table using pgvector.

    **Authorization:**
    - User must be an active member of the specified community server
    - Banned users are rejected with 403 Forbidden
    - External users without membership are rejected with 403 Forbidden
    - Prevents cost abuse by verifying community membership before API calls

    **Process:**
    1. Verifies user is authorized member of community server
    2. Validates community server has OpenAI configuration
    3. Generates embedding using text-embedding-3-small (1536 dimensions)
    4. Queries fact_check_items table with pgvector cosine similarity
    5. Filters by dataset_tags (e.g., 'snopes', 'politifact')
    6. Returns top matches above similarity threshold

    **Performance:**
    - Embedding generation: ~100-200ms (cached for 1 hour)
    - Similarity search: ~10-50ms (with pgvector indexing)

    **Rate Limiting:**
    - Per-user rate limit: 100 requests/hour
    - Per-community rate limits: Based on configured LLM usage limits
    - OpenAI API rate limits: Automatic detection with retry guidance

    **Audit Logging:**
    - All requests logged with user_id, profile_id, and community_server_id
    - Community role logged for authorization tracking
    - Cost attribution tracked per community server

    Args:
        request: FastAPI request object (required by SlowAPI rate limiter)
        search_request: Similarity search request with text and parameters
        current_user: Authenticated user or API key
        db: Database session
        embedding_service: Embedding service instance
        usage_tracker: LLM usage tracker instance

    Returns:
        List of matching fact-check items with similarity scores

    Raises:
        400: Invalid request parameters
        403: User not authorized (not a member, banned, or inactive)
        404: Community server or OpenAI configuration not found
        429: Rate limit exceeded (per-user, per-community, or OpenAI API)
        500: Internal server error
    """
    membership = await verify_community_membership(
        search_request.community_server_id, current_user, db, request
    )

    logger.info(
        f"User {current_user.id} performing similarity search",
        extra={
            "user_id": str(current_user.id),
            "profile_id": str(membership.profile_id),
            "community_server_id": search_request.community_server_id,
            "community_role": membership.role,
            "text_length": len(search_request.text),
            "dataset_tags": search_request.dataset_tags,
            "threshold": search_request.similarity_threshold,
        },
    )

    estimated_tokens = len(search_request.text) // 4

    try:
        community_server_uuid = await get_community_server_uuid(
            db, search_request.community_server_id
        )

        if community_server_uuid:
            allowed, reason = await usage_tracker.check_limits(
                community_server_id=community_server_uuid,
                provider="openai",
                estimated_tokens=estimated_tokens,
            )

            if not allowed:
                logger.warning(
                    "Community LLM usage limit exceeded",
                    extra={
                        "user_id": str(current_user.id),
                        "community_server_id": search_request.community_server_id,
                        "community_server_uuid": str(community_server_uuid),
                        "reason": reason,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=reason or "LLM usage limit exceeded",
                    headers={"Retry-After": "3600"},
                )
        response = await embedding_service.similarity_search(
            db=db,
            query_text=search_request.text,
            community_server_id=search_request.community_server_id,
            dataset_tags=search_request.dataset_tags,
            similarity_threshold=search_request.similarity_threshold,
            limit=search_request.limit,
        )

        logger.info(
            "Similarity search completed successfully",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": search_request.community_server_id,
                "matches_found": response.total_matches,
                "top_score": response.matches[0].similarity_score if response.matches else None,
            },
        )

        return response

    except RateLimitError as e:
        logger.error(
            "OpenAI API rate limit exceeded",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": search_request.community_server_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="OpenAI API rate limit exceeded. Please try again later.",
            headers={"Retry-After": "60"},
        ) from e
    except ValueError as e:
        logger.warning(
            "Similarity search validation error",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": search_request.community_server_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        logger.error(
            "Similarity search failed",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": search_request.community_server_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Similarity search failed: {e!s}",
        ) from e
