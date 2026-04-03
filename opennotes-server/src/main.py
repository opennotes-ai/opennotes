import ast
import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from slowapi.errors import RateLimitExceeded

from src.config import get_settings

_otel_settings = get_settings()

if _otel_settings.ENABLE_TRACING and not _otel_settings.TESTING:
    from src.monitoring.observability import setup_observability

    setup_observability(
        service_name=_otel_settings.OTEL_SERVICE_NAME or _otel_settings.PROJECT_NAME,
        service_version=_otel_settings.VERSION,
        environment=_otel_settings.ENVIRONMENT,
        logfire_token=_otel_settings.LOGFIRE_TOKEN,
        trace_content=_otel_settings.LOGFIRE_TRACE_CONTENT,
        sample_rate=_otel_settings.TRACING_SAMPLE_RATE,
        use_gcp_exporters=_otel_settings.USE_GCP_EXPORTERS,
        enable_console_export=_otel_settings.ENABLE_CONSOLE_TRACING,
    )

from src.batch_jobs.router import router as batch_jobs_router
from src.bulk_content_scan.jsonapi_router import router as bulk_content_scan_jsonapi_router
from src.bulk_content_scan.nats_handler import BulkScanEventHandler
from src.cache.cache import cache_manager
from src.cache.redis_client import redis_client
from src.claim_relevance_check.router import router as claim_relevance_check_router
from src.community_config.router import router as community_config_router
from src.community_servers.admin_router import router as community_admin_router
from src.community_servers.clear_router import router as community_clear_router
from src.community_servers.copy_requests_router import router as copy_requests_router
from src.community_servers.router import router as community_servers_router
from src.community_servers.scoring_router import router as community_scoring_router
from src.config import settings
from src.config_router import router as config_router
from src.database import close_db, get_session_maker, init_db
from src.dbos_workflows.config import (
    destroy_dbos,
    get_dbos,
    validate_dbos_connection,
)
from src.dbos_workflows.token_bucket.router import router as token_pool_router
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
from src.middleware.gcp_trace_filter import wrap_app_with_gcp_trace_filter
from src.middleware.internal_auth import InternalHeaderValidationMiddleware
from src.middleware.platform_context import PlatformContextMiddleware
from src.middleware.rate_limiting import limiter
from src.middleware.request_size import RequestSizeLimitMiddleware
from src.middleware.security import SecurityHeadersMiddleware
from src.middleware.timeout import TimeoutMiddleware
from src.middleware.user_context import AuthenticatedUserContextMiddleware
from src.middleware.validation_error_handler import sanitized_validation_exception_handler
from src.moderation_actions.router import router as moderation_actions_jsonapi_router
from src.monitoring import (
    DistributedHealthCoordinator,
    HealthChecker,
    get_logger,
    initialize_instance_metadata,
    parse_log_level_overrides,
    setup_logging,
)
from src.monitoring.health import ComponentHealth, HealthStatus
from src.monitoring.middleware import MetricsMiddleware
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
from src.simulation.orchestrators_jsonapi_router import router as orchestrators_jsonapi_router
from src.simulation.playground_jsonapi_router import router as playground_jsonapi_router
from src.simulation.sim_agents_jsonapi_router import router as sim_agents_jsonapi_router
from src.simulation.sim_channel_messages_jsonapi_router import (
    router as sim_channel_messages_jsonapi_router,
)
from src.simulation.simulations_jsonapi_router import router as simulations_jsonapi_router
from src.startup_migrations import run_startup_migrations
from src.startup_validation import run_startup_checks
from src.tasks.broker import PullBasedJetStreamBroker, get_broker, reset_broker
from src.users.admin_router import router as admin_router
from src.users.communities_jsonapi_router import router as communities_jsonapi_router
from src.users.profile_router import router as profile_auth_router
from src.users.profiles_jsonapi_router import router as profiles_jsonapi_router
from src.users.router import router as auth_router
from src.webhooks.cache import interaction_cache
from src.webhooks.delivery import OutboundWebhookDeliveryService
from src.webhooks.discord_client import close_discord_client
from src.webhooks.rate_limit import rate_limiter
from src.webhooks.router import router as webhook_router

