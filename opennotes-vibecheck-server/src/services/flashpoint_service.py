"""Service for detecting conversation flashpoints using DSPy-optimized prompts.

Port of ``opennotes-server/src/bulk_content_scan/flashpoint_service.py`` with
two substantive changes:

1.  LM backend switches from OpenAI to Vertex AI Gemini via DSPy + litellm
    (``dspy.LM("vertex_ai/...")``). Everything else in vibecheck uses
    pydantic-ai; DSPy stays on its own LM abstraction.

2.  API operates on vibecheck ``Utterance`` objects instead of Discord
    ``BulkScanMessage`` objects. The detector's text input shape is the
    same — ``"<author>: <text>"`` per line.

The DSPy module artifact format is unchanged; only the LM backend differs.
"""

from __future__ import annotations

import asyncio
import json
import math
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.config import Settings, get_settings
from src.monitoring import get_logger
from src.services.gemini_agent import google_vertex_model_name
from src.services.vertex_limiter import vertex_slot
from src.utterances.schema import Utterance

if TYPE_CHECKING:
    import dspy

    from src.analyses.tone._flashpoint_schemas import FlashpointMatch

logger = get_logger(__name__)

_TRANSIENT_ERRORS = (TimeoutError, ConnectionError, OSError)


DERAILMENT_SCORE_MIN = 0
DERAILMENT_SCORE_MAX = 100

DETECTOR_TYPE_KEY = "detector_type"
DETECTOR_TYPE_RUBRIC = "rubric"


RISK_LEVEL_MAPPING: dict[str, int] = {
    "Low Risk": 10,
    "Guarded": 30,
    "Heated": 60,
    "Hostile": 85,
    "Dangerous": 100,
}

RISK_LEVEL_DEFAULT = 50

_RISK_LEVEL_LOOKUP: dict[str, str] = {v.lower(): v for v in RISK_LEVEL_MAPPING}

_SCORE_THRESHOLDS: list[tuple[int, str]] = [
    (100, "Dangerous"),
    (85, "Hostile"),
    (60, "Heated"),
    (30, "Guarded"),
]


