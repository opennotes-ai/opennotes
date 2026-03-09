from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pandas as pd
import pendulum
import pytest


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


def _mock_scalars_all(items: list) -> MagicMock:
    scalars = MagicMock()
    scalars.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _mock_scalar_one_or_none(value) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_snapshot(
    community_server_id: UUID,
    rater_factors: list | None = None,
    note_factors: list | None = None,
    global_intercept: float = 0.0,
    metadata: dict | None = None,
    scored_at: datetime | None = None,
) -> MagicMock:
    snapshot = MagicMock()
    snapshot.community_server_id = community_server_id
    snapshot.rater_factors = rater_factors or []
    snapshot.note_factors = note_factors or []
    snapshot.global_intercept = global_intercept
    snapshot.metadata_ = metadata
    snapshot.scored_at = scored_at or pendulum.now("UTC")
    return snapshot


@pytest.mark.unit
class TestComputeScoringFactorAnalysis:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_snapshot(self):
        from src.notes.scoring.analysis import compute_scoring_factor_analysis

        community_id = uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(None))

        result = await compute_scoring_factor_analysis(community_id, mock_db)

        assert result is None
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_factors_returns_zero_counts(self):
        from src.notes.scoring.analysis import compute_scoring_factor_analysis

        community_id = uuid4()
        scored_at = pendulum.now("UTC")
        snapshot = _make_snapshot(
            community_server_id=community_id,
            rater_factors=[],
            note_factors=[],
            global_intercept=0.5,
            metadata={"tier": "minimal"},
            scored_at=scored_at,
        )

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(snapshot))

        with (
            patch(
                "src.notes.scoring.analysis._resolve_rater_identities",
                return_value={},
            ),
            patch(
                "src.notes.scoring.analysis._resolve_note_metadata",
                return_value={},
            ),
        ):
            result = await compute_scoring_factor_analysis(community_id, mock_db)

        assert result is not None
        assert result.rater_count == 0
        assert result.note_count == 0
        assert result.rater_factors == []
        assert result.note_factors == []
        assert result.global_intercept == 0.5
        assert result.tier == "minimal"
        assert result.scored_at == scored_at

    @pytest.mark.asyncio
    async def test_rater_identity_resolution_populates_agent_info(self):
        from src.notes.scoring.analysis import compute_scoring_factor_analysis

        community_id = uuid4()
        rater_uuid = str(uuid4())
        snapshot = _make_snapshot(
            community_server_id=community_id,
            rater_factors=[
                {"rater_id": rater_uuid, "intercept": 0.3, "factor1": -0.1},
            ],
            note_factors=[],
            global_intercept=0.42,
            metadata={"tier": "intermediate"},
        )

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(snapshot))

        identity_map = {
            rater_uuid: {"agent_name": "FactChecker", "personality": "skeptical"},
        }
        with (
            patch(
                "src.notes.scoring.analysis._resolve_rater_identities",
                return_value=identity_map,
            ),
            patch(
                "src.notes.scoring.analysis._resolve_note_metadata",
                return_value={},
            ),
        ):
            result = await compute_scoring_factor_analysis(community_id, mock_db)

        assert result is not None
        assert result.rater_count == 1
        assert result.rater_factors[0].rater_id == rater_uuid
        assert result.rater_factors[0].agent_name == "FactChecker"
        assert result.rater_factors[0].personality == "skeptical"
        assert result.rater_factors[0].intercept == pytest.approx(0.3)
        assert result.rater_factors[0].factor1 == pytest.approx(-0.1)

    @pytest.mark.asyncio
    async def test_rater_without_identity_gets_none_fields(self):
        from src.notes.scoring.analysis import compute_scoring_factor_analysis

        community_id = uuid4()
        rater_uuid = str(uuid4())
        snapshot = _make_snapshot(
            community_server_id=community_id,
            rater_factors=[
                {"rater_id": rater_uuid, "intercept": 0.1, "factor1": 0.2},
            ],
            note_factors=[],
            global_intercept=0.0,
            metadata={},
        )

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(snapshot))

        with (
            patch(
                "src.notes.scoring.analysis._resolve_rater_identities",
                return_value={},
            ),
            patch(
                "src.notes.scoring.analysis._resolve_note_metadata",
                return_value={},
            ),
        ):
            result = await compute_scoring_factor_analysis(community_id, mock_db)

        assert result is not None
        assert result.rater_factors[0].agent_name is None
        assert result.rater_factors[0].personality is None

    @pytest.mark.asyncio
    async def test_note_metadata_resolution_populates_note_info(self):
        from src.notes.scoring.analysis import compute_scoring_factor_analysis

        community_id = uuid4()
        note_uuid = str(uuid4())
        snapshot = _make_snapshot(
            community_server_id=community_id,
            rater_factors=[],
            note_factors=[
                {"note_id": note_uuid, "intercept": 0.7, "factor1": 0.1, "status": None},
            ],
            global_intercept=0.55,
            metadata={"tier": "full"},
        )

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(snapshot))

        note_meta = {
            note_uuid: {
                "status": "CURRENTLY_RATED_HELPFUL",
                "classification": "NOT_MISLEADING",
                "author_agent_name": "TruthSeeker",
            },
        }
        with (
            patch(
                "src.notes.scoring.analysis._resolve_rater_identities",
                return_value={},
            ),
            patch(
                "src.notes.scoring.analysis._resolve_note_metadata",
                return_value=note_meta,
            ),
        ):
            result = await compute_scoring_factor_analysis(community_id, mock_db)

        assert result is not None
        assert result.note_count == 1
        nf = result.note_factors[0]
        assert nf.note_id == note_uuid
        assert nf.intercept == pytest.approx(0.7)
        assert nf.factor1 == pytest.approx(0.1)
        assert nf.classification == "NOT_MISLEADING"
        assert nf.author_agent_name == "TruthSeeker"
        assert nf.status == "CURRENTLY_RATED_HELPFUL"

    @pytest.mark.asyncio
    async def test_note_status_from_snapshot_used_when_metadata_missing(self):
        from src.notes.scoring.analysis import compute_scoring_factor_analysis

        community_id = uuid4()
        note_uuid = str(uuid4())
        snapshot = _make_snapshot(
            community_server_id=community_id,
            rater_factors=[],
            note_factors=[
                {
                    "note_id": note_uuid,
                    "intercept": 0.2,
                    "factor1": 0.0,
                    "status": "NEEDS_MORE_RATINGS",
                },
            ],
            global_intercept=0.0,
            metadata={},
        )

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(snapshot))

        with (
            patch(
                "src.notes.scoring.analysis._resolve_rater_identities",
                return_value={},
            ),
            patch(
                "src.notes.scoring.analysis._resolve_note_metadata",
                return_value={},
            ),
        ):
            result = await compute_scoring_factor_analysis(community_id, mock_db)

        assert result is not None
        assert result.note_factors[0].status == "NEEDS_MORE_RATINGS"

    @pytest.mark.asyncio
    async def test_tier_none_when_metadata_empty(self):
        from src.notes.scoring.analysis import compute_scoring_factor_analysis

        community_id = uuid4()
        snapshot = _make_snapshot(
            community_server_id=community_id,
            rater_factors=[],
            note_factors=[],
            global_intercept=0.0,
            metadata={},
        )

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(snapshot))

        with (
            patch(
                "src.notes.scoring.analysis._resolve_rater_identities",
                return_value={},
            ),
            patch(
                "src.notes.scoring.analysis._resolve_note_metadata",
                return_value={},
            ),
        ):
            result = await compute_scoring_factor_analysis(community_id, mock_db)

        assert result is not None
        assert result.tier is None

    @pytest.mark.asyncio
    async def test_tier_none_when_metadata_is_none(self):
        from src.notes.scoring.analysis import compute_scoring_factor_analysis

        community_id = uuid4()
        snapshot = _make_snapshot(
            community_server_id=community_id,
            rater_factors=[],
            note_factors=[],
            global_intercept=0.0,
            metadata=None,
        )

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(snapshot))

        with (
            patch(
                "src.notes.scoring.analysis._resolve_rater_identities",
                return_value={},
            ),
            patch(
                "src.notes.scoring.analysis._resolve_note_metadata",
                return_value={},
            ),
        ):
            result = await compute_scoring_factor_analysis(community_id, mock_db)

        assert result is not None
        assert result.tier is None

    @pytest.mark.asyncio
    async def test_multiple_raters_and_notes(self):
        from src.notes.scoring.analysis import compute_scoring_factor_analysis

        community_id = uuid4()
        rater1 = str(uuid4())
        rater2 = str(uuid4())
        note1 = str(uuid4())
        note2 = str(uuid4())
        snapshot = _make_snapshot(
            community_server_id=community_id,
            rater_factors=[
                {"rater_id": rater1, "intercept": 0.1, "factor1": 0.2},
                {"rater_id": rater2, "intercept": 0.3, "factor1": 0.4},
            ],
            note_factors=[
                {"note_id": note1, "intercept": 0.5, "factor1": 0.6},
                {"note_id": note2, "intercept": 0.7, "factor1": 0.8},
            ],
            global_intercept=0.6,
            metadata={"tier": "full"},
        )

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(snapshot))

        identity_map = {
            rater1: {"agent_name": "Agent1", "personality": "neutral"},
            rater2: {"agent_name": "Agent2", "personality": "critical"},
        }
        note_meta = {
            note1: {
                "status": "CURRENTLY_RATED_HELPFUL",
                "classification": "NOT_MISLEADING",
                "author_agent_name": "Author1",
            },
            note2: {
                "status": "NEEDS_MORE_RATINGS",
                "classification": "MISINFORMED_OR_POTENTIALLY_MISLEADING",
                "author_agent_name": "Author2",
            },
        }

        with (
            patch(
                "src.notes.scoring.analysis._resolve_rater_identities",
                return_value=identity_map,
            ),
            patch(
                "src.notes.scoring.analysis._resolve_note_metadata",
                return_value=note_meta,
            ),
        ):
            result = await compute_scoring_factor_analysis(community_id, mock_db)

        assert result is not None
        assert result.rater_count == 2
        assert result.note_count == 2
        assert result.global_intercept == pytest.approx(0.6)
        assert result.tier == "full"

        rater_names = {rf.agent_name for rf in result.rater_factors}
        assert rater_names == {"Agent1", "Agent2"}

        note_authors = {nf.author_agent_name for nf in result.note_factors}
        assert note_authors == {"Author1", "Author2"}


