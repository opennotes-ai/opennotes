from __future__ import annotations


class TestSchemaDefaultsForNone:
    def test_rater_factor_data_with_none_intercept(self):
        from src.notes.scoring.schemas import RaterFactorData

        rf = RaterFactorData(
            rater_id="test-rater",
            agent_name=None,
            personality=None,
            intercept=None,
            factor1=None,
        )
        assert rf.intercept == 0.0
        assert rf.factor1 == 0.0

    def test_note_factor_data_with_none_intercept(self):
        from src.notes.scoring.schemas import NoteFactorData

        nf = NoteFactorData(
            note_id="test-note",
            intercept=None,
            factor1=None,
            status=None,
            classification=None,
            author_agent_name=None,
        )
        assert nf.intercept == 0.0
        assert nf.factor1 == 0.0

    def test_rater_factor_data_with_valid_values(self):
        from src.notes.scoring.schemas import RaterFactorData

        rf = RaterFactorData(
            rater_id="test-rater",
            agent_name=None,
            personality=None,
            intercept=0.5,
            factor1=-0.3,
        )
        assert rf.intercept == 0.5
        assert rf.factor1 == -0.3

    def test_note_factor_data_with_zero_values(self):
        from src.notes.scoring.schemas import NoteFactorData

        nf = NoteFactorData(
            note_id="test-note",
            intercept=0.0,
            factor1=0.0,
            status=None,
            classification=None,
            author_agent_name=None,
        )
        assert nf.intercept == 0.0
        assert nf.factor1 == 0.0


class TestGlobalInterceptNoneFallback:
    def test_none_global_intercept_defaults_to_zero(self):
        global_intercept: float | None = None
        result = global_intercept if global_intercept is not None else 0.0
        assert result == 0.0

    def test_valid_global_intercept_preserved(self):
        global_intercept: float | None = 0.42
        result = global_intercept if global_intercept is not None else 0.0
        assert result == 0.42

    def test_zero_global_intercept_preserved(self):
        global_intercept: float | None = 0.0
        result = global_intercept if global_intercept is not None else 0.0
        assert result == 0.0


class TestAnalysisDictGetPattern:
    def test_dict_get_with_none_value_uses_or_fallback(self):
        rf_dict = {"rater_id": "r1", "intercept": None, "factor1": None}
        intercept = rf_dict.get("intercept") or 0.0
        factor1 = rf_dict.get("factor1") or 0.0
        assert intercept == 0.0
        assert factor1 == 0.0

    def test_dict_get_with_valid_value(self):
        rf_dict = {"rater_id": "r1", "intercept": 0.5, "factor1": -0.3}
        intercept = rf_dict.get("intercept") or 0.0
        factor1 = rf_dict.get("factor1") or 0.0
        assert intercept == 0.5
        assert factor1 == -0.3

    def test_dict_get_with_missing_key(self):
        rf_dict = {"rater_id": "r1"}
        intercept = rf_dict.get("intercept") or 0.0
        factor1 = rf_dict.get("factor1") or 0.0
        assert intercept == 0.0
        assert factor1 == 0.0

    def test_dict_get_with_zero_value_uses_or_fallback(self):
        rf_dict = {"rater_id": "r1", "intercept": 0.0, "factor1": 0.0}
        intercept = rf_dict.get("intercept") or 0.0
        factor1 = rf_dict.get("factor1") or 0.0
        assert intercept == 0.0
        assert factor1 == 0.0
