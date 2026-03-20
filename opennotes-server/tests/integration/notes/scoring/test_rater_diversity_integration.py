import pyarrow as pa

from src.notes.scoring.rater_diversity_scorer import RaterDiversityScorerAdapter
from src.notes.scoring.scorer_factory import ScorerFactory
from src.notes.scoring.tier_config import MINIMAL_DIVERSITY_THRESHOLD

NOTE_COUNT = 20
CLUSTER_A_RATERS = [f"rater_a{i}" for i in range(8)]
CLUSTER_B_RATERS = [f"rater_b{i}" for i in range(7)]
ALL_RATERS = CLUSTER_A_RATERS + CLUSTER_B_RATERS
NOTES = [f"note_{i}" for i in range(NOTE_COUNT)]

DIVERSE_NOTE = "note_5"
HOMOGENEOUS_NOTE = "note_6"


def _build_ratings_table() -> pa.Table:
    rater_ids: list[str] = []
    note_ids: list[str] = []
    helpfulness_levels: list[str] = []

    for rater in CLUSTER_A_RATERS:
        for note in NOTES[:10]:
            if note in (DIVERSE_NOTE, HOMOGENEOUS_NOTE):
                continue
            rater_ids.append(rater)
            note_ids.append(note)
            helpfulness_levels.append("HELPFUL")
        for note in NOTES[10:]:
            rater_ids.append(rater)
            note_ids.append(note)
            helpfulness_levels.append("NOT_HELPFUL")

    for rater in CLUSTER_B_RATERS:
        for note in NOTES[10:]:
            rater_ids.append(rater)
            note_ids.append(note)
            helpfulness_levels.append("HELPFUL")
        for note in NOTES[:10]:
            if note in (DIVERSE_NOTE, HOMOGENEOUS_NOTE):
                continue
            rater_ids.append(rater)
            note_ids.append(note)
            helpfulness_levels.append("NOT_HELPFUL")

    for rater in CLUSTER_A_RATERS[:4]:
        rater_ids.append(rater)
        note_ids.append(DIVERSE_NOTE)
        helpfulness_levels.append("HELPFUL")

    for rater in CLUSTER_B_RATERS[:4]:
        rater_ids.append(rater)
        note_ids.append(DIVERSE_NOTE)
        helpfulness_levels.append("HELPFUL")

    for rater in CLUSTER_A_RATERS:
        rater_ids.append(rater)
        note_ids.append(HOMOGENEOUS_NOTE)
        helpfulness_levels.append("HELPFUL")

    n = len(rater_ids)
    timestamps = pa.array([1735689600000000] * n, type=pa.int64()).cast(
        pa.timestamp("us", tz="UTC")
    )
    return pa.table(
        {
            "rater_id": pa.array(rater_ids, type=pa.string()),
            "note_id": pa.array(note_ids, type=pa.string()),
            "helpfulness_level": pa.array(helpfulness_levels, type=pa.string()),
            "created_at": timestamps,
        }
    )


class FakeDataProvider:
    def __init__(self, ratings_table: pa.Table) -> None:
        self._ratings = ratings_table

    def get_all_ratings(self, _community_id: str) -> pa.Table:
        return self._ratings

    def get_all_notes(self, _community_id: str) -> pa.Table:
        return pa.table({})

    def get_all_participants(self, _community_id: str) -> pa.Array:
        return pa.array([])


