from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from src.cache.redis_client import redis_client
from src.circuit_breaker import circuit_breaker_registry
from src.config import settings
from src.events.nats_client import nats_client
from src.monitoring import DistributedHealthCoordinator, HealthChecker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


def get_health_checker(request: Request) -> HealthChecker:
    """Get health checker from app state."""
    return request.app.state.health_checker


def get_distributed_health(request: Request) -> DistributedHealthCoordinator:
    """Get distributed health coordinator from app state."""
    return request.app.state.distributed_health


class ServiceStatus(BaseModel):
    status: str = Field(..., description="Service status: 'healthy', 'degraded', or 'unhealthy'")
    latency_ms: float | None = Field(None, description="Response latency in milliseconds")
    message: str | None = Field(None, description="Additional status message")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional details")


class HealthCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: str = Field(..., description="Overall system status")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: str = Field(..., description="API version")
    environment: str | None = Field(None, description="Environment name")
    services: dict[str, ServiceStatus] = Field(
        default_factory=dict, description="Individual service statuses"
    )
    components: dict[str, ServiceStatus] | None = Field(
        None, description="Component statuses (alias for services)"
    )


@router.get("/health")
async def health_check(
    health_checker: Annotated[HealthChecker, Depends(get_health_checker)],
) -> Any:
    """Comprehensive health check that checks all registered components."""
    return await health_checker.check_all()


@router.get("/health/live")
async def liveness_check(
    health_checker: Annotated[HealthChecker, Depends(get_health_checker)],
) -> dict[str, bool]:
    """Kubernetes liveness probe endpoint."""
    is_alive = await health_checker.liveness()
    return {"alive": is_alive}


@router.get("/health/ready")
async def readiness_check(
    health_checker: Annotated[HealthChecker, Depends(get_health_checker)],
) -> dict[str, bool]:
    """Kubernetes readiness probe endpoint."""
    is_ready = await health_checker.readiness()
    return {"ready": is_ready}


@router.get("/health/distributed")
async def distributed_health_check(
    distributed_health: Annotated[DistributedHealthCoordinator, Depends(get_distributed_health)],
) -> dict[str, Any]:
    """Get aggregated health status across all instances."""
    return await distributed_health.get_aggregated_status()


@router.get("/health/instances")
async def instances_health_check(
    distributed_health: Annotated[DistributedHealthCoordinator, Depends(get_distributed_health)],
) -> dict[str, Any]:
    """Get health status of all instances."""
    return await distributed_health.get_all_instances_health()


@router.get("/health/instances/{instance_id}")
async def instance_health_check(
    instance_id: str,
    distributed_health: Annotated[DistributedHealthCoordinator, Depends(get_distributed_health)],
) -> dict[str, Any]:
    """Get health status of a specific instance."""
    health_data = await distributed_health.get_instance_health(instance_id)
    if health_data is None:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    return health_data


@router.get("/health/simple", response_model=HealthCheckResponse)
async def simple_health_check() -> HealthCheckResponse:
    """Simple health check that returns basic status without checking components."""
    return HealthCheckResponse(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        services={},
        components={},
    )


@router.get("/health/redis", response_model=ServiceStatus)
async def redis_health() -> ServiceStatus:
    start = time.time()

    try:
        is_connected = await asyncio.wait_for(
            redis_client.ping(), timeout=settings.HEALTH_CHECK_TIMEOUT
        )
        latency_ms = (time.time() - start) * 1000

        if not is_connected:
            return ServiceStatus(
                status="unhealthy",
                latency_ms=latency_ms,
                message="Redis connection failed",
            )

        info = await asyncio.wait_for(
            redis_client.info("stats"), timeout=settings.HEALTH_CHECK_TIMEOUT
        )
        circuit_status = circuit_breaker_registry.get_status("redis")

        return ServiceStatus(
            status="healthy",
            latency_ms=latency_ms,
            message="Redis is operational",
            details={
                "circuit_breaker": circuit_status,
                "connected_clients": info.get("connected_clients", "unknown"),
                "used_memory_human": info.get("used_memory_human", "unknown"),
            },
        )

    except TimeoutError:
        latency_ms = (time.time() - start) * 1000
        logger.error("Redis health check timed out")
        return ServiceStatus(
            status="unhealthy",
            latency_ms=latency_ms,
            message="Health check timed out",
        )
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.error(f"Redis health check failed: {e}")
        return ServiceStatus(
            status="unhealthy",
            latency_ms=latency_ms,
            message=f"Redis health check failed: {e!s}",
        )


@router.get("/health/nats", response_model=ServiceStatus)
async def nats_health() -> ServiceStatus:
    start = time.time()

    try:
        is_connected = await asyncio.wait_for(
            nats_client.is_connected(), timeout=settings.HEALTH_CHECK_TIMEOUT
        )
        latency_ms = (time.time() - start) * 1000

        if not is_connected:
            return ServiceStatus(
                status="unhealthy",
                latency_ms=latency_ms,
                message="NATS connection lost",
            )

        ping_success = await asyncio.wait_for(
            nats_client.ping(), timeout=settings.HEALTH_CHECK_TIMEOUT
        )
        latency_ms = (time.time() - start) * 1000

        if not ping_success:
            return ServiceStatus(
                status="degraded",
                latency_ms=latency_ms,
                message="NATS ping failed",
            )

        circuit_status = circuit_breaker_registry.get_status("nats")

        return ServiceStatus(
            status="healthy",
            latency_ms=latency_ms,
            message="NATS is operational",
            details={
                "circuit_breaker": circuit_status,
                "stream": settings.NATS_STREAM_NAME,
            },
        )

    except TimeoutError:
        latency_ms = (time.time() - start) * 1000
        logger.error("NATS health check timed out")
        return ServiceStatus(
            status="unhealthy",
            latency_ms=latency_ms,
            message="Health check timed out",
        )
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.error(f"NATS health check failed: {e}")
        return ServiceStatus(
            status="unhealthy",
            latency_ms=latency_ms,
            message=f"NATS health check failed: {e!s}",
        )


@router.get("/health/detailed", response_model=HealthCheckResponse)
async def detailed_health() -> HealthCheckResponse:
    redis_status = await redis_health()
    nats_status = await nats_health()

    overall_status = "healthy"
    if redis_status.status == "unhealthy" or nats_status.status == "unhealthy":
        overall_status = "unhealthy"
    elif redis_status.status == "degraded" or nats_status.status == "degraded":
        overall_status = "degraded"

    return HealthCheckResponse(
        status=overall_status,
        version=settings.VERSION,
        environment=None,
        services={
            "redis": redis_status,
            "nats": nats_status,
        },
        components=None,
    )


@router.get("/health/circuit-breakers")
async def circuit_breakers_status() -> dict[str, Any]:
    return circuit_breaker_registry.get_all_status()
