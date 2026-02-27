from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import click
from rich.console import Console

from opennotes_cli.display import display_batch_job_list, display_batch_job_status
from opennotes_cli.http import add_csrf, get_csrf_token
from opennotes_cli.polling import poll_batch_job_until_complete

if TYPE_CHECKING:
    from opennotes_cli.cli import CliContext

console = Console()
error_console = Console(stderr=True)


@click.group()
def batch() -> None:
    """Manage batch jobs (long-running operations)."""


@batch.command("status")
@click.argument("job_id")
@click.option("--wait", is_flag=True, help="Poll until job completes.")
@click.pass_context
def batch_status(ctx: click.Context, job_id: str, wait: bool) -> None:
    """Get status of a batch job."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print(f"[dim]Fetching job status: {job_id}[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/batch-jobs/{job_id}"
    response = client.get(url, headers=headers)

    if response.status_code == 404:
        error_console.print(f"[red]Error:[/red] Job {job_id} not found.")
        sys.exit(1)
    if response.status_code == 403:
        error_console.print("[red]Error:[/red] Access denied. Authentication required.")
        sys.exit(1)
    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)

    result = response.json()

    if wait:
        status = result.get("status", "unknown")
        if status not in ("completed", "failed", "cancelled"):
            if not cli_ctx.json_output:
                console.print("[dim]Waiting for completion...[/dim]\n")
            result = poll_batch_job_until_complete(client, base_url, headers, job_id)

    display_batch_job_status(result, cli_ctx.json_output)


@batch.command("list")
@click.option("-t", "--type", "job_type", help="Filter by job type (e.g., 'fact_check_import').")
@click.option(
    "-s", "--status", "status_filter",
    help="Filter by status (pending, in_progress, completed, failed, cancelled).",
)
@click.option(
    "-l", "--limit", default=50, type=click.IntRange(1, 100),
    help="Maximum results (1-100).",
)
@click.pass_context
def batch_list(
    ctx: click.Context, job_type: str | None, status_filter: str | None, limit: int
) -> None:
    """List batch jobs with optional filters."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print("[dim]Fetching batch jobs...[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/batch-jobs"
    params: dict[str, str | int] = {"limit": limit}
    if job_type:
        params["job_type"] = job_type
    if status_filter:
        params["status"] = status_filter

    response = client.get(url, headers=headers, params=params)

    if response.status_code == 403:
        error_console.print("[red]Error:[/red] Access denied. Authentication required.")
        sys.exit(1)
    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)

    result = response.json()

    for job in result:
        if job.get("status") == "in_progress":
            jid = job.get("id")
            if jid:
                progress_url = f"{base_url}/api/v1/batch-jobs/{jid}/progress"
                progress_response = client.get(progress_url, headers=headers)
                if progress_response.status_code == 200:
                    progress_data = progress_response.json()
                    job["completed_tasks"] = progress_data.get("processed_count", 0)
                    job["failed_tasks"] = progress_data.get("error_count", 0)

    display_batch_job_list(result, cli_ctx.env_name, cli_ctx.json_output)


@batch.command("cancel")
@click.argument("job_id")
@click.pass_context
def batch_cancel(ctx: click.Context, job_id: str) -> None:
    """Cancel a running or pending batch job."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print(f"[dim]Cancelling job: {job_id}[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/batch-jobs/{job_id}"
    response = client.delete(url, headers=headers)

    if response.status_code == 404:
        error_console.print(f"[red]Error:[/red] Job {job_id} not found.")
        sys.exit(1)
    if response.status_code == 403:
        error_console.print("[red]Error:[/red] Access denied. Authentication required.")
        sys.exit(1)
    if response.status_code == 409:
        error_console.print(
            "[red]Error:[/red] Cannot cancel job in terminal state (completed/failed)."
        )
        sys.exit(1)
    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)

    if cli_ctx.json_output:
        console.print(
            json.dumps({"message": "Job cancelled", "job_id": job_id}, indent=2)
        )
    else:
        console.print(f"[green]\u2713[/green] Job {job_id} cancelled")
