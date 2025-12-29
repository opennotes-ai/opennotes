"""
API router for chunk re-embedding operations.

This module provides endpoints for bulk re-chunking and re-embedding of:
- FactCheckItem content
- PreviouslySeenMessage content

These endpoints are useful for:
- Re-processing content after embedding model changes
- Migrating to chunk-based embeddings from full-document embeddings
- Refreshing embeddings with updated chunking parameters

Rate Limiting and Concurrency Control:
- Endpoints are rate-limited to 1 request per minute per user
- Only one rechunk operation can run per resource (table/community) at a time
- Returns 409 Conflict if an operation is already in progress

Status Tracking:
- Each rechunk operation returns a task_id for status polling
- Use GET /chunks/tasks/{task_id} to check progress
- Task status is stored in Redis with 24-hour TTL
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import verify_community_admin_by_uuid
from src.auth.dependencies import get_current_user_or_api_key
from src.cache.redis_client import redis_client
from src.config import settings
from src.database import get_db
from src.fact_checking.chunk_task_schemas import (
    RechunkTaskCreate,
    RechunkTaskResponse,
    RechunkTaskStartResponse,
    RechunkTaskStatus,
    RechunkTaskType,
)
from src.fact_checking.chunk_task_tracker import (
    RechunkTaskTracker,
    get_rechunk_task_tracker,
)
from src.fact_checking.models import FactCheckItem
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.middleware.rate_limiting import limiter
from src.monitoring import get_logger
from src.tasks.rechunk_tasks import (
    process_fact_check_rechunk_task,
    process_previously_seen_rechunk_task,
)
from src.users.models import User

logger = get_logger(__name__)

RECHUNK_LOCK_TTL_SECONDS = 3600
RECHUNK_LOCK_PREFIX = "rechunk:lock"


class RechunkLockManager:
    """
    Distributed lock manager for rechunk operations using Redis.

    Prevents multiple concurrent rechunk operations for the same resource.
    Uses Redis SET NX (set if not exists) with TTL for distributed locking.

    Redis Unavailability Behavior:
        When Redis is unavailable (e.g., during startup, network issues, or in
        test environments without Redis), this lock manager operates in "permissive"
        mode:
        - acquire_lock() returns True (allows operation to proceed)
        - release_lock() returns True (no-op)
        - is_locked() returns False (reports unlocked)

        This is intentional for development and graceful degradation, but means
        concurrent operations are not prevented when Redis is down. In production,
        ensure Redis is available for proper concurrency control.

        A warning is logged when operating without Redis so this behavior is
        visible in logs.
    """

    def __init__(self, redis: Redis | None = None):
        self._redis = redis

    @property
    def redis(self) -> Redis | None:
        """Get Redis client, falling back to global redis_client if not set."""
        if self._redis is not None:
            return self._redis
        return redis_client.client

    def _get_lock_key(self, operation: str, resource_id: str | None = None) -> str:
        """Generate lock key for an operation."""
        if resource_id:
            return f"{RECHUNK_LOCK_PREFIX}:{operation}:{resource_id}"
        return f"{RECHUNK_LOCK_PREFIX}:{operation}"

    async def acquire_lock(
        self,
        operation: str,
        resource_id: str | None = None,
        ttl: int = RECHUNK_LOCK_TTL_SECONDS,
    ) -> bool:
        """
        Attempt to acquire a lock for a rechunk operation.

        Args:
            operation: Operation type (e.g., 'fact_check', 'previously_seen')
            resource_id: Resource identifier (e.g., community_server_id)
            ttl: Lock TTL in seconds (default: 1 hour)

        Returns:
            True if lock was acquired, False if already locked
        """
        if not self.redis:
            logger.warning("Redis not available, allowing operation without lock")
            return True

        key = self._get_lock_key(operation, resource_id)
        try:
            result = await self.redis.set(key, "locked", nx=True, ex=ttl)
            if result:
                logger.info(
                    "Acquired rechunk lock",
                    extra={"operation": operation, "resource_id": resource_id, "key": key},
                )
            return result is not None
        except Exception as e:
            logger.error(
                "Failed to acquire rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "error": str(e)},
            )
            return True

    async def release_lock(self, operation: str, resource_id: str | None = None) -> bool:
        """
        Release a lock for a rechunk operation.

        Args:
            operation: Operation type (e.g., 'fact_check', 'previously_seen')
            resource_id: Resource identifier (e.g., community_server_id)

        Returns:
            True if lock was released, False otherwise
        """
        if not self.redis:
            return True

        key = self._get_lock_key(operation, resource_id)
        try:
            result = await self.redis.delete(key)
            logger.info(
                "Released rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "key": key},
            )
            return result > 0
        except Exception as e:
            logger.error(
                "Failed to release rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "error": str(e)},
            )
            return False

    async def is_locked(self, operation: str, resource_id: str | None = None) -> bool:
        """
        Check if a rechunk operation is currently locked.

        Args:
            operation: Operation type (e.g., 'fact_check', 'previously_seen')
            resource_id: Resource identifier (e.g., community_server_id)

        Returns:
            True if locked, False otherwise
        """
        if not self.redis:
            return False

        key = self._get_lock_key(operation, resource_id)
        try:
            result = await self.redis.exists(key)
            return result > 0
        except Exception as e:
            logger.error(
                "Failed to check rechunk lock",
                extra={"operation": operation, "resource_id": resource_id, "error": str(e)},
            )
            return False


rechunk_lock_manager = RechunkLockManager()

router = APIRouter(prefix="/chunks", tags=["chunks"])


@router.get(
    "/tasks/{task_id}",
    response_model=RechunkTaskResponse,
    summary="Get rechunk task status",
    description="Retrieve the current status and progress of a rechunk background task. "
    "If the task is associated with a community server, requires admin or moderator access. "
    "If the task was started without a community server (global credentials), only requires authentication.",
)
async def get_rechunk_task_status(
    request: Request,
    task_id: UUID,
    user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tracker: Annotated[RechunkTaskTracker, Depends(get_rechunk_task_tracker)],
) -> RechunkTaskResponse:
    """
    Get the status of a rechunk background task.

    Args:
        request: FastAPI request object
        task_id: The unique identifier of the task
        user: Authenticated user
        db: Database session
        tracker: Task tracker service

    Returns:
        Task status including progress metrics

    Raises:
        HTTPException: 403 if user lacks admin/moderator permission for the task's community
        HTTPException: 404 if task not found
    """
    task = await tracker.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found or has expired",
        )

    if task.community_server_id is not None:
        await verify_community_admin_by_uuid(
            community_server_id=task.community_server_id,
            current_user=user,
            db=db,
            request=request,
        )

    return task


@router.post(
    "/fact-check/rechunk",
    response_model=RechunkTaskStartResponse,
    summary="Re-chunk and re-embed fact check items",
    description="Initiates a background task to re-chunk and re-embed all fact check items. "
    "Useful for updating embeddings after model changes or migration to chunk-based embeddings. "
    "When community_server_id is provided, requires admin or moderator access. "
    "When not provided, uses global LLM credentials and only requires authentication. "
    "Rate limited to 1 request per minute. Returns 409 if operation already in progress.",
)
@limiter.limit("1/minute")
async def rechunk_fact_check_items(
    request: Request,
    user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tracker: Annotated[RechunkTaskTracker, Depends(get_rechunk_task_tracker)],
    community_server_id: UUID | None = Query(
        None,
        description="Community server ID for LLM credentials (optional, uses global fallback if not provided)",
    ),
    batch_size: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Number of items to process in each batch (1-1000)",
    ),
) -> RechunkTaskStartResponse:
    """
    Re-chunk and re-embed all fact check items.

    This endpoint initiates a background task that:
    1. Queries all FactCheckItem records
    2. Clears existing FactCheckChunk entries for each item
    3. Re-chunks the content using ChunkingService
    4. Generates new embeddings via LLMService
    5. Creates new FactCheckChunk entries

    When community_server_id is provided, requires admin or moderator access
    to that community. When not provided, uses global LLM credentials.
    Only one fact check rechunk operation can run at a time.

    Args:
        request: FastAPI request object
        user: Authenticated user (via API key or JWT)
        db: Database session
        tracker: Task tracker service
        community_server_id: Community server UUID for LLM credentials (optional)
        batch_size: Number of items to process per batch (default 100, max 1000)

    Returns:
        Task start response with task_id for status polling

    Raises:
        HTTPException: 403 if user lacks admin/moderator permission for the community
        HTTPException: 409 if a fact check rechunk operation is already in progress
    """
    if community_server_id is not None:
        await verify_community_admin_by_uuid(
            community_server_id=community_server_id,
            current_user=user,
            db=db,
            request=request,
        )

    lock_acquired = await rechunk_lock_manager.acquire_lock("fact_check")
    if not lock_acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A fact check rechunk operation is already in progress. "
            "Please wait for it to complete before starting a new one.",
        )

    try:
        result = await db.execute(select(func.count(FactCheckItem.id)))
        total_items = result.scalar_one()

        task = await tracker.create_task(
            RechunkTaskCreate(
                task_type=RechunkTaskType.FACT_CHECK,
                community_server_id=community_server_id,
                batch_size=batch_size,
                total_items=total_items,
            )
        )
    except Exception:
        await rechunk_lock_manager.release_lock("fact_check")
        raise

    await process_fact_check_rechunk_task.kiq(
        task_id=str(task.task_id),
        community_server_id=str(community_server_id) if community_server_id else None,
        batch_size=batch_size,
        db_url=settings.DATABASE_URL,
        redis_url=settings.REDIS_URL,
    )

    logger.info(
        "Started fact check rechunking task",
        extra={
            "task_id": str(task.task_id),
            "user_id": str(user.id),
            "community_server_id": str(community_server_id) if community_server_id else None,
            "batch_size": batch_size,
            "total_items": total_items,
        },
    )

    return RechunkTaskStartResponse(
        task_id=task.task_id,
        status=RechunkTaskStatus.PENDING,
        total_items=total_items,
        batch_size=batch_size,
        message=f"Re-chunking {total_items} fact check items in batches of {batch_size}",
    )


@router.post(
    "/previously-seen/rechunk",
    response_model=RechunkTaskStartResponse,
    summary="Re-chunk and re-embed previously seen messages",
    description="Initiates a background task to re-chunk and re-embed previously seen messages "
    "for the specified community. Useful for updating embeddings after model changes or "
    "migration to chunk-based embeddings. Requires admin or moderator access to the community server. "
    "Rate limited to 1 request per minute. Returns 409 if operation already in progress for this community.",
)
@limiter.limit("1/minute")
async def rechunk_previously_seen_messages(
    request: Request,
    user: Annotated[User, Depends(get_current_user_or_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tracker: Annotated[RechunkTaskTracker, Depends(get_rechunk_task_tracker)],
    community_server_id: UUID = Query(
        ..., description="Community server ID for filtering and LLM credentials"
    ),
    batch_size: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Number of items to process in each batch (1-1000)",
    ),
) -> RechunkTaskStartResponse:
    """
    Re-chunk and re-embed previously seen messages for a community.

    This endpoint initiates a background task that:
    1. Queries PreviouslySeenMessage records for the specified community
    2. Clears existing PreviouslySeenChunk entries for each message
    3. Re-chunks the content (from metadata) using ChunkingService
    4. Generates new embeddings via LLMService
    5. Creates new PreviouslySeenChunk entries

    Requires admin or moderator access to the community server.
    Only one rechunk operation can run per community at a time.

    Args:
        request: FastAPI request object
        user: Authenticated user (via API key or JWT)
        db: Database session
        tracker: Task tracker service
        community_server_id: Community server UUID for filtering and LLM credentials
        batch_size: Number of items to process per batch (default 100, max 1000)

    Returns:
        Task start response with task_id for status polling

    Raises:
        HTTPException: 403 if user lacks admin/moderator permission for the community
        HTTPException: 409 if a rechunk operation is already in progress for this community
    """
    await verify_community_admin_by_uuid(
        community_server_id=community_server_id,
        current_user=user,
        db=db,
        request=request,
    )

    lock_acquired = await rechunk_lock_manager.acquire_lock(
        "previously_seen", str(community_server_id)
    )
    if not lock_acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A previously seen message rechunk operation is already in progress "
            f"for community {community_server_id}. Please wait for it to complete.",
        )

    try:
        result = await db.execute(
            select(func.count(PreviouslySeenMessage.id)).where(
                PreviouslySeenMessage.community_server_id == community_server_id
            )
        )
        total_items = result.scalar_one()

        task = await tracker.create_task(
            RechunkTaskCreate(
                task_type=RechunkTaskType.PREVIOUSLY_SEEN,
                community_server_id=community_server_id,
                batch_size=batch_size,
                total_items=total_items,
            )
        )
    except Exception:
        await rechunk_lock_manager.release_lock("previously_seen", str(community_server_id))
        raise

    await process_previously_seen_rechunk_task.kiq(
        task_id=str(task.task_id),
        community_server_id=str(community_server_id),
        batch_size=batch_size,
        db_url=settings.DATABASE_URL,
        redis_url=settings.REDIS_URL,
    )

    logger.info(
        "Started previously seen message rechunking task",
        extra={
            "task_id": str(task.task_id),
            "user_id": str(user.id),
            "community_server_id": str(community_server_id),
            "batch_size": batch_size,
            "total_items": total_items,
        },
    )

    return RechunkTaskStartResponse(
        task_id=task.task_id,
        status=RechunkTaskStatus.PENDING,
        total_items=total_items,
        batch_size=batch_size,
        message=f"Re-chunking {total_items} previously seen messages in batches of {batch_size}",
    )
