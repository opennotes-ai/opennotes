import asyncio
import logging
import os
import shutil
import signal
import socket
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)

os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["WANDB_MODE"] = "disabled"
os.environ["WANDB_SILENT"] = "true"

if "JWT_SECRET_KEY" not in os.environ:
    os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-for-testing-only-32-chars-min"

if "CREDENTIALS_ENCRYPTION_KEY" not in os.environ:
    os.environ["CREDENTIALS_ENCRYPTION_KEY"] = "fvcKFp4tKdCkUfhZ0lm9chCwL-ZQfjHtlm6tW2NYWlk="

if "ENCRYPTION_MASTER_KEY" not in os.environ:
    os.environ["ENCRYPTION_MASTER_KEY"] = "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE="

# DATABASE_URL configuration for tests
# CRITICAL: Tests ALWAYS use isolated testcontainers for complete isolation.
#
# Test Isolation Mode:
#   ISOLATED (ONLY MODE): Testcontainers-python with dedicated containers
#      - Spins up dedicated postgres/redis/nats containers on random ports
#      - Complete isolation from dev environment
#      - Automatic cleanup after tests
#      - RECOMMENDED for CI/CD and clean test runs
#      - Uses docker-compose.yml + docker-compose.test.yml
#      - Supports concurrent test runs without conflicts
#      - With pytest-xdist: Each worker gets its own database
#      - IGNORES pre-existing DATABASE_URL to prevent connection errors
#
# Environment Variables:
#   POSTGRES_IMAGE         - Override postgres image (default: pgvector/pgvector:pg18)
#   REDIS_IMAGE            - Override redis image (default: redis:7-alpine)
#   NATS_IMAGE             - Override nats image (default: nats:2.10-alpine)
#   PYTEST_XDIST_WORKER    - Set by pytest-xdist (e.g., "gw0", "gw1") for worker isolation
#
# DEFAULT BEHAVIOR: Isolated testcontainers mode (ALWAYS)
# This ensures complete test isolation and is recommended for CI/CD.
# Any pre-existing DATABASE_URL in the environment is OVERRIDDEN by testcontainers.

print("i Using isolated testcontainers mode")
# Service URLs will be set by test_services fixture below
# IMPORTANT: Do NOT import src.database or src.main yet - they'll be imported after test_services fixture configures the database URLs

# Note: For testcontainers mode, app and Base are imported lazily in the fixtures
# that use them to ensure DATABASE_URL is set before the modules are imported


def pytest_runtest_setup(item):
    """
    Hook that runs before each test to reset database state.

    IMPORTANT: This hook runs VERY EARLY, before fixtures are set up.
    Do NOT clear the engine here as it interferes with setup_database's cleanup.

    The engine reset is handled by pytest_runtest_teardown which runs AFTER
    all fixtures (including setup_database) have completed their cleanup.
    """


def pytest_runtest_teardown(item):
    """
    Hook that runs AFTER each test and after all fixtures have been torn down.

    With asyncio_default_fixture_loop_scope=function, each test gets a fresh
    event loop. The async engine is bound to the loop it was created in.

    After setup_database fixture has cleaned up (await close_db() + dropped test DB),
    we reset the module variables so the next test creates fresh ones bound to its
    new event loop.
    """
    if "unit" in item.keywords:
        return

    try:
        import asyncio

        try:
            # Check if we're still in the test's event loop
            asyncio.get_running_loop()
            # If we are, try to properly close the database engine
            # This prevents connection pool errors in the next test
        except RuntimeError:
            # Event loop is already closed, just reset the variables
            pass

        from src.database import _reset_database_for_test_loop

        _reset_database_for_test_loop()
    except (ImportError, RuntimeError):
        pass


def pytest_configure(config: "pytest.Config") -> None:
    """
    Configuration hook that runs once per session in the MASTER process.

    With pytest-xdist, this allows us to perform setup that should only happen once.
    """


def pytest_collection_modifyitems(config, items):
    """
    Deselect tests that must run serially when xdist is active.

    When xdist is enabled (parallel execution with -n > 0), deselect:
    - integration_messaging: use singleton redis_client/nats_client
    - serial: resource-heavy tests that crash xdist workers (e.g., ML scorer tests)
    - heavy: OOM-risk tests (e.g., matrix factorization) that live in tests/heavy/

    These tests run in separate serial CI steps with -n 0.
    """
    xdist_numprocesses = config.getoption("numprocesses", default=None)

    if xdist_numprocesses and xdist_numprocesses != "0":
        items_to_remove = []
        for item in items:
            if (
                "integration_messaging" in item.keywords
                or "serial" in item.keywords
                or "heavy" in item.keywords
            ):
                items_to_remove.append(item)

        for item in items_to_remove:
            items.remove(item)


def cleanup_old_orphaned_containers():
    """
    Remove orphaned containers on test startup.

    This function is called before starting new test containers to clean up
    any containers left behind from interrupted test runs (older than 1 hour).
    """
    try:
        import docker

        client = docker.from_env()

        filters = {"label": "opennotes.test.session_id", "status": "running"}
        containers = client.containers.list(filters=filters)

        if not containers:
            return

        from datetime import timedelta

        orphaned_removed = 0
        for container in containers:
            labels = container.labels or {}
            timestamp_str = labels.get("opennotes.test.timestamp")

            if not timestamp_str:
                continue

            try:
                container_start_time = datetime.fromisoformat(timestamp_str)
                container_age = datetime.now(UTC) - container_start_time

                if container_age > timedelta(hours=1):
                    try:
                        print(f"🧹 Removing orphaned container: {container.name}")
                        container.stop(timeout=10)
                        container.remove()
                        orphaned_removed += 1
                    except Exception as e:
                        print(f"⚠️  Could not remove container {container.name}: {e}")
            except (ValueError, TypeError):
                pass

        if orphaned_removed > 0:
            print(f"✓ Cleaned up {orphaned_removed} orphaned container(s)")

    except Exception as e:
        print(f"⚠️  Could not cleanup old containers: {e}")