@pytest.mark.unit
class TestResolveRaterIdentities:
    @pytest.mark.asyncio
    async def test_empty_rater_ids_returns_empty_dict(self):
        from src.notes.scoring.analysis import _resolve_rater_identities

        mock_db = AsyncMock()
        result = await _resolve_rater_identities([], uuid4(), mock_db)
        assert result == {}
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_uuid_rater_ids_returns_empty_dict(self):
        from src.notes.scoring.analysis import _resolve_rater_identities

        mock_db = AsyncMock()
        result = await _resolve_rater_identities(["not-a-uuid", "also-invalid"], uuid4(), mock_db)
        assert result == {}
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolves_agent_identity_from_db(self):
        from src.notes.scoring.analysis import _resolve_rater_identities

        community_id = uuid4()
        profile_id = uuid4()
        rater_id_str = str(profile_id)

        member = MagicMock()
        member.profile_id = profile_id

        agent_profile = MagicMock()
        agent_profile.name = "SkepticalBot"
        agent_profile.personality = "skeptical"

        agent_instance = MagicMock()
        agent_instance.user_profile_id = profile_id
        agent_instance.agent_profile = agent_profile

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                _mock_scalars_all([member]),
                _mock_scalars_all([agent_instance]),
            ]
        )

        result = await _resolve_rater_identities([rater_id_str], community_id, mock_db)

        assert rater_id_str in result
        assert result[rater_id_str]["agent_name"] == "SkepticalBot"
        assert result[rater_id_str]["personality"] == "skeptical"

    @pytest.mark.asyncio
    async def test_no_community_member_returns_empty_dict(self):
        from src.notes.scoring.analysis import _resolve_rater_identities

        community_id = uuid4()
        rater_id_str = str(uuid4())

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_mock_scalars_all([]))

        result = await _resolve_rater_identities([rater_id_str], community_id, mock_db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_member_without_agent_instance_gets_none_fields(self):
        from src.notes.scoring.analysis import _resolve_rater_identities

        community_id = uuid4()
        profile_id = uuid4()
        rater_id_str = str(profile_id)

        member = MagicMock()
        member.profile_id = profile_id

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                _mock_scalars_all([member]),
                _mock_scalars_all([]),
            ]
        )

        result = await _resolve_rater_identities([rater_id_str], community_id, mock_db)

        assert rater_id_str in result
        assert result[rater_id_str]["agent_name"] is None
        assert result[rater_id_str]["personality"] is None


