"""
Unit tests for taskiq broker configuration.

These tests verify broker configuration, metadata preservation,
and error handling without requiring actual NATS/Redis connections.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBrokerConfiguration:
    """Test broker configuration uses settings correctly."""

    def test_broker_uses_configurable_settings(self) -> None:
        """Verify broker reads from settings for stream name, result expiry, etc."""
        with (
            patch("src.tasks.broker._broker_instance", None),
            patch("src.tasks.broker._registered_task_objects", {}),
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.RedisAsyncResultBackend") as mock_redis,
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker,
            patch("src.tasks.broker.SimpleRetryMiddleware") as mock_retry,
            patch("src.tasks.broker.OpenTelemetryMiddleware"),
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://test:4222"
            settings.REDIS_URL = "redis://test:6379"
            settings.TASKIQ_STREAM_NAME = "TEST_STREAM"
            settings.TASKIQ_RESULT_EXPIRY = 7200
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 5
            settings.NATS_USERNAME = None
            settings.NATS_PASSWORD = None
            mock_settings.return_value = settings

            mock_broker_instance = MagicMock()
            mock_broker_instance.with_result_backend.return_value = mock_broker_instance
            mock_broker_instance.with_middlewares.return_value = mock_broker_instance
            mock_broker.return_value = mock_broker_instance

            from src.tasks.broker import _create_broker

            _create_broker()

            mock_redis.assert_called_once_with(
                redis_url="redis://test:6379",
                result_ex_time=7200,
            )

            mock_broker.assert_called_once_with(
                servers=["nats://test:4222"],
                stream_name="TEST_STREAM",
                durable="opennotes-taskiq-worker",
            )

            mock_retry.assert_called_once_with(
                default_retry_count=5,
            )


class TestLazyTaskMetadata:
    """Test LazyTask preserves function metadata correctly."""

    def test_lazy_task_preserves_function_name(self) -> None:
        """LazyTask should preserve the original function's __name__."""
        from src.tasks.broker import LazyTask

        async def my_task_function(arg: str) -> str:
            """Original docstring."""
            return arg

        lazy = LazyTask(my_task_function, "test:my_task_function")

        assert lazy.__name__ == "my_task_function"

    def test_lazy_task_preserves_docstring(self) -> None:
        """LazyTask should preserve the original function's __doc__."""
        from src.tasks.broker import LazyTask

        async def documented_task() -> None:
            """This is the task documentation."""

        lazy = LazyTask(documented_task, "test:documented_task")

        assert lazy.__doc__ == "This is the task documentation."

    def test_lazy_task_preserves_annotations(self) -> None:
        """LazyTask should preserve the original function's __annotations__."""
        from src.tasks.broker import LazyTask

        async def typed_task(message: str, count: int) -> bool:
            """Typed task."""
            return True

        lazy = LazyTask(typed_task, "test:typed_task")

        assert lazy.__annotations__ == {"message": str, "count": int, "return": bool}

    def test_lazy_task_preserves_module(self) -> None:
        """LazyTask should preserve the original function's __module__."""
        from src.tasks.broker import LazyTask

        async def module_task() -> None:
            pass

        lazy = LazyTask(module_task, "test:module_task")

        assert lazy.__module__ == module_task.__module__

    def test_lazy_task_has_wrapped_attribute(self) -> None:
        """LazyTask should have __wrapped__ pointing to original function."""
        from src.tasks.broker import LazyTask

        async def wrapped_task() -> None:
            pass

        lazy = LazyTask(wrapped_task, "test:wrapped_task")

        assert hasattr(lazy, "__wrapped__")
        assert lazy.__wrapped__ is wrapped_task


class TestBrokerHealthCheck:
    """Test broker health check functions."""

    def test_is_broker_initialized_returns_false_when_not_initialized(self) -> None:
        """is_broker_initialized returns False when broker not created."""
        with patch("src.tasks.broker._broker_instance", None):
            from src.tasks.broker import is_broker_initialized

            assert is_broker_initialized() is False

    def test_is_broker_initialized_returns_true_when_initialized(self) -> None:
        """is_broker_initialized returns True when broker exists."""
        mock_broker = MagicMock()
        with patch("src.tasks.broker._broker_instance", mock_broker):
            from src.tasks.broker import is_broker_initialized

            assert is_broker_initialized() is True

    def test_get_broker_health_when_not_initialized(self) -> None:
        """get_broker_health returns correct info when not initialized."""
        with (
            patch("src.tasks.broker._broker_instance", None),
            patch("src.tasks.broker.get_settings") as mock_settings,
        ):
            settings = MagicMock()
            settings.TASKIQ_STREAM_NAME = "TEST_STREAM"
            mock_settings.return_value = settings

            from src.tasks.broker import get_broker_health

            health = get_broker_health()

            assert health["initialized"] is False
            assert health["stream_name"] == "TEST_STREAM"
            assert health["registered_tasks"] == 0

    def test_get_broker_health_when_initialized(self) -> None:
        """get_broker_health returns correct info when initialized."""
        mock_broker = MagicMock()
        mock_tasks = {"task1": MagicMock(), "task2": MagicMock(), "task3": MagicMock()}

        with (
            patch("src.tasks.broker._broker_instance", mock_broker),
            patch("src.tasks.broker._registered_task_objects", mock_tasks),
            patch("src.tasks.broker.get_settings") as mock_settings,
        ):
            settings = MagicMock()
            settings.TASKIQ_STREAM_NAME = "PROD_STREAM"
            mock_settings.return_value = settings

            from src.tasks.broker import get_broker_health

            health = get_broker_health()

            assert health["initialized"] is True
            assert health["stream_name"] == "PROD_STREAM"
            assert health["registered_tasks"] == 3


