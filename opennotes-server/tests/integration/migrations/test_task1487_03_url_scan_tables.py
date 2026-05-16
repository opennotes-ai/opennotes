from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import make_url

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_PATH = _REPO_ROOT / "alembic" / "versions" / "task1487_03_url_scan_tables.py"

_URL_SCAN_TABLES = (
    "url_scan_state",
    "url_scan_section_slots",
    "url_scan_scrapes",
    "url_scan_utterances",
    "url_scan_web_risk_lookups",
    "url_scan_sidebar_cache",
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "_task1487_03_migration_for_test", _MIGRATION_PATH
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


@pytest.mark.asyncio
async def test_upgrade_creates_tables_and_enables_rls(db_session):
    await _run_upgrade(db_session)

    result = await db_session.execute(
        text(
            """
            SELECT
                c.relname,
                c.relrowsecurity,
                c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = ANY(:table_names)
            ORDER BY c.relname
            """
        ),
        {"table_names": list(_URL_SCAN_TABLES)},
    )
    rows = result.all()
    assert [row.relname for row in rows] == sorted(_URL_SCAN_TABLES)
    assert all(row.relrowsecurity for row in rows)
    assert all(row.relforcerowsecurity for row in rows)


@pytest.mark.asyncio
async def test_upgrade_creates_application_role_policy_when_role_lacks_bypassrls(db_session):
    await _run_upgrade(db_session)

    configured_role = make_url(os.environ["DATABASE_URL"]).username
    assert configured_role is not None

    result = await db_session.execute(
        text(
            """
            SELECT rolname AS role_name, rolbypassrls
            FROM pg_roles
            WHERE rolname = :role_name
            """
        ),
        {"role_name": configured_role},
    )
    role_name, has_bypassrls = result.one()

    if has_bypassrls:
        pytest.skip(f"configured app role {role_name} already has BYPASSRLS")

    policies = await db_session.execute(
        text(
            """
            SELECT schemaname, tablename, policyname, roles, qual, with_check
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = ANY(:table_names)
            ORDER BY tablename, policyname
            """
        ),
        {"table_names": list(_URL_SCAN_TABLES)},
    )
    policy_rows = policies.all()
    assert len(policy_rows) == len(_URL_SCAN_TABLES)
    assert {row.tablename for row in policy_rows} == set(_URL_SCAN_TABLES)
    for row in policy_rows:
        assert role_name in row.roles
        assert row.qual == "true"
        assert row.with_check == "true"


@pytest.mark.asyncio
async def test_upgrade_cascade_deletes_url_scan_child_rows_with_batch_job(db_session):
    await _run_upgrade(db_session)

    job_id = uuid4()
    attempt_id = uuid4()

    await db_session.execute(
        text(
            """
            INSERT INTO batch_jobs (
                id, job_type, status, total_tasks, completed_tasks, failed_tasks, metadata
            )
            VALUES (
                CAST(:job_id AS uuid), 'url_scan', 'pending', 0, 0, 0, '{}'::jsonb
            )
            """
        ),
        {"job_id": str(job_id)},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO url_scan_state (
                job_id, source_url, normalized_url, host, attempt_id, utterance_count
            )
            VALUES (
                CAST(:job_id AS uuid),
                'https://example.com/a',
                'https://example.com/a',
                'example.com',
                CAST(:attempt_id AS uuid),
                0
            )
            """
        ),
        {"job_id": str(job_id), "attempt_id": str(attempt_id)},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO url_scan_section_slots (
                job_id, slug, state, attempt_id, created_at, updated_at
            )
            VALUES (
                CAST(:job_id AS uuid), 'safety', 'PENDING', CAST(:attempt_id AS uuid), NOW(), NOW()
            )
            """
        ),
        {"job_id": str(job_id), "attempt_id": str(attempt_id)},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO url_scan_utterances (job_id, utterance_id, payload)
            VALUES (
                CAST(:job_id AS uuid), 'utt-1', '{"kind":"fact"}'::jsonb
            )
            """
        ),
        {"job_id": str(job_id)},
    )

    await db_session.execute(
        text("DELETE FROM batch_jobs WHERE id = CAST(:job_id AS uuid)"),
        {"job_id": str(job_id)},
    )

    for table_name in ("url_scan_state", "url_scan_section_slots", "url_scan_utterances"):
        result = await db_session.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE job_id = CAST(:job_id AS uuid)"),
            {"job_id": str(job_id)},
        )
        assert result.scalar_one() == 0


@pytest.mark.asyncio
async def test_url_scan_section_slot_attempt_id_compare_and_swap_contract(db_session):
    await _run_upgrade(db_session)

    job_id = uuid4()
    current_attempt_id = uuid4()
    stale_attempt_id = uuid4()

    await db_session.execute(
        text(
            """
            INSERT INTO batch_jobs (
                id, job_type, status, total_tasks, completed_tasks, failed_tasks, metadata
            )
            VALUES (
                CAST(:job_id AS uuid), 'url_scan', 'pending', 0, 0, 0, '{}'::jsonb
            )
            """
        ),
        {"job_id": str(job_id)},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO url_scan_section_slots (
                job_id, slug, state, attempt_id, created_at, updated_at
            )
            VALUES (
                CAST(:job_id AS uuid), 'safety', 'RUNNING', CAST(:attempt_id AS uuid), NOW(), NOW()
            )
            """
        ),
        {"job_id": str(job_id), "attempt_id": str(current_attempt_id)},
    )

    stale_update = await db_session.execute(
        text(
            """
            UPDATE url_scan_section_slots
            SET state = 'DONE', updated_at = NOW()
            WHERE job_id = CAST(:job_id AS uuid)
              AND slug = 'safety'
              AND attempt_id = CAST(:attempt_id AS uuid)
            """
        ),
        {"job_id": str(job_id), "attempt_id": str(stale_attempt_id)},
    )
    assert stale_update.rowcount == 0

    matching_update = await db_session.execute(
        text(
            """
            UPDATE url_scan_section_slots
            SET state = 'DONE', updated_at = NOW()
            WHERE job_id = CAST(:job_id AS uuid)
              AND slug = 'safety'
              AND attempt_id = CAST(:attempt_id AS uuid)
            """
        ),
        {"job_id": str(job_id), "attempt_id": str(current_attempt_id)},
    )
    assert matching_update.rowcount == 1
