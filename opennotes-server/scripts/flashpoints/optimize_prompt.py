#!/usr/bin/env python3
"""Optimize flashpoint detection prompt using DSPy GEPA.

This script uses the GEPA optimizer to find the best prompt instructions
for the flashpoint detection task. GEPA is preferred over MIPRO because:
- More sample-efficient (works well with smaller training sets)
- Better at structured outputs (bool + reasoning)
- Excels at multi-step reasoning tasks

Usage:
    # Run optimization with default settings
    uv run python scripts/flashpoints/optimize_prompt.py

    # Run with custom model and auto level
    uv run python scripts/flashpoints/optimize_prompt.py --model openai/gpt-5.1 --auto heavy

    # Evaluate an existing optimized model
    uv run python scripts/flashpoints/optimize_prompt.py --eval-only data/flashpoints/optimized_detector.json
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import dspy
from tqdm import tqdm

from scripts.flashpoints.dspy_dataset import load_flashpoint_datasets
from scripts.flashpoints.flashpoint_module import (
    FlashpointDetector,
    flashpoint_metric,
    flashpoint_metric_with_feedback,
)
from src.bulk_content_scan.flashpoint_utils import parse_bool


def optimize_flashpoint_detector(
    model: str = "openai/gpt-5-mini",
    auto: str = "medium",
    output_path: Path | None = None,
    reflection_model: str | None = None,
    max_train: int = 200,
    max_dev: int = 50,
    log_dir: Path | None = None,
    reflection_minibatch_size: int = 5,
    num_threads: int = 6,
) -> FlashpointDetector:
    """Run GEPA optimization on the flashpoint detector.

    Args:
        model: The LLM model to use for the detector
        auto: GEPA optimization level (light, medium, heavy)
        output_path: Where to save the optimized program
        reflection_model: Model to use for GEPA reflection (defaults to gpt-5.1)
        max_train: Maximum training examples to use
        max_dev: Maximum dev examples to use
        log_dir: Directory for GEPA checkpoints (enables resume on restart)

    Returns:
        The optimized FlashpointDetector module
    """
    lm = dspy.LM(model)
    dspy.configure(lm=lm)

    trainset, devset, _ = load_flashpoint_datasets()
    print(f"Loaded {len(trainset)} training examples, {len(devset)} dev examples")

    trainset = trainset[:max_train]
    devset = devset[:max_dev]
    print(f"Using {len(trainset)} training, {len(devset)} dev examples for optimization")

    reflection_lm = dspy.LM(
        reflection_model or "openai/gpt-5.1",
        temperature=1.0,
        max_tokens=32000,
    )

    gepa_kwargs: dict[str, Any] = {
        "metric": flashpoint_metric_with_feedback,
        "auto": auto,
        "num_threads": num_threads,
        "track_stats": True,
        "reflection_minibatch_size": reflection_minibatch_size,
        "reflection_lm": reflection_lm,
    }
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        gepa_kwargs["log_dir"] = str(log_dir)

    optimizer = dspy.GEPA(**gepa_kwargs)

    detector = FlashpointDetector()

    print(f"Starting GEPA optimization (auto={auto}, model={model})...")
    print("This may take a while depending on the auto level and dataset size.")
    optimized = optimizer.compile(
        detector,
        trainset=trainset,
        valset=devset,
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        optimized.save(str(output_path))
        print(f"Saved optimized program to {output_path}")

    return optimized


def _evaluate_single(
    detector: FlashpointDetector, idx: int, example: dspy.Example
) -> tuple[int, float | None, int | None, str | None]:
    """Evaluate a single example. Returns (idx, score, error_msg)."""
    try:
        pred = detector(context=example.context, message=example.message)
        score = flashpoint_metric(example, pred)
        expected = parse_bool(example.will_derail)
        predicted = parse_bool(pred.will_derail)

        if expected and predicted:
            category = 0  # TP
        elif not expected and predicted:
            category = 1  # FP
        elif expected and not predicted:
            category = 2  # FN
        else:
            category = 3  # TN

        return (idx, score, category, None)
    except Exception as e:
        return (idx, None, None, str(e))


def evaluate_detector(
    detector: FlashpointDetector,
    testset: list[dspy.Example],
    verbose: bool = False,
    num_threads: int = 1,
) -> dict:
    """Evaluate the detector on the test set.

    Returns accuracy, precision, recall, F1, and confusion matrix.
    """
    correct = 0
    errors = 0
    counters = [0, 0, 0, 0]  # TP, FP, FN, TN

    def _update_progress(pbar, idx, score, category, error_msg):
        nonlocal correct, errors
        if error_msg is not None:
            errors += 1
            tqdm.write(f"Error evaluating example {idx}: {error_msg}")
        else:
            correct += score
            counters[category] += 1

        if sum(counters) > 0:
            tp, fp, fn, tn = counters
            p = tp / (tp + fp) if (tp + fp) > 0 else 0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
            pbar.set_postfix(
                TP=tp,
                FP=fp,
                FN=fn,
                TN=tn,
                P=f"{p:.0%}",
                R=f"{r:.0%}",
                F1=f"{f1:.0%}",
                err=errors,
            )
        pbar.update(1)

    pbar = tqdm(total=len(testset), desc="Evaluating", unit="ex")

    if num_threads <= 1:
        for i, example in enumerate(testset):
            idx, score, category, error_msg = _evaluate_single(detector, i, example)
            _update_progress(pbar, idx, score, category, error_msg)
    else:
        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = {
                pool.submit(_evaluate_single, detector, i, ex): i for i, ex in enumerate(testset)
            }
            for future in as_completed(futures):
                idx, score, category, error_msg = future.result()
                _update_progress(pbar, idx, score, category, error_msg)

    pbar.close()

    true_positives, false_positives, false_negatives, true_negatives = counters
    evaluated = len(testset) - errors
    accuracy = correct / evaluated if evaluated > 0 else 0
    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0
    )
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_negatives": true_negatives,
        "errors": errors,
        "error_rate": errors / len(testset) if testset else 0,
        "total": len(testset),
        "evaluated": evaluated,
    }


def print_metrics(metrics: dict) -> None:
    """Print evaluation metrics in a formatted way."""
    print("\n" + "=" * 50)
    print("EVALUATION RESULTS")
    print("=" * 50)
    print(f"Accuracy:  {metrics['accuracy']:.2%}")
    print(f"Precision: {metrics['precision']:.2%}")
    print(f"Recall:    {metrics['recall']:.2%}")
    print(f"F1 Score:  {metrics['f1']:.2%}")
    print("\nConfusion Matrix:")
    print(f"  True Positives:  {metrics['true_positives']}")
    print(f"  False Positives: {metrics['false_positives']}")
    print(f"  False Negatives: {metrics['false_negatives']}")
    print(f"  True Negatives:  {metrics['true_negatives']}")
    print(f"\nTotal evaluated: {metrics['evaluated']}/{metrics['total']}")
    if metrics["errors"] > 0:
        print(f"\nErrors: {metrics['errors']} ({metrics['error_rate']:.1%})")

    if metrics["f1"] >= 0.75:
        print("\n*** QUALITY GATE PASSED: F1 >= 0.75 ***")
    else:
        print(f"\n*** QUALITY GATE FAILED: F1 = {metrics['f1']:.2%} < 0.75 ***")


def main():
    parser = argparse.ArgumentParser(
        description="Optimize flashpoint detection prompt using DSPy GEPA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run optimization with defaults
  uv run python scripts/flashpoints/optimize_prompt.py

  # Use a different model
  uv run python scripts/flashpoints/optimize_prompt.py --model openai/gpt-5.1

  # Heavy optimization for better results
  uv run python scripts/flashpoints/optimize_prompt.py --auto heavy

  # Evaluate existing model without re-optimizing
  uv run python scripts/flashpoints/optimize_prompt.py --eval-only data/flashpoints/optimized_detector.json
        """,
    )
    parser.add_argument(
        "--model",
        default="openai/gpt-5-mini",
        help="LLM model to use for the detector (default: openai/gpt-5-mini)",
    )
    parser.add_argument(
        "--reflection-model",
        default=None,
        help="LLM model for GEPA reflection (default: openai/gpt-5.1)",
    )
    parser.add_argument(
        "--auto",
        default="medium",
        choices=["light", "medium", "heavy"],
        help="GEPA optimization level (default: medium)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent.parent
        / "data"
        / "flashpoints"
        / "optimized_detector.json",
        help="Where to save optimized model (default: data/flashpoints/optimized_detector.json)",
    )
    parser.add_argument(
        "--eval-only",
        type=Path,
        default=None,
        help="Load and evaluate existing model without optimization",
    )
    parser.add_argument(
        "--max-test",
        type=int,
        default=200,
        help="Maximum test examples for evaluation (default: 200)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress during evaluation",
    )
    parser.add_argument(
        "--reflection-minibatch-size",
        type=int,
        default=5,
        help="Number of examples per GEPA reflection minibatch (default: 5)",
    )
    parser.add_argument(
        "--num-threads",
        type=int,
        default=6,
        help="Number of threads for GEPA optimization (default: 6)",
    )
    parser.add_argument(
        "--num-eval-threads",
        type=int,
        default=8,
        help="Number of threads for parallel evaluation (default: 8)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path(__file__).parent.parent.parent / "data" / "flashpoints" / "gepa_logs",
        help="Directory for GEPA checkpoints/resume (default: data/flashpoints/gepa_logs)",
    )

    args = parser.parse_args()

    if args.eval_only:
        lm = dspy.LM(args.model)
        dspy.configure(lm=lm)
        print(f"Loading existing model from {args.eval_only}...")
        detector = FlashpointDetector()
        detector.load(str(args.eval_only))
        print("Model loaded successfully.")
    else:
        detector = optimize_flashpoint_detector(
            model=args.model,
            auto=args.auto,
            output_path=args.output,
            reflection_model=args.reflection_model,
            log_dir=args.log_dir,
            reflection_minibatch_size=args.reflection_minibatch_size,
            num_threads=args.num_threads,
        )

    _, _, testset = load_flashpoint_datasets()
    testset = testset[: args.max_test]

    print(f"\nEvaluating on {len(testset)} test examples ({args.num_eval_threads} threads)...")
    metrics = evaluate_detector(
        detector, testset, verbose=args.verbose, num_threads=args.num_eval_threads
    )
    print_metrics(metrics)

    error_rate_threshold = 0.05
    if metrics["error_rate"] > error_rate_threshold:
        print(
            f"\n*** FAILED: Error rate {metrics['error_rate']:.1%} > {error_rate_threshold:.0%} threshold ***"
        )
        print("This indicates infrastructure issues (API rate limiting, model errors, etc.)")
        return 2

    return 0 if metrics["f1"] >= 0.75 else 1


if __name__ == "__main__":
    sys.exit(main())
