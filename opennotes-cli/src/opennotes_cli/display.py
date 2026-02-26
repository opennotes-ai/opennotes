from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
error_console = Console(stderr=True)


def get_status_style(status: str) -> tuple[str, str]:
    styles = {
        "pending": ("yellow", "\u23f3"),
        "in_progress": ("blue", "\U0001f504"),
        "running": ("blue", "\U0001f504"),
        "paused": ("cyan", "\u23f8"),
        "completed": ("green", "\u2713"),
        "failed": ("red", "\u2717"),
        "cancelled": ("dim", "\u2298"),
    }
    return styles.get(status.lower(), ("white", "?"))


def display_search_results(results: dict[str, Any], query_text: str) -> None:
    attrs = results.get("data", {}).get("attributes", {})
    matches = attrs.get("matches", [])

    console.print()
    console.print(
        Panel(
            f"[bold]Query:[/bold] {query_text[:100]}{'...' if len(query_text) > 100 else ''}\n"
            f"[bold]Total matches:[/bold] {attrs.get('total_matches', 0)}",
            title="[bold blue]Hybrid Search Results[/bold blue]",
            subtitle="FTS + Semantic with CC",
        )
    )

    if not matches:
        console.print("\n[yellow]No matching fact-checks found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3)
    table.add_column("CC Score", justify="right", width=10)
    table.add_column("Rating", width=12)
    table.add_column("Title", no_wrap=False)

    for i, match in enumerate(matches, 1):
        score = match.get("cc_score", 0)
        rating = match.get("rating", "Unknown")
        title = match.get("title", "No title")

        rating_color = {
            "True": "green",
            "False": "red",
            "Misleading": "yellow",
            "Unverified": "dim",
        }.get(rating, "white")

        table.add_row(
            str(i), f"{score:.4f}", f"[{rating_color}]{rating}[/{rating_color}]", title
        )

    console.print(table)

    console.print("\n[dim]Source URLs:[/dim]")
    for i, match in enumerate(matches, 1):
        source_url = match.get("source_url", "")
        if source_url:
            console.print(f"  [dim]{i}.[/dim] {source_url}")


def display_task_status(task: dict[str, Any], json_output: bool = False) -> None:
    if json_output:
        console.print(json.dumps(task, indent=2, default=str))
        return

    status = task.get("status", "unknown")
    color, symbol = get_status_style(status)
    completed = task.get("completed_tasks", 0)
    failed = task.get("failed_tasks", 0)
    processed = completed + failed
    total = task.get("total_tasks", 0)
    progress_pct = (processed / total * 100) if total > 0 else 0
    metadata = task.get("metadata", {}) or {}
    batch_size = metadata.get("batch_size", "N/A")

    panel_content = (
        f"[bold]Task ID:[/bold] {task.get('id', 'N/A')}\n"
        f"[bold]Type:[/bold] {task.get('job_type', 'N/A')}\n"
        f"[bold]Status:[/bold] [{color}]{symbol} {status.upper()}[/{color}]\n"
        f"[bold]Progress:[/bold] {processed:,} / {total:,} ({progress_pct:.1f}%)\n"
        f"[bold]Batch Size:[/bold] {batch_size}"
    )

    if task.get("error_summary"):
        panel_content += f"\n[bold red]Error:[/bold red] {task['error_summary']}"

    console.print(Panel(panel_content, title="[bold]Rechunk Task Status[/bold]"))


def display_task_start(
    response: dict[str, Any],
    env_name: str,
    json_output: bool = False,
) -> None:
    if json_output:
        console.print(json.dumps(response, indent=2, default=str))
        return

    task_id = response.get("task_id", "N/A")
    total = response.get("total_items", 0)
    batch_size = response.get("batch_size", 100)
    message = response.get("message", "Task started")
    cli_prefix = get_cli_prefix(env_name)

    console.print(
        Panel(
            f"[bold]Task ID:[/bold] {task_id}\n"
            f"[bold]Total Items:[/bold] {total:,}\n"
            f"[bold]Batch Size:[/bold] {batch_size}\n"
            f"[bold]Message:[/bold] {message}",
            title="[bold green]Rechunk Task Started[/bold green]",
        )
    )
    console.print(f"\n[dim]Poll status with:[/dim] {cli_prefix} rechunk status {task_id}")
    console.print(f"[dim]Cancel task with:[/dim]  {cli_prefix} rechunk delete {task_id}")


def display_task_list(
    tasks: list[dict[str, Any]],
    env_name: str,
    json_output: bool = False,
) -> None:
    if json_output:
        console.print(json.dumps(tasks, indent=2, default=str))
        return

    if not tasks:
        console.print("[yellow]No active rechunk tasks found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Task ID", no_wrap=True)
    table.add_column("Type", width=20)
    table.add_column("Status", width=12)
    table.add_column("Progress", justify="right", width=20)

    for task in tasks:
        task_id = task.get("id", "N/A")
        task_type = task.get("job_type", "N/A")
        status = task.get("status", "unknown")
        completed = task.get("completed_tasks", 0)
        failed = task.get("failed_tasks", 0)
        processed = completed + failed
        total = task.get("total_tasks", 0)

        color, symbol = get_status_style(status)
        progress_pct = (processed / total * 100) if total > 0 else 0
        progress_str = f"{processed:,} / {total:,} ({progress_pct:.1f}%)"

        table.add_row(
            task_id,
            task_type,
            f"[{color}]{symbol} {status}[/{color}]",
            progress_str,
        )

    console.print(table)

    cli_prefix = get_cli_prefix(env_name)
    console.print(f"\n[dim]View task details:[/dim] {cli_prefix} rechunk status <task_id>")
    console.print(f"[dim]Cancel a task:[/dim]    {cli_prefix} rechunk delete <task_id>")


def display_batch_job_status(job: dict[str, Any], json_output: bool = False) -> None:
    if json_output:
        console.print(json.dumps(job, indent=2, default=str))
        return

    status = job.get("status", "unknown")
    color, symbol = get_status_style(status)
    completed = job.get("completed_tasks", 0)
    failed = job.get("failed_tasks", 0)
    total = job.get("total_tasks", 0)
    processed = completed + failed
    progress_pct = (processed / total * 100) if total > 0 else 0

    panel_content = (
        f"[bold]Job ID:[/bold] {job.get('id', 'N/A')}\n"
        f"[bold]Type:[/bold] {job.get('job_type', 'N/A')}\n"
        f"[bold]Status:[/bold] [{color}]{symbol} {status.upper()}[/{color}]\n"
        f"[bold]Processed:[/bold] {processed:,} / {total:,} ({progress_pct:.1f}%)\n"
        f"[bold]Succeeded:[/bold] {completed:,}\n"
        f"[bold]Failed:[/bold] {failed:,}"
    )

    if job.get("started_at"):
        panel_content += f"\n[bold]Started:[/bold] {job['started_at']}"
    if job.get("completed_at"):
        panel_content += f"\n[bold]Completed:[/bold] {job['completed_at']}"
    if job.get("error_summary"):
        panel_content += f"\n[bold red]Error Summary:[/bold red] {job['error_summary']}"

    console.print(Panel(panel_content, title="[bold]Batch Job Status[/bold]"))


def display_batch_job_list(
    jobs: list[dict[str, Any]],
    env_name: str,
    json_output: bool = False,
) -> None:
    if json_output:
        console.print(json.dumps(jobs, indent=2, default=str))
        return

    if not jobs:
        console.print("[yellow]No batch jobs found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Job ID", no_wrap=True, width=36)
    table.add_column("Type", width=25)
    table.add_column("Status", width=12)
    table.add_column("Progress", justify="right", width=20)

    for job in jobs:
        job_id = job.get("id", "N/A")
        job_type = job.get("job_type", "N/A")
        status = job.get("status", "unknown")
        completed = job.get("completed_tasks", 0)
        failed = job.get("failed_tasks", 0)
        total = job.get("total_tasks", 0)

        color, symbol = get_status_style(status)
        processed = completed + failed
        progress_pct = (processed / total * 100) if total > 0 else 0
        progress_str = f"{processed:,} / {total:,} ({progress_pct:.1f}%)"
        if failed > 0:
            progress_str += f" [red]({failed} failed)[/red]"

        table.add_row(
            job_id,
            job_type,
            f"[{color}]{symbol} {status}[/{color}]",
            progress_str,
        )

    console.print(table)

    cli_prefix = get_cli_prefix(env_name)
    console.print(f"\n[dim]View job details:[/dim] {cli_prefix} batch status <job_id>")
    console.print(f"[dim]Cancel a job:[/dim]    {cli_prefix} batch cancel <job_id>")


def display_batch_job_start(
    job: dict[str, Any],
    env_name: str,
    json_output: bool = False,
) -> None:
    if json_output:
        console.print(json.dumps(job, indent=2, default=str))
        return

    job_id = job.get("id", "N/A")
    job_type = job.get("job_type", "unknown")
    status = job.get("status", "pending")
    color, symbol = get_status_style(status)
    cli_prefix = get_cli_prefix(env_name)

    console.print(
        Panel(
            f"[bold]Job ID:[/bold] {job_id}\n"
            f"[bold]Type:[/bold] {job_type}\n"
            f"[bold]Status:[/bold] [{color}]{symbol} {status.upper()}[/{color}]",
            title="[bold green]Import Job Started[/bold green]",
        )
    )
    console.print(f"\n[dim]Check progress:[/dim] {cli_prefix} batch status {job_id}")
    console.print(f"[dim]Cancel job:[/dim]     {cli_prefix} batch cancel {job_id}")


def display_candidates_list(data: dict[str, Any], json_output: bool = False) -> None:
    if json_output:
        console.print(json.dumps(data, indent=2, default=str))
        return

    candidates = data.get("data", [])
    meta = data.get("meta", {})
    total = meta.get("count", len(candidates))

    if not candidates:
        console.print("[yellow]No candidates found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", no_wrap=True, width=12)
    table.add_column("Status", width=12)
    table.add_column("Rating", width=12)
    table.add_column("Dataset", width=20)
    table.add_column("Title", no_wrap=False)
    table.add_column("Published", width=12)

    for candidate in candidates:
        attrs = candidate.get("attributes", {})
        candidate_id = candidate.get("id", "N/A")
        id_truncated = (
            candidate_id[:8] + "..." if len(candidate_id) > 11 else candidate_id
        )

        status_val = attrs.get("status", "unknown")
        status_color = {
            "pending": "yellow",
            "scraped": "blue",
            "promoted": "green",
            "failed": "red",
        }.get(status_val, "white")

        rating = attrs.get("rating") or "-"
        dataset = attrs.get("dataset_name", "N/A")
        title = attrs.get("title", "No title")
        title_truncated = title[:40] + "..." if len(title) > 43 else title
        published = attrs.get("published_date", "")
        if published:
            published = published[:10] if len(published) > 10 else published

        table.add_row(
            id_truncated,
            f"[{status_color}]{status_val}[/{status_color}]",
            rating,
            dataset,
            title_truncated,
            published or "-",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {total} candidates[/dim]")


def display_candidate_single(data: dict[str, Any], json_output: bool = False) -> None:
    if json_output:
        console.print(json.dumps(data, indent=2, default=str))
        return

    candidate = data.get("data", {})
    attrs = candidate.get("attributes", {})

    panel_content = (
        f"[bold]ID:[/bold] {candidate.get('id', 'N/A')}\n"
        f"[bold]Status:[/bold] {attrs.get('status', 'unknown')}\n"
        f"[bold]Rating:[/bold] {attrs.get('rating') or 'Not set'}\n"
        f"[bold]Dataset:[/bold] {attrs.get('dataset_name', 'N/A')}\n"
        f"[bold]Title:[/bold] {attrs.get('title', 'No title')}\n"
        f"[bold]Source URL:[/bold] {attrs.get('source_url', 'N/A')}"
    )

    console.print(Panel(panel_content, title="[bold]Candidate Updated[/bold]"))


def handle_jsonapi_error(response: Any) -> None:
    if response.status_code < 400:
        return

    if response.status_code == 401:
        error_console.print("[red]Error:[/red] Authentication required.")
        sys.exit(1)
    if response.status_code == 403:
        error_console.print("[red]Error:[/red] Access denied. Admin privileges required.")
        sys.exit(1)
    if response.status_code == 404:
        try:
            errors = response.json().get("errors", [])
            detail = (errors[0] if errors else {}).get("detail", "Resource not found")
        except Exception:
            detail = "Resource not found"
        error_console.print(f"[red]Error:[/red] {detail}")
        sys.exit(1)
    if response.status_code == 409:
        try:
            errors = response.json().get("errors", [])
            detail = (errors[0] if errors else {}).get("detail", "Conflict")
        except Exception:
            detail = "Conflict"
        error_console.print(f"[red]Error:[/red] {detail}")
        sys.exit(1)
    if response.status_code == 422:
        try:
            errors = response.json().get("errors", [])
            detail = (errors[0] if errors else {}).get("detail", "Validation error")
        except Exception:
            detail = response.text[:300]
        error_console.print(f"[red]Error:[/red] {detail}")
        sys.exit(1)
    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)


def get_cli_prefix(env_name: str) -> str:
    prefix = "opennotes"
    if env_name == "local":
        prefix += " --local"
    elif env_name != "production":
        prefix += f" -e {env_name}"
    return prefix
