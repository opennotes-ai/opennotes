import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from slowapi.errors import RateLimitExceeded

_testing = os.getenv("TESTING", "false").lower() == "true"
_otel_enabled = os.getenv("ENABLE_TRACING", "true").lower() == "true"

if _otel_enabled and not _testing:
    from src.monitoring.otel import setup_otel

    _service_name = os.getenv("OTEL_SERVICE_NAME", "opennotes-server")
    _service_version = os.getenv("SERVICE_VERSION", "0.0.1")
    _environment = os.getenv("ENVIRONMENT", "development")
    _otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTLP_ENDPOINT")
    _otlp_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS") or os.getenv("OTLP_HEADERS")
    _sample_rate = float(
        os.getenv("TRACING_SAMPLE_RATE") or os.getenv("TRACE_SAMPLE_RATE") or "1.0"
    )
    _console_export = os.getenv("ENABLE_CONSOLE_TRACING", "false").lower() == "true"

    setup_otel(
        service_name=_service_name,
        service_version=_service_version,
        environment=_environment,
        otlp_endpoint=_otlp_endpoint,
        otlp_headers=_otlp_headers,
        sample_rate=_sample_rate,
        enable_console_export=_console_export,
    )

LoggingInstrumentor().instrument(set_logging_format=False)

from src.batch_jobs.router import router as batch_jobs_router
from src.bulk_content_scan.jsonapi_router import router as bulk_content_scan_jsonapi_router
from src.bulk_content_scan.nats_handler import BulkScanEventHandler
from src.cache.cache import cache_manager
from src.cache.redis_client import redis_client
from src.community_config.router import router as community_config_router
from src.community_servers.admin_router import router as community_admin_router
from src.community_servers.clear_router import router as community_clear_router
from src.community_servers.router import router as community_servers_router
from src.config import settings
from src.config_router import router as config_router
from src.database import close_db, get_session_maker, init_db
from src.dbos_workflows.config import get_dbos
from src.events.nats_client import nats_client
from src.events.schemas import EventType
from src.events.subscriber import event_subscriber
from src.fact_checking.chunk_router import router as chunk_router
from src.fact_checking.embedding_service import EmbeddingService
from src.fact_checking.embeddings_jsonapi_router import (
    router as embeddings_jsonapi_router,
)
from src.fact_checking.hybrid_searches_jsonapi_router import (
    router as hybrid_searches_jsonapi_router,
)
from src.fact_checking.import_pipeline.candidates_jsonapi_router import (
    router as candidates_jsonapi_router,
)
from src.fact_checking.import_pipeline.router import router as fact_check_import_router
from src.fact_checking.monitored_channels_jsonapi_router import (
    router as monitored_channels_jsonapi_router,
)
from src.fact_checking.previously_seen_jsonapi_router import (
    router as previously_seen_jsonapi_router,
)
from src.health import router as health_router
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.router import router as llm_config_router
from src.llm_config.service import LLMService
from src.middleware.audit import AuditMiddleware
from src.middleware.csrf import CSRFMiddleware
from src.middleware.discord_context import DiscordContextMiddleware
from src.middleware.internal_auth import InternalHeaderValidationMiddleware
from src.middleware.rate_limiting import limiter
from src.middleware.request_size import RequestSizeLimitMiddleware
from src.middleware.security import SecurityHeadersMiddleware
from src.middleware.timeout import TimeoutMiddleware
from src.middleware.user_context import AuthenticatedUserContextMiddleware
from src.monitoring import (
    DistributedHealthCoordinator,
    HealthChecker,
    MetricsMiddleware,
    get_logger,
    get_metrics,
    initialize_instance_metadata,
    setup_logging,
)
from src.monitoring.health import ComponentHealth, HealthStatus
from src.notes.note_publisher_jsonapi_router import (
    router as note_publisher_jsonapi_router,
)
from src.notes.notes_jsonapi_router import router as jsonapi_notes_router
from src.notes.ratings_jsonapi_router import router as ratings_jsonapi_router
from src.notes.requests_jsonapi_router import router as requests_jsonapi_router
from src.notes.scoring_jsonapi_router import router as scoring_jsonapi_router
from src.notes.stats_jsonapi_router import router as stats_jsonapi_router
from src.search.fusion_weights_router import router as fusion_weights_router
from src.services.ai_note_writer import AINoteWriter
from src.services.vision_service import VisionService
from src.startup_validation import run_startup_checks
from src.tasks.broker import PullBasedJetStreamBroker, get_broker, reset_broker
from src.users.admin_router import router as admin_router
from src.users.communities_jsonapi_router import router as communities_jsonapi_router
from src.users.profile_router import router as profile_auth_router
from src.users.profiles_jsonapi_router import router as profiles_jsonapi_router
from src.users.router import router as auth_router
from src.webhooks.cache import interaction_cache
from src.webhooks.discord_client import close_discord_client
from src.webhooks.rate_limit import rate_limiter
from src.webhooks.router import router as webhook_router
from src.workers.vision_worker import VisionDescriptionHandler

