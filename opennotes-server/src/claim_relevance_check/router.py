"""JSON:API v2 claim-relevance-checks router.

Implements JSON:API 1.1 compliant endpoint for claim relevance checking.
POST /claim-relevance-checks: Check if a fact-check match is relevant to a user message.

Reference: https://jsonapi.org/format/
"""

import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.claim_relevance_check.schemas import (
    ClaimRelevanceCheckRequest,
    ClaimRelevanceCheckResponse,
    ClaimRelevanceCheckResultAttributes,
    ClaimRelevanceCheckResultResource,
    RelevanceOutcome,
)
from src.claim_relevance_check.service import ClaimRelevanceService
from src.common.jsonapi import (
    JSONAPI_CONTENT_TYPE,
)
from src.common.jsonapi import (
    create_error_response as create_error_response_model,
)
from src.config import settings
from src.database import get_db
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.service import LLMService
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter()


@lru_cache
def _get_encryption_service() -> EncryptionService:
    """Get or create thread-safe encryption service singleton."""
    return EncryptionService(settings.ENCRYPTION_MASTER_KEY)


@lru_cache
def _get_llm_service() -> LLMService:
    """Get or create LLM service singleton."""
    encryption_service = _get_encryption_service()
    client_manager = LLMClientManager(encryption_service)
    return LLMService(client_manager)


def _get_relevance_service(
    llm_service: Annotated[LLMService, Depends(_get_llm_service)],
) -> ClaimRelevanceService:
    """Get claim relevance service with LLM service dependency."""
    return ClaimRelevanceService(llm_service)


def _create_error_response(
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


SHOULD_FLAG_OUTCOMES = {
    RelevanceOutcome.RELEVANT,
    RelevanceOutcome.INDETERMINATE,
    RelevanceOutcome.CONTENT_FILTERED,
}


@router.post(
    "/claim-relevance-checks",
    response_class=JSONResponse,
    response_model=ClaimRelevanceCheckResponse,
)
@limiter.limit("100/minute")
async def create_claim_relevance_check(
    request: HTTPRequest,
    body: ClaimRelevanceCheckRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    relevance_service: Annotated[ClaimRelevanceService, Depends(_get_relevance_service)],
) -> JSONResponse:
    """Check if a fact-check match is relevant to a user's message.

    Uses LLM to determine whether the matched content addresses a specific
    verifiable claim in the original message. Returns an outcome and reasoning.

    Fail-open semantics: if the LLM is unavailable, returns indeterminate
    with should_flag=true so legitimate matches are never silently dropped.

    JSON:API 1.1 action endpoint.
    """
    try:
        attrs = body.data.attributes

        logger.info(
            "Claim relevance check requested",
            extra={
                "user_id": str(current_user.id),
                "original_message_length": len(attrs.original_message),
                "matched_content_length": len(attrs.matched_content),
                "similarity_score": attrs.similarity_score,
            },
        )

        outcome, reasoning = await relevance_service.check_relevance(
            db=db,
            original_message=attrs.original_message,
            matched_content=attrs.matched_content,
            matched_source=attrs.matched_source,
        )

        should_flag = outcome in SHOULD_FLAG_OUTCOMES

        result = ClaimRelevanceCheckResultResource(
            type="claim-relevance-checks",
            id=str(uuid.uuid4()),
            attributes=ClaimRelevanceCheckResultAttributes(
                outcome=outcome.value,
                reasoning=reasoning,
                should_flag=should_flag,
            ),
        )

        response = ClaimRelevanceCheckResponse(data=result)

        logger.info(
            "Claim relevance check completed",
            extra={
                "user_id": str(current_user.id),
                "outcome": outcome.value,
                "should_flag": should_flag,
                "similarity_score": attrs.similarity_score,
            },
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.error(
            "Claim relevance check failed",
            extra={
                "user_id": str(current_user.id),
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        return _create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Claim relevance check failed. Please try again later.",
        )
