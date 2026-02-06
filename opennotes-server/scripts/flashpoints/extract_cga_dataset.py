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


class PairedFlashpointExample(TypedDict):
    """A paired/contrastive training example for comparative scoring.

    Each example pairs a derailing conversation snippet with a
    non-derailing one from the same corpus, enabling the GEPA
    optimizer to learn discriminative features via contrastive training.
    """

    derailing_context: str
    derailing_message: str
    derailing_conversation_id: str
    non_derailing_context: str
    non_derailing_message: str
    non_derailing_conversation_id: str


def load_cga_corpus() -> "Corpus":
    """Download and load the CGA-CMV corpus."""
    from convokit import Corpus, download

    corpus_path = download("conversations-gone-awry-cmv-corpus-large")
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

        if not derailed and not derail_idx:
            derailed = convo.meta.get("has_removed_comment", False)
            if derailed:
                derail_idx = len(utterances) - 1

        if derailed and derail_idx is not None:
            sample_range = range(max(1, derail_idx - 3), derail_idx)
            sample_points = (
                list(sample_range) if sample_range else [min(derail_idx, len(utterances) - 1)]
            )
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
        elif len(utterances) >= 3:
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


def create_paired_dataset(
    examples: list[FlashpointExample],
    seed: int = 42,
) -> list[PairedFlashpointExample]:
    """Create paired/contrastive examples from unpaired examples.

    Each derailing example is paired with a randomly selected non-derailing
    example from the corpus. This enables comparative training where the
    GEPA optimizer learns to assign higher derailment scores to derailing
    conversations relative to non-derailing ones.

    Args:
        examples: List of unpaired FlashpointExample dicts
        seed: Random seed for reproducible pairing

    Returns:
        List of PairedFlashpointExample dicts
    """
    rng = random.Random(seed)
    derailing = [e for e in examples if e["will_derail"]]
    non_derailing = [e for e in examples if not e["will_derail"]]

    if not non_derailing:
        return []

    paired: list[PairedFlashpointExample] = []
    for pos in derailing:
        neg = rng.choice(non_derailing)
        paired.append(
            PairedFlashpointExample(
                derailing_context=pos["context"],
                derailing_message=pos["current_message"],
                derailing_conversation_id=pos["conversation_id"],
                non_derailing_context=neg["context"],
                non_derailing_message=neg["current_message"],
                non_derailing_conversation_id=neg["conversation_id"],
            )
        )
    return paired


def save_datasets(
    train: list[FlashpointExample],
    dev: list[FlashpointExample],
    test: list[FlashpointExample],
    output_dir: Path,
    paired_train: list[PairedFlashpointExample] | None = None,
    paired_dev: list[PairedFlashpointExample] | None = None,
) -> None:
    """Save datasets as JSONL files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, data in [("train", train), ("dev", dev), ("test", test)]:
        path = output_dir / f"flashpoints_{name}.jsonl"
        with path.open("w") as f:
            for example in data:
                f.write(json.dumps(example) + "\n")
        print(f"Saved {len(data)} examples to {path}")

    if paired_train is not None:
        path = output_dir / "flashpoints_paired_train.jsonl"
        with path.open("w") as f:
            for example in paired_train:
                f.write(json.dumps(example) + "\n")
        print(f"Saved {len(paired_train)} paired training examples to {path}")

    if paired_dev is not None:
        path = output_dir / "flashpoints_paired_dev.jsonl"
        with path.open("w") as f:
            for example in paired_dev:
                f.write(json.dumps(example) + "\n")
        print(f"Saved {len(paired_dev)} paired dev examples to {path}")


def main() -> None:
    """Main extraction pipeline."""
    print("Loading CGA-CMV corpus...")
    corpus = load_cga_corpus()

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

    print("Creating paired/contrastive datasets...")
    paired_train = create_paired_dataset(train)
    paired_dev = create_paired_dataset(dev, seed=43)
    print(f"Paired: {len(paired_train)} train, {len(paired_dev)} dev")

    output_dir = Path(__file__).parent.parent.parent / "data" / "flashpoints"
    save_datasets(train, dev, test, output_dir, paired_train=paired_train, paired_dev=paired_dev)
    print(f"\nDatasets saved to {output_dir}")


if __name__ == "__main__":
    main()
