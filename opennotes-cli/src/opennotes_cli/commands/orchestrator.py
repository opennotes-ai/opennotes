from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

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


@click.group()
def orchestrator() -> None:
    """Manage simulation orchestrators."""


@orchestrator.command("list")
@click.option("--page", default=1, type=click.IntRange(1), help="Page number.")
@click.option("--page-size", default=20, type=click.IntRange(1, 100), help="Page size (1-100).")
@click.pass_context
def orchestrator_list(ctx: click.Context, page: int, page_size: int) -> None:
    """List orchestrators."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    params = {"page[number]": page, "page[size]": page_size}
    response = client.get(
        f"{base_url}/api/v2/simulation-orchestrators", headers=headers, params=params
    )
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    items = result.get("data", [])
    total = result.get("meta", {}).get("count", len(items))

    if not items:
        console.print("[yellow]No orchestrators found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", no_wrap=True)
    table.add_column("Name", width=20)
    table.add_column("Max Agents", justify="right", width=10)
    table.add_column("Cadence (s)", justify="right", width=11)
    table.add_column("Removal Rate", justify="right", width=12)
    table.add_column("Max Turns", justify="right", width=10)
    table.add_column("Active", width=6)
    table.add_column("Created At", width=20)

    for item in items:
        attrs = item.get("attributes", {})
        created = (attrs.get("created_at") or "")[:19]
        active = "[green]Yes[/green]" if attrs.get("is_active") else "[red]No[/red]"
        table.add_row(
            item.get("id", "N/A"),
            attrs.get("name", "N/A"),
            str(attrs.get("max_agents", "N/A")),
            str(attrs.get("turn_cadence_seconds", "N/A")),
            f"{attrs.get('removal_rate') or 0:.2f}",
            str(attrs.get("max_turns_per_agent", "N/A")),
            active,
            created,
        )

    console.print(table)
    console.print(f"\n[dim]Total: {total} orchestrator(s)[/dim]")


@orchestrator.command("get")
@click.argument("orchestrator_id")
@click.pass_context
def orchestrator_get(ctx: click.Context, orchestrator_id: str) -> None:
    """Show details of an orchestrator."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    response = client.get(
        f"{base_url}/api/v2/simulation-orchestrators/{orchestrator_id}", headers=headers
    )
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    attrs = result.get("data", {}).get("attributes", {})
    active = "[green]Yes[/green]" if attrs.get("is_active") else "[red]No[/red]"

    panel_content = (
        f"[bold]ID:[/bold] {result.get('data', {}).get('id', 'N/A')}\n"
        f"[bold]Name:[/bold] {attrs.get('name', 'N/A')}\n"
        f"[bold]Active:[/bold] {active}\n"
        f"[bold]Max Agents:[/bold] {attrs.get('max_agents', 'N/A')}\n"
        f"[bold]Turn Cadence:[/bold] {attrs.get('turn_cadence_seconds', 'N/A')}s\n"
        f"[bold]Removal Rate:[/bold] {attrs.get('removal_rate', 'N/A')}\n"
        f"[bold]Max Turns/Agent:[/bold] {attrs.get('max_turns_per_agent', 'N/A')}"
    )

    desc = attrs.get("description")
    if desc:
        panel_content += f"\n[bold]Description:[/bold] {desc}"

    agent_ids = attrs.get("agent_profile_ids")
    if agent_ids:
        panel_content += "\n[bold]Agent Profile IDs:[/bold]"
        for aid in agent_ids:
            panel_content += f"\n  - {aid}"

    scoring = attrs.get("scoring_config")
    if scoring:
        panel_content += f"\n[bold]Scoring Config:[/bold] {json.dumps(scoring, indent=2)}"

    cs_id = attrs.get("community_server_id")
    if cs_id:
        panel_content += f"\n[bold]Community Server:[/bold] {cs_id}"

    for ts_field in ("created_at", "updated_at"):
        val = attrs.get(ts_field)
        if val:
            label = ts_field.replace("_", " ").title()
            panel_content += f"\n[bold]{label}:[/bold] {val[:19]}"

    console.print(Panel(panel_content, title="[bold]Orchestrator[/bold]"))


