"""API router for Bulk Content Scan endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    _get_profile_id_from_user,
    verify_community_admin_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.bulk_content_scan.flashpoint_service import get_flashpoint_service
from src.bulk_content_scan.models import BulkContentScanLog
from src.bulk_content_scan.repository import has_recent_scan
from src.bulk_content_scan.scan_types import DEFAULT_SCAN_TYPES, ScanType
from src.bulk_content_scan.schemas import (
    BulkScanCreateRequest,
    BulkScanResponse,
    BulkScanResultsResponse,
    BulkScanStatus,
    CreateNoteRequestsRequest,
    NoteRequestsResponse,
)
from src.bulk_content_scan.service import (
    BulkContentScanService,
    create_note_requests_from_flagged_messages,
)
from src.cache.redis_client import redis_client
from src.database import get_db
from src.dbos_workflows.content_scan_workflow import dispatch_content_scan_workflow
from src.fact_checking.embedding_service import EmbeddingService
from src.fact_checking.embeddings_jsonapi_router import get_embedding_service, get_llm_service
from src.llm_config.models import CommunityServer
from src.llm_config.service import LLMService
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.users.models import User
from src.users.profile_models import CommunityMember

logger = get_logger(__name__)

router = APIRouter(prefix="/bulk-content-scan", tags=["Bulk Content Scan"])


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


async def get_current_user_for_bulk_scan(
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> User:
    """Get current user for bulk scan operations."""
    return current_user


async def verify_scan_admin_access(
    community_server_id: UUID,
    current_user: User,
    db: AsyncSession,
    request: Request,
) -> CommunityMember:
    """
    Verify the current user has admin access to a community for bulk scan operations.

    This is a helper function that wraps verify_community_admin_by_uuid to:
    1. Handle the case where community_server_id comes from request body or scan lookup
    2. Maintain consistent authorization checks across all bulk scan endpoints

    Args:
        community_server_id: UUID of the community server to check access for
        current_user: The authenticated user
        db: Database session
        request: HTTP request (for Discord claims)

    Returns:
        CommunityMember: The user's membership record with admin access

    Raises:
        HTTPException: 403 if user lacks admin access
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
    request: Request,
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

    user_profile_id = await _get_profile_id_from_user(db, current_user)

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


@router.post(
    "/scans",
    response_model=BulkScanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a bulk content scan",
    description="Start a new bulk content scan for a community server. "
    "This will scan message history and flag potentially misleading content. "
    "Requires admin access to the target community. Service accounts have unrestricted access.",
)
@limiter.limit("5/hour")
async def initiate_scan(
    body: BulkScanCreateRequest,
    http_request: Request,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
    current_user: Annotated[User, Depends(get_current_user_for_bulk_scan)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BulkScanResponse:
    """Initiate a new bulk content scan.

    Authorization: Requires admin access to the target community.
    Service accounts have unrestricted access.

    Args:
        body: Scan initiation request
        http_request: HTTP request (for Discord claims)
        service: Bulk scan service
        current_user: Authenticated user
        session: Database session

    Returns:
        BulkScanResponse with scan_id and status

    Raises:
        HTTPException: 403 if user lacks admin access to the community
    """
    await verify_scan_admin_access(
        community_server_id=body.community_server_id,
        current_user=current_user,
        db=session,
        request=http_request,
    )

    profile_id = await _get_profile_id_from_user(session, current_user)
    if not profile_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to determine user profile ID",
        )

    logger.info(
        "Initiating bulk content scan",
        extra={
            "community_server_id": str(body.community_server_id),
            "user_id": str(current_user.id),
            "profile_id": str(profile_id),
            "scan_window_days": body.scan_window_days,
            "channel_count": len(body.channel_ids),
        },
    )

    scan_log = await service.initiate_scan(
        community_server_id=body.community_server_id,
        initiated_by_user_id=profile_id,
        scan_window_days=body.scan_window_days,
    )

    scan_types = list(DEFAULT_SCAN_TYPES)
    try:
        result = await session.execute(
            sa_select(CommunityServer.flashpoint_detection_enabled).where(
                CommunityServer.id == body.community_server_id
            )
        )
        if result.scalar_one_or_none():
            scan_types.append(ScanType.CONVERSATION_FLASHPOINT)
    except Exception:
        logger.warning(
            "Failed to check flashpoint_detection_enabled",
            extra={"community_server_id": str(body.community_server_id)},
            exc_info=True,
        )

    try:
        workflow_id = await dispatch_content_scan_workflow(
            scan_id=scan_log.id,
            community_server_id=body.community_server_id,
            scan_types=[str(st) for st in scan_types],
        )
    except Exception as e:
        logger.error(
            "DBOS workflow dispatch raised unexpected error",
            extra={
                "scan_id": str(scan_log.id),
                "error": str(e),
            },
            exc_info=True,
        )
        scan_log.status = BulkScanStatus.FAILED
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dispatch scan workflow: {e}",
        )

    if not workflow_id:
        logger.error(
            "DBOS workflow dispatch returned None",
            extra={"scan_id": str(scan_log.id)},
        )
        scan_log.status = BulkScanStatus.FAILED
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dispatch scan workflow. The scan record was created but processing could not be started.",
        )

    logger.info(
        "DBOS content scan workflow dispatched",
        extra={
            "scan_id": str(scan_log.id),
            "workflow_id": workflow_id,
        },
    )

    return BulkScanResponse(
        scan_id=scan_log.id,
        status=scan_log.status,
        initiated_at=scan_log.initiated_at,
        completed_at=scan_log.completed_at,
        messages_scanned=scan_log.messages_scanned,
        messages_flagged=scan_log.messages_flagged,
    )


