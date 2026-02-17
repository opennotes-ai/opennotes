"""JSON:API v2 router for Bulk Content Scan.

This module implements JSON:API 1.1 compliant endpoints for bulk content scanning.
It provides:
- POST /bulk-scans - Initiate a bulk content scan
- GET /bulk-scans/{scan_id} - Get scan status and flagged results
- GET /bulk-scans/communities/{community_server_id}/recent - Check for recent scan
- POST /bulk-scans/{scan_id}/note-requests - Create note requests from flagged messages

Reference: https://jsonapi.org/format/
"""

import uuid as uuid_module
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    get_profile_id_from_user,
    verify_community_admin_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.bulk_content_scan.flashpoint_service import get_flashpoint_service
from src.bulk_content_scan.models import BulkContentScanLog
from src.bulk_content_scan.repository import get_latest_scan_for_community, has_recent_scan
from src.bulk_content_scan.scan_types import DEFAULT_SCAN_TYPES, ScanType
from src.bulk_content_scan.schemas import BulkScanStatus, FlaggedMessage, MatchResult
from src.bulk_content_scan.service import (
    BulkContentScanService,
    create_note_requests_from_flagged_messages,
)
from src.cache.redis_client import redis_client
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
from src.dbos_workflows.content_scan_workflow import dispatch_content_scan_workflow
from src.fact_checking.embedding_service import EmbeddingService
from src.fact_checking.embeddings_jsonapi_router import get_embedding_service, get_llm_service
from src.fact_checking.models import FactCheckItem
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.services.ai_note_writer import AINoteWriter
from src.users.models import User
from src.users.profile_models import CommunityMember

logger = get_logger(__name__)

router = APIRouter()


class BulkScanCreateAttributes(StrictInputSchema):
    """Attributes for creating a bulk scan."""

    community_server_id: UUID = Field(..., description="Community server UUID to scan")
    scan_window_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Number of days to scan back",
    )
    channel_ids: list[str] = Field(
        default_factory=list,
        description="Specific channel IDs to scan (empty = all channels)",
    )


class BulkScanCreateData(BaseModel):
    """JSON:API data object for bulk scan creation."""

    type: Literal["bulk-scans"] = Field(..., description="Resource type must be 'bulk-scans'")
    attributes: BulkScanCreateAttributes


class BulkScanCreateJSONAPIRequest(BaseModel):
    """JSON:API request body for creating a bulk scan."""

    data: BulkScanCreateData


class BulkScanAttributes(SQLAlchemySchema):
    """Attributes for a bulk scan resource."""

    status: str = Field(..., description="Scan status: pending, in_progress, completed, failed")
    initiated_at: datetime = Field(..., description="When the scan was initiated")
    completed_at: datetime | None = Field(None, description="When the scan completed")
    messages_scanned: int = Field(default=0, description="Total messages scanned")
    messages_flagged: int = Field(default=0, description="Number of flagged messages")


class BulkScanResource(BaseModel):
    """JSON:API resource object for a bulk scan."""

    type: str = "bulk-scans"
    id: str
    attributes: BulkScanAttributes


class BulkScanSingleResponse(SQLAlchemySchema):
    """JSON:API response for a single bulk scan resource."""

    data: BulkScanResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class FlaggedMessageAttributes(SQLAlchemySchema):
    """Attributes for a flagged message resource."""

    channel_id: str = Field(..., description="Channel ID where message was found")
    content: str = Field(..., description="Message content")
    author_id: str = Field(..., description="Author ID")
    timestamp: datetime = Field(..., description="Message timestamp")
    matches: list[MatchResult] = Field(
        default_factory=list,
        description="List of match results from different scan types",
    )


class FlaggedMessageResource(BaseModel):
    """JSON:API resource object for a flagged message."""

    type: str = "flagged-messages"
    id: str
    attributes: FlaggedMessageAttributes


