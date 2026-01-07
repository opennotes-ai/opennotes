"""Optimization script for relevance check prompts using DSPy."""

import json
from pathlib import Path

import dspy
from dspy.teleprompt import BootstrapFewShot, LabeledFewShot

from src.claim_relevance_check.prompt_optimization.dataset import get_train_test_split
from src.claim_relevance_check.prompt_optimization.evaluate import evaluate_model, relevance_metric
from src.claim_relevance_check.prompt_optimization.signature import RelevanceCheck
from src.claim_relevance_check.prompt_optimization.utils import setup_openai_environment

DEFAULT_TEST_RATIO = 0.3


def create_relevance_module() -> dspy.ChainOfThought:
    """Create a ChainOfThought module for relevance checking."""
    return dspy.ChainOfThought(RelevanceCheck)


def optimize_with_labeled_fewshot(
    trainset: list[dspy.Example],
    k: int | None = None,
) -> dspy.Module:
    """Optimize using LabeledFewShot - simplest approach for small datasets.

    Args:
        trainset: Training examples
        k: Number of examples to include (default: all)

    Returns:
        Optimized module with few-shot examples
    """
    module = create_relevance_module()
    optimizer = LabeledFewShot(k=len(trainset) if k is None else k)
    return optimizer.compile(module, trainset=trainset)


def optimize_with_bootstrap(
    trainset: list[dspy.Example],
    max_bootstrapped_demos: int = 4,
    max_labeled_demos: int = 4,
    max_rounds: int = 1,
) -> dspy.Module:
    """Optimize using BootstrapFewShot - self-generates additional demonstrations.

    Args:
        trainset: Training examples
        max_bootstrapped_demos: Max self-generated demonstrations
        max_labeled_demos: Max labeled demonstrations to include
        max_rounds: Number of optimization rounds

    Returns:
        Optimized module
    """
    module = create_relevance_module()
    optimizer = BootstrapFewShot(
        metric=relevance_metric,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_labeled_demos,
        max_rounds=max_rounds,
    )
    return optimizer.compile(module, trainset=trainset)


def optimize_relevance_module(
    method: str = "bootstrap",
    model: str = "openai/gpt-5-mini",
    dataset_path: Path | None = None,
) -> tuple[dspy.Module, dict]:
    """Main optimization function.

    Args:
        method: Optimization method ('labeled' or 'bootstrap')
        model: LLM model to use
        dataset_path: Optional path to dataset file (YAML or JSON)

    Returns:
        Tuple of (optimized_module, evaluation_results)
    """
    api_key = setup_openai_environment()
    dspy.configure(lm=dspy.LM(model, api_key=api_key))

    trainset, testset = get_train_test_split(
        test_ratio=DEFAULT_TEST_RATIO, dataset_path=dataset_path
    )

    print(f"Training set: {len(trainset)} examples")
    print(f"Test set: {len(testset)} examples")

    if method == "labeled":
        optimized = optimize_with_labeled_fewshot(trainset)
    else:
        optimized = optimize_with_bootstrap(trainset)

    print("\nEvaluating on test set...")
    eval_results = evaluate_model(optimized, testset)

    print("\nResults:")
    print(f"  Accuracy: {eval_results['accuracy']:.2%}")
    print(f"  Precision: {eval_results['precision']:.2%}")
    print(f"  Recall: {eval_results['recall']:.2%}")
    print(f"  F1: {eval_results['f1']:.2%}")

    return optimized, eval_results


def save_optimized_module(module: dspy.Module, path: Path) -> None:
    """Save an optimized module to disk."""
    module.save(str(path))
    print(f"Saved optimized module to {path}")


def load_optimized_module(path: Path) -> dspy.Module:
    """Load an optimized module from disk."""
    module = create_relevance_module()
    module.load(str(path))
    return module


def extract_prompts_from_module(module: dspy.Module) -> dict:
    """Extract the optimized prompts from a compiled module.

    This extracts the system prompt (signature docstring) and
    few-shot examples that can be used in the production code.
    """
    result: dict = {
        "signature_docstring": RelevanceCheck.__doc__,
        "demos": [],
    }

    demos = getattr(module, "demos", None)
    if demos is not None and isinstance(demos, list):
        for demo in demos:
            fact_check_content = demo.fact_check_content or ""
            truncated_content = (
                fact_check_content[:200] + "..."
                if len(fact_check_content) > 200
                else fact_check_content
            )
            result["demos"].append(
                {
                    "message": demo.message or "",
                    "fact_check_title": demo.fact_check_title or "",
                    "fact_check_content": truncated_content,
                    "is_relevant": demo.is_relevant,
                    "reasoning": demo.reasoning or "",
                }
            )

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Optimize relevance check prompts")
    parser.add_argument(
        "--method",
        choices=["labeled", "bootstrap"],
        default="bootstrap",
        help="Optimization method",
    )
    parser.add_argument(
        "--model",
        default="openai/gpt-5-mini",
        help="LLM model to use",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("optimized_relevance_module.json"),
        help="Output path for optimized module",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to dataset file (YAML or JSON). Defaults to examples.yaml",
    )

    args = parser.parse_args()

    optimized, results = optimize_relevance_module(
        method=args.method,
        model=args.model,
        dataset_path=args.dataset,
    )
    save_optimized_module(optimized, args.output)

    prompts = extract_prompts_from_module(optimized)
    print("\nExtracted prompts:")
    print(json.dumps(prompts, indent=2))
