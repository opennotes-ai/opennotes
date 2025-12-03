import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.webhooks.cache import interaction_cache
from src.webhooks.models import Interaction, Task
from src.webhooks.queue import task_queue
from src.webhooks.rate_limit import rate_limiter
from src.webhooks.responses import create_deferred_response, create_message_response
from src.webhooks.types import DiscordInteraction, InteractionType

logger = logging.getLogger(__name__)


class WebhookHandler:
    async def handle_interaction(
        self,
        interaction: DiscordInteraction,
        db: AsyncSession,
    ) -> dict[str, Any]:
        if await interaction_cache.check_duplicate(interaction.id):
            logger.warning(f"Duplicate interaction {interaction.id}")
            cached = await interaction_cache.get_cached_response(interaction.id)
            if cached:
                return cached
            logger.error(f"Duplicate interaction {interaction.id} has no cached response")
            return create_message_response(
                content="This interaction has already been processed.",
                ephemeral=True,
            )

        if interaction.community_server_id:
            allowed, _remaining = await rate_limiter.check_rate_limit(
                community_server_id=interaction.community_server_id,
                user_id=interaction.user_id,
            )

            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for community server {interaction.community_server_id} "
                    f"user {interaction.user_id}"
                )
                response = create_message_response(
                    content="Rate limit exceeded. Please try again later.",
                    ephemeral=True,
                )
                await interaction_cache.cache_response(interaction.id, response)
                return response

        if interaction.type == InteractionType.PING:
            response = await self._handle_ping(interaction, db)
        elif interaction.type == InteractionType.APPLICATION_COMMAND:
            response = await self._handle_command(interaction, db)
        elif interaction.type == InteractionType.MESSAGE_COMPONENT:
            response = await self._handle_component(interaction, db)
        elif interaction.type == InteractionType.APPLICATION_COMMAND_AUTOCOMPLETE:
            response = await self._handle_autocomplete(interaction, db)
        elif interaction.type == InteractionType.MODAL_SUBMIT:
            response = await self._handle_modal(interaction, db)
        else:
            logger.warning(f"Unknown interaction type: {interaction.type}")
            response = create_message_response(
                content="Unknown interaction type",
                ephemeral=True,
            )

        await interaction_cache.cache_response(interaction.id, response)
        await interaction_cache.mark_processed(interaction.id)

        return response

    async def _handle_ping(
        self,
        interaction: DiscordInteraction,
        db: AsyncSession,
    ) -> dict[str, int]:
        logger.info("Handling PING interaction")

        await self._log_interaction(interaction, db, response_type=1)

        return {"type": 1}

    async def _handle_command(
        self,
        interaction: DiscordInteraction,
        db: AsyncSession,
    ) -> dict[str, Any]:
        logger.info(f"Handling command: {interaction.command_name}")

        await self._log_interaction(interaction, db)

        task_id = await task_queue.enqueue(
            task_type="command",
            task_data={
                "interaction_id": interaction.id,
                "interaction_token": interaction.token,
                "application_id": interaction.application_id,
                "community_server_id": interaction.community_server_id,
                "channel_id": interaction.channel_id,
                "user_id": interaction.user_id,
                "command_name": interaction.command_name,
                "data": interaction.data.model_dump() if interaction.data else None,
            },
        )

        task = Task(
            task_id=task_id,
            interaction_id=interaction.id,
            interaction_token=interaction.token,
            application_id=interaction.application_id,
            task_type="command",
            status="pending",
            task_data={
                "command_name": interaction.command_name,
                "community_server_id": interaction.community_server_id,
                "channel_id": interaction.channel_id,
                "user_id": interaction.user_id,
                "data": interaction.data.model_dump() if interaction.data else None,
            },
        )
        db.add(task)
        await db.commit()

        return create_deferred_response()

    async def _handle_component(
        self,
        interaction: DiscordInteraction,
        db: AsyncSession,
    ) -> dict[str, Any]:
        custom_id = interaction.data.custom_id if interaction.data else "unknown"
        logger.info(f"Handling component: {custom_id}")

        await self._log_interaction(interaction, db)

        task_id = await task_queue.enqueue(
            task_type="component",
            task_data={
                "interaction_id": interaction.id,
                "interaction_token": interaction.token,
                "application_id": interaction.application_id,
                "community_server_id": interaction.community_server_id,
                "channel_id": interaction.channel_id,
                "user_id": interaction.user_id,
                "custom_id": custom_id,
                "data": interaction.data.model_dump() if interaction.data else None,
            },
        )

        task = Task(
            task_id=task_id,
            interaction_id=interaction.id,
            interaction_token=interaction.token,
            application_id=interaction.application_id,
            task_type="component",
            status="pending",
            task_data={
                "custom_id": custom_id,
                "community_server_id": interaction.community_server_id,
                "channel_id": interaction.channel_id,
                "user_id": interaction.user_id,
                "data": interaction.data.model_dump() if interaction.data else None,
            },
        )
        db.add(task)
        await db.commit()

        return create_deferred_response(is_update=True)

    async def _handle_autocomplete(
        self,
        interaction: DiscordInteraction,
        db: AsyncSession,
    ) -> dict[str, Any]:
        logger.info(f"Handling autocomplete for: {interaction.command_name}")

        await self._log_interaction(interaction, db)

        return {
            "type": 8,
            "data": {
                "choices": [],
            },
        }

    async def _handle_modal(
        self,
        interaction: DiscordInteraction,
        db: AsyncSession,
    ) -> dict[str, Any]:
        custom_id = interaction.data.custom_id if interaction.data else "unknown"
        logger.info(f"Handling modal submit: {custom_id}")

        await self._log_interaction(interaction, db)

        task_id = await task_queue.enqueue(
            task_type="modal",
            task_data={
                "interaction_id": interaction.id,
                "interaction_token": interaction.token,
                "application_id": interaction.application_id,
                "community_server_id": interaction.community_server_id,
                "channel_id": interaction.channel_id,
                "user_id": interaction.user_id,
                "custom_id": custom_id,
                "data": interaction.data.model_dump() if interaction.data else None,
            },
        )

        task = Task(
            task_id=task_id,
            interaction_id=interaction.id,
            interaction_token=interaction.token,
            application_id=interaction.application_id,
            task_type="modal",
            status="pending",
            task_data={
                "custom_id": custom_id,
                "community_server_id": interaction.community_server_id,
                "channel_id": interaction.channel_id,
                "user_id": interaction.user_id,
                "data": interaction.data.model_dump() if interaction.data else None,
            },
        )
        db.add(task)
        await db.commit()

        return create_deferred_response()

    async def _log_interaction(
        self,
        interaction: DiscordInteraction,
        db: AsyncSession,
        response_type: int | None = None,
    ) -> None:
        interaction_record = Interaction(
            interaction_id=interaction.id,
            interaction_type=interaction.type,
            community_server_id=interaction.community_server_id,
            channel_id=interaction.channel_id,
            user_id=interaction.user_id,
            command_name=interaction.command_name,
            data=interaction.data.model_dump() if interaction.data else None,
            response_sent=True,
            response_type=response_type,
            processed_at=datetime.now(UTC).replace(tzinfo=None),
        )

        db.add(interaction_record)
        await db.commit()


webhook_handler = WebhookHandler()