class ScanErrorInfoSchema(BaseModel):
    """Error information for a failed message scan."""

    error_type: str = Field(..., description="Type of error (e.g., 'TypeError')")
    message_id: str | None = Field(None, description="Message ID that caused error")
    batch_number: int | None = Field(None, description="Batch number where error occurred")
    error_message: str = Field(..., description="Error message details")


class ScanErrorSummarySchema(BaseModel):
    """Summary of errors encountered during scan."""

    total_errors: int = Field(default=0, ge=0, description="Total number of errors")
    error_types: dict[str, int] = Field(
        default_factory=dict,
        description="Count of errors by type",
    )
    sample_errors: list[ScanErrorInfoSchema] = Field(
        default_factory=list,
        description="Sample of error messages (up to 5)",
    )


class BulkScanResultsAttributes(SQLAlchemySchema):
    """Attributes for bulk scan results."""

    status: str = Field(..., description="Scan status")
    messages_scanned: int = Field(default=0, description="Total messages scanned")
    messages_flagged: int = Field(default=0, description="Number of flagged messages")
    error_summary: ScanErrorSummarySchema | None = Field(
        None,
        description="Summary of errors encountered during scan",
    )


class BulkScanResultsResource(BaseModel):
    """JSON:API resource object for bulk scan results."""

    type: str = "bulk-scans"
    id: str
    attributes: BulkScanResultsAttributes
    relationships: dict[str, Any] | None = None


class BulkScanResultsJSONAPIResponse(SQLAlchemySchema):
    """JSON:API response for bulk scan results with included flagged messages."""

    data: BulkScanResultsResource
    included: list[FlaggedMessageResource] = Field(default_factory=list)
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class RecentScanAttributes(BaseModel):
    """Attributes for recent scan check."""

    has_recent_scan: bool = Field(..., description="Whether community has a recent scan")


class RecentScanResource(BaseModel):
    """JSON:API resource for recent scan status."""

    type: str = "bulk-scan-status"
    id: str
    attributes: RecentScanAttributes


class RecentScanResponse(SQLAlchemySchema):
    """JSON:API response for recent scan check."""

    data: RecentScanResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class LatestScanAttributes(SQLAlchemySchema):
    """Attributes for the latest scan resource."""

    status: str = Field(..., description="Scan status: pending, in_progress, completed, failed")
    initiated_at: datetime = Field(..., description="When the scan was initiated")
    completed_at: datetime | None = Field(None, description="When the scan completed")
    messages_scanned: int = Field(default=0, description="Total messages scanned")
    messages_flagged: int = Field(default=0, description="Number of flagged messages")
    error_summary: ScanErrorSummarySchema | None = Field(
        None,
        description="Summary of errors encountered during scan",
    )


class LatestScanResource(BaseModel):
    """JSON:API resource object for the latest scan."""

    type: str = "bulk-scans"
    id: str
    attributes: LatestScanAttributes
    relationships: dict[str, Any] | None = None


class LatestScanJSONAPIResponse(SQLAlchemySchema):
    """JSON:API response for the latest scan with included flagged messages."""

    data: LatestScanResource
    included: list[FlaggedMessageResource] = Field(default_factory=list)
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class NoteRequestsCreateAttributes(StrictInputSchema):
    """Attributes for creating note requests from flagged messages."""

    message_ids: list[str] = Field(
        ...,
        min_length=1,
        description="List of message IDs to create note requests for",
    )
    generate_ai_notes: bool = Field(
        default=False,
        description="Whether to generate AI draft notes",
    )


class NoteRequestsCreateData(BaseModel):
    """JSON:API data object for note requests creation."""

    type: Literal["note-requests"] = Field(..., description="Resource type must be 'note-requests'")
    attributes: NoteRequestsCreateAttributes


class NoteRequestsCreateRequest(BaseModel):
    """JSON:API request body for creating note requests."""

    data: NoteRequestsCreateData


class NoteRequestsResultAttributes(BaseModel):
    """Attributes for note requests creation result."""

    created_count: int = Field(..., description="Number of note requests created")
    request_ids: list[str] = Field(default_factory=list, description="Created request IDs")


