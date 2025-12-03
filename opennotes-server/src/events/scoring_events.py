from uuid import UUID

from src.events.publisher import event_publisher
from src.monitoring import get_logger

logger = get_logger(__name__)


class ScoringEventPublisher:
    """
    Publishes scoring-related events to NATS for consumption by Discord bot
    and other services.

    Deprecated: Use event_publisher.publish_note_score_updated() directly instead.
    This class is maintained for backward compatibility.
    """

    @staticmethod
    async def publish_note_score_updated(
        note_id: UUID,
        score: float,
        confidence: str,
        algorithm: str,
        rating_count: int,
        tier: int,
        tier_name: str,
        original_message_id: str | None = None,
        channel_id: str | None = None,
        community_server_id: str | None = None,
    ) -> None:
        """
        Publish a note.score.updated event when a note's score is calculated or updated.

        Args:
            note_id: The note ID
            score: Calculated score (0.0-1.0)
            confidence: Confidence level (no_data, provisional, standard)
            algorithm: Algorithm used for scoring
            rating_count: Number of ratings used
            tier: Scoring tier level
            tier_name: Scoring tier name
            original_message_id: Message ID where note was created (optional)
            channel_id: Channel ID (optional)
            community_server_id: Community server ID (optional)

        Raises:
            Exception: Propagates any exception from event publishing
        """
        try:
            await event_publisher.publish_note_score_updated(
                note_id=note_id,
                score=score,
                confidence=confidence,
                algorithm=algorithm,
                rating_count=rating_count,
                tier=tier,
                tier_name=tier_name,
                original_message_id=original_message_id,
                channel_id=channel_id,
                community_server_id=community_server_id,
            )

            logger.info(
                "Published note.score.updated event",
                extra={
                    "note_id": note_id,
                    "score": score,
                    "confidence": confidence,
                    "rating_count": rating_count,
                    "has_message_context": original_message_id is not None,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to publish note.score.updated event",
                extra={
                    "note_id": note_id,
                    "error": str(e),
                },
            )
            raise
