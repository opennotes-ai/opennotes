import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import _startup_background, lifespan


def _build_mock_app():
    app = MagicMock()
    app.state = MagicMock()
    app.state.startup_complete = False
    app.state.startup_failed = False
    return app


def _make_cancelled_task():
    """Create a future that raises CancelledError when awaited, mimicking a cancelled asyncio.Task."""
    fut = asyncio.get_event_loop().create_future()
    fut.cancel()
    return fut


def _build_background_patches(
    migrations_side_effect=None,
    init_db_side_effect=None,
):
    return {
        "run_startup_migrations": patch(
            "src.main.run_startup_migrations",
            new_callable=AsyncMock,
            side_effect=migrations_side_effect,
        ),
        "init_db": patch(
            "src.main.init_db",
            new_callable=AsyncMock,
            side_effect=init_db_side_effect,
        ),
        "_init_dbos": patch("src.main._init_dbos", new_callable=AsyncMock),
        "redis_connect": patch("src.main.redis_client.connect", new_callable=AsyncMock),
        "rate_limiter_connect": patch("src.main.rate_limiter.connect", new_callable=AsyncMock),
        "interaction_cache_connect": patch(
            "src.main.interaction_cache.connect", new_callable=AsyncMock
        ),
        "_connect_nats": patch("src.main._connect_nats", new_callable=AsyncMock),
        "_init_worker_services": patch(
            "src.main._init_worker_services",
            new_callable=AsyncMock,
            return_value=(None, None),
        ),
        "_register_health_checks": patch("src.main._register_health_checks"),
        "distributed_health_start": patch(
            "src.main.distributed_health.start_heartbeat", new_callable=AsyncMock
        ),
        "settings": patch("src.main.settings"),
    }


def _start_patches(patches):
    mocks = {}
    for name, p in patches.items():
        mocks[name] = p.start()
    mocks["settings"].TESTING = False
    mocks["settings"].SERVER_MODE = "full"
    mocks["settings"].PROJECT_NAME = "test"
    mocks["settings"].VERSION = "0.0.0"
    mocks["settings"].ENVIRONMENT = "test"
    mocks["settings"].DEBUG = False
    mocks["settings"].INSTANCE_ID = "test-instance"
    return mocks


def _stop_patches(patches):
    for p in patches.values():
        p.stop()


class TestStartupBackground:
    @pytest.mark.asyncio
    async def test_background_task_sets_startup_complete(self):
        app = _build_mock_app()
        patches = _build_background_patches()
        _start_patches(patches)
        try:
            await _startup_background(app, is_dbos_worker=False)
            assert app.state.startup_complete is True
            assert app.state.startup_failed is not True
        finally:
            _stop_patches(patches)

    @pytest.mark.asyncio
    async def test_background_task_calls_init_chain_in_order(self):
        app = _build_mock_app()
        call_order: list[str] = []

        patches = _build_background_patches()
        mocks = _start_patches(patches)

        mocks["run_startup_migrations"].side_effect = lambda *a: call_order.append("migrations")
        mocks["init_db"].side_effect = lambda: call_order.append("init_db")
        mocks["_init_dbos"].side_effect = lambda *a: call_order.append("init_dbos")
        mocks["redis_connect"].side_effect = lambda: call_order.append("redis")
        mocks["_connect_nats"].side_effect = lambda: call_order.append("nats")
        mocks["_init_worker_services"].side_effect = lambda *a, **kw: (
            call_order.append("worker_services"),
            (None, None),
        )[1]
        mocks["_register_health_checks"].side_effect = lambda *a: call_order.append("health_checks")
        mocks["distributed_health_start"].side_effect = lambda *a: call_order.append("heartbeat")

        try:
            await _startup_background(app, is_dbos_worker=False)
            assert call_order == [
                "migrations",
                "init_db",
                "init_dbos",
                "redis",
                "nats",
                "worker_services",
                "health_checks",
                "heartbeat",
            ]
        finally:
            _stop_patches(patches)

    @pytest.mark.asyncio
    async def test_background_task_exits_on_failure(self):
        app = _build_mock_app()
        patches = _build_background_patches(
            migrations_side_effect=RuntimeError("lock timeout"),
        )
        _start_patches(patches)
        try:
            with patch("src.main.os._exit") as mock_exit:
                await _startup_background(app, is_dbos_worker=False)
                mock_exit.assert_called_once_with(1)
                assert app.state.startup_failed is True
        finally:
            _stop_patches(patches)

    @pytest.mark.asyncio
    async def test_background_task_exits_on_init_db_failure(self):
        app = _build_mock_app()
        patches = _build_background_patches(
            init_db_side_effect=RuntimeError("connection refused"),
        )
        _start_patches(patches)
        try:
            with patch("src.main.os._exit") as mock_exit:
                await _startup_background(app, is_dbos_worker=False)
                mock_exit.assert_called_once_with(1)
                assert app.state.startup_failed is True
                assert app.state.startup_complete is not True
        finally:
            _stop_patches(patches)

    @pytest.mark.asyncio
    async def test_background_task_handles_cancelled_error(self):
        app = _build_mock_app()
        patches = _build_background_patches()
        mocks = _start_patches(patches)
        mocks["run_startup_migrations"].side_effect = asyncio.CancelledError()
        try:
            with patch("src.main.os._exit") as mock_exit:
                with pytest.raises(asyncio.CancelledError):
                    await _startup_background(app, is_dbos_worker=False)
                mock_exit.assert_not_called()
                assert app.state.startup_failed is not True
        finally:
            _stop_patches(patches)

    @pytest.mark.asyncio
    async def test_background_task_skips_migrations_in_testing(self):
        app = _build_mock_app()
        patches = _build_background_patches()
        mocks = _start_patches(patches)
        mocks["settings"].TESTING = True
        try:
            await _startup_background(app, is_dbos_worker=False)
            mocks["run_startup_migrations"].assert_not_called()
            assert app.state.startup_complete is True
        finally:
            _stop_patches(patches)


