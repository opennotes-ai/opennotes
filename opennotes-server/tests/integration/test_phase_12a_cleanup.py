"""Phase 1.2a — post-backfill data cleanup tests."""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_003d_deactivates_empty_scope_sa_keys(db_session):
    """Empty-scope keys held by agent/system principals are deactivated."""
    from tests.fixtures.principal_factory import make_agent_user, make_api_key, make_human_user

    agent = await make_agent_user(db_session)
    key = await make_api_key(db_session, agent, scopes=[])
    assert key.is_active is True

    human = await make_human_user(db_session)
    human_key = await make_api_key(db_session, human, scopes=[])

    await db_session.commit()

    await db_session.execute(
        text("""
        UPDATE api_keys SET is_active = FALSE
        WHERE user_id IN (SELECT id FROM users WHERE principal_type IN ('agent','system'))
          AND (scopes IS NULL OR jsonb_array_length(scopes) = 0)
          AND is_active = TRUE
    """)
    )
    await db_session.commit()

    await db_session.refresh(key)
    await db_session.refresh(human_key)
    assert key.is_active is False
    assert human_key.is_active is True


@pytest.mark.asyncio
async def test_003d_system_principal_keys_also_deactivated(db_session):
    """Empty-scope keys held by system principals are also deactivated."""
    from tests.fixtures.principal_factory import make_api_key, make_system_user

    system = await make_system_user(db_session)
    key = await make_api_key(db_session, system, scopes=[])
    assert key.is_active is True

    await db_session.commit()

    await db_session.execute(
        text("""
        UPDATE api_keys SET is_active = FALSE
        WHERE user_id IN (SELECT id FROM users WHERE principal_type IN ('agent','system'))
          AND (scopes IS NULL OR jsonb_array_length(scopes) = 0)
          AND is_active = TRUE
    """)
    )
    await db_session.commit()

    await db_session.refresh(key)
    assert key.is_active is False


@pytest.mark.asyncio
async def test_003d_nonempty_scope_keys_untouched(db_session):
    """Agent keys with non-empty scopes are NOT deactivated."""
    from tests.fixtures.principal_factory import make_agent_user, make_api_key

    agent = await make_agent_user(db_session)
    key_with_scopes = await make_api_key(db_session, agent, scopes=["notes:read"])
    assert key_with_scopes.is_active is True

    await db_session.commit()

    await db_session.execute(
        text("""
        UPDATE api_keys SET is_active = FALSE
        WHERE user_id IN (SELECT id FROM users WHERE principal_type IN ('agent','system'))
          AND (scopes IS NULL OR jsonb_array_length(scopes) = 0)
          AND is_active = TRUE
    """)
    )
    await db_session.commit()

    await db_session.refresh(key_with_scopes)
    assert key_with_scopes.is_active is True


@pytest.mark.asyncio
async def test_003d_idempotent(db_session):
    """Running 003d SQL twice produces the same result."""
    from tests.fixtures.principal_factory import make_agent_user, make_api_key

    agent = await make_agent_user(db_session)
    key = await make_api_key(db_session, agent, scopes=[])
    await db_session.commit()

    sql = text("""
        UPDATE api_keys SET is_active = FALSE
        WHERE user_id IN (SELECT id FROM users WHERE principal_type IN ('agent','system'))
          AND (scopes IS NULL OR jsonb_array_length(scopes) = 0)
          AND is_active = TRUE
    """)
    await db_session.execute(sql)
    await db_session.commit()
    await db_session.execute(sql)
    await db_session.commit()

    await db_session.refresh(key)
    assert key.is_active is False
