from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import make_url

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_PATH = (
    _REPO_ROOT / "alembic" / "versions" / "task1657_07_url_scan_vision_cache_tables.py"
)

_VISION_CACHE_TABLES = (
    "url_scan_image_analysis_cache",
    "url_scan_video_analysis_cache",
)

_PREREQ_MIGRATION_PATH = (
    _REPO_ROOT / "alembic" / "versions" / "task1657_21_url_scan_state_deleted_at.py"
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
    for path in [
        _REPO_ROOT / "alembic" / "versions" / "task1487_03_url_scan_tables.py",
        _REPO_ROOT / "alembic" / "versions" / "task1657_21_url_scan_state_deleted_at.py",
    ]:
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
async def test_upgrade_creates_vision_cache_tables_and_enables_rls(db_session):
    await _run_prereq_migrations(db_session)
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
        {"table_names": list(_VISION_CACHE_TABLES)},
    )
    rows = result.all()
    assert [row.relname for row in rows] == sorted(_VISION_CACHE_TABLES)
    assert all(row.relrowsecurity for row in rows)
    assert all(row.relforcerowsecurity for row in rows)


@pytest.mark.asyncio
async def test_upgrade_creates_expires_at_indexes(db_session):
    await _run_prereq_migrations(db_session)
    await _run_upgrade(db_session)

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
        {
            "index_names": [
                "ix_url_scan_image_analysis_cache_expires_at",
                "ix_url_scan_video_analysis_cache_expires_at",
            ]
        },
    )
    index_names = [row.indexname for row in result.all()]
    assert "ix_url_scan_image_analysis_cache_expires_at" in index_names
    assert "ix_url_scan_video_analysis_cache_expires_at" in index_names


@pytest.mark.asyncio
async def test_upgrade_creates_application_role_policy_when_role_lacks_bypassrls(db_session):
    await _run_prereq_migrations(db_session)
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
        {"table_names": list(_VISION_CACHE_TABLES)},
    )
    policy_rows = policies.all()
    assert len(policy_rows) == len(_VISION_CACHE_TABLES)
    assert {row.tablename for row in policy_rows} == set(_VISION_CACHE_TABLES)
    for row in policy_rows:
        assert role_name in row.roles
        assert row.qual == "true"
        assert row.with_check == "true"


@pytest.mark.asyncio
async def test_image_cache_table_accepts_saferesult_payload(db_session):
    await _run_prereq_migrations(db_session)
    await _run_upgrade(db_session)

    await db_session.execute(
        text(
            """
            INSERT INTO url_scan_image_analysis_cache
                (image_url, result_payload, checked_at, expires_at)
            VALUES (
                :image_url,
                :payload,
                now(),
                now() + interval '24 hours'
            )
            """
        ),
        {
            "image_url": "https://cdn.example.com/test.png",
            "payload": '{"adult":0.0,"violence":0.9,"racy":0.0,"medical":0.0,"spoof":0.0,"flagged":true,"max_likelihood":0.9}',
        },
    )

    result = await db_session.execute(
        text(
            "SELECT image_url, result_payload->>'flagged' AS flagged "
            "FROM url_scan_image_analysis_cache "
            "WHERE image_url = :image_url"
        ),
        {"image_url": "https://cdn.example.com/test.png"},
    )
    row = result.one()
    assert row.image_url == "https://cdn.example.com/test.png"
    assert row.flagged == "true"


@pytest.mark.asyncio
async def test_video_cache_table_accepts_frame_findings_payload(db_session):
    await _run_prereq_migrations(db_session)
    await _run_upgrade(db_session)

    await db_session.execute(
        text(
            """
            INSERT INTO url_scan_video_analysis_cache
                (video_url, frame_findings_payload, checked_at, expires_at)
            VALUES (
                :video_url,
                :payload,
                now(),
                now() + interval '24 hours'
            )
            """
        ),
        {
            "video_url": "https://cdn.example.com/clip.mp4",
            "payload": '[{"frame_offset_ms":0,"adult":0.0,"violence":0.8,"racy":0.0,"medical":0.0,"spoof":0.0,"flagged":true,"max_likelihood":0.8}]',
        },
    )

    result = await db_session.execute(
        text(
            "SELECT video_url, jsonb_array_length(frame_findings_payload) AS finding_count "
            "FROM url_scan_video_analysis_cache "
            "WHERE video_url = :video_url"
        ),
        {"video_url": "https://cdn.example.com/clip.mp4"},
    )
    row = result.one()
    assert row.video_url == "https://cdn.example.com/clip.mp4"
    assert row.finding_count == 1
