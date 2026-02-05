import asyncio
import contextlib
import json
import time
from typing import Any

from src.cache.redis_client import redis_client
from src.config import settings
from src.monitoring.health import ComponentHealth, HealthStatus
from src.monitoring.logging import get_logger


class DistributedHealthCoordinator:
    INSTANCES_KEY = "health:instances"
    INSTANCE_HEALTH_PREFIX = "health:instance:"
    HEARTBEAT_TTL = settings.HEALTH_CHECK_UNHEALTHY_TIMEOUT + 10

    def __init__(self) -> None:
        self.instance_id = settings.INSTANCE_ID
        self.heartbeat_interval = settings.HEALTH_CHECK_HEARTBEAT_INTERVAL
        self.unhealthy_timeout = settings.HEALTH_CHECK_UNHEALTHY_TIMEOUT
        self._heartbeat_task: asyncio.Task[Any] | None = None

    async def start_heartbeat(self, health_check_func: Any) -> None:
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(health_check_func))

    async def stop_heartbeat(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

    async def _heartbeat_loop(self, health_check_func: Any) -> None:
        logger = get_logger(__name__)
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                health_data = await health_check_func()
                await self._register_instance(health_data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in heartbeat loop: {e}")

    async def _register_instance(self, health_data: Any) -> None:
        try:
            if not redis_client.client:
                return

            instance_key = f"{self.INSTANCE_HEALTH_PREFIX}{self.instance_id}"

            instance_info = {
                "instance_id": self.instance_id,
                "timestamp": time.time(),
                "status": health_data.status.value
                if isinstance(health_data, ComponentHealth)
                else str(health_data),
                "version": settings.VERSION,
                "environment": settings.ENVIRONMENT,
            }

            if isinstance(health_data, ComponentHealth):
                instance_info["latency_ms"] = health_data.latency_ms
                instance_info["error"] = health_data.error
                instance_info["details"] = health_data.details

            await redis_client.client.setex(
                instance_key,
                self.HEARTBEAT_TTL,
                json.dumps(instance_info),
            )

            await self._update_instances_set()
        except Exception:
            pass

    async def _update_instances_set(self) -> None:
        try:
            if not redis_client.client:
                return

            instance_key = f"{self.INSTANCE_HEALTH_PREFIX}{self.instance_id}"
            await redis_client.client.sadd(self.INSTANCES_KEY, self.instance_id)  # type: ignore[reportGeneralClassIssue]

            instances = await redis_client.client.smembers(self.INSTANCES_KEY)  # type: ignore[reportGeneralClassIssue]
            active_instances = []

            for instance_id in instances:
                instance_key = f"{self.INSTANCE_HEALTH_PREFIX}{instance_id}"
                exists = await redis_client.client.exists(instance_key)
                if exists:
                    active_instances.append(instance_id)
                else:
                    await redis_client.client.srem(self.INSTANCES_KEY, instance_id)  # type: ignore[reportGeneralClassIssue]

        except Exception:
            pass

    async def get_all_instances_health(self) -> dict[str, Any]:
        try:
            if not redis_client.client:
                return {}

            instances = await redis_client.client.smembers(self.INSTANCES_KEY)  # type: ignore[reportGeneralClassIssue]
            instances_health = {}
            current_time = time.time()

            for instance_id in instances:
                instance_key = f"{self.INSTANCE_HEALTH_PREFIX}{instance_id}"
                instance_data = await redis_client.client.get(instance_key)

                if instance_data:
                    try:
                        info = json.loads(instance_data)
                        last_heartbeat = info.get("timestamp", current_time)
                        time_since_heartbeat = current_time - last_heartbeat

                        is_healthy = time_since_heartbeat <= self.unhealthy_timeout
                        status = info.get("status", "unknown")

                        if not is_healthy:
                            status = HealthStatus.UNHEALTHY.value

                        instances_health[instance_id] = {
                            "instance_id": instance_id,
                            "status": status,
                            "last_heartbeat": last_heartbeat,
                            "time_since_heartbeat_seconds": time_since_heartbeat,
                            "version": info.get("version"),
                            "environment": info.get("environment"),
                            "latency_ms": info.get("latency_ms"),
                            "error": info.get("error"),
                            "details": info.get("details"),
                        }
                    except json.JSONDecodeError:
                        pass
                else:
                    await redis_client.client.srem(self.INSTANCES_KEY, instance_id)  # type: ignore[reportGeneralClassIssue]

            return instances_health

        except Exception:
            return {}

    async def get_aggregated_status(self) -> dict[str, Any]:
        instances_health = await self.get_all_instances_health()

        if not instances_health:
            return {
                "status": HealthStatus.HEALTHY.value,
                "message": "No instances registered",
                "instance_count": 0,
                "healthy_instances": 0,
                "degraded_instances": 0,
                "unhealthy_instances": 0,
                "instances": {},
            }

        healthy_count = 0
        degraded_count = 0
        unhealthy_count = 0

        for instance in instances_health.values():
            status = instance.get("status", "unknown")
            if status == HealthStatus.HEALTHY.value:
                healthy_count += 1
            elif status == HealthStatus.DEGRADED.value:
                degraded_count += 1
            else:
                unhealthy_count += 1

        overall_status = HealthStatus.HEALTHY.value
        if unhealthy_count > 0:
            overall_status = HealthStatus.UNHEALTHY.value
        elif degraded_count > 0:
            overall_status = HealthStatus.DEGRADED.value

        return {
            "status": overall_status,
            "instance_count": len(instances_health),
            "healthy_instances": healthy_count,
            "degraded_instances": degraded_count,
            "unhealthy_instances": unhealthy_count,
            "instances": instances_health,
        }

    async def get_instance_health(self, instance_id: str) -> dict[str, Any] | None:
        instances_health = await self.get_all_instances_health()
        return instances_health.get(instance_id)
