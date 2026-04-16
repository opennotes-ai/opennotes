"""TASK-1451.12 — Phase 15a backfill must not include api-keys:create.

Codex xhigh review caught that migration 470bb55476a0 backfilled NULL-scope
active API keys with a "conservative" set that incorrectly included
``api-keys:create`` (a RESTRICTED scope per ``src/auth/models.py``). Backfilled
legacy keys could then mint arbitrary scoped keys via
``/api/v2/admin/api-keys``.

Two safeguards under test:

1. The Phase 15a migration module's ``_CONSERVATIVE_SCOPES`` constant must NOT
   contain ``api-keys:create``.
2. A forward-repair migration (79a8f0ad842e) must rewrite any rows already
   backfilled with the buggy 11-scope array to the corrected 10-scope array,
   while leaving other shapes untouched. The repair must also be idempotent.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import text

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE_15A_PATH = (
    _REPO_ROOT / "alembic" / "versions" / "470bb55476a0_phase_15a_backfill_null_scopes.py"
)


def _load_phase_15a():
    spec = importlib.util.spec_from_file_location(
        "_phase_15a_backfill_null_scopes_for_test", _PHASE_15A_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_phase_15a_conservative_scopes_excludes_api_keys_create():
    module = _load_phase_15a()
    assert "api-keys:create" not in module._CONSERVATIVE_SCOPES, (
        "Phase 15a backfill must not grant api-keys:create — that scope is "
        "RESTRICTED and would let backfilled legacy keys mint new scoped keys."
    )


_OLD_BUGGY_SCOPES = sorted(
    [
        "simulations:read",
        "requests:read",
        "requests:write",
        "notes:read",
        "notes:write",
        "notes:delete",
        "ratings:write",
        "profiles:read",
        "community-servers:read",
        "moderation-actions:read",
        "api-keys:create",
    ]
)
_NEW_CONSERVATIVE = [s for s in _OLD_BUGGY_SCOPES if s != "api-keys:create"]


async def _seed_user(db_session, username: str) -> str:
    await db_session.execute(
        text(
            """
            INSERT INTO users (id, username, email, hashed_password, is_active, created_at, updated_at)
            VALUES (gen_random_uuid(), :u, :e, 'fakehash', true, NOW(), NOW())
            ON CONFLICT DO NOTHING
            """
        ),
        {"u": username, "e": f"{username}@test.example"},
    )
    await db_session.flush()
    result = await db_session.execute(
        text("SELECT id FROM users WHERE username = :u"), {"u": username}
    )
    return str(result.scalar_one())


async def _insert_key(db_session, user_id: str, name: str, scopes_json: str) -> None:
    await db_session.execute(
        text(
            """
            INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, scopes, is_active, created_at)
            VALUES (gen_random_uuid(), :uid, :name, :h, 'ak_', CAST(:scopes AS jsonb), true, NOW())
            """
        ),
        {
            "uid": user_id,
            "name": name,
            "h": f"hash-{name}",
            "scopes": scopes_json,
        },
    )
    await db_session.flush()


def _repair_sql() -> str:
    return (
        "UPDATE api_keys SET scopes = CAST(:new AS jsonb) WHERE scopes::jsonb = CAST(:old AS jsonb)"
    )


@pytest.mark.asyncio
async def test_repair_migration_strips_api_keys_create_from_buggy_rows(db_session):
    user_id = await _seed_user(db_session, "phase15a-repair-buggy")
    await _insert_key(db_session, user_id, "buggy-backfilled", json.dumps(_OLD_BUGGY_SCOPES))

    await db_session.execute(
        text(_repair_sql()),
        {"new": json.dumps(_NEW_CONSERVATIVE), "old": json.dumps(_OLD_BUGGY_SCOPES)},
    )
    await db_session.flush()

    result = await db_session.execute(
        text("SELECT scopes FROM api_keys WHERE name = 'buggy-backfilled'")
    )
    scopes = result.scalar_one()
    assert "api-keys:create" not in scopes
    for kept in _NEW_CONSERVATIVE:
        assert kept in scopes


@pytest.mark.asyncio
async def test_repair_migration_leaves_other_scope_shapes_untouched(db_session):
    user_id = await _seed_user(db_session, "phase15a-repair-untouched")
    benign_scopes = ["notes:read"]
    await _insert_key(db_session, user_id, "benign-key", json.dumps(benign_scopes))
    legitimate_admin = ["api-keys:create", "notes:read"]
    await _insert_key(db_session, user_id, "legitimate-admin-key", json.dumps(legitimate_admin))

    await db_session.execute(
        text(_repair_sql()),
        {"new": json.dumps(_NEW_CONSERVATIVE), "old": json.dumps(_OLD_BUGGY_SCOPES)},
    )
    await db_session.flush()

    benign_result = await db_session.execute(
        text("SELECT scopes FROM api_keys WHERE name = 'benign-key'")
    )
    assert benign_result.scalar_one() == benign_scopes

    admin_result = await db_session.execute(
        text("SELECT scopes FROM api_keys WHERE name = 'legitimate-admin-key'")
    )
    assert admin_result.scalar_one() == legitimate_admin


@pytest.mark.asyncio
async def test_repair_migration_is_idempotent(db_session):
    user_id = await _seed_user(db_session, "phase15a-repair-idem")
    await _insert_key(db_session, user_id, "idem-buggy", json.dumps(_OLD_BUGGY_SCOPES))

    for _ in range(2):
        await db_session.execute(
            text(_repair_sql()),
            {
                "new": json.dumps(_NEW_CONSERVATIVE),
                "old": json.dumps(_OLD_BUGGY_SCOPES),
            },
        )
        await db_session.flush()

    result = await db_session.execute(text("SELECT scopes FROM api_keys WHERE name = 'idem-buggy'"))
    scopes = result.scalar_one()
    assert "api-keys:create" not in scopes
    assert sorted(scopes) == _NEW_CONSERVATIVE
