"""Similarity search capability for bulk content scanning."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.bulk_content_scan.schemas import ContentItem, SimilarityMatch
from src.config import settings
from src.fact_checking.embedding_service import EmbeddingService
from src.monitoring import get_logger

logger = get_logger(__name__)


async def search_similar_claims(
    content_item: ContentItem,
    embedding_service: EmbeddingService,
    session: AsyncSession,
    threshold: float | None = None,
) -> SimilarityMatch | None:
    """Search for fact-check claims similar to the given content item.

    Args:
        content_item: The platform-agnostic content item to check.
        embedding_service: Service for performing embedding-based similarity search.
        session: AsyncSession for database queries.
        threshold: Similarity threshold (defaults to settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD).

    Returns:
        SimilarityMatch if a match was found above the threshold, None otherwise.
    """
    if threshold is None:
        threshold = settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD

    try:
        search_response = await embedding_service.similarity_search(
            db=session,
            query_text=content_item.content_text,
            community_server_id=content_item.community_server_id,
            dataset_tags=[],
            similarity_threshold=threshold,
            score_threshold=0.1,
            limit=1,
        )

        if search_response.matches:
            best_match = search_response.matches[0]
            matched_content = best_match.content or best_match.title or ""

            return SimilarityMatch(
                score=best_match.similarity_score,
                matched_claim=matched_content,
                matched_source=best_match.source_url or "",
                fact_check_item_id=best_match.id,
            )

    except Exception as e:
        logger.warning(
            "Error in similarity search capability",
            extra={
                "content_id": content_item.content_id,
                "error": str(e),
            },
        )

    return None
