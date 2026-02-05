"""Service for detecting conversation flashpoints using DSPy-optimized prompts."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.monitoring import get_logger

if TYPE_CHECKING:
    import dspy

    from src.bulk_content_scan.flashpoint_utils import FlashpointDetector
    from src.bulk_content_scan.schemas import BulkScanMessage, ConversationFlashpointMatch

logger = get_logger(__name__)

_TRANSIENT_ERRORS = (ValueError, TimeoutError, ConnectionError, OSError)


class FlashpointDetectionService:
    """Service for detecting conversation flashpoints.

    Uses a DSPy-optimized prompt to identify early warning signs
    that a conversation may derail into conflict.
    """

    DEFAULT_MODEL = "openai/gpt-4o-mini"
    DEFAULT_MAX_CONTEXT = 5
    CONFIDENCE_DERAIL = 0.9
    CONFIDENCE_NO_DERAIL = 0.2

    def __init__(
        self,
        model: str | None = None,
        optimized_model_path: Path | None = None,
    ) -> None:
        """Initialize the flashpoint detection service.

        Args:
            model: The LLM model to use (defaults to DEFAULT_MODEL)
            optimized_model_path: Path to optimized DSPy program (optional).
                Defaults to data/flashpoints/optimized_detector.json relative
                to the opennotes-server root.
        """
        self.model = model or self.DEFAULT_MODEL
        self._lm: dspy.LM | None = None
        self._detector: FlashpointDetector | None = None
        self._optimized_path = optimized_model_path
        self._init_lock = threading.Lock()

    def _get_default_optimized_path(self) -> Path:
        """Get the default path for the optimized detector."""
        return (
            Path(__file__).parent.parent.parent / "data" / "flashpoints" / "optimized_detector.json"
        )

    def _get_detector(self) -> FlashpointDetector:
        """Lazily initialize the detector (thread-safe)."""
        if self._detector is not None:
            return self._detector

        with self._init_lock:
            if self._detector is not None:
                return self._detector

            import dspy as _dspy

            from src.bulk_content_scan.flashpoint_utils import (
                FlashpointDetector as _FlashpointDetector,
            )

            self._lm = _dspy.LM(self.model)

            self._detector = _FlashpointDetector()

            optimized_path = self._optimized_path or self._get_default_optimized_path()
            if optimized_path.exists():
                logger.info(
                    "Loading optimized flashpoint detector",
                    extra={"path": str(optimized_path)},
                )
                self._detector.load(str(optimized_path))
            else:
                logger.info(
                    "Using base flashpoint detector (optimized model not found)",
                    extra={"expected_path": str(optimized_path)},
                )

        return self._detector

    def _run_detector(
        self, detector: FlashpointDetector, context_str: str, current_msg: str
    ) -> Any:
        """Run the detector synchronously (intended for use with asyncio.to_thread)."""
        import dspy as _dspy

        with _dspy.context(lm=self._lm):
            return detector(context=context_str, message=current_msg)

    async def detect_flashpoint(
        self,
        message: BulkScanMessage,
        context_messages: list[BulkScanMessage],
        max_context: int | None = None,
    ) -> ConversationFlashpointMatch | None:
        """Detect if a message shows conversation flashpoint signals.

        Args:
            message: The message to analyze
            context_messages: Previous messages in the conversation (time-ordered)
            max_context: Maximum number of context messages to include
                (defaults to DEFAULT_MAX_CONTEXT)

        Returns:
            ConversationFlashpointMatch if flashpoint detected, None otherwise

        Raises:
            Exception: Re-raises critical (non-transient) errors after logging.
        """
        from src.bulk_content_scan.flashpoint_utils import parse_bool
        from src.bulk_content_scan.schemas import ConversationFlashpointMatch

        if max_context is None:
            max_context = self.DEFAULT_MAX_CONTEXT

        try:
            recent_context = context_messages[-max_context:] if context_messages else []
            context_str = "\n".join(
                f"{m.author_username or m.author_id}: {m.content}" for m in recent_context
            )

            current_msg = f"{message.author_username or message.author_id}: {message.content}"

            detector = self._get_detector()
            result = await asyncio.to_thread(self._run_detector, detector, context_str, current_msg)

            will_derail = parse_bool(result.will_derail)

            if not will_derail:
                return None

            confidence = self.CONFIDENCE_DERAIL if will_derail else self.CONFIDENCE_NO_DERAIL

            return ConversationFlashpointMatch(
                will_derail=will_derail,
                confidence=confidence,
                reasoning=result.reasoning,
                context_messages=len(recent_context),
            )

        except _TRANSIENT_ERRORS as e:
            logger.warning(
                "Flashpoint detection failed (transient)",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "message_id": message.message_id,
                },
            )
            return None

        except Exception as e:
            logger.error(
                "Flashpoint detection failed (critical)",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "message_id": message.message_id,
                },
            )
            raise


_flashpoint_service: FlashpointDetectionService | None = None
_singleton_lock = threading.Lock()


def get_flashpoint_service(
    model: str | None = None,
    optimized_model_path: Path | None = None,
) -> FlashpointDetectionService:
    """Return a cached singleton FlashpointDetectionService."""
    global _flashpoint_service

    if _flashpoint_service is not None:
        return _flashpoint_service

    with _singleton_lock:
        if _flashpoint_service is not None:
            return _flashpoint_service
        _flashpoint_service = FlashpointDetectionService(
            model=model,
            optimized_model_path=optimized_model_path,
        )

    return _flashpoint_service