def parse_derailment_score(value: Any) -> int:  # noqa: PLR0911
    """Parse a derailment score from LLM output, clamping to [0, 100]."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(DERAILMENT_SCORE_MIN, min(DERAILMENT_SCORE_MAX, value))
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return DERAILMENT_SCORE_MAX if value == float("inf") else DERAILMENT_SCORE_MIN
        return max(DERAILMENT_SCORE_MIN, min(DERAILMENT_SCORE_MAX, round(value)))
    if isinstance(value, str):
        try:
            numeric = int(float(value.strip()))
        except (ValueError, OverflowError):
            logger.warning("parse_derailment_score: unrecognized string %r", value)
            return 0
        return max(DERAILMENT_SCORE_MIN, min(DERAILMENT_SCORE_MAX, numeric))
    try:
        return max(DERAILMENT_SCORE_MIN, min(DERAILMENT_SCORE_MAX, int(value)))
    except (TypeError, ValueError):
        logger.warning("parse_derailment_score: unrecognized type %s", type(value).__name__)
        return 0


def parse_risk_level(value: str, derailment_score: int | None = None) -> str:
    """Normalize LLM risk_level output to a valid RiskLevel value.

    Case-insensitive lookup against known values. Falls back to deriving
    from ``derailment_score`` if provided, otherwise defaults to "Heated".
    """
    normalized = value.lower().strip()
    if normalized in _RISK_LEVEL_LOOKUP:
        return _RISK_LEVEL_LOOKUP[normalized]

    if derailment_score is not None:
        for threshold, level in _SCORE_THRESHOLDS:
            if derailment_score >= threshold:
                return level
        return "Low Risk"

    return "Heated"


def _import_dspy():
    import dspy as _dspy  # noqa: PLC0415  # lazy import: dspy is ~100MB

    return _dspy


class CategoricalRiskSignature:
    """Lazy wrapper for categorical risk assessment signature."""

    _cls: type | None = None

    @classmethod
    def get(cls) -> type:
        if cls._cls is None:
            dspy = _import_dspy()

            class _CategoricalRiskSignature(dspy.Signature):
                """Assess the risk level of this conversation potentially derailing into conflict."""

                context: str = dspy.InputField(desc="Previous messages in the conversation")
                message: str = dspy.InputField(desc="The current message to analyze")
                risk_level: str = dspy.OutputField(
                    desc="Select one: 'Low Risk', 'Guarded', 'Heated', 'Hostile', 'Dangerous'"
                )
                reasoning: str = dspy.OutputField(desc="Why this risk level fits")

            cls._cls = _CategoricalRiskSignature
        return cls._cls


class RubricDetector:
    """Rubric-based flashpoint detector using categorical classification.

    Port of opennotes-server's ``RubricDetector``. Forces the LLM to choose
    a risk category; the category maps deterministically to a numeric score.
    """

    detector_type: str = DETECTOR_TYPE_RUBRIC

    def __init__(self) -> None:
        dspy = _import_dspy()
        sig = CategoricalRiskSignature.get()

        class _Inner(dspy.Module):
            def __init__(self_inner) -> None:  # noqa: N805  # pyright: ignore[reportSelfClsParameterName]
                super().__init__()
                self_inner.assess = dspy.ChainOfThought(sig)

            def forward(self_inner, context: str, message: str):  # noqa: N805  # pyright: ignore[reportSelfClsParameterName]
                pred = self_inner.assess(context=context, message=message)
                score = RISK_LEVEL_MAPPING.get(pred.risk_level, RISK_LEVEL_DEFAULT)
                return dspy.Prediction(
                    derailment_score=score,
                    reasoning=pred.reasoning,
                    risk_level=pred.risk_level,
                )

        self._inner = _Inner()
        self.assess = self._inner.assess

    def forward(self, context: str, message: str):
        return self._inner.forward(context=context, message=message)

    def load(self, path: str) -> None:
        data = json.loads(Path(path).read_text())
        self.detector_type = data.get(DETECTOR_TYPE_KEY, DETECTOR_TYPE_RUBRIC)
        self._inner.load(path)
        self.assess = self._inner.assess

    def save(self, path: str) -> None:
        self._inner.save(path)

    def __call__(self, context: str, message: str):
        return self.forward(context=context, message=message)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class FlashpointDetectionService:
    """Detect conversation flashpoints in vibecheck utterances via DSPy.

    Binds DSPy to Vertex AI Gemini using the ``vertex_ai/`` litellm prefix
    and Application Default Credentials. Loads the optimized DSPy module
    from ``models/flashpoint_module.json`` if present; otherwise falls back
    to the un-optimized base detector.

    Returns a continuous ``derailment_score`` (0-100) plus a categorical
    ``risk_level``. Callers apply their own threshold.
    """

    DEFAULT_MAX_CONTEXT = 5
    DEFAULT_SCORE_THRESHOLD = 50

    def __init__(
        self,
        settings: Settings | None = None,
        optimized_model_path: Path | None = None,
    ) -> None:
        self._settings: Settings = settings if settings is not None else get_settings()
        self._lm: dspy.LM | None = None
        self._detector: RubricDetector | None = None
        self._optimized_path = optimized_model_path
        self._init_lock = threading.Lock()

    def warm_up(self) -> None:
        """Eagerly initialize the detector so DSPy import + module loading
        happens at startup rather than silently hanging during a request."""
        self._get_detector()

    def _get_default_optimized_path(self) -> Path:
        """Default path for the optimized detector.

        Resolves to ``<vibecheck-server-root>/models/flashpoint_module.json``.
        """
        return Path(__file__).parent.parent.parent / "models" / "flashpoint_module.json"

    def _build_lm(self) -> dspy.LM:
        dspy = _import_dspy()
        model_name = google_vertex_model_name(
            self._settings.VERTEXAI_FAST_MODEL,
            setting_name="VERTEXAI_FAST_MODEL",
        )
        return dspy.LM(
            f"vertex_ai/{model_name}",
            vertex_project=self._settings.VERTEXAI_PROJECT,
            vertex_location=self._settings.VERTEXAI_LOCATION,
            temperature=0.0,
        )

    def _get_detector(self) -> RubricDetector:
        """Lazily initialize the detector (thread-safe)."""
        if self._detector is not None:
            return self._detector

        with self._init_lock:
            if self._detector is not None:
                return self._detector

            dspy = _import_dspy()
            self._lm = self._build_lm()
            dspy.configure(lm=self._lm)

            self._detector = RubricDetector()

            optimized_path = self._optimized_path or self._get_default_optimized_path()
            if optimized_path.exists():
                logger.info("Loading optimized flashpoint detector from %s", optimized_path)
                self._detector.load(str(optimized_path))
            else:
                logger.info(
                    "Using base flashpoint detector (optimized model not found at %s)",
                    optimized_path,
                )

        return self._detector

    def _run_detector(
        self,
        detector: RubricDetector,
        context_str: str,
        current_msg: str,
    ) -> Any:
        """Run the detector synchronously (intended for ``asyncio.to_thread``)."""
        dspy = _import_dspy()
        with dspy.context(lm=self._lm):
            return detector(context=context_str, message=current_msg)

    @staticmethod
    def _format_line(utt: Utterance) -> str:
        return f"{utt.author or utt.utterance_id or 'unknown'}: {utt.text}"

    async def detect_flashpoint(
        self,
        utterance: Utterance,
        context: list[Utterance],
        max_context: int | None = None,
        score_threshold: int | None = None,
    ) -> FlashpointMatch | None:
        """Score an utterance for conversation-derailment risk.

        Args:
            utterance: The utterance to analyze.
            context: Previous utterances in the same thread (time-ordered).
            max_context: Maximum number of context utterances to include
                (defaults to ``DEFAULT_MAX_CONTEXT``).
            score_threshold: Minimum ``derailment_score`` to flag
                (defaults to ``DEFAULT_SCORE_THRESHOLD``).

        Returns:
            ``FlashpointMatch`` if the score meets the threshold, otherwise
            ``None``. Returns ``None`` on transient network/IO errors;
            re-raises critical errors after logging.
        """
        from src.analyses.tone._flashpoint_schemas import (  # noqa: PLC0415
            FlashpointMatch,
            RiskLevel,
        )

        if max_context is None:
            max_context = self.DEFAULT_MAX_CONTEXT
        if score_threshold is None:
            score_threshold = self.DEFAULT_SCORE_THRESHOLD

        try:
            recent_context = context[-max_context:] if context else []
            context_str = "\n".join(self._format_line(c) for c in recent_context)
            current_msg = self._format_line(utterance)

            detector = self._get_detector()
            async with vertex_slot(self._settings):
                result = await asyncio.to_thread(
                    self._run_detector, detector, context_str, current_msg
                )

            derailment_score = parse_derailment_score(result.derailment_score)

            if derailment_score < score_threshold:
                return None

            risk_level_str = parse_risk_level(getattr(result, "risk_level", ""), derailment_score)
            return FlashpointMatch(
                utterance_id=utterance.utterance_id or "",
                derailment_score=derailment_score,
                risk_level=RiskLevel(risk_level_str),
                reasoning=getattr(result, "reasoning", ""),
                context_messages=len(recent_context),
            )

        except _TRANSIENT_ERRORS as e:
            logger.warning(
                "Flashpoint detection failed (transient): %s: %s",
                type(e).__name__,
                e,
            )
            return None

        except Exception as e:
            logger.error(
                "Flashpoint detection failed (critical): %s: %s",
                type(e).__name__,
                e,
            )
            raise


_flashpoint_service: FlashpointDetectionService | None = None
_singleton_lock = threading.Lock()


def get_flashpoint_service(
    settings: Settings | None = None,
    optimized_model_path: Path | None = None,
) -> FlashpointDetectionService:
    """Return a cached singleton ``FlashpointDetectionService``."""
    global _flashpoint_service  # noqa: PLW0603

    if _flashpoint_service is not None:
        return _flashpoint_service

    with _singleton_lock:
        if _flashpoint_service is not None:
            return _flashpoint_service
        _flashpoint_service = FlashpointDetectionService(
            settings=settings, optimized_model_path=optimized_model_path
        )

    return _flashpoint_service


def reset_flashpoint_service() -> None:
    """Reset the singleton (intended for tests)."""
    global _flashpoint_service  # noqa: PLW0603
    _flashpoint_service = None
