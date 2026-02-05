"""Service for detecting conversation flashpoints using DSPy-optimized prompts."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import dspy

from src.bulk_content_scan.schemas import ConversationFlashpointMatch
from src.monitoring import get_logger

if TYPE_CHECKING:
    from src.bulk_content_scan.schemas import BulkScanMessage

logger = get_logger(__name__)


class FlashpointSignature(dspy.Signature):
    """Predict whether a conversation is about to derail into conflict."""

    context: str = dspy.InputField(desc="Previous messages in the conversation")
    message: str = dspy.InputField(desc="The current message to analyze")
    will_derail: bool = dspy.OutputField(desc="True if the conversation shows signs of derailing")
    reasoning: str = dspy.OutputField(desc="Brief explanation of the key signals detected")


class FlashpointDetector(dspy.Module):
    """DSPy module for detecting conversation flashpoints."""

    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.ChainOfThought(FlashpointSignature)

    def forward(self, context: str, message: str) -> dspy.Prediction:
        return self.predict(context=context, message=message)


class FlashpointDetectionService:
    """Service for detecting conversation flashpoints.

    Uses a DSPy-optimized prompt to identify early warning signs
    that a conversation may derail into conflict.
    """

    DEFAULT_MODEL = "openai/gpt-4o-mini"
    DEFAULT_MAX_CONTEXT = 5

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
        self._detector: FlashpointDetector | None = None
        self._optimized_path = optimized_model_path

    def _get_default_optimized_path(self) -> Path:
        """Get the default path for the optimized detector."""
        return (
            Path(__file__).parent.parent.parent / "data" / "flashpoints" / "optimized_detector.json"
        )

    def _get_detector(self) -> FlashpointDetector:
        """Lazily initialize the detector."""
        if self._detector is None:
            lm = dspy.LM(self.model)
            dspy.configure(lm=lm)

            self._detector = FlashpointDetector()

            optimized_path = self._optimized_path or self._get_default_optimized_path()
            if optimized_path.exists():
                logger.info("Loading optimized flashpoint detector", path=str(optimized_path))
                self._detector.load(str(optimized_path))
            else:
                logger.info(
                    "Using base flashpoint detector (optimized model not found)",
                    expected_path=str(optimized_path),
                )

        return self._detector

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
        """
        if max_context is None:
            max_context = self.DEFAULT_MAX_CONTEXT

        try:
            recent_context = context_messages[-max_context:] if context_messages else []
            context_str = "\n".join(
                f"{m.author_username or m.author_id}: {m.content}" for m in recent_context
            )

            current_msg = f"{message.author_username or message.author_id}: {message.content}"

            detector = self._get_detector()
            result = detector(context=context_str, message=current_msg)

            will_derail = result.will_derail
            if isinstance(will_derail, str):
                will_derail = will_derail.lower() in ("true", "yes", "1")

            if not will_derail:
                return None

            return ConversationFlashpointMatch(
                will_derail=will_derail,
                confidence=0.8,
                reasoning=result.reasoning,
                context_messages=len(recent_context),
            )

        except Exception as e:
            logger.error(
                "Flashpoint detection failed",
                error=str(e),
                message_id=message.message_id,
            )
            return None
