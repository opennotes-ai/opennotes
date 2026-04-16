"""OpenAI content moderation capability for bulk content scanning."""

from typing import Any

from src.bulk_content_scan.schemas import ContentItem, OpenAIModerationMatch
from src.monitoring import get_logger

logger = get_logger(__name__)


async def check_content_moderation(
    content_item: ContentItem,
    moderation_service: Any,
) -> OpenAIModerationMatch | None:
    """Run OpenAI content moderation on the given content item.

    Args:
        content_item: The platform-agnostic content item to moderate.
        moderation_service: OpenAIModerationService instance, or None if not configured.

    Returns:
        OpenAIModerationMatch if the content was flagged, None otherwise.
    """
    if moderation_service is None:
        logger.warning(
            "Moderation service not configured",
            extra={"content_id": content_item.content_id},
        )
        return None

    try:
        if content_item.attachment_urls:
            moderation_result = await moderation_service.moderate_multimodal(
                text=content_item.content_text,
                image_urls=content_item.attachment_urls,
            )
        else:
            moderation_result = await moderation_service.moderate_text(content_item.content_text)

        if moderation_result.flagged:
            return OpenAIModerationMatch(
                max_score=moderation_result.max_score,
                categories=moderation_result.categories,
                scores=moderation_result.scores,
                flagged_categories=moderation_result.flagged_categories,
            )

    except Exception as e:
        logger.warning(
            "Error in content moderation capability",
            extra={
                "content_id": content_item.content_id,
                "error": str(e),
            },
        )

    return None
