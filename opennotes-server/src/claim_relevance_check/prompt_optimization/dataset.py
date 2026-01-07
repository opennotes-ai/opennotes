"""Dataset loading utilities for relevance check training."""

import json
import warnings
from dataclasses import dataclass
from pathlib import Path

import dspy
import yaml


@dataclass
class RelevanceExample:
    """A labeled example for relevance checking."""

    example_id: str
    message: str
    fact_check_title: str
    fact_check_content: str
    is_relevant: bool
    reasoning: str

    def to_dspy_example(self) -> dspy.Example:
        """Convert to a DSPy Example with proper input/output field marking."""
        return dspy.Example(
            message=self.message,
            fact_check_title=self.fact_check_title,
            fact_check_content=self.fact_check_content,
            is_relevant=self.is_relevant,
            reasoning=self.reasoning,
        ).with_inputs("message", "fact_check_title", "fact_check_content")


DEFAULT_DATASET_PATH = Path(__file__).parent / "examples.yaml"


def load_examples_from_yaml(yaml_path: Path | None = None) -> list[RelevanceExample]:
    """Load examples from a YAML file.

    Args:
        yaml_path: Path to YAML file. Defaults to examples.yaml in this directory.

    Returns:
        List of RelevanceExample objects
    """
    path = yaml_path or DEFAULT_DATASET_PATH
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    with path.open() as f:
        data = yaml.safe_load(f)

    examples_data = data.get("examples", [])
    if not examples_data:
        raise ValueError(f"No examples found in {path}")

    examples = []
    for item in examples_data:
        ex = RelevanceExample(
            example_id=item.get("example_id", "unknown"),
            message=item["message"],
            fact_check_title=item["fact_check_title"],
            fact_check_content=item["fact_check_content"][:500],
            is_relevant=item["is_relevant"],
            reasoning=item["reasoning"],
        )
        examples.append(ex)

    return examples


def load_examples_from_json(json_path: Path) -> list[RelevanceExample]:
    """Load examples from a JSON file.

    Args:
        json_path: Path to JSON file

    Returns:
        List of RelevanceExample objects
    """
    with json_path.open() as f:
        data = json.load(f)

    examples_data = data if isinstance(data, list) else data.get("examples", [data])

    examples = []
    for item in examples_data:
        if "original_message" in item:
            ex = RelevanceExample(
                example_id=item.get("example_id", "unknown"),
                message=item["original_message"],
                fact_check_title=item["fact_check"]["title"],
                fact_check_content=item["fact_check"]["content"][:500],
                is_relevant=item["expected_is_relevant"],
                reasoning=item["expected_reasoning"],
            )
        else:
            ex = RelevanceExample(
                example_id=item.get("example_id", "unknown"),
                message=item["message"],
                fact_check_title=item["fact_check_title"],
                fact_check_content=item["fact_check_content"][:500],
                is_relevant=item["is_relevant"],
                reasoning=item["reasoning"],
            )
        examples.append(ex)

    return examples


def validate_dataset(examples: list[RelevanceExample]) -> dict:
    """Validate dataset balance and quality.

    Args:
        examples: List of examples to validate

    Returns:
        Validation results dict with counts and warnings
    """
    n_total = len(examples)
    n_positive = sum(1 for ex in examples if ex.is_relevant)
    n_negative = n_total - n_positive

    results = {
        "total": n_total,
        "true_positives": n_positive,
        "false_positives": n_negative,
        "ratio": n_positive / n_total if n_total > 0 else 0,
        "warnings": [],
    }

    if n_total < 6:
        results["warnings"].append(
            f"Very small dataset ({n_total} examples). Recommend at least 10."
        )

    if n_positive == 0 or n_negative == 0:
        results["warnings"].append("Dataset has no examples for one class. Both TP and FP needed.")
    elif abs(n_positive - n_negative) / n_total > 0.4:
        results["warnings"].append(
            f"Dataset is imbalanced: {n_positive} TP vs {n_negative} FP. Consider adding more examples."
        )

    return results


def load_training_examples(
    dataset_path: Path | None = None,
    validate: bool = True,
) -> list[dspy.Example]:
    """Load all training examples as DSPy Examples.

    Args:
        dataset_path: Optional path to YAML/JSON file. Defaults to examples.yaml.
        validate: If True, validate and warn about dataset issues.

    Returns:
        List of DSPy Example objects
    """
    path = DEFAULT_DATASET_PATH if dataset_path is None else dataset_path

    if path.suffix in (".yaml", ".yml"):
        examples = load_examples_from_yaml(path)
    elif path.suffix == ".json":
        examples = load_examples_from_json(path)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}. Use .yaml or .json")

    if validate:
        validation = validate_dataset(examples)
        for warning in validation["warnings"]:
            warnings.warn(warning, stacklevel=2)
        print(
            f"Dataset: {validation['total']} examples ({validation['true_positives']} TP, {validation['false_positives']} FP)"
        )

    return [ex.to_dspy_example() for ex in examples]


def get_train_test_split(
    test_ratio: float = 0.2,
    dataset_path: Path | None = None,
) -> tuple[list[dspy.Example], list[dspy.Example]]:
    """Split examples into train and test sets.

    Args:
        test_ratio: Ratio of examples to use for testing
        dataset_path: Optional path to dataset file

    Returns:
        Tuple of (train_examples, test_examples)
    """
    examples = load_training_examples(dataset_path)
    n_test = max(1, int(len(examples) * test_ratio))
    return examples[:-n_test], examples[-n_test:]
