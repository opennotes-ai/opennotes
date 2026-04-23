"""Startup-time wiring tests (TASK-1473 codex W1 P1.1/P1.2 follow-up).

These tests verify that the FastAPI lifespan actually invokes
`configure_logfire()` — prior to this fix, the function was defined but
never called at startup, so signed-URL scrubbing silently no-oped in
production. They also verify that the Logfire `ScrubbingOptions` we
install carries the custom `extra_patterns` needed for the built-in
scrubber to surface token/signature query-param values to our callback.
"""
from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _reset_logfire_flag() -> Iterator[None]:
    """Reset the module-level idempotency flag so each test triggers configure."""
    import src.monitoring as monitoring_mod

    monitoring_mod._logfire_configured = False
    try:
        yield
    finally:
        monitoring_mod._logfire_configured = False


def test_lifespan_calls_configure_logfire(_reset_logfire_flag: None) -> None:
    """FastAPI startup must invoke configure_logfire so span-level redaction is active."""
    from src.main import app

    with patch("src.startup.configure_logfire") as mock_configure:
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200

    assert mock_configure.called, (
        "configure_logfire must be invoked during app lifespan init"
    )


def test_configure_logfire_installs_extra_patterns(_reset_logfire_flag: None) -> None:
    """ScrubbingOptions must carry extra_patterns covering signed-URL keywords.

    The built-in Logfire scrubber only forwards to our callback when one of
    its own patterns matches. Without `extra_patterns`, `token=`,
    `X-Amz-Signature=`, `X-Goog-Signature=`, `sign=`, `sig=`, and `bearer`
    never match, so our callback never fires and Supabase signed URLs leak.
    """
    from src.monitoring import configure_logfire

    captured: dict[str, object] = {}

    class _StubScrubbing:
        def __init__(
            self,
            callback: object = None,
            extra_patterns: object = None,
        ) -> None:
            captured["callback"] = callback
            captured["extra_patterns"] = extra_patterns

    def _stub_configure(**_kwargs: object) -> None:
        return None

    with patch("logfire.ScrubbingOptions", _StubScrubbing), patch(
        "logfire.configure", _stub_configure
    ):
        configure_logfire()

    patterns = captured.get("extra_patterns")
    assert patterns is not None, "extra_patterns must be passed to ScrubbingOptions"
    pattern_strs: list[str] = [str(p) for p in patterns]  # pyright: ignore[reportGeneralTypeIssues]
    joined = " ".join(pattern_strs)
    assert "token" in joined.lower()
    assert "x-amz-signature" in joined.lower()
    assert "x-goog-signature" in joined.lower()
    assert "sign" in joined.lower()
    assert "bearer" in joined.lower()
    # codex W3 P1-6: the sanitizer regex matches `sig=` (the shortest
    # Firecrawl/Supabase alias) but the Logfire extra_patterns list was
    # missing it, so the scrubber callback never fired for that shape.
    assert any("sig=" in p for p in pattern_strs), (
        "extra_patterns must include a literal 'sig=' token"
    )


def test_metrics_endpoint_rejects_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unauthenticated GET /metrics must 401 (TASK-1473.37).

    Pre-fix the bare `app.mount("/metrics", make_asgi_app())` exposed
    operational signals to anyone reaching the Cloud Run revision when
    `--allow-unauthenticated` was set. The endpoint now requires the
    same OIDC dependency the internal worker uses.
    """
    from src.config import get_settings
    from src.main import app

    monkeypatch.setenv("VIBECHECK_SERVER_URL", "https://vibecheck.test")
    monkeypatch.setenv(
        "VIBECHECK_TASKS_ENQUEUER_SA",
        "vibecheck-tasks@open-notes-core.iam.gserviceaccount.com",
    )
    get_settings.cache_clear()

    with TestClient(app) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 401
    body = resp.json()
    # The OIDC dependency raises HTTPException(detail={...}); the body is
    # FastAPI's default `{"detail": {...}}` shape there. We assert the
    # error code surfaces somewhere so the gate can't be misinterpreted
    # as a 200 with empty payload.
    assert "unauthorized" in str(body)

    get_settings.cache_clear()
