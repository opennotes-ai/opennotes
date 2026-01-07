"""Compare current prompts with optimized module and update if better."""

import json
import logging
from pathlib import Path

import dspy

from src.claim_relevance_check.prompt_optimization.dataset import get_train_test_split
from src.claim_relevance_check.prompt_optimization.evaluate import evaluate_model
from src.claim_relevance_check.prompt_optimization.optimize import (
    DEFAULT_TEST_RATIO,
    create_relevance_module,
    setup_openai_environment,
)

logger = logging.getLogger(__name__)


def evaluate_current_prompts(
    testset: list[dspy.Example],
    model: str = "openai/gpt-5-mini",
    dataset_path: Path | None = None,
) -> dict:
    """Evaluate the current prompts.py approach on test data.

    This uses the DSPy module without any demos to simulate
    the baseline behavior.

    Args:
        testset: Test examples to evaluate on
        model: LLM model to use for evaluation
        dataset_path: Optional path to dataset file (for consistency with API)
    """
    _ = dataset_path
    api_key = setup_openai_environment()
    dspy.configure(lm=dspy.LM(model, api_key=api_key))

    module = create_relevance_module()
    return evaluate_model(module, testset)


def evaluate_optimized_module(
    testset: list[dspy.Example],
    module_path: Path,
    model: str = "openai/gpt-5-mini",
    dataset_path: Path | None = None,
) -> dict:
    """Evaluate the optimized module on test data.

    Args:
        testset: Test examples to evaluate on
        module_path: Path to the optimized module JSON
        model: LLM model to use for evaluation
        dataset_path: Optional path to dataset file (for consistency with API)
    """
    _ = dataset_path
    api_key = setup_openai_environment()
    dspy.configure(lm=dspy.LM(model, api_key=api_key))

    module = create_relevance_module()
    module.load(str(module_path))
    return evaluate_model(module, testset)


def format_metrics(results: dict) -> str:
    """Format evaluation results for display."""
    return (
        f"Accuracy: {results['accuracy']:.1%}, "
        f"Precision: {results['precision']:.1%}, "
        f"Recall: {results['recall']:.1%}, "
        f"F1: {results['f1']:.1%}"
    )


def generate_prompts_py(module_path: Path, output_path: Path) -> None:
    """Generate a new prompts.py from the optimized module."""
    with module_path.open() as f:
        data = json.load(f)

    if "predict" not in data:
        logger.warning(
            "Module JSON missing 'predict' key at %s. "
            "Expected structure: {predict: {demos: [...], signature: {instructions: ...}}}",
            module_path,
        )
    predict_data = data.get("predict", {})
    if predict_data and "demos" not in predict_data:
        logger.warning("Module JSON missing 'demos' key in 'predict' section")
    if predict_data and "signature" not in predict_data:
        logger.warning("Module JSON missing 'signature' key in 'predict' section")

    demos = predict_data.get("demos", [])
    instructions = predict_data.get("signature", {}).get("instructions", "")

    # Build the few-shot examples section
    examples_text = []
    for i, demo in enumerate(demos, 1):
        is_relevant = demo.get("is_relevant", False)
        label = "RELEVANT" if is_relevant else "NOT RELEVANT"
        reasoning = demo.get("reasoning", "")
        truncated_reasoning = reasoning[:100] + "..." if len(reasoning) > 100 else reasoning
        examples_text.append(f"""
Example {i} - {label}:
Message: "{demo.get("message", "")}"
Fact-check: "{demo.get("fact_check_title", "")}"
Result: {{"is_relevant": {str(is_relevant).lower()}, "reasoning": "{truncated_reasoning}"}}""")

    examples_section = "\n".join(examples_text)

    # Generate the new prompts.py content
    content = f'''"""Optimized prompts for relevance checking.

AUTO-GENERATED from optimized_relevance_module.json
Do not edit manually - run compare_and_update.py to regenerate.
"""

OPTIMIZED_SYSTEM_PROMPT = """{instructions}

FEW-SHOT EXAMPLES:
{examples_section}

Respond ONLY with JSON: {{"is_relevant": true/false, "reasoning": "brief explanation"}}"""


OPTIMIZED_USER_PROMPT_TEMPLATE = """Analyze this message for relevance to the fact-check:

MESSAGE: {{message}}

FACT-CHECK TITLE: {{fact_check_title}}
FACT-CHECK CONTENT: {{fact_check_content}}

STEP-BY-STEP ANALYSIS:
1. CLAIM DETECTION: Does the message contain a SPECIFIC, VERIFIABLE CLAIM (not just a topic mention, question, or name drop)?
2. RELEVANCE CHECK: If a claim exists, does this fact-check ADDRESS that specific claim?

IMPORTANT: If Step 1 is NO (no specific claim found), immediately return is_relevant: false.

Your JSON response:"""


def get_optimized_prompts(
    message: str,
    fact_check_title: str,
    fact_check_content: str,
    source_url: str | None = None,
) -> tuple[str, str]:
    """Get optimized system and user prompts for relevance checking.

    Args:
        message: The user's original message
        fact_check_title: Title of the matched fact-check
        fact_check_content: Content/summary of the fact-check
        source_url: Optional source URL

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    content_with_source = fact_check_content
    if source_url:
        content_with_source = fact_check_content + "\\nSource: " + source_url

    user_prompt = OPTIMIZED_USER_PROMPT_TEMPLATE.format(
        message=message,
        fact_check_title=fact_check_title,
        fact_check_content=content_with_source,
    )

    return OPTIMIZED_SYSTEM_PROMPT, user_prompt
'''

    with output_path.open("w") as f:
        f.write(content)

    print(f"Generated new prompts at {output_path}")


