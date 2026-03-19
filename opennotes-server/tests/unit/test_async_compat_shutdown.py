import pytest

from src.utils.async_compat import (
    _bg_state,
    _ensure_background_loop,
    reset,
    run_sync,
    shutdown,
)


class TestShutdownFlag:
    def setup_method(self):
        reset()

    def teardown_method(self):
        reset()

    def test_ensure_background_loop_raises_after_shutdown(self):
        shutdown()
        with pytest.raises(RuntimeError, match="shutting down"):
            _ensure_background_loop()

    def test_run_sync_raises_after_shutdown(self):
        shutdown()

        async def noop():
            return 42

        with pytest.raises(RuntimeError, match="shutting down"):
            run_sync(noop())

    def test_shutdown_sets_shutting_down_flag(self):
        assert _bg_state["shutting_down"] is False
        shutdown()
        assert _bg_state["shutting_down"] is True

    def test_reset_clears_shutting_down_flag(self):
        shutdown()
        assert _bg_state["shutting_down"] is True
        reset()
        assert _bg_state["shutting_down"] is False

    def test_background_loop_works_after_reset(self):
        shutdown()
        reset()

        async def add(a, b):
            return a + b

        result = run_sync(add(1, 2))
        assert result == 3


class TestShutdownTimeout:
    def setup_method(self):
        reset()

    def teardown_method(self):
        reset()

    def test_shutdown_default_timeout_is_2s(self):
        import inspect

        sig = inspect.signature(shutdown)
        timeout_param = sig.parameters.get("timeout")
        assert timeout_param is not None
        assert timeout_param.default == 2.0
