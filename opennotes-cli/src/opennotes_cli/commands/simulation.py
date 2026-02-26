from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from opennotes_cli.display import get_cli_prefix, get_status_style, handle_jsonapi_error
from opennotes_cli.http import add_csrf, get_csrf_token
from opennotes_cli.polling import poll_simulation_until_complete

if TYPE_CHECKING:
    from opennotes_cli.cli import CliContext

console = Console()
error_console = Console(stderr=True)


@click.group()
def simulation() -> None:
    """Manage simulation runs."""


@simulation.command("list")
@click.option("--page", default=1, type=click.IntRange(1), help="Page number.")
@click.option("--page-size", default=20, type=click.IntRange(1, 100), help="Page size (1-100).")
@click.pass_context
def simulation_list(ctx: click.Context, page: int, page_size: int) -> None:
    """List simulation runs."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    params = {"page[number]": page, "page[size]": page_size}
    response = client.get(f"{base_url}/api/v2/simulations", headers=headers, params=params)
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    items = result.get("data", [])
    total = result.get("meta", {}).get("count", len(items))

    if not items:
        console.print("[yellow]No simulation runs found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", no_wrap=True)
    table.add_column("Status", width=12)
    table.add_column("Orchestrator ID", no_wrap=True)
    table.add_column("Community Server ID", no_wrap=True)
    table.add_column("Created At", width=20)

    for item in items:
        attrs = item.get("attributes", {})
        status = attrs.get("status", "unknown")
        color, symbol = get_status_style(status)
        created = (attrs.get("created_at") or "")[:19]

        table.add_row(
            item.get("id", "N/A"),
            f"[{color}]{symbol} {status}[/{color}]",
            attrs.get("orchestrator_id", "N/A"),
            attrs.get("community_server_id", "N/A"),
            created,
        )

    console.print(table)
    console.print(f"\n[dim]Total: {total} simulation(s)[/dim]")


@simulation.command("status")
@click.argument("simulation_id")
@click.pass_context
def simulation_status(ctx: click.Context, simulation_id: str) -> None:
    """Show status of a simulation run."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    response = client.get(
        f"{base_url}/api/v2/simulations/{simulation_id}", headers=headers
    )
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    attrs = result.get("data", {}).get("attributes", {})
    status = attrs.get("status", "unknown")
    color, symbol = get_status_style(status)

    panel_content = (
        f"[bold]ID:[/bold] {result.get('data', {}).get('id', 'N/A')}\n"
        f"[bold]Status:[/bold] [{color}]{symbol} {status}[/{color}]\n"
        f"[bold]Orchestrator:[/bold] {attrs.get('orchestrator_id', 'N/A')}\n"
        f"[bold]Community Server:[/bold] {attrs.get('community_server_id', 'N/A')}"
    )

    for ts_field in ("started_at", "completed_at", "paused_at", "created_at", "updated_at"):
        val = attrs.get(ts_field)
        if val:
            label = ts_field.replace("_", " ").title()
            panel_content += f"\n[bold]{label}:[/bold] {val[:19]}"

    metrics = attrs.get("metrics")
    if metrics:
        panel_content += f"\n[bold]Metrics:[/bold] {json.dumps(metrics, indent=2)}"

    error_msg = attrs.get("error_message")
    if error_msg:
        panel_content += f"\n[bold red]Error:[/bold red] {error_msg}"

    console.print(Panel(panel_content, title="[bold]Simulation Run[/bold]"))


@simulation.command("create")
@click.option("--orchestrator-id", required=True, help="Orchestrator UUID.")
@click.option(
    "--community-server-id", required=True,
    help="Community server UUID (must be playground).",
)
@click.option("--wait", is_flag=True, help="Poll until simulation reaches a terminal state.")
@click.pass_context
def simulation_create(
    ctx: click.Context, orchestrator_id: str, community_server_id: str, wait: bool
) -> None:
    """Create and start a simulation run."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    payload = {
        "data": {
            "type": "simulations",
            "attributes": {
                "orchestrator_id": orchestrator_id,
                "community_server_id": community_server_id,
            },
        }
    }

    response = client.post(
        f"{base_url}/api/v2/simulations", headers=headers, json=payload
    )
    handle_jsonapi_error(response)

    result = response.json()
    sim_id = result.get("data", {}).get("id", "N/A")

    if wait:
        if not cli_ctx.json_output:
            console.print(f"[dim]Simulation created: {sim_id}[/dim]")
            console.print("[dim]Waiting for completion...[/dim]\n")
        result = poll_simulation_until_complete(client, base_url, headers, sim_id)

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    attrs = result.get("data", {}).get("attributes", {})
    status = attrs.get("status", "unknown")
    color, symbol = get_status_style(status)

    console.print(
        Panel(
            f"[bold]ID:[/bold] {sim_id}\n"
            f"[bold]Status:[/bold] [{color}]{symbol} {status}[/{color}]\n"
            f"[bold]Orchestrator:[/bold] {attrs.get('orchestrator_id', 'N/A')}\n"
            f"[bold]Community Server:[/bold] {attrs.get('community_server_id', 'N/A')}",
            title="[bold green]Simulation Created[/bold green]",
        )
    )

    if not wait:
        cli_prefix = get_cli_prefix(cli_ctx.env_name)
        console.print(f"\n[dim]Check status:[/dim] {cli_prefix} simulation status {sim_id}")


def _simulation_lifecycle_cmd(
    ctx: click.Context, simulation_id: str, action: str
) -> None:
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    response = client.post(
        f"{base_url}/api/v2/simulations/{simulation_id}/{action}", headers=headers
    )
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    attrs = result.get("data", {}).get("attributes", {})
    status = attrs.get("status", "unknown")
    color, symbol = get_status_style(status)
    console.print(
        f"[{color}]{symbol}[/{color}] Simulation {simulation_id} is now [{color}]{status}[/{color}]"
    )


@simulation.command("pause")
@click.argument("simulation_id")
@click.pass_context
def simulation_pause(ctx: click.Context, simulation_id: str) -> None:
    """Pause a running simulation."""
    _simulation_lifecycle_cmd(ctx, simulation_id, "pause")


@simulation.command("resume")
@click.argument("simulation_id")
@click.pass_context
def simulation_resume(ctx: click.Context, simulation_id: str) -> None:
    """Resume a paused simulation."""
    _simulation_lifecycle_cmd(ctx, simulation_id, "resume")


@simulation.command("cancel")
@click.argument("simulation_id")
@click.pass_context
def simulation_cancel(ctx: click.Context, simulation_id: str) -> None:
    """Cancel a simulation."""
    _simulation_lifecycle_cmd(ctx, simulation_id, "cancel")
