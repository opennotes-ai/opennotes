from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from opennotes_cli.cli import cli
from opennotes_cli.commands.simulation import _escape_md


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _make_csrf_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    return resp


SAMPLE_NOTE_RESOURCES = [
    {
        "type": "simulation-detailed-notes",
        "id": "note-001",
        "attributes": {
            "note_id": "note-001",
            "summary": "This claim is misleading because statistics are cherry-picked",
            "classification": "MISINFORMATION",
            "status": "scored",
            "helpfulness_score": 0.85,
            "author_agent_name": "Skeptic",
            "author_agent_profile_id": "skeptic-1",
            "request_id": "req-001",
            "created_at": "2026-03-01T10:00:00Z",
            "ratings": [
                {
                    "rater_agent_name": "Optimist",
                    "rater_agent_profile_id": "optimist-1",
                    "helpfulness_level": "HELPFUL",
                    "created_at": "2026-03-01T10:10:00Z",
                }
            ],
        },
    },
    {
        "type": "simulation-detailed-notes",
        "id": "note-002",
        "attributes": {
            "note_id": "note-002",
            "summary": "The source is generally reliable and well-cited",
            "classification": "ACCURATE",
            "status": "scored",
            "helpfulness_score": 0.72,
            "author_agent_name": "Optimist",
            "author_agent_profile_id": "optimist-1",
            "request_id": "req-002",
            "created_at": "2026-03-01T10:05:00Z",
            "ratings": [
                {
                    "rater_agent_name": "Skeptic",
                    "rater_agent_profile_id": "skeptic-1",
                    "helpfulness_level": "SOMEWHAT_HELPFUL",
                    "created_at": "2026-03-01T10:15:00Z",
                }
            ],
        },
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

SAMPLE_AGENTS = [
    {
        "agent_profile_id": "inst-001",
        "agent_name": "Skeptic",
        "personality": "Critical thinker who challenges claims",
        "model_name": "gpt-4o",
        "memory_compaction_strategy": "sliding_window",
        "turn_count": 5,
        "state": "active",
        "token_count": 1200,
        "recent_actions": ["rate_note", "write_note"],
        "last_messages": [{"role": "assistant", "content": "Analyzing claim..."}],
    },
    {
        "agent_profile_id": "inst-002",
        "agent_name": "Optimist",
        "personality": "Sees the best in sources",
        "model_name": "claude-sonnet-4-20250514",
        "memory_compaction_strategy": "summarize",
        "turn_count": 3,
        "state": "active",
        "token_count": 800,
        "recent_actions": ["write_note"],
        "last_messages": [],
    },
]


def _make_page_response(
    simulation_id: str,
    note_resources: list[dict],
    requests: list[dict],
    page_number: int,
    total_pages: int,
    total_items: int,
    page_size: int = 50,
    agents: list[dict] | None = None,
) -> MagicMock:
    links: dict = {
        "self": f"/api/v2/simulations/{simulation_id}/analysis/detailed?page[number]={page_number}&page[size]={page_size}",
        "next": (
            f"/api/v2/simulations/{simulation_id}/analysis/detailed?page[number]={page_number + 1}&page[size]={page_size}"
            if page_number < total_pages
            else None
        ),
        "last": f"/api/v2/simulations/{simulation_id}/analysis/detailed?page[number]={total_pages}&page[size]={page_size}",
    }
    if page_number > 1:
        links["prev"] = f"/api/v2/simulations/{simulation_id}/analysis/detailed?page[number]={page_number - 1}&page[size]={page_size}"

    body = {
        "data": note_resources,
        "links": links,
        "meta": {
            "count": total_items,
            "request_variance": {
                "requests": requests,
                "total_requests": len(requests),
            },
            "agents": agents if agents is not None else [],
        },
    }

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    return resp

SIM_ID = "019536b8-bdb2-7c81-8975-77f5c3dbdff8"


def _make_single_page_client() -> MagicMock:
    csrf_resp = _make_csrf_response()
    page_resp = _make_page_response(
        SIM_ID, SAMPLE_NOTE_RESOURCES, SAMPLE_REQUESTS,
        page_number=1, total_pages=1, total_items=2,
        agents=SAMPLE_AGENTS,
    )
    mock_client = MagicMock()
    mock_client.get.side_effect = [csrf_resp, page_resp]
    mock_client.cookies = MagicMock()
    mock_client.cookies.get.return_value = "test-csrf"
    return mock_client


def _make_multi_page_client() -> MagicMock:
    csrf_resp = _make_csrf_response()
    page1_resp = _make_page_response(
        SIM_ID, SAMPLE_NOTE_RESOURCES[:1], SAMPLE_REQUESTS,
        page_number=1, total_pages=2, total_items=2, page_size=1,
        agents=SAMPLE_AGENTS,
    )
    page2_resp = _make_page_response(
        SIM_ID, SAMPLE_NOTE_RESOURCES[1:], SAMPLE_REQUESTS,
        page_number=2, total_pages=2, total_items=2, page_size=1,
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
        output = result.output.replace("\u200b", "")
        assert "note-001" in output
        assert "Ske" in output
        assert "MI" in output

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
        assert "req-001" in result.output.replace("\u200b", "")
        assert "https://example.com/article-1" in result.output

    def test_terminal_shows_variance_summary(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", SIM_ID]
            )
        assert result.exit_code == 0
        assert "0.92" in result.output
        assert "0.45" in result.output

    def test_terminal_shows_agents_table(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", SIM_ID]
            )
        assert result.exit_code == 0
        assert "Agents" in result.output
        assert "Skeptic" in result.output
        assert "Optimist" in result.output
        assert "gpt-4o" in result.output
        assert "active" in result.output

    def test_terminal_shows_agent_count_in_header(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", SIM_ID]
            )
        assert result.exit_code == 0
        assert "Agents" in result.output
        assert "2" in result.output


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
        assert "note-001" in result.output.replace("\u200b", "")
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
        assert "req-001" in result.output.replace("\u200b", "")

    def test_markdown_has_variance_summary(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert "## Request Variance Summary" in result.output
        assert "0.92" in result.output

    def test_markdown_has_agents_section(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert "## Agents" in result.output
        assert "Skeptic" in result.output
        assert "Optimist" in result.output
        assert "gpt-4o" in result.output
        assert "sliding_window" in result.output
        assert "1 messages" in result.output

    def test_markdown_agents_count_in_summary(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert "- Agents: 2" in result.output


class TestPaginationAccumulation:
    def test_accumulates_all_pages(self, runner: CliRunner) -> None:
        mock_client = _make_multi_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        output = result.output.replace("\u200b", "")
        assert "note-001" in output
        assert "note-002" in output
        assert "req-001" in output
        assert "req-002" in output

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
                cli, ["--local", "simulation", "analysis", "019536b8-bdb2-7c81-8975-77f5c3dbdff8"]
            )

        assert result.exit_code == 0
        assert "Rating Distribution" in result.output
        assert "0.85" in result.output
        get_calls = mock_client.get.call_args_list
        assert len(get_calls) == 2
        analysis_url = get_calls[1][0][0]
        assert "/analysis/detailed" not in analysis_url
        assert "/analysis" in analysis_url


HUUID_SIM_ID = "Vudrotlab-Kuvkattor-Tevzelpim-Liksiksas"


class TestDetailedHuuidInput:
    def test_detailed_accepts_huuid(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", HUUID_SIM_ID]
            )
        assert result.exit_code == 0
        assert "note-001" in result.output.replace("\u200b", "")


class TestDetailedUuidFlag:
    def test_uuid_flag_shows_raw_uuid(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "--uuid", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert SIM_ID in result.output.replace("\u200b", "")

    def test_default_shows_huuid(self, runner: CliRunner) -> None:
        mock_client = _make_single_page_client()
        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert HUUID_SIM_ID in result.output.replace("\u200b", "")


class TestEscapeMdHelper:
    def test_escapes_pipe(self) -> None:
        assert _escape_md("a | b") == "a \\| b"

    def test_no_pipe_unchanged(self) -> None:
        assert _escape_md("no pipes here") == "no pipes here"

    def test_multiple_pipes(self) -> None:
        assert _escape_md("a|b|c") == "a\\|b\\|c"

    def test_empty_string(self) -> None:
        assert _escape_md("") == ""


class TestMarkdownPipeEscaping:
    def test_pipe_in_summary_is_escaped(self, runner: CliRunner) -> None:
        note_with_pipe = [
            {
                "type": "simulation-detailed-notes",
                "id": "note-pipe",
                "attributes": {
                    "note_id": "note-pipe",
                    "summary": "True | False claim",
                    "classification": "MISINFORMATION",
                    "status": "scored",
                    "helpfulness_score": 0.5,
                    "author_agent_name": "Agent|One",
                    "author_agent_profile_id": "a1",
                    "request_id": "req-p",
                    "created_at": "2026-03-01T10:00:00Z",
                    "ratings": [
                        {
                            "rater_agent_name": "Agent|Two",
                            "rater_agent_profile_id": "a2",
                            "helpfulness_level": "HELPFUL",
                            "created_at": "2026-03-01T10:10:00Z",
                        }
                    ],
                },
            },
        ]
        pipe_requests = [
            {
                "request_id": "req-p",
                "content": "text with | pipe char",
                "content_type": "text",
                "note_count": 1,
                "variance_score": 0.5,
            },
        ]

        csrf_resp = _make_csrf_response()
        page_resp = _make_page_response(
            SIM_ID, note_with_pipe, pipe_requests,
            page_number=1, total_pages=1, total_items=1,
        )
        mock_client = MagicMock()
        mock_client.get.side_effect = [csrf_resp, page_resp]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli, ["--local", "simulation", "analysis", "--detailed", "--format", "markdown", SIM_ID]
            )
        assert result.exit_code == 0
        assert "True \\| False claim" in result.output
        assert "Agent\\|One" in result.output
        assert "Agent\\|Two" in result.output
        assert "text with \\| pipe char" in result.output
