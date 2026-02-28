from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from click.testing import CliRunner

from opennotes_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


class TestScoreCommand:
    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["score", "--help"])
        assert result.exit_code == 0
        assert "community_server_id" in result.output.lower()

    def test_score_success(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_csrf_resp = MagicMock()
        mock_csrf_resp.status_code = 200

        mock_score_resp = MagicMock()
        mock_score_resp.status_code = 202
        mock_score_resp.json.return_value = {
            "workflow_id": "score-community-abc123",
            "message": "Scoring workflow dispatched",
        }

        mock_client = MagicMock()
        mock_client.get.return_value = mock_csrf_resp
        mock_client.post.return_value = mock_score_resp
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "score", community_id])

        assert result.exit_code == 0
        assert "score-community-abc123" in result.output

    def test_score_json_output(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_csrf_resp = MagicMock()
        mock_csrf_resp.status_code = 200

        mock_score_resp = MagicMock()
        mock_score_resp.status_code = 202
        mock_score_resp.json.return_value = {
            "workflow_id": "wf-xyz",
            "message": "Scoring dispatched",
        }

        mock_client = MagicMock()
        mock_client.get.return_value = mock_csrf_resp
        mock_client.post.return_value = mock_score_resp
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = None

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "--json", "score", community_id])

        assert result.exit_code == 0
        assert "wf-xyz" in result.output

    def test_score_409_already_in_progress(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_csrf_resp = MagicMock()
        mock_csrf_resp.status_code = 200

        mock_score_resp = MagicMock()
        mock_score_resp.status_code = 409

        mock_client = MagicMock()
        mock_client.get.return_value = mock_csrf_resp
        mock_client.post.return_value = mock_score_resp
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = None

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "score", community_id])

        assert result.exit_code == 0
        assert "already in progress" in result.output.lower()

    def test_score_404_not_found(self, runner: CliRunner) -> None:
        community_id = str(uuid4())

        mock_csrf_resp = MagicMock()
        mock_csrf_resp.status_code = 200

        mock_score_resp = MagicMock()
        mock_score_resp.status_code = 404
        mock_score_resp.text = "Not Found"

        mock_client = MagicMock()
        mock_client.get.return_value = mock_csrf_resp
        mock_client.post.return_value = mock_score_resp
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = None

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "score", community_id])

        assert result.exit_code != 0

    def test_score_rejects_non_uuid(self, runner: CliRunner) -> None:
        with patch("opennotes_cli.cli.httpx.Client", return_value=MagicMock()):
            result = runner.invoke(cli, ["--local", "score", "guild-123"])

        assert result.exit_code != 0
        assert "invalid community server id" in result.output.lower()
        assert "expected a uuid" in result.output.lower()

    def test_score_rejects_empty_string(self, runner: CliRunner) -> None:
        with patch("opennotes_cli.cli.httpx.Client", return_value=MagicMock()):
            result = runner.invoke(cli, ["--local", "score", "not-a-uuid-at-all"])

        assert result.exit_code != 0
        assert "expected a uuid" in result.output.lower()
