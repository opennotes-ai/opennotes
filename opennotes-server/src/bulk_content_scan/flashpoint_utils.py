"""Shared utilities for flashpoint detection (runtime + training scripts)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import dspy

logger = logging.getLogger(__name__)

DERAILMENT_SCORE_MIN = 0
DERAILMENT_SCORE_MAX = 100


def parse_bool(value: Any) -> bool:
    """Parse a value to boolean, handling string representations from LLM output."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.lower()
        if lower in ("true", "yes", "1", "y"):
            return True
        if lower in ("false", "no", "0", "n", ""):
            return False
        logger.warning("parse_bool: unrecognized string %r, defaulting to False", value)
        return False
    return bool(value)


def parse_derailment_score(value: Any) -> int:
    """Parse a derailment score from LLM output, clamping to [0, 100]."""
    if isinstance(value, int):
        return max(DERAILMENT_SCORE_MIN, min(DERAILMENT_SCORE_MAX, value))
    if isinstance(value, float):
        return max(DERAILMENT_SCORE_MIN, min(DERAILMENT_SCORE_MAX, round(value)))
    if isinstance(value, str):
        value = value.strip()
        try:
            numeric = int(float(value))
            return max(DERAILMENT_SCORE_MIN, min(DERAILMENT_SCORE_MAX, numeric))
        except (ValueError, OverflowError):
            logger.warning("parse_derailment_score: unrecognized string %r, defaulting to 0", value)
            return 0
    try:
        return max(DERAILMENT_SCORE_MIN, min(DERAILMENT_SCORE_MAX, int(value)))
    except (TypeError, ValueError):
        logger.warning(
            "parse_derailment_score: unrecognized type %s, defaulting to 0", type(value).__name__
        )
        return 0


def _import_dspy():
    import dspy as _dspy

    return _dspy


class FlashpointSignature:
    """Lazy wrapper -- actual dspy.Signature created on first access."""

    _cls: type | None = None

    @classmethod
    def get(cls) -> type:
        if cls._cls is None:
            dspy = _import_dspy()

            class _FlashpointSignature(dspy.Signature):
                """Rate how likely a conversation is to derail into conflict on a scale of 0-100."""

                context: str = dspy.InputField(desc="Previous messages in the conversation")
                message: str = dspy.InputField(desc="The current message to analyze")
                derailment_score: int = dspy.OutputField(
                    desc="Score 0-100. 0=Civil, 50=Heated disagreement, 100=Active hostility/Safety risk",
                )
                reasoning: str = dspy.OutputField(
                    desc="Justification for the score based on escalation signals detected"
                )

            cls._cls = _FlashpointSignature
        return cls._cls


class FlashpointDetector:
    """DSPy module for detecting conversation flashpoints.

    Lazily imports dspy so that importing this module does not pull in
    heavy ML dependencies at startup.  The underlying ``dspy.Module``
    is created in ``__init__`` and all public DSPy APIs (``forward``,
    ``load``, ``save``, ``__call__``) are delegated to it.
    """

    def __init__(self) -> None:
        dspy = _import_dspy()
        sig = FlashpointSignature.get()

        class _Inner(dspy.Module):
            def __init__(self_inner) -> None:  # noqa: N805
                super().__init__()
                self_inner.predict = dspy.ChainOfThought(sig)

            def forward(self_inner, context: str, message: str) -> dspy.Prediction:  # noqa: N805
                return self_inner.predict(context=context, message=message)

        self._inner = _Inner()
        self.predict = self._inner.predict

    def forward(self, context: str, message: str) -> dspy.Prediction:
        return self._inner.forward(context=context, message=message)

    def load(self, path: str) -> None:
        self._inner.load(path)
        self.predict = self._inner.predict

    def save(self, path: str) -> None:
        self._inner.save(path)

    def __call__(self, context: str, message: str) -> dspy.Prediction:
        return self.forward(context=context, message=message)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class EscalationSummarySignature:
    """Lazy wrapper for the escalation summary signature."""

    _cls: type | None = None

    @classmethod
    def get(cls) -> type:
        if cls._cls is None:
            dspy = _import_dspy()

            class _EscalationSummarySignature(dspy.Signature):
                """Extract key escalation signals and conflict trajectory from this conversation."""

                context: str = dspy.InputField(desc="Previous messages in the conversation")
                message: str = dspy.InputField(desc="The current message to analyze")
                escalation_summary: str = dspy.OutputField(
                    desc="Key escalation signals, conflict trajectory, tone shifts, and any de-escalation attempts"
                )

            cls._cls = _EscalationSummarySignature
        return cls._cls


class ScoringSignature:
    """Lazy wrapper for the scoring-from-summary signature."""

    _cls: type | None = None

    @classmethod
    def get(cls) -> type:
        if cls._cls is None:
            dspy = _import_dspy()

            class _ScoringSignature(dspy.Signature):
                """Rate derailment risk based on conversation history and escalation analysis."""

                context: str = dspy.InputField(
                    desc="The verbatim previous messages in the conversation"
                )
                message: str = dspy.InputField(desc="The current message to analyze")
                escalation_analysis: str = dspy.InputField(
                    desc="Analysis of conflict signals and trajectory"
                )
                derailment_score: int = dspy.OutputField(
                    desc="Score 0-100. 0=Civil, 50=Heated disagreement, 100=Active hostility/Safety risk",
                )
                reasoning: str = dspy.OutputField(desc="Justification for the score")

            cls._cls = _ScoringSignature
        return cls._cls


class TwoStageFlashpointDetector:
    """Two-stage flashpoint detector: summarize escalation signals, then score.

    Stage 1 (summarize): Extracts key escalation signals from the conversation.
    Stage 2 (score): Scores derailment risk based on the extracted signals.

    This gives GEPA two components to optimize independently, enabling
    it to learn both what signals matter and how to score them.

    Same external API as FlashpointDetector (context, message -> derailment_score, reasoning).
    """

    def __init__(self) -> None:
        dspy = _import_dspy()
        summary_sig = EscalationSummarySignature.get()
        scoring_sig = ScoringSignature.get()

        class _Inner(dspy.Module):
            def __init__(self_inner) -> None:  # noqa: N805
                super().__init__()
                self_inner.summarize = dspy.ChainOfThought(summary_sig)
                self_inner.score = dspy.ChainOfThought(scoring_sig)

            def forward(self_inner, context: str, message: str) -> dspy.Prediction:  # noqa: N805
                summary = self_inner.summarize(context=context, message=message)
                return self_inner.score(
                    context=context,
                    message=message,
                    escalation_analysis=summary.escalation_summary,
                )

        self._inner = _Inner()
        self.summarize = self._inner.summarize
        self.score = self._inner.score

    def forward(self, context: str, message: str) -> dspy.Prediction:
        return self._inner.forward(context=context, message=message)

    def load(self, path: str) -> None:
        self._inner.load(path)
        self.summarize = self._inner.summarize
        self.score = self._inner.score

    def save(self, path: str) -> None:
        self._inner.save(path)

    def __call__(self, context: str, message: str) -> dspy.Prediction:
        return self.forward(context=context, message=message)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