setup_logging(
    log_level=settings.LOG_LEVEL,
    json_format=settings.ENABLE_JSON_LOGGING,
    service_name=settings.PROJECT_NAME,
)
logger = get_logger(__name__)

initialize_instance_metadata(
    instance_id=settings.INSTANCE_ID,
    environment=settings.ENVIRONMENT,
)
logger.info(f"Instance metadata initialized: {settings.INSTANCE_ID}")

if settings.TRACELOOP_ENABLED and not settings.TESTING:
    from src.monitoring.otel import get_otlp_exporter
    from src.monitoring.traceloop import setup_traceloop

    setup_traceloop(
        app_name=settings.PROJECT_NAME,
        service_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        instance_id=settings.INSTANCE_ID,
        otlp_endpoint=settings.OTLP_ENDPOINT,
        otlp_headers=settings.OTLP_HEADERS,
        trace_content=settings.TRACELOOP_TRACE_CONTENT,
        exporter=get_otlp_exporter(),
    )

health_checker = HealthChecker(
    version=settings.VERSION,
    environment=settings.ENVIRONMENT,
)

distributed_health = DistributedHealthCoordinator()


async def _connect_nats() -> None:
    """Connect to NATS, allowing failure in test mode."""
    try:
        await nats_client.connect()
        logger.info("NATS connection established")
    except Exception as e:
        logger.error(f"Failed to connect to NATS: {e}")
        if settings.TESTING or settings.ENVIRONMENT == "test":
            logger.warning("Running in test mode - continuing without NATS connection")
        else:
            raise


async def _start_taskiq_broker() -> PullBasedJetStreamBroker | None:
    """Start taskiq broker for background task dispatch, allowing failure in test mode."""
    try:
        taskiq_broker = get_broker()
        await taskiq_broker.startup()
        logger.info("Taskiq broker started for task dispatch")
        return taskiq_broker
    except Exception as e:
        logger.error(f"Failed to start taskiq broker: {e}")
        if settings.TESTING or settings.ENVIRONMENT == "test":
            logger.warning("Running in test mode - continuing without taskiq broker")
            return None
        raise


async def _init_ai_services() -> tuple[
    AINoteWriter | None, VisionService | None, LLMService | None
]:
    """Initialize AI Note Writer and Vision services if enabled.

    Returns:
        Tuple of (ai_note_writer, vision_service, llm_service) or (None, None, None) if disabled.
    """
    if not settings.AI_NOTE_WRITING_ENABLED:
        logger.info("AI Note Writer and Vision services disabled (AI_NOTE_WRITING_ENABLED=False)")
        return None, None, None

    llm_client_manager = LLMClientManager(
        encryption_service=EncryptionService(settings.ENCRYPTION_MASTER_KEY)
    )
    llm_service = LLMService(client_manager=llm_client_manager)
    vision_service = VisionService(llm_service=llm_service)
    logger.info("Vision service initialized")

    ai_note_writer = AINoteWriter(llm_service=llm_service, vision_service=vision_service)
    await ai_note_writer.start()
    logger.info("AI Note Writer service started")

    await _register_vision_handler()

    return ai_note_writer, vision_service, llm_service


