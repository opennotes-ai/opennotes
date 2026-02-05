"""DSPy signature and module for conversation flashpoint detection.

This module re-exports the core DSPy components from the shared utility
and defines training-specific metrics.
"""

from typing import Any

import dspy

from src.bulk_content_scan.flashpoint_utils import (
    FlashpointDetector,
    FlashpointSignature,
    parse_bool,
)

__all__ = [
    "FlashpointDetector",
    "FlashpointSignature",
    "flashpoint_metric",
    "flashpoint_metric_with_feedback",
]


def flashpoint_metric(
    example: dspy.Example,
    pred: dspy.Prediction,
    trace: Any = None,
) -> float:
    """Simple metric for evaluating flashpoint predictions.

    Returns 1.0 for correct predictions, 0.0 for incorrect.
    Handles both boolean and string representations.
    """
    expected = parse_bool(example.will_derail)
    predicted = parse_bool(pred.will_derail)
    return 1.0 if predicted == expected else 0.0


def flashpoint_metric_with_feedback(
    example: dspy.Example,
    pred: dspy.Prediction,
    trace: Any = None,
    pred_name: str | None = None,
    pred_trace: Any = None,
) -> dspy.Prediction:
    """GEPA-compatible metric that returns score and feedback.

    GEPA requires metrics that return both a score and feedback
    to guide its reflective optimization process.

    Args:
        example: The gold example with expected will_derail value
        pred: The model's prediction
        trace: Optional execution trace
        pred_name: Optional name of target predictor being optimized
        pred_trace: Optional trace of target predictor

    Returns:
        dspy.Prediction with score (float) and feedback (str)
    """
    expected = parse_bool(example.will_derail)
    predicted = parse_bool(pred.will_derail)

    correct = predicted == expected
    score = 1.0 if correct else 0.0

    if correct:
        feedback = (
            f"Correct prediction. Expected will_derail={expected}, "
            f"predicted will_derail={predicted}."
        )
    else:
        reasoning_preview = str(pred.reasoning)[:300] if hasattr(pred, "reasoning") else "N/A"
        feedback = (
            f"Incorrect prediction. Expected will_derail={expected}, "
            f"predicted will_derail={predicted}. "
            f"The reasoning was: {reasoning_preview}... "
            f"Consider what signals in the context and message led to this error."
        )

    return dspy.Prediction(score=score, feedback=feedback)


if __name__ == "__main__":
    lm = dspy.LM("openai/gpt-4o-mini")
    dspy.configure(lm=lm)

    detector = FlashpointDetector()
    result = detector(
        context="user1: I think we should consider option A\nuser2: That's a terrible idea",
        message="user1: Are you even reading what I wrote? You clearly don't understand",
    )
    print(f"Will derail: {result.will_derail}")
    print(f"Reasoning: {result.reasoning}")
