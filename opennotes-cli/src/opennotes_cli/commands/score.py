from __future__ import annotations

import json
from typing import TYPE_CHECKING

import click
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
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    response = client.post(
        f"{base_url}/api/v2/community-servers/{community_server_id}/score",
        headers=headers,
    )

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
