from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.batch_jobs.rechunk_service import (
    ALL_BATCH_JOB_TYPES,
    StuckJobInfo,
    get_stuck_jobs_info,
)
from src.cache.redis_client import redis_client
from src.circuit_breaker import circuit_breaker_registry
from src.config import settings
from src.database import get_db
from src.events.nats_client import nats_client
from src.monitoring import DistributedHealthCoordinator, HealthChecker
from src.monitoring.metrics import (
    batch_job_stuck_count,
    batch_job_stuck_duration_seconds,
)
from src.tasks.broker import get_broker_health, is_broker_initialized

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


@router.get("/health/taskiq", response_model=ServiceStatus)
async def taskiq_health() -> ServiceStatus:
    """
    Check taskiq broker health status.

    Returns status information about the taskiq background task system:
    - Whether the broker is initialized
    - The configured stream name
    - Number of registered tasks
    """
    start = time.time()

    try:
        is_initialized = is_broker_initialized()
        latency_ms = (time.time() - start) * 1000

        if not is_initialized:
            return ServiceStatus(
                status="degraded",
                latency_ms=latency_ms,
                message="Taskiq broker not initialized",
                details=get_broker_health(),
            )

        health_info = get_broker_health()

        return ServiceStatus(
            status="healthy",
            latency_ms=latency_ms,
            message="Taskiq broker is operational",
            details=health_info,
        )

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.error(f"Taskiq health check failed: {e}")
        return ServiceStatus(
            status="unhealthy",
            latency_ms=latency_ms,
            message=f"Taskiq health check failed: {e!s}",
        )


@router.get("/health/batch-jobs", response_model=ServiceStatus)
async def batch_jobs_health(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServiceStatus:
    """
    Check for stuck batch jobs and update Prometheus metrics.

    Returns status information about batch job processing:
    - Number of jobs stuck with zero progress for >30 minutes
    - Details about each stuck job
    - Status is 'degraded' if any jobs are stuck

    Also updates Prometheus metrics for monitoring dashboards.
    """
    start = time.time()

    try:
        stuck_jobs = await get_stuck_jobs_info(db)
        instance_id = settings.INSTANCE_ID

        by_type: dict[str, list[StuckJobInfo]] = {}
        for job in stuck_jobs:
            by_type.setdefault(job.job_type, []).append(job)

        for job_type, jobs in by_type.items():
            batch_job_stuck_count.labels(
                job_type=job_type,
                instance_id=instance_id,
            ).set(len(jobs))
            max_dur = max(j.stuck_duration_seconds for j in jobs)
            batch_job_stuck_duration_seconds.labels(
                job_type=job_type,
                instance_id=instance_id,
            ).set(max_dur)

        for job_type in ALL_BATCH_JOB_TYPES:
            if job_type not in by_type:
                batch_job_stuck_count.labels(
                    job_type=job_type,
                    instance_id=instance_id,
                ).set(0)
                batch_job_stuck_duration_seconds.labels(
                    job_type=job_type,
                    instance_id=instance_id,
                ).set(0)

        latency_ms = (time.time() - start) * 1000

        if stuck_jobs:
            max_duration = max(job.stuck_duration_seconds for job in stuck_jobs)
            stuck_details = [
                {
                    "job_id": str(job.job_id),
                    "job_type": job.job_type,
                    "status": job.status,
                    "stuck_duration_seconds": round(job.stuck_duration_seconds),
                    "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                }
                for job in stuck_jobs
            ]

            return ServiceStatus(
                status="degraded",
                latency_ms=latency_ms,
                message=f"{len(stuck_jobs)} batch job(s) stuck with zero progress",
                details={
                    "stuck_count": len(stuck_jobs),
                    "max_stuck_duration_seconds": round(max_duration),
                    "stuck_jobs": stuck_details,
                },
            )

        return ServiceStatus(
            status="healthy",
            latency_ms=latency_ms,
            message="No stuck batch jobs",
            details={"stuck_count": 0},
        )

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.error(f"Batch jobs health check failed: {e}")
        return ServiceStatus(
            status="unhealthy",
            latency_ms=latency_ms,
            message=f"Batch jobs health check failed: {e!s}",
        )


@router.get("/health/detailed", response_model=HealthCheckResponse)
async def detailed_health(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HealthCheckResponse:
    redis_status = await redis_health()
    nats_status = await nats_health()
    taskiq_status = await taskiq_health()
    batch_jobs_status = await batch_jobs_health(db)

    all_statuses = [redis_status, nats_status, taskiq_status, batch_jobs_status]

    overall_status = "healthy"
    if any(s.status == "unhealthy" for s in all_statuses):
        overall_status = "unhealthy"
    elif any(s.status == "degraded" for s in all_statuses):
        overall_status = "degraded"

    return HealthCheckResponse(
        status=overall_status,
        version=settings.VERSION,
        environment=None,
        services={
            "redis": redis_status,
            "nats": nats_status,
            "taskiq": taskiq_status,
            "batch_jobs": batch_jobs_status,
        },
        components=None,
    )


@router.get("/health/circuit-breakers")
async def circuit_breakers_status() -> dict[str, Any]:
    return circuit_breaker_registry.get_all_status()
