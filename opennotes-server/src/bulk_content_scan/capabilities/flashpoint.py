"""Flashpoint detection capability for bulk content scanning."""

from src.bulk_content_scan.schemas import (
    BulkScanMessage,
    ContentItem,
    ConversationFlashpointMatch,
)
from src.monitoring import get_logger

logger = get_logger(__name__)


def _content_item_to_bulk_scan_message(item: ContentItem) -> BulkScanMessage:
    """Convert a ContentItem to a BulkScanMessage for the flashpoint service.

    The flashpoint service currently operates on BulkScanMessage. This adapter
    preserves all fields that flashpoint detection uses (content, author, context).
    """
    return BulkScanMessage(
        message_id=item.content_id,
        channel_id=item.channel_id,
        community_server_id=item.community_server_id,
        content=item.content_text,
        author_id=item.author_id,
        author_username=item.author_username,
        timestamp=item.timestamp,
        attachment_urls=item.attachment_urls,
    )


async def detect_flashpoint(
    content_item: ContentItem,
    context_items: list[ContentItem],
    flashpoint_service: object,
) -> ConversationFlashpointMatch | None:
    """Run flashpoint detection on the given content item.

    Detects early warning signs that a conversation may derail into conflict
    using a DSPy-optimized prompt trained on the Conversations Gone Awry corpus.

    The flashpoint_service parameter is typed as object to avoid importing
    FlashpointDetectionService (which has heavy deps) at module load time.
    Pass a FlashpointDetectionService instance or None.

    Args:
        content_item: The platform-agnostic content item to analyze.
        context_items: Previous content items in the channel (time-ordered).
        flashpoint_service: FlashpointDetectionService instance, or None if not configured.

    Returns:
        ConversationFlashpointMatch if a flashpoint was detected, None otherwise.
    """
    if flashpoint_service is None:
        logger.debug(
            "Flashpoint service not configured",
            extra={"content_id": content_item.content_id},
        )
        return None

    try:
        message = _content_item_to_bulk_scan_message(content_item)
        context_messages = [_content_item_to_bulk_scan_message(item) for item in context_items]

        return await flashpoint_service.detect_flashpoint(
            message=message,
            context_messages=context_messages,
        )

    except Exception as e:
        logger.warning(
            "Error in flashpoint detection capability",
            extra={
                "content_id": content_item.content_id,
                "error": str(e),
            },
        )

    return None