@pytest.mark.unit
class TestResolveNoteMetadata:
    @pytest.mark.asyncio
    async def test_empty_note_ids_returns_empty_dict(self):
        from src.notes.scoring.analysis import _resolve_note_metadata

        mock_db = AsyncMock()
        result = await _resolve_note_metadata([], uuid4(), mock_db)
        assert result == {}
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_uuid_note_ids_returns_empty_dict(self):
        from src.notes.scoring.analysis import _resolve_note_metadata

        mock_db = AsyncMock()
        result = await _resolve_note_metadata(["bad-uuid", "also-bad"], uuid4(), mock_db)
        assert result == {}
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolves_note_with_author_agent(self):
        from src.notes.scoring.analysis import _resolve_note_metadata

        community_id = uuid4()
        note_id = uuid4()
        author_id = uuid4()
        note_id_str = str(note_id)

        note = MagicMock()
        note.id = note_id
        note.author_id = author_id
        note.status = "CURRENTLY_RATED_HELPFUL"
        note.classification = "NOT_MISLEADING"

        agent_profile = MagicMock()
        agent_profile.name = "TruthBot"

        agent_instance = MagicMock()
        agent_instance.user_profile_id = author_id
        agent_instance.agent_profile = agent_profile

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                _mock_scalars_all([note]),
                _mock_scalars_all([agent_instance]),
            ]
        )

        result = await _resolve_note_metadata([note_id_str], community_id, mock_db)

        assert note_id_str in result
        assert result[note_id_str]["status"] == "CURRENTLY_RATED_HELPFUL"
        assert result[note_id_str]["classification"] == "NOT_MISLEADING"
        assert result[note_id_str]["author_agent_name"] == "TruthBot"

    @pytest.mark.asyncio
    async def test_note_without_agent_author_gets_none_author(self):
        from src.notes.scoring.analysis import _resolve_note_metadata

        community_id = uuid4()
        note_id = uuid4()
        author_id = uuid4()
        note_id_str = str(note_id)

        note = MagicMock()
        note.id = note_id
        note.author_id = author_id
        note.status = "NEEDS_MORE_RATINGS"
        note.classification = "MISINFORMED_OR_POTENTIALLY_MISLEADING"

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                _mock_scalars_all([note]),
                _mock_scalars_all([]),
            ]
        )

        result = await _resolve_note_metadata([note_id_str], community_id, mock_db)

        assert note_id_str in result
        assert result[note_id_str]["author_agent_name"] is None
        assert result[note_id_str]["status"] == "NEEDS_MORE_RATINGS"


