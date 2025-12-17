"""API router for hybrid search combining text and semantic search."""

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
from src.fact_checking.embedding_service import EmbeddingService
from src.fact_checking.repository import hybrid_search
from src.fact_checking.search_schemas import (
    FactCheckSearchResult,
    HybridSearchRequest,
    HybridSearchResponse,
)
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.llm_config.usage_tracker import LLMUsageTracker
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(prefix="/fact-check", tags=["fact-check"])


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
    """Get community server UUID from platform ID."""
    result = await db.execute(
        select(CommunityServer.id).where(
            CommunityServer.platform == platform,
            CommunityServer.platform_id == platform_id,
            CommunityServer.is_active == True,
        )
    )
    return result.scalar_one_or_none()


@router.post("/search", response_model=HybridSearchResponse)
@limiter.limit("100/hour")
async def search_fact_checks(
    request: Request,
    search_request: HybridSearchRequest,
    community_server_id: str,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
    usage_tracker: Annotated[LLMUsageTracker, Depends(get_usage_tracker)],
) -> HybridSearchResponse:
    """
    Search fact-check items using hybrid text + semantic search.

    Combines full-text search (PostgreSQL FTS) with semantic similarity
    (pgvector) using Reciprocal Rank Fusion (RRF) for optimal relevance.

    The RRF formula: score = 1/(k + rank_semantic) + 1/(k + rank_keyword)
    where k=60 is the standard RRF constant.

    **Authorization:**
    - User must be an active member of the specified community server
    - Banned users are rejected with 403 Forbidden

    **Process:**
    1. Verifies user is authorized member of community server
    2. Generates embedding for query text using community's API key
    3. Performs hybrid search combining FTS and vector similarity
    4. Returns results ranked by combined RRF score

    Args:
        request: FastAPI request object (required for rate limiter)
        search_request: Search request with query and parameters
        community_server_id: Discord guild ID for API key lookup
        current_user: Authenticated user
        db: Database session
        embedding_service: Service for generating embeddings
        usage_tracker: LLM usage tracker

    Returns:
        Search results ranked by combined text + semantic relevance

    Raises:
        403: User not authorized (not a member or banned)
        404: Community server not found
        429: Rate limit exceeded
        500: Internal server error
    """
    membership = await verify_community_membership(community_server_id, current_user, db, request)

    logger.info(
        f"User {current_user.id} performing hybrid search",
        extra={
            "user_id": str(current_user.id),
            "profile_id": str(membership.profile_id),
            "community_server_id": community_server_id,
            "community_role": membership.role,
            "query_length": len(search_request.query),
            "limit": search_request.limit,
        },
    )

    estimated_tokens = len(search_request.query) // 4

    try:
        community_server_uuid = await get_community_server_uuid(db, community_server_id)

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
                        "community_server_id": community_server_id,
                        "reason": reason,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=reason or "LLM usage limit exceeded",
                    headers={"Retry-After": "3600"},
                )

        query_embedding = await embedding_service.generate_embedding(
            db=db,
            text=search_request.query,
            community_server_id=community_server_id,
        )

        results = await hybrid_search(
            session=db,
            query_text=search_request.query,
            query_embedding=query_embedding,
            limit=search_request.limit,
        )

        search_results = [
            FactCheckSearchResult(
                id=item.id,
                title=item.title,
                content=item.content,
                summary=item.summary,
                source_url=item.source_url,
                rating=item.rating,
                dataset_name=item.dataset_name,
                dataset_tags=item.dataset_tags,
                published_date=item.published_date,
                author=item.author,
            )
            for item in results
        ]

        logger.info(
            "Hybrid search completed successfully",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": community_server_id,
                "results_found": len(search_results),
                "query_length": len(search_request.query),
            },
        )

        return HybridSearchResponse(
            results=search_results,
            query=search_request.query,
            total=len(search_results),
        )

    except RateLimitError as e:
        logger.error(
            "OpenAI API rate limit exceeded",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": community_server_id,
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
            "Hybrid search validation error",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": community_server_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        logger.error(
            "Hybrid search failed",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": community_server_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {e!s}",
        ) from e
