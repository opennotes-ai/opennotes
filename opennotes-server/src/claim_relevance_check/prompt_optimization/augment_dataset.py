"""LLM-guided dataset augmentation for relevance check training.

This script helps generate candidate training examples using an LLM,
with optional interactive review for human approval.
"""

import json
import os
import sys
from pathlib import Path

import litellm
import yaml

from src.claim_relevance_check.prompt_optimization.dataset import (
    DEFAULT_DATASET_PATH,
    RelevanceExample,
    load_examples_from_yaml,
    validate_dataset,
)


def setup_openai_environment() -> str:
    """Set up OpenAI environment for litellm."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    api_key = api_key.strip().strip("'\"")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    os.environ["OPENAI_API_KEY"] = api_key
    if "OPENAI_API_BASE" in os.environ:
        del os.environ["OPENAI_API_BASE"]
    return api_key


AUGMENTATION_PROMPT = """You are helping create training data for a claim relevance classifier.

Given a user message and a fact-check article, generate a training example that demonstrates whether the fact-check is RELEVANT to the message.

IMPORTANT DISTINCTIONS:
- FALSE POSITIVE (is_relevant: false): The message is a vague mention, question, or name drop - NOT a specific claim
  Examples: "what about biden", "something about vaccines", "or trump"

- TRUE POSITIVE (is_relevant: true): The message contains a SPECIFIC, VERIFIABLE CLAIM that the fact-check addresses
  Examples: "Biden was a Confederate soldier", "vaccines cause autism", "Trump said to inject bleach"

Generate a {example_type} example.

{context}