@pytest.mark.unit
class TestPersistScoringSnapshot:
    @pytest.mark.asyncio
    async def test_executes_upsert_and_returns_snapshot(self):
        from src.notes.scoring.snapshot_persistence import persist_scoring_snapshot

        community_id = uuid4()
        snapshot_id = uuid4()
        now = pendulum.now("UTC")

        rater_factors = [{"rater_id": "r1", "intercept": 0.5, "factor1": -0.2}]
        note_factors = [{"note_id": "n1", "intercept": 0.7, "factor1": 0.1}]
        metadata = {"tier": "intermediate"}

        row_mapping = {
            "id": snapshot_id,
            "community_server_id": community_id,
            "scored_at": now,
            "rater_factors": rater_factors,
            "note_factors": note_factors,
            "global_intercept": 0.42,
            "metadata": metadata,
        }

        mock_mappings = MagicMock()
        mock_mappings.one.return_value = row_mapping

        mock_result = MagicMock()
        mock_result.mappings.return_value = mock_mappings

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.notes.scoring.snapshot_persistence.pendulum") as mock_pendulum:
            mock_pendulum.now.return_value = now

            snapshot = await persist_scoring_snapshot(
                community_server_id=community_id,
                rater_factors=rater_factors,
                note_factors=note_factors,
                global_intercept=0.42,
                metadata=metadata,
                db=mock_db,
            )

        assert snapshot.id == snapshot_id
        assert snapshot.community_server_id == community_id
        assert snapshot.rater_factors == rater_factors
        assert snapshot.note_factors == note_factors
        assert snapshot.global_intercept == 0.42
        assert snapshot.metadata_ == metadata
        assert snapshot.scored_at == now

        mock_db.execute.assert_called_once()
        mock_pendulum.now.assert_called_once_with("UTC")

    @pytest.mark.asyncio
    async def test_upsert_statement_includes_conflict_handling(self):
        from src.notes.scoring.snapshot_persistence import persist_scoring_snapshot

        community_id = uuid4()
        now = pendulum.now("UTC")

        row_mapping = {
            "id": uuid4(),
            "community_server_id": community_id,
            "scored_at": now,
            "rater_factors": [],
            "note_factors": [],
            "global_intercept": 0.0,
            "metadata": {},
        }

        mock_mappings = MagicMock()
        mock_mappings.one.return_value = row_mapping
        mock_result = MagicMock()
        mock_result.mappings.return_value = mock_mappings

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.notes.scoring.snapshot_persistence.pendulum") as mock_pendulum:
            mock_pendulum.now.return_value = now
            await persist_scoring_snapshot(
                community_server_id=community_id,
                rater_factors=[],
                note_factors=[],
                global_intercept=0.0,
                metadata={},
                db=mock_db,
            )

        executed_stmt = mock_db.execute.call_args[0][0]
        compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "ON CONFLICT" in compiled
        assert "DO UPDATE SET" in compiled
        assert "RETURNING" in compiled