setup_logging(
    log_level=settings.LOG_LEVEL,
    json_format=settings.ENABLE_JSON_LOGGING,
    service_name=settings.PROJECT_NAME,
    module_levels=parse_log_level_overrides(settings.LOG_LEVEL_OVERRIDES),
)
logger = get_logger(__name__)

from src.monitoring.gcp_resource_detector import resolve_effective_instance_id

settings.INSTANCE_ID = resolve_effective_instance_id(settings.INSTANCE_ID)

initialize_instance_metadata(
    instance_id=settings.INSTANCE_ID,
    environment=settings.ENVIRONMENT,
)
logger.info(f"Instance metadata initialized: {settings.INSTANCE_ID}")

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
    logger.info("AI Note Writer service initialized")

    return ai_note_writer, vision_service, llm_service


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


async def _register_outbound_webhook_handlers() -> None:
    if not await nats_client.is_connected():
        logger.warning("NATS not connected - outbound webhook delivery handlers NOT registered.")
        return

    delivery_service = OutboundWebhookDeliveryService(get_session_maker())

    moderation_action_event_types = [
        EventType.MODERATION_ACTION_PROPOSED,
        EventType.MODERATION_ACTION_APPLIED,
        EventType.MODERATION_ACTION_RETRO_REVIEW_STARTED,
        EventType.MODERATION_ACTION_CONFIRMED,
        EventType.MODERATION_ACTION_OVERTURNED,
        EventType.MODERATION_ACTION_DISMISSED,
    ]

    for event_type in moderation_action_event_types:
        captured_type = event_type

        async def _handler(event, _et=captured_type) -> None:
            community_server_id = getattr(event, "community_server_id", None)
            if community_server_id is None:
                logger.warning(
                    f"Outbound webhook handler: missing community_server_id on event "
                    f"event_type={_et.value}"
                )
                return
            await delivery_service.deliver_event(
                _et.value,
                event.event_id,
                event.model_dump(mode="json"),
                community_server_id,
            )

        event_subscriber.register_handler(event_type, _handler)

    try:
        for event_type in moderation_action_event_types:
            await event_subscriber.subscribe(event_type)
        logger.info("Outbound webhook delivery handlers registered and subscribed")
    except TimeoutError:
        logger.warning(
            "NATS JetStream subscribe timed out - outbound webhook delivery handlers "
            "NOT subscribed."
        )


def _validate_encryption_key() -> None:
    logger.info("Validating encryption master key...")
    try:
        EncryptionService(settings.ENCRYPTION_MASTER_KEY)
        logger.info("Encryption master key validated successfully")
    except ValueError as e:
        logger.error(f"Encryption master key validation failed: {e}")
        raise RuntimeError(f"Invalid ENCRYPTION_MASTER_KEY: {e}") from e


async def _run_startup_validation() -> None:
    if settings.TESTING:
        return
    try:
        await run_startup_checks(skip_checks=settings.SKIP_STARTUP_CHECKS)
    except Exception as e:
        logger.error(f"Startup validation failed: {e}")
        raise RuntimeError("Server startup aborted due to failed validation checks") from e


def _is_dbos_workflow_decorator(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "workflow"
        and isinstance(target.value, ast.Name)
        and target.value.id == "DBOS"
    )


@dataclass(frozen=True)
class DiscoveredDBOSWorkflowModule:
    module_path: str
    module_file: Path
    workflow_names: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveredDBOSWorkflowModules:
    discovered_modules: list[DiscoveredDBOSWorkflowModule]
    errors: list[str]


def _build_workflow_registration_error(errors: list[str]) -> RuntimeError:
    return RuntimeError(
        "Workflow registration incomplete:\n" + "\n".join(f"- {error}" for error in errors)
    )


