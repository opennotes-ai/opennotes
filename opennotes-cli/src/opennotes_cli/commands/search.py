from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import click
from rich.console import Console

from opennotes_cli.display import display_search_results
from opennotes_cli.http import add_csrf, get_csrf_token

if TYPE_CHECKING:
    from opennotes_cli.cli import CliContext

console = Console()
error_console = Console(stderr=True)


@click.command("hybrid-search")
@click.argument("text")
@click.option(
    "-c",
    "--community-id",
    default="1448846366938759308",
    help="Community server ID (Discord guild ID).",
)
@click.option(
    "-l",
    "--limit",
    default=10,
    type=click.IntRange(1, 20),
    help="Maximum results (1-20).",
)
@click.pass_context
def hybrid_search(ctx: click.Context, text: str, community_id: str, limit: int) -> None:
    """Search fact-checks using hybrid search (FTS + semantic)."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print(f"[dim]URL: {base_url}[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    payload = {
        "data": {
            "type": "hybrid-searches",
            "attributes": {
                "text": text,
                "community_server_id": community_id,
                "limit": limit,
            },
        }
    }

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Searching with community_server_id: {community_id}[/dim]")
        console.print(
            f"[dim]Text: {text[:80]}{'...' if len(text) > 80 else ''}[/dim]"
        )

    response = client.post(
        f"{base_url}/api/v2/hybrid-searches", headers=headers, json=payload
    )

    if response.status_code == 403:
        error_text = response.text
        if "CSRF" in error_text:
            error_console.print("[red]Error:[/red] CSRF token validation failed")
        else:
            error_console.print(
                "[red]Error:[/red] Access denied. You may not have access to this community."
            )
        error_console.print(f"[dim]Response: {error_text[:500]}[/dim]")
        sys.exit(1)

    if response.status_code == 429:
        error_console.print(
            "[red]Error:[/red] Rate limit exceeded. Please try again later."
        )
        sys.exit(1)

    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]Response: {response.text[:500]}[/dim]")
        sys.exit(1)

    results = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(results, indent=2))
    else:
        display_search_results(results, text)