@pytest.mark.unit
class TestExtractFactorsFromModelResult:
    def test_extracts_rater_and_note_factors(self):
        from src.notes.scoring.snapshot_persistence import (
            extract_factors_from_model_result,
        )

        note_uuid = str(uuid4())
        int_to_uuid = {1: note_uuid}

        model_result = MagicMock()
        model_result.helpfulnessScores = pd.DataFrame(
            {
                "raterParticipantId": ["rater-abc"],
                "coreRaterIntercept": [0.5],
                "coreRaterFactor1": [-0.2],
            }
        )
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [1],
                "coreNoteIntercept": [0.7],
                "coreNoteFactor1": [0.1],
                "coreRatingStatus": ["CURRENTLY_RATED_HELPFUL"],
            }
        )

        result = extract_factors_from_model_result(model_result, int_to_uuid)

        assert result["rater_count"] == 1
        assert result["note_count"] == 1
        assert result["rater_factors"][0]["rater_id"] == "rater-abc"
        assert result["rater_factors"][0]["intercept"] == pytest.approx(0.5)
        assert result["rater_factors"][0]["factor1"] == pytest.approx(-0.2)
        assert result["note_factors"][0]["note_id"] == note_uuid
        assert result["note_factors"][0]["intercept"] == pytest.approx(0.7)
        assert result["note_factors"][0]["factor1"] == pytest.approx(0.1)
        assert result["note_factors"][0]["status"] == "CURRENTLY_RATED_HELPFUL"
        assert result["global_intercept"] == pytest.approx(0.7)

    def test_handles_none_helpfulness_scores(self):
        from src.notes.scoring.snapshot_persistence import (
            extract_factors_from_model_result,
        )

        model_result = MagicMock()
        model_result.helpfulnessScores = None
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [1],
                "coreNoteIntercept": [0.3],
                "coreNoteFactor1": [0.0],
                "coreRatingStatus": ["NEEDS_MORE_RATINGS"],
            }
        )

        result = extract_factors_from_model_result(model_result, {1: "note-1"})

        assert result["rater_count"] == 0
        assert result["rater_factors"] == []
        assert result["note_count"] == 1

    def test_handles_none_scored_notes(self):
        from src.notes.scoring.snapshot_persistence import (
            extract_factors_from_model_result,
        )

        model_result = MagicMock()
        model_result.helpfulnessScores = pd.DataFrame(
            {
                "raterParticipantId": ["r1"],
                "coreRaterIntercept": [0.1],
                "coreRaterFactor1": [0.2],
            }
        )
        model_result.scoredNotes = None

        result = extract_factors_from_model_result(model_result, {})

        assert result["note_count"] == 0
        assert result["note_factors"] == []
        assert result["rater_count"] == 1
        assert result["global_intercept"] == 0.0

    def test_both_none_returns_empty(self):
        from src.notes.scoring.snapshot_persistence import (
            extract_factors_from_model_result,
        )

        model_result = MagicMock()
        model_result.helpfulnessScores = None
        model_result.scoredNotes = None

        result = extract_factors_from_model_result(model_result, {})

        assert result["rater_count"] == 0
        assert result["note_count"] == 0
        assert result["rater_factors"] == []
        assert result["note_factors"] == []
        assert result["global_intercept"] == 0.0

    def test_int_to_uuid_mapping_applied(self):
        from src.notes.scoring.snapshot_persistence import (
            extract_factors_from_model_result,
        )

        uuid_a = str(uuid4())
        uuid_b = str(uuid4())
        int_to_uuid = {10: uuid_a, 20: uuid_b}

        model_result = MagicMock()
        model_result.helpfulnessScores = None
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [10, 20],
                "coreNoteIntercept": [0.1, 0.2],
                "coreNoteFactor1": [0.3, 0.4],
                "coreRatingStatus": ["NEEDS_MORE_RATINGS", "CURRENTLY_RATED_HELPFUL"],
            }
        )

        result = extract_factors_from_model_result(model_result, int_to_uuid)

        note_ids = [nf["note_id"] for nf in result["note_factors"]]
        assert uuid_a in note_ids
        assert uuid_b in note_ids

    def test_unmapped_int_id_falls_back_to_string(self):
        from src.notes.scoring.snapshot_persistence import (
            extract_factors_from_model_result,
        )

        model_result = MagicMock()
        model_result.helpfulnessScores = None
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [999],
                "coreNoteIntercept": [0.5],
                "coreNoteFactor1": [0.0],
                "coreRatingStatus": ["NEEDS_MORE_RATINGS"],
            }
        )

        result = extract_factors_from_model_result(model_result, {})

        assert result["note_factors"][0]["note_id"] == "999"

    def test_global_intercept_is_mean_of_note_intercepts(self):
        from src.notes.scoring.snapshot_persistence import (
            extract_factors_from_model_result,
        )

        model_result = MagicMock()
        model_result.helpfulnessScores = None
        model_result.scoredNotes = pd.DataFrame(
            {
                "noteId": [1, 2, 3],
                "coreNoteIntercept": [0.3, 0.6, 0.9],
                "coreNoteFactor1": [0.0, 0.0, 0.0],
                "coreRatingStatus": ["X", "Y", "Z"],
            }
        )

        result = extract_factors_from_model_result(model_result, {1: "a", 2: "b", 3: "c"})

        assert result["global_intercept"] == pytest.approx(0.6)