def _discover_dbos_workflow_modules() -> DiscoveredDBOSWorkflowModules:
    src_root = Path(__file__).resolve().parent
    package_roots = (
        src_root / "dbos_workflows",
        src_root / "simulation" / "workflows",
    )
    discovered: list[DiscoveredDBOSWorkflowModule] = []
    errors: list[str] = []

    for package_root in package_roots:
        for module_file in sorted(package_root.rglob("*.py")):
            if module_file.name == "__init__.py":
                continue

            module_path = ".".join(module_file.relative_to(src_root.parent).with_suffix("").parts)

            try:
                tree = ast.parse(module_file.read_text(encoding="utf-8"))
            except Exception as e:
                errors.append(
                    f"Failed to inspect workflow module {module_path} "
                    f"({module_file}): {type(e).__name__}: {e}"
                )
                continue

            workflow_names = tuple(
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and any(_is_dbos_workflow_decorator(decorator) for decorator in node.decorator_list)
            )
            if not workflow_names:
                continue

            discovered.append(
                DiscoveredDBOSWorkflowModule(
                    module_path=module_path,
                    module_file=module_file,
                    workflow_names=workflow_names,
                )
            )

    return DiscoveredDBOSWorkflowModules(discovered_modules=discovered, errors=errors)


def _register_dbos_workflows() -> list[str]:
    """Import DBOS workflow modules and return their registered workflow names."""
    import importlib

    discovery = _discover_dbos_workflow_modules()
    registered: set[str] = set()
    errors = list(discovery.errors)

    for discovered_module in discovery.discovered_modules:
        try:
            workflow_module = importlib.import_module(discovered_module.module_path)
        except Exception as e:
            errors.append(
                f"Failed to import workflow module {discovered_module.module_path} "
                f"({discovered_module.module_file}): {type(e).__name__}: {e}"
            )
            continue

        for workflow_name in discovered_module.workflow_names:
            workflow = getattr(workflow_module, workflow_name, None)
            if callable(workflow):
                registered.add(workflow.__qualname__)
            else:
                errors.append(
                    f"Workflow {workflow_name} missing or not callable in module "
                    f"{discovered_module.module_path} ({discovered_module.module_file})"
                )

    if errors:
        raise _build_workflow_registration_error(errors)

    return sorted(registered)


async def _init_dbos(is_dbos_worker: bool) -> None:
    if settings.TESTING:
        return

    if settings.DBOS_CONDUCTOR_KEY:
        logger.info("DBOS Conductor enabled (API key configured)")
    else:
        logger.info("DBOS Conductor disabled (no API key)")

    if is_dbos_worker:
        try:
            registered_workflows = _register_dbos_workflows()

            logger.info(
                "DBOS workflow modules loaded",
                extra={"registered_workflows": registered_workflows},
            )

            dbos = get_dbos()
            dbos.launch()
            await asyncio.to_thread(validate_dbos_connection)

            from src.dbos_workflows.token_bucket.config import (
                ensure_pool_exists_async,
                register_worker_async,
                start_worker_heartbeat,
            )

            await ensure_pool_exists_async(capacity=settings.TOKEN_POOL_CAPACITY)

            try:
                await register_worker_async(capacity=settings.TOKEN_POOL_CAPACITY)
                await start_worker_heartbeat()
            except Exception as e:
                logger.warning(f"Worker registration failed, using static capacity: {e}")

            logger.info(
                "DBOS worker mode - queue polling enabled and validated",
                extra={"schema": "dbos", "registered_workflows": registered_workflows},
            )
        except Exception as e:
            logger.error(f"DBOS initialization failed: {e}")
            raise RuntimeError(f"DBOS initialization failed: {e}") from e

        try:
            from src.bulk_content_scan.flashpoint_service import get_flashpoint_service

            fp_service = get_flashpoint_service()
            await asyncio.to_thread(fp_service.warm_up)
            logger.info("Flashpoint detector loaded at startup")
        except Exception as e:
            logger.error(f"Flashpoint detector warm-up failed: {e}", exc_info=True)
    else:
        try:
            from dbos import DBOS

            registered_workflows = _register_dbos_workflows()
            dbos = get_dbos()
            DBOS.listen_queues([])
            dbos.launch()
            await asyncio.to_thread(validate_dbos_connection)
            logger.info(
                "DBOS server mode - full DBOS with empty queue listeners",
                extra={"registered_workflows": registered_workflows},
            )
        except Exception as e:
            logger.error(f"DBOS server-mode initialization failed: {e}")
            raise RuntimeError(f"DBOS server-mode initialization failed: {e}") from e


