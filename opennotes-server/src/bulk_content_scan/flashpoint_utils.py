"""Shared utilities for flashpoint detection (runtime + training scripts)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import dspy

logger = logging.getLogger(__name__)


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
                """Predict whether a conversation is about to derail into conflict."""

                context: str = dspy.InputField(desc="Previous messages in the conversation")
                message: str = dspy.InputField(desc="The current message to analyze")
                will_derail: bool = dspy.OutputField(
                    desc="True if the conversation shows signs of derailing"
                )
                reasoning: str = dspy.OutputField(
                    desc="Brief explanation of the key signals detected"
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
