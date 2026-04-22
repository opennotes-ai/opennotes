"""Cloud Tasks enqueue wrapper for the async vibecheck pipeline.

The POST /api/analyze handler calls `enqueue_job` after committing the pending
`vibecheck_jobs` row. We publish a Cloud Task whose HTTP target is our own
internal `/_internal/jobs/{job_id}/run` endpoint, authenticated via an
OIDC token the queue mints on our behalf.

The `task_name` deliberately includes the job's initial `attempt_id` so that a
stuck redelivery from a Cloud Tasks retry window cannot collide with a future
attempt for the same job. Cloud Tasks rejects duplicate names, which gives us
idempotency for free: if this function is called twice with the same
`(job_id, expected_attempt_id)`, the second publish is a no-op we can safely
swallow.

Tests stub this function at the route-module level
(`src.routes.analyze.enqueue_job`) via AsyncMock — the real Cloud Tasks client
is loaded lazily so the SDK is not a hard test-time dependency. A separate
unit test patches `_get_async_client` to verify the request payload shape
(OIDC audience, target URL, service-account email).

Codex P0-1 closure: the previous `NotImplementedError` path has been
replaced with an actual `CloudTasksAsyncClient.create_task` call. Callers
still treat the function as opaque, but the real SDK now runs in
production.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.monitoring import get_logger

if TYPE_CHECKING:
    from src.config import Settings

logger = get_logger(__name__)


def build_task_name(job_id: UUID, expected_attempt_id: UUID) -> str:
    """Compose the Cloud Tasks `name` for a (job, attempt) pair.

    Cloud Tasks rejects duplicate task names for a short dedup window, so
    including `expected_attempt_id` in the name ensures a retry rotation that
    mints a fresh attempt gets a distinct name — the old attempt's stuck
    redelivery (if any) does not clobber the new enqueue.

    Path shape: `vibecheck-{job_id}-{attempt_id}`. The parent queue path
    (`projects/.../locations/.../queues/...`) is prepended in `enqueue_job`
    using the configured settings, not here, so this helper is pure and
    trivially unit-testable.
    """
    return f"vibecheck-{job_id}-{expected_attempt_id}"


def _get_async_client() -> Any:
    """Lazily import and construct `CloudTasksAsyncClient`.

    Extracted so unit tests monkeypatch this single seam — they never need
    to import `google.cloud.tasks_v2` just to assert that `enqueue_job`
    wires the right request fields. In production this is called once per
    enqueue; Google's SDK pools the underlying gRPC channel internally.
    """
    from google.cloud import tasks_v2  # noqa: I001, PLC0415  # pyright: ignore[reportAttributeAccessIssue]

    return tasks_v2.CloudTasksAsyncClient()


def _target_url(settings: Settings, job_id: UUID) -> str:
    """Compose the internal worker URL Cloud Tasks POSTs to."""
    base = settings.VIBECHECK_SERVER_URL.rstrip("/")
    return f"{base}/_internal/jobs/{job_id}/run"


def _require_settings(settings: Settings) -> None:
    """Fail loudly when Cloud Tasks settings are missing.

    Silently publishing to the wrong (or default-empty) queue would let
    a misconfig ship to staging and drop jobs on the floor. Refuse at
    call time with an error message that names the missing field so
    operators can fix the env without reading the stack trace.
    """
    missing: list[str] = []
    if not settings.VIBECHECK_TASKS_PROJECT:
        missing.append("VIBECHECK_TASKS_PROJECT")
    if not settings.VIBECHECK_TASKS_LOCATION:
        missing.append("VIBECHECK_TASKS_LOCATION")
    if not settings.VIBECHECK_TASKS_QUEUE:
        missing.append("VIBECHECK_TASKS_QUEUE")
    if not settings.VIBECHECK_TASKS_ENQUEUER_SA:
        missing.append("VIBECHECK_TASKS_ENQUEUER_SA")
    if not settings.VIBECHECK_SERVER_URL:
        missing.append("VIBECHECK_SERVER_URL")
    if missing:
        raise RuntimeError(
            f"enqueue_job: Cloud Tasks settings missing: {', '.join(missing)}"
        )


async def enqueue_job(
    job_id: UUID,
    expected_attempt_id: UUID,
    settings: Settings,
) -> None:
    """Publish a Cloud Task that will invoke the internal job runner.

    The task body is a JSON payload containing
    `{"job_id": ..., "expected_attempt_id": ...}` so the orchestrator
    (TASK-1473.12) can CAS-claim the job row against the attempt it was
    scheduled against. If the attempt has since rotated (retry window
    redelivery hits a superseded attempt_id) the orchestrator drops the
    delivery silently.

    The `oidc_token` block tells Cloud Tasks to mint a Google-signed
    identity token whose audience is our server URL. The internal
    endpoint verifies that token before accepting the body. Audience
    equality is a hard match — do not trim or normalize the URL here.
    """
    _require_settings(settings)

    try:
        client = _get_async_client()
    except ImportError as exc:  # pragma: no cover — prod-only path
        raise RuntimeError(
            "google-cloud-tasks is not installed; enqueue_job cannot publish"
        ) from exc

    parent = client.queue_path(
        settings.VIBECHECK_TASKS_PROJECT,
        settings.VIBECHECK_TASKS_LOCATION,
        settings.VIBECHECK_TASKS_QUEUE,
    )
    task_name = build_task_name(job_id, expected_attempt_id)
    fq_name = f"{parent}/tasks/{task_name}"
    target_url = _target_url(settings, job_id)

    body = json.dumps(
        {
            "job_id": str(job_id),
            "expected_attempt_id": str(expected_attempt_id),
        }
    ).encode("utf-8")

    # Build the task dict (Cloud Tasks accepts dict or proto; the dict
    # form keeps unit tests readable and avoids a hard import of proto
    # classes for test cases that only monkeypatch `_get_async_client`).
    task: dict[str, Any] = {
        "name": fq_name,
        "http_request": {
            "http_method": "POST",
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": body,
            "oidc_token": {
                "service_account_email": settings.VIBECHECK_TASKS_ENQUEUER_SA,
                "audience": settings.VIBECHECK_SERVER_URL,
            },
        },
    }

    logger.info(
        "enqueue_job publishing task_name=%s job_id=%s attempt_id=%s target=%s",
        task_name,
        job_id,
        expected_attempt_id,
        target_url,
    )

    await client.create_task(request={"parent": parent, "task": task})


__all__ = ["build_task_name", "enqueue_job"]
