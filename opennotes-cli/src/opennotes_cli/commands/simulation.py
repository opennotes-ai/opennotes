from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


def _read_urls_from_file(path: str) -> list[str]:
    filepath = Path(path)
    if not filepath.exists():
        error_console.print(f"[red]Error:[/red] File not found: {filepath}")
        sys.exit(1)
    urls: list[str] = []
    for line in filepath.read_text().splitlines():
        line = line.strip()
        if line.startswith(("- ", "* ")):
            line = line[2:].strip()
        if line and line.startswith("http"):
            urls.append(line)
    return urls


def _submit_urls_batch(
    client: Any,
    base_url: str,
    headers: dict[str, str],
    community_server_id: str,
    urls: list[str],
) -> str | None:
    payload = {
        "data": {
            "type": "playground-note-requests",
            "attributes": {"urls": urls},
        }
    }
    response = client.post(
        f"{base_url}/api/v2/playgrounds/{community_server_id}/note-requests",
        headers=headers,
        json=payload,
    )
    handle_jsonapi_error(response)
    return response.json().get("data", {}).get("attributes", {}).get("workflow_id")


@simulation.command("launch")
@click.option("--name", default=None, help="Simulation name (used for orchestrator and playground).")
@click.option("--url", "urls", multiple=True, help="URL to add as note request (repeatable).")
@click.option("--urls-from", "urls_file", default=None, help="File with URLs, one per line.")
@click.option("--text", "texts", multiple=True, help="Text content to submit directly (repeatable).")
@click.option("--agent-ids", default=None, help="Comma-separated agent profile UUIDs (default: all).")
@click.option("--max-agents", default=15, type=int, help="Max concurrent agents (default: 15).")
@click.option("--turn-cadence", default=15, type=int, help="Turn cadence in seconds (default: 15).")
@click.option("--removal-rate", default=0.0, type=float, help="Agent removal rate (default: 0.0).")
@click.option("--max-turns", default=50, type=int, help="Max turns per agent (default: 50).")
@click.option("--wait", is_flag=True, help="Poll until simulation completes.")
@click.pass_context
def simulation_launch(
    ctx: click.Context,
    name: str | None,
    urls: tuple[str, ...],
    urls_file: str | None,
    texts: tuple[str, ...],
    agent_ids: str | None,
    max_agents: int,
    turn_cadence: int,
    removal_rate: float,
    max_turns: int,
    wait: bool,
) -> None:
    """Launch a full simulation: create orchestrator, playground, submit content, start sim."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    all_urls = list(urls)
    if urls_file:
        all_urls.extend(_read_urls_from_file(urls_file))

    if not all_urls and not texts:
        error_console.print("[red]Error:[/red] Provide at least one --url, --urls-from, or --text.")
        sys.exit(1)

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    if not name:
        name = f"sim-{uuid.uuid4().hex[:8]}"

    if agent_ids:
        agent_id_list = [a.strip() for a in agent_ids.split(",") if a.strip()]
    else:
        response = client.get(
            f"{base_url}/api/v2/sim-agents",
            headers=headers,
            params={"page[size]": 100},
        )
        handle_jsonapi_error(response)
        items = response.json().get("data", [])
        agent_id_list = [item["id"] for item in items]
        if not agent_id_list:
            error_console.print("[red]Error:[/red] No sim agents found. Create agents first.")
            sys.exit(1)
        if not cli_ctx.json_output:
            console.print(f"[dim]Discovered {len(agent_id_list)} agent(s)[/dim]")

    orch_attributes: dict[str, Any] = {
        "name": name,
        "turn_cadence_seconds": turn_cadence,
        "max_agents": max_agents,
        "removal_rate": removal_rate,
        "max_turns_per_agent": max_turns,
        "agent_profile_ids": agent_id_list,
    }
    orch_payload = {"data": {"type": "simulation-orchestrators", "attributes": orch_attributes}}
    response = client.post(
        f"{base_url}/api/v2/simulation-orchestrators", headers=headers, json=orch_payload
    )
    handle_jsonapi_error(response)
    orch_id = response.json().get("data", {}).get("id")
    if not cli_ctx.json_output:
        console.print(f"[green]\u2713[/green] Created orchestrator: [bold]{orch_id}[/bold]")

    pg_headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)
    pg_payload: dict[str, Any] = {
        "platform": "playground",
        "platform_community_server_id": uuid.uuid4().hex[:16],
        "name": name,
        "is_active": True,
        "is_public": True,
    }
    response = client.post(
        f"{base_url}/api/v1/community-servers", headers=pg_headers, json=pg_payload
    )
    handle_jsonapi_error(response)
    cs_id = response.json().get("id")
    if not cli_ctx.json_output:
        console.print(f"[green]\u2713[/green] Created playground: [bold]{cs_id}[/bold]")

    jsonapi_headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    if all_urls:
        for i in range(0, len(all_urls), 20):
            batch = all_urls[i : i + 20]
            _submit_urls_batch(client, base_url, jsonapi_headers, cs_id, batch)
        if not cli_ctx.json_output:
            console.print(f"[green]\u2713[/green] Submitted {len(all_urls)} URL(s) for processing")

    if texts:
        all_texts = list(texts)
        for i in range(0, len(all_texts), 20):
            batch = all_texts[i : i + 20]
            text_payload = {
                "data": {
                    "type": "playground-note-requests",
                    "attributes": {"texts": batch},
                }
            }
            response = client.post(
                f"{base_url}/api/v2/playgrounds/{cs_id}/note-requests",
                headers=jsonapi_headers,
                json=text_payload,
            )
            handle_jsonapi_error(response)
        if not cli_ctx.json_output:
            console.print(f"[green]\u2713[/green] Submitted {len(texts)} text(s) for processing")

    sim_payload = {
        "data": {
            "type": "simulations",
            "attributes": {
                "orchestrator_id": orch_id,
                "community_server_id": cs_id,
            },
        }
    }
    response = client.post(
        f"{base_url}/api/v2/simulations", headers=jsonapi_headers, json=sim_payload
    )
    handle_jsonapi_error(response)
    result = response.json()
    sim_id = result.get("data", {}).get("id")

    if not cli_ctx.json_output:
        console.print(f"[green]\u2713[/green] Started simulation: [bold]{sim_id}[/bold]")

    if wait:
        if not cli_ctx.json_output:
            console.print("[dim]Waiting for completion...[/dim]\n")
        result = poll_simulation_until_complete(client, base_url, jsonapi_headers, sim_id)

    if cli_ctx.json_output:
        console.print(json.dumps({
            "orchestrator_id": orch_id,
            "community_server_id": cs_id,
            "simulation_id": sim_id,
            "result": result,
        }, indent=2, default=str))
        return

    cli_prefix = get_cli_prefix(cli_ctx.env_name)
    console.print(
        f"\n[dim]Monitor:[/dim]  {cli_prefix} simulation status {sim_id}"
    )
    console.print(
        f"[dim]Update:[/dim]   {cli_prefix} orchestrator apply {orch_id} --simulation {sim_id} --max-agents 20"
    )


@simulation.command("analysis")
@click.argument("simulation_id")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "markdown"]),
    default="terminal",
    help="Output format.",
)
@click.pass_context
def simulation_analysis(
    ctx: click.Context, simulation_id: str, output_format: str
) -> None:
    """Show analysis results for a simulation run."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    response = client.get(
        f"{base_url}/api/v2/simulations/{simulation_id}/analysis", headers=headers
    )
    handle_jsonapi_error(response)

    result = response.json()

    if cli_ctx.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    attrs = result.get("data", {}).get("attributes", {})

    if _is_empty_analysis(attrs):
        if output_format == "markdown":
            click.echo(f"# Simulation Analysis: {simulation_id}\n\nAnalysis not available yet — simulation may still be running.")
        else:
            console.print("[yellow]Analysis not available yet — simulation may still be running.[/yellow]")
        return

    if output_format == "markdown":
        _render_analysis_markdown(simulation_id, attrs)
    else:
        _render_analysis_terminal(attrs)