@router.get(
    "/scans/{scan_id}",
    response_model=BulkScanResultsResponse,
    summary="Get scan results",
    description="Retrieve the status and flagged results for a bulk content scan. "
    "Supports pagination via page and page_size query parameters. "
    "Requires admin access to the community that was scanned. Service accounts have unrestricted access.",
)
async def get_scan_results(
    scan_id: UUID,
    http_request: Request,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
    current_user: Annotated[User, Depends(get_current_user_for_bulk_scan)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    page_size: int = 50,
) -> BulkScanResultsResponse:
    """Get scan status and flagged results with pagination.

    Authorization: Requires admin access to the community that was scanned.
    Service accounts have unrestricted access.

    Args:
        scan_id: UUID of the scan
        http_request: HTTP request (for Discord claims)
        service: Bulk scan service
        current_user: Authenticated user
        session: Database session
        page: Page number (1-indexed, default: 1)
        page_size: Number of results per page (default: 50, max: 100)

    Returns:
        BulkScanResultsResponse with status, paginated flagged messages, and pagination metadata

    Raises:
        HTTPException: 404 if scan not found, 403 if user lacks admin access, 422 if invalid pagination
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page must be at least 1",
        )

    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page size must be between 1 and 100",
        )

    scan_log = await service.get_scan(scan_id)

    if not scan_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found",
        )

    await verify_scan_admin_access(
        community_server_id=scan_log.community_server_id,
        current_user=current_user,
        db=session,
        request=http_request,
    )

    all_flagged_messages = await service.get_flagged_results(scan_id)
    total = len(all_flagged_messages)

    offset = (page - 1) * page_size
    paginated_messages = all_flagged_messages[offset : offset + page_size]

    return BulkScanResultsResponse(
        scan_id=scan_log.id,
        status=scan_log.status,
        messages_scanned=scan_log.messages_scanned,
        flagged_messages=paginated_messages,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/communities/{community_server_id}/has-recent-scan",
    summary="Check for recent scan",
    description="Check if a community server has had a recent bulk content scan. "
    "Requires admin access to the specified community. Service accounts have unrestricted access.",
)
async def check_recent_scan(
    community_server_id: UUID,
    http_request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_for_bulk_scan)],
) -> dict[str, bool]:
    """Check if community has a recent scan within the configured window.

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Args:
        community_server_id: UUID of the community server
        http_request: HTTP request (for Discord claims)
        session: Database session
        current_user: Authenticated user

    Returns:
        Dict with has_recent_scan boolean

    Raises:
        HTTPException: 403 if user lacks admin access to the community
    """
    await verify_scan_admin_access(
        community_server_id=community_server_id,
        current_user=current_user,
        db=session,
        request=http_request,
    )

    result = await has_recent_scan(session, community_server_id)
    return {"has_recent_scan": result}


@router.post(
    "/scans/{scan_id}/note-requests",
    response_model=NoteRequestsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create note requests from scan",
    description="Create note requests for selected flagged messages from a bulk scan. "
    "Requires the user to be either the scan initiator or a community admin. "
    "Service accounts have unrestricted access.",
)
async def create_note_requests(
    scan_id: UUID,
    body: CreateNoteRequestsRequest,
    http_request: Request,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
    current_user: Annotated[User, Depends(get_current_user_for_bulk_scan)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NoteRequestsResponse:
    """Create note requests for selected flagged messages.

    Authorization: User must be the scan initiator OR a community admin.
    Service accounts have unrestricted access.

    Args:
        scan_id: UUID of the scan
        body: Request with message IDs
        http_request: HTTP request (for Discord claims)
        service: Bulk scan service
        current_user: Authenticated user
        session: Database session

    Returns:
        NoteRequestsResponse with created count

    Raises:
        HTTPException: 404 if scan not found, 403 if user is not owner or admin
    """
    scan_log = await service.get_scan(scan_id)

    if not scan_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found",
        )

    await verify_scan_owner_or_admin_access(
        scan=scan_log,
        current_user=current_user,
        db=session,
        request=http_request,
    )

    flagged_messages = await service.get_flagged_results(scan_id)

    if not flagged_messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No flagged results available for this scan",
        )

    created_ids = await create_note_requests_from_flagged_messages(
        message_ids=body.message_ids,
        scan_id=scan_id,
        session=session,
        user_id=current_user.id,
        community_server_id=scan_log.community_server_id,
        flagged_messages=flagged_messages,
        generate_ai_notes=body.generate_ai_notes,
    )

    return NoteRequestsResponse(
        created_count=len(created_ids),
        request_ids=created_ids,
    )
