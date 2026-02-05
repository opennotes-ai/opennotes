"""DSPy signature and module for conversation flashpoint detection.

This module defines the core DSPy components for detecting early warning
signs that a conversation may derail into conflict.
"""

from typing import Any

import dspy


class FlashpointSignature(dspy.Signature):
    """Predict whether a conversation is about to derail into conflict.

    Given the conversation context and a new message, determine if this
    message shows signs that the conversation is heading toward:
    - Personal attacks
    - Rule-violating behavior
    - Moderator intervention
    - Hostile escalation
    """

    context: str = dspy.InputField(
        desc="Previous messages in the conversation, formatted as 'speaker: message'"
    )
    message: str = dspy.InputField(desc="The current message to analyze for flashpoint signals")
    will_derail: bool = dspy.OutputField(
        desc="True if the conversation shows signs of derailing, False otherwise"
    )
    reasoning: str = dspy.OutputField(
        desc="Brief explanation of the key signals detected (or lack thereof)"
    )


class FlashpointDetector(dspy.Module):
    """DSPy module for detecting conversation flashpoints.

    Uses ChainOfThought to reason step-by-step before predicting
    whether a conversation will derail.
    """

    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(FlashpointSignature)

    def forward(self, context: str, message: str) -> dspy.Prediction:
        return self.predict(context=context, message=message)


def _parse_bool(value: Any) -> bool:
    """Parse a value to boolean, handling string representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "yes", "1")
    return bool(value)


def flashpoint_metric(
    example: dspy.Example,
    pred: dspy.Prediction,
    trace: Any = None,
) -> float:
    """Simple metric for evaluating flashpoint predictions.

    Returns 1.0 for correct predictions, 0.0 for incorrect.
    Handles both boolean and string representations.
    """
    expected = _parse_bool(example.will_derail)
    predicted = _parse_bool(pred.will_derail)
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
    expected = _parse_bool(example.will_derail)
    predicted = _parse_bool(pred.will_derail)

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
