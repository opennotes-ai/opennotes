"""Extract Conversations Gone Awry dataset for DSPy training.

Downloads the CGA-CMV corpus from ConvoKit and transforms it into
DSPy-compatible training examples for conversation flashpoint detection.
"""

import json
import random
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from convokit import Corpus


class FlashpointExample(TypedDict):
    """A single training example for flashpoint detection."""

    conversation_id: str
    context: str
    current_message: str
    will_derail: bool
    derail_point: int | None


def load_cga_corpus() -> "Corpus":
    """Download and load the CGA-CMV corpus."""
    from convokit import Corpus, download

    corpus_path = download("conversations-gone-awry-cmv-corpus")
    return Corpus(filename=corpus_path)


def extract_examples(
    corpus: "Corpus", max_context_turns: int = 5, seed: int = 42
) -> list[FlashpointExample]:
    """Extract training examples from the corpus.

    For each conversation:
    - If it derailed: create examples at various points before derailment
    - If it didn't derail: sample points as negative examples

    Args:
        corpus: The loaded ConvoKit corpus
        max_context_turns: Maximum number of prior turns to include as context

    Returns:
        List of FlashpointExample dictionaries
    """
    rng = random.Random(seed)
    examples: list[FlashpointExample] = []

    for convo in corpus.iter_conversations():
        utterances = list(convo.iter_utterances())
        if len(utterances) < 3:
            continue

        derailed = convo.meta.get("annotation", {}).get("derail", False)
        derail_idx = convo.meta.get("annotation", {}).get("derail_idx")

        if derailed and derail_idx is not None:
            sample_points = range(max(1, derail_idx - 3), derail_idx)
            for idx in sample_points:
                if idx >= len(utterances):
                    continue
                context_start = max(0, idx - max_context_turns)
                context_utts = utterances[context_start:idx]
                context = "\n".join(f"{u.speaker.id}: {u.text}" for u in context_utts)

                examples.append(
                    FlashpointExample(
                        conversation_id=convo.id,
                        context=context,
                        current_message=f"{utterances[idx].speaker.id}: {utterances[idx].text}",
                        will_derail=True,
                        derail_point=derail_idx,
                    )
                )
        elif len(utterances) > 3:
            sample_indices = rng.sample(range(1, len(utterances)), min(2, len(utterances) - 1))
            for idx in sample_indices:
                context_start = max(0, idx - max_context_turns)
                context_utts = utterances[context_start:idx]
                context = "\n".join(f"{u.speaker.id}: {u.text}" for u in context_utts)

                examples.append(
                    FlashpointExample(
                        conversation_id=convo.id,
                        context=context,
                        current_message=f"{utterances[idx].speaker.id}: {utterances[idx].text}",
                        will_derail=False,
                        derail_point=None,
                    )
                )

    return examples


def split_dataset(
    examples: list[FlashpointExample],
    train_ratio: float = 0.2,
    dev_ratio: float = 0.3,
    seed: int = 42,
) -> tuple[list[FlashpointExample], list[FlashpointExample], list[FlashpointExample]]:
    """Split examples into train/dev/test sets.

    Uses reversed allocation (20% train, 30% dev, 50% test) as recommended
    for DSPy prompt optimization to avoid overfitting.
    """
    rng = random.Random(seed)
    shuffled = examples.copy()
    rng.shuffle(shuffled)

    n = len(shuffled)
    train_end = int(n * train_ratio)
    dev_end = train_end + int(n * dev_ratio)

    return shuffled[:train_end], shuffled[train_end:dev_end], shuffled[dev_end:]


def save_datasets(
    train: list[FlashpointExample],
    dev: list[FlashpointExample],
    test: list[FlashpointExample],
    output_dir: Path,
) -> None:
    """Save datasets as JSONL files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, data in [("train", train), ("dev", dev), ("test", test)]:
        path = output_dir / f"flashpoints_{name}.jsonl"
        with path.open("w") as f:
            for example in data:
                f.write(json.dumps(example) + "\n")
        print(f"Saved {len(data)} examples to {path}")


def main() -> None:
    """Main extraction pipeline."""
    print("Loading CGA-CMV corpus...")
    corpus = load_cga_corpus()

    print(f"Corpus contains {len(list(corpus.iter_conversations()))} conversations")

    print("Extracting examples...")
    examples = extract_examples(corpus)
    print(f"Extracted {len(examples)} total examples")

    if not examples:
        print("WARNING: No examples extracted. Check corpus data and network connectivity.")
        return

    positive = sum(1 for e in examples if e["will_derail"])
    print(
        f"Balance: {positive} positive ({positive / len(examples) * 100:.1f}%), "
        f"{len(examples) - positive} negative ({(len(examples) - positive) / len(examples) * 100:.1f}%)"
    )

    print("Splitting dataset...")
    train, dev, test = split_dataset(examples)
    print(f"Split: {len(train)} train, {len(dev)} dev, {len(test)} test")

    output_dir = Path(__file__).parent.parent.parent / "data" / "flashpoints"
    save_datasets(train, dev, test, output_dir)
    print(f"\nDatasets saved to {output_dir}")


if __name__ == "__main__":
    main()
