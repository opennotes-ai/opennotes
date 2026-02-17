"""JSON:API v2 similarity-searches router.

This module implements JSON:API 1.1 compliant endpoint for similarity searches.
It provides:
- POST /similarity-searches: Perform semantic similarity search on fact-check items
- Standard JSON:API response envelope structure
- Proper content-type headers (application/vnd.api+json)

Reference: https://jsonapi.org/format/
"""

import uuid
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from openai import RateLimitError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_membership
from src.auth.dependencies import get_current_user_or_api_key
from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema
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
            CommunityServer.platform_community_server_id == platform_id,
            CommunityServer.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


class SimilaritySearchCreateAttributes(StrictInputSchema):
    """Attributes for performing a similarity search via JSON:API."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Message text to search for similar fact-checks",
    )
    community_server_id: str = Field(
        ...,
        max_length=64,
        description="Community server (guild) ID",
    )
    dataset_tags: list[str] = Field(
        default_factory=lambda: ["snopes"],
        description="Dataset tags to filter by (e.g., ['snopes', 'politifact'])",
    )
    similarity_threshold: float = Field(
        default_factory=lambda: settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD,
        description="Minimum cosine similarity (0.0-1.0) for semantic search pre-filtering",
        ge=0.0,
        le=1.0,
    )
    score_threshold: float = Field(
        0.1,
        description="Minimum CC score (0.0-1.0) for post-fusion filtering",
        ge=0.0,
        le=1.0,
    )
    limit: int = Field(
        5,
        description="Maximum number of results to return",
        ge=1,
        le=20,
    )


class SimilaritySearchCreateData(BaseModel):
    """JSON:API data object for similarity search."""

    type: Literal["similarity-searches"] = Field(
        ..., description="Resource type must be 'similarity-searches'"
    )
    attributes: SimilaritySearchCreateAttributes


class SimilaritySearchJSONAPIRequest(BaseModel):
    """JSON:API request body for performing a similarity search."""

    data: SimilaritySearchCreateData


class FactCheckMatchResource(SQLAlchemySchema):
    """JSON:API-compatible fact-check match in search results."""

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
    embedding_provider: str | None = Field(None, description="LLM provider used for embedding")
    embedding_model: str | None = Field(None, description="Model name used for embedding")
    similarity_score: float = Field(..., description="CC fusion score (0.0-1.0)", ge=0.0, le=1.0)
    cosine_similarity: float | None = Field(
        None,
        description="Raw cosine similarity score (0.0-1.0), None when no semantic match",
        ge=0.0,
        le=1.0,
    )


class SimilaritySearchResultAttributes(SQLAlchemySchema):
    """Attributes for similarity search result."""

    matches: list[FactCheckMatchResource] = Field(..., description="Matching fact-check items")
    query_text: str = Field(..., description="Original query text")
    dataset_tags: list[str] = Field(..., description="Dataset tags used for filtering")
    similarity_threshold: float = Field(..., description="Cosine similarity threshold applied")
    score_threshold: float = Field(..., description="CC score threshold applied")
    total_matches: int = Field(..., description="Number of matches found")


class SimilaritySearchResultResource(BaseModel):
    """JSON:API resource object for similarity search results."""

    type: str = "similarity-search-results"
    id: str
    attributes: SimilaritySearchResultAttributes


class SimilaritySearchResultResponse(SQLAlchemySchema):
    """JSON:API response for similarity search results."""

    data: SimilaritySearchResultResource
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


@router.post(
    "/similarity-searches",
    response_class=JSONResponse,
    response_model=SimilaritySearchResultResponse,
)
@limiter.limit("100/minute")
async def similarity_search_jsonapi(
    request: HTTPRequest,
    body: SimilaritySearchJSONAPIRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
    usage_tracker: Annotated[LLMUsageTracker, Depends(get_usage_tracker)],
) -> JSONResponse:
    """Perform semantic similarity search on fact-check items.

    This endpoint:
    1. Verifies user is authorized member of community server
    2. Validates community server has OpenAI configuration
    3. Generates embedding using text-embedding-3-small (1536 dimensions)
    4. Queries fact_check_items table with pgvector cosine similarity
    5. Filters by dataset_tags (e.g., 'snopes', 'politifact')
    6. Returns top matches above similarity threshold

    JSON:API 1.1 action endpoint that returns search results.

    Rate Limiting:
    - Per-user rate limit: 100 requests/hour
    - Per-community rate limits: Based on configured LLM usage limits
    - OpenAI API rate limits: Automatic detection with retry guidance
    """
    try:
        attrs = body.data.attributes

        membership = await verify_community_membership(
            attrs.community_server_id, current_user, db, request
        )

        logger.info(
            f"User {current_user.id} performing similarity search via JSON:API",
            extra={
                "user_id": str(current_user.id),
                "profile_id": str(membership.profile_id),
                "community_server_id": attrs.community_server_id,
                "community_role": membership.role,
                "text_length": len(attrs.text),
                "dataset_tags": attrs.dataset_tags,
                "threshold": attrs.similarity_threshold,
            },
        )

        estimated_tokens = len(attrs.text) // 4

        community_server_uuid = await get_community_server_uuid(db, attrs.community_server_id)

        if community_server_uuid:
            allowed, reason = await usage_tracker.check_and_reserve_limits(
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

        response = await embedding_service.similarity_search(
            db=db,
            query_text=attrs.text,
            community_server_id=attrs.community_server_id,
            dataset_tags=attrs.dataset_tags,
            similarity_threshold=attrs.similarity_threshold,
            score_threshold=attrs.score_threshold,
            limit=attrs.limit,
        )

        match_resources = [
            FactCheckMatchResource(
                id=str(match.id),
                dataset_name=match.dataset_name,
                dataset_tags=match.dataset_tags,
                title=match.title,
                content=match.content,
                summary=match.summary,
                rating=match.rating,
                source_url=match.source_url,
                published_date=match.published_date,
                author=match.author,
                embedding_provider=match.embedding_provider,
                embedding_model=match.embedding_model,
                similarity_score=match.similarity_score,
                cosine_similarity=match.cosine_similarity,
            )
            for match in response.matches
        ]

        result = SimilaritySearchResultResource(
            type="similarity-search-results",
            id=str(uuid.uuid4()),
            attributes=SimilaritySearchResultAttributes(
                matches=match_resources,
                query_text=response.query_text,
                dataset_tags=response.dataset_tags,
                similarity_threshold=response.similarity_threshold,
                score_threshold=response.score_threshold,
                total_matches=response.total_matches,
            ),
        )

        logger.info(
            "Similarity search completed successfully via JSON:API",
            extra={
                "user_id": str(current_user.id),
                "community_server_id": attrs.community_server_id,
                "matches_found": response.total_matches,
                "top_score": response.matches[0].similarity_score if response.matches else None,
            },
        )

        json_response = SimilaritySearchResultResponse(
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
            "Similarity search authorization error (JSON:API)",
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
            "Similarity search validation error (JSON:API)",
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
            "Similarity search failed (JSON:API)",
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
            "Similarity search failed. Please try again later.",
        )
