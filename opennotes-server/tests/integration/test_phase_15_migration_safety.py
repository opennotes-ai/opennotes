"""Phase 1.5 — migration safety regression tests.

Static text-based assertions on migration files that have already run on
internal DBs. These guard against regression on fresh-DB runs (CI, dev,
future deploys). The migrations themselves cannot be re-executed cleanly
in unit tests, so we assert on file content.

Refs:
  - ADR-001 UUIDv7 standardization
  - TASK-1451.15 (PR #368 code-review CRITICAL findings)
"""

from pathlib import Path

import pytest

ALEMBIC_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _read_migration(name: str) -> str:
    path = ALEMBIC_VERSIONS / name
    assert path.exists(), f"Migration file not found: {path}"
    return path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_phase_105b_uses_uuidv7():
    """task1451_02b orphan-repair INSERT must use uuidv7() per ADR-001."""
    src = _read_migration("task1451_02b_phase_105b_repair_orphan_profiles.py")
    assert "uuidv7()" in src, "Expected uuidv7() in orphan-repair INSERT"
    assert "gen_random_uuid()" not in src, (
        "ADR-001 forbids gen_random_uuid() for new primary keys; use uuidv7()"
    )


@pytest.mark.unit
def test_phase_105b_full_provider_user_id_in_username():
    """Synthetic username must include the full provider_user_id, not a substring.

    Discord snowflakes share leading digits over short windows, so
    substring(provider_user_id, 1, 8) collides on users.username UNIQUE.
    The full ID is unique by construction.
    """
    src = _read_migration("task1451_02b_phase_105b_repair_orphan_profiles.py")
    assert "substring(ui.provider_user_id, 1, 8)" not in src, (
        "Substring of Discord snowflake collides; use full provider_user_id"
    )
    assert "'orphan-' || ui.provider_user_id" in src, (
        "Expected synthetic username to concatenate full provider_user_id"
    )


@pytest.mark.unit
def test_phase_11b_no_silent_else_human():
    """phase_11b must fail loud on NULL is_service_account, not silently map to 'human'.

    The previous CASE had an unconditional ELSE 'human', which silently
    misclassified NULL is_service_account rows. The fix replaces that ELSE
    with an explicit WHEN is_service_account = FALSE plus a pre-UPDATE
    NULL count guard that raises RuntimeError.
    """
    src = _read_migration("a9476c9a7841_phase_11b_backfill_principal_type.py")
    assert "ELSE 'human'" not in src, (
        "Silent ELSE 'human' misclassifies NULL is_service_account rows"
    )
    assert "WHEN is_service_account = FALSE THEN 'human'" in src, (
        "Expected explicit WHEN is_service_account = FALSE branch"
    )
    assert "RuntimeError" in src, (
        "Expected fail-loud RuntimeError guard for NULL is_service_account"
    )
