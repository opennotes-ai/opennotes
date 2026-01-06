"""Evaluation metrics for relevance check optimization."""

from typing import Any

import dspy


def relevance_metric(
    example: dspy.Example,
    prediction: dspy.Prediction,
    trace: Any = None,
) -> float:
    """Metric for relevance check - penalizes false positives heavily.

    Args:
        example: The ground truth example
        prediction: The model's prediction
        trace: Optional trace for debugging

    Returns:
        Score between 0.0 and 1.0
    """
    expected = example.is_relevant
    predicted = prediction.is_relevant

    if expected == predicted:
        return 1.0

    if not expected and predicted:
        return 0.0

    return 0.3


def precision_at_k(
    examples: list[dspy.Example],
    predictions: list[dspy.Prediction],
) -> float:
    """Calculate precision for relevance predictions.

    Precision = TP / (TP + FP)
    """
    true_positives = 0
    false_positives = 0

    for ex, pred in zip(examples, predictions, strict=True):
        if pred.is_relevant:
            if ex.is_relevant:
                true_positives += 1
            else:
                false_positives += 1

    if true_positives + false_positives == 0:
        return 1.0

    return true_positives / (true_positives + false_positives)


def recall_at_k(
    examples: list[dspy.Example],
    predictions: list[dspy.Prediction],
) -> float:
    """Calculate recall for relevance predictions.

    Recall = TP / (TP + FN)
    """
    true_positives = 0
    false_negatives = 0

    for ex, pred in zip(examples, predictions, strict=True):
        if ex.is_relevant:
            if pred.is_relevant:
                true_positives += 1
            else:
                false_negatives += 1

    if true_positives + false_negatives == 0:
        return 1.0

    return true_positives / (true_positives + false_negatives)


def f1_score(
    examples: list[dspy.Example],
    predictions: list[dspy.Prediction],
) -> float:
    """Calculate F1 score (harmonic mean of precision and recall)."""
    p = precision_at_k(examples, predictions)
    r = recall_at_k(examples, predictions)

    if p + r == 0:
        return 0.0

    return 2 * (p * r) / (p + r)


def evaluate_model(
    module: dspy.Module,
    examples: list[dspy.Example],
) -> dict[str, Any]:
    """Evaluate a module on a set of examples.

    Returns:
        Dictionary with precision, recall, f1, accuracy, and per-example results
    """
    predictions = []
    results = []

    for ex in examples:
        try:
            pred = module(
                message=ex.message,
                fact_check_title=ex.fact_check_title,
                fact_check_content=ex.fact_check_content,
            )
            predictions.append(pred)

            results.append(
                {
                    "message": ex.message[:50] + "..." if len(ex.message) > 50 else ex.message,
                    "expected": ex.is_relevant,
                    "predicted": pred.is_relevant,
                    "correct": ex.is_relevant == pred.is_relevant,
                    "reasoning": pred.reasoning,
                }
            )
        except Exception as e:
            results.append(
                {
                    "message": ex.message[:50] + "..." if len(ex.message) > 50 else ex.message,
                    "expected": ex.is_relevant,
                    "predicted": None,
                    "correct": False,
                    "error": str(e),
                }
            )
            dummy_pred = dspy.Prediction(is_relevant=True, reasoning="Error")
            predictions.append(dummy_pred)

    correct = sum(1 for r in results if r["correct"])
    accuracy = correct / len(examples) if examples else 0.0

    return {
        "accuracy": accuracy,
        "precision": precision_at_k(examples, predictions),
        "recall": recall_at_k(examples, predictions),
        "f1": f1_score(examples, predictions),
        "total": len(examples),
        "correct": correct,
        "results": results,
    }
