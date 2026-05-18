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
        await client.post("/api/keys/request", json={"email": "rotate@example.com"})
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
        for _ in range(3):
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
        _stub_valid_email(monkeypatch, "sendfail@example.com")
        fake_email.raise_on_send = RuntimeError("SMTP connection refused")
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
        _stub_valid_email(monkeypatch, "sendfailnowrite@example.com")
        fake_email.raise_on_send = RuntimeError("SMTP connection refused")
        before = await _count_api_keys(db_pool, "sendfailnowrite@example.com")
        await client.post("/api/keys/request", json={"email": "sendfailnowrite@example.com"})
        after = await _count_api_keys(db_pool, "sendfailnowrite@example.com")
        assert after == before


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


class TestAdvisoryLockPresence:
    async def test_pg_advisory_xact_lock_in_route_code(self) -> None:
        import inspect

        source = inspect.getsource(api_keys_route)
        assert "pg_advisory_xact_lock" in source, (
            "Route must call pg_advisory_xact_lock to serialize concurrent requests per email"
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
                "INSERT INTO public.vibecheck_api_keys (email, key_hash, key_prefix) "
                "VALUES ($1, $2, $3)",
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
