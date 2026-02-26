from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console

from opennotes_cli.display import (
    display_batch_job_start,
    display_batch_job_status,
    display_candidate_single,
    display_candidates_list,
)
from opennotes_cli.http import add_csrf, get_csrf_token
from opennotes_cli.polling import poll_batch_job_until_complete

if TYPE_CHECKING:
    from opennotes_cli.cli import CliContext

console = Console()
error_console = Console(stderr=True)


@click.group("fact-check")
def fact_check() -> None:
    """Fact-check related operations."""


@fact_check.group()
def candidates() -> None:
    """Manage fact-check candidates (import, scrape, promote)."""


def _handle_job_response(
    response: Any,
    *,
    conflict_msg: str = "A job is already in progress.",
) -> None:
    if response.status_code == 401:
        error_console.print("[red]Error:[/red] Authentication required. Provide an API key.")
        sys.exit(1)
    if response.status_code == 403:
        error_console.print(
            "[red]Error:[/red] Access denied. Check your API key permissions."
        )
        sys.exit(1)
    # The server returns 429 (not 409) when a conflicting batch job already exists
    # for this endpoint, reusing the rate-limit status to signal "one at a time".
    if response.status_code == 429:
        error_console.print(f"[red]Error:[/red] {conflict_msg}")
        error_console.print(
            "[dim]Wait for the current job to complete before starting a new one.[/dim]"
        )
        sys.exit(1)
    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)


