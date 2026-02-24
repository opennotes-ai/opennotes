import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from src.monitoring import HealthChecker, get_logger


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "version" in data
    assert "components" in data


def test_liveness_endpoint(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert "alive" in data
    assert data["alive"] is True


def test_readiness_endpoint(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "ready" in data


def test_otel_metrics_recorded() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test-monitoring")

    counter = meter.create_counter("test.http.requests")
    up_down = meter.create_up_down_counter("test.active_requests")
    histogram = meter.create_histogram("test.http.duration")
    errors = meter.create_counter("test.errors")

    counter.add(1, {"method": "GET", "endpoint": "/test", "status": "200"})
    up_down.add(1)
    up_down.add(-1)
    histogram.record(0.5, {"method": "GET", "endpoint": "/test"})
    errors.add(1, {"error_type": "TestError", "endpoint": "/test"})

    metrics_data = reader.get_metrics_data()
    assert metrics_data is not None
    resource_metrics = metrics_data.resource_metrics
    assert len(resource_metrics) > 0
    scope_metrics = resource_metrics[0].scope_metrics
    assert len(scope_metrics) > 0
    recorded_metrics = scope_metrics[0].metrics
    assert len(recorded_metrics) == 4


def test_structured_logging() -> None:
    logger = get_logger(__name__)
    logger.info("Test log message", extra={"test_key": "test_value"})


def test_health_checker() -> None:
    checker = HealthChecker(version="1.0.0", environment="test")

    async def dummy_check():
        from src.monitoring.health import ComponentHealth, HealthStatus

        return ComponentHealth(status=HealthStatus.HEALTHY)

    checker.register_check("test", dummy_check)
    assert "test" in checker._checks


@pytest.mark.asyncio
async def test_health_check_execution() -> None:
    from src.monitoring.health import ComponentHealth, HealthStatus

    checker = HealthChecker(version="1.0.0", environment="test")

    async def healthy_check():
        return ComponentHealth(status=HealthStatus.HEALTHY, latency_ms=10.0)

    async def unhealthy_check():
        return ComponentHealth(status=HealthStatus.UNHEALTHY, error="Test error")

    checker.register_check("healthy", healthy_check)
    checker.register_check("unhealthy", unhealthy_check)

    result = await checker.check_all()

    assert result.status == HealthStatus.UNHEALTHY
    assert "healthy" in result.components
    assert "unhealthy" in result.components
    assert result.components["healthy"].status == HealthStatus.HEALTHY
    assert result.components["unhealthy"].status == HealthStatus.UNHEALTHY


@pytest.mark.asyncio
async def test_readiness_check() -> None:
    from src.monitoring.health import ComponentHealth, HealthStatus

    checker = HealthChecker(version="1.0.0", environment="test")

    async def database_check():
        return ComponentHealth(status=HealthStatus.HEALTHY)

    async def redis_check():
        return ComponentHealth(status=HealthStatus.HEALTHY)

    checker.register_check("database", database_check)
    checker.register_check("redis", redis_check)

    is_ready = await checker.readiness()
    assert is_ready is True


@pytest.mark.asyncio
async def test_readiness_check_fails_on_unhealthy() -> None:
    from src.monitoring.health import ComponentHealth, HealthStatus

    checker = HealthChecker(version="1.0.0", environment="test")

    async def database_check():
        return ComponentHealth(status=HealthStatus.UNHEALTHY, error="DB down")

    checker.register_check("database", database_check)

    is_ready = await checker.readiness()
    assert is_ready is False


def test_dbos_health_endpoint(client: TestClient) -> None:
    """Test DBOS health endpoint returns expected response structure."""
    response = client.get("/health/dbos")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "latency_ms" in data
    assert "details" in data


def test_dbos_health_endpoint_returns_schema_info(client: TestClient) -> None:
    """Test DBOS health endpoint includes schema configuration."""
    response = client.get("/health/dbos")
    assert response.status_code == 200
    data = response.json()
    details = data.get("details", {})
    if details.get("enabled") is not False:
        assert "schema_name" in details or data.get("message") == "DBOS disabled in test mode"


def test_detailed_health_includes_dbos(client: TestClient) -> None:
    """Test /health/detailed includes DBOS in components list."""
    response = client.get("/health/detailed")
    assert response.status_code == 200
    data = response.json()
    assert "components" in data
    components = data["components"]
    assert "dbos" in components
    assert components["dbos"]["status"] in ("healthy", "degraded", "unhealthy")