def test_sqlalchemy_relationships():
    """
    Validate all SQLAlchemy relationships can be resolved.

    This test ensures that all string-based relationship references in models
    can be resolved by SQLAlchemy at runtime. It catches issues where:
    - Models are imported only in TYPE_CHECKING blocks (not available at runtime)
    - Circular imports prevent proper model registration
    - Relationship back_populates references don't match

    This test runs early to fail fast on relationship configuration issues
    that would otherwise cause cryptic errors during test execution.

    CRITICAL: Import order matters for circular dependency resolution.
    Import dependent models BEFORE their parent models to avoid mapper errors.
    """
    try:
        # Import all models first to ensure they're registered
        # Import in dependency order to avoid circular import issues

        # Core models
        # Trigger mapper configuration - this will fail if relationships are broken
        from sqlalchemy.orm import configure_mappers

        from src.llm_config.models import (  # noqa: F401
            CommunityServer,
            CommunityServerLLMConfig,
        )
        from src.notes.models import Note  # noqa: F401

        # Note-related models (NotePublisherPost must be before Note due to relationship)
        from src.notes.note_publisher_models import (  # noqa: F401
            NotePublisherConfig,
            NotePublisherPost,
        )
        from src.users.models import User  # noqa: F401
        from src.users.profile_models import (  # noqa: F401
            CommunityMember,
            UserIdentity,
            UserProfile,
        )

        configure_mappers()

    except Exception as e:
        pytest.fail(
            f"SQLAlchemy relationship validation failed: {e}\n\n"
            "This usually means a model references another model in a relationship "
            "but the referenced model is only imported in a TYPE_CHECKING block. "
            "SQLAlchemy needs the model available at runtime to resolve string-based "
            "relationship references.\n\n"
            f"Error details: {type(e).__name__}: {e}"
        )


def _verify_external_services(
    database_url: str | None, redis_url: str | None, nats_url: str | None
) -> bool:
    """
    Verify that external services are reachable.

    Returns True if all services are accessible, False otherwise.
    This allows the test fixture to fall back to testcontainers if external services
    are configured but not actually running.
    """
    import socket
    from urllib.parse import urlparse

    def check_tcp_connection(url: str | None, service_name: str) -> bool:
        if not url:
            return False
        try:
            parsed = urlparse(url)
            host = parsed.hostname or "localhost"
            port = parsed.port
            if not port:
                return False

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                print(f"   ✅ {service_name} reachable at {host}:{port}")
                return True
            print(f"   ❌ {service_name} not reachable at {host}:{port}")
            return False
        except Exception as e:
            print(f"   ❌ {service_name} connection check failed: {e}")
            return False

    print("🔍 Checking external services availability...")

    # Check PostgreSQL (extract port from asyncpg URL)
    pg_url = database_url.replace("+asyncpg", "") if database_url else None
    pg_ok = check_tcp_connection(pg_url, "PostgreSQL")

    # Check Redis
    redis_ok = check_tcp_connection(redis_url, "Redis")

    # Check NATS
    nats_ok = check_tcp_connection(nats_url, "NATS")

    return pg_ok and redis_ok and nats_ok


