"""TASK-1450.21 — rewrite ``ck_llm_config_provider`` CHECK constraint.

Verifies:

- Existing ``community_server_llm_config.provider`` rows with legacy values
  (``gemini``, ``google``) are rewritten to ``vertex_ai`` by ``upgrade()``.
- The CHECK constraint definition is swapped to the new value set so the
  new ``vertex_ai`` canonical value passes and the removed ``google`` value fails.
- ``downgrade()`` raises ``NotImplementedError``.

Tests invoke the migration's real ``upgrade()`` function inside an alembic
``Operations`` context bound to the test session's connection.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_PATH = (
    _REPO_ROOT / "alembic" / "versions" / "task1450_21_rewrite_llm_config_provider_check.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "_task1450_21_migration_for_test", _MIGRATION_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _invoke_real_upgrade(sync_connection) -> None:
    migration = _load_migration_module()
    migration_context = MigrationContext.configure(connection=sync_connection)
    with Operations.context(migration_context):
        migration.upgrade()


async def _run_upgrade(db_session) -> None:
    connection = await db_session.connection()
    await connection.run_sync(_invoke_real_upgrade)
    await db_session.flush()


async def _fetch_check_constraint_body(db_session) -> str:
    result = await db_session.execute(
        text(
            """
            SELECT pg_get_constraintdef(oid) AS defn
              FROM pg_constraint
             WHERE conname = 'ck_llm_config_provider'
            """
        )
    )
    return result.scalar_one()


async def _restore_legacy_constraint(db_session) -> None:
    """Undo the migration so the test can exercise it from scratch.

    The template DB used by testcontainers already applies all migrations
    (including this one), so without rewinding the constraint the pre-state
    assertions would be tautological. We do NOT restore the pre-migration
    provider values — tests seed the rows they care about after the rewind.
    """

    await db_session.execute(
        text("ALTER TABLE community_server_llm_config DROP CONSTRAINT ck_llm_config_provider")
    )
    await db_session.execute(
        text(
            """
            ALTER TABLE community_server_llm_config
            ADD CONSTRAINT ck_llm_config_provider
            CHECK (provider IN ('openai', 'anthropic', 'google', 'cohere', 'custom'))
            """
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_upgrade_narrows_check_constraint(db_session):
    await _restore_legacy_constraint(db_session)

    before = await _fetch_check_constraint_body(db_session)
    assert "'google'" in before
    assert "'vertex_ai'" not in before

    await _run_upgrade(db_session)

    after = await _fetch_check_constraint_body(db_session)
    assert "'vertex_ai'" in after
    assert "'google'" not in after
    assert "'cohere'" not in after
    assert "'custom'" not in after


@pytest.mark.asyncio
async def test_upgrade_rewrites_legacy_gemini_and_google_rows(db_session):
    """Rows using legacy provider values are rewritten to ``vertex_ai``.

    Roll back the constraint to the legacy shape first so the INSERTs are
    allowed; disable replication-role triggers so the FK to
    ``community_servers`` doesn't block the insert.
    """

    await _restore_legacy_constraint(db_session)

    await db_session.execute(text("SET LOCAL session_replication_role = 'replica'"))
    # Only 'google' is representable under the legacy CHECK constraint;
    # 'gemini' was never valid DB-side (it was a Pydantic-flavor adapter key).
    # The migration still covers 'gemini' defensively in case a row got in
    # via direct SQL, but the test can only verify the 'google' path here.
    await db_session.execute(
        text(
            r"""
            INSERT INTO community_server_llm_config (
                id, community_server_id, provider,
                api_key_encrypted, api_key_preview,
                encryption_key_id, enabled
            )
            VALUES
                ('33333333-3333-3333-3333-333333333333'::uuid,
                 '44444444-4444-4444-4444-444444444444'::uuid,
                 'google', '\x00'::bytea, '*** redacted', 'k1', true)
            """
        )
    )
    await db_session.flush()

    await _run_upgrade(db_session)

    result = await db_session.execute(
        text(
            "SELECT id, provider FROM community_server_llm_config "
            "WHERE id = '33333333-3333-3333-3333-333333333333'::uuid"
        )
    )
    row = result.one()
    assert row.provider == "vertex_ai"


def test_downgrade_raises():
    migration = _load_migration_module()

    with pytest.raises(NotImplementedError, match=r"TASK-1450\.21 downgrade"):
        migration.downgrade()
