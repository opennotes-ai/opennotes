"""Tests for UidCookieMiddleware and get_uid helper.

Behavior tested:
1. First request (no cookie) → response sets httpOnly vibecheck_uid cookie with a valid UUID v7.
2. Second request reusing the cookie → no Set-Cookie header; route returns the same uid.
3. Request with a malformed cookie → middleware regenerates a UUID v7 and sets Set-Cookie.
4. Concurrent independent requests do not leak uid state across them.

All tests use a real TestClient against a minimal FastAPI app with the middleware
mounted — no mocks for the middleware itself.
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.middleware.uid_cookie import (
    UID_COOKIE_MAX_AGE,
    UID_COOKIE_NAME,
    UidCookieMiddleware,
    get_uid,
)


def _make_app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(UidCookieMiddleware)

    @test_app.get("/uid")
    async def uid_endpoint(request: Request) -> dict[str, str]:
        return {"uid": str(get_uid(request))}

    return test_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=True)


def test_first_request_sets_httponly_uuid7_cookie(client: TestClient) -> None:
    resp = client.get("/uid", cookies={})
    assert resp.status_code == 200

    set_cookie = resp.headers.get("set-cookie", "")
    assert UID_COOKIE_NAME in set_cookie, "Expected Set-Cookie header with vibecheck_uid"
    assert "HttpOnly" in set_cookie, "Cookie must be httpOnly"

    cookie_value = resp.cookies.get(UID_COOKIE_NAME)
    assert cookie_value is not None, "vibecheck_uid cookie must be present in response"

    uid = UUID(cookie_value)
    assert uid.version == 7, f"Expected UUID v7, got version {uid.version}"

    body_uid = UUID(resp.json()["uid"])
    assert body_uid == uid, "Route uid must match the cookie value"


def test_second_request_with_cookie_no_set_cookie(client: TestClient) -> None:
    first = client.get("/uid", cookies={})
    existing_uid = first.cookies.get(UID_COOKIE_NAME)
    assert existing_uid is not None

    second = client.get("/uid", cookies={UID_COOKIE_NAME: existing_uid})
    assert "set-cookie" not in second.headers, "Should not set cookie when valid cookie present"
    assert second.json()["uid"] == existing_uid, "Route must return the same uid"


def test_malformed_cookie_regenerates_uuid7(client: TestClient) -> None:
    resp = client.get("/uid", cookies={UID_COOKIE_NAME: "garbage-not-a-uuid"})
    assert resp.status_code == 200

    set_cookie = resp.headers.get("set-cookie", "")
    assert UID_COOKIE_NAME in set_cookie, "Expected Set-Cookie for malformed cookie"
    assert "HttpOnly" in set_cookie

    new_value = resp.cookies.get(UID_COOKIE_NAME)
    assert new_value is not None
    assert new_value != "garbage-not-a-uuid"

    uid = UUID(new_value)
    assert uid.version == 7


def test_concurrent_requests_have_independent_uids() -> None:
    app = _make_app()

    with TestClient(app, raise_server_exceptions=True) as c1:
        with TestClient(app, raise_server_exceptions=True) as c2:
            r1 = c1.get("/uid", cookies={})
            r2 = c2.get("/uid", cookies={})

    uid1 = UUID(r1.cookies[UID_COOKIE_NAME])
    uid2 = UUID(r2.cookies[UID_COOKIE_NAME])

    assert uid1 != uid2, "Independent requests must get independent uids"
    assert uid1.version == 7
    assert uid2.version == 7


def test_cookie_max_age_is_two_years() -> None:
    resp = TestClient(_make_app()).get("/uid", cookies={})
    set_cookie = resp.headers.get("set-cookie", "")
    assert f"Max-Age={UID_COOKIE_MAX_AGE}" in set_cookie
