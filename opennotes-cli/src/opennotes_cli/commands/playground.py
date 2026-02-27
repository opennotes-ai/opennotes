from __future__ import annotations

import json
import sys
import uuid
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console
from rich.panel import Panel

from opennotes_cli.display import get_cli_prefix, handle_jsonapi_error
from opennotes_cli.http import add_csrf, get_csrf_token

if TYPE_CHECKING:
    from opennotes_cli.cli import CliContext

console = Console()
error_console = Console(stderr=True)


@click.group()
def playground() -> None:
    """Manage playground community servers."""


@playground.command("create")
@click.option("--name", required=True, help="Playground name.")
@click.option("--description", default=None, help="Playground description.")
@click.option("--platform-id", default=None, help="Platform ID (auto-generated if omitted).")
@click.pass_context
def playground_create(
    ctx: click.Context, name: str, description: str | None, platform_id: str | None
) -> None:
    """Create a new playground community server."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if not platform_id:
        platform_id = uuid.uuid4().hex[:16]

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    payload: dict[str, Any] = {
        "platform": "playground",
        "platform_community_server_id": platform_id,
        "name": name,
        "is_active": True,
        "is_public": True,
    }
    if description:
        payload["description"] = description

    response = client.post(
        f"{base_url}/api/v1/community-servers", headers=headers, json=payload
    )
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    cs_id = result.get("id", "N/A")
    console.print(
        Panel(
            f"[bold]ID:[/bold] {cs_id}\n"
            f"[bold]Name:[/bold] {result.get('name', 'N/A')}\n"
            f"[bold]Platform:[/bold] {result.get('platform', 'N/A')}\n"
            f"[bold]Platform ID:[/bold] {result.get('platform_community_server_id', 'N/A')}",
            title="[bold green]Playground Created[/bold green]",
        )
    )
    console.print(f"\n[bold]Community Server ID:[/bold] {cs_id}")
    cli_prefix = get_cli_prefix(cli_ctx.env_name)
    console.print(
        f"[dim]Use with:[/dim] {cli_prefix} simulation create --community-server-id {cs_id} --orchestrator-id <id>"
    )


@playground.command("add-request")
@click.option(
    "--community-server-id", required=True,
    help="Community server UUID (must be playground).",
)
@click.option(
    "--url", "urls", required=True, multiple=True,
    help="URL to fetch content from (max 20, can repeat).",
)
@click.pass_context
def playground_add_request(
    ctx: click.Context, community_server_id: str, urls: tuple[str, ...]
) -> None:
    """Add note requests to a playground by fetching URLs (async via DBOS workflow)."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if len(urls) > 20:
        error_console.print("[red]Error:[/red] Maximum 20 URLs per request.")
        sys.exit(1)

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    payload = {
        "data": {
            "type": "playground-note-requests",
            "attributes": {
                "urls": list(urls),
            },
        }
    }

    response = client.post(
        f"{base_url}/api/v2/playgrounds/{community_server_id}/note-requests",
        headers=headers,
        json=payload,
    )

    if response.status_code == 400:
        error_console.print("[red]Error:[/red] Community server is not a playground.")
        sys.exit(1)

    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    data = result.get("data", {})
    attrs = data.get("attributes", {})
    workflow_id = attrs.get("workflow_id", "unknown")
    url_count = attrs.get("url_count", len(urls))
    job_status = attrs.get("status", "ACCEPTED")

    status_color = "green" if job_status == "ACCEPTED" else "yellow"
    console.print(f"[{status_color}]Job accepted[/{status_color}]")
    console.print(f"  Workflow ID: [bold]{workflow_id}[/bold]")
    console.print(f"  URLs queued: {url_count}")
    console.print(
        "\n[dim]URL extraction is running asynchronously via DBOS workflow.[/dim]"
    )
    console.print("[dim]Check playground requests later to see results.[/dim]")
