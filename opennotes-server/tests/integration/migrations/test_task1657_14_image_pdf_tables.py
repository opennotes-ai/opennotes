"""Integration test for task1657_14 migration (TASK-1657.14).

Verifies:
- url_scan_image_upload_batches table is created with correct structure
- url_scan_pdf_archives table is created with correct structure
- RLS is enabled and forced on both tables
- Application role policy is created when role lacks BYPASSRLS
- Both tables accept valid INSERT payloads
"""

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
from sqlalchemy.exc import DBAPIError

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_PATH = (
    _REPO_ROOT / "alembic" / "versions" / "task1657_14_url_scan_image_and_pdf_tables.py"
)

_NEW_TABLES = (
    "url_scan_image_upload_batches",
    "url_scan_pdf_archives",
)


def _load_migration_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"_migration_{path.stem}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _invoke_real_upgrade(sync_connection, module) -> None:
    migration_context = MigrationContext.configure(connection=sync_connection)
    with Operations.context(migration_context):
        module.upgrade()


async def _run_prereq_migrations(db_session) -> None:
    for stem in [
        "task1487_03_url_scan_tables",
        "task1657_21_url_scan_state_deleted_at",
        "task1657_07_url_scan_vision_cache_tables",
    ]:
        path = _REPO_ROOT / "alembic" / "versions" / f"{stem}.py"
        module = _load_migration_module(path)
        connection = await db_session.connection()
        await connection.run_sync(_invoke_real_upgrade, module)
        await db_session.flush()


async def _run_upgrade(db_session) -> None:
    module = _load_migration_module(_MIGRATION_PATH)
    connection = await db_session.connection()
    await connection.run_sync(_invoke_real_upgrade, module)
    await db_session.flush()


@pytest.mark.asyncio
async def test_upgrade_creates_tables_with_rls(db_session):
    await _run_prereq_migrations(db_session)
    await _run_upgrade(db_session)

    result = await db_session.execute(
        text(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = ANY(:table_names)
            ORDER BY c.relname
            """
        ),
        {"table_names": list(_NEW_TABLES)},
    )
    rows = result.all()
    assert sorted([row.relname for row in rows]) == sorted(_NEW_TABLES)
    assert all(row.relrowsecurity for row in rows), "RLS must be enabled"
    assert all(row.relforcerowsecurity for row in rows), "RLS must be forced"


@pytest.mark.asyncio
async def test_upgrade_creates_indexes(db_session):
    await _run_prereq_migrations(db_session)
    await _run_upgrade(db_session)

    expected_indexes = [
        "ix_url_scan_image_upload_batches_job_id",
        "ix_url_scan_pdf_archives_expires_at",
    ]
    result = await db_session.execute(
        text(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = ANY(:index_names)
            ORDER BY indexname
            """
        ),
        {"index_names": expected_indexes},
    )
    found = [row.indexname for row in result.all()]
    for idx in expected_indexes:
        assert idx in found, f"Expected index {idx!r} not found"

    result2 = await db_session.execute(
        text(
            """
            SELECT indexname, indisunique
            FROM pg_indexes
            JOIN pg_class ON pg_class.relname = pg_indexes.indexname
            JOIN pg_index ON pg_index.indexrelid = pg_class.oid
            WHERE schemaname = 'public'
              AND indexname = 'ix_url_scan_image_upload_batches_job_id'
            """
        ),
    )
    row = result2.first()
    assert row is not None
    assert row.indisunique is True, "job_id index must be unique"


@pytest.mark.asyncio
async def test_upgrade_creates_application_role_policy(db_session):
    await _run_prereq_migrations(db_session)
    await _run_upgrade(db_session)

    configured_role = make_url(os.environ["DATABASE_URL"]).username
    assert configured_role is not None

    result = await db_session.execute(
        text(
            """
            SELECT rolname, rolbypassrls
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
            SELECT tablename, policyname, roles, qual, with_check
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = ANY(:table_names)
            ORDER BY tablename, policyname
            """
        ),
        {"table_names": list(_NEW_TABLES)},
    )
    policy_rows = policies.all()
    assert len(policy_rows) == len(_NEW_TABLES)
    assert {row.tablename for row in policy_rows} == set(_NEW_TABLES)
    for row in policy_rows:
        assert role_name in row.roles
        assert row.qual == "true"
        assert row.with_check == "true"


@pytest.mark.asyncio
async def test_image_upload_batches_accepts_valid_insert(db_session):
    await _run_prereq_migrations(db_session)
    await _run_upgrade(db_session)

    batch_job_id = uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO batch_jobs (id, job_type, status, total_tasks, completed_tasks, failed_tasks)
            VALUES (:id, 'url_scan', 'pending', 1, 0, 0)
            """
        ),
        {"id": batch_job_id},
    )

    await db_session.execute(
        text(
            """
            INSERT INTO url_scan_image_upload_batches
                (job_id, images, conversion_status, generated_pdf_gcs_key)
            VALUES (
                :job_id,
                :images,
                'awaiting_upload',
                :pdf_key
            )
            """
        ),
        {
            "job_id": batch_job_id,
            "images": '[{"ordinal":0,"gcs_key":"image-uploads/test/source/000-abc","content_type":"image/jpeg","size_bytes":1024}]',
            "pdf_key": f"image-uploads/{batch_job_id}/generated.pdf",
        },
    )

    result = await db_session.execute(
        text("SELECT conversion_status FROM url_scan_image_upload_batches WHERE job_id = :job_id"),
        {"job_id": batch_job_id},
    )
    row = result.one()
    assert row.conversion_status == "awaiting_upload"


@pytest.mark.asyncio
async def test_pdf_archives_accepts_valid_insert(db_session):
    await _run_prereq_migrations(db_session)
    await _run_upgrade(db_session)

    job_id = uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO batch_jobs (id, job_type, status, total_tasks, completed_tasks, failed_tasks)
            VALUES (:id, 'url_scan', 'pending', 1, 0, 0)
            """
        ),
        {"id": job_id},
    )

    await db_session.execute(
        text(
            """
            INSERT INTO url_scan_pdf_archives (job_id, html)
            VALUES (:job_id, :html)
            """
        ),
        {"job_id": job_id, "html": "<html><body>PDF content</body></html>"},
    )

    result = await db_session.execute(
        text("SELECT html, expires_at FROM url_scan_pdf_archives WHERE job_id = :job_id"),
        {"job_id": job_id},
    )
    row = result.one()
    assert "PDF content" in row.html
    assert row.expires_at is not None


@pytest.mark.asyncio
async def test_image_upload_batches_rejects_invalid_status(db_session):
    await _run_prereq_migrations(db_session)
    await _run_upgrade(db_session)

    job_id = uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO batch_jobs (id, job_type, status, total_tasks, completed_tasks, failed_tasks)
            VALUES (:id, 'url_scan', 'pending', 1, 0, 0)
            """
        ),
        {"id": job_id},
    )

    async def _do_bad_insert() -> None:
        await db_session.execute(
            text(
                """
                INSERT INTO url_scan_image_upload_batches
                    (job_id, images, conversion_status)
                VALUES (:job_id, '[]', 'invalid_status')
                """
            ),
            {"job_id": job_id},
        )
        await db_session.flush()

    with pytest.raises(DBAPIError):
        await _do_bad_insert()
