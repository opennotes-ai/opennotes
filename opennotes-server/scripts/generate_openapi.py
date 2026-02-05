#!/usr/bin/env python3
"""
Generate OpenAPI specification from the FastAPI application.

This script starts the FastAPI app and exports its OpenAPI schema to a JSON file.
The schema can be used to validate API clients and generate documentation.

Usage:
    uv run python scripts/generate_openapi.py [--output OUTPUT_PATH]

Example:
    uv run python scripts/generate_openapi.py --output openapi.json
"""

import json
import sys
from pathlib import Path

try:
    import click
except ImportError:
    print("Error: click is not installed. Install it with: uv pip install click")
    sys.exit(1)


@click.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="openapi.json",
    help="Output path for the OpenAPI specification file",
)
def generate_openapi(output: str) -> None:
    """Generate OpenAPI specification from the FastAPI application."""
    try:
        from src.main import app
    except ImportError as e:
        click.echo(f"Error: Failed to import FastAPI app: {e}", err=True)
        click.echo("Make sure you're running this from the opennotes-server directory", err=True)
        sys.exit(1)

    openapi_schema = app.openapi()

    output_path = Path(output)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        json.dump(openapi_schema, f, indent=2)
        f.write("\n")

    click.echo(f"✓ OpenAPI specification generated: {output_path.absolute()}")
    click.echo(f"  Title: {openapi_schema.get('info', {}).get('title', 'N/A')}")
    click.echo(f"  Version: {openapi_schema.get('info', {}).get('version', 'N/A')}")
    click.echo(f"  Endpoints: {len(openapi_schema.get('paths', {}))}")


if __name__ == "__main__":
    generate_openapi()
