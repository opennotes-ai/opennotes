from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

from opennotes_cli.cli import CliContext, cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _mock_csrf_response() -> httpx.Response:
    resp = httpx.Response(200, text="OK", request=httpx.Request("GET", "http://test"))
    return resp


class TestCliGroup:
    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "OpenNotes CLI" in result.output

    def test_local_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--local", "--help"])
        assert result.exit_code == 0

    def test_env_option(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["-e", "staging", "--help"])
        assert result.exit_code == 0

    def test_json_option(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--json", "--help"])
        assert result.exit_code == 0

    def test_verbose_option(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["-v", "--help"])
        assert result.exit_code == 0


class TestAllCommandsRegistered:
    @pytest.mark.parametrize(
        "cmd",
        [
            "health",
            "hybrid-search",
            "rechunk",
            "fact-check",
            "batch",
            "simulation",
            "sim-agent",
            "orchestrator",
            "playground",
        ],
    )
    def test_command_registered(self, runner: CliRunner, cmd: str) -> None:
        result = runner.invoke(cli, [cmd, "--help"])
        assert result.exit_code == 0, f"Command '{cmd}' failed: {result.output}"


class TestRechunkSubcommands:
    @pytest.mark.parametrize(
        "subcmd",
        ["factchecks", "previously-seen", "status", "delete", "list"],
    )
    def test_subcommand_registered(self, runner: CliRunner, subcmd: str) -> None:
        result = runner.invoke(cli, ["rechunk", subcmd, "--help"])
        assert result.exit_code == 0, f"rechunk {subcmd} failed: {result.output}"


class TestCandidateSubcommands:
    @pytest.mark.parametrize(
        "subcmd",
        ["import", "scrape", "promote", "list", "set-rating", "approve-predicted"],
    )
    def test_subcommand_registered(self, runner: CliRunner, subcmd: str) -> None:
        result = runner.invoke(cli, ["fact-check", "candidates", subcmd, "--help"])
        assert result.exit_code == 0, f"candidates {subcmd} failed: {result.output}"


class TestBatchSubcommands:
    @pytest.mark.parametrize("subcmd", ["status", "list", "cancel"])
    def test_subcommand_registered(self, runner: CliRunner, subcmd: str) -> None:
        result = runner.invoke(cli, ["batch", subcmd, "--help"])
        assert result.exit_code == 0, f"batch {subcmd} failed: {result.output}"


class TestSimulationSubcommands:
    @pytest.mark.parametrize(
        "subcmd", ["list", "status", "create", "pause", "resume", "cancel"]
    )
    def test_subcommand_registered(self, runner: CliRunner, subcmd: str) -> None:
        result = runner.invoke(cli, ["simulation", subcmd, "--help"])
        assert result.exit_code == 0, f"simulation {subcmd} failed: {result.output}"


class TestSimAgentSubcommands:
    @pytest.mark.parametrize("subcmd", ["list", "get", "create"])
    def test_subcommand_registered(self, runner: CliRunner, subcmd: str) -> None:
        result = runner.invoke(cli, ["sim-agent", subcmd, "--help"])
        assert result.exit_code == 0, f"sim-agent {subcmd} failed: {result.output}"


class TestOrchestratorSubcommands:
    @pytest.mark.parametrize("subcmd", ["list", "get", "create"])
    def test_subcommand_registered(self, runner: CliRunner, subcmd: str) -> None:
        result = runner.invoke(cli, ["orchestrator", subcmd, "--help"])
        assert result.exit_code == 0, f"orchestrator {subcmd} failed: {result.output}"


class TestPlaygroundSubcommands:
    @pytest.mark.parametrize("subcmd", ["create", "add-request"])
    def test_subcommand_registered(self, runner: CliRunner, subcmd: str) -> None:
        result = runner.invoke(cli, ["playground", subcmd, "--help"])
        assert result.exit_code == 0, f"playground {subcmd} failed: {result.output}"


class TestHealthCommand:
    def test_health_json_output(self, runner: CliRunner) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok"}'
        mock_response.json.return_value = {"status": "ok"}

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = None

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "--json", "health"])

        assert result.exit_code == 0
        assert "environment" in result.output


class TestDisplayHelpers:
    def test_get_status_style(self) -> None:
        from opennotes_cli.display import get_status_style

        color, symbol = get_status_style("completed")
        assert color == "green"
        assert "\u2713" in symbol

        color, symbol = get_status_style("failed")
        assert color == "red"

        color, symbol = get_status_style("pending")
        assert color == "yellow"

        color, symbol = get_status_style("unknown_status")
        assert color == "white"

    def test_handle_jsonapi_error_success(self) -> None:
        from opennotes_cli.display import handle_jsonapi_error

        mock_response = MagicMock()
        mock_response.status_code = 200
        handle_jsonapi_error(mock_response)

    def test_handle_jsonapi_error_401(self) -> None:
        from opennotes_cli.display import handle_jsonapi_error

        mock_response = MagicMock()
        mock_response.status_code = 401
        with pytest.raises(SystemExit):
            handle_jsonapi_error(mock_response)

    def test_handle_jsonapi_error_404(self) -> None:
        from opennotes_cli.display import handle_jsonapi_error

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "errors": [{"detail": "Not found"}]
        }
        with pytest.raises(SystemExit):
            handle_jsonapi_error(mock_response)


class TestCliContext:
    def test_base_url_from_auth(self) -> None:
        from opennotes_cli.auth import JwtAuthProvider

        auth = JwtAuthProvider(server_url="http://test:8000")
        client = MagicMock()
        ctx = CliContext(
            auth=auth,
            json_output=False,
            verbose=False,
            env_name="test",
            client=client,
        )
        assert ctx.base_url == "http://test:8000"


class TestHttpHelpers:
    def test_add_csrf(self) -> None:
        from opennotes_cli.http import add_csrf

        headers = {"Content-Type": "application/json"}
        result = add_csrf(headers, "my-csrf-token")
        assert result["X-CSRF-Token"] == "my-csrf-token"

    def test_add_csrf_none(self) -> None:
        from opennotes_cli.http import add_csrf

        headers = {"Content-Type": "application/json"}
        result = add_csrf(headers, None)
        assert "X-CSRF-Token" not in result

    def test_env_urls(self) -> None:
        from opennotes_cli.http import ENV_URLS

        assert "local" in ENV_URLS
        assert "staging" in ENV_URLS
        assert "production" in ENV_URLS
        assert ENV_URLS["local"] == "http://localhost:8000"
