import logging
from typing import Any, cast

import httpx

from src.config import settings
from src.webhooks.types import Embed

logger = logging.getLogger(__name__)


class DiscordClient:
    def __init__(
        self,
        application_id: str,
        base_url: str = "https://discord.com/api/v10",
        timeout: float = 30.0,
    ) -> None:
        self.application_id = application_id
        self.base_url = base_url
        self.timeout = timeout
        self.client: httpx.AsyncClient | None = None
        self._closed = False

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self.client is None or self._closed:
            self.client = httpx.AsyncClient(timeout=self.timeout)
            self._closed = False
        return self.client

    async def __aenter__(self) -> "DiscordClient":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def send_followup_message(
        self,
        interaction_token: str,
        content: str | None = None,
        embeds: list[Embed] | list[dict[str, Any]] | None = None,
        ephemeral: bool = False,
    ) -> dict[str, Any]:
        client = await self._ensure_client()
        url = f"{self.base_url}/webhooks/{self.application_id}/{interaction_token}"

        payload: dict[str, Any] = {}

        if content:
            payload["content"] = content

        if embeds:
            payload["embeds"] = embeds

        if ephemeral:
            payload["flags"] = 64

        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            logger.error(f"Discord API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.exception(f"Failed to send followup message: {e}")
            raise

    async def edit_original_response(
        self,
        interaction_token: str,
        content: str | None = None,
        embeds: list[Embed] | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        client = await self._ensure_client()
        url = (
            f"{self.base_url}/webhooks/{self.application_id}/{interaction_token}/messages/@original"
        )

        payload: dict[str, Any] = {}

        if content:
            payload["content"] = content

        if embeds:
            payload["embeds"] = embeds

        try:
            response = await client.patch(url, json=payload)
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            logger.error(f"Discord API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.exception(f"Failed to edit original response: {e}")
            raise

    async def close(self) -> None:
        if self.client and not self._closed:
            await self.client.aclose()
            self._closed = True
            logger.debug("DiscordClient closed")


_shared_discord_client: DiscordClient | None = None


def get_discord_client() -> DiscordClient:
    global _shared_discord_client  # noqa: PLW0603 - Module-level lazy-loaded singleton for shared Discord client instance
    if _shared_discord_client is None:
        _shared_discord_client = DiscordClient(
            application_id=settings.DISCORD_APPLICATION_ID,
            base_url=settings.DISCORD_API_URL,
            timeout=settings.DISCORD_API_TIMEOUT,
        )
    return _shared_discord_client


async def close_discord_client() -> None:
    global _shared_discord_client  # noqa: PLW0603 - Cleanup module-level singleton on shutdown
    if _shared_discord_client:
        await _shared_discord_client.close()
        _shared_discord_client = None
