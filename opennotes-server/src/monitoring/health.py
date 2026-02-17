import asyncio
import time
from enum import Enum
from typing import Any, Protocol

import httpx
from pydantic import Field
from sqlalchemy import text

from src.common.base_schemas import SQLAlchemySchema
from src.config import settings


class CacheManagerProtocol(Protocol):
    def get_metrics(self) -> dict[str, Any]: ...


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ServiceStatus(SQLAlchemySchema):
    status: str = Field(..., description="Service status: 'healthy', 'degraded', or 'unhealthy'")
    latency_ms: float | None = Field(default=None, description="Response latency in milliseconds")
    message: str | None = Field(default=None, description="Additional status message")
    error: str | None = Field(default=None, description="Error message if unhealthy")
    details: dict[str, Any] | None = Field(default=None, description="Additional details")


ComponentHealth = ServiceStatus


class HealthCheckResponse(SQLAlchemySchema):
    status: str = Field(..., description="Overall system status")
    timestamp: float = Field(default_factory=time.time, description="Unix epoch timestamp")
    version: str = Field(..., description="API version")
    environment: str | None = Field(default=None, description="Environment name")
    components: dict[str, ServiceStatus] = Field(
        default_factory=dict, description="Component statuses"
    )
    uptime_seconds: float | None = Field(default=None, description="Server uptime in seconds")


class VersionResponse(SQLAlchemySchema):
    git_sha: str | None = Field(default=None, description="Git commit SHA")
    build_date: str | None = Field(default=None, description="Build timestamp")
    revision: str | None = Field(default=None, description="Cloud Run revision name")


class HealthChecker:
    def __init__(
        self,
        version: str,
        environment: str,
        component_timeout: float | None = None,
        cache_hit_rate_threshold: float | None = None,
    ) -> None:
        self.version = version
        self.environment = environment
        self.start_time = time.time()
        self._checks: dict[str, Any] = {}
        self.component_timeout = component_timeout or settings.HEALTH_CHECK_COMPONENT_TIMEOUT
        self.cache_hit_rate_threshold = (
            cache_hit_rate_threshold or settings.CACHE_HIT_RATE_THRESHOLD
        )

    def register_check(self, name: str, check_func: Any) -> None:
        self._checks[name] = check_func

    async def check_database(self, db_session: Any) -> ComponentHealth:
        """
        Check database health and verify schema is initialized.

        Verifies:
        1. Database connectivity (SELECT 1)
        2. Critical tables exist (alembic_version, users, notes)

        Returns UNHEALTHY if migrations haven't been run.
        """
        start = time.time()
        try:
            await db_session.execute(text("SELECT 1"))

            critical_tables = ["alembic_version", "users", "notes"]
            missing_tables = []

            for table in critical_tables:
                result = await db_session.execute(
                    text(
                        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"
                    ),
                    {"table_name": table},
                )
                exists = result.scalar()
                if not exists:
                    missing_tables.append(table)

            latency_ms = (time.time() - start) * 1000

            if missing_tables:
                return ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency_ms,
                    error=f"Missing tables: {', '.join(missing_tables)}. Run migrations: alembic upgrade head",
                    details={"missing_tables": missing_tables},
                )

            return ComponentHealth(
                status=HealthStatus.HEALTHY,
                latency_ms=latency_ms,
                details={"schema_initialized": True},
            )
        except Exception as e:
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                error=str(e),
            )

    async def check_redis(self, redis_client: Any) -> ComponentHealth:
        start = time.time()
        try:
            await redis_client.ping()
            latency_ms = (time.time() - start) * 1000
            return ComponentHealth(
                status=HealthStatus.HEALTHY,
                latency_ms=latency_ms,
            )
        except Exception as e:
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                error=str(e),
            )

    async def check_cache(self, cache_manager: CacheManagerProtocol) -> ComponentHealth:
        start = time.time()
        try:
            async with asyncio.timeout(self.component_timeout):
                metrics = cache_manager.get_metrics()
                latency_ms = (time.time() - start) * 1000

                hit_rate = metrics.get("hit_rate", 0.0)
                status = HealthStatus.HEALTHY

                if hit_rate < self.cache_hit_rate_threshold:
                    status = HealthStatus.DEGRADED

                return ComponentHealth(
                    status=status,
                    latency_ms=latency_ms,
                    details={
                        "hits": metrics.get("hits", 0),
                        "misses": metrics.get("misses", 0),
                        "hit_rate_percent": round(hit_rate * 100, 2),
                        "size": metrics.get("size", 0),
                        "evictions": metrics.get("evictions", 0),
                        "threshold_percent": round(self.cache_hit_rate_threshold * 100, 2),
                    },
                )
        except TimeoutError:
            return ComponentHealth(
                status=HealthStatus.DEGRADED,
                error=f"Cache check timeout after {self.component_timeout}s",
            )
        except Exception as e:
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                error=str(e),
            )

    async def check_external_service(
        self,
        url: str,
        timeout: float = 5.0,
    ) -> ComponentHealth:
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                latency_ms = (time.time() - start) * 1000

                if response.status_code == 200:
                    return ComponentHealth(
                        status=HealthStatus.HEALTHY,
                        latency_ms=latency_ms,
                    )
                return ComponentHealth(
                    status=HealthStatus.DEGRADED,
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}",
                )
        except httpx.TimeoutException:
            return ComponentHealth(
                status=HealthStatus.DEGRADED,
                error="Timeout",
            )
        except Exception as e:
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                error=str(e),
            )

    async def check_all(self) -> HealthCheckResponse:
        components: dict[str, ComponentHealth] = {}
        tasks = {}

        for name, check_func in self._checks.items():
            tasks[name] = asyncio.create_task(check_func())

        for name, task in tasks.items():
            try:
                components[name] = await task
            except Exception as e:
                components[name] = ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    error=str(e),
                )

        overall_status = self._determine_overall_status(components)
        uptime = time.time() - self.start_time

        return HealthCheckResponse(
            status=overall_status,
            timestamp=time.time(),
            version=self.version,
            environment=self.environment,
            components=components,
            uptime_seconds=uptime,
        )

    def _determine_overall_status(
        self,
        components: dict[str, ComponentHealth],
    ) -> HealthStatus:
        if not components:
            return HealthStatus.HEALTHY

        unhealthy_count = sum(1 for c in components.values() if c.status == HealthStatus.UNHEALTHY)
        degraded_count = sum(1 for c in components.values() if c.status == HealthStatus.DEGRADED)

        if unhealthy_count > 0:
            return HealthStatus.UNHEALTHY
        if degraded_count > 0:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    async def readiness(self) -> bool:
        result = await self.check_all()
        critical_components = ["database", "redis", "cache"]

        for component in critical_components:
            if (
                component in result.components
                and result.components[component].status == HealthStatus.UNHEALTHY
            ):
                return False

        return True

    async def liveness(self) -> bool:
        try:
            async with asyncio.timeout(1.0):
                await asyncio.sleep(0.001)
                return True
        except TimeoutError:
            return False