@candidates.command("import")
@click.argument("source", type=click.Choice(["fact-check-bureau"]), default="fact-check-bureau")
@click.option(
    "-b",
    "--batch-size",
    default=100,
    type=click.IntRange(1, 10000),
    help="Batch size for import operations (1-10000).",
)
@click.option("--dry-run", is_flag=True, help="Validate only, do not insert into database.")
@click.option(
    "--enqueue-scrapes",
    is_flag=True,
    help="Enqueue scrape tasks for pending candidates instead of importing.",
)
@click.option("--wait", is_flag=True, help="Wait for import to complete, polling for progress.")
@click.pass_context
def import_candidates(
    ctx: click.Context,
    source: str,
    batch_size: int,
    dry_run: bool,
    enqueue_scrapes: bool,
    wait: bool,
) -> None:
    """Import fact-check candidates from an external source."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        if enqueue_scrapes:
            console.print("[dim]Enqueueing scrape tasks for pending candidates...[/dim]")
        elif dry_run:
            console.print("[dim]Starting import in DRY RUN mode (no database changes)...[/dim]")
        else:
            console.print(f"[dim]Starting {source} import job...[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/fact-checking/import/{source}"
    payload = {
        "batch_size": batch_size,
        "dry_run": dry_run,
        "enqueue_scrapes": enqueue_scrapes,
    }

    if not cli_ctx.json_output:
        with console.status("[bold blue]Starting job...[/bold blue]", spinner="dots"):
            response = client.post(url, headers=headers, json=payload)
    else:
        response = client.post(url, headers=headers, json=payload)

    _handle_job_response(response)

    result = response.json()
    job_id = result.get("id")

    if wait and job_id:
        if not cli_ctx.json_output:
            console.print(f"[dim]Job started: {job_id}[/dim]")
            console.print("[dim]Waiting for completion...[/dim]\n")
        final_status = poll_batch_job_until_complete(client, base_url, headers, job_id)
        display_batch_job_status(final_status, cli_ctx.json_output)
    else:
        display_batch_job_start(result, cli_ctx.env_name, cli_ctx.json_output)


@candidates.command("scrape")
@click.option(
    "-b",
    "--batch-size",
    default=1000,
    type=click.IntRange(1, 10000),
    help="Maximum candidates to process (1-10000).",
)
@click.option(
    "--base-delay",
    default=1.0,
    type=click.FloatRange(0.1, 30.0),
    help="Minimum delay in seconds between requests to the same domain (0.1-30.0).",
)
@click.option("--dry-run", is_flag=True, help="Count candidates only, do not scrape.")
@click.option("--wait", is_flag=True, help="Wait for job to complete, polling for progress.")
@click.pass_context
def scrape_candidates(
    ctx: click.Context,
    batch_size: int,
    base_delay: float,
    dry_run: bool,
    wait: bool,
) -> None:
    """Scrape content for pending fact-check candidates."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        if dry_run:
            console.print("[dim]Starting scrape in DRY RUN mode (count only)...[/dim]")
        else:
            console.print("[dim]Starting candidate scrape job...[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/fact-checking/import/scrape-candidates"
    payload = {
        "batch_size": batch_size,
        "base_delay": base_delay,
        "dry_run": dry_run,
    }

    if not cli_ctx.json_output:
        with console.status("[bold blue]Starting job...[/bold blue]", spinner="dots"):
            response = client.post(url, headers=headers, json=payload)
    else:
        response = client.post(url, headers=headers, json=payload)

    _handle_job_response(response, conflict_msg="A scrape job is already in progress.")

    result = response.json()
    job_id = result.get("id")

    if wait and job_id:
        if not cli_ctx.json_output:
            console.print(f"[dim]Job started: {job_id}[/dim]")
            console.print("[dim]Waiting for completion...[/dim]\n")
        final_status = poll_batch_job_until_complete(client, base_url, headers, job_id)
        display_batch_job_status(final_status, cli_ctx.json_output)
    else:
        display_batch_job_start(result, cli_ctx.env_name, cli_ctx.json_output)


@candidates.command("promote")
@click.option(
    "-b",
    "--batch-size",
    default=1000,
    type=click.IntRange(1, 10000),
    help="Maximum candidates to process (1-10000).",
)
@click.option("--dry-run", is_flag=True, help="Count candidates only, do not promote.")
@click.option("--wait", is_flag=True, help="Wait for job to complete, polling for progress.")
@click.pass_context
def promote_candidates(
    ctx: click.Context,
    batch_size: int,
    dry_run: bool,
    wait: bool,
) -> None:
    """Promote scraped candidates to fact-check items."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        if dry_run:
            console.print("[dim]Starting promote in DRY RUN mode (count only)...[/dim]")
        else:
            console.print("[dim]Starting candidate promote job...[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)

    url = f"{base_url}/api/v1/fact-checking/import/promote-candidates"
    payload = {
        "batch_size": batch_size,
        "dry_run": dry_run,
    }

    if not cli_ctx.json_output:
        with console.status("[bold blue]Starting job...[/bold blue]", spinner="dots"):
            response = client.post(url, headers=headers, json=payload)
    else:
        response = client.post(url, headers=headers, json=payload)

    _handle_job_response(response, conflict_msg="A promote job is already in progress.")

    result = response.json()
    job_id = result.get("id")

    if wait and job_id:
        if not cli_ctx.json_output:
            console.print(f"[dim]Job started: {job_id}[/dim]")
            console.print("[dim]Waiting for completion...[/dim]\n")
        final_status = poll_batch_job_until_complete(client, base_url, headers, job_id)
        display_batch_job_status(final_status, cli_ctx.json_output)
    else:
        display_batch_job_start(result, cli_ctx.env_name, cli_ctx.json_output)


@candidates.command("list")
@click.option(
    "-s", "--status", "status_filter",
    help="Filter by status (pending, scraped, promoted, failed).",
)
@click.option("--dataset-name", help="Filter by dataset name (exact match).")
@click.option(
    "--dataset-tags", multiple=True,
    help="Filter by dataset tags (can be specified multiple times).",
)
@click.option(
    "--rating", "rating_filter",
    help="Filter by rating: 'null', 'not_null', or exact value.",
)
@click.option(
    "--has-content", type=bool, default=None,
    help="Filter by whether candidate has content (true/false).",
)
@click.option("--published-date-from", help="Filter by published_date >= this value (ISO 8601).")
@click.option("--published-date-to", help="Filter by published_date <= this value (ISO 8601).")
@click.option("--page", default=1, type=click.IntRange(1), help="Page number (default: 1).")
@click.option(
    "--page-size", default=20, type=click.IntRange(1, 100),
    help="Page size (1-100, default: 20).",
)
@click.pass_context
def list_candidates_cmd(
    ctx: click.Context,
    status_filter: str | None,
    dataset_name: str | None,
    dataset_tags: tuple[str, ...],
    rating_filter: str | None,
    has_content: bool | None,
    published_date_from: str | None,
    published_date_to: str | None,
    page: int,
    page_size: int,
) -> None:
    """List fact-check candidates with filtering."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print("[dim]Fetching candidates...[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)
    headers["Accept"] = "application/vnd.api+json"

    url = f"{base_url}/api/v1/fact-checking/candidates"

    params: list[tuple[str, str | int]] = [
        ("page[number]", page),
        ("page[size]", page_size),
    ]
    if status_filter:
        params.append(("filter[status]", status_filter))
    if dataset_name:
        params.append(("filter[dataset_name]", dataset_name))
    for tag in dataset_tags:
        params.append(("filter[dataset_tags]", tag))
    if rating_filter:
        params.append(("filter[rating]", rating_filter))
    if has_content is not None:
        params.append(("filter[has_content]", str(has_content).lower()))
    if published_date_from:
        params.append(("filter[published_date_from]", published_date_from))
    if published_date_to:
        params.append(("filter[published_date_to]", published_date_to))

    response = client.get(url, headers=headers, params=params)

    if response.status_code == 401:
        error_console.print("[red]Error:[/red] Authentication required. Provide an API key.")
        sys.exit(1)
    if response.status_code == 403:
        error_console.print(
            "[red]Error:[/red] Access denied. Check your API key permissions."
        )
        sys.exit(1)
    if response.status_code == 422:
        error_console.print("[red]Error:[/red] Invalid filter value.")
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)
    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)

    result = response.json()
    display_candidates_list(result, cli_ctx.json_output)