@pytest.fixture(scope="session")
def test_services():
    """
    Spin up test services using either testcontainers or local environment.

    This fixture provides a flexible approach to test service setup:

    1. If external services are pre-provisioned (CI or local): Use those
       - Checks for DATABASE_URL, REDIS_URL, NATS_URL environment variables
       - Verifies services are reachable before using them
       - Skips testcontainers entirely (faster startup)
       - Set SKIP_TESTCONTAINERS=1 to force this mode

    2. If Docker is available and no external services: Use testcontainers
       - Spins up postgres, redis, nats in isolated containers
       - Sets DATABASE_URL, REDIS_URL, NATS_URL
       - Automatic cleanup on test completion

    3. If neither available: Fail with helpful error message

    This allows tests to run in any environment:
    - CI/CD with GitHub Actions services (external, pre-provisioned)
    - Local development with OpenTofu services (external, pre-provisioned)
    - Isolated testing with testcontainers (when no external services)
    """

    import time

    # Check for pre-provisioned external services FIRST
    # This handles CI (GitHub Actions services) and local development (OpenTofu)
    skip_testcontainers = os.environ.get("SKIP_TESTCONTAINERS", "").lower() in ("1", "true", "yes")
    local_database_url = os.environ.get("DATABASE_URL")
    local_redis_url = os.environ.get("REDIS_URL")
    local_nats_url = os.environ.get("NATS_URL")

    # If external services are configured, try to use them
    use_external = skip_testcontainers or (
        local_database_url and local_redis_url and local_nats_url
    )
    if use_external and _verify_external_services(
        local_database_url, local_redis_url, local_nats_url
    ):
        print("🟢 Using pre-provisioned external services")
        print(f"   DATABASE_URL: {local_database_url}")
        print(f"   REDIS_URL: {local_redis_url}")
        print(f"   NATS_URL: {local_nats_url}")
        print("")

        # Import and configure app modules with external service URLs
        import importlib
        import sys

        from src.config import get_settings

        get_settings.cache_clear()

        from src import config

        importlib.reload(config)

        from src import database

        importlib.reload(database)

        from slowapi import Limiter as SlowAPILimiter

        from src.database import Base
        from src.main import app

        def disabled_limit_decorator(_self, _limit_string: str):
            def decorator(func):
                return func

            return decorator

        SlowAPILimiter.limit = disabled_limit_decorator

        current_module = sys.modules[__name__]
        current_module.Base = Base
        current_module.app = app

        yield None
        return

    # Check if Docker is available
    docker_available = shutil.which("docker") is not None

    if not docker_available:
        # Check if local services are already configured
        if local_database_url:
            print("🟢 Using existing services from local environment")
            print(f"   DATABASE_URL: {local_database_url}")
            print(
                f"   REDIS_URL: {os.environ.get('REDIS_URL', '(not set - using testcontainers default)')}"
            )
            print(
                f"   NATS_URL: {os.environ.get('NATS_URL', '(not set - using testcontainers default)')}"
            )
            print("")
            print("   Note: Ensure local services are running before executing tests:")
            print("   $ mise run tofu:local:apply")
            print("")

            # Skip testcontainers setup, use existing environment
            yield None
            return
        else:
            # Neither Docker nor local services available
            raise RuntimeError(
                "\n" + "=" * 70 + "\n"
                "ERROR: No test service provider available\n"
                "=" * 70 + "\n"
                "\nCannot run tests without Docker or local services.\n"
                "\nYou have two options:\n"
                "\n1. DOCKER (Recommended for CI/CD, isolated testing):\n"
                "   - Install Docker Desktop from https://www.docker.com/products/docker-desktop\n"
                "   - Start Docker daemon\n"
                "   - Tests will automatically use testcontainers\n"
                "\n2. LOCAL SERVICES (Recommended for local development):\n"
                "   - Deploy local infrastructure: mise run tofu:local:apply\n"
                "   - Get connection details: mise run tofu:local:output\n"
                "   - Export environment variables:\n"
                "     export DATABASE_URL='postgresql+asyncpg://opennotes:testpass@localhost:5432/opennotes'\n"
                "     export REDIS_URL='redis://localhost:6379/0'\n"
                "     export NATS_URL='nats://localhost:4222'\n"
                "   - Run tests with these variables set\n"
                "\nFor more information, see: TEST_INFRASTRUCTURE_ANALYSIS.md\n" + "=" * 70
            )

    # Docker is available - use testcontainers (existing implementation)
    from testcontainers.compose import DockerCompose
    from testcontainers.core.docker_client import DockerClient

    class DockerComposeWithProperCleanup(DockerCompose):
        def __exit__(self, exc_type, exc_val, exc_tb):
            try:
                docker_client = DockerClient()
                compose_containers = self.get_containers()

                for compose_container in compose_containers:
                    try:
                        container_id = compose_container.id
                        docker_container = docker_client.client.containers.get(container_id)
                        print(f"🛑 Explicitly stopping container: {docker_container.name}")
                        docker_container.stop(timeout=10)
                    except Exception as e:
                        print(f"⚠️  Warning: Failed to stop container {compose_container.name}: {e}")
            except Exception as e:
                print(f"⚠️  Warning: Failed during explicit container cleanup: {e}")

            return super().__exit__(exc_type, exc_val, exc_tb)

    cleanup_old_orphaned_containers()

    from pathlib import Path

    compose_dir = str(Path(__file__).resolve().parent.parent.parent)

    project_id = str(uuid.uuid4())[:8]
    os.environ["COMPOSE_PROJECT_NAME"] = f"test-{project_id}"

    session_id = f"test-{project_id}"
    os.environ["TEST_SESSION_ID"] = session_id

    compose_env = {
        "POSTGRES_PASSWORD": os.environ.get("POSTGRES_PASSWORD", "testpass"),
        "POSTGRES_IMAGE": os.environ.get(
            "POSTGRES_IMAGE", "opennotes/postgres:18-pgvector-pgroonga"
        ),
        "REDIS_IMAGE": os.environ.get("REDIS_IMAGE", "redis:7-alpine"),
        "NATS_IMAGE": os.environ.get("NATS_IMAGE", "nats:2.10-alpine"),
        "DISCORD_TOKEN": "dummy-token-for-parsing",
        "DISCORD_CLIENT_ID": "dummy-client-id",
        "JWT_SECRET_KEY": "dummy-jwt-secret-key-for-compose-parsing-only",
        "COMPOSE_PROJECT_NAME": f"test-{project_id}",
        "PYTEST_PID": str(os.getpid()),
        "TEST_START_TIME": datetime.now(UTC).isoformat(),
        "HOSTNAME": socket.gethostname(),
        "USER": os.getenv("USER", "unknown"),
    }

    print("🐳 Starting test services with testcontainers-python...")
    print(f"📂 Compose directory: {compose_dir}")
    print(f"🔖 Project name: test-{project_id}")

    # Set environment variables for docker-compose before starting
    # These are passed to docker-compose via environment
    for key, value in compose_env.items():
        os.environ[key] = value

    # Start docker-compose with base + test override
    # Only start infrastructure services (not application services)
    with DockerComposeWithProperCleanup(
        context=compose_dir,
        compose_file_name=["docker-compose.yml", "docker-compose.test.yml"],
        pull=False,  # Don't pull images (assume they exist)
        build=False,  # Don't build images (assume they exist)
        wait=True,  # Wait for services to be healthy
        services=["postgres", "redis", "nats"],  # Only start infrastructure
        env_file=None,
    ) as compose:
        # Wait for services to be healthy
        print("⏳ Waiting for services to be healthy...")
        max_wait = 60  # seconds
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                # Check if postgres is ready
                postgres_host = compose.get_service_host("postgres", 5432)
                postgres_port = compose.get_service_port("postgres", 5432)

                # Check if redis is ready - use docker SDK directly for dynamic port
                import docker

                docker_client = docker.from_env()
                project_name = f"test-{project_id}"

                # Get Redis container and extract port mapping
                try:
                    redis_container = docker_client.containers.get(f"{project_name}-redis-1")
                    redis_port_mapping = redis_container.ports.get("6379/tcp")
                    if redis_port_mapping and len(redis_port_mapping) > 0:
                        redis_port = int(redis_port_mapping[0]["HostPort"])
                    else:
                        print(
                            f"   Warning: Redis port mapping not found, ports: {redis_container.ports}"
                        )
                        redis_port = compose.get_service_port("redis", 6379)
                except Exception as redis_error:
                    print(f"   Warning: Failed to get Redis port via docker SDK: {redis_error}")
                    redis_port = compose.get_service_port("redis", 6379)

                # Get NATS container and extract port mapping
                try:
                    nats_container = docker_client.containers.get(f"{project_name}-nats-1")
                    nats_port_mapping = nats_container.ports.get("4222/tcp")
                    if nats_port_mapping and len(nats_port_mapping) > 0:
                        nats_port = int(nats_port_mapping[0]["HostPort"])
                    else:
                        print(
                            f"   Warning: NATS port mapping not found, ports: {nats_container.ports}"
                        )
                        nats_port = compose.get_service_port("nats", 4222)
                except Exception as nats_error:
                    print(f"   Warning: Failed to get NATS port via docker SDK: {nats_error}")
                    nats_port = compose.get_service_port("nats", 4222)

                # All services are up, configure environment variables
                # Use localhost instead of 0.0.0.0 for connection URLs
                postgres_password = compose_env["POSTGRES_PASSWORD"]
                host = "localhost" if postgres_host == "0.0.0.0" else postgres_host

                os.environ["DATABASE_URL"] = (
                    f"postgresql+asyncpg://opennotes:{postgres_password}@{host}:{postgres_port}/opennotes"
                )
                os.environ["REDIS_URL"] = f"redis://{host}:{redis_port}/0"
                os.environ["NATS_URL"] = f"nats://{host}:{nats_port}"

                # Clear the cached settings so get_settings() will create a new Settings instance
                # with the updated environment variables
                import importlib
                import sys

                from src.config import get_settings

                get_settings.cache_clear()

                # Reload the config module so it picks up the new DATABASE_URL
                from src import config

                importlib.reload(config)

                # Reload the database module so it uses the new settings
                from src import database

                importlib.reload(database)

                # Now get references to the reloaded modules

                from slowapi import Limiter as SlowAPILimiter

                # Now import Base and app which depend on the correct DATABASE_URL
                from src.database import Base
                from src.main import app

                # Patch slowapi rate limiter

                def disabled_limit_decorator(_self, _limit_string: str):
                    """Rate limit decorator that does nothing - for test environment"""

                    def decorator(func):
                        return func

                    return decorator

                SlowAPILimiter.limit = disabled_limit_decorator

                # Set the global module variables for use by test fixtures

                current_module = sys.modules[__name__]
                current_module.Base = Base
                current_module.app = app

                print(f"✅ PostgreSQL: {host}:{postgres_port}")
                print(f"✅ Redis: {host}:{redis_port}")
                print(f"✅ NATS: {host}:{nats_port}")
                break

            except Exception as e:
                if time.time() - start_time >= max_wait:
                    print(f"❌ Services failed to start: {e}")
                    raise
                time.sleep(1)

        yield compose

        print("🧹 Cleaning up test services...")

        # Explicit cleanup to remove containers, networks, and volumes
        # The DockerCompose context manager stops containers but may not remove all resources
        try:
            import subprocess

            project_name = f"test-{project_id}"
            compose_files = [
                "-f",
                str(Path(compose_dir) / "docker-compose.yml"),
                "-f",
                str(Path(compose_dir) / "docker-compose.test.yml"),
            ]

            # Run docker compose down with volume removal and orphan cleanup
            # -v removes named volumes declared in compose file
            # --remove-orphans removes containers for services not defined in compose file
            cmd = [
                "docker",
                "compose",
                "-p",
                project_name,
                *compose_files,
                "down",
                "-v",  # Remove volumes
                "--remove-orphans",
                "--timeout",
                "10",
            ]

            print(f"   Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            if result.returncode == 0:
                print("   ✅ Successfully cleaned up containers, networks, and volumes")
            else:
                print(f"   ⚠️  Cleanup warning: {result.stderr}")

        except Exception as e:
            print(f"   ⚠️  Could not cleanup test resources: {e}")


@pytest.fixture(scope="session", autouse=True)
def cleanup_manager(request):
    """
    Register cleanup handlers for test containers on exit and interrupt.

    This fixture ensures that test containers are properly cleaned up even when:
    - Tests complete normally
    - Tests are interrupted (Ctrl+C)
    - Pytest is terminated (SIGTERM)
    - Tests crash unexpectedly

    Cleanup is handled through:
    1. Signal handlers (SIGINT, SIGTERM)
    2. Explicit cleanup on normal fixture exit
    3. State tracking in ~/.opennotes/test_containers.json

    The cleanup script identifies orphaned containers by:
    - Process check: PID no longer exists or is not a pytest process
    - Age threshold: Container is older than 1 hour
    - Grace period: Containers younger than 10 minutes are never removed
    """
    session_id = os.environ.get("TEST_SESSION_ID")

    def cleanup_on_signal(_signum, _frame):
        if session_id:
            try:
                import subprocess

                subprocess.run(
                    [
                        "python",
                        "opennotes-server/scripts/cleanup_test_containers.py",
                        "--update-state",
                        "--session-id",
                        session_id,
                    ],
                    check=False,
                    cwd="/Users/mike/code/opennotes-ai/multiverse/opennotes",
                    capture_output=True,
                    timeout=5,
                )
            except Exception as e:
                print(f"⚠️  Could not update cleanup state: {e}")
        raise KeyboardInterrupt("Test interrupted")

    if session_id:
        signal.signal(signal.SIGINT, cleanup_on_signal)
        signal.signal(signal.SIGTERM, cleanup_on_signal)

    yield

    if session_id:
        try:
            import subprocess

            subprocess.run(
                [
                    "python",
                    "opennotes-server/scripts/cleanup_test_containers.py",
                    "--update-state",
                    "--session-id",
                    session_id,
                ],
                check=False,
                cwd="/Users/mike/code/opennotes-ai/multiverse/opennotes",
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass


@pytest.fixture(scope="session")
def template_database(test_services):
    """
    Create a template database with full schema once per test session.

    This template is used as a fast clone source for each worker's test database.
    Using templates is much faster than running migrations for each test.

    IMPORTANT: Template is NOT marked as datistemplate=TRUE to avoid locking issues.
    PostgreSQL CREATE DATABASE ... TEMPLATE works even without the datistemplate flag.
    """

    import subprocess
    import sys

    # Import all models to ensure they're registered with Base.metadata
    # Import in dependency order to avoid mapper configuration errors
    from src.llm_config.models import (  # noqa: F401
        CommunityServer,
        CommunityServerLLMConfig,
    )
    from src.notes.models import Note  # noqa: F401
    from src.notes.note_publisher_models import (  # noqa: F401
        NotePublisherConfig,
        NotePublisherPost,
    )
    from src.users.models import User  # noqa: F401
    from src.users.profile_models import (  # noqa: F401
        CommunityMember,
        UserIdentity,
        UserProfile,
    )

    # Get the base database URL from environment
    base_db_url = os.environ.get("DATABASE_URL", "")
    if not base_db_url:
        # If no DATABASE_URL, skip template creation (will be set by test_services)
        yield None
        return

    # Extract connection params from DATABASE_URL
    # postgresql+asyncpg://user:pass@host:port/dbname
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(base_db_url)
    template_db_name = "opennotes_template"

    # Create URL for template database
    template_parsed = parsed._replace(path=f"/{template_db_name}")
    template_db_url = urlunparse(template_parsed)

    # Create URL for postgres database (for admin operations)
    admin_parsed = parsed._replace(path="/postgres")
    admin_db_url = urlunparse(admin_parsed)

    print(f"🔧 Creating template database: {template_db_name}")

    # Create template database using synchronous connection
    from sqlalchemy import create_engine, text

    admin_engine = create_engine(
        admin_db_url.replace("+asyncpg", ""),  # Use psycopg2 for admin operations
        isolation_level="AUTOCOMMIT",
    )

    with admin_engine.connect() as conn:
        # Drop template if it exists
        conn.execute(text(f"DROP DATABASE IF EXISTS {template_db_name}"))
        # Create new template database
        conn.execute(text(f"CREATE DATABASE {template_db_name}"))
    admin_engine.dispose()

    # Create pgvector extension on template database
    template_engine = create_engine(
        template_db_url.replace("+asyncpg", ""), isolation_level="AUTOCOMMIT"
    )
    with template_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    template_engine.dispose()

    # Set DATABASE_URL to template database temporarily for migrations
    original_db_url = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = template_db_url

    # Run migrations on template database using SYNCHRONOUS mode
    # CRITICAL: Set ALEMBIC_SYNC_MODE=1 to avoid async connection issues
    # during template database creation. Async connections can fail with
    # "connection was closed in the middle of operation" errors during
    # concurrent operations in testcontainers setup.
    alembic_dir = str(Path(__file__).parent.parent)
    print(f"🔧 Running migrations on template database: {template_db_name}")
    print(f"   DATABASE_URL: {os.environ['DATABASE_URL']}")
    print("   Using synchronous migration mode (ALEMBIC_SYNC_MODE=1)")

    migration_env = os.environ.copy()
    migration_env["ALEMBIC_SYNC_MODE"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
        cwd=alembic_dir,
        capture_output=True,
        text=True,
        timeout=180,
        env=migration_env,
    )

    # Log migration output for debugging
    if result.stdout:
        print(f"📝 Migration stdout:\n{result.stdout}")
    if result.stderr:
        print(f"📝 Migration stderr:\n{result.stderr}")

    if result.returncode != 0:
        print(f"⚠️  Template migration failed with return code {result.returncode}")
        raise RuntimeError(f"Template migration failed: {result.stderr}")

    sync_template_url = template_db_url.replace("+asyncpg", "")
    print("🔧 Running DBOS system table migrations on template database")
    from dbos import run_dbos_database_migrations

    run_dbos_database_migrations(system_database_url=sync_template_url)
    print("✅ DBOS system tables created in template database")

    # Restore original DATABASE_URL
    os.environ["DATABASE_URL"] = original_db_url

    # DO NOT mark as datistemplate=TRUE - causes locking issues with parallel workers
    # PostgreSQL allows CREATE DATABASE ... TEMPLATE even without this flag

    print(f"✅ Template database created: {template_db_name}")

    yield template_db_name

    # Cleanup: Drop template database
    admin_engine = create_engine(admin_db_url.replace("+asyncpg", ""), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        # Terminate any active connections to template database
        conn.execute(
            text(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{template_db_name}'
              AND pid <> pg_backend_pid()
        """)
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {template_db_name}"))
    admin_engine.dispose()


@pytest.fixture(autouse=True)
async def setup_database(request):
    """
    Setup and teardown database for each test with fresh state.

    Uses fast database cloning from template_database instead of running migrations.
    This is much faster than running migrations for each test.

    With pytest-xdist: Each worker gets its own database cloned from the template.
    """
    if "unit" in request.keywords:
        yield
        return

    # Lazily load fixtures only for non-unit tests to avoid database connection attempts
    test_services = request.getfixturevalue("test_services")  # noqa: F841
    template_database = request.getfixturevalue("template_database")

    # Skip if no template database (shouldn't happen in normal flow)
    if not template_database:
        yield
        return

    import src.database

    # Import all models

    # Get worker ID for pytest-xdist
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    test_db_name = f"opennotes_test_{worker_id}"

    # Get base database URL
    base_db_url = os.environ.get("DATABASE_URL", "")
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(base_db_url)

    # Create URLs
    test_parsed = parsed._replace(path=f"/{test_db_name}")
    test_db_url = urlunparse(test_parsed)

    template_parsed = parsed._replace(path=f"/{template_database}")
    template_db_url = urlunparse(template_parsed)

    admin_parsed = parsed._replace(path="/postgres")
    admin_db_url = urlunparse(admin_parsed)

    # Create test database from template using synchronous connection
    from sqlalchemy import create_engine, text

    admin_engine = create_engine(admin_db_url.replace("+asyncpg", ""), isolation_level="AUTOCOMMIT")

    print(f"🔄 Cloning test database: {test_db_name} from template: {template_database}")
    print(f"   Admin DB URL: {admin_db_url}")
    print(f"   Test DB URL will be: {test_db_url}")

    with admin_engine.connect() as conn:
        # Drop test database if it exists
        conn.execute(text(f"DROP DATABASE IF EXISTS {test_db_name}"))
        # Create test database from template (fast!)
        print(f"   Executing: CREATE DATABASE {test_db_name} TEMPLATE {template_database}")
        conn.execute(text(f"CREATE DATABASE {test_db_name} TEMPLATE {template_database}"))
        print(f"   ✅ Database {test_db_name} cloned from {template_database}")

        # Verify tables exist in cloned database
        conn.execute(text("SELECT 1"))  # Dummy query to ensure connection works

    admin_engine.dispose()

    # Verify the cloned database has tables
    print("🔍 Verifying schema in cloned database...")
    verify_engine = create_engine(test_db_url.replace("+asyncpg", ""), isolation_level="AUTOCOMMIT")
    with verify_engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
        )
        table_count = result.scalar()
        print(f"   Tables in {test_db_name}: {table_count}")
        if table_count == 0:
            print("   ⚠️  WARNING: No tables found in cloned database!")
            # List tables in template for comparison
            template_engine = create_engine(
                template_db_url.replace("+asyncpg", ""), isolation_level="AUTOCOMMIT"
            )
            with template_engine.connect() as template_conn:
                template_result = template_conn.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
                    )
                )
                template_table_count = template_result.scalar()
                print(f"   Tables in template {template_database}: {template_table_count}")
            template_engine.dispose()
    verify_engine.dispose()

    # Update DATABASE_URL to point to test database
    original_db_url = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = test_db_url
    print(f"   DATABASE_URL updated to: {test_db_url}")

    # CRITICAL FIX: Update settings.DATABASE_URL too!
    # The engine uses settings.DATABASE_URL, not os.environ
    from src.config import settings

    original_settings_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url
    print(f"   settings.DATABASE_URL updated to: {test_db_url}")

    # CRITICAL: Reset database module state immediately after updating settings
    # This ensures the engine is in a clean state BEFORE any client initialization.
    # Each test gets a fresh event loop, and async engines are bound to the event loop
    # they were created in. Resetting here guarantees get_engine() will create a new
    # one bound to the current event loop when clients try to use it.
    src.database._engine = None
    src.database._async_session_maker = None
    src.database._engine_loop = None
    print(
        "   Database module state reset (_engine, _async_session_maker, _engine_loop set to None)"
    )

    # CRITICAL FIX: Update settings.REDIS_URL and settings.NATS_URL too!
    # Redis and NATS clients use settings, not os.environ
    original_settings_redis_url = settings.REDIS_URL
    original_settings_nats_url = settings.NATS_URL

    # Use the REDIS_URL and NATS_URL already set by test_services fixture
    if "REDIS_URL" in os.environ:
        settings.REDIS_URL = os.environ["REDIS_URL"]
        print(f"   settings.REDIS_URL updated to: {settings.REDIS_URL}")

    if "NATS_URL" in os.environ:
        settings.NATS_URL = os.environ["NATS_URL"]
        print(f"   settings.NATS_URL updated to: {settings.NATS_URL}")
        print(f"   [DEBUG] db_session: id(settings)={id(settings)}, NATS_URL={settings.NATS_URL}")

    # Reset DBOS client to reconnect with updated DATABASE_URL
    import src.dbos_workflows.config as dbos_config_module

    dbos_config_module.settings = settings
    dbos_config_module.reset_dbos_client()
    print("   DBOS client reset for reconnection with updated DATABASE_URL")

    # Reset redis_client to reconnect with updated REDIS_URL
    # redis_client is initialized at module import with old REDIS_URL
    from src.cache.redis_client import redis_client

    if redis_client.client is not None:
        print("   Disconnecting existing Redis connection...")
        try:
            await redis_client.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting Redis: {e}")
    print("   redis_client reset for reconnection with updated REDIS_URL")

    # Reset nats_client to reconnect with updated NATS_URL
    # nats_client is initialized at module import with old NATS_URL
    from src.events.nats_client import nats_client

    if nats_client.nc is not None:
        print("   Disconnecting existing NATS connection...")
        try:
            await nats_client.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting NATS: {e}")
    print("   nats_client reset for reconnection with updated NATS_URL")

    # Reset cache_manager to pick up new REDIS_URL
    # cache_manager is initialized at module import with old REDIS_URL

    from src.cache.cache import cache_manager

    if cache_manager._started:
        print("   Stopping existing cache_manager...")
        try:
            # Check if there's a running event loop
            loop = asyncio.get_running_loop()
            if not loop.is_closed() and loop.is_running():
                await cache_manager.cache.stop()
            else:
                print("   Event loop is closed or not running, skipping cache.stop()")
            cache_manager._started = False
        except RuntimeError:
            # No running event loop - can't await stop()
            print("   No running event loop, skipping cache.stop()")
            cache_manager._started = False
        except Exception as e:
            # Event loop is closed or other error - just reset the flag
            print(f"   Error stopping cache (event loop may be closed): {e}")
            cache_manager._started = False

    # Recreate the cache adapter with updated REDIS_URL
    from src.cache.adapters import RedisCacheAdapter
    from src.cache.interfaces import CacheConfig

    cache_manager.cache = RedisCacheAdapter(
        config=CacheConfig(
            default_ttl=settings.CACHE_DEFAULT_TTL,
            key_prefix="",
        ),
        url=settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        max_retries=3,
        socket_timeout=float(settings.REDIS_SOCKET_TIMEOUT),
        socket_connect_timeout=float(settings.REDIS_SOCKET_CONNECT_TIMEOUT),
    )
    print(f"   cache_manager.cache recreated with URL: {settings.REDIS_URL}")

    # Force reimport of database-dependent modules to pick up new DATABASE_URL
    # This is needed because test files import app at module level (anti-pattern but widespread)
    import sys

    if "src.main" in sys.modules:
        print("   Warning: src.main already imported - app may have stale database connection")
        # Try to reset app's database state if possible
        try:
            pass
            # FastAPI app state doesn't directly expose database, but we've reset src.database
            # which should be picked up by dependency injection on next request
        except Exception as e:
            print(f"   Could not access app: {e}")

    yield

    # Cleanup: Close database connection
    # Note: With asyncio_default_fixture_loop_scope=function, the event loop is about to close.
    # We skip calling dispose() and just abandon the engine to avoid asyncpg errors when
    # trying to cleanly close connections in a closing/closed event loop.
    # The database connections will be cleaned up by the OS when containers shut down.

    # Reset to None - next test will create a new engine bound to its event loop
    src.database._engine = None
    src.database._async_session_maker = None
    src.database._engine_loop = None

    # Additional cleanup: Force garbage collection to release any lingering async connections
    # NOTE: Disabled gc.collect() because it triggers engine cleanup in a closing event loop,
    # causing asyncpg errors. The connections will be cleaned up when the container shuts down.

    import signal
    import time

    def timeout_handler(signum, frame):
        raise TimeoutError("Database cleanup timed out")

    try:
        # Set a 5-second timeout for database cleanup operations
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)

        try:
            admin_engine = create_engine(
                admin_db_url.replace("+asyncpg", ""), isolation_level="AUTOCOMMIT"
            )
            with admin_engine.connect() as conn:
                # CRITICAL: Terminate all active connections to the test database before dropping it
                # This prevents "database is being accessed by other users" errors from asyncpg connection
                # pool, lingering sessions, or other sources
                conn.execute(
                    text(f"""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = '{test_db_name}'
                      AND pid <> pg_backend_pid()
                """)
                )
                # Give PostgreSQL a moment to clean up the terminated connections
                time.sleep(0.1)
                # Now drop the database - all connections should be closed
                conn.execute(text(f"DROP DATABASE IF EXISTS {test_db_name}"))
            admin_engine.dispose()
        finally:
            # Cancel the alarm
            signal.alarm(0)
    except TimeoutError:
        print("   ⚠️  Database cleanup timed out after 5 seconds (connections may be stuck)")
    except Exception as e:
        print(f"   ⚠️  Error during database cleanup: {e}")
    finally:
        # Ensure signal alarm is cancelled
        try:
            signal.alarm(0)
        except Exception:
            pass

    # Restore original DATABASE_URL, REDIS_URL, and NATS_URL
    os.environ["DATABASE_URL"] = original_db_url
    settings.DATABASE_URL = original_settings_db_url
    settings.REDIS_URL = original_settings_redis_url
    settings.NATS_URL = original_settings_nats_url


@pytest.fixture(autouse=True)
def disable_rate_limiting(monkeypatch):
    """
    Disable rate limiting for all tests by patching the limiter.

    This fixture ensures rate limiting doesn't interfere with tests in two ways:
    1. Environment variable RATE_LIMIT_ENABLED=false disables slowapi's storage checks
    2. This fixture patches the limiter's limit() method to be a no-op decorator

    Combined, these ensure tests can make unlimited requests without hitting rate limits.
    """
    from src.middleware.rate_limiting import limiter

    def mock_limit_decorator(_limit_string: str):
        """Return a decorator that doesn't enforce any rate limits"""

        def decorator(func):
            return func

        return decorator

    monkeypatch.setattr(limiter, "limit", mock_limit_decorator)
    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture(scope="session")
def test_client(test_services) -> TestClient:
    from src.main import app

    return TestClient(app)


@pytest.fixture
def client(test_services) -> TestClient:
    """
    Provide TestClient for each test with fresh database connection.

    Function-scoped to ensure each test gets a clean client that connects
    to the correct per-test database created by setup_database fixture.
    """
    from src.main import app

    return TestClient(app)


@pytest.fixture
async def async_client(test_services):
    """
    Provide AsyncClient for async tests with fresh database connection.

    Function-scoped to ensure each test gets a clean client that connects
    to the correct per-test database created by setup_database fixture.
    """
    from httpx import ASGITransport, AsyncClient

    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_participant_ids() -> dict[str, str]:
    """Sample participant IDs for Community Notes testing"""
    return {
        "alice": "00000000000000000001",
        "bob": "00000000000000000002",
        "charlie": "00000000000000000003",
    }


@pytest.fixture
def test_user_data():
    """Standard test user data for authentication tests"""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "TestPassword123!",
        "full_name": "Test User",
    }


@pytest.fixture
async def registered_user(client, test_user_data):
    """
    Create a registered user for tests that need authentication.

    Uses the standard client fixture to ensure proper database isolation.
    Works with both TestClient and AsyncClient.
    """
    from httpx import ASGITransport, AsyncClient
    from starlette.testclient import TestClient

    # Handle both TestClient (has .app) and AsyncClient (already async)
    if isinstance(client, TestClient):
        # Convert TestClient to AsyncClient for async test support
        async with AsyncClient(
            transport=ASGITransport(app=client.app), base_url="http://test"
        ) as async_client:
            # First, get CSRF token by making a GET request
            get_response = await async_client.get("/api/v1/auth/register")
            csrf_token = None
            if "csrf_token" in get_response.cookies:
                csrf_token = get_response.cookies["csrf_token"]

            headers = {}
            if csrf_token:
                headers["X-CSRF-Token"] = csrf_token

            response = await async_client.post(
                "/api/v1/auth/register", json=test_user_data, headers=headers
            )
    else:
        # Already an AsyncClient
        # First, get CSRF token by making a GET request
        get_response = await client.get("/api/v1/auth/register")
        csrf_token = None
        if "csrf_token" in get_response.cookies:
            csrf_token = get_response.cookies["csrf_token"]

        headers = {}
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token

        response = await client.post("/api/v1/auth/register", json=test_user_data, headers=headers)

    # If user already exists (from previous test), that's ok
    if response.status_code == 400:
        # Return minimal user data that matches what would be returned
        return {
            "id": 1,
            "username": test_user_data["username"],
            "email": test_user_data["email"],
            "full_name": test_user_data["full_name"],
            "role": "user",
            "is_active": True,
            "is_superuser": False,
        }

    assert response.status_code == 201, f"Failed to create user: {response.text}"
    return response.json()


@pytest.fixture
async def auth_headers(registered_user):
    """Generate valid JWT token for authenticated requests using a registered test user"""
    from src.auth.auth import create_access_token

    # Create token with all required claims from registered user
    # The registered_user fixture ensures a real user exists in the database
    token_data = {
        "sub": str(registered_user["id"]),  # user id as string (must be a valid UUID)
        "username": registered_user["username"],
        "role": registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def async_auth_headers(registered_user):
    """Generate valid JWT token for authenticated requests (async version)"""
    from src.auth.auth import create_access_token

    # Create token with all required claims from registered user
    token_data = {
        "sub": str(registered_user["id"]),  # user id as string
        "username": registered_user["username"],
        "role": registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def auth_headers_for_user(registered_user):
    """Generate valid JWT token and user_id for authenticated requests"""
    from src.auth.auth import create_access_token

    # Create token with all required claims from registered user
    token_data = {
        "sub": str(registered_user["id"]),  # user id as string
        "username": registered_user["username"],
        "role": registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {
        "user_id": registered_user["id"],
        "access_token": access_token,
    }


@pytest.fixture
async def db():
    """Provide async database session for integration tests"""
    from src.database import get_db

    # Get a database session
    async for session in get_db():
        yield session
        # Session cleanup handled by get_db context manager


@pytest.fixture
async def db_session(db):
    """Alias for db fixture for compatibility with tests expecting db_session"""
    return db


async def create_valid_oauth_state() -> str:
    """
    Generate and store a valid OAuth state for testing Discord OAuth flows.

    This helper generates a cryptographically secure state token and stores it
    in the mocked Redis client, simulating the /discord/init endpoint behavior.

    Returns:
        str: A valid OAuth state token ready for use in Discord registration/login requests.

    Usage in tests:
        state = await create_valid_oauth_state()
        response = await client.post(
            "/api/v1/profile/auth/register/discord",
            json={"code": "...", "state": state, "display_name": "..."}
        )
    """
    from src.auth.oauth_state import generate_oauth_state, store_oauth_state

    state = generate_oauth_state()
    await store_oauth_state(state)
    return state


async def verify_email_for_testing(email: str):
    """
    Helper function to directly verify an email in the database for testing.

    This bypasses the email verification token flow for testing purposes.
    """
    from sqlalchemy import select

    from src.database import get_db
    from src.users.profile_models import UserIdentity

    # Create a new database session
    async for db in get_db():
        # Find the identity by email
        result = await db.execute(
            select(UserIdentity).where(
                UserIdentity.provider == "email", UserIdentity.provider_user_id == email
            )
        )
        identity = result.scalar_one_or_none()

        if identity:
            identity.email_verified = True
            identity.email_verification_token = None
            identity.email_verification_token_expires = None
            await db.commit()
            await db.refresh(identity)

        return identity
    return None


@pytest.fixture
async def community_server(db):
    """
    Create a CommunityServer for tests that need it.

    Returns the UUID of the created community server.
    This fixture creates a minimal CommunityServer that can be used
    for testing Notes, Requests, and other entities that require a community_server_id.
    """
    from uuid import uuid4

    from src.llm_config.models import CommunityServer

    # Create a test community server
    server = CommunityServer(
        id=uuid4(),
        platform="discord",
        platform_community_server_id="test-server-123",
        name="Test Server",
        is_active=True,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)

    return server.id


@pytest.fixture(autouse=True)
async def mock_external_services(request):
    """
    Mock external services for all tests using centralized Redis mocking.

    Skipped for:
    - Unit tests (marked with @pytest.mark.unit)
    - Integration messaging tests (marked with @pytest.mark.integration_messaging)

    IMPORTANT: Redis Mocking Standards
    -----------------------------------
    All tests should use the centralized Redis mocking approach:

    1. **For unit tests**, use the `create_stateful_redis_mock()` helper:
       ```python
       from tests.redis_mock import create_stateful_redis_mock

       mock_redis = create_stateful_redis_mock()
       service.redis_client = mock_redis
       ```

    2. **For integration tests**, this fixture automatically provides mocked Redis
       via the `mock_external_services` fixture (auto-used).

    3. **DO NOT create ad-hoc mocks**: Avoid patterns like:
       ```python
       # ❌ BAD
       mock_redis = AsyncMock()
       mock_redis.get = AsyncMock(return_value=None)

       # ✅ GOOD
       mock_redis = create_stateful_redis_mock()
       ```

    Benefits of centralized mocking:
    - Consistent behavior across all tests
    - Full Redis state management (keys, TTLs, sets, sorted sets)
    - Realistic Redis operations with proper return values
    - Pipeline support for atomic operations
    - Easier maintenance and updates

    See tests/redis_mock.py for full StatefulRedisMock API documentation.
    """
    # Skip for unit tests and integration messaging tests
    if "unit" in request.keywords or "integration_messaging" in request.keywords:
        yield
        return

    # Get test_services fixture to ensure services are running
    test_services = request.getfixturevalue("test_services")  # noqa: F841

    # Mock the actual instances, not the classes
    from src.cache.redis_client import redis_client
    from src.events.nats_client import nats_client
    from src.middleware.rate_limiting import limiter
    from src.webhooks.cache import interaction_cache
    from src.webhooks.rate_limit import rate_limiter
    from tests.redis_mock import create_stateful_redis_mock

    # Create stateful mock Redis client instance using centralized mocking
    mock_redis = create_stateful_redis_mock()

    # Disable slowapi rate limiting for tests
    limiter.enabled = False

    # Mock NATS client methods
    nats_client.connect = AsyncMock()
    nats_client.disconnect = AsyncMock()
    nats_client.is_connected = AsyncMock(return_value=True)
    nats_client.publish = AsyncMock()
    nats_client.subscribe = AsyncMock()
    nats_client.ping = AsyncMock(return_value=True)

    # Mock Redis client methods using the stateful mock
    redis_client.client = mock_redis
    redis_client.connect = AsyncMock()
    redis_client.disconnect = AsyncMock()
    redis_client.get = mock_redis.get
    redis_client.set = mock_redis.set
    redis_client.delete = mock_redis.delete
    redis_client.exists = mock_redis.exists
    redis_client.ttl = mock_redis.ttl
    redis_client.ping = mock_redis.ping
    redis_client.keys = mock_redis.keys
    redis_client.setex = mock_redis.setex
    # Hash operations for progress tracker
    redis_client.hset = mock_redis.hset
    redis_client.hget = mock_redis.hget
    redis_client.hgetall = mock_redis.hgetall
    redis_client.hincrby = mock_redis.hincrby
    redis_client.expire = mock_redis.expire

    # Mock rate limiter to bypass rate limiting in tests
    rate_limiter.redis_client = mock_redis
    rate_limiter.connect = AsyncMock()
    rate_limiter.disconnect = AsyncMock()
    # Mock check_rate_limit to always allow requests (bypass rate limiting in tests)
    rate_limiter.check_rate_limit = AsyncMock(return_value=(True, 999))
    # Mock get_rate_limit_info for completeness
    rate_limiter.get_rate_limit_info = AsyncMock(
        return_value={"limit": 1000, "remaining": 999, "window": 3600}
    )

    # Mock interaction cache methods
    interaction_cache.redis = mock_redis
    interaction_cache.redis_client = mock_redis  # Fix for webhook tests
    interaction_cache.connect = AsyncMock()
    interaction_cache.disconnect = AsyncMock()
    interaction_cache.get = AsyncMock(return_value=None)
    interaction_cache.set = AsyncMock()
    interaction_cache.check_duplicate = AsyncMock(return_value=False)
    interaction_cache.mark_processed = AsyncMock()
    interaction_cache.store_response = AsyncMock()
    interaction_cache.get_cached_response = AsyncMock(return_value=None)

    yield

    # Cleanup - Clear Redis mock state to prevent test pollution
    mock_redis.store.clear()
    mock_redis.ttl_store.clear()

    # Reset all AsyncMock call counts and call history
    nats_client.connect.reset_mock()
    nats_client.disconnect.reset_mock()
    nats_client.is_connected.reset_mock()
    nats_client.publish.reset_mock()
    nats_client.subscribe.reset_mock()
    nats_client.ping.reset_mock()

    redis_client.connect.reset_mock()
    redis_client.disconnect.reset_mock()

    rate_limiter.connect.reset_mock()
    rate_limiter.disconnect.reset_mock()
    rate_limiter.check_rate_limit.reset_mock()
    rate_limiter.get_rate_limit_info.reset_mock()

    interaction_cache.connect.reset_mock()
    interaction_cache.disconnect.reset_mock()
    interaction_cache.get.reset_mock()
    interaction_cache.set.reset_mock()
    interaction_cache.check_duplicate.reset_mock()
    interaction_cache.mark_processed.reset_mock()
    interaction_cache.store_response.reset_mock()
    interaction_cache.get_cached_response.reset_mock()

    # Clean up references
    redis_client.client = None
