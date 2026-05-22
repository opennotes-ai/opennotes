"""Behavior-first tests for POST /api/keys/request (TASK-1651.04).

Tests use:
- testcontainers PostgreSQL for DB assertions (vibecheck_api_keys table)
- FakeEmailService stub (not a mock-everything pattern) to capture sends
- httpx.AsyncClient against the live ASGI app

ACs verified:
  1. 200 { ok: true } on success
  2. Invalid email → 400 invalid_email
  3. Email sent BEFORE DB write; send failure → 503, no DB write
  4. pg_advisory_xact_lock acquired + prior active row soft-deleted on success
  5. Row stores lowercased email, key_prefix, key_hash, created_at, NULL last_used_at, NULL deleted_at
  6. Email body contains plaintext key + 48h deletion notice
  7. No authorization required
  8. Per-IP rate limit (10/hour)
  9. Per-email rate limit (5/hour)
  10. email_validator with MX check + timeout path
"""
from __future__ import annotations

import asyncio
import hashlib
import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.main import app
from src.routes import api_keys as api_keys_route

_REAL_GETADDRINFO = socket.getaddrinfo

_API_KEYS_DDL = """
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE OR REPLACE FUNCTION extensions_uuidv7_stub()
RETURNS uuid AS $$
BEGIN
    RETURN gen_random_uuid();
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS public.vibecheck_api_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL,
    key_hash text NOT NULL UNIQUE,
    key_prefix text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    deleted_at timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vibecheck_api_keys_email_active
    ON public.vibecheck_api_keys (lower(email))
    WHERE deleted_at IS NULL;
"""


