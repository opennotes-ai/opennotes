from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm_config.models import CommunityServer


@dataclass(frozen=True, slots=True)
class ScoreEventRoutingContext:
    original_message_id: str | None
    channel_id: str | None
    community_server_id: str | None


async def build_score_event_routing_context(
    db: AsyncSession, note: Any
) -> ScoreEventRoutingContext:
    request = getattr(note, "request", None)
    message_archive = getattr(request, "message_archive", None)

    original_message_id = None
    channel_id = None
    if message_archive:
        original_message_id = getattr(message_archive, "platform_message_id", None)
        channel_id = getattr(message_archive, "platform_channel_id", None)

    channel_id = channel_id or getattr(note, "channel_id", None)

    community_server_id = None
    note_community_server_id = getattr(note, "community_server_id", None)
    if note_community_server_id:
        platform_id_result = await db.execute(
            select(CommunityServer.platform_community_server_id).where(
                CommunityServer.id == note_community_server_id
            )
        )
        community_server_id = platform_id_result.scalar_one_or_none()

    return ScoreEventRoutingContext(
        original_message_id=original_message_id,
        channel_id=channel_id,
        community_server_id=community_server_id,
    )