async def _register_vision_handler() -> None:
    """Register vision description event handler for async processing."""
    if not await nats_client.is_connected():
        logger.warning(
            "NATS not connected - vision description event handler NOT registered. "
            "Vision requests will use synchronous processing only."
        )
        return

    vision_handler = VisionDescriptionHandler()
    vision_handler.register()
    try:
        await event_subscriber.subscribe(EventType.VISION_DESCRIPTION_REQUESTED)
        logger.info("Vision description event handler registered and subscribed")
    except TimeoutError:
        logger.warning(
            "NATS JetStream subscribe timed out - vision description event handler "
            "NOT subscribed. Vision requests will use synchronous processing only."
        )


async def _register_bulk_scan_handlers(llm_service: LLMService | None = None) -> None:
    """Register bulk scan event handlers if NATS is connected.

    Args:
        llm_service: Optional LLM service for embeddings. If not provided, one will be created.
    """
    if await nats_client.is_connected():
        if redis_client.client is None:
            logger.warning(
                "Redis not connected - bulk scan event handlers NOT registered. "
                "Bulk scans will not process message batches."
            )
            return

        if llm_service is None:
            llm_client_manager = LLMClientManager(
                encryption_service=EncryptionService(settings.ENCRYPTION_MASTER_KEY)
            )
            llm_service = LLMService(client_manager=llm_client_manager)

        embedding_service = EmbeddingService(llm_service=llm_service)
        bulk_scan_handler = BulkScanEventHandler(
            embedding_service=embedding_service,
            redis_client=redis_client.client,
            nats_client=nats_client,
            llm_service=llm_service,
        )
        bulk_scan_handler.register()
        try:
            await event_subscriber.subscribe(EventType.BULK_SCAN_MESSAGE_BATCH)
            await event_subscriber.subscribe(EventType.BULK_SCAN_ALL_BATCHES_TRANSMITTED)
            logger.info("Bulk scan event handlers registered and subscribed")
        except TimeoutError:
            logger.warning(
                "NATS JetStream subscribe timed out - bulk scan event handlers "
                "NOT subscribed. Bulk scans will not process message batches."
            )
    else:
        logger.warning(
            "NATS not connected - bulk scan event handlers NOT registered. "
            "Bulk scans will not process message batches."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")

    logger.info("Validating encryption master key...")
    try:
        EncryptionService(settings.ENCRYPTION_MASTER_KEY)
        logger.info("Encryption master key validated successfully")
    except ValueError as e:
        logger.error(f"Encryption master key validation failed: {e}")
        raise RuntimeError(f"Invalid ENCRYPTION_MASTER_KEY: {e}") from e

    # Run startup validation checks
    if not settings.TESTING:  # Skip in test mode
        try:
            await run_startup_checks(skip_checks=settings.SKIP_STARTUP_CHECKS)
        except Exception as e:
            logger.error(f"Startup validation failed: {e}")
            raise RuntimeError("Server startup aborted due to failed validation checks") from e

    await init_db()
    logger.info("Database initialized")

    if not settings.TESTING:
        try:
            dbos = get_dbos()
            dbos.launch()
            logger.info("DBOS initialized successfully", extra={"schema": "dbos"})
        except Exception as e:
            logger.error(f"DBOS initialization failed: {e}")
            raise RuntimeError(f"DBOS initialization failed: {e}") from e

    await redis_client.connect()
    await rate_limiter.connect()
    await interaction_cache.connect()
    logger.info("Redis connections established")

    await _connect_nats()
    app.state.taskiq_broker = await _start_taskiq_broker()

    # Initialize AI Note Writer and Vision services if enabled
    ai_note_writer, vision_service, llm_service = await _init_ai_services()

    await _register_bulk_scan_handlers(llm_service=llm_service)

    # Store in app state for dependency injection
    app.state.ai_note_writer = ai_note_writer
    app.state.vision_service = vision_service
    app.state.health_checker = health_checker
    app.state.distributed_health = distributed_health

    async def check_db() -> Any:
        async with get_session_maker()() as session:
            return await health_checker.check_database(session)

    async def check_redis() -> Any:
        return await health_checker.check_redis(rate_limiter.redis_client)

    async def check_cache() -> Any:
        return await health_checker.check_cache(cache_manager)

    async def check_nats() -> Any:
        try:
            is_connected = await nats_client.is_connected()
            if not is_connected:
                return ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    error="NATS not connected",
                )

            subscriptions_healthy = await nats_client.verify_subscriptions_healthy()
            if not subscriptions_healthy:
                resubscribed = await nats_client.resubscribe_if_needed()
                logger.warning(
                    f"NATS subscriptions were unhealthy, resubscribed {resubscribed} consumers"
                )
                return ComponentHealth(
                    status=HealthStatus.DEGRADED,
                    details={"resubscribed_count": resubscribed},
                )

            return ComponentHealth(status=HealthStatus.HEALTHY)
        except Exception as e:
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                error=f"NATS health check failed: {e}",
            )

    async def check_dbos() -> Any:
        try:
            if settings.TESTING:
                return ComponentHealth(
                    status=HealthStatus.HEALTHY,
                    details={"enabled": False, "reason": "Disabled in test mode"},
                )
            _dbos = get_dbos()
            del _dbos
            return ComponentHealth(
                status=HealthStatus.HEALTHY,
                details={"schema": "dbos", "workflows_enabled": True},
            )
        except Exception as e:
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                error=f"DBOS health check failed: {e}",
            )

    health_checker.register_check("database", check_db)
    health_checker.register_check("redis", check_redis)
    health_checker.register_check("cache", check_cache)
    health_checker.register_check("nats", check_nats)
    health_checker.register_check("dbos", check_dbos)
    logger.info("Health checks registered")

    await distributed_health.start_heartbeat(health_checker.check_all)
    logger.info(f"Distributed health heartbeat started for instance {settings.INSTANCE_ID}")

    yield

    await distributed_health.stop_heartbeat()
    logger.info("Distributed health heartbeat stopped")

    # Stop AI Note Writer service if it was started
    if ai_note_writer:
        await ai_note_writer.stop()
        logger.info("AI Note Writer service stopped")

    # Shutdown taskiq broker
    if hasattr(app.state, "taskiq_broker") and app.state.taskiq_broker:
        try:
            await app.state.taskiq_broker.shutdown()
            reset_broker()
            logger.info("Taskiq broker shutdown complete")
        except Exception as e:
            logger.warning(f"Error shutting down taskiq broker: {e}")

    try:
        await nats_client.disconnect()
        logger.info("NATS connection closed")
    except Exception as e:
        logger.warning(f"Error closing NATS connection: {e}")

    await close_discord_client()
    logger.info("Discord client closed")

    await rate_limiter.disconnect()
    await interaction_cache.disconnect()
    await redis_client.disconnect()
    logger.info("Redis connections closed")

    await close_db()
    logger.info(f"Shutting down {settings.PROJECT_NAME}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
    docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else None,
    redoc_url=f"{settings.API_V1_PREFIX}/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
    separate_input_output_schemas=False,
)

