from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from click.testing import CliRunner

from opennotes_cli.cli import cli
from opennotes_cli.commands.analyze import analyze


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


class TestAnalyzeCommandGroup:
    def test_analyze_is_click_group(self):
        import click

        assert isinstance(analyze, click.Group)

    def test_mf_subcommand_exists(self):
        assert "mf" in analyze.commands

    def test_mf_command_has_rescore_option(self):
        mf_cmd = analyze.commands["mf"]
        param_names = [p.name for p in mf_cmd.params]
        assert "rescore" in param_names

    def test_mf_command_has_format_option(self):
        mf_cmd = analyze.commands["mf"]
        param_names = [p.name for p in mf_cmd.params]
        assert "fmt" in param_names

    def test_mf_command_has_sections_option(self):
        mf_cmd = analyze.commands["mf"]
        param_names = [p.name for p in mf_cmd.params]
        assert "sections" in param_names

    def test_mf_command_has_no_prompt_option(self):
        mf_cmd = analyze.commands["mf"]
        param_names = [p.name for p in mf_cmd.params]
        assert "no_prompt" in param_names


class TestTriggerRescore:
    def test_reads_workflow_id_from_flat_response(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_csrf_resp = MagicMock()
        mock_csrf_resp.status_code = 200

        mock_score_resp = MagicMock()
        mock_score_resp.status_code = 202
        mock_score_resp.json.return_value = {
            "workflow_id": "score-community-test123",
            "message": "Scoring workflow dispatched",
        }

        mock_analysis_resp = MagicMock()
        mock_analysis_resp.status_code = 200
        mock_analysis_resp.json.return_value = {
            "data": {
                "attributes": {
                    "rater_factors": [],
                    "note_factors": [],
                    "scored_at": "2026-01-01",
                    "tier": "FULL",
                    "global_intercept": 0.0,
                    "rater_count": 0,
                    "note_count": 0,
                }
            }
        }

        mock_client = MagicMock()
        mock_client.get.side_effect = [mock_csrf_resp, mock_analysis_resp]
        mock_client.post.return_value = mock_score_resp
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["--local", "analyze", "mf", "--rescore", "--no-prompt", community_id],
            )

        assert result.exit_code == 0
        assert "score-community-test123" in result.output
        assert "background" in result.output.lower()

    def test_handles_409_conflict(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_csrf_resp = MagicMock()
        mock_csrf_resp.status_code = 200

        mock_score_resp = MagicMock()
        mock_score_resp.status_code = 409

        mock_analysis_resp = MagicMock()
        mock_analysis_resp.status_code = 200
        mock_analysis_resp.json.return_value = {
            "data": {
                "attributes": {
                    "rater_factors": [],
                    "note_factors": [],
                    "scored_at": "2026-01-01",
                    "tier": "FULL",
                    "global_intercept": 0.0,
                    "rater_count": 0,
                    "note_count": 0,
                }
            }
        }

        mock_client = MagicMock()
        mock_client.get.side_effect = [mock_csrf_resp, mock_analysis_resp]
        mock_client.post.return_value = mock_score_resp
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["--local", "analyze", "mf", "--rescore", "--no-prompt", community_id],
            )

        assert result.exit_code == 0
        assert "already in progress" in result.output.lower()

    def test_no_batch_job_polling(self) -> None:
        from opennotes_cli.commands import analyze as analyze_mod

        assert not hasattr(analyze_mod, "poll_batch_job_until_complete") or \
            "poll_batch_job_until_complete" not in dir(analyze_mod)


class TestNetworkErrorHandling:
    def test_fetch_analysis_connection_error(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["--local", "analyze", "mf", "--no-prompt", community_id],
            )

        assert result.exit_code != 0
        assert "could not connect" in result.output.lower()

    def test_fetch_analysis_timeout(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ReadTimeout("Read timed out")

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["--local", "analyze", "mf", "--no-prompt", community_id],
            )

        assert result.exit_code != 0
        assert "timed out" in result.output.lower()

    def test_trigger_rescore_connection_error(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_csrf_resp = MagicMock()
        mock_csrf_resp.status_code = 200

        mock_client = MagicMock()
        mock_client.get.return_value = mock_csrf_resp
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["--local", "analyze", "mf", "--rescore", "--no-prompt", community_id],
            )

        assert result.exit_code != 0
        assert "could not connect" in result.output.lower()

    def test_history_connection_error(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["--local", "analyze", "mf", "--history", community_id],
            )

        assert result.exit_code != 0
        assert "could not connect" in result.output.lower()

    def test_csrf_token_connection_error(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                ["--local", "analyze", "mf", "--rescore", "--no-prompt", community_id],
            )

        assert result.exit_code != 0
        assert "could not connect" in result.output.lower()
