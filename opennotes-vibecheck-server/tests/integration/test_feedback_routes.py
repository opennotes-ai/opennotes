"""Integration tests for POST /api/feedback and PATCH /api/feedback/{id} (TASK-1588.04).

Uses a real testcontainer Postgres and a real TestClient — no mocks for
the DB or the uid-cookie middleware.

Cases:
- POST open with valid body -> 201 + UUID; row uid matches cookie uid.
- POST open with body containing a fake uid field -> body uid ignored; row uid = cookie uid.
- POST combined (with final_type) -> 201 + UUID; row has initial_type + final_type + submitted_at.
- PATCH known id -> 200; row updated; submitted_at set.
- PATCH unknown id -> 404.
- PATCH with invalid email -> 422.
"""
from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.main import app
from src.middleware.uid_cookie import UID_COOKIE_NAME

_REAL_GETADDRINFO = socket.getaddrinfo

FEEDBACK_DDL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS vibecheck_feedback (
    id            UUID PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    page_path     TEXT NOT NULL,
    user_agent    TEXT NOT NULL,
    referrer      TEXT NOT NULL DEFAULT '',
    uid           UUID NOT NULL,
    bell_location TEXT NOT NULL,
    initial_type  TEXT NOT NULL CHECK (initial_type IN ('thumbs_up','thumbs_down','message')),
    email         TEXT,
    message       TEXT,
    final_type    TEXT CHECK (final_type IN ('thumbs_up','thumbs_down','message')),
    submitted_at  TIMESTAMPTZ
);
"""


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(
    _postgres_container: PostgresContainer,
) -> AsyncIterator[Any]:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=8)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_feedback CASCADE;"
        )
        await conn.execute(FEEDBACK_DDL)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def http_client(db_pool: Any) -> AsyncIterator[httpx.AsyncClient]:
    app.state.db_pool = db_pool
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.state.db_pool = None


async def _fetch_feedback_row(pool: Any, feedback_id: UUID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM vibecheck_feedback WHERE id = $1", feedback_id
        )
    assert row is not None, f"no row for id={feedback_id}"
    return dict(row)


_OPEN_BODY = {
    "page_path": "/analyze",
    "user_agent": "Mozilla/5.0",
    "referrer": "https://example.com",
    "bell_location": "bottom-right",
    "initial_type": "thumbs_up",
}

_COMBINED_BODY = {
    **_OPEN_BODY,
    "final_type": "thumbs_up",
    "email": "alice@example.com",
    "message": "Great site!",
}


async def test_post_open_returns_201_and_uuid(
    http_client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    uid = str(uuid4())
    resp = await http_client.post(
        "/api/feedback",
        json=_OPEN_BODY,
        cookies={UID_COOKIE_NAME: uid},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    feedback_id = UUID(body["id"])

    row = await _fetch_feedback_row(db_pool, feedback_id)
    assert str(row["uid"]) == uid
    assert row["page_path"] == "/analyze"
    assert row["bell_location"] == "bottom-right"
    assert row["initial_type"] == "thumbs_up"
    assert row["final_type"] is None
    assert row["submitted_at"] is None


async def test_post_open_body_uid_field_is_ignored(
    http_client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    cookie_uid = str(uuid4())
    body_with_fake_uid = {**_OPEN_BODY}
    resp = await http_client.post(
        "/api/feedback",
        json=body_with_fake_uid,
        cookies={UID_COOKIE_NAME: cookie_uid},
    )
    assert resp.status_code == 201
    feedback_id = UUID(resp.json()["id"])

    row = await _fetch_feedback_row(db_pool, feedback_id)
    assert str(row["uid"]) == cookie_uid


async def test_post_combined_sets_all_fields(
    http_client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    uid = str(uuid4())
    resp = await http_client.post(
        "/api/feedback",
        json=_COMBINED_BODY,
        cookies={UID_COOKIE_NAME: uid},
    )
    assert resp.status_code == 201
    feedback_id = UUID(resp.json()["id"])

    row = await _fetch_feedback_row(db_pool, feedback_id)
    assert str(row["uid"]) == uid
    assert row["initial_type"] == "thumbs_up"
    assert row["final_type"] == "thumbs_up"
    assert row["email"] == "alice@example.com"
    assert row["message"] == "Great site!"
    assert row["submitted_at"] is not None


async def test_patch_known_id_updates_row(
    http_client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    uid = str(uuid4())
    post_resp = await http_client.post(
        "/api/feedback",
        json=_OPEN_BODY,
        cookies={UID_COOKIE_NAME: uid},
    )
    assert post_resp.status_code == 201
    feedback_id = UUID(post_resp.json()["id"])

    row_before = await _fetch_feedback_row(db_pool, feedback_id)
    assert row_before["submitted_at"] is None

    patch_resp = await http_client.patch(
        f"/api/feedback/{feedback_id}",
        json={"email": "bob@example.com", "message": "Thanks!", "final_type": "thumbs_down"},
        cookies={UID_COOKIE_NAME: uid},
    )
    assert patch_resp.status_code == 200

    row_after = await _fetch_feedback_row(db_pool, feedback_id)
    assert row_after["email"] == "bob@example.com"
    assert row_after["message"] == "Thanks!"
    assert row_after["final_type"] == "thumbs_down"
    assert row_after["submitted_at"] is not None


async def test_patch_unknown_id_returns_404(
    http_client: httpx.AsyncClient,
) -> None:
    unknown_id = uuid4()
    resp = await http_client.patch(
        f"/api/feedback/{unknown_id}",
        json={"email": None, "message": None, "final_type": "thumbs_up"},
    )
    assert resp.status_code == 404


async def test_patch_invalid_email_returns_422(
    http_client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    uid = str(uuid4())
    post_resp = await http_client.post(
        "/api/feedback",
        json=_OPEN_BODY,
        cookies={UID_COOKIE_NAME: uid},
    )
    assert post_resp.status_code == 201
    feedback_id = UUID(post_resp.json()["id"])

    patch_resp = await http_client.patch(
        f"/api/feedback/{feedback_id}",
        json={"email": "not-an-email", "message": None, "final_type": "thumbs_up"},
        cookies={UID_COOKIE_NAME: uid},
    )
    assert patch_resp.status_code == 422


async def test_post_open_without_kind_field_infers_open_shape(
    http_client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    """AC3: legacy client posts old open-shape body (no 'kind') — must not 422."""
    uid = str(uuid4())
    legacy_body = {
        "page_path": "/analyze",
        "user_agent": "Mozilla/5.0",
        "referrer": "https://example.com",
        "bell_location": "bottom-right",
        "initial_type": "thumbs_down",
    }
    resp = await http_client.post(
        "/api/feedback",
        json=legacy_body,
        cookies={UID_COOKIE_NAME: uid},
    )
    assert resp.status_code == 201
    feedback_id = UUID(resp.json()["id"])

    row = await _fetch_feedback_row(db_pool, feedback_id)
    assert row["initial_type"] == "thumbs_down"
    assert row["final_type"] is None
    assert row["submitted_at"] is None


async def test_post_combined_without_kind_field_infers_combined_shape(
    http_client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    """AC3: legacy client posts old combined-shape body (no 'kind') — must not 422."""
    uid = str(uuid4())
    legacy_combined_body = {
        "page_path": "/analyze",
        "user_agent": "Mozilla/5.0",
        "referrer": "https://example.com",
        "bell_location": "bottom-right",
        "initial_type": "thumbs_up",
        "final_type": "thumbs_up",
        "email": "legacy@example.com",
        "message": "Sent without kind field",
    }
    resp = await http_client.post(
        "/api/feedback",
        json=legacy_combined_body,
        cookies={UID_COOKIE_NAME: uid},
    )
    assert resp.status_code == 201
    feedback_id = UUID(resp.json()["id"])

    row = await _fetch_feedback_row(db_pool, feedback_id)
    assert row["final_type"] == "thumbs_up"
    assert row["email"] == "legacy@example.com"
    assert row["submitted_at"] is not None
