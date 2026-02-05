"""LLM-guided dataset augmentation for relevance check training.

This script helps generate candidate training examples using an LLM,
with optional interactive review for human approval.
"""

import fcntl
import json
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any

import litellm
from ruamel.yaml import YAML

from src.claim_relevance_check.prompt_optimization.dataset import (
    DEFAULT_DATASET_PATH,
    RelevanceExample,
    load_examples_from_yaml,
    validate_dataset,
)
from src.claim_relevance_check.prompt_optimization.utils import (
    setup_openai_environment,
    truncate_utf8_safe,
)

REQUIRED_EXAMPLE_FIELDS = frozenset(
    {"example_id", "message", "fact_check_title", "fact_check_content", "is_relevant", "reasoning"}
)

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
) -> dict[str, Any] | None:
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
        content = response.choices[0].message.content  # type: ignore[reportAttributeAccessIssue]
        if content is None:
            return None
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Error parsing LLM response as JSON: {e}")
        return None
    except litellm.exceptions.APIError as e:
        print(f"LLM API error: {e}")
        return None
    except litellm.exceptions.AuthenticationError as e:
        print(f"LLM authentication error: {e}")
        return None


def validate_example_fields(example: dict[str, Any]) -> tuple[bool, str]:
    """Validate that an LLM-generated example has all required fields.

    Args:
        example: The example dict to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    missing_fields = REQUIRED_EXAMPLE_FIELDS - set(example.keys())
    if missing_fields:
        return False, f"Missing required fields: {', '.join(sorted(missing_fields))}"

    if not isinstance(example.get("is_relevant"), bool):
        return False, "Field 'is_relevant' must be a boolean"

    for field in ("message", "fact_check_title", "fact_check_content", "reasoning", "example_id"):
        if not isinstance(example.get(field), str):
            return False, f"Field '{field}' must be a string"
        if not example[field].strip():
            return False, f"Field '{field}' cannot be empty"

    return True, ""


def interactive_review(example: dict[str, Any]) -> str:
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
    content = example.get("fact_check_content", "")
    print(f"Content: {truncate_utf8_safe(content, 200)}")
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


def edit_example(example: dict[str, Any]) -> dict[str, Any]:
    """Allow user to edit an example interactively."""
    print("\nEditing example. Press Enter to keep current value.\n")

    new_message = input(f"Message [{example.get('message', '')}]: ").strip()
    if new_message:
        example["message"] = new_message

    new_title = input(f"Fact-check title [{example.get('fact_check_title', '')}]: ").strip()
    if new_title:
        example["fact_check_title"] = new_title

    content_preview = truncate_utf8_safe(example.get("fact_check_content", ""), 50)
    new_content = input(f"Fact-check content [{content_preview}]: ").strip()
    if new_content:
        example["fact_check_content"] = new_content

    relevant_str = (
        input(f"Is relevant [{example.get('is_relevant', False)}] (true/false): ").strip().lower()
    )
    if relevant_str in ("true", "false"):
        example["is_relevant"] = relevant_str == "true"

    reasoning_preview = truncate_utf8_safe(example.get("reasoning", ""), 50)
    new_reasoning = input(f"Reasoning [{reasoning_preview}]: ").strip()
    if new_reasoning:
        example["reasoning"] = new_reasoning

    return example


def append_to_dataset(example: dict[str, Any], dataset_path: Path) -> None:
    """Append an example to the YAML dataset file with file locking and atomic write.

    Uses file locking to prevent concurrent corruption and writes to a temp file
    first, then atomically renames to preserve data integrity.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.allow_unicode = True

    lock_path = dataset_path.with_suffix(".lock")

    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            with dataset_path.open() as f:
                data = yaml.load(f)

            if data is None:
                data = {}
            if "examples" not in data:
                data["examples"] = []

            data["examples"].append(example)

            fd, temp_path_str = tempfile.mkstemp(
                dir=dataset_path.parent,
                prefix=".tmp_dataset_",
                suffix=".yaml",
            )
            temp_path = Path(temp_path_str)
            try:
                with os.fdopen(fd, "w") as temp_file:
                    yaml.dump(data, temp_file)

                temp_path.rename(dataset_path)
            except Exception:
                if temp_path.exists():
                    temp_path.unlink()
                raise

            print(f"Added {example['example_id']} to {dataset_path}")
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def get_next_example_id(examples: list[RelevanceExample], is_positive: bool) -> str:
    """Generate the next example ID based on existing examples.

    Handles malformed IDs gracefully by skipping them with a warning.
    """
    prefix = "tp" if is_positive else "fp"
    existing_ids: list[int] = []

    for ex in examples:
        if not ex.example_id.startswith(prefix):
            continue
        parts = ex.example_id.split("-")
        if len(parts) != 2:
            warnings.warn(
                f"Skipping malformed example ID '{ex.example_id}': expected format '{prefix}-NNN'",
                stacklevel=2,
            )
            continue
        try:
            existing_ids.append(int(parts[1]))
        except ValueError:
            warnings.warn(
                f"Skipping malformed example ID '{ex.example_id}': "
                f"'{parts[1]}' is not a valid integer",
                stacklevel=2,
            )
            continue

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

        is_valid, error_msg = validate_example_fields(example)
        if not is_valid:
            print(f"Invalid example from LLM: {error_msg}. Skipping.")
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
            message_preview = truncate_utf8_safe(example["message"], 40)
            print(f'  Added: {example["example_id"]} - "{message_preview}"')

    print(f"\nAdded {added} examples to dataset")
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

    augment_dataset(
        count=args.count,
        balance=not args.no_balance,
        interactive=not args.no_interactive,
        context=args.context,
        model=args.model,
        dataset_path=args.dataset,
    )