if settings.ENABLE_TRACING and not settings.TESTING:
    app.add_middleware(DiscordContextMiddleware)
    app.add_middleware(AuthenticatedUserContextMiddleware)

app.state.limiter = limiter
app.state.health_checker = health_checker
app.state.distributed_health = distributed_health
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "rate_limit_exceeded", "message": "Too many requests"},
    ),
)

if settings.ENABLE_METRICS:
    app.add_middleware(MetricsMiddleware)

app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
    compresslevel=5,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
    max_age=3600,
)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(TimeoutMiddleware, timeout_seconds=settings.REQUEST_TIMEOUT)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(InternalHeaderValidationMiddleware)

# Auth routes (no prefix)
app.include_router(auth_router)
app.include_router(profile_auth_router)
app.include_router(admin_router)
app.include_router(fusion_weights_router)

# JSON:API v2 routes
app.include_router(jsonapi_notes_router, prefix=settings.API_V2_PREFIX, tags=["notes-jsonapi"])
app.include_router(ratings_jsonapi_router, prefix=settings.API_V2_PREFIX, tags=["ratings-jsonapi"])
app.include_router(
    profiles_jsonapi_router, prefix=settings.API_V2_PREFIX, tags=["profiles-jsonapi"]
)
app.include_router(
    communities_jsonapi_router, prefix=settings.API_V2_PREFIX, tags=["community-servers-jsonapi"]
)
app.include_router(stats_jsonapi_router, prefix=settings.API_V2_PREFIX, tags=["stats-jsonapi"])
app.include_router(
    requests_jsonapi_router, prefix=settings.API_V2_PREFIX, tags=["requests-jsonapi"]
)
app.include_router(scoring_jsonapi_router, prefix=settings.API_V2_PREFIX, tags=["scoring-jsonapi"])
app.include_router(
    monitored_channels_jsonapi_router,
    prefix=settings.API_V2_PREFIX,
    tags=["monitored-channels-jsonapi"],
)
app.include_router(
    note_publisher_jsonapi_router, prefix=settings.API_V2_PREFIX, tags=["note-publisher-jsonapi"]
)
app.include_router(
    previously_seen_jsonapi_router, prefix=settings.API_V2_PREFIX, tags=["previously-seen-jsonapi"]
)
app.include_router(
    embeddings_jsonapi_router, prefix=settings.API_V2_PREFIX, tags=["embeddings-jsonapi"]
)
app.include_router(
    hybrid_searches_jsonapi_router,
    prefix=settings.API_V2_PREFIX,
    tags=["hybrid-searches-jsonapi"],
)
app.include_router(
    bulk_content_scan_jsonapi_router,
    prefix=settings.API_V2_PREFIX,
    tags=["bulk-scans-jsonapi"],
)

