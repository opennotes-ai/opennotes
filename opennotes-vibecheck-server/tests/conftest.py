"""Shared pytest fixtures.

- Autouse `_stub_dns`: return a public-looking IP (8.8.8.8) for any hostname
  lookup so tests using fake hostnames like `blocked.example.com` survive the
  SSRF validator added to `src.routes.frame`. Production still does real DNS;
  the stub lives only in the test process.

- `VIBECHECK_JOBS_DDL` (module-level constant): the canonical CREATE TABLE
  block for `vibecheck_jobs` reused by every testcontainer-Postgres unit /
  jobs / routes test. If you add a column to `src/cache/schema.sql`
  `vibecheck_jobs`, update this constant in ONE place and every test picks
  it up. The TASK-1490.03 audit script is the production drift detector;
  this fixture intentionally does not run the schema.sql `exec_sql`
  bootstrap or advisory lock because unit fixtures apply DDL directly. The
  integration suite has its own copy in
  `tests/integration/conftest.py` (it embeds the sweeper function and
  `IF NOT EXISTS` guards, which is a different shape) — keep both in sync
  by hand when columns change.

- Cross-cutting helpers used by `tests/unit/test_concurrency.py`,
  `tests/unit/test_integration_surface.py`, and `tests/integration/`:
    * `fake_firecrawl_client`: a dependency-free stand-in for
      `FirecrawlClient` whose `scrape(...)` returns a programmable
      `ScrapeResult` and whose call log lets tests assert the cache-rescue
      contract (second submit must NOT call `scrape`).
    * `fake_gemini_runner`: a fake pydantic-ai-style agent runner that
      returns a programmable `UtterancesPayload` so the orchestrator's
      extractor seam can be patched without touching Vertex AI.
    * `oidc_headers`: builds the Authorization header the
      `verify_cloud_tasks_oidc` dependency expects when the test has
      installed an OIDC verify mock.
    * `install_oidc_mock`: monkeypatches the OIDC verifier to a happy-path
      claim payload bound to `VIBECHECK_SERVER_URL` /
      `VIBECHECK_TASKS_ENQUEUER_SA`.

The DB-backed pieces (testcontainers Postgres, schema apply) live in the
suite-local conftests under `tests/integration/conftest.py` so unit tests
that don't need Docker stay fast.
"""
from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.firecrawl_client import ScrapeMetadata, ScrapeResult

# ---------------------------------------------------------------------------
# Shared DDL constants for testcontainer-Postgres tests.
# ---------------------------------------------------------------------------

# Canonical `vibecheck_jobs` shape. Keep aligned with `src/cache/schema.sql`'s
# CREATE TABLE block + every ALTER TABLE ADD COLUMN that follows it. Tests
# compose their per-suite `_MINIMAL_DDL` by concatenating this constant with
# the surrounding companion-table DDL they need.
VIBECHECK_JOBS_DDL = """
CREATE TABLE vibecheck_jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    host TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    error_code TEXT,
    error_message TEXT,
    error_host TEXT,
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    sidebar_payload JSONB,
    cached BOOLEAN NOT NULL DEFAULT false,
    source_type TEXT NOT NULL DEFAULT 'url',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    test_fail_slug TEXT,
    safety_recommendation JSONB,
    headline_summary JSONB,
    weather_report JSONB,
    last_stage TEXT,
    preview_description TEXT,
    extract_transient_attempts INT NOT NULL DEFAULT 0,
    expired_at TIMESTAMPTZ,
    protected BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT vibecheck_jobs_status_check
        CHECK (status IN ('pending', 'extracting', 'analyzing', 'done', 'partial', 'failed')),
    CONSTRAINT vibecheck_jobs_error_code_check
        CHECK (
            error_code IS NULL
            OR error_code IN (
                'invalid_url', 'unsafe_url', 'unsupported_site', 'upstream_error',
                'extraction_failed', 'section_failure', 'timeout',
                'pdf_too_large', 'pdf_extraction_failed',
                'upload_key_invalid', 'upload_not_found', 'invalid_pdf_type',
                'image_count_too_large', 'image_aggregate_too_large', 'invalid_image_type',
                'image_conversion_failed',
                'rate_limited', 'internal'
            )
        ),
    CONSTRAINT vibecheck_jobs_source_type_check
        CHECK (source_type IN ('url', 'pdf', 'browser_html')),
    CONSTRAINT vibecheck_jobs_terminal_finished_at
        CHECK (
            (status NOT IN ('done', 'partial', 'failed') AND finished_at IS NULL)
            OR (status IN ('done', 'partial', 'failed') AND finished_at IS NOT NULL)
        )
);
"""


