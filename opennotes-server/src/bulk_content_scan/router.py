"""API router for Bulk Content Scan endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_or_api_key
from src.bulk_content_scan.repository import has_recent_scan
from src.bulk_content_scan.schemas import (
    BulkScanCreateRequest,
    BulkScanResponse,
    BulkScanResultsResponse,
    CreateNoteRequestsRequest,
    NoteRequestsResponse,
)
from src.bulk_content_scan.service import BulkContentScanService
from src.cache.redis_client import redis_client
from src.database import get_db
from src.fact_checking.embedding_router import get_embedding_service
from src.fact_checking.embedding_service import EmbeddingService
from src.monitoring import get_logger
from src.users.models import User

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


async def create_note_requests_for_messages(
    message_ids: list[str],
    scan_id: UUID,
    session: AsyncSession,
    user_id: UUID,
    generate_ai_notes: bool = False,
) -> list[str]:
    """Create note requests for flagged messages.

    This is a placeholder that would integrate with the existing
    Request model and optionally trigger AI note generation.

    Args:
        message_ids: List of message IDs to create requests for
        scan_id: UUID of the scan these messages came from
        session: Database session
        user_id: UUID of the user making the request
        generate_ai_notes: Whether to generate AI draft notes

    Returns:
        List of created request IDs
    """
    logger.info(
        "Creating note requests from bulk scan",
        extra={
            "scan_id": str(scan_id),
            "message_count": len(message_ids),
            "user_id": str(user_id),
            "generate_ai_notes": generate_ai_notes,
        },
    )

    created_ids = []
    for msg_id in message_ids:
        created_ids.append(f"req_{msg_id}")

    return created_ids


@router.post(
    "/scans",
    response_model=BulkScanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a bulk content scan",
    description="Start a new bulk content scan for a community server. "
    "This will scan message history and flag potentially misleading content.",
)
async def initiate_scan(
    request: BulkScanCreateRequest,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
    current_user: Annotated[User, Depends(get_current_user_for_bulk_scan)],
) -> BulkScanResponse:
    """Initiate a new bulk content scan.

    Args:
        request: Scan initiation request
        service: Bulk scan service
        current_user: Authenticated user

    Returns:
        BulkScanResponse with scan_id and status
    """
    logger.info(
        "Initiating bulk content scan",
        extra={
            "community_server_id": str(request.community_server_id),
            "user_id": str(current_user.id),
            "scan_window_days": request.scan_window_days,
            "channel_count": len(request.channel_ids),
        },
    )

    scan_log = await service.initiate_scan(
        community_server_id=request.community_server_id,
        initiated_by_user_id=current_user.id,
        scan_window_days=request.scan_window_days,
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
    description="Retrieve the status and flagged results for a bulk content scan.",
)
async def get_scan_results(
    scan_id: UUID,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
) -> BulkScanResultsResponse:
    """Get scan status and flagged results.

    Args:
        scan_id: UUID of the scan
        service: Bulk scan service

    Returns:
        BulkScanResultsResponse with status and flagged messages

    Raises:
        HTTPException: 404 if scan not found
    """
    scan_log = await service.get_scan(scan_id)

    if not scan_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found",
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
    description="Check if a community server has had a recent bulk content scan.",
)
async def check_recent_scan(
    community_server_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Check if community has a recent scan within the configured window.

    Args:
        community_server_id: UUID of the community server
        session: Database session

    Returns:
        Dict with has_recent_scan boolean
    """
    result = await has_recent_scan(session, community_server_id)
    return {"has_recent_scan": result}


@router.post(
    "/scans/{scan_id}/note-requests",
    response_model=NoteRequestsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create note requests from scan",
    description="Create note requests for selected flagged messages from a bulk scan.",
)
async def create_note_requests(
    scan_id: UUID,
    request: CreateNoteRequestsRequest,
    service: Annotated[BulkContentScanService, Depends(get_bulk_scan_service)],
    current_user: Annotated[User, Depends(get_current_user_for_bulk_scan)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NoteRequestsResponse:
    """Create note requests for selected flagged messages.

    Args:
        scan_id: UUID of the scan
        request: Request with message IDs
        service: Bulk scan service
        current_user: Authenticated user
        session: Database session

    Returns:
        NoteRequestsResponse with created count

    Raises:
        HTTPException: 404 if scan not found
    """
    scan_log = await service.get_scan(scan_id)

    if not scan_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found",
        )

    created_ids = await create_note_requests_for_messages(
        message_ids=request.message_ids,
        scan_id=scan_id,
        session=session,
        user_id=current_user.id,
        generate_ai_notes=request.generate_ai_notes,
    )

    return NoteRequestsResponse(
        created_count=len(created_ids),
        request_ids=created_ids,
    )