def compare_and_update(
    module_path: Path = Path("optimized_relevance_module.json"),
    prompts_path: Path = Path("src/claim_relevance_check/prompt_optimization/prompts.py"),
    model: str = "openai/gpt-5-mini",
    force: bool = False,
    test_ratio: float = DEFAULT_TEST_RATIO,
    dry_run: bool = False,
    dataset_path: Path | None = None,
) -> bool:
    """Compare current prompts with optimized module and update if better.

    Args:
        module_path: Path to the optimized module JSON
        prompts_path: Path to prompts.py to update
        model: LLM model to use for evaluation
        force: If True, update even if not better
        test_ratio: Ratio of data to use for testing
        dry_run: If True, show what would change without modifying files
        dataset_path: Optional path to dataset file (YAML or JSON)

    Returns:
        True if prompts were updated (or would be in dry-run mode), False otherwise
    """
    if dry_run:
        print("🔍 DRY RUN MODE - No files will be modified\n")

    if not module_path.exists():
        print(f"Error: {module_path} not found. Run optimization first.")
        return False

    print(f"Using {test_ratio:.0%} of data for testing...")
    _, testset = get_train_test_split(test_ratio=test_ratio, dataset_path=dataset_path)

    if len(testset) < 2:
        print("Warning: Very small test set. Results may not be reliable.")

    print(f"\nEvaluating on {len(testset)} test examples...")

    print("\n1. Evaluating CURRENT prompts (no demos)...")
    current_results = evaluate_current_prompts(testset, model, dataset_path=dataset_path)
    print(f"   Current: {format_metrics(current_results)}")

    print("\n2. Evaluating OPTIMIZED module...")
    optimized_results = evaluate_optimized_module(
        testset, module_path, model, dataset_path=dataset_path
    )
    print(f"   Optimized: {format_metrics(optimized_results)}")

    # Compare using F1 as primary metric
    current_f1 = current_results["f1"]
    optimized_f1 = optimized_results["f1"]
    improvement = optimized_f1 - current_f1

    print("\n3. Comparison:")
    print(f"   F1 improvement: {improvement:+.1%}")

    if improvement > 0 or force:
        if improvement > 0:
            print(f"\n✓ Optimized prompts are BETTER by {improvement:.1%}")
        else:
            print("\n! Force updating despite no improvement")

        if dry_run:
            print(f"\n📋 Would update: {prompts_path}")
            print("   Run without --dry-run to apply changes.")
            return True

        generate_prompts_py(module_path, prompts_path)
        return True
    if improvement == 0:
        print("\n= No difference in F1 score. Keeping current prompts.")
        return False
    print(f"\n✗ Current prompts are BETTER by {-improvement:.1%}. Keeping current.")
    return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Compare current prompts with optimized module and update if better"
    )
    parser.add_argument(
        "--module",
        type=Path,
        default=Path("optimized_relevance_module.json"),
        help="Path to optimized module JSON",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=Path("src/claim_relevance_check/prompt_optimization/prompts.py"),
        help="Path to prompts.py",
    )
    parser.add_argument(
        "--model",
        default="openai/gpt-5-mini",
        help="LLM model to use for evaluation",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Update prompts even if not better",
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=DEFAULT_TEST_RATIO,
        help=f"Ratio of data to use for testing (default: {DEFAULT_TEST_RATIO})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying files",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to dataset file (YAML or JSON). Defaults to examples.yaml",
    )

    args = parser.parse_args()
    compare_and_update(
        module_path=args.module,
        prompts_path=args.prompts,
        model=args.model,
        force=args.force,
        test_ratio=args.test_ratio,
        dry_run=args.dry_run,
        dataset_path=args.dataset,
    )
