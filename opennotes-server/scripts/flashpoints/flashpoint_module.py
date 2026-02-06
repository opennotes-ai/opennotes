"""DSPy signature and module for conversation flashpoint detection.

This module re-exports the core DSPy components from the shared utility
and defines training-specific metrics including:
- Simple accuracy metric for evaluation
- Comparative metric with ScoreWithFeedback for GEPA optimization
- FlashpointTrainerProgram for paired/contrastive training

Feedback philosophy: the comparative metric provides factual outcome data
(scores, difference, model reasoning) plus meta-coaching guidance that
helps the reflection LM understand how to revise the student's prompt.
It does NOT prescribe specific conversational signals to look for — the
reflection LM is capable of identifying important patterns on its own.
Hardcoding a checklist of escalation signals constrains GEPA's ability
to discover what actually matters for this domain.

Note on LM context: GEPA calls the metric under the student LM context,
not the reflection LM. Any dspy.Predict calls inside the metric would
use the weak student model. This is why feedback generation is purely
programmatic — the reflection LM does all the analytical heavy lifting
when it reads the feedback during instruction proposal.
"""

import json
import os
from pathlib import Path
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
    "set_reasoning_log_path",
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


REASONING_TRUNCATION_LIMIT = 2000

_reasoning_log_path: dict[str, Path | None] = {"path": None}


def set_reasoning_log_path(path: Path | None) -> None:
    """Set the JSONL file path for logging full reasoning traces."""
    _reasoning_log_path["path"] = path


def _extract_reasoning(pred_trace: Any) -> tuple[str, str]:
    """Extract full reasoning from the pred_trace for both derailing and non-derailing runs.

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
            reasoning_parts.append(str(r))
        else:
            reasoning_parts.append("N/A")
    if len(reasoning_parts) >= 2:
        return (reasoning_parts[0], reasoning_parts[1])
    if len(reasoning_parts) == 1:
        return (reasoning_parts[0], "N/A")
    return ("N/A", "N/A")


def _truncate_reasoning(reasoning: str) -> str:
    if reasoning == "N/A" or len(reasoning) <= REASONING_TRUNCATION_LIMIT:
        return reasoning
    half = REASONING_TRUNCATION_LIMIT // 2
    return reasoning[:half] + " [...] " + reasoning[-half:]


def _log_reasoning(
    derailing_score: int,
    non_derailing_score: int,
    derailing_reasoning: str,
    non_derailing_reasoning: str,
) -> None:
    """Append a JSONL entry with full and truncated reasoning for diagnostics."""
    log_path = _reasoning_log_path["path"]
    if log_path is None:
        return
    entry = {
        "derailing_score": derailing_score,
        "non_derailing_score": non_derailing_score,
        "score_diff": derailing_score - non_derailing_score,
        "derailing_reasoning_full": derailing_reasoning,
        "derailing_reasoning_truncated": _truncate_reasoning(derailing_reasoning),
        "derailing_reasoning_len": len(derailing_reasoning),
        "non_derailing_reasoning_full": non_derailing_reasoning,
        "non_derailing_reasoning_truncated": _truncate_reasoning(non_derailing_reasoning),
        "non_derailing_reasoning_len": len(non_derailing_reasoning),
        "was_truncated": (
            len(derailing_reasoning) > REASONING_TRUNCATION_LIMIT
            or len(non_derailing_reasoning) > REASONING_TRUNCATION_LIMIT
        ),
    }
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _build_feedback(
    derailing_score: int,
    non_derailing_score: int,
    score_diff: int,
    derailing_reasoning: str,
    non_derailing_reasoning: str,
) -> str:
    """Build factual feedback with meta-coaching for the reflection LM.

    Provides the factual outcome (scores, reasoning) plus guidance on
    how to revise the student's prompt — without prescribing specific
    conversational signals to look for.
    """
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

    feedback += f"Derailing reasoning: {_truncate_reasoning(derailing_reasoning)}\n"
    feedback += f"Non-derailing reasoning: {_truncate_reasoning(non_derailing_reasoning)}\n"

    if score_diff <= 0:
        feedback += (
            "The model failed to distinguish these conversations. "
            "Revise the prompt to help the model identify what differentiates "
            "derailing from constructive dialogue in this pair.\n"
        )
    elif score_diff < 20:
        feedback += (
            f"Margin is narrow ({score_diff} points). "
            "Revise the prompt to help the model produce more confident separation "
            "between derailing and non-derailing conversations.\n"
        )

    return feedback


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

    Feedback combines factual outcome data with meta-coaching that guides
    the reflection LM on how to revise the student's prompt. Does not
    prescribe specific conversational signals — the reflection LM discovers
    what matters by analyzing the model's reasoning against the outcomes.
    """
    derailing_score = parse_derailment_score(pred.derailing_score)
    non_derailing_score = parse_derailment_score(pred.non_derailing_score)
    score_diff = derailing_score - non_derailing_score
    feedback_score = 1.0 if score_diff > 0 else 0.0

    derailing_reasoning, non_derailing_reasoning = _extract_reasoning(pred_trace)

    if _reasoning_log_path["path"] is not None and derailing_reasoning != "N/A":
        _log_reasoning(
            derailing_score,
            non_derailing_score,
            derailing_reasoning,
            non_derailing_reasoning,
        )

    feedback = _build_feedback(
        derailing_score,
        non_derailing_score,
        score_diff,
        derailing_reasoning,
        non_derailing_reasoning,
    )

    return ScoreWithFeedback(score=feedback_score, feedback=feedback)


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
