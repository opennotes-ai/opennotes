"""
Unit tests for taskiq broker configuration.

These tests verify broker configuration, metadata preservation,
and error handling without requiring actual NATS/Redis connections.
"""

from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry import context as context_api
from opentelemetry.trace import Span
from taskiq import TaskiqMessage, TaskiqResult


class TestBrokerConfiguration:
    """Test broker configuration uses settings correctly."""

    def test_broker_uses_configurable_settings(self) -> None:
        """Verify broker reads from settings for stream name, result expiry, etc."""
        with (
            patch("src.tasks.broker._broker_instance", None),
            patch("src.tasks.broker._registered_task_objects", {}),
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.get_redis_connection_kwargs") as mock_redis_kwargs,
            patch("src.tasks.broker.RedisAsyncResultBackend") as mock_redis,
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker,
            patch("src.tasks.broker.RetryWithFinalCallbackMiddleware") as mock_retry,
            patch("src.tasks.broker.TaskIQMetricsMiddleware"),
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://test:4222"
            settings.NATS_SERVERS = ["nats://test:4222"]
            settings.REDIS_URL = "redis://test:6379"
            settings.TASKIQ_STREAM_NAME = "TEST_STREAM"
            settings.TASKIQ_STREAM_MAX_AGE_SECONDS = 604800  # 7 days
            settings.TASKIQ_RESULT_EXPIRY = 7200
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 5
            settings.NATS_CONNECT_TIMEOUT = 15
            settings.NATS_USERNAME = None
            settings.NATS_PASSWORD = None
            settings.INSTANCE_ID = "test-instance"
            mock_settings.return_value = settings
            mock_redis_kwargs.return_value = {}

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

            mock_broker.assert_called_once()
            call_kwargs = mock_broker.call_args.kwargs
            assert call_kwargs["servers"] == ["nats://test:4222"]
            assert call_kwargs["stream_name"] == "TEST_STREAM"
            assert call_kwargs["durable"] == "opennotes-taskiq-worker"
            assert call_kwargs["connect_timeout"] == 15
            assert call_kwargs["stream_config"].max_age == 604800

            mock_retry.assert_called_once()
            call_kwargs = mock_retry.call_args.kwargs
            assert call_kwargs["default_retry_count"] == 5
            assert "on_error_last_retry" in call_kwargs

    def test_broker_passes_ssl_cert_reqs_for_rediss_url(self) -> None:
        """Verify broker passes ssl_cert_reqs when using rediss:// URL with CA cert."""
        with (
            patch("src.tasks.broker._broker_instance", None),
            patch("src.tasks.broker._registered_task_objects", {}),
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.get_redis_connection_kwargs") as mock_redis_kwargs,
            patch("src.tasks.broker.RedisAsyncResultBackend") as mock_redis,
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker,
            patch("src.tasks.broker.RetryWithFinalCallbackMiddleware"),
            patch("src.tasks.broker.TaskIQMetricsMiddleware"),
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://test:4222"
            settings.REDIS_URL = "rediss://secure-redis:6380"
            settings.TASKIQ_STREAM_NAME = "TEST_STREAM"
            settings.TASKIQ_RESULT_EXPIRY = 3600
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 3
            settings.NATS_CONNECT_TIMEOUT = 10
            settings.NATS_USERNAME = None
            settings.NATS_PASSWORD = None
            settings.INSTANCE_ID = "test-instance"
            mock_settings.return_value = settings
            mock_redis_kwargs.return_value = {
                "ssl_ca_certs": "/path/to/ca.crt",
                "ssl_cert_reqs": "required",
            }

            mock_broker_instance = MagicMock()
            mock_broker_instance.with_result_backend.return_value = mock_broker_instance
            mock_broker_instance.with_middlewares.return_value = mock_broker_instance
            mock_broker.return_value = mock_broker_instance

            from src.tasks.broker import _create_broker

            _create_broker()

            mock_redis.assert_called_once_with(
                redis_url="rediss://secure-redis:6380",
                result_ex_time=3600,
                ssl_ca_certs="/path/to/ca.crt",
                ssl_cert_reqs="required",
            )

    def test_broker_does_not_pass_ssl_for_redis_url(self) -> None:
        """Verify broker does not pass ssl_cert_reqs when using redis:// URL."""
        with (
            patch("src.tasks.broker._broker_instance", None),
            patch("src.tasks.broker._registered_task_objects", {}),
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.get_redis_connection_kwargs") as mock_redis_kwargs,
            patch("src.tasks.broker.RedisAsyncResultBackend") as mock_redis,
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker,
            patch("src.tasks.broker.RetryWithFinalCallbackMiddleware"),
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://test:4222"
            settings.REDIS_URL = "redis://localhost:6379"
            settings.TASKIQ_STREAM_NAME = "TEST_STREAM"
            settings.TASKIQ_RESULT_EXPIRY = 3600
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 3
            settings.NATS_CONNECT_TIMEOUT = 10
            settings.NATS_USERNAME = None
            settings.NATS_PASSWORD = None
            mock_settings.return_value = settings
            mock_redis_kwargs.return_value = {}

            mock_broker_instance = MagicMock()
            mock_broker_instance.with_result_backend.return_value = mock_broker_instance
            mock_broker_instance.with_middlewares.return_value = mock_broker_instance
            mock_broker.return_value = mock_broker_instance

            from src.tasks.broker import _create_broker

            _create_broker()

            mock_redis.assert_called_once_with(
                redis_url="redis://localhost:6379",
                result_ex_time=3600,
            )
            call_kwargs = mock_redis.call_args[1]
            assert "ssl_cert_reqs" not in call_kwargs


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
            patch("src.tasks.broker.RetryWithFinalCallbackMiddleware"),
            patch("src.tasks.broker.TaskIQMetricsMiddleware"),
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker_class,
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://invalid-host:4222"
            settings.REDIS_URL = "redis://localhost:6379"
            settings.TASKIQ_STREAM_NAME = "TEST"
            settings.TASKIQ_RESULT_EXPIRY = 3600
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 3
            settings.NATS_CONNECT_TIMEOUT = 10
            settings.NATS_USERNAME = None
            settings.NATS_PASSWORD = None
            settings.INSTANCE_ID = "test-instance"
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
            patch("src.tasks.broker.RetryWithFinalCallbackMiddleware"),
            patch("src.tasks.broker.TaskIQMetricsMiddleware"),
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker_class,
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://localhost:4222"
            settings.REDIS_URL = "redis://invalid-host:6379"
            settings.TASKIQ_STREAM_NAME = "TEST"
            settings.TASKIQ_RESULT_EXPIRY = 3600
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 3
            settings.NATS_CONNECT_TIMEOUT = 10
            settings.NATS_USERNAME = None
            settings.NATS_PASSWORD = None
            settings.INSTANCE_ID = "test-instance"
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
        """Verify RetryWithFinalCallbackMiddleware is configured with settings values."""
        with (
            patch("src.tasks.broker._broker_instance", None),
            patch("src.tasks.broker._registered_task_objects", {}),
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.RedisAsyncResultBackend"),
            patch("src.tasks.broker.PullBasedJetStreamBroker") as mock_broker,
            patch("src.tasks.broker.RetryWithFinalCallbackMiddleware") as mock_retry,
            patch("src.tasks.broker.TaskIQMetricsMiddleware"),
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://localhost:4222"
            settings.REDIS_URL = "redis://localhost:6379"
            settings.TASKIQ_STREAM_NAME = "TEST"
            settings.TASKIQ_RESULT_EXPIRY = 3600
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 10
            settings.NATS_CONNECT_TIMEOUT = 10
            settings.NATS_USERNAME = None
            settings.NATS_PASSWORD = None
            settings.INSTANCE_ID = "test-instance"
            mock_settings.return_value = settings

            mock_broker_instance = MagicMock()
            mock_broker_instance.with_result_backend.return_value = mock_broker_instance
            mock_broker_instance.with_middlewares.return_value = mock_broker_instance
            mock_broker.return_value = mock_broker_instance

            from src.tasks.broker import _create_broker

            _create_broker()

            mock_retry.assert_called_once()
            call_kwargs = mock_retry.call_args.kwargs
            assert call_kwargs["default_retry_count"] == 10
            assert "on_error_last_retry" in call_kwargs
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
            patch("src.tasks.broker.RetryWithFinalCallbackMiddleware"),
            patch("src.tasks.broker.TaskIQMetricsMiddleware"),
        ):
            settings = MagicMock()
            settings.NATS_URL = "nats://test:4222"
            settings.NATS_SERVERS = ["nats://test:4222"]
            settings.REDIS_URL = "redis://test:6379"
            settings.TASKIQ_STREAM_NAME = "TEST_STREAM"
            settings.TASKIQ_STREAM_MAX_AGE_SECONDS = 604800  # 7 days
            settings.TASKIQ_RESULT_EXPIRY = 3600
            settings.TASKIQ_DEFAULT_RETRY_COUNT = 3
            settings.NATS_CONNECT_TIMEOUT = 30
            settings.NATS_USERNAME = "testuser"
            settings.NATS_PASSWORD = "testpass"
            settings.INSTANCE_ID = "test-instance"
            mock_settings.return_value = settings

            mock_broker_instance = MagicMock()
            mock_broker_instance.with_result_backend.return_value = mock_broker_instance
            mock_broker_instance.with_middlewares.return_value = mock_broker_instance
            mock_broker.return_value = mock_broker_instance

            from src.tasks.broker import _create_broker

            _create_broker()

            mock_broker.assert_called_once()
            call_kwargs = mock_broker.call_args.kwargs
            assert call_kwargs["servers"] == ["nats://test:4222"]
            assert call_kwargs["stream_name"] == "TEST_STREAM"
            assert call_kwargs["connect_timeout"] == 30
            assert call_kwargs["user"] == "testuser"
            assert call_kwargs["password"] == "testpass"
            assert call_kwargs["stream_config"].max_age == 604800


class TestSafeOpenTelemetryMiddleware:
    """Test SafeOpenTelemetryMiddleware handles context token errors gracefully."""

    def _create_mock_message(self, task_id: str = "test-task-123") -> TaskiqMessage:
        """Create a mock TaskiqMessage for testing."""
        return TaskiqMessage(
            task_id=task_id,
            task_name="test:task",
            labels={},
            args=[],
            kwargs={},
        )

    def _create_mock_result(self) -> TaskiqResult:
        """Create a mock TaskiqResult for testing."""
        return TaskiqResult(
            is_err=False,
            log=None,
            return_value={"status": "completed"},
            execution_time=0.1,
        )

    def test_post_save_handles_context_mismatch_error(self) -> None:
        """
        Verify post_save catches 'Token was created in a different Context' error.

        This error occurs when async tasks run in different coroutine contexts
        than where the OpenTelemetry context was originally attached.
        """
        from src.tasks.broker import SafeOpenTelemetryMiddleware

        middleware = SafeOpenTelemetryMiddleware()
        message = self._create_mock_message()
        result = self._create_mock_result()

        mock_span = MagicMock(spec=Span)
        mock_span.is_recording.return_value = True

        mock_activation: AbstractContextManager[Span] = MagicMock()

        mock_token = MagicMock()

        ctx_dict = {(message.task_id, False): (mock_span, mock_activation, mock_token)}
        object.__setattr__(message, "__otel_task_span", ctx_dict)

        with patch.object(
            context_api,
            "detach",
            side_effect=ValueError(f"{mock_token!r} was created in a different Context"),
        ):
            middleware.post_save(message, result)

        mock_activation.__exit__.assert_called_once_with(None, None, None)
        mock_span.set_attribute.assert_any_call("taskiq.action", "execute")
        mock_span.set_attribute.assert_any_call("taskiq.task_name", "test:task")

    def test_post_save_propagates_other_value_errors(self) -> None:
        """
        Verify post_save re-raises ValueErrors that are not context-related.

        Only the specific 'Token was created in a different Context' error
        should be caught and logged; other ValueErrors should propagate.
        """
        from src.tasks.broker import SafeOpenTelemetryMiddleware

        middleware = SafeOpenTelemetryMiddleware()
        message = self._create_mock_message()
        result = self._create_mock_result()

        mock_span = MagicMock(spec=Span)
        mock_span.is_recording.return_value = True

        mock_activation: AbstractContextManager[Span] = MagicMock()
        mock_token = MagicMock()

        ctx_dict = {(message.task_id, False): (mock_span, mock_activation, mock_token)}
        object.__setattr__(message, "__otel_task_span", ctx_dict)

        with (
            patch.object(
                context_api,
                "detach",
                side_effect=ValueError("Some other ValueError"),
            ),
            pytest.raises(ValueError, match="Some other ValueError"),
        ):
            middleware.post_save(message, result)

    def test_post_save_works_normally_without_token(self) -> None:
        """
        Verify post_save works correctly when there is no context token.

        This happens when the sending process is not instrumented with
        OpenTelemetry, so there's no incoming context to attach/detach.
        """
        from src.tasks.broker import SafeOpenTelemetryMiddleware

        middleware = SafeOpenTelemetryMiddleware()
        message = self._create_mock_message()
        result = self._create_mock_result()

        mock_span = MagicMock(spec=Span)
        mock_span.is_recording.return_value = True

        mock_activation: AbstractContextManager[Span] = MagicMock()

        ctx_dict = {(message.task_id, False): (mock_span, mock_activation, None)}
        object.__setattr__(message, "__otel_task_span", ctx_dict)

        with patch.object(context_api, "detach") as mock_detach:
            middleware.post_save(message, result)

        mock_detach.assert_not_called()

        mock_activation.__exit__.assert_called_once_with(None, None, None)

    def test_post_save_handles_no_context(self) -> None:
        """
        Verify post_save handles case when no context is attached to message.
        """
        from src.tasks.broker import SafeOpenTelemetryMiddleware

        middleware = SafeOpenTelemetryMiddleware()
        message = self._create_mock_message()
        result = self._create_mock_result()

        middleware.post_save(message, result)

    def test_post_save_successful_detach(self) -> None:
        """
        Verify post_save calls detach normally when it succeeds.

        In the normal case (same async context), detach should be called
        and succeed without any special handling.
        """
        from src.tasks.broker import SafeOpenTelemetryMiddleware

        middleware = SafeOpenTelemetryMiddleware()
        message = self._create_mock_message()
        result = self._create_mock_result()

        mock_span = MagicMock(spec=Span)
        mock_span.is_recording.return_value = True

        mock_activation: AbstractContextManager[Span] = MagicMock()
        mock_token = MagicMock()

        ctx_dict = {(message.task_id, False): (mock_span, mock_activation, mock_token)}
        object.__setattr__(message, "__otel_task_span", ctx_dict)

        with patch.object(context_api, "detach") as mock_detach:
            middleware.post_save(message, result)

        mock_detach.assert_called_once_with(mock_token)

    @pytest.mark.asyncio
    async def test_concurrent_tasks_with_context_isolation(self) -> None:
        """
        Verify SafeOpenTelemetryMiddleware handles concurrent async tasks.

        This test simulates the production scenario where multiple async
        tasks run concurrently and context tokens may cross task boundaries,
        causing 'Token was created in a different Context' errors.
        """
        import asyncio

        from src.tasks.broker import SafeOpenTelemetryMiddleware

        middleware = SafeOpenTelemetryMiddleware()
        errors: list[Exception] = []

        async def simulate_task_lifecycle(task_num: int) -> None:
            """Simulate a complete task lifecycle with middleware hooks."""
            message = TaskiqMessage(
                task_id=f"task-{task_num}",
                task_name="test:concurrent_task",
                labels={},
                args=[],
                kwargs={},
            )
            result = TaskiqResult(
                is_err=False,
                log=None,
                return_value={"task_num": task_num},
                execution_time=0.01,
            )

            mock_span = MagicMock(spec=Span)
            mock_span.is_recording.return_value = True

            mock_activation: AbstractContextManager[Span] = MagicMock()

            mock_token = MagicMock()

            ctx_dict = {(message.task_id, False): (mock_span, mock_activation, mock_token)}
            object.__setattr__(message, "__otel_task_span", ctx_dict)

            await asyncio.sleep(0.001 * (task_num % 5))

            try:
                with patch.object(
                    context_api,
                    "detach",
                    side_effect=ValueError(f"{mock_token!r} was created in a different Context"),
                ):
                    middleware.post_save(message, result)
            except Exception as e:
                errors.append(e)

        tasks = [simulate_task_lifecycle(i) for i in range(10)]
        await asyncio.gather(*tasks)

        assert len(errors) == 0, f"Expected no errors, got: {errors}"


class TestRedisSSLConnectivityCheck:
    """Test Redis SSL connectivity health check."""

    @pytest.mark.asyncio
    async def test_check_redis_ssl_connectivity_with_ssl_url(self) -> None:
        """Verify health check reports SSL enabled for rediss:// URL."""
        with (
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.get_redis_connection_kwargs") as mock_redis_kwargs,
            patch("src.tasks.broker.create_redis_connection") as mock_create_conn,
        ):
            settings = MagicMock()
            settings.REDIS_URL = "rediss://secure-redis:6380"
            mock_settings.return_value = settings
            mock_redis_kwargs.return_value = {"ssl_cert_reqs": "none"}

            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.aclose = AsyncMock()
            mock_create_conn.return_value = mock_client

            from src.tasks.broker import check_redis_ssl_connectivity

            result = await check_redis_ssl_connectivity()

            assert result["healthy"] is True
            assert result["ssl_enabled"] is True
            assert result["ssl_cert_reqs"] == "none"
            assert "error" not in result
            mock_client.ping.assert_called_once()
            mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_redis_ssl_connectivity_with_non_ssl_url(self) -> None:
        """Verify health check reports SSL disabled for redis:// URL."""
        with (
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.get_redis_connection_kwargs") as mock_redis_kwargs,
            patch("src.tasks.broker.create_redis_connection") as mock_create_conn,
        ):
            settings = MagicMock()
            settings.REDIS_URL = "redis://localhost:6379"
            mock_settings.return_value = settings
            mock_redis_kwargs.return_value = {}

            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.aclose = AsyncMock()
            mock_create_conn.return_value = mock_client

            from src.tasks.broker import check_redis_ssl_connectivity

            result = await check_redis_ssl_connectivity()

            assert result["healthy"] is True
            assert result["ssl_enabled"] is False
            assert "ssl_cert_reqs" not in result
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_check_redis_ssl_connectivity_connection_failure(self) -> None:
        """Verify health check reports error on connection failure."""
        import redis.asyncio as redis

        with (
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.get_redis_connection_kwargs") as mock_redis_kwargs,
            patch("src.tasks.broker.create_redis_connection") as mock_create_conn,
        ):
            settings = MagicMock()
            settings.REDIS_URL = "rediss://unreachable:6380"
            mock_settings.return_value = settings
            mock_redis_kwargs.return_value = {"ssl_cert_reqs": "none"}

            mock_create_conn.side_effect = redis.RedisError("Connection refused")

            from src.tasks.broker import check_redis_ssl_connectivity

            result = await check_redis_ssl_connectivity()

            assert result["healthy"] is False
            assert result["ssl_enabled"] is True
            assert result["ssl_cert_reqs"] == "none"
            assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_check_redis_ssl_connectivity_ping_failure(self) -> None:
        """Verify health check reports error when ping fails after connection."""
        import redis.asyncio as redis

        with (
            patch("src.tasks.broker.get_settings") as mock_settings,
            patch("src.tasks.broker.get_redis_connection_kwargs") as mock_redis_kwargs,
            patch("src.tasks.broker.create_redis_connection") as mock_create_conn,
        ):
            settings = MagicMock()
            settings.REDIS_URL = "rediss://secure-redis:6380"
            mock_settings.return_value = settings
            mock_redis_kwargs.return_value = {"ssl_cert_reqs": "none"}

            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(side_effect=redis.RedisError("SSL handshake failed"))
            mock_client.aclose = AsyncMock()
            mock_create_conn.return_value = mock_client

            from src.tasks.broker import check_redis_ssl_connectivity

            result = await check_redis_ssl_connectivity()

            assert result["healthy"] is False
            assert result["ssl_enabled"] is True
            assert "SSL handshake failed" in result["error"]
            mock_client.aclose.assert_called_once()
