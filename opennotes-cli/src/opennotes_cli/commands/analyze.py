from __future__ import annotations

import json
import sys
import time
from typing import TYPE_CHECKING, Any

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from opennotes_cli.display import handle_jsonapi_error
from opennotes_cli.formatting import format_id, resolve_id
from opennotes_cli.http import add_csrf, get_csrf_token, handle_error_response

if TYPE_CHECKING:
    from opennotes_cli.cli import CliContext

console = Console()
error_console = Console(stderr=True)

ANALYSIS_POLL_INTERVAL = 2.0
ANALYSIS_POLL_MAX_RETRIES = 30


def _fetch_analysis(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    community_server_id: str,
) -> dict[str, Any] | None:
    url = f"{base_url}/api/v2/community-servers/{community_server_id}/scoring-analysis"
    try:
        response = client.get(url, headers=headers)
    except httpx.ConnectError:
        error_console.print(
            f"[red]Error:[/red] Could not connect to server at {base_url}"
        )
        sys.exit(1)
    except httpx.TimeoutException:
        error_console.print(f"[red]Error:[/red] Connection to {base_url} timed out")
        sys.exit(1)
    if response.status_code == 404:
        return None
    handle_jsonapi_error(response)
    return response.json()


def _trigger_rescore(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    csrf_token: str | None,
    community_server_id: str,
) -> None:
    score_headers = add_csrf(dict(headers), csrf_token)
    url = f"{base_url}/api/v2/community-servers/{community_server_id}/score"
    try:
        response = client.post(url, headers=score_headers)
    except httpx.ConnectError:
        error_console.print(
            f"[red]Error:[/red] Could not connect to server at {base_url}"
        )
        sys.exit(1)
    except httpx.TimeoutException:
        error_console.print(f"[red]Error:[/red] Connection to {base_url} timed out")
        sys.exit(1)

    if response.status_code == 409:
        error_console.print(
            "[yellow]Scoring is already in progress for this community server.[/yellow]"
        )
        return

    handle_error_response(response)
    result = response.json()

    workflow_id = result.get("workflow_id", "N/A")
    console.print(
        f"[green]\u2713[/green] Scoring dispatched: workflow [bold]{workflow_id}[/bold]"
    )
    console.print("[dim]Scoring is running in the background.[/dim]")


def _wait_for_analysis(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    community_server_id: str,
    display_community_server_id: str,
    interval: float | None = None,
    max_retries: int | None = None,
) -> dict[str, Any]:
    interval = ANALYSIS_POLL_INTERVAL if interval is None else interval
    max_retries = ANALYSIS_POLL_MAX_RETRIES if max_retries is None else max_retries

    for attempt in range(max_retries):
        data = _fetch_analysis(client, base_url, headers, community_server_id)
        if data is not None:
            return data
        if attempt < max_retries - 1:
            time.sleep(interval)

    error_console.print(
        "[red]Error:[/red] Timed out waiting for a scoring snapshot "
        f"for community server {display_community_server_id}."
    )
    error_console.print(
        "[dim]Scoring may still be running. Re-run `mise run cli -- analyze mf "
        f"{display_community_server_id}` in a few moments.[/dim]"
    )
    sys.exit(1)


def _render_rater_table(rater_factors: list[dict[str, Any]], fmt: str) -> str | None:
    if fmt == "md":
        lines = ["## Rater Factor Matrix", ""]
        lines.append("| Agent | Archetype | Intercept | Factor1 |")
        lines.append("|-------|-----------|-----------|---------|")
        for rf in sorted(
            rater_factors, key=lambda x: x.get("factor1", 0), reverse=True
        ):
            name = rf.get("agent_name") or rf.get("rater_id", "?")
            archetype = rf.get("short_description") or ""
            lines.append(
                f"| {name} | {archetype} | {rf.get('intercept', 0):.4f} | {rf.get('factor1', 0):.4f} |"
            )
        return "\n".join(lines)

    table = Table(title="Rater Factor Matrix", show_header=True, header_style="bold")
    table.add_column("Agent", no_wrap=True)
    table.add_column("Archetype", no_wrap=True)
    table.add_column("Intercept", justify="right")
    table.add_column("Factor1", justify="right")

    for rf in sorted(rater_factors, key=lambda x: x.get("factor1", 0), reverse=True):
        name = rf.get("agent_name") or rf.get("rater_id", "?")
        archetype = rf.get("short_description") or ""
        intercept = rf.get("intercept", 0)
        factor1 = rf.get("factor1", 0)
        f1_color = "green" if factor1 > 0 else "red" if factor1 < 0 else "white"
        table.add_row(
            name,
            archetype,
            f"{intercept:.4f}",
            f"[{f1_color}]{factor1:.4f}[/{f1_color}]",
        )
    console.print(table)
    return None


