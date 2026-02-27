from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console

from opennotes_cli.display import display_task_list, display_task_start, display_task_status
from opennotes_cli.http import add_csrf, get_csrf_token
from opennotes_cli.polling import poll_task_until_complete

if TYPE_CHECKING:
    from opennotes_cli.cli import CliContext

console = Console()
error_console = Console(stderr=True)


@click.group()
def rechunk() -> None:
    """Rechunk and re-embed content."""


@rechunk.command("factchecks")
@click.option(
    "-c",
    "--community-id",
    required=False,
    default=None,
    help="Community server ID (UUID) for LLM credentials. If not provided, uses global API keys.",
)
@click.option(
    "-b",
    "--batch-size",
    default=100,
    type=click.IntRange(1, 1000),
    help="Items per batch (1-1000).",
)
@click.option("--wait", is_flag=True, help="Wait for completion, polling status until done.")
@click.pass_context
def rechunk_factchecks(
    ctx: click.Context, community_id: str | None, batch_size: int, wait: bool
) -> None:
    """Rechunk and re-embed all fact-check items."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        creds_source = f"community {community_id}" if community_id else "global API keys"
        console.print(f"[dim]Triggering fact-check rechunk (using {creds_source})...[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/chunks/fact-check/rechunk"
    params: dict[str, str | int] = {"batch_size": batch_size}
    if community_id:
        params["community_server_id"] = community_id

    response = client.post(url, headers=headers, params=params)

    if response.status_code == 409:
        error_console.print("[red]Error:[/red] A rechunk operation is already in progress.")
        error_console.print(
            "[dim]Wait for the current operation to complete before starting a new one.[/dim]"
        )
        sys.exit(1)

    if response.status_code == 403:
        error_console.print(
            "[red]Error:[/red] Access denied. Admin/moderator access required."
        )
        sys.exit(1)

    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)

    result = response.json()

    if wait:
        task_id = result.get("task_id")
        if not cli_ctx.json_output:
            console.print(f"[dim]Task started: {task_id}[/dim]")
            console.print("[dim]Waiting for completion...[/dim]\n")
        final_status = poll_task_until_complete(client, base_url, headers, task_id)
        display_task_status(final_status, cli_ctx.json_output)
    else:
        display_task_start(result, cli_ctx.env_name, cli_ctx.json_output)


@rechunk.command("previously-seen")
@click.option(
    "-c",
    "--community-id",
    required=True,
    help="Community server ID (UUID) to filter and authenticate.",
)
@click.option(
    "-b",
    "--batch-size",
    default=100,
    type=click.IntRange(1, 1000),
    help="Items per batch (1-1000).",
)
@click.option("--wait", is_flag=True, help="Wait for completion, polling status until done.")
@click.pass_context
def rechunk_previously_seen(
    ctx: click.Context, community_id: str, batch_size: int, wait: bool
) -> None:
    """Rechunk and re-embed previously seen messages for a community."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print("[dim]Triggering previously-seen rechunk...[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/chunks/previously-seen/rechunk"
    params = {"community_server_id": community_id, "batch_size": batch_size}

    response = client.post(url, headers=headers, params=params)

    if response.status_code == 409:
        error_console.print(
            "[red]Error:[/red] A rechunk operation is already in progress for this community."
        )
        error_console.print(
            "[dim]Wait for the current operation to complete before starting a new one.[/dim]"
        )
        sys.exit(1)

    if response.status_code == 403:
        error_console.print(
            "[red]Error:[/red] Access denied. Admin/moderator access required."
        )
        sys.exit(1)

    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)

    result = response.json()

    if wait:
        task_id = result.get("task_id")
        if not cli_ctx.json_output:
            console.print(f"[dim]Task started: {task_id}[/dim]")
            console.print("[dim]Waiting for completion...[/dim]\n")
        final_status = poll_task_until_complete(client, base_url, headers, task_id)
        display_task_status(final_status, cli_ctx.json_output)
    else:
        display_task_start(result, cli_ctx.env_name, cli_ctx.json_output)


