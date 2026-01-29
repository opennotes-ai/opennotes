import pytest
from fastapi.testclient import TestClient

from src.monitoring import HealthChecker, get_logger
from src.monitoring.metrics import (
    active_requests,
    errors_total,
    http_request_duration_seconds,
    http_requests_total,
    notes_scored_total,
)


def test_metrics_endpoint(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"http_requests_total" in response.content
    assert b"http_request_duration_seconds" in response.content


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


def test_metrics_collection() -> None:
    from src.monitoring.instance import InstanceMetadata

    instance_id = InstanceMetadata.get_instance_id()
    initial_value = http_requests_total._metrics.get(("GET", "/test", "200", instance_id))
    initial_count = initial_value._value._value if initial_value else 0

    http_requests_total.labels(
        method="GET", endpoint="/test", status="200", instance_id=instance_id
    ).inc()

    new_metric = http_requests_total._metrics.get(("GET", "/test", "200", instance_id))
    assert new_metric is not None
    new_count = new_metric._value._value
    assert new_count == initial_count + 1


def test_active_requests_gauge() -> None:
    from src.monitoring.instance import InstanceMetadata

    instance_id = InstanceMetadata.get_instance_id()
    gauge = active_requests.labels(instance_id=instance_id)
    initial_value = gauge._value._value if hasattr(gauge, "_value") else 0
    gauge.inc()
    assert gauge._value._value >= initial_value
    gauge.dec()
    assert gauge._value._value >= 0


def test_histogram_observation() -> None:
    from src.monitoring.instance import InstanceMetadata

    instance_id = InstanceMetadata.get_instance_id()
    http_request_duration_seconds.labels(
        method="GET", endpoint="/test", instance_id=instance_id
    ).observe(0.5)


def test_error_metric() -> None:
    from src.monitoring.instance import InstanceMetadata

    instance_id = InstanceMetadata.get_instance_id()
    errors_total.labels(error_type="TestError", endpoint="/test", instance_id=instance_id).inc()


def test_business_metrics() -> None:
    from src.monitoring.instance import InstanceMetadata

    instance_id = InstanceMetadata.get_instance_id()
    notes_scored_total.labels(status="success", instance_id=instance_id).inc(10)


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
    """Test /health/detailed includes DBOS in services list."""
    response = client.get("/health/detailed")
    assert response.status_code == 200
    data = response.json()
    assert "services" in data
    services = data["services"]
    assert "dbos" in services
    assert services["dbos"]["status"] in ("healthy", "degraded", "unhealthy")