def _render_note_table(note_factors: list[dict[str, Any]], fmt: str) -> str | None:
    if fmt == "md":
        lines = ["## Note Factor Matrix", ""]
        lines.append("| Note ID | Author | Archetype | Intercept | Factor1 | Status |")
        lines.append("|---------|--------|-----------|-----------|---------|--------|")
        for nf in sorted(
            note_factors, key=lambda x: x.get("intercept", 0), reverse=True
        ):
            nid = nf.get("note_id") or "?"
            author = nf.get("author_agent_name") or "-"
            archetype = nf.get("author_short_description") or ""
            status = nf.get("status") or "-"
            lines.append(
                f"| {nid} | {author} | {archetype} | {nf.get('intercept', 0):.4f} | "
                f"{nf.get('factor1', 0):.4f} | {status} |"
            )
        return "\n".join(lines)

    table = Table(title="Note Factor Matrix", show_header=True, header_style="bold")
    table.add_column("Note ID")
    table.add_column("Author", no_wrap=True)
    table.add_column("Archetype", no_wrap=True)
    table.add_column("Intercept", justify="right")
    table.add_column("Factor1", justify="right")
    table.add_column("Status")

    for nf in sorted(note_factors, key=lambda x: x.get("intercept", 0), reverse=True):
        nid = format_id(nf.get("note_id"), use_huuid=False)
        author = nf.get("author_agent_name") or "-"
        archetype = nf.get("author_short_description") or ""
        status = nf.get("status") or "-"
        table.add_row(
            nid,
            author,
            archetype,
            f"{nf.get('intercept', 0):.4f}",
            f"{nf.get('factor1', 0):.4f}",
            status,
        )
    console.print(table)
    return None


def _render_correlation(rater_factors: list[dict[str, Any]], fmt: str) -> str | None:
    from opennotes_cli.analysis.correlation import compute_correlation_matrix

    result = compute_correlation_matrix(rater_factors)

    if fmt == "md":
        lines = ["## Rater Correlation Matrix (Cosine Similarity)", ""]
        header = "| |" + "|".join(f" {label[:6]} " for label in result.labels) + "|"
        sep = "|---|" + "|".join("---:" for _ in result.labels) + "|"
        lines.extend([header, sep])
        for i, label in enumerate(result.labels):
            row = f"| {label[:6]} |"
            for j in range(len(result.labels)):
                row += f" {result.similarity_matrix[i, j]:.2f} |"
            lines.append(row)

        lines.extend(["", "## Agent Clusters", ""])
        for c in result.clusters:
            lines.append(
                f"**Cluster {c.cluster_id}** (mean sim: {c.mean_similarity:.3f}): {', '.join(c.members)}"
            )

        lines.extend(["", "## Most Similar Pairs", ""])
        for a, b, s in result.most_similar_pairs:
            lines.append(f"- {a} <-> {b}: {s:.4f}")

        lines.extend(["", "## Most Different Pairs", ""])
        for a, b, s in result.most_different_pairs:
            lines.append(f"- {a} <-> {b}: {s:.4f}")

        return "\n".join(lines)

    n = len(result.labels)
    if n <= 12:
        table = Table(
            title="Rater Correlation Matrix (Cosine Similarity)",
            show_header=True,
            header_style="bold",
        )
        table.add_column("", no_wrap=True, width=8)
        for label in result.labels:
            table.add_column(label[:6], justify="right", width=7)
        for i, label in enumerate(result.labels):
            row_vals = []
            for j in range(n):
                val = result.similarity_matrix[i, j]
                if i == j:
                    row_vals.append("[dim]1.00[/dim]")
                elif val > 0.9:
                    row_vals.append(f"[green]{val:.2f}[/green]")
                elif val < 0.5:
                    row_vals.append(f"[red]{val:.2f}[/red]")
                else:
                    row_vals.append(f"{val:.2f}")
            table.add_row(label[:8], *row_vals)
        console.print(table)

    console.print()
    cluster_table = Table(title="Agent Clusters", show_header=True, header_style="bold")
    cluster_table.add_column("Cluster", justify="center", width=8)
    cluster_table.add_column("Members")
    cluster_table.add_column("Mean Sim", justify="right", width=10)
    for c in result.clusters:
        cluster_table.add_row(
            str(c.cluster_id), ", ".join(c.members), f"{c.mean_similarity:.3f}"
        )
    console.print(cluster_table)

    console.print()
    pairs_table = Table(title="Extreme Pairs", show_header=True, header_style="bold")
    pairs_table.add_column("Type", width=12)
    pairs_table.add_column("Agent A")
    pairs_table.add_column("Agent B")
    pairs_table.add_column("Similarity", justify="right")
    for a, b, s in result.most_similar_pairs[:3]:
        pairs_table.add_row("[green]Similar[/green]", a, b, f"{s:.4f}")
    for a, b, s in result.most_different_pairs[:3]:
        pairs_table.add_row("[red]Different[/red]", a, b, f"{s:.4f}")
    console.print(pairs_table)
    return None


