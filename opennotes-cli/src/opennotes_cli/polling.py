from __future__ import annotations

import sys
import time
from typing import Any

import httpx
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

from opennotes_cli.display import get_status_style, handle_jsonapi_error

error_console = Console(stderr=True)
console = Console()


def poll_task_until_complete(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    task_id: str,
    interval: float = 5.0,
    max_retries: int = 120,
) -> dict[str, Any]:
    job_url = f"{base_url}/api/v1/chunks/jobs/{task_id}"
    progress_url = f"{base_url}/api/v1/batch-jobs/{task_id}/progress"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Rechunking...", total=100, status="pending")
        retries = 0

        while retries < max_retries:
            retries += 1
            response = client.get(job_url, headers=headers)

            if response.status_code == 404:
                error_console.print(f"[red]Error:[/red] Task {task_id} not found")
                sys.exit(1)

            if response.status_code >= 400:
                error_console.print(
                    f"[red]Error:[/red] Failed to get task status: {response.status_code}"
                )
                sys.exit(1)

            data = response.json()
            status = data.get("status", "unknown")
            total = data.get("total_tasks", 0)

            if status == "in_progress":
                progress_response = client.get(progress_url, headers=headers)
                if progress_response.status_code == 200:
                    progress_data = progress_response.json()
                    processed = progress_data.get("processed_count", 0)
                    errors = progress_data.get("error_count", 0)
                    rate = progress_data.get("rate", 0)
                    rate_str = f" ({rate:.1f}/s)" if rate > 0 else ""
                    progress_pct = (processed / total * 100) if total > 0 else 0
                    progress.update(
                        task,
                        completed=progress_pct,
                        status=f"{status}{rate_str}",
                        description=f"Rechunking... {processed:,}/{total:,} ({errors} errors)",
                    )
                else:
                    completed = data.get("completed_tasks", 0)
                    failed = data.get("failed_tasks", 0)
                    processed = completed + failed
                    progress_pct = (processed / total * 100) if total > 0 else 0
                    progress.update(task, completed=progress_pct, status=status)
            else:
                completed = data.get("completed_tasks", 0)
                failed = data.get("failed_tasks", 0)
                processed = completed + failed
                progress_pct = (processed / total * 100) if total > 0 else 0
                progress.update(task, completed=progress_pct, status=status)

            if status in ("completed", "failed"):
                return data

            time.sleep(interval)

    error_console.print(
        f"[red]Error:[/red] Timed out after {max_retries} polls waiting for task {task_id}"
    )
    sys.exit(1)


def poll_batch_job_until_complete(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    job_id: str,
    interval: float = 2.0,
    max_retries: int = 300,
) -> dict[str, Any]:
    job_url = f"{base_url}/api/v1/batch-jobs/{job_id}"
    progress_url = f"{base_url}/api/v1/batch-jobs/{job_id}/progress"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Processing...", total=100, status="pending")
        retries = 0

        while retries < max_retries:
            retries += 1
            response = client.get(job_url, headers=headers)

            if response.status_code == 404:
                error_console.print(f"[red]Error:[/red] Job {job_id} not found")
                sys.exit(1)

            if response.status_code >= 400:
                error_console.print(
                    f"[red]Error:[/red] Failed to get job status: {response.status_code}"
                )
                sys.exit(1)

            data = response.json()
            status = data.get("status", "unknown")
            total = data.get("total_tasks", 0)

            if status == "in_progress":
                progress_response = client.get(progress_url, headers=headers)
                if progress_response.status_code == 200:
                    progress_data = progress_response.json()
                    processed = progress_data.get("processed_count", 0)
                    errors = progress_data.get("error_count", 0)
                    rate = progress_data.get("rate", 0)
                    rate_str = f" ({rate:.1f}/s)" if rate > 0 else ""
                    progress_pct = (processed / total * 100) if total > 0 else 0
                    progress.update(
                        task,
                        completed=progress_pct,
                        status=f"{status}{rate_str}",
                        description=f"Processing... {processed:,}/{total:,} ({errors} errors)",
                    )
                else:
                    completed = data.get("completed_tasks", 0)
                    failed = data.get("failed_tasks", 0)
                    processed = completed + failed
                    progress_pct = (processed / total * 100) if total > 0 else 0
                    progress.update(task, completed=progress_pct, status=status)
            else:
                completed = data.get("completed_tasks", 0)
                failed = data.get("failed_tasks", 0)
                processed = completed + failed
                progress_pct = (processed / total * 100) if total > 0 else 0
                progress.update(task, completed=progress_pct, status=status)

            if status in ("completed", "failed", "cancelled"):
                return data

            time.sleep(interval)

    error_console.print(
        f"[red]Error:[/red] Timed out after {max_retries} polls waiting for job {job_id}"
    )
    sys.exit(1)


def poll_simulation_until_complete(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    simulation_id: str,
    interval: float = 5.0,
    max_retries: int = 720,
) -> dict[str, Any]:
    url = f"{base_url}/api/v2/simulations/{simulation_id}"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Simulation running...", status="pending")
        retries = 0

        while retries < max_retries:
            retries += 1
            response = client.get(url, headers=headers)
            handle_jsonapi_error(response)

            data = response.json()
            attrs = data.get("data", {}).get("attributes", {})
            status = attrs.get("status", "unknown")
            _color, symbol = get_status_style(status)

            progress.update(task, status=f"{symbol} {status}")

            if status in ("completed", "failed", "cancelled"):
                return data

            time.sleep(interval)

    error_console.print(
        f"[red]Error:[/red] Timed out after {max_retries} polls waiting for simulation {simulation_id}"
    )
    sys.exit(1)
