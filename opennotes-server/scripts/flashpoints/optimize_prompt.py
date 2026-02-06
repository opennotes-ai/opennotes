#!/usr/bin/env python3
"""Optimize flashpoint detection prompt using DSPy GEPA with comparative scoring.

Uses the GEPA optimizer with paired/contrastive training: each derailing
conversation is paired with a non-derailing one, and the optimizer learns
to assign higher derailment scores (0-100) to derailing conversations.

Key improvements over binary classification:
- Continuous 0-100 scoring enables flexible thresholding
- Comparative training with rich textual feedback
- Separate stronger reflection LM (gpt-5.2) for GEPA
- Optional BootstrapFinetune second pass
- ROC-style safety-at-audit-budget evaluation

Usage:
    # Run optimization with default settings
    uv run python scripts/flashpoints/optimize_prompt.py

    # Run with custom model and auto level
    uv run python scripts/flashpoints/optimize_prompt.py --model openai/gpt-5.1 --auto heavy

    # Evaluate an existing optimized model
    uv run python scripts/flashpoints/optimize_prompt.py --eval-only data/flashpoints/optimized_detector.json

    # Run with BootstrapFinetune second pass
    uv run python scripts/flashpoints/optimize_prompt.py --finetune
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import dspy
from tqdm import tqdm

from scripts.flashpoints.dspy_dataset import (
    load_flashpoint_datasets,
    load_paired_flashpoint_datasets,
)
from scripts.flashpoints.flashpoint_module import (
    FlashpointDetector,
    FlashpointTrainerProgram,
    comparative_flashpoint_metric,
    flashpoint_metric,
    set_reasoning_log_path,
)
from src.bulk_content_scan.flashpoint_utils import (
    TwoStageFlashpointDetector,
    parse_derailment_score,
)


class _TerseProposerSignature(dspy.Signature):
    """Analyze failure examples and rewrite the instruction in a few concise sentences."""

    current_instruction: str = dspy.InputField(desc="The current instruction for this component")
    failure_summary: str = dspy.InputField(
        desc="Summary of failure patterns from recent examples with feedback"
    )
    new_instruction: str = dspy.OutputField(
        desc="A few concise sentences (2-3 max) that address the failure patterns. Be direct and terse."
    )


class TerseInstructionProposer:
    """Instruction proposer that produces extremely terse, few-sentence prompts.

    Analyzes the reflective dataset (failures + feedback) like the default proposer,
    but constrains output to brief, direct instructions (2-3 sentences max).
    Empirically, short prompts have shown competitive or better performance than
    verbose multi-paragraph ones.
    """

    def __init__(self, reflection_lm: dspy.LM) -> None:
        self.reflection_lm = reflection_lm
        self.proposer = dspy.ChainOfThought(_TerseProposerSignature)

    def __call__(
        self,
        candidate: dict[str, str],
        reflective_dataset: dict[str, list],
        components_to_update: list[str],
    ) -> dict[str, str]:
        updated: dict[str, str] = {}

        with dspy.context(lm=self.reflection_lm):
            for component_name in components_to_update:
                current = candidate.get(component_name, "")
                examples = reflective_dataset.get(component_name, [])

                failure_lines = []
                for ex in examples[-10:]:
                    feedback = getattr(ex, "Feedback", getattr(ex, "feedback", ""))
                    if feedback and ("WRONG" in str(feedback) or "TIED" in str(feedback)):
                        failure_lines.append(str(feedback)[:200])

                if not failure_lines:
                    failure_lines = ["No clear failure patterns detected."]

                failure_summary = "\n".join(failure_lines)

                result = self.proposer(
                    current_instruction=current,
                    failure_summary=failure_summary,
                )
                updated[component_name] = result.new_instruction

        return updated


class _ShortProposerSignature(dspy.Signature):
    """Analyze failure examples and rewrite the instruction as a few short paragraphs."""

    current_instruction: str = dspy.InputField(desc="The current instruction for this component")
    failure_summary: str = dspy.InputField(
        desc="Summary of failure patterns from recent examples with feedback"
    )
    new_instruction: str = dspy.OutputField(
        desc=(
            "An improved instruction in 2-4 short paragraphs that addresses the failure patterns. "
            "You may vary the length — use fewer paragraphs if the instruction is simple, "
            "more if nuance is needed. Keep each paragraph to 1-3 sentences."
        )
    )


class ShortInstructionProposer:
    """Instruction proposer that produces short, paragraph-length prompts.

    Similar to TerseInstructionProposer but allows 2-4 short paragraphs.
    The length of the output is part of what the proposer is allowed to vary
    based on the complexity of the failure patterns.
    """

    def __init__(self, reflection_lm: dspy.LM) -> None:
        self.reflection_lm = reflection_lm
        self.proposer = dspy.ChainOfThought(_ShortProposerSignature)

    def __call__(
        self,
        candidate: dict[str, str],
        reflective_dataset: dict[str, list],
        components_to_update: list[str],
    ) -> dict[str, str]:
        updated: dict[str, str] = {}

        with dspy.context(lm=self.reflection_lm):
            for component_name in components_to_update:
                current = candidate.get(component_name, "")
                examples = reflective_dataset.get(component_name, [])

                failure_lines = []
                for ex in examples[-10:]:
                    feedback = getattr(ex, "Feedback", getattr(ex, "feedback", ""))
                    if feedback and ("WRONG" in str(feedback) or "TIED" in str(feedback)):
                        failure_lines.append(str(feedback)[:200])

                if not failure_lines:
                    failure_lines = ["No clear failure patterns detected."]

                failure_summary = "\n".join(failure_lines)

                result = self.proposer(
                    current_instruction=current,
                    failure_summary=failure_summary,
                )
                updated[component_name] = result.new_instruction

        return updated


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
    finetune: bool = False,
    component_selector: str = "round_robin",
    proposer: str = "default",
    two_stage: bool = False,
    bootstrap: bool = False,
    max_bootstrapped_demos: int = 4,
    max_labeled_demos: int = 4,
) -> FlashpointDetector | TwoStageFlashpointDetector:
    """Run GEPA optimization on the flashpoint detector with comparative training.

    Uses paired/contrastive examples where each derailing conversation is
    paired with a non-derailing one. The GEPA optimizer uses a separate
    reflection LM to iteratively improve the prompt.

    Args:
        model: The LLM model to use for the detector (student model)
        auto: GEPA optimization level (light, medium, heavy)
        output_path: Where to save the optimized program
        reflection_model: Model for GEPA reflection (defaults to gpt-5.2)
        max_train: Maximum paired training examples to use
        max_dev: Maximum paired dev examples to use
        log_dir: Directory for GEPA checkpoints (enables resume on restart)
        reflection_minibatch_size: Examples per GEPA reflection cycle
        num_threads: Threads for parallel evaluation
        finetune: Whether to run BootstrapFinetune as a second pass
        component_selector: "round_robin" (one component per iteration) or "all" (all at once)
        proposer: "default" (GEPA built-in), "terse" (few sentences), or "short" (few paragraphs)
        two_stage: Use two-stage detector (summarizer + scorer) for two GEPA components
        bootstrap: Run BootstrapFewShot pre-pass to seed GEPA with high-quality demos
        max_bootstrapped_demos: Max bootstrapped demonstrations per predictor
        max_labeled_demos: Max labeled demonstrations per predictor

    Returns:
        The optimized detector module
    """
    lm = dspy.LM(model)
    dspy.configure(lm=lm)

    paired_train, paired_dev = load_paired_flashpoint_datasets()
    print(f"Loaded {len(paired_train)} paired training, {len(paired_dev)} paired dev examples")

    paired_train = paired_train[:max_train]
    paired_dev = paired_dev[:max_dev]
    print(f"Using {len(paired_train)} training, {len(paired_dev)} dev paired examples")

    reflection_lm = dspy.LM(
        reflection_model or "openai/gpt-5.2",
        temperature=1.0,
        max_tokens=32000,
    )

    gepa_kwargs: dict[str, Any] = {
        "metric": comparative_flashpoint_metric,
        "auto": auto,
        "num_threads": num_threads,
        "track_stats": True,
        "reflection_minibatch_size": reflection_minibatch_size,
        "reflection_lm": reflection_lm,
        "component_selector": component_selector,
    }
    if proposer == "terse":
        gepa_kwargs["instruction_proposer"] = TerseInstructionProposer(reflection_lm)
    elif proposer == "short":
        gepa_kwargs["instruction_proposer"] = ShortInstructionProposer(reflection_lm)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        gepa_kwargs["log_dir"] = str(log_dir)

    if log_dir:
        reasoning_log = log_dir / "reasoning_traces.jsonl"
        set_reasoning_log_path(reasoning_log)
        print(f"Reasoning traces: {reasoning_log}")

    optimizer = dspy.GEPA(**gepa_kwargs)

    detector = TwoStageFlashpointDetector() if two_stage else FlashpointDetector()
    trainer = FlashpointTrainerProgram(detector)

    if bootstrap:
        from dspy.teleprompt import BootstrapFewShot

        bootstrap_opt = BootstrapFewShot(
            metric=flashpoint_metric,
            max_bootstrapped_demos=max_bootstrapped_demos,
            max_labeled_demos=max_labeled_demos,
            max_rounds=1,
        )
        print(
            f"Running BootstrapFewShot pre-pass "
            f"(max_bootstrapped={max_bootstrapped_demos}, max_labeled={max_labeled_demos})..."
        )
        trainer = bootstrap_opt.compile(trainer, trainset=paired_train)
        print("Bootstrap complete. Seeding GEPA with bootstrapped program.")

    print(f"Starting GEPA optimization (auto={auto}, model={model})...")
    print(f"Reflection LM: {reflection_model or 'openai/gpt-5.2'}")
    print(f"Component selector: {component_selector}, Proposer: {proposer}")
    if two_stage:
        print("Detector: two-stage (summarizer + scorer)")
    print("This may take a while depending on the auto level and dataset size.")

    optimized_trainer = optimizer.compile(
        trainer,
        trainset=paired_train,
        valset=paired_dev,
    )

    optimized_detector = optimized_trainer.detector

    if finetune:
        optimized_detector = _run_finetune(
            optimized_detector, model, paired_train, comparative_flashpoint_metric
        )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        optimized_detector.save(str(output_path))
        print(f"Saved optimized program to {output_path}")

    return optimized_detector


def _run_finetune(
    detector: FlashpointDetector,
    model: str,
    paired_train: list[dspy.Example],
    metric: Any,
) -> FlashpointDetector:
    """Run BootstrapFinetune as a second pass after GEPA prompt optimization.

    Distills the GEPA-optimized prompt into a finetuned student model
    for improved performance beyond prompt-only optimization.
    """
    from dspy.teleprompt import BootstrapFinetune

    print("\nRunning BootstrapFinetune second pass...")

    def finetune_metric(
        gold: dspy.Example, pred: dspy.Prediction, trace: Any = None
    ) -> float | bool:
        result = metric(gold, pred, trace)
        if trace is not None and result.score < 1.0:
            return False
        return result.score

    trainer = FlashpointTrainerProgram(detector)
    finetune_optimizer = BootstrapFinetune(metric=finetune_metric)

    finetuned_trainer = finetune_optimizer.compile(
        trainer,
        trainset=paired_train,
    )

    print("BootstrapFinetune complete.")
    return finetuned_trainer.detector


def _evaluate_single(
    detector: FlashpointDetector | TwoStageFlashpointDetector, idx: int, example: dspy.Example
) -> tuple[int, float | None, int | None, str | None]:
    """Evaluate a single example. Returns (idx, score, category, error_msg)."""
    try:
        pred = detector(context=example.context, message=example.message)
        score = flashpoint_metric(example, pred)
        expected_derailing = getattr(example, "will_derail", False)
        predicted_score = parse_derailment_score(pred.derailment_score)

        if expected_derailing and predicted_score >= 50:
            category = 0  # TP
        elif not expected_derailing and predicted_score >= 50:
            category = 1  # FP
        elif expected_derailing and predicted_score < 50:
            category = 2  # FN
        else:
            category = 3  # TN

        return (idx, score, category, None)
    except Exception as e:
        return (idx, None, None, str(e))


def evaluate_detector(
    detector: FlashpointDetector | TwoStageFlashpointDetector,
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


def _collect_scores(
    detector: FlashpointDetector | TwoStageFlashpointDetector,
    testset: list[dspy.Example],
    num_threads: int = 8,
) -> list[tuple[bool, int]]:
    """Collect (expected_derailing, predicted_score) pairs for ROC analysis."""
    results: list[tuple[bool, int]] = []

    def _score_single(ex):
        pred = detector(context=ex.context, message=ex.message)
        return (
            bool(getattr(ex, "will_derail", False)),
            parse_derailment_score(pred.derailment_score),
        )

    if num_threads <= 1:
        for ex in tqdm(testset, desc="Collecting scores", unit="ex"):
            results.append(_score_single(ex))
    else:
        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(_score_single, ex) for ex in testset]
            for future in tqdm(as_completed(futures), total=len(testset), desc="Collecting scores"):
                try:
                    results.append(future.result())
                except Exception as e:
                    tqdm.write(f"Error: {e}")

    return results


def evaluate_safety_at_audit_budget(
    detector: FlashpointDetector | TwoStageFlashpointDetector,
    testset: list[dspy.Example],
    fpr_levels: list[float] | None = None,
    num_threads: int = 8,
) -> dict:
    """Evaluate using ROC-style safety-at-audit-budget curves.

    For each FPR level, finds the threshold that achieves at most that
    false positive rate, then reports the true positive rate (safety)
    at that threshold.

    Args:
        detector: The flashpoint detector to evaluate
        testset: Test examples with will_derail labels
        fpr_levels: FPR budget levels to evaluate (default: 0.5%-5%)
        num_threads: Threads for parallel scoring

    Returns:
        Dict with per-FPR-level results and overall metrics
    """
    if fpr_levels is None:
        fpr_levels = [0.005, 0.01, 0.02, 0.03, 0.05]

    scores = _collect_scores(detector, testset, num_threads=num_threads)

    positives = [(s, label) for label, s in scores if label]
    negatives = [(s, label) for label, s in scores if not label]
    n_pos = len(positives)
    n_neg = len(negatives)

    if n_pos == 0 or n_neg == 0:
        return {"error": "Need both positive and negative examples", "fpr_levels": {}}

    neg_scores = sorted([s for s, _ in negatives], reverse=True)
    pos_scores = [s for s, _ in positives]

    results: dict[str, Any] = {"fpr_levels": {}, "n_positive": n_pos, "n_negative": n_neg}

    for fpr_budget in fpr_levels:
        max_fp = int(n_neg * fpr_budget)

        if max_fp >= len(neg_scores):
            threshold = 0
        elif max_fp == 0:
            threshold = neg_scores[0] + 1
        else:
            threshold = neg_scores[max_fp - 1]

        tp = sum(1 for s in pos_scores if s >= threshold)
        fp = sum(1 for s, _ in negatives if s >= threshold)
        tpr = tp / n_pos
        actual_fpr = fp / n_neg

        results["fpr_levels"][f"{fpr_budget:.1%}"] = {
            "threshold": threshold,
            "tpr_safety": tpr,
            "actual_fpr": actual_fpr,
            "true_positives": tp,
            "false_positives": fp,
        }

    return results


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


def print_safety_curves(safety_results: dict) -> None:
    """Print ROC-style safety-at-audit-budget results."""
    print("\n" + "=" * 50)
    print("SAFETY-AT-AUDIT-BUDGET CURVES")
    print("=" * 50)
    print(f"Positive examples: {safety_results['n_positive']}")
    print(f"Negative examples: {safety_results['n_negative']}")
    print()
    print(
        f"{'FPR Budget':>12} {'Threshold':>10} {'TPR (Safety)':>14} "
        f"{'Actual FPR':>12} {'TP':>6} {'FP':>6}"
    )
    print("-" * 65)

    for fpr_label, data in safety_results["fpr_levels"].items():
        print(
            f"{fpr_label:>12} {data['threshold']:>10} "
            f"{data['tpr_safety']:>14.2%} {data['actual_fpr']:>12.2%} "
            f"{data['true_positives']:>6} {data['false_positives']:>6}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Optimize flashpoint detection with GEPA comparative scoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run optimization with defaults
  uv run python scripts/flashpoints/optimize_prompt.py

  # Use a different model
  uv run python scripts/flashpoints/optimize_prompt.py --model openai/gpt-5.1

  # Heavy optimization with BootstrapFinetune
  uv run python scripts/flashpoints/optimize_prompt.py --auto heavy --finetune

  # Evaluate existing model without re-optimizing
  uv run python scripts/flashpoints/optimize_prompt.py --eval-only data/flashpoints/optimized_detector.json

  # ROC-style evaluation only
  uv run python scripts/flashpoints/optimize_prompt.py --eval-only data/flashpoints/optimized_detector.json --safety-curves
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
        help="LLM model for GEPA reflection (default: openai/gpt-5.2)",
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
    parser.add_argument(
        "--max-train",
        type=int,
        default=200,
        help="Maximum paired training examples to use (default: 200)",
    )
    parser.add_argument(
        "--max-dev",
        type=int,
        default=50,
        help="Maximum paired dev examples to use (default: 50)",
    )
    parser.add_argument(
        "--component-selector",
        default="round_robin",
        choices=["round_robin", "all"],
        help="GEPA component selection strategy (default: round_robin)",
    )
    parser.add_argument(
        "--proposer",
        default="default",
        choices=["default", "terse", "short"],
        help="Instruction proposer: default (GEPA built-in), terse (few sentences), or short (few paragraphs)",
    )
    parser.add_argument(
        "--two-stage",
        action="store_true",
        help="Use two-stage detector (context summarizer + scorer) for two GEPA components",
    )
    parser.add_argument(
        "--finetune",
        action="store_true",
        help="Run BootstrapFinetune as a second pass after GEPA optimization",
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Run BootstrapFewShot pre-pass to seed GEPA with high-quality demonstrations",
    )
    parser.add_argument(
        "--max-bootstrapped-demos",
        type=int,
        default=4,
        help="Max bootstrapped demonstrations per predictor (default: 4)",
    )
    parser.add_argument(
        "--max-labeled-demos",
        type=int,
        default=4,
        help="Max labeled demonstrations per predictor (default: 4)",
    )
    parser.add_argument(
        "--safety-curves",
        action="store_true",
        help="Evaluate with ROC-style safety-at-audit-budget curves",
    )
    parser.add_argument(
        "--fpr-levels",
        type=float,
        nargs="+",
        default=None,
        help="FPR budget levels for safety curves (default: 0.005 0.01 0.02 0.03 0.05)",
    )

    args = parser.parse_args()

    if args.eval_only:
        lm = dspy.LM(args.model)
        dspy.configure(lm=lm)
        print(f"Loading existing model from {args.eval_only}...")
        detector = TwoStageFlashpointDetector() if args.two_stage else FlashpointDetector()
        detector.load(str(args.eval_only))
        print("Model loaded successfully.")
    else:
        detector = optimize_flashpoint_detector(
            model=args.model,
            auto=args.auto,
            output_path=args.output,
            reflection_model=args.reflection_model,
            max_train=args.max_train,
            max_dev=args.max_dev,
            log_dir=args.log_dir,
            reflection_minibatch_size=args.reflection_minibatch_size,
            num_threads=args.num_threads,
            finetune=args.finetune,
            component_selector=args.component_selector,
            proposer=args.proposer,
            two_stage=args.two_stage,
            bootstrap=args.bootstrap,
            max_bootstrapped_demos=args.max_bootstrapped_demos,
            max_labeled_demos=args.max_labeled_demos,
        )

    _, _, testset = load_flashpoint_datasets()
    testset = testset[: args.max_test]

    print(f"\nEvaluating on {len(testset)} test examples ({args.num_eval_threads} threads)...")
    metrics = evaluate_detector(
        detector, testset, verbose=args.verbose, num_threads=args.num_eval_threads
    )
    print_metrics(metrics)

    if args.safety_curves:
        print("\nRunning safety-at-audit-budget evaluation...")
        safety_results = evaluate_safety_at_audit_budget(
            detector,
            testset,
            fpr_levels=args.fpr_levels,
            num_threads=args.num_eval_threads,
        )
        if "error" in safety_results:
            print(f"\nSafety curve error: {safety_results['error']}")
        else:
            print_safety_curves(safety_results)

    error_rate_threshold = 0.05
    if metrics["error_rate"] > error_rate_threshold:
        print(
            f"\n*** FAILED: Error rate {metrics['error_rate']:.1%} "
            f"> {error_rate_threshold:.0%} threshold ***"
        )
        print("This indicates infrastructure issues (API rate limiting, model errors, etc.)")
        return 2

    return 0 if metrics["f1"] >= 0.75 else 1


if __name__ == "__main__":
    sys.exit(main())
