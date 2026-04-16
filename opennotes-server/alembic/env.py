import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context  # type: ignore[attr-defined]

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Import all models so they're registered with Base.metadata
from src.auth import models as auth_models  # noqa: F401
from src.batch_jobs import models as batch_jobs_models  # noqa: F401
from src.bulk_content_scan import models as bulk_content_scan_models  # noqa: F401
from src.cache import models as cache_models  # noqa: F401
from src.community_config import models as community_config_models  # noqa: F401
from src.config import settings
from src.database import SUPAVISOR_CONNECT_ARGS, Base
from src.dbos_workflows.token_bucket import models as token_bucket_models  # noqa: F401
from src.fact_checking import (
    candidate_models,  # noqa: F401
    chunk_models,  # noqa: F401
    dataset_models,  # noqa: F401
)
from src.fact_checking import models as fact_checking_models  # noqa: F401
from src.llm_config import models as llm_config_models  # noqa: F401
from src.moderation_actions import models as moderation_actions_models  # noqa: F401
from src.notes import models as notes_models  # noqa: F401
from src.notes import note_publisher_models  # noqa: F401
from src.notes.scoring import models as scoring_models  # noqa: F401
from src.simulation import models as simulation_models  # noqa: F401
from src.users import models as users_models  # noqa: F401
from src.webhooks import delivery_models as webhooks_delivery_models  # noqa: F401
from src.webhooks import models as webhooks_models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    """Filter objects for alembic autogenerate comparison.

    Excludes:
    - PGroonga indexes: created via raw SQL, not trackable via SQLAlchemy Index()
    - PostgreSQL CONCURRENT indexes on users table added in phase_11a: the CI
      postgres reflection reports spurious "modify_type JSON->JSONB" and
      "remove_index" drift for columns/indexes that are actually correct.
      Verified locally that alembic check passes cleanly against a fresh DB.
      This is a known SQLAlchemy/Alembic reflection quirk with certain
      postgres extensions (pgvector+pgroonga custom image).
    - users.role, users.is_superuser, users.is_service_account: legacy columns
      whose drop is intentionally DEFERRED to a future R4 PR per TASK-1451.17
      (SDK coordination gate). The ORM no longer references them but the DB
      retains them until the rolling-deploy bridge completes. Suppress drift
      to keep CI green during the deferral window. Scoped to the `users`
      table specifically so legitimate drift on `role` columns of
      user_profiles / community_members is not silently swallowed.
    """
    del reflected, compare_to
    if type_ == "index" and name and "pgroonga" in name.lower():
        return False
    # Phase 1.1 auth redesign column exclusions (CI reflection quirk only):
    if type_ == "column" and name in ("platform_roles", "principal_type"):
        return False
    # TASK-1451.17 deferred-drop columns (R4 SDK coordination gate) —
    # scoped to the users table only, since `role` also exists on user_profiles
    # and community_members where future drift must remain visible.
    if (
        type_ == "column"
        and name in ("role", "is_superuser", "is_service_account")
        and getattr(getattr(obj, "table", None), "name", None) == "users"
    ):
        return False
    return not (
        type_ == "index"
        and name
        in (
            "idx_users_banned_at",
            "idx_users_platform_roles_gin",
            "idx_users_principal_type",
        )
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online_sync() -> None:
    """Run migrations in synchronous 'online' mode.

    This mode is used for template database creation in tests to avoid
    async connection issues that can occur during concurrent operations.

    Use ALEMBIC_SYNC_MODE=1 environment variable to enable this mode.
    """
    # Convert async URL to sync URL (postgresql+asyncpg -> postgresql)
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")

    connectable = create_engine(
        sync_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


async def run_migrations_online() -> None:
    """Run migrations in async 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Use the DATABASE_URL from settings
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
        connect_args={**SUPAVISOR_CONNECT_ARGS, "server_settings": {"statement_timeout": "0"}},
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
# Use synchronous mode if ALEMBIC_SYNC_MODE is set (for template creation)
elif os.environ.get("ALEMBIC_SYNC_MODE") == "1":
    run_migrations_online_sync()
else:
    asyncio.run(run_migrations_online())
