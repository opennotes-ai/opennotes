"""Service for detecting conversation flashpoints using DSPy-optimized prompts."""

from __future__ import annotations

import asyncio
import os
import threading
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.monitoring import get_logger

if TYPE_CHECKING:
    import dspy

    from src.bulk_content_scan.flashpoint_utils import RubricDetector
    from src.bulk_content_scan.schemas import BulkScanMessage, ConversationFlashpointMatch

logger = get_logger(__name__)

_TRANSIENT_ERRORS = (TimeoutError, ConnectionError, OSError)

_API_KEY_ENV_VARS = {
    "openai/": "OPENAI_API_KEY",
    "anthropic/": "ANTHROPIC_API_KEY",
}


class FlashpointDetectionService:
    """Service for detecting conversation flashpoints.

    Uses a DSPy-optimized prompt to identify early warning signs
    that a conversation may derail into conflict.

    Returns a continuous ``derailment_score`` (0-100) rather than a
    binary flag, enabling downstream consumers to apply their own
    thresholds and produce ROC-style safety-at-audit-budget curves.
    """

    DEFAULT_MODEL = "openai/gpt-5-mini"
    DEFAULT_MAX_CONTEXT = 5
    DEFAULT_SCORE_THRESHOLD = 50

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
        self._detector: RubricDetector | None = None
        self._optimized_path = optimized_model_path
        self._init_lock = threading.Lock()

    def warm_up(self) -> None:
        """Eagerly initialize the detector so DSPy import + model loading
        happens at startup rather than silently hanging during a scan."""
        self._get_detector()

    def _get_default_optimized_path(self) -> Path:
        """Get the default path for the optimized detector."""
        return (
            Path(__file__).parent.parent.parent / "data" / "flashpoints" / "optimized_detector.json"
        )

    def _validate_api_key(self) -> None:
        """Validate that the required API key environment variable is set."""
        for prefix, env_var in _API_KEY_ENV_VARS.items():
            if self.model.startswith(prefix):
                if not os.environ.get(env_var):
                    raise RuntimeError(
                        f"Environment variable {env_var} is required for model {self.model}"
                    )
                return

    def _get_detector(self) -> RubricDetector:
        """Lazily initialize the detector (thread-safe)."""
        if self._detector is not None:
            return self._detector

        with self._init_lock:
            if self._detector is not None:
                return self._detector

            self._validate_api_key()

            import dspy as _dspy

            from src.bulk_content_scan.flashpoint_utils import (
                RubricDetector as _RubricDetector,
            )

            self._lm = _dspy.LM(self.model)

            self._detector = _RubricDetector()

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
        self,
        detector: RubricDetector,
        context_str: str,
        current_msg: str,
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
        score_threshold: int | None = None,
    ) -> ConversationFlashpointMatch | None:
        """Detect if a message shows conversation flashpoint signals.

        Args:
            message: The message to analyze
            context_messages: Previous messages in the conversation (time-ordered)
            max_context: Maximum number of context messages to include
                (defaults to DEFAULT_MAX_CONTEXT)
            score_threshold: Minimum derailment_score to flag (defaults to
                DEFAULT_SCORE_THRESHOLD). Messages scoring below this are
                not returned.

        Returns:
            ConversationFlashpointMatch if derailment_score >= threshold, None otherwise

        Raises:
            Exception: Re-raises critical (non-transient) errors after logging.
                Transient errors: TimeoutError, ConnectionError, OSError.
                Critical errors (propagated): ValueError, TypeError, KeyError,
                AttributeError, RuntimeError, and all other Exception subclasses.
        """
        from src.bulk_content_scan.flashpoint_utils import parse_derailment_score
        from src.bulk_content_scan.schemas import ConversationFlashpointMatch

        if max_context is None:
            max_context = self.DEFAULT_MAX_CONTEXT
        if score_threshold is None:
            score_threshold = self.DEFAULT_SCORE_THRESHOLD

        try:
            recent_context = context_messages[-max_context:] if context_messages else []
            context_str = "\n".join(
                f"{m.author_username or m.author_id}: {m.content}" for m in recent_context
            )

            current_msg = f"{message.author_username or message.author_id}: {message.content}"

            detector = self._get_detector()
            result = await asyncio.to_thread(self._run_detector, detector, context_str, current_msg)

            derailment_score = parse_derailment_score(result.derailment_score)

            if derailment_score < score_threshold:
                return None

            return ConversationFlashpointMatch(
                derailment_score=derailment_score,
                risk_level=result.risk_level,
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
        requested_model = model or FlashpointDetectionService.DEFAULT_MODEL
        if model is not None and requested_model != _flashpoint_service.model:
            warnings.warn(
                f"get_flashpoint_service() singleton already created with "
                f"model={_flashpoint_service.model!r}; ignoring requested "
                f"model={requested_model!r}",
                UserWarning,
                stacklevel=2,
            )
        if (
            optimized_model_path is not None
            and optimized_model_path != _flashpoint_service._optimized_path
        ):
            warnings.warn(
                f"get_flashpoint_service() singleton already created with "
                f"optimized_model_path="
                f"{_flashpoint_service._optimized_path!r}; "
                f"ignoring requested "
                f"optimized_model_path={optimized_model_path!r}",
                UserWarning,
                stacklevel=2,
            )
        return _flashpoint_service

    with _singleton_lock:
        if _flashpoint_service is not None:
            return _flashpoint_service
        _flashpoint_service = FlashpointDetectionService(
            model=model,
            optimized_model_path=optimized_model_path,
        )

    return _flashpoint_service
