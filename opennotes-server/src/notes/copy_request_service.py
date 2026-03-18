from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastuuid import uuid7
from sqlalchemy import select

from src.monitoring import get_logger
from src.notes.models import Request
from src.notes.request_service import RequestService

if TYPE_CHECKING:
    from collections.abc import Callable

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
        on_progress: Callable[[int, int], None] | None = None,
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
        skipped = 0
        failed = 0

        for i, source_req in enumerate(source_requests):
            try:
                if source_req.message_archive is None:
                    skipped += 1
                    if on_progress:
                        on_progress(i + 1, total)
                    continue

                content = source_req.message_archive.get_content() or ""
                new_request_id = str(uuid7())

                metadata: dict[str, Any] = {
                    **(source_req.request_metadata or {}),
                    "copied_from": str(source_req.id),
                }

                await RequestService.create_from_message(
                    db=db,
                    request_id=new_request_id,
                    content=content,
                    community_server_id=target_community_server_id,
                    requested_by=source_req.requested_by,
                    platform_message_id=source_req.message_archive.platform_message_id,
                    platform_channel_id=source_req.message_archive.platform_channel_id,
                    platform_author_id=source_req.message_archive.platform_author_id,
                    platform_timestamp=source_req.message_archive.platform_timestamp,
                    dataset_item_id=source_req.dataset_item_id,
                    similarity_score=source_req.similarity_score,
                    dataset_name=source_req.dataset_name,
                    status="PENDING",
                    note_id=None,
                    request_metadata=metadata,
                )
                copied += 1

            except Exception as e:
                logger.warning(
                    "Failed to copy request",
                    extra={"source_request_id": str(source_req.id), "error": str(e)},
                )
                failed += 1

            if on_progress:
                on_progress(i + 1, total)

        return CopyResult(total_copied=copied, total_skipped=skipped, total_failed=failed)
