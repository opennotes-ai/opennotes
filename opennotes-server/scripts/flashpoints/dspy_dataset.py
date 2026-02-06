"""DSPy dataset loader for flashpoint detection training."""

import json
import logging
from pathlib import Path

import dspy

logger = logging.getLogger(__name__)


def load_flashpoint_examples(jsonl_path: Path) -> list[dspy.Example]:
    """Load flashpoint examples from JSONL file into DSPy format.

    Args:
        jsonl_path: Path to the JSONL file

    Returns:
        List of dspy.Example objects with 'context', 'message', and 'will_derail' fields

    Raises:
        FileNotFoundError: If the JSONL file does not exist
    """
    if not jsonl_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {jsonl_path}")

    examples = []
    with jsonl_path.open() as f:
        for line_num, raw_line in enumerate(f, 1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                example = dspy.Example(
                    context=data["context"],
                    message=data["current_message"],
                    will_derail=data["will_derail"],
                ).with_inputs("context", "message")
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSON at %s line %d", jsonl_path, line_num)
                continue
            except KeyError as exc:
                logger.warning(
                    "Skipping record missing key %s at %s line %d",
                    exc,
                    jsonl_path,
                    line_num,
                )
                continue
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

    Raises:
        FileNotFoundError: If the data directory or any dataset file does not exist
    """
    if data_dir is None:
        data_dir = Path(__file__).parent.parent.parent / "data" / "flashpoints"

    if not data_dir.is_dir():
        raise FileNotFoundError(f"Dataset directory not found: {data_dir}")

    trainset = load_flashpoint_examples(data_dir / "flashpoints_train.jsonl")
    devset = load_flashpoint_examples(data_dir / "flashpoints_dev.jsonl")
    testset = load_flashpoint_examples(data_dir / "flashpoints_test.jsonl")

    return trainset, devset, testset


if __name__ == "__main__":
    train, dev, test = load_flashpoint_datasets()
    print(f"Loaded: {len(train)} train, {len(dev)} dev, {len(test)} test")
    if train:
        print(f"\nSample example:\n{train[0]}")
