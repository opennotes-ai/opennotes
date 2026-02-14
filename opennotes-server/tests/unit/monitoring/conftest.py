import pytest


@pytest.fixture(autouse=True)
def _shutdown_otel_after_test():
    yield
    try:
        from src.monitoring.otel import shutdown_otel

        shutdown_otel(flush_timeout_millis=100)
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def _reset_traceloop_after_test():
    yield
    try:
        import src.monitoring.traceloop as traceloop_mod

        traceloop_mod._traceloop_configured = False
    except ImportError:
        pass
