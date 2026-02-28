from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from opennotes_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


SAMPLE_ANALYSIS_RESPONSE: dict = {
    "data": {
        "type": "simulation-analysis",
        "id": "sim-abc-123",
        "attributes": {
            "rating_distribution": {
                "overall": {"HELPFUL": 5, "NOT_HELPFUL": 2, "SOMEWHAT_HELPFUL": 3},
                "per_agent": [
                    {
                        "agent_instance_id": "agent-1",
                        "agent_name": "Skeptic",
                        "distribution": {"HELPFUL": 3, "NOT_HELPFUL": 1},
                        "total": 4,
                    },
                    {
                        "agent_instance_id": "agent-2",
                        "agent_name": "Optimist",
                        "distribution": {"HELPFUL": 2, "SOMEWHAT_HELPFUL": 3, "NOT_HELPFUL": 1},
                        "total": 6,
                    },
                ],
                "total_ratings": 10,
            },
            "consensus_metrics": {
                "mean_agreement": 0.85,
                "polarization_index": 0.12,
                "notes_with_consensus": 4,
                "notes_with_disagreement": 1,
                "total_notes_rated": 5,
            },
            "scoring_coverage": {
                "current_tier": "MODERATE",
                "total_scores_computed": 15,
                "tier_distribution": {"MODERATE": 10, "BASIC": 5},
                "scorer_breakdown": {"BayesianAverage": 10, "CommunityNotes": 5},
                "notes_by_status": {"scored": 12, "pending": 3},
                "tiers_reached": ["BASIC", "MODERATE"],
                "scorers_exercised": ["BayesianAverage", "CommunityNotes"],
            },
            "agent_behaviors": [
                {
                    "agent_instance_id": "agent-1",
                    "agent_name": "Skeptic",
                    "notes_written": 3,
                    "ratings_given": 4,
                    "turn_count": 7,
                    "state": "completed",
                    "helpfulness_trend": ["HELPFUL", "NOT_HELPFUL", "HELPFUL"],
                    "action_distribution": {"write_note": 3, "rate_note": 4},
                },
                {
                    "agent_instance_id": "agent-2",
                    "agent_name": "Optimist",
                    "notes_written": 5,
                    "ratings_given": 6,
                    "turn_count": 11,
                    "state": "completed",
                    "helpfulness_trend": ["HELPFUL", "HELPFUL", "SOMEWHAT_HELPFUL"],
                    "action_distribution": {"write_note": 5, "rate_note": 6},
                },
            ],
            "note_quality": {
                "avg_helpfulness_score": 0.72,
                "notes_by_status": {"scored": 8, "pending": 2},
                "notes_by_classification": {"HELPFUL": 5, "NOT_HELPFUL": 2, "NEEDS_MORE_RATINGS": 1},
            },
        },
    }
}


def _make_mock_client(analysis_response: MagicMock) -> MagicMock:
    mock_csrf_resp = MagicMock()
    mock_csrf_resp.status_code = 200

    mock_client = MagicMock()
    mock_client.get.side_effect = [mock_csrf_resp, analysis_response]
    mock_client.cookies = MagicMock()
    mock_client.cookies.get.return_value = "test-csrf"
    return mock_client


class TestAnalysisSubcommandRegistered:
    def test_analysis_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["simulation", "analysis", "--help"])
        assert result.exit_code == 0
        assert "simulation_id" in result.output.lower()


class TestAnalysisTerminalOutput:
    def test_analysis_terminal_output(self, runner: CliRunner) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_ANALYSIS_RESPONSE

        mock_client = _make_mock_client(mock_resp)

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "simulation", "analysis", "sim-abc-123"])

        assert result.exit_code == 0
        assert "Rating Distribution" in result.output
        assert "HELPFUL" in result.output
        assert "Consensus" in result.output
        assert "0.85" in result.output
        assert "0.12" in result.output
        assert "Scoring" in result.output
        assert "MODERATE" in result.output
        assert "Skeptic" in result.output
        assert "Optimist" in result.output
        assert "Note Quality" in result.output
        assert "0.72" in result.output


class TestAnalysisMarkdownOutput:
    def test_analysis_markdown_output(self, runner: CliRunner) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_ANALYSIS_RESPONSE

        mock_client = _make_mock_client(mock_resp)

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--format", "markdown", "sim-abc-123"]
            )

        assert result.exit_code == 0
        assert "# Simulation Analysis: sim-abc-123" in result.output
        assert "## Rating Distribution" in result.output
        assert "| Rating | Count | % |" in result.output
        assert "HELPFUL" in result.output
        assert "## Consensus Metrics" in result.output
        assert "Mean agreement: 0.85" in result.output
        assert "Polarization index: 0.12" in result.output
        assert "## Scoring Coverage" in result.output
        assert "MODERATE" in result.output
        assert "## Agent Behaviors" in result.output
        assert "Skeptic" in result.output
        assert "## Note Quality" in result.output
        assert "0.72" in result.output


class TestAnalysisJsonOutput:
    def test_analysis_json_output(self, runner: CliRunner) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_ANALYSIS_RESPONSE

        mock_client = _make_mock_client(mock_resp)

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "--json", "simulation", "analysis", "sim-abc-123"]
            )

        assert result.exit_code == 0
        assert "simulation-analysis" in result.output
        assert "sim-abc-123" in result.output
        assert "rating_distribution" in result.output


EMPTY_ANALYSIS_RESPONSE: dict = {
    "data": {
        "type": "simulation-analysis",
        "id": "sim-empty-001",
        "attributes": {
            "rating_distribution": {"overall": {}, "per_agent": [], "total_ratings": 0},
            "consensus_metrics": {
                "mean_agreement": None,
                "polarization_index": None,
                "notes_with_consensus": 0,
                "notes_with_disagreement": 0,
                "total_notes_rated": 0,
            },
            "scoring_coverage": {
                "current_tier": None,
                "total_scores_computed": 0,
                "tier_distribution": {},
                "scorer_breakdown": {},
                "notes_by_status": {},
            },
            "agent_behaviors": [],
            "note_quality": {
                "avg_helpfulness_score": None,
                "notes_by_status": {},
                "notes_by_classification": {},
            },
        },
    }
}


class TestAnalysisEmptyData:
    def test_empty_analysis_terminal(self, runner: CliRunner) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = EMPTY_ANALYSIS_RESPONSE

        mock_client = _make_mock_client(mock_resp)

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "simulation", "analysis", "sim-empty-001"])

        assert result.exit_code == 0
        assert "not available yet" in result.output

    def test_empty_analysis_markdown(self, runner: CliRunner) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = EMPTY_ANALYSIS_RESPONSE

        mock_client = _make_mock_client(mock_resp)

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--format", "markdown", "sim-empty-001"]
            )

        assert result.exit_code == 0
        assert "not available yet" in result.output


class TestAnalysisNotFound:
    def test_analysis_not_found(self, runner: CliRunner) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {
            "errors": [{"detail": "Simulation not found"}]
        }

        mock_client = _make_mock_client(mock_resp)

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "simulation", "analysis", "nonexistent-id"])

        assert result.exit_code != 0