def _render_profile_recovery(
    rater_factors: list[dict[str, Any]], fmt: str
) -> str | None:
    from opennotes_cli.analysis.profile_recovery import compute_profile_recovery

    result = compute_profile_recovery(rater_factors)

    if result.n_agents_matched < 3:
        msg = f"Insufficient matched agents ({result.n_agents_matched}/{result.n_agents_total}) for profile recovery."
        if fmt == "md":
            return f"## Profile Recovery\n\n{msg}"
        console.print(f"\n[yellow]{msg}[/yellow]")
        return None

    if fmt == "md":
        lines = ["## Profile Recovery: Intended vs Revealed Persona", ""]
        lines.append(
            f"Matched {result.n_agents_matched}/{result.n_agents_total} agents to archetype assignments."
        )
        lines.append("")
        lines.append(
            f"**Pearson r:** {result.archetype_factor_correlation:.4f} (p={result.archetype_factor_p_value:.4f})"
        )
        lines.append(
            f"**Spearman rho:** {result.archetype_factor_spearman:.4f} (p={result.archetype_factor_spearman_p:.4f})"
        )
        lines.append("")
        lines.append(
            "| Agent | D-I | D-II.A | E-II | Intercept | Factor1 | Closest (archetype) | Closest (factors) | Match |"
        )
        lines.append(
            "|-------|-----|--------|------|-----------|---------|---------------------|--------------------|----|"
        )
        for ac in result.agent_comparisons:
            dims = ac["dimensions"]
            match_sym = "Y" if ac["match"] else "N"
            lines.append(
                f"| {ac['name']} | {dims['D-I'][:4]} | {dims['D-II.A'][:4]} | "
                f"{dims['E-II'][:4]} | {ac['intercept']:.3f} | {ac['factor1']:.3f} | "
                f"{ac['closest_by_archetype']} | {ac['closest_by_factors']} | {match_sym} |"
            )
        return "\n".join(lines)

    console.print()
    console.print(
        Panel(
            f"[bold]Matched:[/bold] {result.n_agents_matched}/{result.n_agents_total} agents\n"
            f"[bold]Pearson r:[/bold] {result.archetype_factor_correlation:.4f} (p={result.archetype_factor_p_value:.4f})\n"
            f"[bold]Spearman rho:[/bold] {result.archetype_factor_spearman:.4f} (p={result.archetype_factor_spearman_p:.4f})",
            title="[bold]Profile Recovery: Intended vs Revealed[/bold]",
        )
    )

    table = Table(title="Agent Comparison", show_header=True, header_style="bold")
    table.add_column("Agent", no_wrap=True)
    table.add_column("Participation", width=8)
    table.add_column("Epistemic", width=8)
    table.add_column("Intercept", justify="right")
    table.add_column("Factor1", justify="right")
    table.add_column("Closest (arch)", no_wrap=True)
    table.add_column("Closest (fac)", no_wrap=True)
    table.add_column("Match", justify="center", width=5)

    for ac in result.agent_comparisons:
        dims = ac["dimensions"]
        match_color = "green" if ac["match"] else "red"
        match_sym = "Y" if ac["match"] else "N"
        table.add_row(
            ac["name"],
            dims.get("D-I", "?")[:8],
            dims.get("E-II", "?")[:8],
            f"{ac['intercept']:.3f}",
            f"{ac['factor1']:.3f}",
            ac.get("closest_by_archetype") or "?",
            ac.get("closest_by_factors") or "?",
            f"[{match_color}]{match_sym}[/{match_color}]",
        )
    console.print(table)
    return None