class TestLifespanBackground:
    @pytest.mark.asyncio
    async def test_lifespan_yields_immediately(self):
        app = _build_mock_app()
        created_tasks: list = []

        def fake_create_task(coro, *, name=None):
            coro.close()
            task = _make_cancelled_task()
            created_tasks.append({"name": name, "task": task})
            return task

        with (
            patch("src.main._validate_encryption_key"),
            patch("src.main._run_startup_validation", new_callable=AsyncMock),
            patch("src.main.settings") as mock_settings,
            patch("src.main.asyncio.create_task", side_effect=fake_create_task),
            patch("src.main._shutdown_services", new_callable=AsyncMock),
        ):
            mock_settings.PROJECT_NAME = "test"
            mock_settings.VERSION = "0.0.0"
            mock_settings.ENVIRONMENT = "test"
            mock_settings.DEBUG = False
            mock_settings.SERVER_MODE = "full"

            async with lifespan(app):
                assert len(created_tasks) == 1
                assert created_tasks[0]["name"] == "startup-init"

    @pytest.mark.asyncio
    async def test_lifespan_sets_initial_state_before_yield(self):
        app = _build_mock_app()

        def fake_create_task(coro, *, name=None):
            coro.close()
            return _make_cancelled_task()

        with (
            patch("src.main._validate_encryption_key"),
            patch("src.main._run_startup_validation", new_callable=AsyncMock),
            patch("src.main.settings") as mock_settings,
            patch("src.main.asyncio.create_task", side_effect=fake_create_task),
            patch("src.main._shutdown_services", new_callable=AsyncMock),
            patch("src.main.health_checker") as mock_hc,
            patch("src.main.distributed_health") as mock_dh,
        ):
            mock_settings.PROJECT_NAME = "test"
            mock_settings.VERSION = "0.0.0"
            mock_settings.ENVIRONMENT = "test"
            mock_settings.DEBUG = False
            mock_settings.SERVER_MODE = "full"

            async with lifespan(app):
                assert app.state.startup_complete is False
                assert app.state.startup_failed is False
                assert app.state.health_checker == mock_hc
                assert app.state.distributed_health == mock_dh

    @pytest.mark.asyncio
    async def test_shutdown_skipped_when_not_complete(self):
        app = _build_mock_app()
        app.state.startup_complete = False

        def fake_create_task(coro, *, name=None):
            coro.close()
            return _make_cancelled_task()

        with (
            patch("src.main._validate_encryption_key"),
            patch("src.main._run_startup_validation", new_callable=AsyncMock),
            patch("src.main.settings") as mock_settings,
            patch("src.main.asyncio.create_task", side_effect=fake_create_task),
            patch("src.main._shutdown_services", new_callable=AsyncMock) as mock_shutdown,
        ):
            mock_settings.PROJECT_NAME = "test"
            mock_settings.VERSION = "0.0.0"
            mock_settings.ENVIRONMENT = "test"
            mock_settings.DEBUG = False
            mock_settings.SERVER_MODE = "full"

            async with lifespan(app):
                pass

            mock_shutdown.assert_not_called()

    @pytest.mark.asyncio
    async def test_shutdown_called_when_complete(self):
        app = _build_mock_app()

        def fake_create_task(coro, *, name=None):
            coro.close()
            return _make_cancelled_task()

        with (
            patch("src.main._validate_encryption_key"),
            patch("src.main._run_startup_validation", new_callable=AsyncMock),
            patch("src.main.settings") as mock_settings,
            patch("src.main.asyncio.create_task", side_effect=fake_create_task),
            patch("src.main._shutdown_services", new_callable=AsyncMock) as mock_shutdown,
        ):
            mock_settings.PROJECT_NAME = "test"
            mock_settings.VERSION = "0.0.0"
            mock_settings.ENVIRONMENT = "test"
            mock_settings.DEBUG = False
            mock_settings.SERVER_MODE = "full"

            async with lifespan(app):
                app.state.startup_complete = True

            mock_shutdown.assert_called_once_with(app, False)

    @pytest.mark.asyncio
    async def test_init_task_cancelled_on_shutdown(self):
        app = _build_mock_app()
        cancel_called = False

        def fake_create_task(coro, *, name=None):
            coro.close()
            fut = asyncio.get_event_loop().create_future()

            original_cancel = fut.cancel

            def tracked_cancel(*args, **kwargs):
                nonlocal cancel_called
                cancel_called = True
                return original_cancel(*args, **kwargs)

            fut.cancel = tracked_cancel
            return fut

        with (
            patch("src.main._validate_encryption_key"),
            patch("src.main._run_startup_validation", new_callable=AsyncMock),
            patch("src.main.settings") as mock_settings,
            patch("src.main.asyncio.create_task", side_effect=fake_create_task),
            patch("src.main._shutdown_services", new_callable=AsyncMock),
        ):
            mock_settings.PROJECT_NAME = "test"
            mock_settings.VERSION = "0.0.0"
            mock_settings.ENVIRONMENT = "test"
            mock_settings.DEBUG = False
            mock_settings.SERVER_MODE = "full"

            async with lifespan(app):
                pass

            assert cancel_called is True
