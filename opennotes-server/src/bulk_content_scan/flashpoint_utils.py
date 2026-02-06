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
                    desc="Derailment risk score from 0 (no risk) to 100 (certain derailment)",
                )
                reasoning: str = dspy.OutputField(
                    desc="Brief explanation of the key escalation signals detected"
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
