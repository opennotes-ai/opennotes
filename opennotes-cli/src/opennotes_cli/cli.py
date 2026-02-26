from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import click
import httpx
from trogon import tui

from opennotes_cli.auth import AuthProvider, JwtAuthProvider
from opennotes_cli.http import ENV_URLS

from opennotes_cli.commands.batch import batch
from opennotes_cli.commands.candidates import fact_check
from opennotes_cli.commands.health import health
from opennotes_cli.commands.orchestrator import orchestrator
from opennotes_cli.commands.playground import playground
from opennotes_cli.commands.rechunk import rechunk
from opennotes_cli.commands.search import hybrid_search
from opennotes_cli.commands.sim_agent import sim_agent
from opennotes_cli.commands.simulation import simulation


@dataclass
class CliContext:
    auth: AuthProvider
    json_output: bool
    verbose: bool
    env_name: str
    client: httpx.Client

    @property
    def base_url(self) -> str:
        return self.auth.get_server_url()


def _read_api_key_from_env_file(env_file: Path, verbose: bool = False) -> str | None:
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        if line.startswith("OPENNOTES_API_KEY="):
            return line.split("=", 1)[1]
    return None


@tui()
@click.group()
@click.option(
    "-e",
    "--env",
    default="production",
    type=click.Choice(["local", "staging", "production"]),
    help="Server environment to use.",
)
@click.option(
    "--local",
    "use_local",
    is_flag=True,
    help="Use local server (localhost:8000) with no authentication.",
)
@click.option("--json", "json_output", is_flag=True, help="Output raw JSON.")
@click.option("-v", "--verbose", is_flag=True, help="Show verbose output.")
@click.pass_context
def cli(
    ctx: click.Context,
    env: str,
    use_local: bool,
    json_output: bool,
    verbose: bool,
) -> None:
    """OpenNotes CLI - Interact with opennotes-server endpoints."""
    ctx.ensure_object(dict)

    if use_local:
        env = "local"

    server_url = ENV_URLS.get(env, ENV_URLS["production"])

    api_key: str | None = None
    if env == "local":
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        env_file = (
            project_root / "infrastructure" / "environments" / "local" / ".env.generated"
        )
        api_key = _read_api_key_from_env_file(env_file, verbose=verbose)

    auth = JwtAuthProvider(server_url=server_url, api_key=api_key or "")
    client = httpx.Client(timeout=60.0)

    ctx.obj = CliContext(
        auth=auth,
        json_output=json_output,
        verbose=verbose,
        env_name=env,
        client=client,
    )

    ctx.call_on_close(client.close)


cli.add_command(health)
cli.add_command(hybrid_search)
cli.add_command(rechunk)
cli.add_command(fact_check)
cli.add_command(batch)
cli.add_command(simulation)
cli.add_command(sim_agent)
cli.add_command(orchestrator)
cli.add_command(playground)
