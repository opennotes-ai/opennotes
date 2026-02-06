"""
Integration tests for TaskIQ content monitoring tasks.

Task: task-910 - Migrate content monitoring system to TaskIQ

These tests verify:
- AC #9: Integration tests exist for TaskIQ task execution
- Task registration and broker configuration
- OpenTelemetry tracing integration

Bulk scan batch processing and finalization tasks have been migrated to DBOS workflows.
See tests/unit/test_content_scan_workflow.py for DBOS workflow tests.

Note: These tests focus on broker and task registration without importing
the full application modules to avoid torch/litellm import chain issues.
Full end-to-end testing is done via staging environment.
"""


class TestTaskRegistration:
    """Test that remaining content monitoring tasks are properly registered."""

    def test_remaining_content_monitoring_tasks_registered(self):
        """Verify AI note, vision, and audit log tasks are registered with broker."""
        from src.tasks.broker import _all_registered_tasks

        expected_tasks = [
            "content:ai_note",
            "content:vision_description",
            "content:audit_log",
        ]

        for task_name in expected_tasks:
            assert task_name in _all_registered_tasks, f"Task {task_name} not registered"

    def test_removed_tasks_not_registered(self):
        """Verify bulk scan tasks (migrated to DBOS) are no longer registered."""
        from src.tasks.broker import _all_registered_tasks

        removed_tasks = [
            "content:batch_scan",
            "content:finalize_scan",
        ]

        for task_name in removed_tasks:
            assert task_name not in _all_registered_tasks, (
                f"Task {task_name} should not be registered (migrated to DBOS)"
            )

    def test_task_labels_include_component(self):
        """All content monitoring tasks have component label."""
        from src.tasks.broker import _all_registered_tasks

        content_tasks = [name for name in _all_registered_tasks if name.startswith("content:")]

        for task_name in content_tasks:
            _, labels = _all_registered_tasks[task_name]
            assert labels.get("component") == "content_monitoring", (
                f"Task {task_name} missing component label"
            )

    def test_task_labels_include_task_type(self):
        """All content monitoring tasks have task_type label."""
        from src.tasks.broker import _all_registered_tasks

        expected_types = {
            "content:ai_note": "generation",
            "content:vision_description": "vision",
            "content:audit_log": "audit",
        }

        for task_name, expected_type in expected_types.items():
            _, labels = _all_registered_tasks[task_name]
            assert labels.get("task_type") == expected_type, (
                f"Task {task_name} has wrong task_type: {labels.get('task_type')}"
            )


class TestTaskIQBrokerConfiguration:
    """Test TaskIQ broker configuration."""

    def test_broker_has_opentelemetry_middleware(self):
        """Verify broker is configured with OpenTelemetry middleware."""
        from src.tasks.broker import get_broker

        broker = get_broker()
        middleware_types = [type(m).__name__ for m in broker.middlewares]

        assert "SafeOpenTelemetryMiddleware" in middleware_types, (
            f"SafeOpenTelemetryMiddleware not configured on broker. Found: {middleware_types}"
        )

    def test_broker_has_retry_middleware(self):
        """Verify broker is configured with retry middleware."""
        from src.tasks.broker import get_broker

        broker = get_broker()
        middleware_types = [type(m).__name__ for m in broker.middlewares]

        assert "RetryWithFinalCallbackMiddleware" in middleware_types, (
            "RetryWithFinalCallbackMiddleware not configured on broker"
        )
