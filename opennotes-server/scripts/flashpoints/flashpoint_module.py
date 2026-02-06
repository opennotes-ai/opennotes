"""DSPy signature and module for conversation flashpoint detection.

This module re-exports the core DSPy components from the shared utility
and defines training-specific metrics including:
- Simple accuracy metric for evaluation
- Comparative metric with ScoreWithFeedback for GEPA optimization
- FlashpointTrainerProgram for paired/contrastive training

Feedback philosophy: the comparative metric provides factual outcome data
(scores, difference, correctness) without prescribing what conversational
signals the reflection LM should look for. The reflection LM is capable
of identifying important patterns on its own — hardcoding a checklist of
escalation signals constrains its ability to discover what actually matters.

For dynamic feedback mode, a FeedbackGenerator DSPy module generates
diagnostic feedback via LLM, making the feedback itself evolvable.
"""

import os
from collections.abc import Callable
from typing import Any

import dspy
from dspy.teleprompt.gepa.gepa_utils import ScoreWithFeedback

from src.bulk_content_scan.flashpoint_utils import (
    FlashpointDetector,
    FlashpointSignature,
    TwoStageFlashpointDetector,
    parse_derailment_score,
)

__all__ = [
    "FlashpointDetector",
    "FlashpointSignature",
    "FlashpointTrainerProgram",
    "comparative_flashpoint_metric",
    "flashpoint_metric",
    "make_comparative_metric",
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


def _extract_reasoning(pred_trace: Any) -> tuple[str, str]:
    """Extract reasoning from the pred_trace for both derailing and non-derailing runs.

    pred_trace is list[tuple[Predict, dict[str, Any], Prediction]].
    The FlashpointTrainerProgram runs the detector twice, so there may be
    two trace entries. Returns (derailing_reasoning, non_derailing_reasoning).
    """
    if not pred_trace:
        return ("N/A", "N/A")
    reasoning_parts = []
    for _, _, output in pred_trace:
        r = getattr(output, "reasoning", None)
        if r:
            reasoning_parts.append(str(r)[:300])
        else:
            reasoning_parts.append("N/A")
    if len(reasoning_parts) >= 2:
        return (reasoning_parts[0], reasoning_parts[1])
    if len(reasoning_parts) == 1:
        return (reasoning_parts[0], "N/A")
    return ("N/A", "N/A")


def _static_feedback(
    derailing_score: int,
    non_derailing_score: int,
    score_diff: int,
    derailing_reasoning: str,
    non_derailing_reasoning: str,
) -> str:
    """Build factual-only feedback without prescriptive guidance."""
    if score_diff > 0:
        label = "CORRECT"
    elif score_diff == 0:
        label = "TIED (WRONG)"
    else:
        label = "WRONG"

    feedback = (
        f"{label}: Derailing conversation scored {derailing_score}/100, "
        f"non-derailing scored {non_derailing_score}/100 "
        f"(difference: {score_diff:+d}).\n"
    )

    if score_diff <= 0:
        feedback += "The derailing conversation should have scored higher.\n"

    feedback += f"Derailing reasoning: {derailing_reasoning}\n"
    feedback += f"Non-derailing reasoning: {non_derailing_reasoning}\n"

    if score_diff > 0 and score_diff < 20:
        feedback += f"Margin is narrow ({score_diff} points).\n"

    return feedback


class _FeedbackSignature(dspy.Signature):
    """Analyze a flashpoint detection error and provide diagnostic feedback."""

    derailing_score: int = dspy.InputField(desc="Score assigned to the derailing conversation")
    non_derailing_score: int = dspy.InputField(
        desc="Score assigned to the non-derailing conversation"
    )
    score_difference: int = dspy.InputField(
        desc="derailing_score - non_derailing_score (positive means correct ordering)"
    )
    derailing_reasoning: str = dspy.InputField(
        desc="Model's reasoning for the derailing conversation"
    )
    non_derailing_reasoning: str = dspy.InputField(
        desc="Model's reasoning for the non-derailing conversation"
    )
    feedback: str = dspy.OutputField(
        desc=(
            "Diagnostic analysis of what the model got wrong and why. "
            "Identify the key signals in the conversations that were missed or misweighted."
        )
    )


class FeedbackGenerator:
    """Generates diagnostic feedback via LLM for GEPA reflection.

    Uses dspy.Predict internally, making the feedback generation itself
    a parameterizable DSPy component whose instructions can evolve
    if this module is compiled/optimized.
    """

    def __init__(self) -> None:
        self._predict = dspy.Predict(_FeedbackSignature)

    def __call__(
        self,
        derailing_score: int,
        non_derailing_score: int,
        score_diff: int,
        derailing_reasoning: str,
        non_derailing_reasoning: str,
    ) -> str:
        result = self._predict(
            derailing_score=derailing_score,
            non_derailing_score=non_derailing_score,
            score_difference=score_diff,
            derailing_reasoning=derailing_reasoning,
            non_derailing_reasoning=non_derailing_reasoning,
        )
        return str(result.feedback)


_feedback_generator_cache: dict[str, FeedbackGenerator] = {}


def _get_feedback_generator() -> FeedbackGenerator:
    if "instance" not in _feedback_generator_cache:
        _feedback_generator_cache["instance"] = FeedbackGenerator()
    return _feedback_generator_cache["instance"]


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

    Feedback is factual-only: scores, difference, and reasoning excerpts.
    No prescriptive checklists — the reflection LM identifies important
    patterns on its own.
    """
    derailing_score = parse_derailment_score(pred.derailing_score)
    non_derailing_score = parse_derailment_score(pred.non_derailing_score)
    score_diff = derailing_score - non_derailing_score
    feedback_score = 1.0 if score_diff > 0 else 0.0

    derailing_reasoning, non_derailing_reasoning = _extract_reasoning(pred_trace)

    feedback = _static_feedback(
        derailing_score,
        non_derailing_score,
        score_diff,
        derailing_reasoning,
        non_derailing_reasoning,
    )

    return ScoreWithFeedback(score=feedback_score, feedback=feedback)


def _dynamic_comparative_metric(
    gold: dspy.Example,
    pred: dspy.Prediction,
    trace: Any = None,
    pred_name: str | None = None,
    pred_trace: Any = None,
) -> ScoreWithFeedback:
    """GEPA-compatible comparative metric with LLM-generated feedback.

    On correct predictions, returns factual feedback. On errors, invokes
    a FeedbackGenerator DSPy module to produce diagnostic analysis,
    making the feedback itself evolvable.
    """
    derailing_score = parse_derailment_score(pred.derailing_score)
    non_derailing_score = parse_derailment_score(pred.non_derailing_score)
    score_diff = derailing_score - non_derailing_score
    feedback_score = 1.0 if score_diff > 0 else 0.0

    derailing_reasoning, non_derailing_reasoning = _extract_reasoning(pred_trace)

    if score_diff > 0:
        feedback = _static_feedback(
            derailing_score,
            non_derailing_score,
            score_diff,
            derailing_reasoning,
            non_derailing_reasoning,
        )
    else:
        try:
            generator = _get_feedback_generator()
            feedback = generator(
                derailing_score=derailing_score,
                non_derailing_score=non_derailing_score,
                score_diff=score_diff,
                derailing_reasoning=derailing_reasoning,
                non_derailing_reasoning=non_derailing_reasoning,
            )
        except Exception:
            feedback = _static_feedback(
                derailing_score,
                non_derailing_score,
                score_diff,
                derailing_reasoning,
                non_derailing_reasoning,
            )

    return ScoreWithFeedback(score=feedback_score, feedback=feedback)


def make_comparative_metric(
    feedback_mode: str = "static",
) -> Callable:
    """Factory that returns the appropriate comparative metric function.

    Args:
        feedback_mode: "static" for factual-only feedback (default),
            "dynamic" for LLM-generated diagnostic feedback.

    Returns:
        A GEPA-compatible metric function.
    """
    if feedback_mode == "dynamic":
        return _dynamic_comparative_metric
    return comparative_flashpoint_metric


class FlashpointTrainerProgram(dspy.Module):
    """Wrapper that runs the flashpoint detector on both paired examples.

    Mirrors the MonitorTrainerProgram pattern from the GEPA trusted
    monitor tutorial. Takes a paired example (derailing + non-derailing
    conversation) and returns both scores for comparative training.
    """

    def __init__(self, detector: FlashpointDetector | TwoStageFlashpointDetector) -> None:
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
