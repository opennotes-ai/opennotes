import pytest


@pytest.fixture(autouse=True)
def _shutdown_monitoring_after_test():
    yield
    try:
        from src.monitoring import shutdown_monitoring

        shutdown_monitoring(flush_timeout_millis=100)
    except ImportError:
        pass