@orchestrator.command("create")
@click.option("--name", required=True, help="Orchestrator name.")
@click.option("--agent-ids", required=True, help="Comma-separated agent profile UUIDs.")
@click.option("--turn-cadence", required=True, type=int, help="Turn cadence in seconds.")
@click.option("--max-agents", required=True, type=int, help="Maximum concurrent agents.")
@click.option(
    "--removal-rate", required=True, type=float, help="Agent removal rate (0.0-1.0)."
)
@click.option("--max-turns", required=True, type=int, help="Maximum turns per agent.")
@click.option("--description", default=None, help="Orchestrator description.")
@click.pass_context
def orchestrator_create(
    ctx: click.Context,
    name: str,
    agent_ids: str,
    turn_cadence: int,
    max_agents: int,
    removal_rate: float,
    max_turns: int,
    description: str | None,
) -> None:
    """Create an orchestrator."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    agent_id_list = [aid.strip() for aid in agent_ids.split(",") if aid.strip()]

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    attributes: dict[str, Any] = {
        "name": name,
        "turn_cadence_seconds": turn_cadence,
        "max_agents": max_agents,
        "removal_rate": removal_rate,
        "max_turns_per_agent": max_turns,
        "agent_profile_ids": agent_id_list,
    }
    if description:
        attributes["description"] = description

    payload = {
        "data": {
            "type": "simulation-orchestrators",
            "attributes": attributes,
        }
    }

    response = client.post(
        f"{base_url}/api/v2/simulation-orchestrators", headers=headers, json=payload
    )
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    orch_id = result.get("data", {}).get("id", "N/A")
    orch_name = result.get("data", {}).get("attributes", {}).get("name", "N/A")
    console.print(
        f"[green]\u2713[/green] Created orchestrator [bold]{orch_name}[/bold]: {orch_id}"
    )


def _build_update_attributes(
    name: str | None,
    description: str | None,
    max_agents: int | None,
    turn_cadence: int | None,
    removal_rate: float | None,
    max_turns: int | None,
    agent_ids: str | None,
    scoring_config: str | None,
) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    if name is not None:
        attributes["name"] = name
    if description is not None:
        attributes["description"] = description
    if max_agents is not None:
        attributes["max_agents"] = max_agents
    if turn_cadence is not None:
        attributes["turn_cadence_seconds"] = turn_cadence
    if removal_rate is not None:
        attributes["removal_rate"] = removal_rate
    if max_turns is not None:
        attributes["max_turns_per_agent"] = max_turns
    if agent_ids is not None:
        attributes["agent_profile_ids"] = [a.strip() for a in agent_ids.split(",") if a.strip()]
    if scoring_config is not None:
        try:
            attributes["scoring_config"] = json.loads(scoring_config)
        except json.JSONDecodeError:
            error_console.print("[red]Error:[/red] --scoring-config must be valid JSON.")
            sys.exit(1)
    return attributes


@orchestrator.command("update")
@click.argument("orchestrator_id")
@click.option("--name", default=None, help="Orchestrator name.")
@click.option("--description", default=None, help="Description.")
@click.option("--max-agents", default=None, type=int, help="Maximum concurrent agents.")
@click.option("--turn-cadence", default=None, type=int, help="Turn cadence in seconds.")
@click.option("--removal-rate", default=None, type=float, help="Agent removal rate (0.0-1.0).")
@click.option("--max-turns", default=None, type=int, help="Maximum turns per agent.")
@click.option("--agent-ids", default=None, help="Comma-separated agent profile UUIDs.")
@click.option("--scoring-config", default=None, help="Scoring config as JSON string.")
@click.pass_context
def orchestrator_update(
    ctx: click.Context,
    orchestrator_id: str,
    name: str | None,
    description: str | None,
    max_agents: int | None,
    turn_cadence: int | None,
    removal_rate: float | None,
    max_turns: int | None,
    agent_ids: str | None,
    scoring_config: str | None,
) -> None:
    """Update an orchestrator's configuration."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    attributes = _build_update_attributes(
        name, description, max_agents, turn_cadence,
        removal_rate, max_turns, agent_ids, scoring_config,
    )

    if not attributes:
        error_console.print("[red]No update fields specified.[/red]")
        sys.exit(1)

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    payload = {
        "data": {
            "type": "simulation-orchestrators",
            "id": orchestrator_id,
            "attributes": attributes,
        }
    }

    response = client.patch(
        f"{base_url}/api/v2/simulation-orchestrators/{orchestrator_id}",
        headers=headers,
        json=payload,
    )
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    attrs_resp = result.get("data", {}).get("attributes", {})
    console.print(f"[green]\u2713[/green] Updated orchestrator [bold]{orchestrator_id}[/bold]")
    for key, value in sorted(attributes.items()):
        console.print(f"  {key}: {attrs_resp.get(key, value)}")


