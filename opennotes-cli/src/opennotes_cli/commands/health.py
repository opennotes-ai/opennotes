from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import click
import httpx
from rich.console import Console

if TYPE_CHECKING:
    from opennotes_cli.cli import CliContext

console = Console()
error_console = Console(stderr=True)


@click.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Check server connectivity and authentication."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url

    if not cli_ctx.json_output:
        console.print(f"\n[bold]Checking {cli_ctx.env_name} environment[/bold]")
        console.print(f"[dim]URL: {base_url}[/dim]\n")

    results: dict[str, Any] = {
        "environment": cli_ctx.env_name,
        "url": base_url,
        "checks": {},
    }

    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print("[dim]Checking server connectivity...[/dim]")
    try:
        headers: dict[str, str] = {}
        h = cli_ctx.auth.get_headers()
        if "Authorization" in h:
            headers["Authorization"] = h["Authorization"]

        response = client.get(f"{base_url}/api/v2/scoring/health", headers=headers)
        if response.status_code == 200:
            results["checks"]["server"] = {"status": "ok"}
            if not cli_ctx.json_output:
                console.print("[green]\u2713[/green] Server reachable")
        else:
            results["checks"]["server"] = {
                "status": "failed",
                "code": response.status_code,
            }
            if not cli_ctx.json_output:
                console.print(f"[red]\u2717[/red] Server returned {response.status_code}")
    except httpx.RequestError as e:
        results["checks"]["server"] = {"status": "failed", "error": str(e)}
        if not cli_ctx.json_output:
            console.print(f"[red]\u2717[/red] Connection failed: {e}")

    if cli_ctx.json_output:
        console.print(json.dumps(results, indent=2))
    else:
        all_ok = all(
            c.get("status") == "ok" for c in results["checks"].values()
        )
        if all_ok:
            console.print("\n[bold green]All checks passed![/bold green]")
        else:
            console.print("\n[bold red]Some checks failed.[/bold red]")