# API v1 routes
app.include_router(webhook_router, prefix=settings.API_V1_PREFIX)
app.include_router(config_router, prefix=settings.API_V1_PREFIX)
app.include_router(community_config_router, prefix=settings.API_V1_PREFIX)
app.include_router(community_servers_router, prefix=settings.API_V1_PREFIX)
app.include_router(community_admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(community_clear_router, prefix=settings.API_V2_PREFIX)
app.include_router(llm_config_router, prefix=settings.API_V1_PREFIX)
app.include_router(chunk_router, prefix=settings.API_V1_PREFIX)
app.include_router(fact_check_import_router, prefix=settings.API_V1_PREFIX)
app.include_router(candidates_jsonapi_router, prefix=settings.API_V1_PREFIX)
app.include_router(batch_jobs_router, prefix=settings.API_V1_PREFIX)

# Health routes
app.include_router(health_router)


@app.get("/metrics")
async def metrics() -> Response:
    if not settings.ENABLE_METRICS:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    return Response(content=get_metrics(), media_type="text/plain")


@app.exception_handler(Exception)
async def global_exception_handler(request: Any, exc: Exception) -> JSONResponse:
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "details": str(exc) if settings.DEBUG else None,
        },
    )


def _load_gitignore_patterns() -> list[str]:
    """Load and parse .gitignore files to get reload exclusion patterns.

    Reads both opennotes/.gitignore and opennotes/opennotes-server/.gitignore
    and combines their patterns for use with uvicorn's reload_excludes.

    Converts gitignore patterns to glob patterns suitable for watchfiles.
    """
    patterns = []

    # Get the project root (opennotes-server directory)
    project_root = Path(__file__).parent.parent

    # Paths to .gitignore files
    gitignore_files = [
        project_root.parent / ".gitignore",  # opennotes/.gitignore
        project_root / ".gitignore",  # opennotes-server/.gitignore
    ]

    for gitignore_path in gitignore_files:
        if gitignore_path.exists():
            try:
                with gitignore_path.open() as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        # Skip empty lines and comments
                        if line and not line.startswith("#"):
                            # Remove trailing / and convert to glob pattern
                            pattern = line.rstrip("/")
                            if pattern:
                                # For directory patterns, add /** to match everything inside
                                # For file patterns, keep as-is
                                if not any(c in pattern for c in ["*", "?"]):
                                    # Looks like a directory or filename without wildcards
                                    # Add both the exact match and recursive match
                                    patterns.append(f"**/{pattern}")
                                    patterns.append(f"**/{pattern}/**")
                                else:
                                    # Already has wildcards, use as-is
                                    patterns.append(pattern)
            except Exception as e:
                logger.warning(f"Failed to read {gitignore_path}: {e}")

    return patterns


if __name__ == "__main__":
    import uvicorn

    reload_excludes = _load_gitignore_patterns() if settings.DEBUG else None

    uvicorn.run(
        "src.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
        reload_excludes=reload_excludes,
        log_level=settings.LOG_LEVEL.lower(),
    )
