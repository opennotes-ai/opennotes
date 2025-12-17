"""JSON:API v2 hybrid-searches router.

This module implements JSON:API 1.1 compliant endpoint for hybrid searches.
It provides:
- POST /hybrid-searches: Perform hybrid search (FTS + semantic) on fact-check items
- Standard JSON:API response envelope structure
- Proper content-type headers (application/vnd.api+json)

Hybrid search combines PostgreSQL full-text search with pgvector semantic
similarity using Reciprocal Rank Fusion (RRF) for result ranking.

Reference: https://jsonapi.org/format/
"""

import time
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from openai import RateLimitError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_membership
from src.auth.dependencies import get_current_user_or_api_key
from src.common.base_schemas import StrictInputSchema
from src.common.jsonapi import (
    JSONAPI_CONTENT_TYPE,
    JSONAPILinks,
)
from src.common.jsonapi import (
    create_error_response as create_error_response_model,
)
from src.config import settings
from src.database import get_db
from src.fact_checking.embedding_service import EmbeddingService
from src.fact_checking.repository import hybrid_search
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.llm_config.usage_tracker import LLMUsageTracker
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


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
    """Get community server UUID from platform ID.

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
            CommunityServer.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


class HybridSearchCreateAttributes(StrictInputSchema):
    """Attributes for performing a hybrid search via JSON:API."""

    text: str = Field(
        ...,
        min_length=3,
        max_length=50000,
        description="Query text to search for (minimum 3 characters). Uses hybrid search combining FTS and semantic similarity.",
    )
    community_server_id: str = Field(
        ...,
        max_length=64,
        description="Community server (guild) ID",
    )
    limit: int = Field(
        10,
        description="Maximum number of results to return",
        ge=1,
        le=20,
    )


class HybridSearchCreateData(BaseModel):
    """JSON:API data object for hybrid search."""

    type: Literal["hybrid-searches"] = Field(
        ..., description="Resource type must be 'hybrid-searches'"
    )
    attributes: HybridSearchCreateAttributes


class HybridSearchRequest(BaseModel):
    """JSON:API request body for performing a hybrid search."""

    data: HybridSearchCreateData


class HybridSearchMatchResource(BaseModel):
    """JSON:API-compatible fact-check match in hybrid search results."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Fact-check item UUID")
    dataset_name: str = Field(..., description="Source dataset (e.g., 'snopes')")
    dataset_tags: list[str] = Field(..., description="Dataset tags")
    title: str = Field(..., description="Fact-check article title")
    content: str = Field(..., description="Fact-check content")
    summary: str | None = Field(None, description="Brief summary")
    rating: str | None = Field(None, description="Fact-check verdict")
    source_url: str | None = Field(None, description="URL to original article")
    published_date: datetime | None = Field(None, description="Publication date")
    author: str | None = Field(None, description="Author name")
    rrf_score: float = Field(
        ...,
        description="Reciprocal Rank Fusion score combining FTS and semantic rankings",
        ge=0.0,
    )


class HybridSearchResultAttributes(BaseModel):
    """Attributes for hybrid search result."""

    model_config = ConfigDict(from_attributes=True)

    matches: list[HybridSearchMatchResource] = Field(
        ..., description="Matching fact-check items ranked by RRF score"
    )
    query_text: str = Field(..., description="Original query text")
    total_matches: int = Field(..., description="Number of matches found")


class HybridSearchResultResource(BaseModel):
    """JSON:API resource object for hybrid search results."""

    type: str = "hybrid-search-results"
    id: str
    attributes: HybridSearchResultAttributes


class HybridSearchResultResponse(BaseModel):
    """JSON:API response for hybrid search results."""

    model_config = ConfigDict(from_attributes=True)

    data: HybridSearchResultResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


def create_error_response(
    status_code: int,
    title: str,
    detail: str | None = None,
) -> JSONResponse:
    """Create a JSON:API formatted error response as a JSONResponse."""
    error_response = create_error_response_model(
        status_code=status_code,
        title=title,
        detail=detail,
    )
    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(by_alias=True),
        media_type=JSONAPI_CONTENT_TYPE,
    )


