from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastuuid import uuid7
from sqlalchemy import select

from src.monitoring import get_logger
from src.notes.models import Request

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


@dataclass
class CopyResult:
    total_copied: int
    total_skipped: int
    total_failed: int


class CopyRequestService:
    @staticmethod
    async def copy_requests(
        db: AsyncSession,
        source_community_server_id: UUID,
        target_community_server_id: UUID,
        on_progress: Callable[[int, int], None | Awaitable[None]] | None = None,
    ) -> CopyResult:
        stmt = (
            select(Request)
            .where(
                Request.community_server_id == source_community_server_id,
                Request.deleted_at.is_(None),
            )
            .order_by(Request.created_at)
        )
        result = await db.execute(stmt)
        source_requests = result.scalars().all()

        total = len(source_requests)
        copied = 0
        failed = 0

        for i, source_req in enumerate(source_requests):
            try:
                new_request_id = str(uuid7())

                metadata: dict[str, Any] = {
                    **(source_req.request_metadata or {}),
                    "copied_from": str(source_req.id),
                }

                new_request = Request(
                    request_id=new_request_id,
                    community_server_id=target_community_server_id,
                    message_archive_id=source_req.message_archive_id,
                    requested_by=source_req.requested_by,
                    dataset_item_id=source_req.dataset_item_id,
                    similarity_score=source_req.similarity_score,
                    dataset_name=source_req.dataset_name,
                    status="PENDING",
                    note_id=None,
                    request_metadata=metadata,
                )
                db.add(new_request)
                copied += 1

            except Exception as e:
                logger.warning(
                    "Failed to copy request",
                    extra={"source_request_id": str(source_req.id), "error": str(e)},
                )
                failed += 1

            if on_progress:
                _res = on_progress(i + 1, total)
                if inspect.isawaitable(_res):
                    await _res

        return CopyResult(total_copied=copied, total_skipped=0, total_failed=failed)
