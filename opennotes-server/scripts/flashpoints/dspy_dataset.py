"""DSPy dataset loader for flashpoint detection training."""

import json
from pathlib import Path

import dspy


def load_flashpoint_examples(jsonl_path: Path) -> list[dspy.Example]:
    """Load flashpoint examples from JSONL file into DSPy format.

    Args:
        jsonl_path: Path to the JSONL file

    Returns:
        List of dspy.Example objects with 'context', 'message', and 'will_derail' fields
    """
    examples = []
    with jsonl_path.open() as f:
        for line in f:
            data = json.loads(line)
            example = dspy.Example(
                context=data["context"],
                message=data["current_message"],
                will_derail=data["will_derail"],
            ).with_inputs("context", "message")
            examples.append(example)
    return examples


def load_flashpoint_datasets(
    data_dir: Path | None = None,
) -> tuple[list[dspy.Example], list[dspy.Example], list[dspy.Example]]:
    """Load train/dev/test datasets for flashpoint detection.

    Args:
        data_dir: Directory containing the JSONL files. Defaults to data/flashpoints/

    Returns:
        Tuple of (trainset, devset, testset) as lists of dspy.Example
    """
    if data_dir is None:
        data_dir = Path(__file__).parent.parent.parent / "data" / "flashpoints"

    trainset = load_flashpoint_examples(data_dir / "flashpoints_train.jsonl")
    devset = load_flashpoint_examples(data_dir / "flashpoints_dev.jsonl")
    testset = load_flashpoint_examples(data_dir / "flashpoints_test.jsonl")

    return trainset, devset, testset


if __name__ == "__main__":
    train, dev, test = load_flashpoint_datasets()
    print(f"Loaded: {len(train)} train, {len(dev)} dev, {len(test)} test")
    if train:
        print(f"\nSample example:\n{train[0]}")
