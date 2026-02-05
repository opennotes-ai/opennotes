"""Unit tests for flashpoint dataset extraction functions."""

import importlib
import json
import sys
from pathlib import Path

import pytest

convokit = pytest.importorskip("convokit", reason="convokit is an optional dependency")

_repo_root = str(Path(__file__).resolve().parents[3])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

_mod = importlib.import_module("scripts.flashpoints.extract_cga_dataset")
FlashpointExample = _mod.FlashpointExample
save_datasets = _mod.save_datasets
split_dataset = _mod.split_dataset


class TestSplitDataset:
    """Tests for split_dataset function."""

    def test_split_ratios(self):
        """Verify 20/30/50 split ratios (train/dev/test)."""
        examples: list[FlashpointExample] = [
            FlashpointExample(
                conversation_id=f"conv_{i}",
                context=f"context {i}",
                current_message=f"message {i}",
                will_derail=i % 2 == 0,
                derail_point=i if i % 2 == 0 else None,
            )
            for i in range(100)
        ]

        train, dev, test = split_dataset(examples)

        assert len(train) == 20
        assert len(dev) == 30
        assert len(test) == 50
        assert len(train) + len(dev) + len(test) == 100

    def test_split_ratios_with_different_sizes(self):
        """Split ratios should scale correctly for different dataset sizes."""
        examples: list[FlashpointExample] = [
            FlashpointExample(
                conversation_id=f"conv_{i}",
                context=f"context {i}",
                current_message=f"message {i}",
                will_derail=False,
                derail_point=None,
            )
            for i in range(200)
        ]

        train, dev, test = split_dataset(examples)

        assert len(train) == 40
        assert len(dev) == 60
        assert len(test) == 100

    def test_deterministic_with_seed(self):
        """Same seed should produce identical splits."""
        examples: list[FlashpointExample] = [
            FlashpointExample(
                conversation_id=f"conv_{i}",
                context=f"context {i}",
                current_message=f"message {i}",
                will_derail=i % 3 == 0,
                derail_point=i if i % 3 == 0 else None,
            )
            for i in range(50)
        ]

        train1, dev1, test1 = split_dataset(examples, seed=42)
        train2, dev2, test2 = split_dataset(examples, seed=42)

        assert train1 == train2
        assert dev1 == dev2
        assert test1 == test2

    def test_different_seeds_produce_different_splits(self):
        """Different seeds should produce different splits."""
        examples: list[FlashpointExample] = [
            FlashpointExample(
                conversation_id=f"conv_{i}",
                context=f"context {i}",
                current_message=f"message {i}",
                will_derail=False,
                derail_point=None,
            )
            for i in range(50)
        ]

        train1, _, _ = split_dataset(examples, seed=42)
        train2, _, _ = split_dataset(examples, seed=123)

        assert train1 != train2

    def test_preserves_all_examples(self):
        """Split should contain all original examples (no duplicates or losses)."""
        examples: list[FlashpointExample] = [
            FlashpointExample(
                conversation_id=f"conv_{i}",
                context=f"context {i}",
                current_message=f"message {i}",
                will_derail=i % 2 == 0,
                derail_point=i if i % 2 == 0 else None,
            )
            for i in range(30)
        ]

        train, dev, test = split_dataset(examples)

        all_split = train + dev + test
        original_ids = {e["conversation_id"] for e in examples}
        split_ids = {e["conversation_id"] for e in all_split}

        assert original_ids == split_ids


class TestSaveDatasets:
    """Tests for save_datasets function."""

    def test_saves_jsonl_files(self, tmp_path: Path):
        """JSONL files should be saved with correct format."""
        train: list[FlashpointExample] = [
            FlashpointExample(
                conversation_id="train_1",
                context="train context",
                current_message="train message",
                will_derail=True,
                derail_point=5,
            )
        ]
        dev: list[FlashpointExample] = [
            FlashpointExample(
                conversation_id="dev_1",
                context="dev context",
                current_message="dev message",
                will_derail=False,
                derail_point=None,
            )
        ]
        test: list[FlashpointExample] = [
            FlashpointExample(
                conversation_id="test_1",
                context="test context",
                current_message="test message",
                will_derail=True,
                derail_point=3,
            ),
            FlashpointExample(
                conversation_id="test_2",
                context="test context 2",
                current_message="test message 2",
                will_derail=False,
                derail_point=None,
            ),
        ]

        save_datasets(train, dev, test, tmp_path)

        train_path = tmp_path / "flashpoints_train.jsonl"
        dev_path = tmp_path / "flashpoints_dev.jsonl"
        test_path = tmp_path / "flashpoints_test.jsonl"

        assert train_path.exists()
        assert dev_path.exists()
        assert test_path.exists()

    def test_jsonl_content_is_valid(self, tmp_path: Path):
        """Each line in JSONL file should be valid JSON."""
        examples: list[FlashpointExample] = [
            FlashpointExample(
                conversation_id="conv_1",
                context="context 1",
                current_message="message 1",
                will_derail=True,
                derail_point=5,
            ),
            FlashpointExample(
                conversation_id="conv_2",
                context="context 2",
                current_message="message 2",
                will_derail=False,
                derail_point=None,
            ),
        ]

        save_datasets(examples, [], [], tmp_path)

        train_path = tmp_path / "flashpoints_train.jsonl"
        with train_path.open() as f:
            lines = f.readlines()

        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "conversation_id" in parsed
            assert "context" in parsed
            assert "current_message" in parsed
            assert "will_derail" in parsed
            assert "derail_point" in parsed

    def test_creates_output_directory(self, tmp_path: Path):
        """Output directory should be created if it doesn't exist."""
        nested_path = tmp_path / "nested" / "output" / "dir"
        assert not nested_path.exists()

        save_datasets([], [], [], nested_path)

        assert nested_path.exists()

    def test_preserves_example_data(self, tmp_path: Path):
        """Saved data should match input examples exactly."""
        train: list[FlashpointExample] = [
            FlashpointExample(
                conversation_id="test_conv",
                context="User1: Hello\nUser2: Hi there",
                current_message="User1: I disagree",
                will_derail=True,
                derail_point=7,
            )
        ]

        save_datasets(train, [], [], tmp_path)

        train_path = tmp_path / "flashpoints_train.jsonl"
        with train_path.open() as f:
            loaded = json.loads(f.readline())

        assert loaded["conversation_id"] == "test_conv"
        assert loaded["context"] == "User1: Hello\nUser2: Hi there"
        assert loaded["current_message"] == "User1: I disagree"
        assert loaded["will_derail"] is True
        assert loaded["derail_point"] == 7