@candidates.command("set-rating")
@click.argument("candidate_id")
@click.argument("rating")
@click.option("--rating-details", help="Original rating value before normalization.")
@click.option(
    "--auto-promote", is_flag=True,
    help="Promote candidate if ready (has content and rating).",
)
@click.pass_context
def set_rating_cmd(
    ctx: click.Context,
    candidate_id: str,
    rating: str,
    rating_details: str | None,
    auto_promote: bool,
) -> None:
    """Set rating for a specific candidate."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print(f"[dim]Setting rating on candidate {candidate_id}...[/dim]")

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_jsonapi_headers(), csrf_token)

    url = f"{base_url}/api/v1/fact-checking/candidates/{candidate_id}/rating"
    payload = {
        "data": {
            "type": "fact-check-candidates",
            "attributes": {
                "rating": rating,
                "rating_details": rating_details,
                "auto_promote": auto_promote,
            },
        }
    }

    response = client.post(url, headers=headers, json=payload)

    if response.status_code == 401:
        error_console.print("[red]Error:[/red] Authentication required. Provide an API key.")
        sys.exit(1)
    if response.status_code == 403:
        error_console.print(
            "[red]Error:[/red] Access denied. Check your API key permissions."
        )
        sys.exit(1)
    if response.status_code == 404:
        error_console.print(f"[red]Error:[/red] Candidate {candidate_id} not found.")
        sys.exit(1)
    if response.status_code >= 400:
        error_console.print(
            f"[red]Error:[/red] Request failed with status {response.status_code}"
        )
        error_console.print(f"[dim]{response.text[:500]}[/dim]")
        sys.exit(1)

    result = response.json()
    display_candidate_single(result, cli_ctx.json_output)

    if not cli_ctx.json_output:
        if auto_promote:
            console.print("[green]\u2713[/green] Rating set and candidate promoted (if ready)")
        else:
            console.print("[green]\u2713[/green] Rating set successfully")


@candidates.command("approve-predicted")
@click.option(
    "--threshold", default=1.0, type=click.FloatRange(0.0, 1.0),
    help="Predictions >= threshold get approved (0.0-1.0, default: 1.0).",
)
@click.option("--auto-promote", is_flag=True, help="Promote approved candidates that are ready.")
@click.option(
    "-s", "--status", "status_filter",
    help="Filter by status (pending, scraped, promoted, failed).",
)
@click.option("--dataset-name", help="Filter by dataset name (exact match).")
@click.option(
    "--dataset-tags", multiple=True,
    help="Filter by dataset tags (can be specified multiple times).",
)
@click.option(
    "--has-content", type=bool, default=None,
    help="Filter by whether candidate has content (true/false).",
)
@click.option("--published-date-from", help="Filter by published_date >= this value (ISO 8601).")
@click.option("--published-date-to", help="Filter by published_date <= this value (ISO 8601).")
@click.option(
    "--limit", default=200, type=click.IntRange(1, 10000),
    help="Maximum number of candidates to approve (default: 200).",
)
@click.option("--wait", is_flag=True, help="Wait for job to complete, polling for progress.")
@click.pass_context
def approve_predicted_cmd(
    ctx: click.Context,
    threshold: float,
    auto_promote: bool,
    status_filter: str | None,
    dataset_name: str | None,
    dataset_tags: tuple[str, ...],
    has_content: bool | None,
    published_date_from: str | None,
    published_date_to: str | None,
    limit: int,
    wait: bool,
) -> None:
    """Bulk approve candidates from predicted_ratings."""
    cli_ctx: CliContext = ctx.obj
    base_url = cli_ctx.base_url
    client = cli_ctx.client

    if cli_ctx.verbose and not cli_ctx.json_output:
        console.print(f"[dim]Environment: {cli_ctx.env_name}[/dim]")
        console.print(
            f"[dim]Starting bulk approval job with threshold >= {threshold}...[/dim]"
        )

    csrf_token = get_csrf_token(client, base_url, cli_ctx.auth)
    headers = add_csrf(cli_ctx.auth.get_headers(), csrf_token)
    headers["Content-Type"] = "application/json"

    url = f"{base_url}/api/v1/fact-checking/candidates/approve-predicted"

    payload: dict[str, Any] = {
        "threshold": threshold,
        "auto_promote": auto_promote,
        "limit": limit,
    }
    if status_filter:
        payload["status"] = status_filter
    if dataset_name:
        payload["dataset_name"] = dataset_name
    if dataset_tags:
        payload["dataset_tags"] = list(dataset_tags)
    if has_content is not None:
        payload["has_content"] = has_content
    if published_date_from:
        payload["published_date_from"] = published_date_from
    if published_date_to:
        payload["published_date_to"] = published_date_to

    if not cli_ctx.json_output:
        with console.status("[bold blue]Starting job...[/bold blue]", spinner="dots"):
            response = client.post(url, headers=headers, json=payload)
    else:
        response = client.post(url, headers=headers, json=payload)

    _handle_job_response(
        response, conflict_msg="A bulk approval job is already in progress."
    )

    result = response.json()
    job_id = result.get("id")

    if wait and job_id:
        if not cli_ctx.json_output:
            console.print(f"[dim]Job started: {job_id}[/dim]")
            console.print("[dim]Waiting for completion...[/dim]\n")
        final_status = poll_batch_job_until_complete(client, base_url, headers, job_id)
        display_batch_job_status(final_status, cli_ctx.json_output)
    else:
        display_batch_job_start(result, cli_ctx.env_name, cli_ctx.json_output)