class FakeEmailService:
    """Stub EmailService that records sends without hitting SMTP."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raise_on_send: Exception | None = None

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> None:
        if self.raise_on_send is not None:
            raise self.raise_on_send
        self.calls.append(
            {
                "to_email": to_email,
                "subject": subject,
                "html_content": html_content,
                "text_content": text_content,
            }
        )


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container: PostgresContainer) -> AsyncIterator[Any]:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS public.vibecheck_api_keys CASCADE;")
        await conn.execute(_API_KEYS_DDL)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
def fake_email() -> FakeEmailService:
    return FakeEmailService()


@pytest.fixture
async def client(
    db_pool: Any,
    fake_email: FakeEmailService,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(api_keys_route, "EmailService", lambda _settings: fake_email)
    api_keys_route.reset_rate_limit_state_for_testing()
    app.state.db_pool = db_pool
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.state.db_pool = None
    api_keys_route.reset_rate_limit_state_for_testing()


async def _count_api_keys(pool: Any, email: str | None = None) -> int:
    async with pool.acquire() as conn:
        if email is None:
            return await conn.fetchval("SELECT COUNT(*) FROM public.vibecheck_api_keys")
        return await conn.fetchval(
            "SELECT COUNT(*) FROM public.vibecheck_api_keys WHERE lower(email) = lower($1)",
            email,
        )


async def _count_active_keys(pool: Any, email: str) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM public.vibecheck_api_keys "
            "WHERE lower(email) = lower($1) AND deleted_at IS NULL",
            email,
        )


async def _fetch_key_row(pool: Any, email: str) -> Any:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM public.vibecheck_api_keys "
            "WHERE lower(email) = lower($1) AND deleted_at IS NULL",
            email,
        )


def _stub_valid_email(monkeypatch: pytest.MonkeyPatch, normalised: str = "user@example.com") -> None:
    async def _fake_validate(email: str) -> str:
        return normalised

    monkeypatch.setattr(api_keys_route, "_validate_email", _fake_validate)


class TestHappyPath:
    async def test_returns_200_ok(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch)
        resp = await client.post("/api/keys/request", json={"email": "user@example.com"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    async def test_row_inserted_in_db(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "newuser@example.com")
        resp = await client.post("/api/keys/request", json={"email": "newuser@example.com"})
        assert resp.status_code == 200
        count = await _count_api_keys(db_pool, "newuser@example.com")
        assert count == 1

    async def test_email_sent(
        self,
        client: httpx.AsyncClient,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "sendtest@example.com")
        await client.post("/api/keys/request", json={"email": "sendtest@example.com"})
        assert len(fake_email.calls) == 1
        assert fake_email.calls[0]["to_email"] == "sendtest@example.com"

    async def test_no_auth_required(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "noauth@example.com")
        resp = await client.post(
            "/api/keys/request",
            json={"email": "noauth@example.com"},
        )
        assert resp.status_code == 200


class TestRowData:
    async def test_row_stores_lowercased_email(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "rowdata@example.com")
        await client.post("/api/keys/request", json={"email": "ROWDATA@example.com"})
        row = await _fetch_key_row(db_pool, "rowdata@example.com")
        assert row is not None
        assert row["email"] == "rowdata@example.com"

    async def test_row_has_key_prefix_and_hash(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "hashcheck@example.com")
        await client.post("/api/keys/request", json={"email": "hashcheck@example.com"})
        row = await _fetch_key_row(db_pool, "hashcheck@example.com")
        assert row is not None
        assert row["key_prefix"] is not None
        assert len(row["key_prefix"]) == 8
        assert row["key_hash"] is not None
        assert len(row["key_hash"]) == 64

    async def test_row_last_used_at_is_null(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "lastused@example.com")
        await client.post("/api/keys/request", json={"email": "lastused@example.com"})
        row = await _fetch_key_row(db_pool, "lastused@example.com")
        assert row is not None
        assert row["last_used_at"] is None

    async def test_row_deleted_at_is_null(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "deletedat@example.com")
        await client.post("/api/keys/request", json={"email": "deletedat@example.com"})
        row = await _fetch_key_row(db_pool, "deletedat@example.com")
        assert row is not None
        assert row["deleted_at"] is None

    async def test_key_hash_matches_sha256_of_full_key(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "hashverify@example.com")
        await client.post("/api/keys/request", json={"email": "hashverify@example.com"})
        row = await _fetch_key_row(db_pool, "hashverify@example.com")
        assert row is not None
        assert len(fake_email.calls) > 0
        email_text = fake_email.calls[-1]["text_content"] or ""
        full_key_line = [
            line.strip()
            for line in email_text.splitlines()
            if line.strip().startswith("opk_")
        ]
        assert full_key_line, "Full key must appear in the plaintext email body"
        full_key = full_key_line[0]
        expected_hash = hashlib.sha256(full_key.encode()).hexdigest()
        assert row["key_hash"] == expected_hash


class TestPriorKeyRotation:
    async def test_prior_active_key_soft_deleted_on_new_request(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "rotate@example.com")

        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO public.vibecheck_api_keys (email, key_hash, key_prefix, created_at) "
                "VALUES ($1, $2, $3, now() - interval '60 seconds')",
                "rotate@example.com",
                "oldhash1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
                "aabb1122",
            )

        await client.post("/api/keys/request", json={"email": "rotate@example.com"})

        total = await _count_api_keys(db_pool, "rotate@example.com")
        active = await _count_active_keys(db_pool, "rotate@example.com")
        assert total == 2
        assert active == 1

    async def test_three_requests_only_one_active(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "triple@example.com")

        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO public.vibecheck_api_keys (email, key_hash, key_prefix, created_at) "
                "VALUES ($1, $2, $3, now() - interval '120 seconds')",
                "triple@example.com",
                "triple1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
                "cc001122",
            )
            await conn.execute(
                "UPDATE public.vibecheck_api_keys SET deleted_at = now() "
                "WHERE email = $1 AND key_prefix = $2",
                "triple@example.com",
                "cc001122",
            )
            await conn.execute(
                "INSERT INTO public.vibecheck_api_keys (email, key_hash, key_prefix, created_at) "
                "VALUES ($1, $2, $3, now() - interval '60 seconds')",
                "triple@example.com",
                "triple2abcdef1234567890abcdef1234567890abcdef1234567890abcdef123456",
                "cc003344",
            )

        await client.post("/api/keys/request", json={"email": "triple@example.com"})

        active = await _count_active_keys(db_pool, "triple@example.com")
        assert active == 1


class TestEmailBody:
    async def test_email_contains_plaintext_key(
        self,
        client: httpx.AsyncClient,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "bodycheck@example.com")
        await client.post("/api/keys/request", json={"email": "bodycheck@example.com"})
        assert len(fake_email.calls) == 1
        text = fake_email.calls[0]["text_content"] or ""
        assert "opk_" in text

    async def test_email_contains_48h_deletion_warning(
        self,
        client: httpx.AsyncClient,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "warningcheck@example.com")
        await client.post("/api/keys/request", json={"email": "warningcheck@example.com"})
        assert len(fake_email.calls) == 1
        text = fake_email.calls[0]["text_content"] or ""
        assert "48 hours" in text
        assert "deleted" in text.lower()

    async def test_email_contains_use_example(
        self,
        client: httpx.AsyncClient,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "useexample@example.com")
        await client.post("/api/keys/request", json={"email": "useexample@example.com"})
        text = fake_email.calls[0]["text_content"] or ""
        assert "curl" in text or "Authorization" in text


class TestInvalidEmail:
    async def test_invalid_syntax_returns_400(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import email_validator

        async def _raise(_email: str) -> str:
            raise email_validator.EmailNotValidError("bad syntax")

        monkeypatch.setattr(api_keys_route, "_validate_email", _raise)
        resp = await client.post("/api/keys/request", json={"email": "not-an-email"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["error_code"] == "invalid_email"

    async def test_invalid_syntax_no_db_write(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import email_validator

        async def _raise(_email: str) -> str:
            raise email_validator.EmailNotValidError("bad syntax")

        monkeypatch.setattr(api_keys_route, "_validate_email", _raise)
        before = await _count_api_keys(db_pool)
        await client.post("/api/keys/request", json={"email": "not-an-email"})
        after = await _count_api_keys(db_pool)
        assert after == before

    async def test_invalid_syntax_no_email_sent(
        self,
        client: httpx.AsyncClient,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import email_validator

        async def _raise(_email: str) -> str:
            raise email_validator.EmailNotValidError("bad syntax")

        monkeypatch.setattr(api_keys_route, "_validate_email", _raise)
        await client.post("/api/keys/request", json={"email": "not-an-email"})
        assert len(fake_email.calls) == 0

    async def test_mx_failure_returns_400(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import email_validator

        async def _raise_mx(_email: str) -> str:
            raise email_validator.EmailNotValidError("DNS MX lookup failed")

        monkeypatch.setattr(api_keys_route, "_validate_email", _raise_mx)
        resp = await client.post(
            "/api/keys/request", json={"email": "user@nonexistent-mx-domain.invalid"}
        )
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "invalid_email"

    async def test_validation_timeout_returns_400(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def _timeout(_email: str) -> str:
            raise TimeoutError()

        monkeypatch.setattr(api_keys_route, "_validate_email", _timeout)
        resp = await client.post(
            "/api/keys/request", json={"email": "user@slow-dns.example.com"}
        )
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "invalid_email"


class TestEmailSendFailure:
    async def test_send_failure_returns_503(
        self,
        client: httpx.AsyncClient,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import aiosmtplib

        _stub_valid_email(monkeypatch, "sendfail@example.com")
        fake_email.raise_on_send = aiosmtplib.SMTPException("SMTP connection refused")
        resp = await client.post("/api/keys/request", json={"email": "sendfail@example.com"})
        assert resp.status_code == 503
        assert resp.json()["error_code"] == "email_send_failed"

    async def test_send_failure_no_db_write(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import aiosmtplib

        _stub_valid_email(monkeypatch, "sendfailnowrite@example.com")
        fake_email.raise_on_send = aiosmtplib.SMTPException("SMTP connection refused")
        before = await _count_api_keys(db_pool, "sendfailnowrite@example.com")
        await client.post("/api/keys/request", json={"email": "sendfailnowrite@example.com"})
        after = await _count_api_keys(db_pool, "sendfailnowrite@example.com")
        assert after == before

    async def test_send_failure_logs_exception_with_hashed_email(
        self,
        client: httpx.AsyncClient,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import aiosmtplib

        _stub_valid_email(monkeypatch, "logcheck@example.com")
        fake_email.raise_on_send = aiosmtplib.SMTPException("forced failure")
        with caplog.at_level("ERROR", logger="src.routes.api_keys"):
            resp = await client.post("/api/keys/request", json={"email": "logcheck@example.com"})
        assert resp.status_code == 503
        hashed = hashlib.sha256(b"logcheck@example.com").hexdigest()[:16]
        assert any(hashed in r.getMessage() for r in caplog.records), (
            f"expected hashed email {hashed} in ERROR logs; got: {[r.getMessage() for r in caplog.records]}"
        )
        assert all("logcheck@example.com" not in r.getMessage() for r in caplog.records), (
            "raw email leaked into logs"
        )


class _FakePoolFailOnSecondAcquire:
    """Proxy pool that passes through the first acquire() and raises PostgresError on the second.

    The first acquire() is the advisory-lock connection; the second is the write transaction.
    asyncpg.Pool.acquire() is read-only so we wrap the pool instead of patching it.
    """

    def __init__(self, real_pool: Any) -> None:
        self._real_pool = real_pool
        self._call_count = 0

    def acquire(self) -> _ProxyCtx:
        self._call_count += 1
        should_fail = self._call_count > 1
        real_ctx = self._real_pool.acquire()
        return _ProxyCtx(real_ctx, should_fail)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real_pool, name)


class _ProxyCtx:
    def __init__(self, real_ctx: Any, should_fail: bool) -> None:
        self._real_ctx = real_ctx
        self._should_fail = should_fail

    async def __aenter__(self) -> Any:
        if self._should_fail:
            raise asyncpg.PostgresError("forced db error")
        return await self._real_ctx.__aenter__()

    async def __aexit__(self, *args: Any) -> None:
        if not self._should_fail:
            await self._real_ctx.__aexit__(*args)


class TestDbWriteFailure:
    async def test_db_write_failure_returns_503(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "dbfail@example.com")
        fake_pool = _FakePoolFailOnSecondAcquire(db_pool)
        monkeypatch.setattr(api_keys_route, "_get_db_pool", lambda _req: fake_pool)
        resp = await client.post("/api/keys/request", json={"email": "dbfail@example.com"})
        assert resp.status_code == 503
        assert resp.json()["error_code"] == "db_write_failed"

    async def test_db_write_failure_logs_exception_with_hashed_email(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _stub_valid_email(monkeypatch, "dblogcheck@example.com")
        fake_pool = _FakePoolFailOnSecondAcquire(db_pool)
        monkeypatch.setattr(api_keys_route, "_get_db_pool", lambda _req: fake_pool)
        with caplog.at_level("ERROR", logger="src.routes.api_keys"):
            resp = await client.post("/api/keys/request", json={"email": "dblogcheck@example.com"})
        assert resp.status_code == 503
        hashed = hashlib.sha256(b"dblogcheck@example.com").hexdigest()[:16]
        assert any(hashed in r.getMessage() for r in caplog.records), (
            f"expected hashed email {hashed} in ERROR logs; got: {[r.getMessage() for r in caplog.records]}"
        )
        assert all("dblogcheck@example.com" not in r.getMessage() for r in caplog.records), (
            "raw email leaked into logs"
        )


class TestRateLimiting:
    async def test_ip_rate_limit_triggers_on_11th_request(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        email_counter = {"n": 0}

        async def _unique_email(email: str) -> str:
            email_counter["n"] += 1
            return f"iplimit{email_counter['n']}@example.com"

        monkeypatch.setattr(api_keys_route, "_validate_email", _unique_email)

        responses = []
        for i in range(12):
            resp = await client.post(
                "/api/keys/request",
                json={"email": f"iplimit{i}@example.com"},
            )
            responses.append(resp.status_code)

        assert 429 in responses
        assert responses.index(429) >= 10

    async def test_email_rate_limit_triggers_on_6th_request(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        call_count = {"n": 0}

        async def _same_email(_email: str) -> str:
            call_count["n"] += 1
            return "emaillimit@example.com"

        monkeypatch.setattr(api_keys_route, "_validate_email", _same_email)

        responses = []
        for _ in range(7):
            resp = await client.post(
                "/api/keys/request",
                json={"email": "emaillimit@example.com"},
            )
            responses.append(resp.status_code)

        assert 429 in responses
        assert responses.index(429) >= 5


class TestConcurrentRequestsLockOrdering:
    """P0 — lock must be acquired BEFORE email send so concurrent requests
    for the same address cannot both slip through to the send step."""

    async def test_only_one_email_sent_on_concurrent_requests(
        self,
        db_pool: Any,
        fake_email: FakeEmailService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(api_keys_route, "EmailService", lambda _settings: fake_email)
        api_keys_route.reset_rate_limit_state_for_testing()
        app.state.db_pool = db_pool

        _stub_valid_email(monkeypatch, "concurrent@example.com")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            results = await asyncio.gather(
                c.post("/api/keys/request", json={"email": "concurrent@example.com"}),
                c.post("/api/keys/request", json={"email": "concurrent@example.com"}),
                c.post("/api/keys/request", json={"email": "concurrent@example.com"}),
            )

        app.state.db_pool = None
        api_keys_route.reset_rate_limit_state_for_testing()

        status_codes = [r.status_code for r in results]
        assert 200 in status_codes, "At least one request should succeed"

        assert len(fake_email.calls) == 1, (
            f"Expected exactly 1 email send but got {len(fake_email.calls)}. "
            "The advisory lock must be acquired before email send."
        )

        active = await _count_active_keys(db_pool, "concurrent@example.com")
        assert active == 1, "Only one active key row should exist after concurrent requests"


class TestAdvisoryLockPresence:
    async def test_pg_advisory_lock_in_route_code(self) -> None:
        import inspect

        source = inspect.getsource(api_keys_route)
        assert "pg_advisory_lock" in source, (
            "Route must call pg_advisory_lock to serialize concurrent requests per email"
        )

    async def test_update_soft_deletes_prior_active_rows(
        self,
        client: httpx.AsyncClient,
        db_pool: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_valid_email(monkeypatch, "locktest@example.com")

        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO public.vibecheck_api_keys (email, key_hash, key_prefix, created_at) "
                "VALUES ($1, $2, $3, now() - interval '60 seconds')",
                "locktest@example.com",
                "existinghash1234567890abcdef1234567890abcdef1234567890abcdef12345678",
                "aabbccdd",
            )

        active_before = await _count_active_keys(db_pool, "locktest@example.com")
        assert active_before == 1

        await client.post("/api/keys/request", json={"email": "locktest@example.com"})

        active_after = await _count_active_keys(db_pool, "locktest@example.com")
        assert active_after == 1

        total = await _count_api_keys(db_pool, "locktest@example.com")
        assert total == 2


class TestIPKeyXFF:
    """P1.15 — rate-limit key must use X-Forwarded-For, not request.client.host."""

    def test_xff_single_hop_used(self) -> None:
        from unittest.mock import MagicMock

        req = MagicMock()
        req.headers = {"x-forwarded-for": "1.2.3.4"}
        req.client = MagicMock()
        req.client.host = "10.0.0.1"

        key = api_keys_route._ip_key(req)
        assert "1.2.3.4" in key, f"XFF left-most IP must appear in rate-limit key, got: {key}"
        assert "10.0.0.1" not in key, "Internal LB IP must not appear in the key"

    def test_xff_multi_hop_uses_leftmost(self) -> None:
        from unittest.mock import MagicMock

        req = MagicMock()
        req.headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1, 10.0.0.2"}
        req.client = MagicMock()
        req.client.host = "172.16.0.1"

        key = api_keys_route._ip_key(req)
        assert "203.0.113.5" in key, f"Left-most IP must be used; got: {key}"

    def test_no_xff_falls_back_to_client_host(self) -> None:
        from unittest.mock import MagicMock

        req = MagicMock()
        req.headers = {}
        req.client = MagicMock()
        req.client.host = "9.9.9.9"

        key = api_keys_route._ip_key(req)
        assert "9.9.9.9" in key, f"Fallback to request.client.host; got: {key}"


class TestNarrowExceptionHandling:
    """P1.16 — only EmailNotValidError and TimeoutError must be caught as 400;
    unexpected exceptions must propagate (not be silenced as invalid_email)."""

    async def test_unexpected_exception_propagates_not_swallowed_as_400(
        self,
        db_pool: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(api_keys_route, "EmailService", lambda _settings: FakeEmailService())
        api_keys_route.reset_rate_limit_state_for_testing()
        app.state.db_pool = db_pool

        async def _crash(_email: str) -> str:
            raise ValueError("unexpected internal error")

        monkeypatch.setattr(api_keys_route, "_validate_email", _crash)

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/api/keys/request", json={"email": "user@example.com"})

        app.state.db_pool = None
        api_keys_route.reset_rate_limit_state_for_testing()

        assert resp.status_code == 500, (
            f"Unexpected exceptions must yield 500, not silenced as 400, got {resp.status_code}"
        )

    async def test_email_not_valid_returns_400(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import email_validator

        async def _raise(_email: str) -> str:
            raise email_validator.EmailNotValidError("bad domain")

        monkeypatch.setattr(api_keys_route, "_validate_email", _raise)
        resp = await client.post("/api/keys/request", json={"email": "bad@bad"})
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "invalid_email"

    async def test_timeout_error_returns_400(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def _timeout(_email: str) -> str:
            raise TimeoutError()

        monkeypatch.setattr(api_keys_route, "_validate_email", _timeout)
        resp = await client.post("/api/keys/request", json={"email": "user@slow.com"})
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "invalid_email"
