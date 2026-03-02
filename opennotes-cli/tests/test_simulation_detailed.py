from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from opennotes_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _make_csrf_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    return resp


def _make_page_response(
    simulation_id: str,
    notes: list[dict],
    ratings: list[dict],
    requests: list[dict],
    page_number: int,
    total_pages: int,
    total_items: int,
    page_size: int = 50,
) -> MagicMock:
    links: dict = {
        "self": f"/api/v2/simulations/{simulation_id}/analysis/detailed?page[number]={page_number}&page[size]={page_size}",
    }
    if page_number < total_pages:
        links["next"] = f"/api/v2/simulations/{simulation_id}/analysis/detailed?page[number]={page_number + 1}&page[size]={page_size}"
    if page_number > 1:
        links["prev"] = f"/api/v2/simulations/{simulation_id}/analysis/detailed?page[number]={page_number - 1}&page[size]={page_size}"
    links["last"] = f"/api/v2/simulations/{simulation_id}/analysis/detailed?page[number]={total_pages}&page[size]={page_size}"

    body = {
        "data": {
            "type": "simulation-analysis-detailed",
            "id": simulation_id,
            "attributes": {
                "notes": notes,
                "ratings": ratings,
                "requests": requests,
            },
        },
        "links": links,
        "meta": {
            "page": {
                "number": page_number,
                "size": page_size,
                "total_pages": total_pages,
                "total_items": total_items,
            }
        },
    }

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    return resp


SAMPLE_NOTES = [
    {
        "note_id": "note-001",
        "summary": "This claim is misleading because statistics are cherry-picked",
        "classification": "MISINFORMATION",
        "status": "scored",
        "helpfulness_score": 0.85,
        "author_agent": "Skeptic",
        "request_id": "req-001",
        "created_at": "2026-03-01T10:00:00Z",
    },
    {
        "note_id": "note-002",
        "summary": "The source is generally reliable and well-cited",
        "classification": "ACCURATE",
        "status": "scored",
        "helpfulness_score": 0.72,
        "author_agent": "Optimist",
        "request_id": "req-002",
        "created_at": "2026-03-01T10:05:00Z",
    },
]

SAMPLE_RATINGS = [
    {
        "note_id": "note-001",
        "note_summary": "This claim is misleading because statistics are cherry-picked",
        "rater_agent": "Optimist",
        "helpfulness_level": "HELPFUL",
        "created_at": "2026-03-01T10:10:00Z",
    },
    {
        "note_id": "note-002",
        "note_summary": "The source is generally reliable and well-cited",
        "rater_agent": "Skeptic",
        "helpfulness_level": "SOMEWHAT_HELPFUL",
        "created_at": "2026-03-01T10:15:00Z",
    },
]

SAMPLE_REQUESTS = [
    {
        "request_id": "req-001",
        "content": "https://example.com/article-1",
        "content_type": "url",
        "note_count": 3,
        "variance_score": 0.92,
    },
    {
        "request_id": "req-002",
        "content": "Some user-submitted text claim about vaccines",
        "content_type": "text",
        "note_count": 2,
        "variance_score": 0.45,
    },
]

SIM_ID = "sim-detailed-001"


def _make_single_page_client() -> MagicMock:
    csrf_resp = _make_csrf_response()
    page_resp = _make_page_response(
        SIM_ID, SAMPLE_NOTES, SAMPLE_RATINGS, SAMPLE_REQUESTS,
        page_number=1, total_pages=1, total_items=2,
    )
    mock_client = MagicMock()
    mock_client.get.side_effect = [csrf_resp, page_resp]
    mock_client.cookies = MagicMock()
    mock_client.cookies.get.return_value = "test-csrf"
    return mock_client


