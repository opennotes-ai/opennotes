import pytest

from src.simulation.workflows.playground_url_workflow import set_workflow_result_step


@pytest.mark.unit
class TestSetWorkflowResultStep:
    def test_counts_succeeded_and_failed(self):
        results = [
            {"request_id": "r1", "url": "u1", "status": "PENDING"},
            {"request_id": "r2", "url": "u2", "status": "FAILED", "error": "timeout"},
            {"request_id": "r3", "url": "u3", "status": "PENDING"},
        ]

        summary = set_workflow_result_step.__wrapped__(results, 3)

        assert summary["url_count"] == 3
        assert summary["succeeded"] == 2
        assert summary["failed"] == 1
        assert len(summary["results"]) == 3

    def test_all_failed(self):
        results = [
            {"request_id": "r1", "url": "u1", "status": "FAILED", "error": "e1"},
            {"request_id": "r2", "url": "u2", "status": "FAILED", "error": "e2"},
        ]

        summary = set_workflow_result_step.__wrapped__(results, 2)

        assert summary["succeeded"] == 0
        assert summary["failed"] == 2

    def test_all_succeeded(self):
        results = [
            {"request_id": "r1", "url": "u1", "status": "PENDING"},
            {"request_id": "r2", "url": "u2", "status": "PENDING"},
        ]

        summary = set_workflow_result_step.__wrapped__(results, 2)

        assert summary["succeeded"] == 2
        assert summary["failed"] == 0

    def test_empty_results(self):
        summary = set_workflow_result_step.__wrapped__([], 0)

        assert summary["url_count"] == 0
        assert summary["succeeded"] == 0
        assert summary["failed"] == 0
        assert summary["results"] == []