class TestDiverseVsHomogeneousScoring:
    def test_diverse_supporters_score_higher_than_homogeneous(self):
        table = _build_ratings_table()
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "test_community")

        diverse_ratings = [1.0] * 8
        homogeneous_ratings = [1.0] * 8

        diverse_result = adapter.score_note(DIVERSE_NOTE, diverse_ratings)
        homogeneous_result = adapter.score_note(HOMOGENEOUS_NOTE, homogeneous_ratings)

        assert diverse_result.score > homogeneous_result.score
        assert (
            diverse_result.metadata["diversity_score"]
            > homogeneous_result.metadata["diversity_score"]
        )

    def test_diverse_note_has_strong_diversity_signal(self):
        table = _build_ratings_table()
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "test_community")

        result = adapter.score_note(DIVERSE_NOTE, [1.0] * 8)

        assert result.metadata["diversity_signal"] == "strong"
        assert result.metadata["supporter_count"] >= 2

    def test_homogeneous_note_has_weak_or_zero_diversity(self):
        table = _build_ratings_table()
        provider = FakeDataProvider(table)
        adapter = RaterDiversityScorerAdapter(provider, "test_community")

        result = adapter.score_note(HOMOGENEOUS_NOTE, [1.0] * 8)

        assert result.metadata["diversity_signal"] in ("weak", "insufficient")

    def test_blending_formula_applied_correctly(self):
        table = _build_ratings_table()
        provider = FakeDataProvider(table)
        bonus = 0.3
        adapter = RaterDiversityScorerAdapter(provider, "test_community", diversity_bonus=bonus)

        result = adapter.score_note(DIVERSE_NOTE, [1.0] * 8)

        bayesian_base = result.metadata["bayesian_base_score"]
        diversity_score = result.metadata["diversity_score"]
        expected = min(bayesian_base * (1.0 + bonus * diversity_score), 1.0)
        assert abs(result.score - expected) < 1e-9


class TestScorerFactoryDiversitySelection:
    def test_factory_returns_diversity_adapter_above_threshold(self):
        table = _build_ratings_table()
        provider = FakeDataProvider(table)
        factory = ScorerFactory()

        scorer = factory.get_scorer(
            "test_community",
            note_count=NOTE_COUNT,
            data_provider=provider,
            community_id="test_community",
        )

        assert isinstance(scorer, RaterDiversityScorerAdapter)
        assert NOTE_COUNT >= MINIMAL_DIVERSITY_THRESHOLD

    def test_factory_scorer_produces_diversity_aware_scores(self):
        table = _build_ratings_table()
        provider = FakeDataProvider(table)
        factory = ScorerFactory()

        scorer = factory.get_scorer(
            "test_community",
            note_count=NOTE_COUNT,
            data_provider=provider,
            community_id="test_community",
        )

        diverse_result = scorer.score_note(DIVERSE_NOTE, [1.0] * 8)
        homogeneous_result = scorer.score_note(HOMOGENEOUS_NOTE, [1.0] * 8)

        assert diverse_result.score > homogeneous_result.score
        assert "diversity_score" in diverse_result.metadata
        assert "diversity_score" in homogeneous_result.metadata


class TestRatingMatrixStructure:
    def test_all_notes_present_in_rating_matrix(self):
        table = _build_ratings_table()
        note_ids_in_table = set(table.column("note_id").to_pylist())

        for note in NOTES:
            assert note in note_ids_in_table

    def test_both_clusters_rate_diverse_note(self):
        table = _build_ratings_table()
        diverse_rows = table.filter(pa.compute.equal(table.column("note_id"), DIVERSE_NOTE))
        raters = set(diverse_rows.column("rater_id").to_pylist())

        cluster_a_supporters = raters & set(CLUSTER_A_RATERS)
        cluster_b_supporters = raters & set(CLUSTER_B_RATERS)

        assert len(cluster_a_supporters) >= 2
        assert len(cluster_b_supporters) >= 2

    def test_only_cluster_a_rates_homogeneous_note(self):
        table = _build_ratings_table()
        homogeneous_rows = table.filter(pa.compute.equal(table.column("note_id"), HOMOGENEOUS_NOTE))
        raters = set(homogeneous_rows.column("rater_id").to_pylist())
        helpful_rows = homogeneous_rows.filter(
            pa.compute.equal(homogeneous_rows.column("helpfulness_level"), "HELPFUL")
        )
        helpful_raters = set(helpful_rows.column("rater_id").to_pylist())

        assert helpful_raters.issubset(set(CLUSTER_A_RATERS))
        assert len(raters & set(CLUSTER_B_RATERS)) == 0