@click.group()
def analyze() -> None:
    """Analysis tools for community server data."""


def _fetch_history(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    community_server_id: str,
) -> list[dict[str, Any]]:
    url = f"{base_url}/api/v2/community-servers/{community_server_id}/scoring-history"
    try:
        response = client.get(url, headers=headers)
    except httpx.ConnectError:
        error_console.print(
            f"[red]Error:[/red] Could not connect to server at {base_url}"
        )
        sys.exit(1)
    except httpx.TimeoutException:
        error_console.print(f"[red]Error:[/red] Connection to {base_url} timed out")
        sys.exit(1)
    handle_jsonapi_error(response)
    data = response.json()
    return [resource.get("attributes", {}) for resource in data.get("data", [])]


def _fetch_history_snapshot(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    community_server_id: str,
    timestamp: str,
) -> dict[str, Any] | None:
    url = f"{base_url}/api/v2/community-servers/{community_server_id}/scoring-history/{timestamp}"
    try:
        response = client.get(url, headers=headers)
    except httpx.ConnectError:
        error_console.print(
            f"[red]Error:[/red] Could not connect to server at {base_url}"
        )
        sys.exit(1)
    except httpx.TimeoutException:
        error_console.print(f"[red]Error:[/red] Connection to {base_url} timed out")
        sys.exit(1)
    if response.status_code == 404:
        return None
    handle_jsonapi_error(response)
    data = response.json()
    return data.get("data", {}).get("attributes", {}).get("snapshot")


