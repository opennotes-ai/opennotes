import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings
from src.monitoring.distributed_health import DistributedHealthCoordinator
from src.monitoring.health import ComponentHealth, HealthStatus
from tests.redis_mock import create_stateful_redis_mock


@pytest.mark.asyncio
async def test_distributed_health_coordinator_initialization() -> None:
    coordinator = DistributedHealthCoordinator()

    assert coordinator.instance_id == settings.INSTANCE_ID
    assert coordinator.heartbeat_interval == settings.HEALTH_CHECK_HEARTBEAT_INTERVAL
    assert coordinator.unhealthy_timeout == settings.HEALTH_CHECK_UNHEALTHY_TIMEOUT


@pytest.mark.asyncio
async def test_register_instance(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()

    health_data = ComponentHealth(
        status=HealthStatus.HEALTHY,
        latency_ms=10.0,
    )

    with patch("src.monitoring.distributed_health.redis_client") as mock_redis:
        mock_redis.client = redis_mock
        await coordinator._register_instance(health_data)

        instance_key = f"{coordinator.INSTANCE_HEALTH_PREFIX}{coordinator.instance_id}"
        redis_mock.setex.assert_called_once()

        call_args = redis_mock.setex.call_args
        assert call_args[0][0] == instance_key
        assert call_args[0][1] == coordinator.HEARTBEAT_TTL


@pytest.mark.asyncio
async def test_get_all_instances_health_empty(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()

    redis_mock.smembers = AsyncMock(return_value=set())

    with patch("src.monitoring.distributed_health.redis_client") as mock_redis:
        mock_redis.client = redis_mock
        result = await coordinator.get_all_instances_health()

        assert result == {}


@pytest.mark.asyncio
async def test_get_all_instances_health_with_instances(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()

    instance_data = {
        "instance_id": "opennotes-server-1",
        "timestamp": time.time(),
        "status": "healthy",
        "version": "1.0.0",
        "environment": "test",
        "latency_ms": 5.0,
        "error": None,
        "details": None,
    }

    redis_mock.smembers = AsyncMock(return_value={"opennotes-server-1"})
    redis_mock.get = AsyncMock(return_value=json.dumps(instance_data).encode())
    redis_mock.srem = AsyncMock()

    with patch("src.monitoring.distributed_health.redis_client") as mock_redis:
        mock_redis.client = redis_mock
        result = await coordinator.get_all_instances_health()

        assert "opennotes-server-1" in result
        assert result["opennotes-server-1"]["instance_id"] == "opennotes-server-1"
        assert result["opennotes-server-1"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_get_all_instances_health_unhealthy_timeout(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()

    old_timestamp = time.time() - (coordinator.unhealthy_timeout + 5)
    instance_data = {
        "instance_id": "opennotes-server-1",
        "timestamp": old_timestamp,
        "status": "healthy",
        "version": "1.0.0",
        "environment": "test",
    }

    redis_mock.smembers = AsyncMock(return_value={"opennotes-server-1"})
    redis_mock.get = AsyncMock(return_value=json.dumps(instance_data).encode())
    redis_mock.srem = AsyncMock()

    with patch("src.monitoring.distributed_health.redis_client") as mock_redis:
        mock_redis.client = redis_mock
        result = await coordinator.get_all_instances_health()

        assert result["opennotes-server-1"]["status"] == HealthStatus.UNHEALTHY.value


@pytest.mark.asyncio
async def test_get_aggregated_status_no_instances(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()

    with patch(
        "src.monitoring.distributed_health.DistributedHealthCoordinator.get_all_instances_health",
        new_callable=AsyncMock,
    ) as mock_get_health:
        mock_get_health.return_value = {}

        result = await coordinator.get_aggregated_status()

        assert result["status"] == HealthStatus.HEALTHY.value
        assert result["instance_count"] == 0
        assert result["healthy_instances"] == 0


@pytest.mark.asyncio
async def test_get_aggregated_status_all_healthy(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()

    instances = {
        "opennotes-server-1": {
            "instance_id": "opennotes-server-1",
            "status": HealthStatus.HEALTHY.value,
            "time_since_heartbeat_seconds": 5,
        },
        "opennotes-server-2": {
            "instance_id": "opennotes-server-2",
            "status": HealthStatus.HEALTHY.value,
            "time_since_heartbeat_seconds": 5,
        },
    }

    with patch(
        "src.monitoring.distributed_health.DistributedHealthCoordinator.get_all_instances_health",
        new_callable=AsyncMock,
    ) as mock_get_health:
        mock_get_health.return_value = instances

        result = await coordinator.get_aggregated_status()

        assert result["status"] == HealthStatus.HEALTHY.value
        assert result["instance_count"] == 2
        assert result["healthy_instances"] == 2
        assert result["degraded_instances"] == 0
        assert result["unhealthy_instances"] == 0


@pytest.mark.asyncio
async def test_get_aggregated_status_with_degraded(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()

    instances = {
        "opennotes-server-1": {
            "instance_id": "opennotes-server-1",
            "status": HealthStatus.HEALTHY.value,
        },
        "opennotes-server-2": {
            "instance_id": "opennotes-server-2",
            "status": HealthStatus.DEGRADED.value,
        },
    }

    with patch(
        "src.monitoring.distributed_health.DistributedHealthCoordinator.get_all_instances_health",
        new_callable=AsyncMock,
    ) as mock_get_health:
        mock_get_health.return_value = instances

        result = await coordinator.get_aggregated_status()

        assert result["status"] == HealthStatus.DEGRADED.value
        assert result["healthy_instances"] == 1
        assert result["degraded_instances"] == 1


@pytest.mark.asyncio
async def test_get_aggregated_status_with_unhealthy(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()

    instances = {
        "opennotes-server-1": {
            "instance_id": "opennotes-server-1",
            "status": HealthStatus.HEALTHY.value,
        },
        "opennotes-server-2": {
            "instance_id": "opennotes-server-2",
            "status": HealthStatus.UNHEALTHY.value,
        },
    }

    with patch(
        "src.monitoring.distributed_health.DistributedHealthCoordinator.get_all_instances_health",
        new_callable=AsyncMock,
    ) as mock_get_health:
        mock_get_health.return_value = instances

        result = await coordinator.get_aggregated_status()

        assert result["status"] == HealthStatus.UNHEALTHY.value
        assert result["healthy_instances"] == 1
        assert result["unhealthy_instances"] == 1


@pytest.mark.asyncio
async def test_get_instance_health_found(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()

    instances = {
        "opennotes-server-1": {
            "instance_id": "opennotes-server-1",
            "status": HealthStatus.HEALTHY.value,
        }
    }

    with patch(
        "src.monitoring.distributed_health.DistributedHealthCoordinator.get_all_instances_health",
        new_callable=AsyncMock,
    ) as mock_get_health:
        mock_get_health.return_value = instances

        result = await coordinator.get_instance_health("opennotes-server-1")

        assert result is not None
        assert result["instance_id"] == "opennotes-server-1"


@pytest.mark.asyncio
async def test_get_instance_health_not_found(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()

    with patch(
        "src.monitoring.distributed_health.DistributedHealthCoordinator.get_all_instances_health",
        new_callable=AsyncMock,
    ) as mock_get_health:
        mock_get_health.return_value = {}

        result = await coordinator.get_instance_health("opennotes-server-99")

        assert result is None


@pytest.mark.asyncio
async def test_heartbeat_loop(redis_mock: MagicMock) -> None:
    coordinator = DistributedHealthCoordinator()
    coordinator.heartbeat_interval = 0.01

    health_check_func = AsyncMock(return_value=ComponentHealth(status=HealthStatus.HEALTHY))

    heartbeat_task = asyncio.create_task(coordinator._heartbeat_loop(health_check_func))

    await asyncio.sleep(0.05)
    heartbeat_task.cancel()

    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass

    assert health_check_func.call_count >= 1


@pytest.mark.asyncio
async def test_start_and_stop_heartbeat() -> None:
    coordinator = DistributedHealthCoordinator()
    coordinator.heartbeat_interval = 0.01

    health_check_func = AsyncMock(return_value=ComponentHealth(status=HealthStatus.HEALTHY))

    with patch("src.monitoring.distributed_health.redis_client"):
        await coordinator.start_heartbeat(health_check_func)
        assert coordinator._heartbeat_task is not None
        assert not coordinator._heartbeat_task.done()

        await asyncio.sleep(0.02)

        await coordinator.stop_heartbeat()
        await asyncio.sleep(0.01)

        assert coordinator._heartbeat_task.done()


@pytest.fixture
def redis_mock():
    """
    Create a centralized stateful Redis mock for distributed health tests.

    This fixture uses the StatefulRedisMock which provides full Redis state management
    and realistic behavior for testing distributed health coordination.
    """
    return create_stateful_redis_mock()
