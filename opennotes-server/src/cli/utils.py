"""
Shared utilities for CLI commands.

Provides async execution helpers, job polling, and output formatting.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID

import click

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.batch_jobs.models import BatchJob

T = TypeVar("T")

DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_TIMEOUT = 3600


def run_async(coro: Awaitable[T]) -> T:
    """
    Run an async coroutine from synchronous Click command context.

    Args:
        coro: The coroutine to execute

    Returns:
        The result of the coroutine
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        raise RuntimeError("Cannot call run_async from an async context")

    return asyncio.run(coro)


def common_batch_options(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator that adds common batch job options to a Click command.

    Adds: --batch-size, --dry-run, --wait, --verbose
    """
    func = click.option(
        "--batch-size",
        "-b",
        type=int,
        default=1000,
        show_default=True,
        help="Number of items to process per batch",
    )(func)
    func = click.option(
        "--dry-run",
        "-n",
        is_flag=True,
        help="Validate only, do not make changes",
    )(func)
    func = click.option(
        "--wait",
        "-w",
        is_flag=True,
        help="Wait for job completion and show progress",
    )(func)
    return click.option(
        "--verbose",
        "-v",
        is_flag=True,
        help="Enable verbose output",
    )(func)


async def poll_job_until_complete(
    session: AsyncSession,
    job_id: UUID,
    interval: float = DEFAULT_POLL_INTERVAL,
    timeout: float = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> BatchJob | None:
    """
    Poll a batch job until it reaches a terminal state.

    Args:
        session: Database session for querying job status
        job_id: The batch job ID to poll
        interval: Seconds between polls (default 2)
        timeout: Maximum seconds to wait (default 3600 = 1 hour)
        verbose: Whether to print progress updates

    Returns:
        The final BatchJob state, or None if not found
    """
    from src.batch_jobs.service import BatchJobService  # noqa: PLC0415

    service = BatchJobService(session)
    start_time = time.time()
    last_progress = -1

    while True:
        job = await service.get_job(job_id)
        if job is None:
            click.echo(f"Error: Job {job_id} not found", err=True)
            return None

        if job.is_terminal:
            return job

        elapsed = time.time() - start_time
        if elapsed > timeout:
            click.echo(
                f"Warning: Timeout after {timeout}s. Job {job_id} still {job.status}",
                err=True,
            )
            return job

        current_progress = job.completed_tasks
        if current_progress != last_progress:
            if job.total_tasks > 0:
                pct = job.progress_percentage
                click.echo(f"Progress: {job.completed_tasks}/{job.total_tasks} ({pct:.1f}%)")
            else:
                click.echo(f"Progress: {job.completed_tasks} processed")
            last_progress = current_progress

        await asyncio.sleep(interval)


def format_job_output(job: BatchJob, verbose: bool = False) -> str:
    """
    Format a batch job for CLI output.

    Args:
        job: The batch job to format
        verbose: Whether to include detailed information

    Returns:
        Formatted string for display
    """
    lines = [
        f"Job ID: {job.id}",
        f"Status: {job.status}",
    ]

    if job.total_tasks > 0:
        lines.append(f"Progress: {job.completed_tasks}/{job.total_tasks}")
    else:
        lines.append(f"Completed: {job.completed_tasks}")

    if job.failed_tasks > 0:
        lines.append(f"Failed: {job.failed_tasks}")

    if verbose:
        lines.append(f"Type: {job.job_type}")
        if job.started_at:
            lines.append(f"Started: {job.started_at.isoformat()}")
        if job.completed_at:
            lines.append(f"Completed: {job.completed_at.isoformat()}")
        if job.metadata_:
            lines.append(f"Metadata: {job.metadata_}")
        if job.error_summary:
            lines.append(f"Errors: {job.error_summary}")

    return "\n".join(lines)


def print_job_result(job: BatchJob, verbose: bool = False) -> int:
    """
    Print job result to stdout with appropriate formatting.

    Args:
        job: The batch job to print
        verbose: Whether to include detailed information

    Returns:
        Exit code: 0 for success/cancelled, 1 for failed
    """
    click.echo(format_job_output(job, verbose))

    if job.status == "completed":
        click.echo(click.style("Job completed successfully", fg="green"))
        return 0
    if job.status == "failed":
        click.echo(click.style("Job failed", fg="red"), err=True)
        if job.error_summary:
            click.echo(f"Error details: {job.error_summary}", err=True)
        return 1
    if job.status == "cancelled":
        click.echo(click.style("Job was cancelled", fg="yellow"))
        return 0
    return 0
