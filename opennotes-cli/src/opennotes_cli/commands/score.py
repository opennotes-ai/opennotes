from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING
from uuid import UUID

import click
import httpx
from rich.console import Console

from opennotes_cli.http import add_csrf, get_csrf_token, handle_error_response

if TYPE_CHECKING:
    from opennotes_cli.cli import CliContext

console = Console()
error_console = Console(stderr=True)


@click.command()
@click.argument("community_server_id")
@click.pass_context
def score(ctx: click.Context, community_server_id: str) -> None:
    """Trigger manual scoring for a community server."""
    try:
        UUID(community_server_id)
    except ValueError:
        error_console.print(
            f"[red]Error:[/red] Invalid community server ID: '{community_server_id}'. Expected a UUID."
        )
        sys.exit(1)

    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    try:
        csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    except httpx.ConnectError:
        error_console.print(
            f"[red]Error:[/red] Could not connect to server at {base_url}"
        )
        sys.exit(1)
    except httpx.TimeoutException:
        error_console.print(
            f"[red]Error:[/red] Connection to {base_url} timed out"
        )
        sys.exit(1)

    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    try:
        response = client.post(
            f"{base_url}/api/v2/community-servers/{community_server_id}/score",
            headers=headers,
        )
    except httpx.ConnectError:
        error_console.print(
            f"[red]Error:[/red] Could not connect to server at {base_url}"
        )
        sys.exit(1)
    except httpx.TimeoutException:
        error_console.print(
            f"[red]Error:[/red] Request to {base_url} timed out"
        )
        sys.exit(1)

    if response.status_code == 409:
        error_console.print(
            "[yellow]Scoring is already in progress for this community server.[/yellow]"
        )
        return

    handle_error_response(
        response,
        custom_handlers={
            404: f"Community server {community_server_id} not found.",
        },
    )

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    workflow_id = result.get("workflow_id", "N/A")
    console.print(
        f"[green]\u2713[/green] Scoring dispatched: workflow [bold]{workflow_id}[/bold]"
    )
    console.print("[dim]Scoring is running in the background.[/dim]")
