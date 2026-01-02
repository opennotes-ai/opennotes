"""Service for automatically generating community notes using AI for fact-check matches."""

import asyncio
import contextlib
import time
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.events.schemas import EventType, RequestAutoCreatedEvent
from src.events.subscriber import event_subscriber
from src.fact_checking.models import FactCheckItem
from src.llm_config.models import CommunityServer
from src.llm_config.providers.base import LLMMessage
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.monitoring.instance import InstanceMetadata
from src.monitoring.metrics import (
    ai_note_generation_duration_seconds,
    ai_notes_failed_total,
    ai_notes_generated_total,
)
from src.notes import loaders as note_loaders
from src.notes.message_archive_models import ContentType
from src.notes.models import Note, Request
from src.services.vision_service import VisionService
from src.tasks.content_monitoring_tasks import generate_ai_note_task
from src.webhooks.rate_limit import rate_limiter

logger = get_logger(__name__)


class NoteGenerationStrategy(str, Enum):
    """Strategy for generating AI notes based on available data."""

    FACT_CHECK = "fact_check"  # Note based on fact-check match (requires dataset_item_id)
    GENERAL_EXPLANATION = (
        "general_explanation"  # General explanation (default, no fact-check required)
    )


class AINoteWriter:
    """
    Service for automatically generating community notes using AI.

    Listens to REQUEST_AUTO_CREATED events and generates notes when:
    - A request is auto-created with a fact-check match
    - AI note writing is enabled for the community server
    - Rate limits are not exceeded
    """

    def __init__(
        self, llm_service: LLMService, vision_service: VisionService | None = None
    ) -> None:
        """
        Initialize AI note writer service.

        Args:
            llm_service: LLM service for generating note content
            vision_service: Optional vision service for generating image descriptions
        """
        self.llm_service = llm_service
        self.vision_service = vision_service
        self._subscription_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start listening for auto-created request events."""
        if self._running:
            logger.warning("AINoteWriter already running")
            return

        self._running = True
        logger.info("Starting AINoteWriter service")

        # Register handler and subscribe to REQUEST_AUTO_CREATED events
        event_subscriber.register_handler(
            event_type=EventType.REQUEST_AUTO_CREATED,
            handler=self._handle_request_auto_created,
        )

        # Subscribe in background with retry logic to handle startup timing issues
        # Ephemeral consumers occasionally timeout during concurrent startup operations
        # Retry with exponential backoff ensures eventual subscription success
        async def subscribe_in_background() -> None:
            max_retries = 5
            base_delay = 2

            for attempt in range(1, max_retries + 1):
                delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff: 2, 4, 8, 16, 32
                await asyncio.sleep(delay)

                try:
                    await event_subscriber.subscribe(EventType.REQUEST_AUTO_CREATED)
                    logger.info(
                        f"AINoteWriter subscribed to REQUEST_AUTO_CREATED events successfully (attempt {attempt})"
                    )
                    return  # Success!
                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(
                            f"Failed to subscribe to REQUEST_AUTO_CREATED events (attempt {attempt}/{max_retries}): {e}. "
                            f"Retrying in {base_delay * (2**attempt)}s..."
                        )
                    else:
                        logger.error(
                            f"Failed to subscribe to REQUEST_AUTO_CREATED events after {max_retries} attempts: {e}. "
                            "AI note writing will not work until subscription succeeds."
                        )

        self._subscription_task = asyncio.create_task(subscribe_in_background())
        logger.info("AINoteWriter service started (subscription in progress)")

    async def stop(self) -> None:
        """Stop listening for events and clean up resources."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping AINoteWriter service")

        if self._subscription_task and not self._subscription_task.done():
            self._subscription_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._subscription_task

        logger.info("AINoteWriter service stopped")

    async def _handle_request_auto_created(self, event: RequestAutoCreatedEvent) -> None:
        """
        Handle REQUEST_AUTO_CREATED event by dispatching to TaskIQ.

        Uses the hybrid NATS→TaskIQ pattern:
        - NATS provides cross-service event routing
        - TaskIQ provides retries, result storage, and tracing

        Args:
            event: Request auto-created event
        """
        logger.info(
            f"Dispatching AI note generation to TaskIQ: {event.request_id}",
            extra={
                "request_id": event.request_id,
                "scan_type": event.scan_type,
                "fact_check_item_id": event.fact_check_item_id,
                "community_server_id": event.community_server_id,
                "similarity_score": event.similarity_score,
            },
        )

        try:
            await generate_ai_note_task.kiq(
                community_server_id=event.community_server_id,
                request_id=event.request_id,
                content=event.content,
                scan_type=event.scan_type,
                fact_check_item_id=event.fact_check_item_id,
                similarity_score=event.similarity_score,
                db_url=settings.DATABASE_URL,
            )

            logger.debug(
                f"AI note generation dispatched to TaskIQ: {event.request_id}",
                extra={
                    "request_id": event.request_id,
                    "scan_type": event.scan_type,
                    "fact_check_item_id": event.fact_check_item_id,
                },
            )

        except Exception as e:
            instance_id = InstanceMetadata.get_instance_id()
            error_type = type(e).__name__
            ai_notes_failed_total.labels(
                community_server_id=event.community_server_id,
                error_type=error_type,
                instance_id=instance_id,
            ).inc()
            logger.exception(
                f"Failed to dispatch AI note generation to TaskIQ: {event.request_id}: {e}",
                extra={
                    "request_id": event.request_id,
                    "error_type": error_type,
                },
            )
            raise

    async def generate_note_for_request(self, db: AsyncSession, request_id: str) -> Note:
        """
        Generate an AI note for a specific request (public API for on-demand generation).

        Args:
            db: Database session
            request_id: Request ID

        Returns:
            Generated Note object

        Raises:
            ValueError: If request not found or missing required data
            Exception: If note generation or submission fails
        """
        instance_id = InstanceMetadata.get_instance_id()
        request: Request | None = None

        try:
            result = await db.execute(
                select(Request)
                .options(*note_loaders.request_with_archive())
                .where(Request.request_id == request_id)
            )
            request = result.scalar_one_or_none()

            if not request:
                raise ValueError(f"Request not found: {request_id}")

            # Validate required data (minimal - only content and server needed)
            if not request.community_server_id:
                raise ValueError(f"Request {request_id} is missing community_server_id")

            # Get content - for images, this returns the URL
            original_message = request.content
            if not original_message:
                raise ValueError(f"Request {request_id} is missing original message content")

            # Get image description if available
            image_description = await self._get_image_description(db, request, request_id)

            # Check if AI note writing is enabled
            community_server_id_str = str(request.community_server_id)
            if not await self._is_ai_note_writing_enabled(db, community_server_id_str):
                raise ValueError(
                    f"AI note writing is disabled for community server {community_server_id_str}"
                )

            # Check rate limits
            rate_limit_key = f"ai_note_writer:{community_server_id_str}"
            allowed, _ = await rate_limiter.check_rate_limit(community_server_id=rate_limit_key)
            if not allowed:
                raise ValueError(
                    f"Rate limit exceeded for AI note writing: {community_server_id_str}"
                )

            # Select strategy based on available data
            strategy = self._select_strategy(request)
            logger.info(
                f"Selected note generation strategy: {strategy.value}",
                extra={"request_id": request_id, "strategy": strategy.value},
            )

            # Generate note content using selected strategy
            start_time = time.time()

            if strategy == NoteGenerationStrategy.FACT_CHECK:
                # Type narrowing: strategy selection ensures these are not None
                if request.dataset_item_id is None or request.similarity_score is None:
                    raise ValueError(
                        "FACT_CHECK strategy requires dataset_item_id and similarity_score"
                    )

                # Retrieve fact-check item
                fact_check_item = await self._get_fact_check_item(db, request.dataset_item_id)
                if not fact_check_item:
                    raise ValueError(f"Fact-check item not found: {request.dataset_item_id}")

                note_content = await self._generate_fact_check_note(
                    db,
                    request.community_server_id,
                    original_message,
                    fact_check_item,
                    request.similarity_score,
                    image_description=image_description,
                )
            else:  # GENERAL_EXPLANATION strategy
                note_content = await self._generate_general_explanation_note(
                    db,
                    request.community_server_id,
                    original_message,
                    image_description=image_description,
                )

            duration = time.time() - start_time
            ai_note_generation_duration_seconds.labels(
                community_server_id=community_server_id_str, instance_id=instance_id
            ).observe(duration)

            # Create note (UUID v7 primary key generated by database)
            note = Note(
                request_id=request.request_id,
                author_participant_id="ai-note-writer",
                summary=note_content,
                classification="NOT_MISLEADING",
                status="NEEDS_MORE_RATINGS",
                community_server_id=request.community_server_id,
                ai_generated=True,
                ai_provider=settings.AI_NOTE_WRITER_MODEL.split("/")[0]
                if "/" in settings.AI_NOTE_WRITER_MODEL
                else "openai",
            )

            db.add(note)
            await db.commit()
            await db.refresh(note)

            ai_notes_generated_total.labels(
                community_server_id=community_server_id_str,
                dataset_name=request.dataset_name,
                instance_id=instance_id,
            ).inc()

            logger.info(
                f"Successfully generated AI note {note.id} for request {request_id}",
                extra={
                    "note_id": str(note.id),
                    "request_id": request_id,
                    "fact_check_item_id": request.dataset_item_id,
                },
            )

            return note

        except Exception as e:
            error_type = type(e).__name__
            # Only record metrics if we have a community_server_id
            if request and request.community_server_id:
                ai_notes_failed_total.labels(
                    community_server_id=str(request.community_server_id),
                    error_type=error_type,
                    instance_id=instance_id,
                ).inc()

            logger.exception(
                f"Failed to generate AI note for request {request_id}: {e}",
                extra={
                    "request_id": request_id,
                    "error_type": error_type,
                },
            )
            raise

    def _select_strategy(self, request: Request) -> NoteGenerationStrategy:
        """
        Select note generation strategy based on available request data.

        Args:
            request: Request object

        Returns:
            Selected strategy

        Strategy selection logic:
        - If request has fact-check metadata (dataset_item_id + similarity_score + dataset_name)
          → FACT_CHECK strategy
        - Otherwise → GENERAL_EXPLANATION strategy (default)
        """
        has_fact_check_data = all(
            [
                request.dataset_item_id is not None,
                request.similarity_score is not None,
                request.dataset_name is not None,
            ]
        )

        if has_fact_check_data:
            return NoteGenerationStrategy.FACT_CHECK
        return NoteGenerationStrategy.GENERAL_EXPLANATION

    async def _is_ai_note_writing_enabled(
        self, _db: AsyncSession, _community_server_id: str
    ) -> bool:
        """
        Check if AI note writing is enabled for a community server.

        Args:
            _db: Database session (reserved for future use)
            _community_server_id: Community server platform ID (reserved for future use)

        Returns:
            True if enabled, False otherwise
        """
        # For now, use a simple settings flag
        # In the future, this will check per-server configuration in the database
        return bool(settings.AI_NOTE_WRITING_ENABLED)

    @retry(
        retry=retry_if_exception_type((Exception,)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _generate_and_submit_note(
        self, db: AsyncSession, event: RequestAutoCreatedEvent
    ) -> None:
        """
        Generate AI note and submit it.

        Args:
            db: Database session
            event: Request auto-created event

        Raises:
            Exception: If note generation or submission fails
        """
        # Retrieve fact-check item
        fact_check_item = await self._get_fact_check_item(db, event.fact_check_item_id)

        if not fact_check_item:
            raise ValueError(f"Fact-check item not found: {event.fact_check_item_id}")

        # Get community server UUID
        community_server_uuid = await self._get_community_server_uuid(db, event.community_server_id)

        # Generate note content using LLM (fact-check strategy for auto-created events)
        note_content = await self._generate_fact_check_note(
            db,
            community_server_uuid,
            event.content,
            fact_check_item,
            event.similarity_score,
        )

        # Submit note
        await self._submit_note(
            db,
            event.request_id,
            note_content,
            community_server_uuid,
        )

        logger.info(
            f"Successfully generated and submitted AI note for request {event.request_id}",
            extra={
                "request_id": event.request_id,
                "fact_check_item_id": event.fact_check_item_id,
            },
        )

    async def _get_image_description(
        self, db: AsyncSession, request: Request, request_id: str
    ) -> str | None:
        """
        Get image description for a request, generating synchronously if needed.

        Args:
            db: Database session
            request: Request object with message_archive
            request_id: Request ID for logging

        Returns:
            Image description string, or None if not available or not an image
        """
        if not request.message_archive:
            return None

        if request.message_archive.image_description:
            logger.info(
                f"Using existing image description for request {request_id}",
                extra={
                    "request_id": request_id,
                    "has_image_description": True,
                    "description_length": len(request.message_archive.image_description),
                },
            )
            return request.message_archive.image_description

        is_image = request.message_archive.content_type == ContentType.IMAGE
        if not is_image or self.vision_service is None:
            return None

        logger.info(
            f"Image lacks description for request {request_id}, generating synchronously",
            extra={
                "request_id": request_id,
                "message_archive_id": str(request.message_archive.id),
                "image_url": request.message_archive.content_url,
            },
        )

        try:
            result_platform = await db.execute(
                select(CommunityServer.platform_id).where(
                    CommunityServer.id == request.community_server_id
                )
            )
            platform_id = result_platform.scalar_one_or_none()

            if not platform_id or not request.message_archive.content_url:
                return None

            description = await self.vision_service.describe_image(
                db=db,
                image_url=request.message_archive.content_url,
                community_server_id=platform_id,
                detail="auto",
                max_tokens=300,
            )

            request.message_archive.image_description = description
            await db.commit()
            await db.refresh(request.message_archive)

            logger.info(
                f"Successfully generated image description synchronously for request {request_id}",
                extra={
                    "request_id": request_id,
                    "description_length": len(description),
                },
            )
            return description
        except Exception as e:
            logger.warning(
                f"Failed to generate image description synchronously for request {request_id}: {e}",
                extra={
                    "request_id": request_id,
                    "error": str(e),
                },
            )
            return None

    async def _get_fact_check_item(
        self, db: AsyncSession, fact_check_item_id: str
    ) -> FactCheckItem | None:
        """
        Retrieve fact-check item from database.

        Args:
            db: Database session
            fact_check_item_id: Fact-check item ID (UUID string)

        Returns:
            FactCheckItem or None if not found
        """
        result = await db.execute(
            select(FactCheckItem).where(FactCheckItem.id == UUID(fact_check_item_id))
        )
        return result.scalar_one_or_none()

    async def _get_community_server_uuid(self, db: AsyncSession, community_server_id: str) -> UUID:
        """
        Get community server UUID from platform ID.

        Args:
            db: Database session
            community_server_id: Community server platform ID

        Returns:
            Community server UUID

        Raises:
            ValueError: If community server not found
        """
        result = await db.execute(
            select(CommunityServer.id).where(CommunityServer.platform_id == community_server_id)
        )
        community_server_uuid = result.scalar_one_or_none()

        if not community_server_uuid:
            raise ValueError(f"Community server not found: {community_server_id}")

        return community_server_uuid

    async def _generate_fact_check_note(
        self,
        db: AsyncSession,
        community_server_uuid: UUID,
        original_message: str,
        fact_check_item: FactCheckItem,
        similarity_score: float,
        image_description: str | None = None,
    ) -> str:
        """
        Generate fact-check note content using LLM (FACT_CHECK strategy).

        Args:
            db: Database session
            community_server_uuid: Community server UUID
            original_message: Original message content
            fact_check_item: Matched fact-check item
            similarity_score: Similarity score of the match
            image_description: AI-generated description of image (if message contains image)

        Returns:
            Generated note content

        Raises:
            Exception: If LLM call fails
        """
        # Construct prompt
        prompt = self._build_fact_check_prompt(
            original_message, fact_check_item, similarity_score, image_description
        )

        messages = [
            LLMMessage(role="system", content=settings.AI_NOTE_WRITER_SYSTEM_PROMPT),
            LLMMessage(role="user", content=prompt),
        ]

        # Generate completion using LLMService
        response = await self.llm_service.complete(
            db=db,
            messages=messages,
            community_server_id=community_server_uuid,
            provider="openai",
            model=settings.AI_NOTE_WRITER_MODEL,
            max_tokens=500,
            temperature=0.7,
        )

        logger.info(
            "Generated AI note content",
            extra={
                "content_length": len(response.content),
                "model": response.model,
                "tokens_used": response.tokens_used,
            },
        )

        return response.content

    async def _generate_general_explanation_note(
        self,
        db: AsyncSession,
        community_server_uuid: UUID,
        original_message: str,
        image_description: str | None = None,
    ) -> str:
        """
        Generate general explanation note content using LLM (GENERAL_EXPLANATION strategy).

        This strategy is used when no fact-check data is available. The AI provides
        general context and explanation for the message content.

        Args:
            db: Database session
            community_server_uuid: Community server UUID
            original_message: Original message content
            image_description: AI-generated description of image (if message contains image)

        Returns:
            Generated note content

        Raises:
            Exception: If LLM call fails
        """
        # Construct prompt
        prompt = self._build_general_explanation_prompt(original_message, image_description)

        messages = [
            LLMMessage(role="system", content=settings.AI_NOTE_WRITER_SYSTEM_PROMPT),
            LLMMessage(role="user", content=prompt),
        ]

        # Generate completion using LLMService
        response = await self.llm_service.complete(
            db=db,
            messages=messages,
            community_server_id=community_server_uuid,
            provider="openai",
            model=settings.AI_NOTE_WRITER_MODEL,
            max_tokens=500,
            temperature=0.7,
        )

        logger.info(
            "Generated AI note content (general explanation)",
            extra={
                "content_length": len(response.content),
                "model": response.model,
                "tokens_used": response.tokens_used,
            },
        )

        return response.content

    def _build_fact_check_prompt(
        self,
        original_message: str,
        fact_check_item: FactCheckItem,
        similarity_score: float,
        image_description: str | None = None,
    ) -> str:
        """
        Build prompt for fact-check note generation (FACT_CHECK strategy).

        Args:
            original_message: Original message content
            fact_check_item: Matched fact-check item
            similarity_score: Similarity score
            image_description: AI-generated description of image (if available)

        Returns:
            Formatted prompt
        """
        # Build message context section
        message_context = f"Original Message:\n{original_message}"
        if image_description:
            message_context += f"\n\nImage Content:\n{image_description}"

        return f"""{message_context}

Fact-Check Information:
Title: {fact_check_item.title}
Rating: {fact_check_item.rating}
Summary: {fact_check_item.summary}
Content: {fact_check_item.content}
Source: {fact_check_item.source_url}

Match Confidence: {similarity_score:.2%}

Please write a concise, informative community note that:
1. Addresses the claim in the original message or image
2. Provides context from the fact-check information
3. Maintains a neutral, factual tone
4. Is clear and easy to understand
5. Is no more than 280 characters if possible

Community Note:"""

    def _build_general_explanation_prompt(
        self, original_message: str, image_description: str | None = None
    ) -> str:
        """
        Build prompt for general explanation note generation (GENERAL_EXPLANATION strategy).

        Args:
            original_message: Original message content
            image_description: AI-generated description of image (if available)

        Returns:
            Formatted prompt
        """
        # Build message context section
        message_context = f"Original Message:\n{original_message}"
        if image_description:
            message_context += f"\n\nImage Content:\n{image_description}"

        return f"""{message_context}

Please analyze this content and write a concise, informative community note that:
1. Explains the message{"and image" if image_description else ""} content
2. Provides helpful context and clarification
3. Addresses any potential misunderstandings
4. Maintains a neutral, factual tone
5. Is clear and easy to understand
6. Is no more than 280 characters if possible

Focus on helping readers understand what the content is about, what context might be important, and any relevant information that would be helpful to know.

Community Note:"""

    async def _submit_note(
        self,
        db: AsyncSession,
        request_id: str,
        note_content: str,
        community_server_uuid: UUID,
    ) -> None:
        """
        Submit generated note to database.

        Args:
            db: Database session
            request_id: Request ID
            note_content: Generated note content
            community_server_uuid: Community server UUID

        Raises:
            Exception: If note submission fails
        """
        # Create note (UUID v7 primary key generated by database)
        note = Note(
            request_id=request_id,
            author_participant_id="ai-note-writer",
            summary=note_content,
            classification="NOT_MISLEADING",
            status="NEEDS_MORE_RATINGS",
            community_server_id=community_server_uuid,
            ai_generated=True,
            ai_provider="openai",
        )

        db.add(note)
        await db.commit()
        await db.refresh(note)

        logger.info(
            f"Submitted AI-generated note {note.id}",
            extra={
                "note_id": str(note.id),
                "request_id": request_id,
            },
        )

    async def generate_scan_explanation(
        self,
        original_message: str,
        fact_check_data: dict[str, str | float | None],
        db: AsyncSession,
        community_server_id: UUID,
    ) -> str:
        """
        Generate a one-sentence explanation for why a message was flagged.

        This method is used by the vibecheck scan results display to provide
        users with a quick explanation of why a message matched a fact-check.

        Args:
            original_message: The original Discord message content
            fact_check_data: Dictionary containing fact-check info:
                - id: UUID of the FactCheckItem
                - title: Title of the fact-check
                - content: Content/claim text
                - rating: Fact-check rating (e.g., "false", "mostly-false")
                - source_url: URL to the fact-check source
                - similarity_score: Match confidence score (0-1)
            db: Database session for LLMService calls
            community_server_id: Community server UUID for LLMService

        Returns:
            One-sentence explanation of why the message was flagged
        """
        prompt = f"""Original message: "{original_message}"

Fact-check information:
{self._format_fact_check_json(fact_check_data)}

Write a one sentence explanation (max 100 words) of why this message was flagged.
Be concise and factual. Start directly with the explanation, no preamble."""

        messages = [
            LLMMessage(role="user", content=prompt),
        ]

        response = await self.llm_service.complete(
            db=db,
            messages=messages,
            community_server_id=community_server_id,
            provider="openai",
            model=settings.AI_NOTE_WRITER_MODEL,
            max_tokens=150,
            temperature=0.3,
        )

        return response.content.strip()

    def _format_fact_check_json(self, fact_check_data: dict[str, str | float | None]) -> str:
        """Format fact-check data as readable key-value pairs."""
        lines = []
        for key, value in fact_check_data.items():
            if value is not None:
                if isinstance(value, float):
                    lines.append(f"- {key}: {value:.2f}")
                else:
                    lines.append(f"- {key}: {value}")
        return "\n".join(lines)
