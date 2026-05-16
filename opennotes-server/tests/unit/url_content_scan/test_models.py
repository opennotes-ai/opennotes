from __future__ import annotations

from pathlib import Path

import pytest


def test_url_scan_models_module_exists():
    from src.url_content_scan import models

    assert models is not None


@pytest.mark.unit
def test_url_scan_state_metadata_contract():
    from src.url_content_scan.models import UrlScanState

    table = UrlScanState.__table__
    column_names = {column.name for column in table.columns}

    assert UrlScanState.__tablename__ == "url_scan_state"
    assert "job_id" in column_names
    assert "normalized_url" in column_names
    assert "attempt_id" in column_names
    assert "heartbeat_at" in column_names
    assert "finished_at" in column_names
    assert "status" not in column_names
    assert "sections" not in column_names


@pytest.mark.unit
def test_url_scan_state_fk_and_partial_indexes():
    from src.url_content_scan.models import UrlScanState

    table = UrlScanState.__table__
    foreign_keys = list(table.c.job_id.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "batch_jobs.id"
    assert foreign_keys[0].ondelete == "CASCADE"

    indexes = {index.name: index for index in table.indexes}
    assert "ix_url_scan_state_normalized_url" in indexes
    assert "ix_url_scan_state_heartbeat_at_active" in indexes
    assert "ix_url_scan_state_finished_at_terminal" in indexes


@pytest.mark.unit
def test_url_scan_section_slot_metadata_contract():
    from src.url_content_scan.models import UrlScanSectionSlot

    table = UrlScanSectionSlot.__table__
    pk_columns = [column.name for column in table.primary_key.columns]
    assert pk_columns == ["job_id", "slug"]

    indexes = {index.name: index for index in table.indexes}
    state_index = indexes["ix_url_scan_section_slots_job_id_state"]
    assert [column.name for column in state_index.columns] == ["job_id", "state"]

    foreign_keys = list(table.c.job_id.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "CASCADE"


@pytest.mark.unit
def test_url_scan_cache_tables_have_expected_primary_keys_and_indexes():
    from src.url_content_scan.models import (
        UrlScanScrape,
        UrlScanSidebarCache,
        UrlScanUtterance,
        UrlScanWebRiskLookup,
    )

    assert [column.name for column in UrlScanScrape.__table__.primary_key.columns] == [
        "normalized_url",
        "tier",
    ]
    assert [column.name for column in UrlScanWebRiskLookup.__table__.primary_key.columns] == [
        "normalized_url"
    ]
    assert [column.name for column in UrlScanSidebarCache.__table__.primary_key.columns] == [
        "normalized_url"
    ]
    assert [column.name for column in UrlScanUtterance.__table__.primary_key.columns] == [
        "job_id",
        "utterance_id",
    ]

    assert "ix_url_scan_scrapes_expires_at" in {
        index.name for index in UrlScanScrape.__table__.indexes
    }
    assert "ix_url_scan_web_risk_lookups_expires_at" in {
        index.name for index in UrlScanWebRiskLookup.__table__.indexes
    }
    assert "ix_url_scan_sidebar_cache_expires_at" in {
        index.name for index in UrlScanSidebarCache.__table__.indexes
    }


@pytest.mark.unit
def test_url_scan_migration_declares_rls_and_skips_pg_cron():
    migration_path = (
        Path(__file__).resolve().parents[3]
        / "alembic"
        / "versions"
        / "task1487_03_url_scan_tables.py"
    )
    assert migration_path.exists()

    migration_text = migration_path.read_text()

    assert "ENABLE ROW LEVEL SECURITY" in migration_text
    assert "FORCE ROW LEVEL SECURITY" in migration_text
    assert "DATABASE_URL" in migration_text
    assert "current_user" in migration_text
    assert "rolbypassrls" in migration_text
    assert "WITH CHECK (true)" in migration_text

    for table_name in (
        "url_scan_state",
        "url_scan_section_slots",
        "url_scan_scrapes",
        "url_scan_utterances",
        "url_scan_web_risk_lookups",
        "url_scan_sidebar_cache",
    ):
        assert f"public.{table_name}" in migration_text

    assert "pg_cron" in migration_text
    assert "not migrated" in migration_text.lower()