async def _init_worker_services(
    app: FastAPI,
    is_dbos_worker: bool,
) -> tuple[AINoteWriter | None, VisionService | None]:
    ai_note_writer = None
    vision_service = None
    if is_dbos_worker:
        logger.info("DBOS worker mode - skipping TaskIQ, AI services, and event handlers")
        app.state.taskiq_broker = None
    else:
        app.state.taskiq_broker = await _start_taskiq_broker()
        ai_note_writer, vision_service, llm_service = await _init_ai_services()
        await _register_bulk_scan_handlers(llm_service=llm_service)
        await _register_outbound_webhook_handlers()
    return ai_note_writer, vision_service


def _register_health_checks(is_dbos_worker: bool) -> None:
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
            if is_dbos_worker:
                _dbos = get_dbos()
                del _dbos
                return ComponentHealth(
                    status=HealthStatus.HEALTHY,
                    details={"mode": "worker", "schema": "dbos", "workflows_enabled": True},
                )
            _dbos = get_dbos()
            del _dbos
            return ComponentHealth(
                status=HealthStatus.HEALTHY,
                details={"mode": "server", "schema": "dbos", "full_dbos": True},
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


async def _shutdown_services(app: FastAPI, is_dbos_worker: bool) -> None:
    if is_dbos_worker:
        try:
            from src.dbos_workflows.token_bucket.config import (
                deregister_worker_async,
                stop_worker_heartbeat,
            )

            await stop_worker_heartbeat()
            await deregister_worker_async()
            logger.info("Worker heartbeat stopped and deregistered")
        except Exception as e:
            logger.warning(f"Error during worker deregistration: {e}")

    await distributed_health.stop_heartbeat()
    logger.info("Distributed health heartbeat stopped")

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

    _destroy_dbos(is_dbos_worker)

    from src.database import dispose_background_engines

    dispose_background_engines()
    logger.info("Background engine(s) disposed")

    from src.utils.async_compat import shutdown as shutdown_bg_loop

    await asyncio.to_thread(shutdown_bg_loop)
    logger.info("Background event loop stopped")

    await close_db()
    logger.info(f"Shutting down {settings.PROJECT_NAME}")


def _destroy_dbos(is_dbos_worker: bool) -> None:
    try:
        destroy_dbos()
        logger.info("DBOS destroyed")
    except Exception as e:
        logger.warning(f"Error destroying DBOS: {e}")


async def _startup_background(app: FastAPI, is_dbos_worker: bool) -> None:
    """Run full init chain in background after lifespan yields."""
    try:
        if not settings.TESTING:
            await run_startup_migrations(settings.SERVER_MODE)

        await init_db()
        logger.info("Database initialized")

        await _init_dbos(is_dbos_worker)

        await redis_client.connect()
        await rate_limiter.connect()
        await interaction_cache.connect()
        logger.info("Redis connections established")

        await _connect_nats()

        ai_note_writer, vision_service = await _init_worker_services(app, is_dbos_worker)

        app.state.ai_note_writer = ai_note_writer
        app.state.vision_service = vision_service

        _register_health_checks(is_dbos_worker)

        await distributed_health.start_heartbeat(health_checker.check_all)
        logger.info(f"Distributed health heartbeat started for instance {settings.INSTANCE_ID}")

        app.state.startup_complete = True
        logger.info("Background initialization complete — server ready")
    except asyncio.CancelledError:
        logger.warning("Background init cancelled (shutdown during startup)")
        raise
    except Exception as e:
        logger.critical(f"Background initialization failed: {e}", exc_info=True)
        app.state.startup_failed = True
        os._exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"Server mode: {settings.SERVER_MODE}")

    is_dbos_worker = settings.SERVER_MODE == "dbos_worker"

    app.state.startup_complete = False
    app.state.startup_failed = False
    app.state.health_checker = health_checker
    app.state.distributed_health = distributed_health

    _validate_encryption_key()
    await _run_startup_validation()

    init_task = asyncio.create_task(
        _startup_background(app, is_dbos_worker),
        name="startup-init",
    )

    yield

    init_task.cancel()
    try:
        await init_task
    except asyncio.CancelledError:
        pass

    if app.state.startup_complete:
        await _shutdown_services(app, is_dbos_worker)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
    docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else None,
    redoc_url=f"{settings.API_V1_PREFIX}/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
    separate_input_output_schemas=False,
    default_response_class=ORJSONResponse,
)

