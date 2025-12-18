"""API router for Bulk Content Scan endpoints."""

import uuid as uuid_module
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import (
    _get_profile_id_from_user,
    verify_community_admin_by_uuid,
)
from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.bulk_content_scan.models import BulkContentScanLog
from src.bulk_content_scan.repository import has_recent_scan
from src.bulk_content_scan.schemas import (
    BulkScanCreateRequest,
    BulkScanResponse,
    BulkScanResultsResponse,
    CreateNoteRequestsRequest,
    FlaggedMessage,
    NoteRequestsResponse,
)
from src.bulk_content_scan.service import BulkContentScanService
from src.cache.redis_client import redis_client
from src.database import get_db
from src.fact_checking.embedding_router import get_embedding_service
from src.fact_checking.embedding_service import EmbeddingService
from src.monitoring import get_logger
from src.notes.request_service import RequestService
from src.users.models import User
from src.users.profile_models import CommunityMember

logger = get_logger(__name__)

router = APIRouter(prefix="/bulk-content-scan", tags=["Bulk Content Scan"])


async def get_redis() -> Redis:
    """Get Redis client for bulk scan operations."""
    if redis_client.client is None:
        await redis_client.connect()
    return redis_client.client


async def get_bulk_scan_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> BulkContentScanService:
    """Get bulk scan service with dependencies."""
    return BulkContentScanService(
        session=session,
        embedding_service=embedding_service,
        redis_client=redis,
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


async def create_note_requests_for_messages(
    message_ids: list[str],
    scan_id: UUID,
    session: AsyncSession,
    user_id: UUID,
    community_server_id: UUID,
    flagged_messages: list[FlaggedMessage],
    generate_ai_notes: bool = False,
) -> list[str]:
    """Create note requests for flagged messages.

    Creates Request entries in the database for selected flagged messages
    from a bulk content scan. Each request includes the message content,
    match information, and metadata for potential AI note generation.

    Args:
        message_ids: List of Discord message IDs to create requests for
        scan_id: UUID of the scan these messages came from
        session: Database session
        user_id: UUID of the user making the request
        community_server_id: UUID of the community server
        flagged_messages: List of FlaggedMessage objects from the scan results
        generate_ai_notes: Whether to generate AI draft notes

    Returns:
        List of created request IDs (string request_id values)
    """
    logger.info(
        "Creating note requests from bulk scan",
        extra={
            "scan_id": str(scan_id),
            "message_count": len(message_ids),
            "user_id": str(user_id),
            "community_server_id": str(community_server_id),
            "generate_ai_notes": generate_ai_notes,
        },
    )

    flagged_by_message_id = {msg.message_id: msg for msg in flagged_messages}

    created_ids: list[str] = []
    for msg_id in message_ids:
        flagged_msg = flagged_by_message_id.get(msg_id)
        if not flagged_msg:
            logger.warning(
                "Message ID not found in flagged results",
                extra={
                    "message_id": msg_id,
                    "scan_id": str(scan_id),
                },
            )
            continue

        request_id = f"bulkscan_{scan_id.hex[:8]}_{uuid_module.uuid4().hex[:8]}"

        try:
            request = await RequestService.create_from_message(
                db=session,
                request_id=request_id,
                content=flagged_msg.content,
                community_server_id=community_server_id,
                requested_by=str(user_id),
                platform_message_id=flagged_msg.message_id,
                platform_channel_id=flagged_msg.channel_id,
                platform_author_id=flagged_msg.author_id,
                platform_timestamp=flagged_msg.timestamp,
                similarity_score=flagged_msg.match_score,
                dataset_name="bulk_scan",
                status="PENDING",
                priority="normal",
                reason=f"Flagged by bulk scan {scan_id}",
                request_metadata={
                    "scan_id": str(scan_id),
                    "matched_claim": flagged_msg.matched_claim,
                    "matched_source": flagged_msg.matched_source,
                    "match_score": flagged_msg.match_score,
                    "generate_ai_notes": generate_ai_notes,
                },
            )

            created_ids.append(request.request_id)

            logger.debug(
                "Created note request from bulk scan",
                extra={
                    "request_id": request.request_id,
                    "message_id": msg_id,
                    "scan_id": str(scan_id),
                    "match_score": flagged_msg.match_score,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to create note request",
                extra={
                    "message_id": msg_id,
                    "scan_id": str(scan_id),
                    "error": str(e),
                },
            )
            continue

    await session.commit()

    logger.info(
        "Note requests created from bulk scan",
        extra={
            "scan_id": str(scan_id),
            "requested_count": len(message_ids),
            "created_count": len(created_ids),
            "user_id": str(user_id),
        },
    )

    return created_ids


@router.post(
    "/scans",
    response_model=BulkScanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a bulk content scan",
    description="Start a new bulk content scan for a community server. "
    "This will scan message history and flag potentially misleading content. "
    "Requires admin access to the target community. Service accounts have unrestricted access.",
)
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

    logger.info(
        "Initiating bulk content scan",
        extra={
            "community_server_id": str(body.community_server_id),
            "user_id": str(current_user.id),
            "scan_window_days": body.scan_window_days,
            "channel_count": len(body.channel_ids),
        },
    )

    scan_log = await service.initiate_scan(
        community_server_id=body.community_server_id,
        initiated_by_user_id=current_user.id,
        scan_window_days=body.scan_window_days,
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
    "Requires admin access to the community that was scanned. Service accounts have unrestricted access.",
)
async def get_scan_results(
    scan_id: UUID,
    http_request: Request,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
    current_user: Annotated[User, Depends(get_current_user_for_bulk_scan)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BulkScanResultsResponse:
    """Get scan status and flagged results.

    Authorization: Requires admin access to the community that was scanned.
    Service accounts have unrestricted access.

    Args:
        scan_id: UUID of the scan
        http_request: HTTP request (for Discord claims)
        service: Bulk scan service
        current_user: Authenticated user
        session: Database session

    Returns:
        BulkScanResultsResponse with status and flagged messages

    Raises:
        HTTPException: 404 if scan not found, 403 if user lacks admin access
    """
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

    flagged_messages = await service.get_flagged_results(scan_id)

    return BulkScanResultsResponse(
        scan_id=scan_log.id,
        status=scan_log.status,
        messages_scanned=scan_log.messages_scanned,
        flagged_messages=flagged_messages,
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
) -> dict:
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

    created_ids = await create_note_requests_for_messages(
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
