"""Optimization script for relevance check prompts using DSPy."""

import json
import os
from pathlib import Path

import dspy
from dspy.teleprompt import BootstrapFewShot, LabeledFewShot

from src.claim_relevance_check.prompt_optimization.dataset import get_train_test_split
from src.claim_relevance_check.prompt_optimization.evaluate import evaluate_model, relevance_metric
from src.claim_relevance_check.prompt_optimization.signature import RelevanceCheck


def setup_openai_environment() -> str:
    """Set up OpenAI environment for litellm.

    Cleans the API key and removes any OPENAI_API_BASE override
    (e.g., from VSCode/GitHub Copilot) to ensure requests go to OpenAI.

    Returns:
        The cleaned API key
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    # Strip whitespace and any quotes that might have been included
    api_key = api_key.strip().strip("'\"")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")

    # Set cleaned key back into environment for litellm's internal use
    os.environ["OPENAI_API_KEY"] = api_key

    # Remove OPENAI_API_BASE if set (e.g., from VSCode/GitHub Copilot)
    # to ensure requests go to the actual OpenAI API
    if "OPENAI_API_BASE" in os.environ:
        del os.environ["OPENAI_API_BASE"]

    return api_key


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
    optimizer = LabeledFewShot(k=k or len(trainset))
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
    model: str = "openai/o4-mini",
) -> tuple[dspy.Module, dict]:
    """Main optimization function.

    Args:
        method: Optimization method ('labeled' or 'bootstrap')
        model: LLM model to use

    Returns:
        Tuple of (optimized_module, evaluation_results)
    """
    api_key = setup_openai_environment()
    dspy.configure(lm=dspy.LM(model, api_key=api_key))

    trainset, testset = get_train_test_split(test_ratio=0.2)

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
            result["demos"].append(
                {
                    "message": demo.message,
                    "fact_check_title": demo.fact_check_title,
                    "fact_check_content": demo.fact_check_content[:200] + "...",
                    "is_relevant": demo.is_relevant,
                    "reasoning": demo.reasoning,
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
        default="openai/o4-mini",
        help="LLM model to use",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("optimized_relevance_module.json"),
        help="Output path for optimized module",
    )

    args = parser.parse_args()

    optimized, results = optimize_relevance_module(method=args.method, model=args.model)
    save_optimized_module(optimized, args.output)

    prompts = extract_prompts_from_module(optimized)
    print("\nExtracted prompts:")
    print(json.dumps(prompts, indent=2))
