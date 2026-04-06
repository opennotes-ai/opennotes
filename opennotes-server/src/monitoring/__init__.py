from src.monitoring.distributed_health import DistributedHealthCoordinator
from src.monitoring.errors import record_span_error
from src.monitoring.gcp_resource_detector import (
    detect_gcp_cloud_run_resource,
    is_cloud_run_environment,
)
from src.monitoring.health import (
    HealthChecker,
    HealthCheckResponse,
    HealthStatus,
    ServiceStatus,
)
from src.monitoring.instance import InstanceMetadata, initialize_instance_metadata
from src.monitoring.logging import get_logger, parse_log_level_overrides, setup_logging
from src.monitoring.observability import (
    instrument_fastapi_app,
    setup_observability,
    shutdown_observability,
)
from src.monitoring.otel import is_otel_configured

__all__ = [
    "DistributedHealthCoordinator",
    "HealthCheckResponse",
    "HealthChecker",
    "HealthStatus",
    "InstanceMetadata",
    "ServiceStatus",
    "detect_gcp_cloud_run_resource",
    "get_logger",
    "initialize_instance_metadata",
    "instrument_fastapi_app",
    "is_cloud_run_environment",
    "is_otel_configured",
    "parse_log_level_overrides",
    "record_span_error",
    "setup_logging",
    "setup_observability",
    "shutdown_monitoring",
    "shutdown_observability",
]


def shutdown_monitoring(flush_timeout_millis: int | None = None) -> None:
    shutdown_observability(flush_timeout_millis=flush_timeout_millis)
