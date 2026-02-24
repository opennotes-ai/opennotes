"""Tests for GEPA state validation in optimize_prompt.py."""

import pickle
from pathlib import Path

from scripts.flashpoints.flashpoint_module import FlashpointTrainerProgram
from scripts.flashpoints.optimize_prompt import _validate_gepa_state
from src.bulk_content_scan.flashpoint_utils import (
    FlashpointDetector,
    RubricDetector,
    TwoStageFlashpointDetector,
)


def _make_gepa_state(log_dir: Path, predictor_names: list[str]) -> Path:
    state_path = log_dir / "gepa_state.bin"
    state_data = {"list_of_named_predictors": predictor_names}
    with state_path.open("wb") as f:
        pickle.dump(state_data, f)
    return state_path


class TestValidateGepaState:
    def test_no_state_file_is_noop(self, tmp_path: Path):
        trainer = FlashpointTrainerProgram(FlashpointDetector())
        _validate_gepa_state(tmp_path, trainer)

    def test_matching_state_is_preserved(self, tmp_path: Path):
        trainer = FlashpointTrainerProgram(FlashpointDetector())
        current_names = [name for name, _ in trainer.named_predictors()]
        state_path = _make_gepa_state(tmp_path, current_names)
        _validate_gepa_state(tmp_path, trainer)
        assert state_path.exists()

    def test_stale_state_is_deleted(self, tmp_path: Path):
        trainer = FlashpointTrainerProgram(FlashpointDetector())
        state_path = _make_gepa_state(tmp_path, ["predict.predict"])
        _validate_gepa_state(tmp_path, trainer)
        assert not state_path.exists()

    def test_stale_state_prints_warning(self, tmp_path: Path, capsys):
        trainer = FlashpointTrainerProgram(FlashpointDetector())
        _make_gepa_state(tmp_path, ["predict.predict"])
        _validate_gepa_state(tmp_path, trainer)
        captured = capsys.readouterr()
        assert "stale predictor names" in captured.out

    def test_detector_type_switch_detected(self, tmp_path: Path):
        single_trainer = FlashpointTrainerProgram(FlashpointDetector())
        single_names = [name for name, _ in single_trainer.named_predictors()]
        state_path = _make_gepa_state(tmp_path, single_names)

        rubric_trainer = FlashpointTrainerProgram(RubricDetector())
        _validate_gepa_state(tmp_path, rubric_trainer)
        assert not state_path.exists()

    def test_corrupted_state_is_ignored(self, tmp_path: Path):
        trainer = FlashpointTrainerProgram(FlashpointDetector())
        state_path = tmp_path / "gepa_state.bin"
        state_path.write_bytes(b"not valid pickle")
        _validate_gepa_state(tmp_path, trainer)
        assert state_path.exists()


class TestDetectorPredictorNames:
    """Verify the predictor name hierarchy for each detector type."""

    def test_single_detector_predictor_names(self):
        trainer = FlashpointTrainerProgram(FlashpointDetector())
        names = [name for name, _ in trainer.named_predictors()]
        assert names == ["detector.predict.predict"]

    def test_rubric_detector_predictor_names(self):
        trainer = FlashpointTrainerProgram(RubricDetector())
        names = [name for name, _ in trainer.named_predictors()]
        assert names == ["detector.assess.predict"]

    def test_two_stage_detector_predictor_names(self):
        trainer = FlashpointTrainerProgram(TwoStageFlashpointDetector())
        names = sorted(name for name, _ in trainer.named_predictors())
        assert names == ["detector.score.predict", "detector.summarize.predict"]
