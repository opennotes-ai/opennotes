"""TASK-1450.09 — data migration rewrites ``opennotes_sim_agents.model_name``.

Verifies:

- Every from-pattern is rewritten to the correct ``google-vertex`` Gemini 3 SKU.
- The specific ``google-gla:gemini-2.5-flash`` mapping wins over the
  ``google-gla:%`` catch-all so flash never collapses into the pro preview.
- Legacy ``global/`` shapes
  (``google-vertex:global/gemini-2.5-{pro,flash}``) are rewritten too — these
  come from the older ``vertex_ai/global/...`` slash format that leaked into
  persisted rows.
- Re-running the upgrade is a no-op (idempotent WHERE clauses).
- ``downgrade()`` raises ``NotImplementedError`` to prevent resurrecting
  Gemini 2.5 SKUs after their 2026-10-16 retirement on Vertex.

The tests invoke the migration's real ``upgrade()`` function inside an alembic
``Operations`` context bound to the test session's connection, rather than
duplicating the SQL.  This ensures the test follows actual migration behavior
and catches any drift between the migration and the expected rewrites.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_PATH = (
    _REPO_ROOT / "alembic" / "versions" / "task1450_09_migrate_sim_agents_model_name_to_gemini3.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "_task1450_09_migration_for_test", _MIGRATION_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _seed_agent(db_session, name: str, model_name: str) -> str:
    agent_id = str(uuid4())
    await db_session.execute(
        text(
            """
            INSERT INTO opennotes_sim_agents (
                id, name, personality, model_name,
                memory_compaction_strategy, created_at, updated_at
            )
            VALUES (
                CAST(:id AS uuid), :name, :personality, :model_name,
                'sliding_window', NOW(), NOW()
            )
            """
        ),
        {
            "id": agent_id,
            "name": name,
            "personality": f"personality for {name}",
            "model_name": model_name,
        },
    )
    await db_session.flush()
    return agent_id


async def _read_model(db_session, agent_id: str) -> str:
    result = await db_session.execute(
        text("SELECT model_name FROM opennotes_sim_agents WHERE id = CAST(:id AS uuid)"),
        {"id": agent_id},
    )
    return result.scalar_one()


def _invoke_real_upgrade(sync_connection) -> None:
    """Run the migration's real ``upgrade()`` against ``sync_connection``.

    Binds a fresh ``MigrationContext`` + ``Operations`` scope so the module's
    ``from alembic import op`` proxy routes ``op.execute`` through the caller's
    connection.
    """

    migration = _load_migration_module()
    migration_context = MigrationContext.configure(connection=sync_connection)
    with Operations.context(migration_context):
        migration.upgrade()


async def _run_upgrade(db_session) -> None:
    connection = await db_session.connection()
    await connection.run_sync(_invoke_real_upgrade)
    await db_session.flush()


@pytest.mark.asyncio
async def test_migration_rewrites_google_gla_pro_to_pro_preview(db_session):
    agent_id = await _seed_agent(db_session, "agent-gla-pro", "google-gla:gemini-2.5-pro")

    await _run_upgrade(db_session)

    assert await _read_model(db_session, agent_id) == "google-vertex:gemini-3.1-pro-preview"


@pytest.mark.asyncio
async def test_migration_rewrites_google_gla_flash_to_gemini_3_flash(db_session):
    agent_id = await _seed_agent(db_session, "agent-gla-flash", "google-gla:gemini-2.5-flash")

    await _run_upgrade(db_session)

    assert await _read_model(db_session, agent_id) == "google-vertex:gemini-3-flash"


@pytest.mark.asyncio
async def test_migration_rewrites_google_vertex_2_5_pro(db_session):
    agent_id = await _seed_agent(db_session, "agent-vertex-pro", "google-vertex:gemini-2.5-pro")

    await _run_upgrade(db_session)

    assert await _read_model(db_session, agent_id) == "google-vertex:gemini-3.1-pro-preview"


@pytest.mark.asyncio
async def test_migration_rewrites_google_vertex_2_5_flash(db_session):
    agent_id = await _seed_agent(db_session, "agent-vertex-flash", "google-vertex:gemini-2.5-flash")

    await _run_upgrade(db_session)

    assert await _read_model(db_session, agent_id) == "google-vertex:gemini-3-flash"


@pytest.mark.asyncio
async def test_migration_rewrites_google_vertex_global_2_5_pro(db_session):
    """Legacy ``global/`` pro shape is rewritten to the pro preview."""

    agent_id = await _seed_agent(
        db_session,
        "agent-vertex-global-pro",
        "google-vertex:global/gemini-2.5-pro",
    )

    await _run_upgrade(db_session)

    assert await _read_model(db_session, agent_id) == "google-vertex:gemini-3.1-pro-preview"


@pytest.mark.asyncio
async def test_migration_rewrites_google_vertex_global_2_5_flash(db_session):
    """Legacy ``global/`` flash shape is rewritten to gemini-3-flash, not pro preview."""

    agent_id = await _seed_agent(
        db_session,
        "agent-vertex-global-flash",
        "google-vertex:global/gemini-2.5-flash",
    )

    await _run_upgrade(db_session)

    assert await _read_model(db_session, agent_id) == "google-vertex:gemini-3-flash"


@pytest.mark.asyncio
async def test_migration_catch_all_for_unknown_google_gla_models(db_session):
    agent_id = await _seed_agent(db_session, "agent-gla-unknown", "google-gla:gemini-1.5-weirdo")

    await _run_upgrade(db_session)

    assert await _read_model(db_session, agent_id) == "google-vertex:gemini-3.1-pro-preview"


@pytest.mark.asyncio
async def test_migration_is_idempotent(db_session):
    pro_id = await _seed_agent(db_session, "agent-idem-pro", "google-gla:gemini-2.5-pro")
    flash_id = await _seed_agent(db_session, "agent-idem-flash", "google-gla:gemini-2.5-flash")
    vertex_pro_id = await _seed_agent(
        db_session, "agent-idem-vertex-pro", "google-vertex:gemini-2.5-pro"
    )
    vertex_flash_id = await _seed_agent(
        db_session, "agent-idem-vertex-flash", "google-vertex:gemini-2.5-flash"
    )
    vertex_global_pro_id = await _seed_agent(
        db_session,
        "agent-idem-vertex-global-pro",
        "google-vertex:global/gemini-2.5-pro",
    )
    vertex_global_flash_id = await _seed_agent(
        db_session,
        "agent-idem-vertex-global-flash",
        "google-vertex:global/gemini-2.5-flash",
    )
    unknown_id = await _seed_agent(
        db_session, "agent-idem-unknown", "google-gla:gemini-experimental"
    )

    await _run_upgrade(db_session)

    first_pass = {
        pro_id: await _read_model(db_session, pro_id),
        flash_id: await _read_model(db_session, flash_id),
        vertex_pro_id: await _read_model(db_session, vertex_pro_id),
        vertex_flash_id: await _read_model(db_session, vertex_flash_id),
        vertex_global_pro_id: await _read_model(db_session, vertex_global_pro_id),
        vertex_global_flash_id: await _read_model(db_session, vertex_global_flash_id),
        unknown_id: await _read_model(db_session, unknown_id),
    }

    await _run_upgrade(db_session)

    second_pass = {
        pro_id: await _read_model(db_session, pro_id),
        flash_id: await _read_model(db_session, flash_id),
        vertex_pro_id: await _read_model(db_session, vertex_pro_id),
        vertex_flash_id: await _read_model(db_session, vertex_flash_id),
        vertex_global_pro_id: await _read_model(db_session, vertex_global_pro_id),
        vertex_global_flash_id: await _read_model(db_session, vertex_global_flash_id),
        unknown_id: await _read_model(db_session, unknown_id),
    }

    assert first_pass == second_pass
    assert first_pass[pro_id] == "google-vertex:gemini-3.1-pro-preview"
    assert first_pass[flash_id] == "google-vertex:gemini-3-flash"
    assert first_pass[vertex_pro_id] == "google-vertex:gemini-3.1-pro-preview"
    assert first_pass[vertex_flash_id] == "google-vertex:gemini-3-flash"
    assert first_pass[vertex_global_pro_id] == "google-vertex:gemini-3.1-pro-preview"
    assert first_pass[vertex_global_flash_id] == "google-vertex:gemini-3-flash"
    assert first_pass[unknown_id] == "google-vertex:gemini-3.1-pro-preview"


@pytest.mark.unit
def test_downgrade_raises():
    migration = _load_migration_module()
    with pytest.raises(NotImplementedError, match="2026-10-16"):
        migration.downgrade()
