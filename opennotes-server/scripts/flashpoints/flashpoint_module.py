"""DSPy signature and module for conversation flashpoint detection.

This module re-exports the core DSPy components from the shared utility
and defines training-specific metrics including:
- Simple accuracy metric for evaluation
- Comparative metric with ScoreWithFeedback for GEPA optimization
- FlashpointTrainerProgram for paired/contrastive training
"""

import os
from typing import Any

import dspy
from dspy.teleprompt.gepa.gepa_utils import ScoreWithFeedback

from src.bulk_content_scan.flashpoint_utils import (
    FlashpointDetector,
    FlashpointSignature,
    parse_derailment_score,
)

__all__ = [
    "FlashpointDetector",
    "FlashpointSignature",
    "FlashpointTrainerProgram",
    "comparative_flashpoint_metric",
    "flashpoint_metric",
]


def flashpoint_metric(
    example: dspy.Example,
    pred: dspy.Prediction,
    trace: Any = None,
) -> float:
    """Simple metric for evaluating flashpoint predictions.

    Returns 1.0 when derailing conversations score higher than
    non-derailing ones (for paired examples) or when the score
    crosses the 50-point threshold correctly (for single examples).
    """
    if hasattr(example, "derailing_context"):
        derailing_score = parse_derailment_score(pred.derailing_score)
        non_derailing_score = parse_derailment_score(pred.non_derailing_score)
        return 1.0 if derailing_score > non_derailing_score else 0.0

    expected_derailing = getattr(example, "will_derail", False)
    predicted_score = parse_derailment_score(pred.derailment_score)
    if expected_derailing:
        return 1.0 if predicted_score >= 50 else 0.0
    return 1.0 if predicted_score < 50 else 0.0


def comparative_flashpoint_metric(
    gold: dspy.Example,
    pred: dspy.Prediction,
    trace: Any = None,
    pred_name: str | None = None,
    pred_trace: Any = None,
) -> ScoreWithFeedback:
    """GEPA-compatible comparative metric returning ScoreWithFeedback.

    Compares the derailment scores assigned to a derailing vs non-derailing
    conversation pair. The monitor should assign a higher score to the
    derailing conversation.

    Returns ScoreWithFeedback with:
    - score: 1.0 if derailing_score > non_derailing_score, else 0.0
    - feedback: Rich textual guidance for GEPA reflection including
      score comparison, escalation signals, and coaching guidance
    """
    derailing_score = parse_derailment_score(pred.derailing_score)
    non_derailing_score = parse_derailment_score(pred.non_derailing_score)

    score_diff = derailing_score - non_derailing_score
    feedback_score = 1.0 if score_diff > 0 else 0.0

    feedback = ""

    if score_diff > 0:
        feedback += "CORRECT: "
    elif score_diff == 0:
        feedback += "TIED (WRONG): "
    else:
        feedback += "WRONG: "

    feedback += (
        f"You rated the derailing conversation at {derailing_score}/100 "
        f"and the non-derailing conversation at {non_derailing_score}/100 "
        f"(difference: {score_diff:+d}).\n"
    )

    if score_diff <= 0:
        feedback += (
            "\nThe derailing conversation should have received a HIGHER score. "
            "Look for escalation signals such as:\n"
            "- Shift from topic disagreement to personal attacks\n"
            "- Increasingly aggressive or dismissive language\n"
            "- Absolutist language ('always', 'never', 'you people')\n"
            "- Questioning competence or motives rather than ideas\n"
            "\nThe non-derailing conversation should have received a LOWER score. "
            "Constructive disagreement features:\n"
            "- Focus on ideas rather than people\n"
            "- Acknowledgment of other viewpoints\n"
            "- Absence of personal attacks or dismissiveness\n"
            "\nTry to use the full 0-100 range. Precision matters most "
            "at moderate scores (30-70) where separation is hardest.\n"
        )
    else:
        feedback += "Good separation between derailing and non-derailing conversations.\n"
        if score_diff < 20:
            feedback += (
                f"However, the gap ({score_diff} points) is small. "
                "Try to increase separation for more confident classification.\n"
            )

    return ScoreWithFeedback(
        score=feedback_score,
        feedback=feedback,
    )


class FlashpointTrainerProgram(dspy.Module):
    """Wrapper that runs the flashpoint detector on both paired examples.

    Mirrors the MonitorTrainerProgram pattern from the GEPA trusted
    monitor tutorial. Takes a paired example (derailing + non-derailing
    conversation) and returns both scores for comparative training.
    """

    def __init__(self, detector: FlashpointDetector) -> None:
        super().__init__()
        self.detector = detector._inner

    def forward(
        self,
        derailing_context: str,
        derailing_message: str,
        non_derailing_context: str,
        non_derailing_message: str,
    ) -> dspy.Prediction:
        derailing_pred = self.detector(
            context=derailing_context,
            message=derailing_message,
        )
        non_derailing_pred = self.detector(
            context=non_derailing_context,
            message=non_derailing_message,
        )
        return dspy.Prediction(
            derailing_score=parse_derailment_score(derailing_pred.derailment_score),
            non_derailing_score=parse_derailment_score(non_derailing_pred.derailment_score),
        )


DEFAULT_MODEL = "openai/gpt-5-mini"

_API_KEY_ENV_VARS = {
    "openai/": "OPENAI_API_KEY",
    "anthropic/": "ANTHROPIC_API_KEY",
}


def _validate_api_key(model: str) -> None:
    """Validate the required API key env var is set for *model*."""
    for prefix, env_var in _API_KEY_ENV_VARS.items():
        if model.startswith(prefix):
            if not os.environ.get(env_var):
                raise SystemExit(
                    f"Error: {env_var} environment variable is required for model {model!r}"
                )
            return


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run a quick flashpoint detection demo.")
    parser.add_argument(
        "--model",
        default=os.environ.get("FLASHPOINT_MODEL", DEFAULT_MODEL),
        help=f"LLM model identifier (default: $FLASHPOINT_MODEL or {DEFAULT_MODEL})",
    )
    args = parser.parse_args()

    model: str = args.model
    _validate_api_key(model)

    lm = dspy.LM(model)
    dspy.configure(lm=lm)

    detector = FlashpointDetector()
    result = detector(
        context="user1: I think we should consider option A\nuser2: That's a terrible idea",
        message="user1: Are you even reading what I wrote? You clearly don't understand",
    )
    print(f"Derailment score: {result.derailment_score}")
    print(f"Reasoning: {result.reasoning}")