@rechunk.command("status")
@click.argument("task_id")
@click.option("--wait", is_flag=True, help="Poll until task completes.")
@click.pass_context
def rechunk_status(ctx: click.Context, task_id: str, wait: bool) -> None:
    """Get status of a rechunk task."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print(f"[dim]Fetching task status: {task_id}[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/chunks/jobs/{task_id}"
    response = client.get(url, headers=headers)

    if response.status_code == 404:
        error_console.print(f"[red]Error:[/red] Task {task_id} not found.")
        error_console.print(
            "[dim]The task may have expired (24h TTL) or the ID is invalid.[/dim]"
        )
        sys.exit(1)

    if response.status_code == 403:
        error_console.print(
            "[red]Error:[/red] Access denied. You don't have access to this task."
        )
        sys.exit(1)

    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)

    result = response.json()

    if result.get("status") == "in_progress":
        progress_url = f"{base_url}/api/v1/batch-jobs/{task_id}/progress"
        progress_response = client.get(progress_url, headers=headers)
        if progress_response.status_code == 200:
            progress_data = progress_response.json()
            result["completed_tasks"] = progress_data.get("processed_count", 0)
            result["failed_tasks"] = progress_data.get("error_count", 0)

    if wait:
        status = result.get("status", "unknown")
        if status not in ("completed", "failed"):
            if not cli_ctx.json_output:
                console.print("[dim]Waiting for completion...[/dim]\n")
            result = poll_task_until_complete(client, base_url, headers, task_id)

    display_task_status(result, cli_ctx.json_output)


@rechunk.command("delete")
@click.argument("task_id")
@click.option("--force", is_flag=True, help="Force delete even if task is completed/failed.")
@click.pass_context
def rechunk_delete(ctx: click.Context, task_id: str, force: bool) -> None:
    """Cancel and delete a rechunk task."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print(f"[dim]Deleting task: {task_id}[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/chunks/jobs/{task_id}"
    params: dict[str, Any] = {}
    if force:
        params["force"] = "true"

    response = client.delete(url, headers=headers, params=params)

    if response.status_code == 404:
        error_console.print(f"[red]Error:[/red] Task {task_id} not found.")
        error_console.print(
            "[dim]The task may have expired (24h TTL) or the ID is invalid.[/dim]"
        )
        sys.exit(1)

    if response.status_code == 403:
        error_console.print(
            "[red]Error:[/red] Access denied. Admin/moderator access required."
        )
        sys.exit(1)

    if response.status_code == 409:
        error_console.print(
            "[red]Error:[/red] Cannot cancel task in terminal state (completed/failed)."
        )
        error_console.print("[dim]Use --force to delete anyway.[/dim]")
        sys.exit(1)

    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)

    if response.status_code == 204:
        if cli_ctx.json_output:
            console.print(json.dumps({"message": "Task cancelled"}, indent=2))
        else:
            console.print(f"[green]\u2713[/green] Task {task_id} cancelled")
        return

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
    else:
        message = result.get("message", "Task deleted")
        console.print(f"[green]\u2713[/green] {message}")


@rechunk.command("list")
@click.option(
    "-s",
    "--status",
    "status_filter",
    help="Filter by status (pending, in_progress, completed, failed).",
)
@click.pass_context
def rechunk_list(ctx: click.Context, status_filter: str | None) -> None:
    """List all active rechunk tasks."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print("[dim]Fetching rechunk tasks...[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/chunks/jobs"
    params: dict[str, str] = {}
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
            job_id = job.get("id")
            if job_id:
                progress_url = f"{base_url}/api/v1/batch-jobs/{job_id}/progress"
                progress_response = client.get(progress_url, headers=headers)
                if progress_response.status_code == 200:
                    progress_data = progress_response.json()
                    job["completed_tasks"] = progress_data.get("processed_count", 0)
                    job["failed_tasks"] = progress_data.get("error_count", 0)

    display_task_list(result, cli_ctx.env_name, cli_ctx.json_output)
