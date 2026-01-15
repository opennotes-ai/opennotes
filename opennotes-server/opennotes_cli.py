#!/usr/bin/env python
"""
OpenNotes CLI - Command line interface for server management.

Usage:
    uv run python opennotes_cli.py [COMMAND] [OPTIONS]

Examples:
    uv run python opennotes_cli.py fact-check candidates import fact-check-bureau
    uv run python opennotes_cli.py fact-check candidates scrape-content --wait
    uv run python opennotes_cli.py fact-check candidates promote --batch-size 100
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import click

from src.cli.fact_check import fact_check


@click.group()
@click.version_option(version="0.1.0", prog_name="opennotes-cli")
def cli() -> None:
    """OpenNotes CLI - Server management commands."""


cli.add_command(fact_check)


if __name__ == "__main__":
    cli()
