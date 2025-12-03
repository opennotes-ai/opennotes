import json
import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import DatabaseError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.webhooks.handler import webhook_handler
from src.webhooks.models import Task, Webhook
from src.webhooks.queue import task_queue
from src.webhooks.rate_limit import rate_limiter
from src.webhooks.types import (
    DiscordInteraction,
    TaskStatus,
    WebhookConfigResponse,
    WebhookConfigSecure,
    WebhookCreateRequest,
    WebhookUpdateRequest,
)
from src.webhooks.verification import verify_discord_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/discord/interactions")
async def handle_discord_interaction(
    request: Request,
    x_signature_ed25519: Annotated[str, Header()],
    x_signature_timestamp: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    body = await request.body()

    if not verify_discord_signature(
        body=body,
        signature=x_signature_ed25519,
        timestamp=x_signature_timestamp,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid request signature",
        )

    try:
        interaction_data = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {e!s}",
        )

    try:
        interaction = DiscordInteraction(**interaction_data)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid interaction data: {e.errors()}",
        )

    try:
        return await webhook_handler.handle_interaction(interaction, db)
    except DatabaseError as e:
        logger.exception(f"Database error handling interaction: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )
    except Exception as e:
        logger.exception(f"Error handling interaction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process interaction",
        )


@router.post("/register", response_model=WebhookConfigSecure)
async def register_webhook(
    webhook_request: WebhookCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> WebhookConfigSecure:
    webhook = Webhook(
        url=webhook_request.url,
        secret=webhook_request.secret,
        community_server_id=webhook_request.community_server_id,
        channel_id=webhook_request.channel_id,
        active=True,
    )

    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    return WebhookConfigSecure(
        id=webhook.id,
        url=webhook.url,
        secret=webhook.secret,
        community_server_id=webhook.community_server_id,
        channel_id=webhook.channel_id,
        active=webhook.active,
    )


@router.get("/{community_server_id}", response_model=list[WebhookConfigResponse])
async def get_webhooks_by_community_server(
    community_server_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[WebhookConfigResponse]:
    result = await db.execute(
        select(Webhook).where(
            Webhook.community_server_id == community_server_id, Webhook.active == True
        )
    )
    webhooks = result.scalars().all()

    return [
        WebhookConfigResponse(
            id=w.id,
            url=w.url,
            community_server_id=w.community_server_id,
            channel_id=w.channel_id,
            active=w.active,
        )
        for w in webhooks
    ]


@router.put("/{webhook_id}", response_model=WebhookConfigResponse)
async def update_webhook(
    webhook_id: UUID,
    webhook_update: WebhookUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> WebhookConfigResponse:
    result = await db.execute(select(Webhook).where(Webhook.id == webhook_id))
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    if webhook_update.url is not None:
        webhook.url = webhook_update.url
    if webhook_update.secret is not None:
        webhook.secret = webhook_update.secret
    if webhook_update.channel_id is not None:
        webhook.channel_id = webhook_update.channel_id
    if webhook_update.active is not None:
        webhook.active = webhook_update.active

    await db.commit()
    await db.refresh(webhook)

    return WebhookConfigResponse(
        id=webhook.id,
        url=webhook.url,
        community_server_id=webhook.community_server_id,
        channel_id=webhook.channel_id,
        active=webhook.active,
    )


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(Webhook).where(Webhook.id == webhook_id))
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    webhook.active = False
    await db.commit()

    return {"message": "Webhook deactivated successfully"}


@router.get("/health/webhooks")
async def webhook_health() -> dict[str, Any]:
    try:
        queue_stats = await task_queue.get_queue_stats()

        return {
            "status": "healthy",
            "service": "webhooks",
            "queue": queue_stats,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy",
        )


@router.get("/stats/{community_server_id}")
async def get_community_server_stats(
    community_server_id: str,
) -> dict[str, Any]:
    rate_limit_info = await rate_limiter.get_rate_limit_info(community_server_id)

    return {
        "community_server_id": community_server_id,
        "rate_limit": rate_limit_info,
    }


@router.get("/tasks/by-interaction/{interaction_id}", response_model=TaskStatus)
async def get_task_by_interaction(
    interaction_id: str,
    db: AsyncSession = Depends(get_db),
) -> TaskStatus:
    result = await db.execute(select(Task).where(Task.interaction_id == interaction_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return TaskStatus(
        task_id=task.task_id,
        interaction_id=task.interaction_id,
        task_type=task.task_type,
        status=task.status,
        result=task.result,
        error=task.error,
        retry_count=task.retry_count,
        created_at=task.created_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


@router.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_by_id(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> TaskStatus:
    result = await db.execute(select(Task).where(Task.task_id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return TaskStatus(
        task_id=task.task_id,
        interaction_id=task.interaction_id,
        task_type=task.task_type,
        status=task.status,
        result=task.result,
        error=task.error,
        retry_count=task.retry_count,
        created_at=task.created_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )
