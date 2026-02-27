from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from opennotes_cli.display import handle_jsonapi_error
from opennotes_cli.http import add_csrf, get_csrf_token

if TYPE_CHECKING:
    from opennotes_cli.cli import CliContext

console = Console()
error_console = Console(stderr=True)


@click.group("sim-agent")
def sim_agent() -> None:
    """Manage simulation agent personalities."""


@sim_agent.command("list")
@click.option("--page", default=1, type=click.IntRange(1), help="Page number.")
@click.option("--page-size", default=20, type=click.IntRange(1, 100), help="Page size (1-100).")
@click.pass_context
def sim_agent_list(ctx: click.Context, page: int, page_size: int) -> None:
    """List agent personalities."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    params = {"page[number]": page, "page[size]": page_size}
    response = client.get(f"{base_url}/api/v2/sim-agents", headers=headers, params=params)
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    items = result.get("data", [])
    total = result.get("meta", {}).get("count", len(items))

    if not items:
        console.print("[yellow]No agent personalities found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", no_wrap=True)
    table.add_column("Name", width=25)
    table.add_column("Model", width=30)
    table.add_column("Memory Strategy", width=20)
    table.add_column("Created At", width=20)

    for item in items:
        attrs = item.get("attributes", {})
        created = (attrs.get("created_at") or "")[:19]
        table.add_row(
            item.get("id", "N/A"),
            attrs.get("name", "N/A"),
            attrs.get("model_name", "N/A"),
            attrs.get("memory_compaction_strategy", "N/A"),
            created,
        )

    console.print(table)
    console.print(f"\n[dim]Total: {total} agent(s)[/dim]")


@sim_agent.command("get")
@click.argument("agent_id")
@click.pass_context
def sim_agent_get(ctx: click.Context, agent_id: str) -> None:
    """Show details of an agent personality."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    response = client.get(f"{base_url}/api/v2/sim-agents/{agent_id}", headers=headers)
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    attrs = result.get("data", {}).get("attributes", {})

    panel_content = (
        f"[bold]ID:[/bold] {result.get('data', {}).get('id', 'N/A')}\n"
        f"[bold]Name:[/bold] {attrs.get('name', 'N/A')}\n"
        f"[bold]Model:[/bold] {attrs.get('model_name', 'N/A')}\n"
        f"[bold]Memory Strategy:[/bold] {attrs.get('memory_compaction_strategy', 'N/A')}"
    )

    personality = attrs.get("personality", "")
    if personality:
        preview = personality[:200] + ("..." if len(personality) > 200 else "")
        panel_content += f"\n[bold]Personality:[/bold] {preview}"

    model_params = attrs.get("model_params")
    if model_params:
        panel_content += f"\n[bold]Model Params:[/bold] {json.dumps(model_params)}"

    tool_config = attrs.get("tool_config")
    if tool_config:
        panel_content += f"\n[bold]Tool Config:[/bold] {json.dumps(tool_config)}"

    memory_config = attrs.get("memory_compaction_config")
    if memory_config:
        panel_content += f"\n[bold]Memory Config:[/bold] {json.dumps(memory_config)}"

    cs_id = attrs.get("community_server_id")
    if cs_id:
        panel_content += f"\n[bold]Community Server:[/bold] {cs_id}"

    for ts_field in ("created_at", "updated_at"):
        val = attrs.get(ts_field)
        if val:
            label = ts_field.replace("_", " ").title()
            panel_content += f"\n[bold]{label}:[/bold] {val[:19]}"

    console.print(Panel(panel_content, title="[bold]Agent Personality[/bold]"))


@sim_agent.command("create")
@click.option("--name", required=True, help="Agent name.")
@click.option(
    "--personality", required=True,
    help="Personality text (use @filename to read from file).",
)
@click.option("--model-name", required=True, help="LLM model name.")
@click.option(
    "--memory-strategy", default="sliding_window",
    help="Memory compaction strategy.",
)
@click.pass_context
def sim_agent_create(
    ctx: click.Context,
    name: str,
    personality: str,
    model_name: str,
    memory_strategy: str,
) -> None:
    """Create an agent personality."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if personality.startswith("@"):
        filepath = Path(personality[1:])
        if not filepath.exists():
            error_console.print(f"[red]Error:[/red] File not found: {filepath}")
            sys.exit(1)
        personality = filepath.read_text().strip()

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    payload = {
        "data": {
            "type": "sim-agents",
            "attributes": {
                "name": name,
                "personality": personality,
                "model_name": model_name,
                "memory_compaction_strategy": memory_strategy,
            },
        }
    }

    response = client.post(f"{base_url}/api/v2/sim-agents", headers=headers, json=payload)
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    agent_id = result.get("data", {}).get("id", "N/A")
    agent_name = result.get("data", {}).get("attributes", {}).get("name", "N/A")
    console.print(
        f"[green]\u2713[/green] Created agent [bold]{agent_name}[/bold]: {agent_id}"
    )
