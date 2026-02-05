"""Unit tests for dspy_dataset.py flashpoint example loading."""

import json
import logging
from pathlib import Path

import pytest

from scripts.flashpoints.dspy_dataset import load_flashpoint_examples


class TestLoadFlashpointExamples:
    """Tests for load_flashpoint_examples."""

    def test_skips_record_with_missing_key(self, tmp_path: Path, caplog):
        """Records with valid JSON but missing required keys should be skipped."""
        jsonl_path = tmp_path / "test.jsonl"
        records = [
            json.dumps({"context": "ctx", "current_message": "msg", "will_derail": True}),
            json.dumps({"context": "ctx only"}),
            json.dumps({"context": "ctx2", "current_message": "msg2", "will_derail": False}),
        ]
        jsonl_path.write_text("\n".join(records) + "\n")

        with caplog.at_level(logging.WARNING):
            examples = load_flashpoint_examples(jsonl_path)

        assert len(examples) == 2
        assert "missing key" in caplog.text.lower()

    def test_skips_malformed_json(self, tmp_path: Path, caplog):
        """Lines with invalid JSON should be skipped with a warning."""
        jsonl_path = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"context": "ctx", "current_message": "msg", "will_derail": True}),
            "not valid json {{{",
            json.dumps({"context": "ctx2", "current_message": "msg2", "will_derail": False}),
        ]
        jsonl_path.write_text("\n".join(lines) + "\n")

        with caplog.at_level(logging.WARNING):
            examples = load_flashpoint_examples(jsonl_path)

        assert len(examples) == 2
        assert "malformed json" in caplog.text.lower()

    def test_loads_valid_records(self, tmp_path: Path):
        """Valid records should be loaded as dspy.Example objects."""
        jsonl_path = tmp_path / "test.jsonl"
        record = {"context": "hello", "current_message": "world", "will_derail": True}
        jsonl_path.write_text(json.dumps(record) + "\n")

        examples = load_flashpoint_examples(jsonl_path)

        assert len(examples) == 1
        assert examples[0].context == "hello"
        assert examples[0].message == "world"
        assert examples[0].will_derail is True

    def test_file_not_found(self, tmp_path: Path):
        """Missing file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_flashpoint_examples(tmp_path / "nonexistent.jsonl")

    def test_skips_empty_lines(self, tmp_path: Path):
        """Empty lines should be skipped without error."""
        jsonl_path = tmp_path / "test.jsonl"
        record = json.dumps({"context": "c", "current_message": "m", "will_derail": False})
        jsonl_path.write_text(f"\n{record}\n\n")

        examples = load_flashpoint_examples(jsonl_path)

        assert len(examples) == 1
