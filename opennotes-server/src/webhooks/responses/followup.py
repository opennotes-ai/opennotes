import logging
from typing import Any, cast

import httpx

from src.config import settings
from src.webhooks.types import Embed

logger = logging.getLogger(__name__)


async def send_followup_message(
    application_id: str,
    interaction_token: str,
    content: str | None = None,
    embeds: list[Embed] | list[dict[str, Any]] | None = None,
    components: list[dict[str, Any]] | None = None,
    ephemeral: bool = False,
) -> dict[str, Any] | None:
    url = f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}"

    payload: dict[str, Any] = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds
    if components:
        payload["components"] = components
    if ephemeral:
        payload["flags"] = 64

    headers = {
        "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
    except httpx.HTTPError as e:
        logger.error(f"Failed to send followup message: {e}")
        return None
