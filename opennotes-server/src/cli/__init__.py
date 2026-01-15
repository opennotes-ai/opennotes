"""CLI module for opennotes-server management commands."""

import click

from src.cli.fact_check import fact_check


@click.group()
@click.version_option(version="0.1.0", prog_name="opennotes-cli")
def cli() -> None:
    """OpenNotes CLI - Server management commands."""


cli.add_command(fact_check)


def main() -> None:
    """Entry point for the opennotes-cli command."""
    cli()