@analyze.command("mf")
@click.argument("community_server_id")
@click.option("--rescore", is_flag=True, help="Trigger fresh scoring before analysis")
@click.option(
    "--no-prompt", is_flag=True, help="Don't prompt for rescore if no snapshot exists"
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "md"]),
    default="table",
    help="Output format",
)
@click.option(
    "--sections",
    type=str,
    default="all",
    help="Sections to show: factors,correlation,recovery or 'all'",
)
@click.option(
    "--history", is_flag=True, help="List available historical scoring snapshots"
)
@click.option(
    "--snapshot-date",
    type=str,
    default=None,
    help="Fetch and analyze a historical snapshot by timestamp",
)
@click.pass_context
def mf_analysis(
    ctx: click.Context,
    community_server_id: str,
    rescore: bool,
    no_prompt: bool,
    fmt: str,
    sections: str,
    history: bool,
    snapshot_date: str | None,
) -> None:
    """Analyze MF scoring factors for a community server."""
    try:
        community_server_id = resolve_id(community_server_id)
    except click.BadParameter as e:
        error_console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client
    headers = cli_ctx.auth.get_headers()
    display_community_server_id = format_id(community_server_id, cli_ctx.use_huuid)

    if cli_ctx.json_output:
        fmt = "json"

    if history:
        entries = _fetch_history(client, base_url, headers, community_server_id)
        if not entries:
            error_console.print("[yellow]No historical snapshots found.[/yellow]")
            sys.exit(0)

        if fmt == "json":
            console.print(json.dumps(entries, indent=2, default=str))
            return

        table = Table(title="Scoring History", show_header=True, header_style="bold")
        table.add_column("Timestamp", no_wrap=True)
        table.add_column("Size", justify="right")
        for entry in entries:
            size_kb = entry.get("size", 0) / 1024
            table.add_row(entry.get("timestamp", "?"), f"{size_kb:.1f} KB")
        console.print(table)
        return

    if snapshot_date:
        snapshot = _fetch_history_snapshot(
            client, base_url, headers, community_server_id, snapshot_date
        )
        if snapshot is None:
            error_console.print(
                f"[red]Error:[/red] No snapshot found for timestamp '{snapshot_date}'"
            )
            sys.exit(1)

        if fmt == "json":
            console.print(json.dumps(snapshot, indent=2, default=str))
            return

        rater_factors = snapshot.get("rater_factors", [])
        note_factors = snapshot.get("note_factors", [])

        console.print(
            Panel(
                f"[bold]Snapshot:[/bold] {snapshot_date}\n"
                f"[bold]Tier:[/bold] {snapshot.get('tier', 'N/A')}\n"
                f"[bold]Global Intercept:[/bold] {snapshot.get('global_intercept', 0):.4f}\n"
                f"[bold]Raters:[/bold] {snapshot.get('rater_count', 0)} | "
                f"[bold]Notes:[/bold] {snapshot.get('note_count', 0)}",
                title="[bold blue]Historical Scoring Snapshot[/bold blue]",
            )
        )
        _render_rater_table(rater_factors, "table")
        console.print()
        _render_note_table(note_factors, "table")
        return

    csrf_token = None
    if rescore:
        try:
            csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
        except httpx.ConnectError:
            error_console.print(
                f"[red]Error:[/red] Could not connect to server at {base_url}"
            )
            sys.exit(1)
        except httpx.TimeoutException:
            error_console.print(f"[red]Error:[/red] Connection to {base_url} timed out")
            sys.exit(1)
        _trigger_rescore(client, base_url, headers, csrf_token, community_server_id)
        data = _wait_for_analysis(
            client,
            base_url,
            headers,
            community_server_id,
            display_community_server_id,
        )
    else:
        data = _fetch_analysis(client, base_url, headers, community_server_id)

    if data is None and not no_prompt and not rescore:
        if click.confirm("No scoring snapshot found. Trigger a scoring run?"):
            try:
                csrf_token = csrf_token or get_csrf_token(
                    client, base_url, cli_ctx.auth
                )
            except httpx.ConnectError:
                error_console.print(
                    f"[red]Error:[/red] Could not connect to server at {base_url}"
                )
                sys.exit(1)
            except httpx.TimeoutException:
                error_console.print(
                    f"[red]Error:[/red] Connection to {base_url} timed out"
                )
                sys.exit(1)
            _trigger_rescore(client, base_url, headers, csrf_token, community_server_id)
            data = _wait_for_analysis(
                client,
                base_url,
                headers,
                community_server_id,
                display_community_server_id,
            )

    if data is None:
        error_console.print(
            "[yellow]No scoring snapshot available for this community server.[/yellow]"
        )
        sys.exit(1)

    if fmt == "json":
        console.print(json.dumps(data, indent=2, default=str))
        return

    attrs = data.get("data", {}).get("attributes", {})
    rater_factors = attrs.get("rater_factors", [])
    note_factors = attrs.get("note_factors", [])

    show_sections = (
        set(sections.split(","))
        if sections != "all"
        else {"factors", "correlation", "recovery"}
    )

    if fmt == "md":
        md_parts = [
            f"# MF Scoring Analysis: {display_community_server_id}",
            "",
            f"**Scored at:** {attrs.get('scored_at', 'N/A')}",
            f"**Tier:** {attrs.get('tier', 'N/A')}",
            f"**Global Intercept:** {attrs.get('global_intercept', 0):.4f}",
            f"**Raters:** {attrs.get('rater_count', 0)} | **Notes:** {attrs.get('note_count', 0)}",
            "",
        ]

        if "factors" in show_sections:
            r = _render_rater_table(rater_factors, "md")
            if r:
                md_parts.append(r)
            md_parts.append("")
            r = _render_note_table(note_factors, "md")
            if r:
                md_parts.append(r)
            md_parts.append("")

        if "correlation" in show_sections and len(rater_factors) >= 3:
            r = _render_correlation(rater_factors, "md")
            if r:
                md_parts.append(r)
            md_parts.append("")

        if "recovery" in show_sections:
            r = _render_profile_recovery(rater_factors, "md")
            if r:
                md_parts.append(r)

        click.echo("\n".join(md_parts))
        return

    console.print(
        Panel(
            f"[bold]Scored at:[/bold] {attrs.get('scored_at', 'N/A')}\n"
            f"[bold]Tier:[/bold] {attrs.get('tier', 'N/A')}\n"
            f"[bold]Global Intercept:[/bold] {attrs.get('global_intercept', 0):.4f}\n"
            f"[bold]Raters:[/bold] {attrs.get('rater_count', 0)} | "
            f"[bold]Notes:[/bold] {attrs.get('note_count', 0)}",
            title="[bold blue]MF Scoring Analysis[/bold blue]",
        )
    )

    if "factors" in show_sections:
        _render_rater_table(rater_factors, "table")
        console.print()
        _render_note_table(note_factors, "table")

    if "correlation" in show_sections and len(rater_factors) >= 3:
        _render_correlation(rater_factors, "table")

    if "recovery" in show_sections:
        _render_profile_recovery(rater_factors, "table")
