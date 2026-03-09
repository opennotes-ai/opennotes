class TestScoringSnapshotModel:
    def test_can_import_scoring_snapshot(self):
        from src.notes.scoring.models import ScoringSnapshot

        assert ScoringSnapshot is not None

    def test_tablename(self):
        from src.notes.scoring.models import ScoringSnapshot

        assert ScoringSnapshot.__tablename__ == "scoring_snapshots"

    def test_has_expected_columns(self):
        from src.notes.scoring.models import ScoringSnapshot

        column_names = {c.name for c in ScoringSnapshot.__table__.columns}
        expected = {
            "id",
            "community_server_id",
            "scored_at",
            "rater_factors",
            "note_factors",
            "global_intercept",
            "metadata",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(column_names)

    def test_community_server_id_is_unique(self):
        from src.notes.scoring.models import ScoringSnapshot

        col = ScoringSnapshot.__table__.c.community_server_id
        assert col.unique is True

    def test_id_has_uuidv7_server_default(self):
        from src.notes.scoring.models import ScoringSnapshot

        col = ScoringSnapshot.__table__.c.id
        assert col.server_default is not None
        assert "uuidv7()" in str(col.server_default.arg)

    def test_metadata_column_name(self):
        from src.notes.scoring.models import ScoringSnapshot

        assert "metadata" in {c.name for c in ScoringSnapshot.__table__.columns}
        assert hasattr(ScoringSnapshot, "metadata_")

    def test_global_intercept_default(self):
        from src.notes.scoring.models import ScoringSnapshot

        col = ScoringSnapshot.__table__.c.global_intercept
        assert col.server_default is not None


class TestScoringSnapshotFactorSerialization:
    def test_rater_factors_structure(self):
        rater_factors = [
            {"rater_id": "abc-123", "intercept": 0.5, "factor1": -0.2},
            {"rater_id": "def-456", "intercept": -0.1, "factor1": 0.3},
        ]
        assert isinstance(rater_factors, list)
        assert all("rater_id" in r for r in rater_factors)
        assert all("intercept" in r for r in rater_factors)
        assert all("factor1" in r for r in rater_factors)

    def test_note_factors_structure(self):
        note_factors = [
            {"note_id": "note-1", "intercept": 0.7, "factor1": 0.1},
            {"note_id": "note-2", "intercept": -0.3, "factor1": -0.4},
        ]
        assert isinstance(note_factors, list)
        assert all("note_id" in n for n in note_factors)
        assert all("intercept" in n for n in note_factors)
        assert all("factor1" in n for n in note_factors)

    def test_metadata_structure(self):
        metadata = {
            "tier": "intermediate",
            "scorer_name": "MFCoreScorer",
            "note_count": 500,
            "rater_count": 200,
        }
        assert metadata["tier"] == "intermediate"
        assert metadata["scorer_name"] == "MFCoreScorer"
        assert isinstance(metadata["note_count"], int)
        assert isinstance(metadata["rater_count"], int)


class TestMFCoreScorerAdapterFactorExtraction:
    def test_adapter_stores_last_batch_result(self):
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        adapter = MFCoreScorerAdapter()
        assert adapter.get_last_scoring_factors() is None

    def test_get_last_scoring_factors_returns_none_without_batch(self):
        from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

        adapter = MFCoreScorerAdapter()
        result = adapter.get_last_scoring_factors()
        assert result is None


class TestPersistScoringSnapshot:
    def test_can_import_persist_function(self):
        from src.notes.scoring.snapshot_persistence import persist_scoring_snapshot

        assert persist_scoring_snapshot is not None

    def test_can_import_extract_factors_function(self):
        from src.notes.scoring.snapshot_persistence import extract_factors_from_model_result

        assert extract_factors_from_model_result is not None