def _is_empty_analysis(attrs: dict[str, Any]) -> bool:
    if not attrs:
        return True
    total_ratings = attrs.get("rating_distribution", {}).get("total_ratings", 0)
    total_notes = attrs.get("consensus_metrics", {}).get("total_notes_rated", 0)
    total_scores = attrs.get("scoring_coverage", {}).get("total_scores_computed", 0)
    return total_ratings == 0 and total_notes == 0 and total_scores == 0


def _render_analysis_terminal(attrs: dict[str, Any]) -> None:
    rating_dist = attrs.get("rating_distribution", {})
    overall = rating_dist.get("overall", {})
    total_ratings = rating_dist.get("total_ratings", 0)

    table = Table(title="Rating Distribution", show_header=True, header_style="bold")
    table.add_column("Rating")
    table.add_column("Count", justify="right")
    table.add_column("Percentage", justify="right")
    for rating, count in sorted(overall.items()):
        pct = (count / total_ratings * 100) if total_ratings > 0 else 0
        table.add_row(rating, str(count), f"{pct:.1f}%")
    total_pct = "100.0%" if total_ratings > 0 else "N/A"
    table.add_row("[bold]Total[/bold]", f"[bold]{total_ratings}[/bold]", f"[bold]{total_pct}[/bold]")
    console.print(table)

    per_agent = rating_dist.get("per_agent", [])
    if per_agent:
        agent_table = Table(
            title="Per-Agent Rating Breakdown", show_header=True, header_style="bold"
        )
        agent_table.add_column("Agent")
        agent_table.add_column("Ratings", justify="right")
        agent_table.add_column("Distribution")
        for agent in per_agent:
            dist_parts = [f"{k}: {v}" for k, v in agent.get("distribution", {}).items()]
            agent_table.add_row(
                agent.get("agent_name", "N/A"),
                str(agent.get("total", 0)),
                ", ".join(dist_parts),
            )
        console.print(agent_table)

    consensus = attrs.get("consensus_metrics", {})
    consensus_content = (
        f"[bold]Mean agreement:[/bold] {consensus.get('mean_agreement', 'N/A')}\n"
        f"[bold]Polarization index:[/bold] {consensus.get('polarization_index', 'N/A')}\n"
        f"[bold]Notes with consensus:[/bold] {consensus.get('notes_with_consensus', 'N/A')}\n"
        f"[bold]Notes with disagreement:[/bold] {consensus.get('notes_with_disagreement', 'N/A')}\n"
        f"[bold]Total notes rated:[/bold] {consensus.get('total_notes_rated', 'N/A')}"
    )
    console.print(Panel(consensus_content, title="[bold]Consensus Metrics[/bold]"))

    scoring = attrs.get("scoring_coverage", {})
    scoring_content = (
        f"[bold]Current tier:[/bold] {scoring.get('current_tier', 'N/A')}\n"
        f"[bold]Total scores computed:[/bold] {scoring.get('total_scores_computed', 'N/A')}"
    )
    console.print(Panel(scoring_content, title="[bold]Scoring Coverage[/bold]"))

    tier_dist = scoring.get("tier_distribution", {})
    if tier_dist:
        tier_table = Table(show_header=True, header_style="bold")
        tier_table.add_column("Tier")
        tier_table.add_column("Count", justify="right")
        for tier, count in sorted(tier_dist.items()):
            tier_table.add_row(tier, str(count))
        console.print(tier_table)

    scorer_bd = scoring.get("scorer_breakdown", {})
    if scorer_bd:
        scorer_table = Table(show_header=True, header_style="bold")
        scorer_table.add_column("Scorer")
        scorer_table.add_column("Count", justify="right")
        for scorer, count in sorted(scorer_bd.items()):
            scorer_table.add_row(scorer, str(count))
        console.print(scorer_table)

    scoring_notes = scoring.get("notes_by_status", {})
    if scoring_notes:
        sn_table = Table(show_header=True, header_style="bold")
        sn_table.add_column("Status")
        sn_table.add_column("Count", justify="right")
        for status, count in sorted(scoring_notes.items()):
            sn_table.add_row(status, str(count))
        console.print(sn_table)

    behaviors = attrs.get("agent_behaviors", [])
    if behaviors:
        beh_table = Table(title="Agent Behaviors", show_header=True, header_style="bold")
        beh_table.add_column("Agent")
        beh_table.add_column("Notes", justify="right")
        beh_table.add_column("Ratings", justify="right")
        beh_table.add_column("Turns", justify="right")
        beh_table.add_column("State")
        beh_table.add_column("Top Actions")
        for agent in behaviors:
            actions = agent.get("action_distribution", {})
            top = sorted(actions.items(), key=lambda x: x[1], reverse=True)[:3]
            top_str = ", ".join(f"{k}: {v}" for k, v in top)
            beh_table.add_row(
                agent.get("agent_name", "N/A"),
                str(agent.get("notes_written", 0)),
                str(agent.get("ratings_given", 0)),
                str(agent.get("turn_count", 0)),
                agent.get("state", "N/A"),
                top_str,
            )
        console.print(beh_table)

    quality = attrs.get("note_quality", {})
    avg_score = quality.get("avg_helpfulness_score")
    avg_display = f"{avg_score}" if avg_score is not None else "N/A"
    quality_content = f"[bold]Avg helpfulness score:[/bold] {avg_display}"
    console.print(Panel(quality_content, title="[bold]Note Quality[/bold]"))

    quality_status = quality.get("notes_by_status", {})
    if quality_status:
        qs_table = Table(show_header=True, header_style="bold")
        qs_table.add_column("Status")
        qs_table.add_column("Count", justify="right")
        for status, count in sorted(quality_status.items()):
            qs_table.add_row(status, str(count))
        console.print(qs_table)

    quality_class = quality.get("notes_by_classification", {})
    if quality_class:
        qc_table = Table(show_header=True, header_style="bold")
        qc_table.add_column("Classification")
        qc_table.add_column("Count", justify="right")
        for cls, count in sorted(quality_class.items()):
            qc_table.add_row(cls, str(count))
        console.print(qc_table)


