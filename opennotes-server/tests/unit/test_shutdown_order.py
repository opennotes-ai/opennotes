from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import _shutdown_services
from src.utils.async_compat import reset as reset_bg_loop

pytestmark = pytest.mark.serial


def _build_mock_app():
    app = MagicMock()
    app.state = MagicMock()
    return app


def _build_patches(call_order):
    return [
        patch("src.main.distributed_health.stop_heartbeat", new_callable=AsyncMock),
        patch("src.main.nats_client.disconnect", new_callable=AsyncMock),
        patch("src.main.close_discord_client", new_callable=AsyncMock),
        patch("src.main.rate_limiter.disconnect", new_callable=AsyncMock),
        patch("src.main.interaction_cache.disconnect", new_callable=AsyncMock),
        patch("src.main.redis_client.disconnect", new_callable=AsyncMock),
        patch(
            "src.main._destroy_dbos",
            side_effect=lambda *a, **kw: call_order.append("dbos"),
        ),
        patch(
            "src.main.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=lambda fn, *a, **kw: call_order.append("async_compat"),
        ),
        patch(
            "src.main.close_db",
            new_callable=AsyncMock,
            side_effect=lambda: call_order.append("close_db"),
        ),
    ]


class TestShutdownOrder:
    def setup_method(self):
        reset_bg_loop()

    def teardown_method(self):
        reset_bg_loop()

    @pytest.mark.asyncio
    async def test_shutdown_order_full_server(self):
        call_order: list[str] = []
        app = _build_mock_app()

        patches = _build_patches(call_order)
        for p in patches:
            p.start()
        try:
            await _shutdown_services(app, is_dbos_worker=False)
        finally:
            for p in patches:
                p.stop()

        assert call_order == ["dbos", "async_compat", "close_db"]

    @pytest.mark.asyncio
    async def test_shutdown_order_dbos_worker(self):
        call_order: list[str] = []
        app = _build_mock_app()

        patches = _build_patches(call_order)
        patches.append(
            patch(
                "src.dbos_workflows.token_bucket.config.stop_worker_heartbeat",
                new_callable=AsyncMock,
            )
        )
        patches.append(
            patch(
                "src.dbos_workflows.token_bucket.config.deregister_worker_async",
                new_callable=AsyncMock,
            )
        )
        for p in patches:
            p.start()
        try:
            await _shutdown_services(app, is_dbos_worker=True)
        finally:
            for p in patches:
                p.stop()

        assert call_order == ["dbos", "async_compat", "close_db"]

    @pytest.mark.asyncio
    async def test_shutting_down_flag_set_after_shutdown(self):
        from src.utils.async_compat import _bg_state, reset

        reset()

        call_order: list[str] = []
        app = _build_mock_app()

        def fake_to_thread(fn, *args, **kwargs):
            fn(*args, **kwargs)
            call_order.append("async_compat")

        patches = [
            patch("src.main.distributed_health.stop_heartbeat", new_callable=AsyncMock),
            patch("src.main.nats_client.disconnect", new_callable=AsyncMock),
            patch("src.main.close_discord_client", new_callable=AsyncMock),
            patch("src.main.rate_limiter.disconnect", new_callable=AsyncMock),
            patch("src.main.interaction_cache.disconnect", new_callable=AsyncMock),
            patch("src.main.redis_client.disconnect", new_callable=AsyncMock),
            patch("src.main._destroy_dbos", side_effect=lambda *a, **kw: call_order.append("dbos")),
            patch("src.main.asyncio.to_thread", new_callable=AsyncMock, side_effect=fake_to_thread),
            patch(
                "src.main.close_db",
                new_callable=AsyncMock,
                side_effect=lambda: call_order.append("close_db"),
            ),
        ]
        for p in patches:
            p.start()
        try:
            await _shutdown_services(app, is_dbos_worker=False)
        finally:
            for p in patches:
                p.stop()

        assert _bg_state["shutting_down"] is True
        reset()
