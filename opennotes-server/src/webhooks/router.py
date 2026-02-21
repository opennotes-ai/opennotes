import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.community_dependencies import get_community_server_by_platform_id
from src.database import get_db
from src.webhooks.models import Webhook
from src.webhooks.rate_limit import rate_limiter
from src.webhooks.types import (
    WebhookConfigResponse,
    WebhookConfigSecure,
    WebhookCreateRequest,
    WebhookUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/register", response_model=WebhookConfigSecure)
async def register_webhook(
    webhook_request: WebhookCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> WebhookConfigSecure:
    # Look up or auto-create CommunityServer by platform ID
    community_server = await get_community_server_by_platform_id(
        db, webhook_request.platform_community_server_id, auto_create=True
    )
    if not community_server:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create or retrieve community server",
        )

    webhook = Webhook(
        url=webhook_request.url,
        secret=webhook_request.secret,
        community_server_id=community_server.id,
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


@router.get(
    "/by-community/{platform_community_server_id}", response_model=list[WebhookConfigResponse]
)
async def get_webhooks_by_community_server(
    platform_community_server_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[WebhookConfigResponse]:
    # Look up CommunityServer by platform ID (don't auto-create for GET)
    community_server = await get_community_server_by_platform_id(
        db, platform_community_server_id, auto_create=False
    )
    if not community_server:
        return []

    result = await db.execute(
        select(Webhook).where(
            Webhook.community_server_id == community_server.id, Webhook.active == True
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
    webhook_id: UUID,
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


@router.get("/stats/{platform_community_server_id}")
async def get_community_server_stats(
    platform_community_server_id: str,
) -> dict[str, Any]:
    rate_limit_info = await rate_limiter.get_rate_limit_info(platform_community_server_id)

    return {
        "platform_community_server_id": platform_community_server_id,
        "rate_limit": rate_limit_info,
    }