VIBECHECK_IMAGE_UPLOAD_BATCHES_DDL = """
CREATE TABLE vibecheck_image_upload_batches (
    job_id UUID PRIMARY KEY REFERENCES vibecheck_jobs(job_id) ON DELETE CASCADE,
    images JSONB NOT NULL,
    conversion_status TEXT NOT NULL DEFAULT 'awaiting_upload',
    generated_pdf_gcs_key TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_getaddrinfo(
        host: str,
        port: object,
        family: int = 0,
        type: int = 0,  # noqa: A002
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        # Return a public IP regardless of hostname. Tests that need to exercise
        # the block-list path should call `src.routes.frame._validate_http_url`
        # directly with a hostname in `_BLOCKED_HOSTNAMES` or stub this fixture.
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


# ---------------------------------------------------------------------------
# Fake Firecrawl client + Gemini agent runner.
# ---------------------------------------------------------------------------


class FakeFirecrawlClient:
    """Programmable stand-in for `FirecrawlClient`.

    The orchestrator only uses `scrape(url, formats=, only_main_content=)`
    in the production code path. Tests inject a `default_result` (or a
    per-URL map via `results_by_url`) and observe `calls` to assert that
    a cache-hit second submit does NOT invoke `scrape` again.
    """

    def __init__(
        self,
        *,
        default_result: ScrapeResult | None = None,
        results_by_url: dict[str, ScrapeResult] | None = None,
        raise_on_call: BaseException | None = None,
    ) -> None:
        self.default_result = default_result or ScrapeResult(
            markdown="hello world",
            html="<p>hello world</p>",
            metadata=ScrapeMetadata(source_url="https://example.com/a"),
        )
        self.results_by_url: dict[str, ScrapeResult] = dict(results_by_url or {})
        self.raise_on_call = raise_on_call
        self.calls: list[dict[str, Any]] = []

    async def scrape(
        self, url: str, formats: list[str], *, only_main_content: bool = False
    ) -> ScrapeResult:
        self.calls.append(
            {
                "url": url,
                "formats": list(formats),
                "only_main_content": only_main_content,
            }
        )
        if self.raise_on_call is not None:
            raise self.raise_on_call
        return self.results_by_url.get(url, self.default_result)


@pytest.fixture
def fake_firecrawl_client() -> FakeFirecrawlClient:
    return FakeFirecrawlClient()


class FakeGeminiAgentRunner:
    """A dependency-free fake for pydantic-ai's `Agent.run` surface.

    Production code calls `agent.run(prompt, deps=...)` and inspects
    `result.output`. The fake returns whatever payload was configured at
    construction time and records calls so tests can assert invocation.
    """

    def __init__(self, output: Any) -> None:
        self._output = output
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> FakeGeminiAgentRunner:
        return self

    @property
    def output(self) -> Any:
        return self._output

    def tool(self, fn: Any) -> Any:
        return fn

    async def run(self, prompt: Any, deps: Any = None) -> FakeGeminiAgentRunner:
        self.calls.append({"prompt": prompt, "deps": deps})
        return self


@pytest.fixture
def fake_gemini_runner() -> FakeGeminiAgentRunner:
    return FakeGeminiAgentRunner(output=None)


# ---------------------------------------------------------------------------
# OIDC mock helpers (Cloud Tasks → /_internal handoff).
# ---------------------------------------------------------------------------


_DEFAULT_OIDC_AUDIENCE = "https://vibecheck.test"
_DEFAULT_OIDC_EMAIL = (
    "vibecheck-tasks@open-notes-core.iam.gserviceaccount.com"
)


@pytest.fixture
def install_oidc_mock(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """Install a happy-path OIDC verifier mock + matching settings.

    Sets `VIBECHECK_SERVER_URL` + `VIBECHECK_TASKS_ENQUEUER_SA` so the
    dependency's deploy-time-misconfig guard does not trip. The verifier
    mock returns a claim mapping bound to those values; tests can mutate
    `mock.return_value` / `mock.side_effect` to simulate failures.
    """
    from src.auth import cloud_tasks_oidc
    from src.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("VIBECHECK_SERVER_URL", _DEFAULT_OIDC_AUDIENCE)
    monkeypatch.setenv("VIBECHECK_TASKS_ENQUEUER_SA", _DEFAULT_OIDC_EMAIL)
    get_settings.cache_clear()

    mock = MagicMock(
        return_value={
            "iss": "https://accounts.google.com",
            "aud": _DEFAULT_OIDC_AUDIENCE,
            "email": _DEFAULT_OIDC_EMAIL,
            "email_verified": True,
        }
    )
    monkeypatch.setattr(cloud_tasks_oidc, "_verify_oauth2_token", mock)
    yield mock
    get_settings.cache_clear()


@pytest.fixture
def oidc_headers() -> dict[str, str]:
    """Authorization header bundle for the /_internal endpoint.

    Pair with `install_oidc_mock` — the bearer string is opaque since the
    verifier itself is mocked; only the header shape matters.
    """
    return {"Authorization": "Bearer fake.jwt.token"}