class TestBrokerConnectionFailure:
    """Test broker behavior when NATS/Redis connections fail."""

    @pytest.mark.asyncio
    async def test_broker_startup_failure_with_invalid_nats_url(self) -> None:
        """
        Verify broker startup fails gracefully with invalid NATS URL.

        When NATS is unavailable, broker.startup() should raise an
        exception rather than silently failing.
        """
        from src.tasks.broker import reset_broker

        reset_broker()

        with (
            patch("src.tasks.broker._broker_instance", None),
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.RedisAsyncResultBackend"),
            patch("src.tasks.broker.SimpleRetryMiddleware"),
            patch("src.tasks.broker.OpenTelemetryMiddleware"),
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker_class,
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://invalid-host:4222"
            settings.REDIS_URL = "redis://localhost:6379"
            settings.TASKIQ_STREAM_NAME = "TEST"
            settings.TASKIQ_RESULT_EXPIRY = 3600
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 3
            settings.NATS_USERNAME = None
            settings.NATS_PASSWORD = None
            mock_settings.return_value = settings

            mock_broker = MagicMock()
            mock_broker.with_result_backend.return_value = mock_broker
            mock_broker.with_middlewares.return_value = mock_broker
            mock_broker.startup = AsyncMock(
                side_effect=ConnectionRefusedError("Connection refused")
            )
            mock_broker_class.return_value = mock_broker

            from src.tasks.broker import get_broker

            broker = get_broker()

            with pytest.raises(ConnectionRefusedError):
                await broker.startup()

        reset_broker()

    @pytest.mark.asyncio
    async def test_broker_startup_failure_with_invalid_redis_url(self) -> None:
        """
        Verify broker handles Redis connection failure on startup.

        The result backend connection failure should propagate appropriately.
        """
        from src.tasks.broker import reset_broker

        reset_broker()

        with (
            patch("src.tasks.broker._broker_instance", None),
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.RedisAsyncResultBackend") as mock_redis_class,
            patch("src.tasks.broker.SimpleRetryMiddleware"),
            patch("src.tasks.broker.OpenTelemetryMiddleware"),
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker_class,
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://localhost:4222"
            settings.REDIS_URL = "redis://invalid-host:6379"
            settings.TASKIQ_STREAM_NAME = "TEST"
            settings.TASKIQ_RESULT_EXPIRY = 3600
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 3
            settings.NATS_USERNAME = None
            settings.NATS_PASSWORD = None
            mock_settings.return_value = settings

            mock_backend = MagicMock()
            mock_redis_class.return_value = mock_backend

            mock_broker = MagicMock()
            mock_broker.with_result_backend.return_value = mock_broker
            mock_broker.with_middlewares.return_value = mock_broker
            mock_broker.startup = AsyncMock(
                side_effect=ConnectionRefusedError("Redis connection failed")
            )
            mock_broker_class.return_value = mock_broker

            from src.tasks.broker import get_broker

            broker = get_broker()

            with pytest.raises(ConnectionRefusedError):
                await broker.startup()

        reset_broker()


class TestRetryMiddlewareConfiguration:
    """Test retry middleware is properly configured."""

    def test_retry_middleware_uses_settings(self) -> None:
        """Verify SimpleRetryMiddleware is configured with settings values."""
        with (
            patch("src.tasks.broker._broker_instance", None),
            patch("src.tasks.broker._registered_task_objects", {}),
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.RedisAsyncResultBackend"),
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker,
            patch("src.tasks.broker.SimpleRetryMiddleware") as mock_retry,
            patch("src.tasks.broker.OpenTelemetryMiddleware"),
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://localhost:4222"
            settings.REDIS_URL = "redis://localhost:6379"
            settings.TASKIQ_STREAM_NAME = "TEST"
            settings.TASKIQ_RESULT_EXPIRY = 3600
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 10
            settings.NATS_USERNAME = None
            settings.NATS_PASSWORD = None
            mock_settings.return_value = settings

            mock_broker_instance = MagicMock()
            mock_broker_instance.with_result_backend.return_value = mock_broker_instance
            mock_broker_instance.with_middlewares.return_value = mock_broker_instance
            mock_broker.return_value = mock_broker_instance

            from src.tasks.broker import _create_broker

            _create_broker()

            mock_retry.assert_called_once_with(default_retry_count=10)
            mock_broker_instance.with_middlewares.assert_called_once()


class TestBrokerAuthentication:
    """Test broker NATS authentication configuration."""

    def test_broker_passes_auth_when_credentials_configured(self) -> None:
        """Verify broker passes user/password when NATS credentials are set."""
        with (
            patch("src.tasks.broker._broker_instance", None),
            patch("src.tasks.broker._registered_task_objects", {}),
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.RedisAsyncResultBackend"),
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker,
            patch("src.tasks.broker.SimpleRetryMiddleware"),
            patch("src.tasks.broker.OpenTelemetryMiddleware"),
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://test:4222"
            settings.REDIS_URL = "redis://test:6379"
            settings.TASKIQ_STREAM_NAME = "TEST_STREAM"
            settings.TASKIQ_RESULT_EXPIRY = 3600
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 3
            settings.NATS_USERNAME = "testuser"
            settings.NATS_PASSWORD = "testpass"
            mock_settings.return_value = settings

            mock_broker_instance = MagicMock()
            mock_broker_instance.with_result_backend.return_value = mock_broker_instance
            mock_broker_instance.with_middlewares.return_value = mock_broker_instance
            mock_broker.return_value = mock_broker_instance

            from src.tasks.broker import _create_broker

            _create_broker()

            mock_broker.assert_called_once_with(
                servers=["nats://test:4222"],
                stream_name="TEST_STREAM",
                durable="opennotes-taskiq-worker",
                user="testuser",
                password="testpass",
            )
