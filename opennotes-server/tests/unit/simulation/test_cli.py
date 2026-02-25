from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from click.testing import CliRunner


class TestSimulationResultsAgentFilter:
    def test_agent_filter_sends_correct_query_parameter(self) -> None:
        from scripts.opennotes_cli import simulation_group

        runner = CliRunner()
        sim_id = str(uuid4())
        agent_id = str(uuid4())

        mock_response: dict = {
            "data": [],
            "meta": {"total": 0},
        }

        with patch("scripts.opennotes_cli.api_get", return_value=mock_response) as mock_get:
            runner.invoke(
                simulation_group,
                ["results", sim_id, "--agent-id", agent_id],
            )

            mock_get.assert_called_once()
            call_args = mock_get.call_args
            params = call_args[1].get("params") or call_args[0][1]

            assert "agent_instance_id" in params
            assert params["agent_instance_id"] == agent_id
            assert "filter[agent_instance_id]" not in params

    def test_agent_filter_omitted_when_no_agent_id(self) -> None:
        from scripts.opennotes_cli import simulation_group

        runner = CliRunner()
        sim_id = str(uuid4())

        mock_response: dict = {
            "data": [],
            "meta": {"total": 0},
        }

        with patch("scripts.opennotes_cli.api_get", return_value=mock_response) as mock_get:
            runner.invoke(
                simulation_group,
                ["results", sim_id],
            )

            mock_get.assert_called_once()
            call_args = mock_get.call_args
            params = call_args[1].get("params") or call_args[0][1]

            assert "agent_instance_id" not in params
            assert "filter[agent_instance_id]" not in params