def _make_multi_page_client() -> MagicMock:
    csrf_resp = _make_csrf_response()
    page1_resp = _make_page_response(
        SIM_ID, SAMPLE_NOTES[:1], SAMPLE_RATINGS[:1], SAMPLE_REQUESTS[:1],
        page_number=1, total_pages=2, total_items=4, page_size=1,
    )
    page2_resp = _make_page_response(
        SIM_ID, SAMPLE_NOTES[1:], SAMPLE_RATINGS[1:], SAMPLE_REQUESTS[1:],
        page_number=2, total_pages=2, total_items=4, page_size=1,
    )
    mock_client = MagicMock()
    mock_client.get.side_effect = [csrf_resp, page1_resp, page2_resp]
    mock_client.cookies = MagicMock()
    mock_client.cookies.get.return_value = "test-csrf"
    return mock_client


class TestDetailedFlagRegistered:
    def test_detailed_flag_in_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["simulation", "analysis", "--help"])
        assert result.exit_code == 0
        assert "--detailed" in result.output

    def test_format_choices_include_xlsx(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["simulation", "analysis", "--help"])
        assert result.exit_code == 0
        assert "xlsx" in result.output


class TestDetailedTerminalOutput:
    def test_terminal_shows_notes(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", SIM_ID]
            )
        assert result.exit_code == 0
        assert "note-001" in result.output
        assert "Ske" in result.output
        assert "MI" in result.output

    def test_terminal_shows_ratings(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", SIM_ID]
            )
        assert result.exit_code == 0
        assert "HELPFUL" in result.output
        assert "Optimist" in result.output

    def test_terminal_shows_requests(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", SIM_ID]
            )
        assert result.exit_code == 0
        assert "req-001" in result.output
        assert "example.com" in result.output

    def test_terminal_shows_variance_summary(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", SIM_ID]
            )
        assert result.exit_code == 0
        assert "0.92" in result.output
        assert "0.45" in result.output


class TestDetailedMarkdownOutput:
    def test_markdown_has_notes_section(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert "# Detailed Simulation Analysis" in result.output
        assert "## Notes" in result.output
        assert "note-001" in result.output
        assert "Skeptic" in result.output

    def test_markdown_has_ratings_section(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert "## Ratings" in result.output
        assert "HELPFUL" in result.output

    def test_markdown_has_requests_section(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert "## Requests" in result.output
        assert "req-001" in result.output

    def test_markdown_has_variance_summary(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert "## Request Variance Summary" in result.output
        assert "0.92" in result.output


class TestPaginationAccumulation:
    def test_accumulates_all_pages(self, runner: CliRunner) -> None:
        mock_client = _make_multi_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert "note-001" in result.output
        assert "note-002" in result.output
        assert "req-001" in result.output
        assert "req-002" in result.output

    def test_pagination_calls_correct_urls(self, runner: CliRunner) -> None:
        mock_client = _make_multi_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", SIM_ID]
            )
        get_calls = mock_client.get.call_args_list
        assert len(get_calls) == 3


class TestExistingAnalysisUnchanged:
    def test_existing_analysis_without_detailed_flag(self, runner: CliRunner) -> None:
        sample_response = {
            "data": {
                "type": "simulation-analysis",
                "id": "sim-abc-123",
                "attributes": {
                    "rating_distribution": {
                        "overall": {"HELPFUL": 5},
                        "per_agent": [],
                        "total_ratings": 5,
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
                        "tier_distribution": {},
                        "scorer_breakdown": {},
                        "notes_by_status": {},
                    },
                    "agent_behaviors": [],
                    "note_quality": {
                        "avg_helpfulness_score": 0.72,
                        "notes_by_status": {},
                        "notes_by_classification": {},
                    },
                },
            }
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_response

        csrf_resp = _make_csrf_response()
        mock_client = MagicMock()
        mock_client.get.side_effect = [csrf_resp, mock_resp]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "sim-abc-123"]
            )

        assert result.exit_code == 0
        assert "Rating Distribution" in result.output
        assert "0.85" in result.output
        get_calls = mock_client.get.call_args_list
        assert len(get_calls) == 2
        analysis_url = get_calls[1][0][0]
        assert "/analysis/detailed" not in analysis_url
        assert "/analysis" in analysis_url