@router.post("/hybrid-searches", response_class=JSONResponse)
@limiter.limit("100/hour")
async def hybrid_search_jsonapi(
    request: HTTPRequest,
    body: HybridSearchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
    usage_tracker: Annotated[LLMUsageTracker, Depends(get_usage_tracker)],
) -> JSONResponse:
    """Perform hybrid search on fact-check items combining FTS and semantic similarity.

    This endpoint:
    1. Verifies user is authorized member of community server
    2. Validates community server has OpenAI configuration
    3. Generates embedding using text-embedding-3-small (1536 dimensions)
    4. Executes hybrid search combining:
       - PostgreSQL full-text search (ts_rank_cd with weighted tsvector)
       - pgvector embedding similarity (cosine distance)
    5. Uses Reciprocal Rank Fusion (RRF) to combine rankings
    6. Returns top matches ranked by combined RRF score

    The RRF formula: score = 1/(k + rank_semantic) + 1/(k + rank_keyword)
    where k=60 is the standard RRF constant.

    JSON:API 1.1 action endpoint that returns search results.

    Rate Limiting:
    - Per-user rate limit: 100 requests/hour
    - Per-community rate limits: Based on configured LLM usage limits
    - OpenAI API rate limits: Automatic detection with retry guidance
    """
    total_start = time.perf_counter()
    try:
        attrs = body.data.attributes

        membership = await verify_community_membership(
            attrs.community_server_id, current_user, db, request
        )

        logger.info(
            f"User {current_user.id} performing hybrid search via JSON:API",
            extra={
                "user_id": str(current_user.id),
                "profile_id": str(membership.profile_id),
                "community_server_id": attrs.community_server_id,
                "community_role": membership.role,
                "text_length": len(attrs.text),
                "limit": attrs.limit,
            },
        )

        estimated_tokens = len(attrs.text) // 4

        community_server_uuid = await get_community_server_uuid(db, attrs.community_server_id)

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
                        "community_server_id": attrs.community_server_id,
                        "community_server_uuid": str(community_server_uuid),
                        "reason": reason,
                    },
                )
                return create_error_response(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Rate Limit Exceeded",
                    reason or "LLM usage limit exceeded",
                )

        embedding_start = time.perf_counter()
        query_embedding = await embedding_service.generate_embedding(
            db=db,
            text=attrs.text,
            community_server_id=attrs.community_server_id,
        )
        embedding_duration_ms = (time.perf_counter() - embedding_start) * 1000

        search_start = time.perf_counter()
        search_results = await hybrid_search(
            session=db,
            query_text=attrs.text,
            query_embedding=query_embedding,
            limit=attrs.limit,
        )
        search_duration_ms = (time.perf_counter() - search_start) * 1000

        match_resources = [
            HybridSearchMatchResource(
                id=str(result.item.id),
                dataset_name=result.item.dataset_name,
                dataset_tags=result.item.dataset_tags,
                title=result.item.title,
                content=result.item.content,
                summary=result.item.summary,
                rating=result.item.rating,
                source_url=result.item.source_url,
                published_date=result.item.published_date,
                author=result.item.author,
                rrf_score=result.rrf_score,
            )
            for result in search_results
        ]

        result = HybridSearchResultResource(
            type="hybrid-search-results",
            id=str(uuid.uuid4()),
            attributes=HybridSearchResultAttributes(
                matches=match_resources,
                query_text=attrs.text,
                total_matches=len(search_results),
            ),
        )

        total_duration_ms = (time.perf_counter() - total_start) * 1000
        logger.info(
            "Hybrid search completed successfully via JSON:API",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": attrs.community_server_id,
                "matches_found": len(search_results),
                "total_duration_ms": round(total_duration_ms, 2),
                "embedding_duration_ms": round(embedding_duration_ms, 2),
                "search_duration_ms": round(search_duration_ms, 2),
            },
        )

        json_response = HybridSearchResultResponse(
            data=result,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=json_response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except RateLimitError as e:
        logger.error(
            "OpenAI API rate limit exceeded",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": body.data.attributes.community_server_id,
                "error": str(e),
            },
        )
        return create_error_response(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate Limit Exceeded",
            "OpenAI API rate limit exceeded. Please try again later.",
        )
    except HTTPException as e:
        logger.warning(
            "Hybrid search authorization error (JSON:API)",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": body.data.attributes.community_server_id,
                "status_code": e.status_code,
                "detail": e.detail,
            },
        )
        return create_error_response(
            e.status_code,
            "Forbidden" if e.status_code == 403 else "Not Found",
            e.detail,
        )
    except ValueError as e:
        logger.warning(
            "Hybrid search validation error (JSON:API)",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": body.data.attributes.community_server_id,
                "error": str(e),
            },
        )
        return create_error_response(
            status.HTTP_404_NOT_FOUND,
            "Not Found",
            str(e),
        )
    except Exception as e:
        logger.error(
            "Hybrid search failed (JSON:API)",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": body.data.attributes.community_server_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            f"Hybrid search failed: {e!s}",
        )
