from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bulk_content_scan.models import BulkContentScanLog
from src.config import get_settings


async def has_recent_scan(
    session: AsyncSession,
    community_server_id: UUID,
    window_days: int | None = None,
) -> bool:
    """Check if community has a completed scan within the configured window.

    Args:
        session: Database session
        community_server_id: The community server to check
        window_days: Override for the re-prompt window (defaults to config setting)

    Returns:
        True if a completed scan exists within the window, False otherwise
    """
    settings = get_settings()
    days = window_days or settings.BULK_CONTENT_SCAN_REPROMPT_DAYS
    cutoff = datetime.now(UTC) - timedelta(days=days)

    stmt = (
        select(BulkContentScanLog.id)
        .where(
            BulkContentScanLog.community_server_id == community_server_id,
            BulkContentScanLog.status == "completed",
            BulkContentScanLog.completed_at >= cutoff,
        )
        .limit(1)
    )

    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