class NoteRequestsResultResource(BaseModel):
    """JSON:API resource for note requests creation result."""

    type: str = "note-request-batches"
    id: str
    attributes: NoteRequestsResultAttributes


class NoteRequestsResultResponse(SQLAlchemySchema):
    """JSON:API response for note requests creation."""

    data: NoteRequestsResultResource
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None


class ExplanationCreateAttributes(StrictInputSchema):
    """Attributes for generating a scan explanation."""

    original_message: str = Field(..., description="Original message content that was flagged")
    fact_check_item_id: UUID = Field(..., description="UUID of the matched FactCheckItem")
    community_server_id: UUID = Field(..., description="Community server UUID for context")


class ExplanationCreateData(BaseModel):
    """JSON:API data object for explanation generation."""

    type: Literal["scan-explanations"] = Field(
        ..., description="Resource type must be 'scan-explanations'"
    )
    attributes: ExplanationCreateAttributes


class ExplanationCreateRequest(BaseModel):
    """JSON:API request body for generating a scan explanation."""

    data: ExplanationCreateData


class ExplanationResultAttributes(BaseModel):
    """Attributes for explanation result."""

    explanation: str = Field(
        ..., description="AI-generated explanation for why message was flagged"
    )


class ExplanationResultResource(BaseModel):
    """JSON:API resource for explanation result."""

    type: str = "scan-explanations"
    id: str
    attributes: ExplanationResultAttributes


class ExplanationResultResponse(SQLAlchemySchema):
    """JSON:API response for explanation generation."""

    data: ExplanationResultResource
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


async def verify_scan_admin_access(
    community_server_id: UUID,
    current_user: User,
    db: AsyncSession,
    request: HTTPRequest,
) -> CommunityMember:
    """
    Verify the current user has admin access to a community for bulk scan operations.

    This is a helper function that wraps verify_community_admin_by_uuid to:
    1. Handle the case where community_server_id comes from request body or scan lookup
    2. Convert HTTPExceptions to JSON:API error responses

    Args:
        community_server_id: UUID of the community server to check access for
        current_user: The authenticated user
        db: Database session
        request: HTTP request (for Discord claims)

    Returns:
        CommunityMember: The user's membership record with admin access

    Raises:
        HTTPException: 403 if user lacks admin access, with JSON:API formatted detail
    """
    return await verify_community_admin_by_uuid(
        community_server_id=community_server_id,
        current_user=current_user,
        db=db,
        request=request,
    )


async def verify_scan_owner_or_admin_access(
    scan: BulkContentScanLog,
    current_user: User,
    db: AsyncSession,
    request: HTTPRequest,
) -> None:
    """
    Verify the current user has access to create note requests for a scan.

    Authorization allows:
    1. Service accounts - always have access
    2. Scan owner - user who initiated the scan
    3. Community admin - admin of the scanned community

    Args:
        scan: The bulk content scan log to check access for
        current_user: The authenticated user
        db: Database session
        request: HTTP request (for Discord claims)

    Raises:
        HTTPException: 403 if user is not the scan owner and lacks admin access
    """
    if is_service_account(current_user):
        return

    user_profile_id = await get_profile_id_from_user(db, current_user)

    if user_profile_id and scan.initiated_by_user_id == user_profile_id:
        return

    try:
        await verify_scan_admin_access(
            community_server_id=scan.community_server_id,
            current_user=current_user,
            db=db,
            request=request,
        )
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Only the scan initiator or community admins can create note requests from this scan.",
        )


async def get_redis() -> Redis:
    """Get Redis client for bulk scan operations."""
    if redis_client.client is None:
        await redis_client.connect()
    if redis_client.client is None:
        raise RuntimeError("Failed to establish Redis connection")
    return redis_client.client


async def get_bulk_scan_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
    redis: Annotated[Redis, Depends(get_redis)],
    llm_service: Annotated[LLMService, Depends(get_llm_service)],
) -> BulkContentScanService:
    """Get bulk scan service with dependencies."""
    return BulkContentScanService(
        session=session,
        embedding_service=embedding_service,
        redis_client=redis,
        llm_service=llm_service,
        flashpoint_service=get_flashpoint_service(),
    )


