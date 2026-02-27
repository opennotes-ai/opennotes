from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

from opennotes_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _mock_csrf_response() -> httpx.Response:
    return httpx.Response(200, text="OK", request=httpx.Request("GET", "http://test"))


class TestScoreCommand:
    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["score", "--help"])
        assert result.exit_code == 0
        assert "community_server_id" in result.output.lower()

    def test_score_success(self, runner: CliRunner) -> None:
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
            result = runner.invoke(cli, ["--local", "score", "guild-123"])

        assert result.exit_code == 0
        assert "score-community-abc123" in result.output

    def test_score_json_output(self, runner: CliRunner) -> None:
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
            result = runner.invoke(cli, ["--local", "--json", "score", "guild-456"])

        assert result.exit_code == 0
        assert "wf-xyz" in result.output

    def test_score_409_already_in_progress(self, runner: CliRunner) -> None:
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
            result = runner.invoke(cli, ["--local", "score", "guild-789"])

        assert result.exit_code == 0
        assert "already in progress" in result.output.lower()

    def test_score_404_not_found(self, runner: CliRunner) -> None:
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
            result = runner.invoke(cli, ["--local", "score", "unknown-guild"])

        assert result.exit_code != 0
