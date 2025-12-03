import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.webhooks.discord_client import DiscordClient, get_discord_client
from src.webhooks.models import Task
from src.webhooks.types import (
    CommandResultData,
    ComponentResultData,
    ModalResultData,
    QueueTaskData,
)

logger = logging.getLogger(__name__)


class TaskProcessor:
    def __init__(self, db: AsyncSession, discord_client: DiscordClient | None = None) -> None:
        self.db = db
        self.discord_client = discord_client or get_discord_client()

    async def process_task(self, task_data: QueueTaskData) -> None:
        task_id = task_data["id"]
        task_type = task_data["type"]
        data = task_data["data"]

        result = await self.db.execute(select(Task).where(Task.task_id == task_id))
        task = result.scalar_one_or_none()

        if not task:
            logger.error(f"Task {task_id} not found in database")
            return

        try:
            task.status = "processing"
            task.started_at = datetime.now(UTC)
            await self.db.commit()

            if task_type == "command":
                await self._process_command(task, data)
            elif task_type == "component":
                await self._process_component(task, data)
            elif task_type == "modal":
                await self._process_modal(task, data)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

            task.status = "completed"
            task.completed_at = datetime.now(UTC)
            await self.db.commit()

        except Exception as e:
            logger.exception(f"Error processing task {task_id}: {e}")
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise

    async def _process_command(self, task: Task, data: dict[str, Any]) -> None:
        command_name = data.get("command_name")
        logger.info(f"Processing command: {command_name}")

        content = f"Command `{command_name}` processed successfully!"
        result_data: CommandResultData = {
            "command": command_name or "",
            "processed_at": datetime.now(UTC).isoformat(),
        }

        await self.discord_client.send_followup_message(
            interaction_token=task.interaction_token,
            content=content,
        )

        task.result = dict(result_data)

    async def _process_component(self, task: Task, data: dict[str, Any]) -> None:
        custom_id = data.get("custom_id")
        logger.info(f"Processing component: {custom_id}")

        content = f"Component `{custom_id}` processed successfully!"
        result_data: ComponentResultData = {
            "custom_id": custom_id or "",
            "processed_at": datetime.now(UTC).isoformat(),
        }

        await self.discord_client.send_followup_message(
            interaction_token=task.interaction_token,
            content=content,
        )

        task.result = dict(result_data)

    async def _process_modal(self, task: Task, data: dict[str, Any]) -> None:
        custom_id = data.get("custom_id")
        logger.info(f"Processing modal: {custom_id}")

        content = f"Modal `{custom_id}` processed successfully!"
        result_data: ModalResultData = {
            "custom_id": custom_id or "",
            "processed_at": datetime.now(UTC).isoformat(),
        }

        await self.discord_client.send_followup_message(
            interaction_token=task.interaction_token,
            content=content,
        )

        task.result = dict(result_data)