@orchestrator.command("apply")
@click.argument("orchestrator_id")
@click.option("--simulation", "simulation_id", required=True, help="Simulation run UUID to restart.")
@click.option("--name", default=None, help="Orchestrator name.")
@click.option("--description", default=None, help="Description.")
@click.option("--max-agents", default=None, type=int, help="Maximum concurrent agents.")
@click.option("--turn-cadence", default=None, type=int, help="Turn cadence in seconds.")
@click.option("--removal-rate", default=None, type=float, help="Agent removal rate (0.0-1.0).")
@click.option("--max-turns", default=None, type=int, help="Maximum turns per agent.")
@click.option("--agent-ids", default=None, help="Comma-separated agent profile UUIDs.")
@click.option("--scoring-config", default=None, help="Scoring config as JSON string.")
@click.pass_context
def orchestrator_apply(
    ctx: click.Context,
    orchestrator_id: str,
    simulation_id: str,
    name: str | None,
    description: str | None,
    max_agents: int | None,
    turn_cadence: int | None,
    removal_rate: float | None,
    max_turns: int | None,
    agent_ids: str | None,
    scoring_config: str | None,
) -> None:
    """Update orchestrator config and restart simulation to pick up changes."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    attributes = _build_update_attributes(
        name, description, max_agents, turn_cadence,
        removal_rate, max_turns, agent_ids, scoring_config,
    )

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    if attributes:
        payload = {
            "data": {
                "type": "simulation-orchestrators",
                "id": orchestrator_id,
                "attributes": attributes,
            }
        }
        response = client.patch(
            f"{base_url}/api/v2/simulation-orchestrators/{orchestrator_id}",
            headers=headers,
            json=payload,
        )
        handle_jsonapi_error(response)

        if cli_ctx.json_output:
            result = response.json()
            console.print(json.dumps(result, indent=2, default=str))
        else:
            console.print("[green]\u2713[/green] Updated orchestrator config")

    sim_response = client.get(
        f"{base_url}/api/v2/simulations/{simulation_id}", headers=headers
    )
    handle_jsonapi_error(sim_response)
    sim_status = sim_response.json().get("data", {}).get("attributes", {}).get("status")

    if sim_status == "running":
        pause_response = client.post(
            f"{base_url}/api/v2/simulations/{simulation_id}/pause", headers=headers
        )
        handle_jsonapi_error(pause_response)
        if not cli_ctx.json_output:
            console.print("[yellow]\u23f8[/yellow]  Paused simulation {simulation_id}".format(simulation_id=simulation_id))
    elif sim_status == "paused":
        if not cli_ctx.json_output:
            console.print("[dim]Simulation already paused[/dim]")
    else:
        error_console.print(f"[red]Simulation is '{sim_status}', cannot apply config[/red]")
        sys.exit(1)

    resume_response = client.post(
        f"{base_url}/api/v2/simulations/{simulation_id}/resume", headers=headers
    )
    handle_jsonapi_error(resume_response)

    if cli_ctx.json_output:
        console.print(json.dumps(resume_response.json(), indent=2, default=str))
    else:
        console.print("[green]\u25b6[/green]  Resumed simulation {simulation_id}".format(simulation_id=simulation_id))
        console.print("[green]\u2713[/green] Config applied \u2014 orchestrator will use new settings")
