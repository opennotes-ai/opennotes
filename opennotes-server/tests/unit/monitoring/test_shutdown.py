import threading
from unittest.mock import patch


class TestShutdownObservability:
    def test_resets_observability_initialized_flag(self):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = True

        with patch("logfire.shutdown"):
            obs_mod.shutdown_observability()

        assert obs_mod._observability_initialized is False

    def test_idempotent_when_not_initialized(self):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False
        obs_mod.shutdown_observability()
        assert obs_mod._observability_initialized is False

    def test_thread_safety_of_initialized_flag(self):
        import src.monitoring.observability as obs_mod

        assert hasattr(obs_mod, "_observability_lock")
        assert isinstance(obs_mod._observability_lock, type(threading.Lock()))


class TestShutdownMonitoring:
    def test_calls_shutdown_observability(self):
        from src.monitoring import shutdown_monitoring

        with patch("src.monitoring.shutdown_observability") as mock_shutdown:
            shutdown_monitoring(flush_timeout_millis=100)
            mock_shutdown.assert_called_once_with(flush_timeout_millis=100)

    def test_exported_from_monitoring_init(self):
        from src.monitoring import __all__

        assert "shutdown_monitoring" in __all__

    def test_passes_default_flush_timeout(self):
        from src.monitoring import shutdown_monitoring

        with patch("src.monitoring.shutdown_observability") as mock_shutdown:
            shutdown_monitoring()
            mock_shutdown.assert_called_once_with(flush_timeout_millis=None)
