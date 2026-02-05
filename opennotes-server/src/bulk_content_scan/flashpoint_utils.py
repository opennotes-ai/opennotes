"""Shared utilities for flashpoint detection (runtime + training scripts)."""

from __future__ import annotations

from typing import Any

import dspy


def parse_bool(value: Any) -> bool:
    """Parse a value to boolean, handling string representations from LLM output."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.lower()
        if lower in ("true", "yes", "1", "y"):
            return True
        if lower in ("false", "no", "0", "n"):
            return False
        return bool(value)
    return bool(value)


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
