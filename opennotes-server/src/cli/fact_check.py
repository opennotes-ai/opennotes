"""
CLI commands for fact-check operations.

Provides command-line interface for:
- Importing fact-check candidates from external sources
- Scraping content for candidates
- Promoting candidates to fact-check items
"""

import logging
import sys

import click

from src.cli.utils import (
    common_batch_options,
    poll_job_until_complete,
    print_job_result,
    run_async,
)


@click.group()
def fact_check() -> None:
    """Fact-check related operations."""


@fact_check.group()
def candidates() -> None:
    """Manage fact-check candidates (import, scrape, promote)."""


@candidates.command("import")
@click.argument("source", type=click.Choice(["fact-check-bureau"]))
@common_batch_options
def import_candidates(
    source: str,
    batch_size: int,
    dry_run: bool,
    wait: bool,
    verbose: bool,
) -> None:
    """
    Import fact-check candidates from an external source.

    SOURCE: The data source to import from (e.g., fact-check-bureau)

    Examples:

        opennotes-cli fact-check candidates import fact-check-bureau

        opennotes-cli fact-check candidates import fact-check-bureau --dry-run

        opennotes-cli fact-check candidates import fact-check-bureau --wait --verbose
    """
    _setup_logging(verbose)
    logger = logging.getLogger(__name__)

    async def _run() -> None:
        from src.batch_jobs.import_service import ImportBatchJobService  # noqa: PLC0415
        from src.database import get_session_maker  # noqa: PLC0415

        async with get_session_maker()() as session:
            service = ImportBatchJobService(session)

            click.echo(f"Starting import from {source}...")
            if dry_run:
                click.echo("DRY RUN: No data will be inserted")

            job = await service.start_import_job(
                batch_size=batch_size,
                dry_run=dry_run,
            )

            click.echo(f"Created job: {job.id}")

            if wait:
                click.echo("Waiting for job completion...")
                final_job = await poll_job_until_complete(
                    session=session,
                    job_id=job.id,
                    verbose=verbose,
                )
                if final_job:
                    print_job_result(final_job, verbose)
            else:
                click.echo(f"Job {job.id} started. Use --wait to monitor progress.")

    try:
        run_async(_run())
    except Exception as e:
        logger.exception("Import failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@candidates.command("scrape-content")
@common_batch_options
def scrape_content(
    batch_size: int,
    dry_run: bool,
    wait: bool,
    verbose: bool,
) -> None:
    """
    Scrape content for pending fact-check candidates.

    Processes candidates that have been imported but don't yet have
    their claim content scraped from the source URL.

    Examples:

        opennotes-cli fact-check candidates scrape-content

        opennotes-cli fact-check candidates scrape-content --batch-size 500 --wait
    """
    _setup_logging(verbose)
    logger = logging.getLogger(__name__)

    async def _run() -> None:
        from src.batch_jobs.import_service import ImportBatchJobService  # noqa: PLC0415
        from src.database import get_session_maker  # noqa: PLC0415

        async with get_session_maker()() as session:
            service = ImportBatchJobService(session)

            if not hasattr(service, "start_scrape_job"):
                click.echo(
                    "Error: start_scrape_job not yet implemented. "
                    "This feature requires PR 118 to be merged.",
                    err=True,
                )
                sys.exit(1)

            click.echo("Starting content scraping...")
            if dry_run:
                click.echo("DRY RUN: No content will be scraped")

            job = await service.start_scrape_job(
                batch_size=batch_size,
                dry_run=dry_run,
            )

            click.echo(f"Created job: {job.id}")

            if wait:
                click.echo("Waiting for job completion...")
                final_job = await poll_job_until_complete(
                    session=session,
                    job_id=job.id,
                    verbose=verbose,
                )
                if final_job:
                    print_job_result(final_job, verbose)
            else:
                click.echo(f"Job {job.id} started. Use --wait to monitor progress.")

    try:
        run_async(_run())
    except Exception as e:
        logger.exception("Scrape failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@candidates.command("promote")
@common_batch_options
def promote_candidates(
    batch_size: int,
    dry_run: bool,
    wait: bool,
    verbose: bool,
) -> None:
    """
    Promote scraped candidates to fact-check items.

    Processes candidates that have been scraped and are ready to be
    promoted to full fact-check items for community review.

    Examples:

        opennotes-cli fact-check candidates promote

        opennotes-cli fact-check candidates promote --batch-size 100 --wait --verbose
    """
    _setup_logging(verbose)
    logger = logging.getLogger(__name__)

    async def _run() -> None:
        from src.batch_jobs.import_service import ImportBatchJobService  # noqa: PLC0415
        from src.database import get_session_maker  # noqa: PLC0415

        async with get_session_maker()() as session:
            service = ImportBatchJobService(session)

            if not hasattr(service, "start_promotion_job"):
                click.echo(
                    "Error: start_promotion_job not yet implemented. "
                    "This feature requires PR 118 to be merged.",
                    err=True,
                )
                sys.exit(1)

            click.echo("Starting candidate promotion...")
            if dry_run:
                click.echo("DRY RUN: No candidates will be promoted")

            job = await service.start_promotion_job(
                batch_size=batch_size,
                dry_run=dry_run,
            )

            click.echo(f"Created job: {job.id}")

            if wait:
                click.echo("Waiting for job completion...")
                final_job = await poll_job_until_complete(
                    session=session,
                    job_id=job.id,
                    verbose=verbose,
                )
                if final_job:
                    print_job_result(final_job, verbose)
            else:
                click.echo(f"Job {job.id} started. Use --wait to monitor progress.")

    try:
        run_async(_run())
    except Exception as e:
        logger.exception("Promotion failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _setup_logging(verbose: bool) -> None:
    """Configure logging for CLI commands."""
    from src.config import get_settings  # noqa: PLC0415
    from src.monitoring.logging import setup_logging  # noqa: PLC0415

    settings = get_settings()
    setup_logging(
        log_level="DEBUG" if verbose else settings.LOG_LEVEL,
        json_format=False,
        service_name="opennotes-cli",
    )