def flagged_message_to_resource(msg: FlaggedMessage) -> FlaggedMessageResource:
    """Convert a FlaggedMessage to a JSON:API resource."""
    return FlaggedMessageResource(
        type="flagged-messages",
        id=msg.message_id,
        attributes=FlaggedMessageAttributes(
            channel_id=msg.channel_id,
            content=msg.content,
            author_id=msg.author_id,
            timestamp=msg.timestamp,
            matches=msg.matches,
        ),
    )


async def get_fact_check_item_by_id(
    session: AsyncSession,
    fact_check_item_id: UUID,
) -> FactCheckItem | None:
    """Get a fact check item by ID."""
    result = await session.execute(
        select(FactCheckItem).where(FactCheckItem.id == fact_check_item_id)
    )
    return result.scalar_one_or_none()


def get_ai_note_writer() -> AINoteWriter:
    """Get AI note writer service."""
    encryption_service = EncryptionService(settings.ENCRYPTION_MASTER_KEY)
    client_manager = LLMClientManager(encryption_service)
    llm_service = LLMService(client_manager)
    return AINoteWriter(llm_service=llm_service)


@router.post("/bulk-scans", response_class=JSONResponse, response_model=BulkScanSingleResponse)
@limiter.limit("5/hour")
async def initiate_scan(
    body: BulkScanCreateJSONAPIRequest,
    request: HTTPRequest,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Initiate a new bulk content scan.

    JSON:API request body must contain:
    - data.type: "bulk-scans"
    - data.attributes.community_server_id: UUID of community to scan
    - data.attributes.scan_window_days: Number of days to scan back (1-30)
    - data.attributes.channel_ids: Optional list of specific channel IDs

    Authorization: Requires admin access to the target community.
    Service accounts have unrestricted access.

    Returns a bulk-scans resource with scan_id and initial status.
    """
    try:
        attrs = body.data.attributes

        try:
            await verify_scan_admin_access(
                community_server_id=attrs.community_server_id,
                current_user=current_user,
                db=session,
                request=request,
            )
        except HTTPException as e:
            return create_error_response(
                status_code=e.status_code,
                title="Forbidden" if e.status_code == 403 else "Not Found",
                detail=e.detail,
            )

        profile_id = await get_profile_id_from_user(session, current_user)
        if not profile_id:
            return create_error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Internal Server Error",
                "Failed to determine user profile ID",
            )

        logger.info(
            "Initiating bulk content scan (JSON:API)",
            extra={
                "community_server_id": str(attrs.community_server_id),
                "user_id": str(current_user.id),
                "profile_id": str(profile_id),
                "scan_window_days": attrs.scan_window_days,
                "channel_count": len(attrs.channel_ids),
            },
        )

        scan_log = await service.initiate_scan(
            community_server_id=attrs.community_server_id,
            initiated_by_user_id=profile_id,
            scan_window_days=attrs.scan_window_days,
        )

        scan_types: list[ScanType] = list(DEFAULT_SCAN_TYPES)
        try:
            cs_result = await session.execute(
                select(CommunityServer.flashpoint_detection_enabled).where(
                    CommunityServer.id == attrs.community_server_id
                )
            )
            if cs_result.scalar_one_or_none():
                scan_types.append(ScanType.CONVERSATION_FLASHPOINT)
        except Exception:
            logger.warning(
                "Failed to check flashpoint_detection_enabled",
                extra={"community_server_id": str(attrs.community_server_id)},
                exc_info=True,
            )

        try:
            workflow_id = await dispatch_content_scan_workflow(
                scan_id=scan_log.id,
                community_server_id=attrs.community_server_id,
                scan_types=[str(st) for st in scan_types],
            )
        except Exception as e:
            logger.error(
                "DBOS workflow dispatch raised unexpected error (JSON:API)",
                extra={
                    "scan_id": str(scan_log.id),
                    "error": str(e),
                },
                exc_info=True,
            )
            scan_log.status = BulkScanStatus.FAILED
            await session.commit()
            return create_error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Internal Server Error",
                "Failed to dispatch scan workflow",
            )

        if not workflow_id:
            logger.error(
                "DBOS workflow dispatch returned None (JSON:API)",
                extra={"scan_id": str(scan_log.id)},
            )
            scan_log.status = BulkScanStatus.FAILED
            await session.commit()
            return create_error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Internal Server Error",
                "Failed to dispatch scan workflow. The scan record was created but processing could not be started.",
            )

        logger.info(
            "DBOS content scan workflow dispatched (JSON:API)",
            extra={
                "scan_id": str(scan_log.id),
                "workflow_id": workflow_id,
            },
        )

        resource = BulkScanResource(
            type="bulk-scans",
            id=str(scan_log.id),
            attributes=BulkScanAttributes(
                status=scan_log.status,
                initiated_at=scan_log.initiated_at,
                completed_at=scan_log.completed_at,
                messages_scanned=scan_log.messages_scanned or 0,
                messages_flagged=scan_log.messages_flagged or 0,
            ),
        )

        response = BulkScanSingleResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url) + "/" + str(scan_log.id)),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to initiate bulk scan (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to initiate bulk scan",
        )


@router.get(
    "/bulk-scans/{scan_id}",
    response_class=JSONResponse,
    response_model=BulkScanResultsJSONAPIResponse,
)
async def get_scan_results(
    scan_id: UUID,
    request: HTTPRequest,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Get scan status and flagged results.

    Authorization: Requires admin access to the community that was scanned.
    Service accounts have unrestricted access.

    Returns the bulk scan resource with flagged messages included as related resources.
    Uses JSON:API compound documents with 'included' array.
    """
    try:
        scan_log = await service.get_scan(scan_id)

        if not scan_log:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Scan {scan_id} not found",
            )

        try:
            await verify_scan_admin_access(
                community_server_id=scan_log.community_server_id,
                current_user=current_user,
                db=session,
                request=request,
            )
        except HTTPException as e:
            return create_error_response(
                status_code=e.status_code,
                title="Forbidden" if e.status_code == 403 else "Not Found",
                detail=e.detail,
            )

        flagged_messages = await service.get_flagged_results(scan_id)
        error_summary_schema: ScanErrorSummarySchema | None = None

        if scan_log.status in ("completed", "failed"):
            error_summary_data = await service.get_error_summary(scan_id)

            if error_summary_data.get("total_errors", 0) > 0:
                error_summary_schema = ScanErrorSummarySchema(
                    total_errors=error_summary_data["total_errors"],
                    error_types=error_summary_data.get("error_types", {}),
                    sample_errors=[
                        ScanErrorInfoSchema(
                            error_type=err.get("error_type", "Unknown"),
                            message_id=err.get("message_id"),
                            batch_number=err.get("batch_number"),
                            error_message=err.get("error_message", ""),
                        )
                        for err in error_summary_data.get("sample_errors", [])
                    ],
                )

        resource = BulkScanResultsResource(
            type="bulk-scans",
            id=str(scan_id),
            attributes=BulkScanResultsAttributes(
                status=scan_log.status,
                messages_scanned=scan_log.messages_scanned or 0,
                messages_flagged=len(flagged_messages),
                error_summary=error_summary_schema,
            ),
            relationships={
                "flagged-messages": {
                    "data": [
                        {"type": "flagged-messages", "id": msg.message_id}
                        for msg in flagged_messages
                    ],
                },
            },
        )

        included = [flagged_message_to_resource(msg) for msg in flagged_messages]

        response = BulkScanResultsJSONAPIResponse(
            data=resource,
            included=included,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get scan results (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to retrieve scan results",
        )


@router.get(
    "/bulk-scans/communities/{community_server_id}/recent",
    response_class=JSONResponse,
    response_model=RecentScanResponse,
)
async def check_recent_scan(
    community_server_id: UUID,
    request: HTTPRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> JSONResponse:
    """Check if community has a recent scan within the configured window.

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Returns a bulk-scan-status singleton resource with has_recent_scan boolean.
    """
    try:
        try:
            await verify_scan_admin_access(
                community_server_id=community_server_id,
                current_user=current_user,
                db=session,
                request=request,
            )
        except HTTPException as e:
            return create_error_response(
                status_code=e.status_code,
                title="Forbidden" if e.status_code == 403 else "Not Found",
                detail=e.detail,
            )

        result = await has_recent_scan(session, community_server_id)

        resource = RecentScanResource(
            type="bulk-scan-status",
            id=str(community_server_id),
            attributes=RecentScanAttributes(has_recent_scan=result),
        )

        response = RecentScanResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to check recent scan (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to check recent scan status",
        )


@router.get(
    "/bulk-scans/communities/{community_server_id}/latest",
    response_class=JSONResponse,
    response_model=LatestScanJSONAPIResponse,
)
async def get_latest_scan(
    community_server_id: UUID,
    request: HTTPRequest,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Get the most recent scan for a community server.

    Returns the latest bulk content scan with full details including:
    - Scan status (pending, in_progress, completed, failed)
    - Message counts (scanned and flagged)
    - Timestamps (initiated_at, completed_at)
    - Flagged messages with match details (if scan is completed)

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.
    """
    try:
        try:
            await verify_scan_admin_access(
                community_server_id=community_server_id,
                current_user=current_user,
                db=session,
                request=request,
            )
        except HTTPException as e:
            return create_error_response(
                status_code=e.status_code,
                title="Forbidden" if e.status_code == 403 else "Not Found",
                detail=e.detail,
            )

        scan_log = await get_latest_scan_for_community(session, community_server_id)

        if not scan_log:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"No scans found for community {community_server_id}",
            )

        flagged_messages: list[FlaggedMessage] = []
        error_summary_schema: ScanErrorSummarySchema | None = None

        if scan_log.status in ("completed", "failed"):
            flagged_messages = await service.get_flagged_results(scan_log.id)
            error_summary_data = await service.get_error_summary(scan_log.id)

            if error_summary_data.get("total_errors", 0) > 0:
                error_summary_schema = ScanErrorSummarySchema(
                    total_errors=error_summary_data["total_errors"],
                    error_types=error_summary_data.get("error_types", {}),
                    sample_errors=[
                        ScanErrorInfoSchema(
                            error_type=err.get("error_type", "Unknown"),
                            message_id=err.get("message_id"),
                            batch_number=err.get("batch_number"),
                            error_message=err.get("error_message", ""),
                        )
                        for err in error_summary_data.get("sample_errors", [])
                    ],
                )

        resource = LatestScanResource(
            type="bulk-scans",
            id=str(scan_log.id),
            attributes=LatestScanAttributes(
                status=scan_log.status,
                initiated_at=scan_log.initiated_at,
                completed_at=scan_log.completed_at,
                messages_scanned=scan_log.messages_scanned or 0,
                messages_flagged=scan_log.messages_flagged or 0,
                error_summary=error_summary_schema,
            ),
            relationships={
                "flagged-messages": {
                    "data": [
                        {"type": "flagged-messages", "id": msg.message_id}
                        for msg in flagged_messages
                    ],
                },
            }
            if flagged_messages
            else None,
        )

        included = [flagged_message_to_resource(msg) for msg in flagged_messages]

        response = LatestScanJSONAPIResponse(
            data=resource,
            included=included,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except Exception as e:
        logger.exception(f"Failed to get latest scan (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to retrieve latest scan",
        )


@router.post(
    "/bulk-scans/{scan_id}/note-requests",
    response_class=JSONResponse,
    response_model=NoteRequestsResultResponse,
)
async def create_note_requests(
    scan_id: UUID,
    body: NoteRequestsCreateRequest,
    request: HTTPRequest,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Create note requests for selected flagged messages.

    JSON:API request body must contain:
    - data.type: "note-requests"
    - data.attributes.message_ids: List of message IDs from flagged results
    - data.attributes.generate_ai_notes: Whether to generate AI drafts

    Authorization: User must be the scan initiator OR a community admin.
    Service accounts have unrestricted access.

    Returns a note-request-batches resource with created count and IDs.
    """
    try:
        scan_log = await service.get_scan(scan_id)

        if not scan_log:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Scan {scan_id} not found",
            )

        try:
            await verify_scan_owner_or_admin_access(
                scan=scan_log,
                current_user=current_user,
                db=session,
                request=request,
            )
        except HTTPException as e:
            return create_error_response(
                status_code=e.status_code,
                title="Forbidden" if e.status_code == 403 else "Not Found",
                detail=e.detail,
            )

        flagged_messages = await service.get_flagged_results(scan_id)

        if not flagged_messages:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "Bad Request",
                "No flagged results available for this scan",
            )

        attrs = body.data.attributes
        created_ids = await create_note_requests_from_flagged_messages(
            message_ids=attrs.message_ids,
            scan_id=scan_id,
            session=session,
            user_id=current_user.id,
            community_server_id=scan_log.community_server_id,
            flagged_messages=flagged_messages,
            generate_ai_notes=attrs.generate_ai_notes,
        )

        batch_id = f"batch_{scan_id.hex[:8]}_{uuid_module.uuid4().hex[:8]}"
        resource = NoteRequestsResultResource(
            type="note-request-batches",
            id=batch_id,
            attributes=NoteRequestsResultAttributes(
                created_count=len(created_ids),
                request_ids=created_ids,
            ),
        )

        response = NoteRequestsResultResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create note requests (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to create note requests",
        )


@router.post(
    "/bulk-scans/explanations",
    response_class=JSONResponse,
    response_model=ExplanationResultResponse,
)
async def generate_explanation(
    body: ExplanationCreateRequest,
    request: HTTPRequest,
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Generate an AI explanation for why a message was flagged.

    JSON:API request body must contain:
    - data.type: "scan-explanations"
    - data.attributes.original_message: The flagged message content
    - data.attributes.fact_check_item_id: UUID of the matched fact-check item
    - data.attributes.community_server_id: Community server UUID for context

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Returns a scan-explanations resource with the generated explanation.
    """
    try:
        attrs = body.data.attributes

        try:
            await verify_scan_admin_access(
                community_server_id=attrs.community_server_id,
                current_user=current_user,
                db=session,
                request=request,
            )
        except HTTPException as e:
            return create_error_response(
                status_code=e.status_code,
                title="Forbidden" if e.status_code == 403 else "Not Found",
                detail=e.detail,
            )

        fact_check_item = await get_fact_check_item_by_id(session, attrs.fact_check_item_id)

        if not fact_check_item:
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "Not Found",
                f"Fact check item {attrs.fact_check_item_id} not found",
            )

        fact_check_data: dict[str, str | float | None] = {
            "id": str(fact_check_item.id),
            "title": fact_check_item.title,
            "content": fact_check_item.content,
            "rating": fact_check_item.rating,
            "source_url": fact_check_item.source_url,
        }

        ai_note_writer = get_ai_note_writer()
        explanation = await ai_note_writer.generate_scan_explanation(
            original_message=attrs.original_message,
            fact_check_data=fact_check_data,
            db=session,
            community_server_id=attrs.community_server_id,
        )

        resource = ExplanationResultResource(
            type="scan-explanations",
            id=str(uuid_module.uuid4()),
            attributes=ExplanationResultAttributes(explanation=explanation),
        )

        response = ExplanationResultResponse(
            data=resource,
            links=JSONAPILinks(self_=str(request.url)),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(by_alias=True, mode="json"),
            media_type=JSONAPI_CONTENT_TYPE,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate explanation (JSON:API): {e}")
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "Failed to generate explanation",
        )
