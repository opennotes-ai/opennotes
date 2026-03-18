from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
from click.testing import CliRunner

from opennotes_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


ORCH_ID = "019536b8-bdb2-7c81-8975-77f5c3dbdff8"
CS_ID = "019536b8-bdb2-7c81-8975-88a5c3dbdff8"
SOURCE_CS_ID = "019536b8-bdb2-7c81-8975-99b5c3dbdff8"
SIM_ID = "019536b8-bdb2-7c81-8975-aab5c3dbdff8"
COPY_JOB_ID = "019536b8-bdb2-7c81-8975-bbc5c3dbdff8"


def _make_csrf_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    return resp


def _make_copy_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": {"type": "copy-requests", "id": COPY_JOB_ID}}
    return resp


def _make_sim_response(sim_id: str = SIM_ID) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": {
            "type": "simulations",
            "id": sim_id,
            "attributes": {
                "status": "pending",
                "orchestrator_id": ORCH_ID,
                "community_server_id": CS_ID,
            },
        }
    }
    return resp


def _make_orch_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": {"type": "simulation-orchestrators", "id": ORCH_ID}
    }
    return resp


def _make_playground_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"id": CS_ID}
    return resp


def _make_url_submission_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": {
            "type": "playground-note-requests",
            "attributes": {"workflow_id": "wf-123"},
        }
    }
    return resp


class TestSimulationCreateCopyRequestsFrom:
    def test_create_with_copy_requests_triggers_post_and_polls(
        self, runner: CliRunner
    ) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.post.side_effect = [_make_copy_response(), _make_sim_response()]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with (
            patch("opennotes_cli.cli.httpx.Client", return_value=mock_client),
            patch(
                "opennotes_cli.commands.simulation.poll_batch_job_until_complete"
            ) as mock_poll,
        ):
            mock_poll.return_value = {"status": "completed"}

            result = runner.invoke(
                cli,
                [
                    "--local",
                    "simulation",
                    "create",
                    "--orchestrator-id",
                    ORCH_ID,
                    "--community-server-id",
                    CS_ID,
                    "--copy-requests-from",
                    SOURCE_CS_ID,
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"

        post_calls = mock_client.post.call_args_list
        assert len(post_calls) == 2

        copy_call = post_calls[0]
        assert f"/copy-requests" in copy_call.args[0]
        copy_payload = copy_call.kwargs.get("json", {})
        assert (
            copy_payload["data"]["attributes"]["source_community_server_id"]
            == SOURCE_CS_ID
        )

        mock_poll.assert_called_once()
        poll_args = mock_poll.call_args
        assert poll_args[0][3] == COPY_JOB_ID

        sim_call = post_calls[1]
        assert "/api/v2/simulations" in sim_call.args[0]

    def test_create_without_copy_requests_skips_copy(
        self, runner: CliRunner
    ) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.post.side_effect = [_make_sim_response()]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with (
            patch("opennotes_cli.cli.httpx.Client", return_value=mock_client),
            patch(
                "opennotes_cli.commands.simulation.poll_batch_job_until_complete"
            ) as mock_poll,
        ):
            result = runner.invoke(
                cli,
                [
                    "--local",
                    "simulation",
                    "create",
                    "--orchestrator-id",
                    ORCH_ID,
                    "--community-server-id",
                    CS_ID,
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"

        post_calls = mock_client.post.call_args_list
        assert len(post_calls) == 1
        assert "/api/v2/simulations" in post_calls[0].args[0]

        mock_poll.assert_not_called()


class TestSimulationLaunchCopyRequestsFrom:
    def test_launch_with_copy_requests_triggers_post_and_polls(
        self, runner: CliRunner
    ) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.post.side_effect = [
            _make_orch_response(),
            _make_playground_response(),
            _make_copy_response(),
            _make_url_submission_response(),
            _make_sim_response(),
        ]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        with (
            patch("opennotes_cli.cli.httpx.Client", return_value=mock_client),
            patch(
                "opennotes_cli.commands.simulation.poll_batch_job_until_complete"
            ) as mock_poll,
        ):
            mock_poll.return_value = {"status": "completed"}

            result = runner.invoke(
                cli,
                [
                    "--local",
                    "simulation",
                    "launch",
                    "--url",
                    "http://example.com/article",
                    "--agent-ids",
                    ORCH_ID,
                    "--copy-requests-from",
                    SOURCE_CS_ID,
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"

        post_calls = mock_client.post.call_args_list
        assert len(post_calls) == 5

        copy_call = post_calls[2]
        assert "/copy-requests" in copy_call.args[0]
        copy_payload = copy_call.kwargs.get("json", {})
        assert (
            copy_payload["data"]["attributes"]["source_community_server_id"]
            == SOURCE_CS_ID
        )

        mock_poll.assert_called_once()
        poll_args = mock_poll.call_args
        assert poll_args[0][3] == COPY_JOB_ID

        url_call = post_calls[3]
        assert "/note-requests" in url_call.args[0]

        sim_call = post_calls[4]
        assert "/api/v2/simulations" in sim_call.args[0]

    def test_launch_copy_requests_happens_before_url_submission(
        self, runner: CliRunner
    ) -> None:
        call_order: list[str] = []

        mock_client = MagicMock()
        mock_client.get.side_effect = [_make_csrf_response()]
        mock_client.cookies = MagicMock()
        mock_client.cookies.get.return_value = "test-csrf"

        def track_post(url: str, **kwargs: object) -> MagicMock:
            if "/copy-requests" in url:
                call_order.append("copy-requests")
                return _make_copy_response()
            elif "/note-requests" in url:
                call_order.append("note-requests")
                return _make_url_submission_response()
            elif "/simulation-orchestrators" in url:
                call_order.append("orchestrator")
                return _make_orch_response()
            elif "/community-servers" in url:
                call_order.append("playground")
                return _make_playground_response()
            elif "/simulations" in url:
                call_order.append("simulation")
                return _make_sim_response()
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {}
            return resp

        mock_client.post.side_effect = track_post

        with (
            patch("opennotes_cli.cli.httpx.Client", return_value=mock_client),
            patch(
                "opennotes_cli.commands.simulation.poll_batch_job_until_complete"
            ) as mock_poll,
        ):
            mock_poll.return_value = {"status": "completed"}

            result = runner.invoke(
                cli,
                [
                    "--local",
                    "simulation",
                    "launch",
                    "--url",
                    "http://example.com/article",
                    "--agent-ids",
                    ORCH_ID,
                    "--copy-requests-from",
                    SOURCE_CS_ID,
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"

        copy_idx = call_order.index("copy-requests")
        note_idx = call_order.index("note-requests")
        sim_idx = call_order.index("simulation")
        assert copy_idx < note_idx, "copy-requests should happen before note-requests"
        assert copy_idx < sim_idx, "copy-requests should happen before simulation creation"
