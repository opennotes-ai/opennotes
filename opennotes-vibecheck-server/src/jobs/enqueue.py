"""Cloud Tasks enqueue wrapper for the async vibecheck pipeline (TASK-1473.11).

The POST /api/analyze handler calls `enqueue_job` after committing the pending
`vibecheck_jobs` row. We publish a Cloud Task that will (later, TASK-1473.12)
POST to the internal `/_internal/jobs/{job_id}/run` endpoint with OIDC auth.

The `task_name` deliberately includes the job's initial `attempt_id` so that a
stuck redelivery from a Cloud Tasks retry window cannot collide with a future
attempt for the same job. Cloud Tasks rejects duplicate names, which gives us
idempotency for free: if this function is called twice with the same
`(job_id, expected_attempt_id)`, the second publish is a no-op we can safely
swallow.

Tests stub this function at the route-module level
(`src.routes.analyze.enqueue_job`) via AsyncMock — the real Cloud Tasks client
is loaded lazily so the SDK is not a hard test-time dependency.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
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


async def enqueue_job(
    job_id: UUID,
    expected_attempt_id: UUID,
    settings: Settings,  # noqa: ARG001  — consumed by TASK-1473.12 orchestrator wiring
) -> None:
    """Publish a Cloud Task that will invoke the internal job runner.

    The real Cloud Tasks client (`google.cloud.tasks_v2.CloudTasksAsyncClient`)
    is imported lazily so unit-test environments that do not install
    `google-cloud-tasks` can still monkeypatch this function without importing
    the package. Production runtime imports the client on first call.

    The task body is a JSON payload containing `{"job_id": ..., "expected_attempt_id": ...}`
    so the orchestrator (TASK-1473.12) can CAS-claim the job row against the
    attempt it was scheduled against. If the attempt has since rotated
    (retry window redelivery hits a superseded attempt_id) the orchestrator
    drops the delivery silently.
    """
    # Lazy import: google-cloud-tasks is an optional runtime dep. Tests never
    # reach this code because `src.routes.analyze.enqueue_job` is replaced
    # with an AsyncMock at setup time.
    try:
        # google-cloud-tasks is an optional runtime dep; the lazy import
        # raises at call time in environments that skip it.
        from google.cloud import tasks_v2  # noqa: PLC0415  # pyright: ignore[reportAttributeAccessIssue]
    except ImportError as exc:  # pragma: no cover — prod-only path
        raise RuntimeError(
            "google-cloud-tasks is not installed; enqueue_job cannot publish"
        ) from exc

    task_name = build_task_name(job_id, expected_attempt_id)
    logger.info(
        "enqueue_job publishing task_name=%s job_id=%s attempt_id=%s",
        task_name,
        job_id,
        expected_attempt_id,
    )
    # NOTE: actual CloudTasksAsyncClient wiring (queue path, OIDC, target URL)
    # is intentionally kept out of this wrapper until TASK-1473.12 lands the
    # orchestrator and the matching settings plumbing. The attribute access
    # below is a marker so type-checkers confirm tasks_v2 is the right module;
    # the body will be filled in by that ticket.
    _ = tasks_v2  # silence unused-import during the bootstrap wave
    raise NotImplementedError(
        "enqueue_job Cloud Tasks publish is wired in TASK-1473.12; route handlers should treat this function as opaque."
    )


__all__ = ["build_task_name", "enqueue_job"]