if settings.ENABLE_TRACING and not settings.TESTING:
    app.add_middleware(PlatformContextMiddleware)
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

app.add_exception_handler(RequestValidationError, sanitized_validation_exception_handler)

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

from src.middleware.startup_gate import StartupGateMiddleware

app.add_middleware(StartupGateMiddleware)

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
    claim_relevance_check_router,
    prefix=settings.API_V2_PREFIX,
    tags=["claim-relevance-checks-jsonapi"],
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
app.include_router(
    sim_agents_jsonapi_router,
    prefix=settings.API_V2_PREFIX,
    tags=["sim-agents-jsonapi"],
)
app.include_router(
    orchestrators_jsonapi_router,
    prefix=settings.API_V2_PREFIX,
    tags=["simulation-orchestrators-jsonapi"],
)
app.include_router(
    playground_jsonapi_router,
    prefix=settings.API_V2_PREFIX,
    tags=["playground-jsonapi"],
)
app.include_router(
    sim_channel_messages_jsonapi_router,
    prefix=settings.API_V2_PREFIX,
    tags=["sim-channel-messages-jsonapi"],
)
app.include_router(
    moderation_actions_jsonapi_router,
    prefix=settings.API_V2_PREFIX,
    tags=["moderation-actions-jsonapi"],
)

# API v1 routes
app.include_router(webhook_router, prefix=settings.API_V1_PREFIX)
app.include_router(config_router, prefix=settings.API_V1_PREFIX)
app.include_router(community_config_router, prefix=settings.API_V1_PREFIX)
app.include_router(community_servers_router, prefix=settings.API_V1_PREFIX)
app.include_router(community_admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(community_clear_router, prefix=settings.API_V2_PREFIX)
app.include_router(community_scoring_router, prefix=settings.API_V2_PREFIX)
app.include_router(copy_requests_router, prefix=settings.API_V2_PREFIX)
app.include_router(llm_config_router, prefix=settings.API_V1_PREFIX)
app.include_router(chunk_router, prefix=settings.API_V1_PREFIX)
app.include_router(fact_check_import_router, prefix=settings.API_V1_PREFIX)
app.include_router(candidates_jsonapi_router, prefix=settings.API_V1_PREFIX)
app.include_router(batch_jobs_router, prefix=settings.API_V1_PREFIX)
app.include_router(token_pool_router, prefix=settings.API_V1_PREFIX)
app.include_router(
    simulations_jsonapi_router,
    prefix=settings.API_V2_PREFIX,
    tags=["simulations-jsonapi"],
)

# Health routes
app.include_router(health_router)

# Wrap app with GCP trace header filter at ASGI level (outermost layer).
# This strips GCP-injected traceparent headers before OpenTelemetry can extract them,
# ensuring each HTTP request starts a new independent trace.
# Must be applied AFTER all middleware/routes are configured.
asgi_app = wrap_app_with_gcp_trace_filter(app)


@app.exception_handler(Exception)
async def global_exception_handler(request: Any, exc: Exception) -> JSONResponse:
    import logging

    try:
        from src.monitoring import record_span_error

        record_span_error(exc)

        http_context = {
            "method": request.method,
            "url": str(request.url),
            "userAgent": request.headers.get("user-agent", ""),
            "remoteIp": request.client.host if request.client else None,
            "referrer": request.headers.get("referer", ""),
        }

        logger.exception(
            f"Unhandled exception: {exc}",
            extra={"httpRequest": http_context},
        )
    except Exception:
        logging.getLogger(__name__).error(
            "Unhandled exception (error handler fallback): %s", exc, exc_info=True
        )

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
        "src.main:asgi_app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
        reload_excludes=reload_excludes,
        log_level=settings.LOG_LEVEL.lower(),
    )
