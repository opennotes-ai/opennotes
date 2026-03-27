from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

from opennotes_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


SAMPLE_ATTRS = {
    "name": "test-orch",
    "turn_cadence_seconds": 15,
    "max_active_agents": 10,
    "max_total_spawns": 100,
    "removal_rate": 0.1,
    "max_turns_per_agent": 50,
    "is_active": True,
    "agent_profile_ids": ["019572a1-0000-7000-8000-aaaaaaaaaaaa"],
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}

ORCH_ID = "019572a1-0000-7000-8000-000000000001"


def _make_csrf_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    return resp


def _make_orch_response(attrs: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": {
            "type": "simulation-orchestrators",
            "id": ORCH_ID,
            "attributes": attrs or SAMPLE_ATTRS,
        }
    }
    return resp


class TestOrchestratorCreateFields:
    def test_create_help_shows_max_active_agents(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["orchestrator", "create", "--help"])
        assert result.exit_code == 0
        assert "--max-active-agents" in result.output

    def test_create_help_shows_max_total_spawns(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["orchestrator", "create", "--help"])
        assert result.exit_code == 0
        assert "--max-total-spawns" in result.output

    def test_create_sends_max_active_agents_in_payload(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.post.side_effect = [_make_orch_response()]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                [
                    "--local",
                    "orchestrator",
                    "create",
                    "--name",
                    "test",
                    "--agent-ids",
                    "019572a1-0000-7000-8000-aaaaaaaaaaaa",
                    "--turn-cadence",
                    "15",
                    "--max-active-agents",
                    "10",
                    "--removal-rate",
                    "0.1",
                    "--max-turns",
                    "50",
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        post_call = mock_client.post.call_args
        payload = post_call.kwargs.get("json", {})
        attrs = payload["data"]["attributes"]
        assert "max_active_agents" in attrs
        assert attrs["max_active_agents"] == 10
        assert "max_agents" not in attrs

    def test_create_sends_max_total_spawns_in_payload(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.post.side_effect = [_make_orch_response()]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                [
                    "--local",
                    "orchestrator",
                    "create",
                    "--name",
                    "test",
                    "--agent-ids",
                    "019572a1-0000-7000-8000-aaaaaaaaaaaa",
                    "--turn-cadence",
                    "15",
                    "--max-active-agents",
                    "10",
                    "--max-total-spawns",
                    "100",
                    "--removal-rate",
                    "0.1",
                    "--max-turns",
                    "50",
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        post_call = mock_client.post.call_args
        payload = post_call.kwargs.get("json", {})
        attrs = payload["data"]["attributes"]
        assert "max_total_spawns" in attrs
        assert attrs["max_total_spawns"] == 100

    def test_deprecated_max_agents_alias_still_works(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.post.side_effect = [_make_orch_response()]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                [
                    "--local",
                    "orchestrator",
                    "create",
                    "--name",
                    "test",
                    "--agent-ids",
                    "019572a1-0000-7000-8000-aaaaaaaaaaaa",
                    "--turn-cadence",
                    "15",
                    "--max-agents",
                    "10",
                    "--removal-rate",
                    "0.1",
                    "--max-turns",
                    "50",
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        post_call = mock_client.post.call_args
        payload = post_call.kwargs.get("json", {})
        attrs = payload["data"]["attributes"]
        assert "max_active_agents" in attrs
        assert attrs["max_active_agents"] == 10
        assert "max_agents" not in attrs

    def test_create_omits_max_total_spawns_when_not_provided(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.post.side_effect = [_make_orch_response()]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                [
                    "--local",
                    "orchestrator",
                    "create",
                    "--name",
                    "test",
                    "--agent-ids",
                    "019572a1-0000-7000-8000-aaaaaaaaaaaa",
                    "--turn-cadence",
                    "15",
                    "--max-active-agents",
                    "10",
                    "--removal-rate",
                    "0.1",
                    "--max-turns",
                    "50",
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        post_call = mock_client.post.call_args
        payload = post_call.kwargs.get("json", {})
        attrs = payload["data"]["attributes"]
        assert "max_total_spawns" not in attrs


class TestOrchestratorUpdateFields:
    def test_update_help_shows_max_active_agents(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["orchestrator", "update", "--help"])
        assert result.exit_code == 0
        assert "--max-active-agents" in result.output

    def test_update_help_shows_max_total_spawns(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["orchestrator", "update", "--help"])
        assert result.exit_code == 0
        assert "--max-total-spawns" in result.output

    def test_update_sends_max_active_agents_in_payload(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.patch.side_effect = [_make_orch_response()]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                [
                    "--local",
                    "orchestrator",
                    "update",
                    ORCH_ID,
                    "--max-active-agents",
                    "20",
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        patch_call = mock_client.patch.call_args
        payload = patch_call.kwargs.get("json", {})
        attrs = payload["data"]["attributes"]
        assert "max_active_agents" in attrs
        assert attrs["max_active_agents"] == 20
        assert "max_agents" not in attrs

    def test_update_deprecated_max_agents_alias(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.patch.side_effect = [_make_orch_response()]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                [
                    "--local",
                    "orchestrator",
                    "update",
                    ORCH_ID,
                    "--max-agents",
                    "20",
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        patch_call = mock_client.patch.call_args
        payload = patch_call.kwargs.get("json", {})
        attrs = payload["data"]["attributes"]
        assert "max_active_agents" in attrs
        assert "max_agents" not in attrs

    def test_update_sends_max_total_spawns_in_payload(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.patch.side_effect = [_make_orch_response()]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(
                cli,
                [
                    "--local",
                    "orchestrator",
                    "update",
                    ORCH_ID,
                    "--max-total-spawns",
                    "500",
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        patch_call = mock_client.patch.call_args
        payload = patch_call.kwargs.get("json", {})
        attrs = payload["data"]["attributes"]
        assert "max_total_spawns" in attrs
        assert attrs["max_total_spawns"] == 500


class TestOrchestratorListDisplay:
    def test_list_table_headers(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        list_resp = MagicMock()
        list_resp.status_code = 200
        list_resp.json.return_value = {
            "data": [
                {
                    "type": "simulation-orchestrators",
                    "id": ORCH_ID,
                    "attributes": SAMPLE_ATTRS,
                }
            ],
            "meta": {"count": 1},
        }
        mock_client.get.side_effect = [_make_csrf_response(), list_resp]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "orchestrator", "list"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "Max" in result.output
        assert "Act" in result.output
        assert "Spa" in result.output

    def test_list_table_does_not_show_old_max_agents_header(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        list_resp = MagicMock()
        list_resp.status_code = 200
        list_resp.json.return_value = {
            "data": [
                {
                    "type": "simulation-orchestrators",
                    "id": ORCH_ID,
                    "attributes": SAMPLE_ATTRS,
                }
            ],
            "meta": {"count": 1},
        }
        mock_client.get.side_effect = [_make_csrf_response(), list_resp]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "orchestrator", "list"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "Max Agents" not in result.output


class TestOrchestratorGetDisplay:
    def test_get_detail_shows_max_active_agents(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {
            "data": {
                "type": "simulation-orchestrators",
                "id": ORCH_ID,
                "attributes": SAMPLE_ATTRS,
            }
        }
        mock_client.get.side_effect = [_make_csrf_response(), get_resp]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "orchestrator", "get", ORCH_ID])

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "Max Active Agents" in result.output
        assert "10" in result.output

    def test_get_detail_shows_max_total_spawns(self, runner: CliRunner) -> None:
        mock_client = MagicMock()
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {
            "data": {
                "type": "simulation-orchestrators",
                "id": ORCH_ID,
                "attributes": SAMPLE_ATTRS,
            }
        }
        mock_client.get.side_effect = [_make_csrf_response(), get_resp]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
            result = runner.invoke(cli, ["--local", "orchestrator", "get", ORCH_ID])

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "Max Total Spawns" in result.output
        assert "100" in result.output


class TestOrchestratorApplyFields:
    def test_apply_help_shows_max_active_agents(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["orchestrator", "apply", "--help"])
        assert result.exit_code == 0
        assert "--max-active-agents" in result.output

    def test_apply_help_shows_max_total_spawns(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["orchestrator", "apply", "--help"])
        assert result.exit_code == 0
        assert "--max-total-spawns" in result.output


class TestBuildUpdateAttributes:
    def test_max_active_agents_key_in_output(self) -> None:
        from opennotes_cli.commands.orchestrator import _build_update_attributes

        result = _build_update_attributes(
            name=None,
            description=None,
            max_active_agents=5,
            max_total_spawns=None,
            turn_cadence=None,
            removal_rate=None,
            max_turns=None,
            agent_ids=None,
            scoring_config=None,
        )
        assert "max_active_agents" in result
        assert "max_agents" not in result
        assert result["max_active_agents"] == 5

    def test_max_total_spawns_key_in_output(self) -> None:
        from opennotes_cli.commands.orchestrator import _build_update_attributes

        result = _build_update_attributes(
            name=None,
            description=None,
            max_active_agents=None,
            max_total_spawns=200,
            turn_cadence=None,
            removal_rate=None,
            max_turns=None,
            agent_ids=None,
            scoring_config=None,
        )
        assert "max_total_spawns" in result
        assert result["max_total_spawns"] == 200

    def test_both_fields_together(self) -> None:
        from opennotes_cli.commands.orchestrator import _build_update_attributes

        result = _build_update_attributes(
            name=None,
            description=None,
            max_active_agents=8,
            max_total_spawns=500,
            turn_cadence=None,
            removal_rate=None,
            max_turns=None,
            agent_ids=None,
            scoring_config=None,
        )
        assert result["max_active_agents"] == 8
        assert result["max_total_spawns"] == 500
        assert "max_agents" not in result

    def test_none_values_excluded(self) -> None:
        from opennotes_cli.commands.orchestrator import _build_update_attributes

        result = _build_update_attributes(
            name=None,
            description=None,
            max_active_agents=None,
            max_total_spawns=None,
            turn_cadence=None,
            removal_rate=None,
            max_turns=None,
            agent_ids=None,
            scoring_config=None,
        )
        assert "max_active_agents" not in result
        assert "max_total_spawns" not in result
        assert "max_agents" not in result
