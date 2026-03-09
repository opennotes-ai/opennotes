from datetime import UTC, datetime


class TestScoringAnalysisSchemas:
    def test_can_import_rater_factor_data(self):
        from src.notes.scoring.schemas import RaterFactorData

        assert RaterFactorData is not None

    def test_can_import_note_factor_data(self):
        from src.notes.scoring.schemas import NoteFactorData

        assert NoteFactorData is not None

    def test_can_import_scoring_analysis_attributes(self):
        from src.notes.scoring.schemas import ScoringAnalysisAttributes

        assert ScoringAnalysisAttributes is not None

    def test_can_import_scoring_analysis_resource(self):
        from src.notes.scoring.schemas import ScoringAnalysisResource

        assert ScoringAnalysisResource is not None

    def test_can_import_scoring_analysis_response(self):
        from src.notes.scoring.schemas import ScoringAnalysisResponse

        assert ScoringAnalysisResponse is not None

    def test_rater_factor_data_construction(self):
        from src.notes.scoring.schemas import RaterFactorData

        data = RaterFactorData(
            rater_id="abc-123",
            agent_name="Agent_Alpha",
            personality="skeptical fact-checker",
            intercept=0.5,
            factor1=-0.2,
        )
        assert data.rater_id == "abc-123"
        assert data.agent_name == "Agent_Alpha"
        assert data.personality == "skeptical fact-checker"
        assert data.intercept == 0.5
        assert data.factor1 == -0.2

    def test_rater_factor_data_none_agent(self):
        from src.notes.scoring.schemas import RaterFactorData

        data = RaterFactorData(
            rater_id="abc-123",
            agent_name=None,
            personality=None,
            intercept=0.5,
            factor1=-0.2,
        )
        assert data.agent_name is None
        assert data.personality is None

    def test_note_factor_data_construction(self):
        from src.notes.scoring.schemas import NoteFactorData

        data = NoteFactorData(
            note_id="note-1",
            intercept=0.7,
            factor1=0.1,
            status="CURRENTLY_RATED_HELPFUL",
            classification="NOT_MISLEADING",
            author_agent_name="Agent_Beta",
        )
        assert data.note_id == "note-1"
        assert data.intercept == 0.7
        assert data.status == "CURRENTLY_RATED_HELPFUL"
        assert data.author_agent_name == "Agent_Beta"

    def test_scoring_analysis_attributes_construction(self):
        from src.notes.scoring.schemas import (
            NoteFactorData,
            RaterFactorData,
            ScoringAnalysisAttributes,
        )

        attrs = ScoringAnalysisAttributes(
            scored_at=datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC),
            tier="intermediate",
            global_intercept=0.15,
            rater_count=5,
            note_count=10,
            rater_factors=[
                RaterFactorData(
                    rater_id="r1",
                    agent_name=None,
                    personality=None,
                    intercept=0.3,
                    factor1=0.1,
                ),
            ],
            note_factors=[
                NoteFactorData(
                    note_id="n1",
                    intercept=0.5,
                    factor1=-0.1,
                    status="CURRENTLY_RATED_HELPFUL",
                    classification=None,
                    author_agent_name=None,
                ),
            ],
        )
        assert attrs.tier == "intermediate"
        assert attrs.global_intercept == 0.15
        assert len(attrs.rater_factors) == 1
        assert len(attrs.note_factors) == 1

    def test_scoring_analysis_resource_type(self):
        from src.notes.scoring.schemas import (
            ScoringAnalysisAttributes,
            ScoringAnalysisResource,
        )

        resource = ScoringAnalysisResource(
            id="test-id",
            attributes=ScoringAnalysisAttributes(
                scored_at=datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC),
                tier=None,
                global_intercept=0.0,
                rater_count=0,
                note_count=0,
                rater_factors=[],
                note_factors=[],
            ),
        )
        assert resource.type == "scoring-analyses"

    def test_scoring_analysis_response_jsonapi_version(self):
        from src.notes.scoring.schemas import (
            ScoringAnalysisAttributes,
            ScoringAnalysisResource,
            ScoringAnalysisResponse,
        )

        response = ScoringAnalysisResponse(
            data=ScoringAnalysisResource(
                id="test-id",
                attributes=ScoringAnalysisAttributes(
                    scored_at=datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC),
                    tier=None,
                    global_intercept=0.0,
                    rater_count=0,
                    note_count=0,
                    rater_factors=[],
                    note_factors=[],
                ),
            ),
        )
        assert response.jsonapi == {"version": "1.1"}


class TestScoringAnalysisFunction:
    def test_can_import_compute_function(self):
        from src.notes.scoring.analysis import compute_scoring_factor_analysis

        assert compute_scoring_factor_analysis is not None