Respond with JSON only:
{{
  "example_id": "{example_id}",
  "message": "the user message",
  "fact_check_title": "title of the fact-check",
  "fact_check_content": "summary of the fact-check (1-2 sentences)",
  "is_relevant": {is_relevant},
  "reasoning": "explanation of why this is or isn't relevant (2-3 sentences)"
}}"""


def generate_example_with_llm(
    example_type: str,
    example_id: str,
    context: str = "",
    model: str = "openai/gpt-5-mini",
) -> dict | None:
    """Generate a single training example using an LLM.

    Args:
        example_type: "false_positive" or "true_positive"
        example_id: ID for the new example (e.g., "fp-006")
        context: Optional context to guide generation
        model: LLM model to use

    Returns:
        Generated example dict or None if failed
    """

    is_relevant = example_type == "true_positive"
    type_label = "TRUE POSITIVE" if is_relevant else "FALSE POSITIVE"

    prompt = AUGMENTATION_PROMPT.format(
        example_type=type_label,
        example_id=example_id,
        is_relevant=str(is_relevant).lower(),
        context=context
        if context
        else "Create a realistic example based on current events or common misinformation.",
    )

    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content  # type: ignore[union-attr]
        if content is None:
            return None
        return json.loads(content)
    except Exception as e:
        print(f"Error generating example: {e}")
        return None


def interactive_review(example: dict) -> str:
    """Present an example for interactive review.

    Args:
        example: Generated example dict

    Returns:
        "accept", "reject", or "edit"
    """
    print("\n" + "=" * 60)
    print("GENERATED EXAMPLE")
    print("=" * 60)
    print(f"\nID: {example.get('example_id', 'unknown')}")
    print(f'\nMessage: "{example.get("message", "")}"')
    print(f"\nFact-check: {example.get('fact_check_title', '')}")
    print(f"Content: {example.get('fact_check_content', '')[:200]}...")
    print(f"\nIs Relevant: {example.get('is_relevant', False)}")
    print(f"\nReasoning: {example.get('reasoning', '')}")
    print("\n" + "-" * 60)

    while True:
        choice = input("\n[A]ccept / [R]eject / [E]dit / [Q]uit? ").strip().lower()
        if choice in ("a", "accept"):
            return "accept"
        if choice in ("r", "reject"):
            return "reject"
        if choice in ("e", "edit"):
            return "edit"
        if choice in ("q", "quit"):
            return "quit"
        print("Invalid choice. Enter A, R, E, or Q.")


def edit_example(example: dict) -> dict:
    """Allow user to edit an example interactively."""
    print("\nEditing example. Press Enter to keep current value.\n")

    new_message = input(f"Message [{example.get('message', '')}]: ").strip()
    if new_message:
        example["message"] = new_message

    new_title = input(f"Fact-check title [{example.get('fact_check_title', '')}]: ").strip()
    if new_title:
        example["fact_check_title"] = new_title

    new_content = input(
        f"Fact-check content [{example.get('fact_check_content', '')[:50]}...]: "
    ).strip()
    if new_content:
        example["fact_check_content"] = new_content

    relevant_str = (
        input(f"Is relevant [{example.get('is_relevant', False)}] (true/false): ").strip().lower()
    )
    if relevant_str in ("true", "false"):
        example["is_relevant"] = relevant_str == "true"

    new_reasoning = input(f"Reasoning [{example.get('reasoning', '')[:50]}...]: ").strip()
    if new_reasoning:
        example["reasoning"] = new_reasoning

    return example


def append_to_dataset(example: dict, dataset_path: Path) -> None:
    """Append an example to the YAML dataset file."""
    with dataset_path.open() as f:
        data = yaml.safe_load(f)

    if "examples" not in data:
        data["examples"] = []

    data["examples"].append(example)

    with dataset_path.open("w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"✓ Added {example['example_id']} to {dataset_path}")


def get_next_example_id(examples: list[RelevanceExample], is_positive: bool) -> str:
    """Generate the next example ID based on existing examples."""
    prefix = "tp" if is_positive else "fp"
    existing_ids = [
        int(ex.example_id.split("-")[1]) for ex in examples if ex.example_id.startswith(prefix)
    ]
    next_num = max(existing_ids, default=0) + 1
    return f"{prefix}-{next_num:03d}"


def augment_dataset(
    count: int = 5,
    balance: bool = True,
    interactive: bool = True,
    context: str = "",
    model: str = "openai/gpt-5-mini",
    dataset_path: Path | None = None,
) -> int:
    """Generate candidate examples and optionally add to dataset.

    Args:
        count: Number of examples to generate
        balance: If True, generate equal TP and FP examples
        interactive: If True, prompt for review of each example
        context: Optional context to guide generation
        model: LLM model to use
        dataset_path: Path to dataset file

    Returns:
        Number of examples added
    """
    setup_openai_environment()

    path = dataset_path or DEFAULT_DATASET_PATH
    existing = load_examples_from_yaml(path)
    validation = validate_dataset(existing)

    print(
        f"\nCurrent dataset: {validation['total']} examples "
        f"({validation['true_positives']} TP, {validation['false_positives']} FP)"
    )

    if balance:
        n_fp = count // 2
        n_tp = count - n_fp
        if validation["true_positives"] < validation["false_positives"]:
            n_tp, n_fp = n_fp, n_tp
        example_types = ["false_positive"] * n_fp + ["true_positive"] * n_tp
    else:
        example_types = ["false_positive" if i % 2 == 0 else "true_positive" for i in range(count)]

    added = 0

    for i, example_type in enumerate(example_types, 1):
        is_positive = example_type == "true_positive"
        example_id = get_next_example_id(existing, is_positive)

        print(f"\n[{i}/{count}] Generating {example_type} example...")

        example = generate_example_with_llm(
            example_type=example_type,
            example_id=example_id,
            context=context,
            model=model,
        )

        if not example:
            print("Failed to generate example, skipping.")
            continue

        if interactive:
            while True:
                action = interactive_review(example)
                if action == "accept":
                    append_to_dataset(example, path)
                    existing.append(RelevanceExample(**example))
                    added += 1
                    break
                if action == "reject":
                    print("Example rejected.")
                    break
                if action == "edit":
                    example = edit_example(example)
                if action == "quit":
                    print(f"\nQuitting. Added {added} examples.")
                    return added
        else:
            append_to_dataset(example, path)
            existing.append(RelevanceExample(**example))
            added += 1
            print(f'  Added: {example["example_id"]} - "{example["message"][:40]}..."')

    print(f"\n✓ Added {added} examples to dataset")
    return added


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate candidate training examples using LLM")
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of examples to generate (default: 5)",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Skip interactive review (auto-accept all)",
    )
    parser.add_argument(
        "--no-balance",
        action="store_true",
        help="Don't balance TP/FP examples",
    )
    parser.add_argument(
        "--context",
        type=str,
        default="",
        help="Context to guide example generation",
    )
    parser.add_argument(
        "--model",
        default="openai/gpt-5-mini",
        help="LLM model to use",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to dataset file (default: examples.yaml)",
    )

    args = parser.parse_args()

    if args.no_interactive:
        print("⚠️  Running in non-interactive mode. All examples will be auto-accepted.")
        confirm = input("Continue? [y/N] ").strip().lower()
        if confirm != "y":
            sys.exit(0)

    augment_dataset(
        count=args.count,
        balance=not args.no_balance,
        interactive=not args.no_interactive,
        context=args.context,
        model=args.model,
        dataset_path=args.dataset,
    )
