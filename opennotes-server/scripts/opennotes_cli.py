#!/usr/bin/env python3
"""
OpenNotes CLI — administration tool for the OpenNotes server.

Usage:
    uv run scripts/opennotes_cli.py simulation progress <id>
    uv run scripts/opennotes_cli.py simulation results <id>

Environment variables:
    OPENNOTES_API_URL   Base URL of the server (default: http://localhost:8000)
    OPENNOTES_API_KEY   API key for authentication
"""

from __future__ import annotations

import os
import sys
from typing import Any

import click
import httpx
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()

DEFAULT_API_URL = "http://localhost:8000"
API_PREFIX = "/api/v2"


def get_api_url() -> str:
    return os.environ.get("OPENNOTES_API_URL", DEFAULT_API_URL).rstrip("/")


def get_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/vnd.api+json"}
    api_key = os.environ.get("OPENNOTES_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{get_api_url()}{API_PREFIX}{path}"
    try:
        resp = httpx.get(url, headers=get_headers(), params=params, timeout=30.0)
    except httpx.ConnectError:
        console.print(f"[red]Connection refused:[/red] {url}")
        console.print("Is the server running? Set OPENNOTES_API_URL if needed.")
        sys.exit(1)

    if resp.status_code == 404:
        return {"_status": 404}

    if resp.status_code >= 400:
        console.print(f"[red]API error {resp.status_code}:[/red] {resp.text[:500]}")
        sys.exit(1)

    data: dict[str, Any] = resp.json()
    data["_status"] = resp.status_code
    return data


@click.group()
def cli() -> None:
    """OpenNotes administration CLI."""


@cli.group("simulation")
def simulation_group() -> None:
    """Manage simulation runs."""


@simulation_group.command("status")
@click.argument("simulation_id")
def simulation_status(simulation_id: str) -> None:
    """Show basic status of a simulation run."""
    resp = api_get(f"/simulations/{simulation_id}")

    if resp.get("_status") == 404:
        console.print(f"[red]Simulation {simulation_id} not found.[/red]")
        sys.exit(1)

    attrs = resp["data"]["attributes"]

    table = Table(title=f"Simulation {simulation_id[:8]}...")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Status", attrs.get("status", "unknown"))
    table.add_row("Orchestrator", attrs.get("orchestrator_id", "—"))
    table.add_row("Community", attrs.get("community_server_id", "—"))
    table.add_row("Started", attrs.get("started_at") or "—")
    table.add_row("Completed", attrs.get("completed_at") or "—")

    if attrs.get("error_message"):
        table.add_row("Error", attrs["error_message"])

    console.print(table)


@simulation_group.command("progress")
@click.argument("simulation_id")
def simulation_progress(simulation_id: str) -> None:
    """Show detailed progress of a running simulation."""
    status_resp = api_get(f"/simulations/{simulation_id}")

    if status_resp.get("_status") == 404:
        console.print(f"[red]Simulation {simulation_id} not found.[/red]")
        sys.exit(1)

    attrs = status_resp["data"]["attributes"]
    metrics: dict[str, Any] = attrs.get("metrics") or {}

    progress_resp = api_get(f"/simulations/{simulation_id}/progress")
    if progress_resp.get("_status") != 404:
        progress_attrs = progress_resp.get("data", {}).get("attributes", {})
        metrics.update(progress_attrs)

    tree = Tree(f"[bold]Simulation {simulation_id[:8]}... Progress[/bold]")
    tree.add(f"[cyan]Status:[/cyan] {attrs.get('status', 'unknown')}")
    tree.add(f"[cyan]Iterations:[/cyan] {metrics.get('iterations', 0)}")
    tree.add(f"[cyan]Turns Dispatched:[/cyan] {metrics.get('total_turns', 0)}")
    tree.add(f"[cyan]Turns Completed:[/cyan] {metrics.get('turns_completed', 0)}")
    tree.add(
        f"[cyan]Active Agents:[/cyan] {metrics.get('active_agents', metrics.get('agents_spawned', 0) - metrics.get('agents_removed', 0))}"
    )
    tree.add(f"[cyan]Agents Spawned:[/cyan] {metrics.get('agents_spawned', 0)}")
    tree.add(f"[cyan]Agents Removed:[/cyan] {metrics.get('agents_removed', 0)}")
    tree.add(f"[cyan]Notes Written:[/cyan] {metrics.get('notes_written', 0)}")
    tree.add(f"[cyan]Ratings Given:[/cyan] {metrics.get('ratings_given', 0)}")

    if attrs.get("error_message"):
        tree.add(f"[red]Error:[/red] {attrs['error_message']}")

    console.print(tree)


@simulation_group.command("results")
@click.argument("simulation_id")
@click.option("--page", default=1, type=int, help="Page number (1-based)")
@click.option("--agent-id", default=None, help="Filter by agent instance ID")
def simulation_results(simulation_id: str, page: int, agent_id: str | None) -> None:
    """Show simulation results (notes, ratings) with pagination."""
    params: dict[str, Any] = {"page[number]": page}
    if agent_id:
        params["filter[agent_instance_id]"] = agent_id

    resp = api_get(f"/simulations/{simulation_id}/results", params=params)

    if resp.get("_status") == 404:
        console.print(
            "[yellow]Results endpoint not yet available. "
            "Use 'simulation status' or 'simulation progress' instead.[/yellow]"
        )
        sys.exit(0)

    resources = resp.get("data", [])
    meta = resp.get("meta", {})

    if not resources:
        console.print("[dim]No results found.[/dim]")
        return

    table = Table(title=f"Simulation {simulation_id[:8]}... Results (page {page})")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Agent", style="green")
    table.add_column("Content", max_width=60)
    table.add_column("Created", style="dim")

    for resource in resources:
        attrs = resource.get("attributes", {})
        table.add_row(
            resource.get("id", "—")[:8] + "...",
            resource.get("type", "—"),
            attrs.get("agent_instance_id", "—")[:8] + "..."
            if attrs.get("agent_instance_id")
            else "—",
            (attrs.get("content") or attrs.get("summary") or "—")[:60],
            attrs.get("created_at", "—"),
        )

    console.print(table)

    total = meta.get("count")
    if total is not None:
        console.print(f"[dim]Total: {total}[/dim]")


if __name__ == "__main__":
    cli()