def _render_analysis_markdown(simulation_id: str, attrs: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append(f"# Simulation Analysis: {simulation_id}")
    lines.append("")

    rating_dist = attrs.get("rating_distribution", {})
    overall = rating_dist.get("overall", {})
    total_ratings = rating_dist.get("total_ratings", 0)

    lines.append("## Rating Distribution")
    lines.append("")
    lines.append("| Rating | Count | % |")
    lines.append("|--------|-------|---|")
    for rating, count in sorted(overall.items()):
        pct = (count / total_ratings * 100) if total_ratings > 0 else 0
        lines.append(f"| {rating} | {count} | {pct:.1f}% |")
    total_pct = "100.0%" if total_ratings > 0 else "N/A"
    lines.append(f"| **Total** | **{total_ratings}** | **{total_pct}** |")
    lines.append("")

    per_agent = rating_dist.get("per_agent", [])
    if per_agent:
        lines.append("### Per-Agent Breakdown")
        lines.append("")
        for agent in per_agent:
            name = agent.get("agent_name", "N/A")
            total = agent.get("total", 0)
            lines.append(f"**{name}** ({total} ratings)")
            dist = agent.get("distribution", {})
            for r, c in sorted(dist.items()):
                lines.append(f"- {r}: {c}")
            lines.append("")

    consensus = attrs.get("consensus_metrics", {})
    lines.append("## Consensus Metrics")
    lines.append("")
    lines.append(f"- Mean agreement: {consensus.get('mean_agreement', 'N/A')}")
    lines.append(f"- Polarization index: {consensus.get('polarization_index', 'N/A')}")
    lines.append(f"- Notes with consensus: {consensus.get('notes_with_consensus', 'N/A')}")
    lines.append(
        f"- Notes with disagreement: {consensus.get('notes_with_disagreement', 'N/A')}"
    )
    lines.append(f"- Total notes rated: {consensus.get('total_notes_rated', 'N/A')}")
    lines.append("")

    scoring = attrs.get("scoring_coverage", {})
    lines.append("## Scoring Coverage")
    lines.append("")
    lines.append(f"- Current tier: {scoring.get('current_tier', 'N/A')}")
    lines.append(f"- Total scores computed: {scoring.get('total_scores_computed', 'N/A')}")
    lines.append("")

    tier_dist = scoring.get("tier_distribution", {})
    if tier_dist:
        lines.append("### Tier Distribution")
        lines.append("")
        lines.append("| Tier | Count |")
        lines.append("|------|-------|")
        for tier, count in sorted(tier_dist.items()):
            lines.append(f"| {tier} | {count} |")
        lines.append("")

    scorer_bd = scoring.get("scorer_breakdown", {})
    if scorer_bd:
        lines.append("### Scorer Breakdown")
        lines.append("")
        lines.append("| Scorer | Count |")
        lines.append("|--------|-------|")
        for scorer, count in sorted(scorer_bd.items()):
            lines.append(f"| {scorer} | {count} |")
        lines.append("")

    scoring_notes = scoring.get("notes_by_status", {})
    if scoring_notes:
        lines.append("### Notes by Status")
        lines.append("")
        lines.append("| Status | Count |")
        lines.append("|--------|-------|")
        for status, count in sorted(scoring_notes.items()):
            lines.append(f"| {status} | {count} |")
        lines.append("")

    behaviors = attrs.get("agent_behaviors", [])
    if behaviors:
        lines.append("## Agent Behaviors")
        lines.append("")
        lines.append("| Agent | Notes Written | Ratings Given | Turns | State |")
        lines.append("|-------|---------------|---------------|-------|-------|")
        for agent in behaviors:
            lines.append(
                f"| {agent.get('agent_name', 'N/A')}"
                f" | {agent.get('notes_written', 0)}"
                f" | {agent.get('ratings_given', 0)}"
                f" | {agent.get('turn_count', 0)}"
                f" | {agent.get('state', 'N/A')} |"
            )
        lines.append("")

    quality = attrs.get("note_quality", {})
    avg_score = quality.get("avg_helpfulness_score")
    avg_display = str(avg_score) if avg_score is not None else "N/A"

    lines.append("## Note Quality")
    lines.append("")
    lines.append(f"- Avg helpfulness score: {avg_display}")
    lines.append("")

    quality_status = quality.get("notes_by_status", {})
    if quality_status:
        lines.append("### Notes by Status")
        lines.append("")
        lines.append("| Status | Count |")
        lines.append("|--------|-------|")
        for status, count in sorted(quality_status.items()):
            lines.append(f"| {status} | {count} |")
        lines.append("")

    quality_class = quality.get("notes_by_classification", {})
    if quality_class:
        lines.append("### Notes by Classification")
        lines.append("")
        lines.append("| Classification | Count |")
        lines.append("|----------------|-------|")
        for cls, count in sorted(quality_class.items()):
            lines.append(f"| {cls} | {count} |")
        lines.append("")

    click.echo("\n".join(lines))
