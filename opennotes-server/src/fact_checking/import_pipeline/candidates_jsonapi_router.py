"""JSON:API router for fact-check candidate review and rating management.

Implements JSON:API 1.1 compliant endpoints for:
- Listing candidates with filtering and pagination
- Setting ratings on individual candidates
- Bulk approval from predicted_ratings

Reference: https://jsonapi.org/format/
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.common.jsonapi import (
    JSONAPI_CONTENT_TYPE,
    JSONAPILinks,
    JSONAPIMeta,
    create_pagination_links,
)
from src.common.jsonapi import (
    create_error_response as create_error_response_model,
)
from src.database import get_db
from src.fact_checking.candidate_models import FactCheckedItemCandidate
from src.fact_checking.import_pipeline.candidate_schemas import (
    BulkApproveRequest,
    BulkApproveResponse,
    BulkApproveResponseMeta,
    CandidateAttributes,
    CandidateListResponse,
    CandidateResource,
    CandidateSingleResponse,
    SetRatingRequest,
)
from src.fact_checking.import_pipeline.candidate_service import (
    bulk_approve_from_predictions,
    list_candidates,
    set_candidate_rating,
)
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(
    prefix="/fact-checking/candidates",
    tags=["fact-checking-candidates"],
)


def candidate_to_resource(candidate: FactCheckedItemCandidate) -> CandidateResource:
    """Convert a FactCheckedItemCandidate model to a JSON:API resource object."""
    return CandidateResource(
        type="fact-check-candidates",
        id=str(candidate.id),
        attributes=CandidateAttributes(
            source_url=candidate.source_url,
            title=candidate.title,
            content=candidate.content,
            summary=candidate.summary,
            rating=candidate.rating,
            rating_details=candidate.rating_details,
            predicted_ratings=candidate.predicted_ratings,
            published_date=candidate.published_date,
            dataset_name=candidate.dataset_name,
            dataset_tags=candidate.dataset_tags or [],
            original_id=candidate.original_id,
            status=candidate.status,
            error_message=candidate.error_message,
            created_at=candidate.created_at,
            updated_at=candidate.updated_at,
        ),
    )


def create_pagination_links_from_request(
    request: HTTPRequest,
    page: int,
    size: int,
    total: int,
) -> JSONAPILinks:
    """Create JSON:API pagination links from a FastAPI request."""
    base_url = str(request.url).split("?")[0]
    query_params = {k: v for k, v in request.query_params.items() if not k.startswith("page[")}
    return create_pagination_links(
        base_url=base_url,
        page=page,
        size=size,
        total=total,
        query_params=query_params,
    )


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


@router.get("", response_class=JSONResponse, response_model=CandidateListResponse)
async def list_candidates_jsonapi(
    request: HTTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    page_number: int = Query(1, ge=1, alias="page[number]"),
    page_size: int = Query(20, ge=1, le=100, alias="page[size]"),
    filter_status: str | None = Query(None, alias="filter[status]"),
    filter_dataset_name: str | None = Query(None, alias="filter[dataset_name]"),
    filter_dataset_tags: list[str] | None = Query(None, alias="filter[dataset_tags]"),
    filter_rating: str | None = Query(
        None,
        alias="filter[rating]",
        description="Filter by rating: 'null', 'not_null', or exact value",
    ),
    filter_has_content: bool | None = Query(None, alias="filter[has_content]"),
    filter_published_date_from: datetime | None = Query(None, alias="filter[published_date_from]"),
    filter_published_date_to: datetime | None = Query(None, alias="filter[published_date_to]"),
) -> JSONResponse:
    """List fact-check candidates with filtering and pagination.

    Returns a JSON:API formatted paginated list of candidates.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[status]: Filter by candidate status (exact match)
    - filter[dataset_name]: Filter by dataset name (exact match)
    - filter[dataset_tags]: Filter by dataset tags (array overlap)
    - filter[rating]: Filter by rating - "null", "not_null", or exact value
    - filter[has_content]: Filter by whether content exists (true/false)
    - filter[published_date_from]: Filter by published_date >= datetime
    - filter[published_date_to]: Filter by published_date <= datetime
    """
    try:
        candidates, total = await list_candidates(
            session=db,
            page=page_number,
            page_size=page_size,
            status=filter_status,
            dataset_name=filter_dataset_name,
            dataset_tags=filter_dataset_tags,
            rating_filter=filter_rating,
            has_content=filter_has_content,
            published_date_from=filter_published_date_from,
            published_date_to=filter_published_date_to,
        )

        candidate_resources = [candidate_to_resource(c) for c in candidates]

        response = CandidateListResponse(
            data=candidate_resources,
            links=create_pagination_links_from_request(request, page_number, page_size, total),
            meta=JSONAPIMeta(count=total),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to list candidates (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to list candidates",
        )


@router.post(
    "/{candidate_id}/rating",
    response_class=JSONResponse,
    response_model=CandidateSingleResponse,
)
async def set_rating_jsonapi(
    candidate_id: UUID,
    request: HTTPRequest,
    body: SetRatingRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Set rating for a specific candidate.

    Sets the human-approved rating on a candidate. Optionally triggers
    promotion if the candidate is ready (has content and rating).

    Args:
        candidate_id: UUID of the candidate to update.
        body: JSON:API request with rating attributes.

    Returns:
        JSON:API response with updated candidate resource.
    """
    try:
        attrs = body.data.attributes

        candidate, promoted = await set_candidate_rating(
            session=db,
            candidate_id=candidate_id,
            rating=attrs.rating,
            rating_details=attrs.rating_details,
            auto_promote=attrs.auto_promote,
        )

        if not candidate:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Candidate {candidate_id} not found",
            )

        logger.info(
            f"Set rating on candidate {candidate_id} via JSON:API by user {current_user.id}",
            extra={
                "candidate_id": str(candidate_id),
                "user_id": str(current_user.id),
                "rating": attrs.rating,
                "promoted": promoted,
            },
        )

        response = CandidateSingleResponse(
            data=candidate_to_resource(candidate),
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to set rating (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to set rating",
        )


@router.post(
    "/approve-predicted",
    response_class=JSONResponse,
    response_model=BulkApproveResponse,
)
async def bulk_approve_predicted_jsonapi(
    request: HTTPRequest,
    body: BulkApproveRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Bulk approve candidates from predicted_ratings.

    Sets rating from predicted_ratings where any prediction >= threshold.
    Accepts the same filters as the list endpoint.

    For each matching candidate without a rating:
    1. Find the first predicted_rating entry >= threshold
    2. Set that as the candidate's rating
    3. Optionally promote if auto_promote=True

    Args:
        body: Bulk approve request with threshold and filters.

    Returns:
        JSON:API response with counts of updated and promoted candidates.
    """
    try:
        updated_count, promoted_count = await bulk_approve_from_predictions(
            session=db,
            threshold=body.threshold,
            auto_promote=body.auto_promote,
            status=body.status,
            dataset_name=body.dataset_name,
            dataset_tags=body.dataset_tags,
            has_content=body.has_content,
            published_date_from=body.published_date_from,
            published_date_to=body.published_date_to,
        )

        logger.info(
            f"Bulk approved candidates via JSON:API by user {current_user.id}",
            extra={
                "user_id": str(current_user.id),
                "threshold": body.threshold,
                "updated_count": updated_count,
                "promoted_count": promoted_count,
                "auto_promote": body.auto_promote,
            },
        )

        response = BulkApproveResponse(
            meta=BulkApproveResponseMeta(
                updated_count=updated_count,
                promoted_count=promoted_count,
            ),
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to bulk approve (JSON:API): {e}")
        await db.rollback()
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to bulk approve candidates",
        )
