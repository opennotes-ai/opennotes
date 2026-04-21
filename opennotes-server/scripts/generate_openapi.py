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
import re
import sys
from pathlib import Path

try:
    import click
except ImportError:
    print("Error: click is not installed. Install it with: uv pip install click")
    sys.exit(1)


_COMPONENT_SCHEMA_REF_RE = re.compile(r"^#/components/schemas/(?P<name>[^/]+)$")
_OPENAPI_TITLE = "Open Notes Server"


def normalize_openapi_metadata(schema: dict) -> dict:
    """Return ``schema`` with metadata stable across local and CI environments."""
    return {
        **schema,
        "info": {
            **schema.get("info", {}),
            "title": _OPENAPI_TITLE,
        },
    }


def filter_public_paths(schema: dict, prefix: str) -> dict:
    """Return a shallow-copy of ``schema`` with ``paths`` trimmed to entries
    under ``prefix``.

    A path matches when it equals ``prefix`` or begins with ``prefix + "/"`` —
    a plain ``startswith(prefix)`` would also match a future ``/api/public/v10``
    and silently fold it into the v1 artifact.

    Use ``prune_unreferenced_components`` after this filter for public artifacts.
    """
    prefix_slash = prefix + "/"
    filtered = {**schema}
    filtered["paths"] = {
        path: op
        for path, op in schema.get("paths", {}).items()
        if path == prefix or path.startswith(prefix_slash)
    }
    return filtered


def _collect_component_schema_refs(node: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            match = _COMPONENT_SCHEMA_REF_RE.match(ref)
            if match:
                refs.add(match.group("name"))
        for value in node.values():
            refs.update(_collect_component_schema_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.update(_collect_component_schema_refs(item))
    return refs


def prune_unreferenced_components(schema: dict) -> dict:
    """Prune components.schemas to schemas reachable from retained paths.

    Only ``components.schemas`` is modified. Other component groups, including
    securitySchemes, are preserved until docs tooling confirms they are safe to
    trim independently.
    """
    components = schema.get("components")
    if not isinstance(components, dict):
        return schema
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        return schema

    reachable = _collect_component_schema_refs(schema.get("paths", {}))
    expanded: set[str] = set()

    while True:
        pending = reachable - expanded
        if not pending:
            break
        for name in pending:
            expanded.add(name)
            schema_body = schemas.get(name)
            if schema_body is not None:
                reachable.update(_collect_component_schema_refs(schema_body))

    filtered_schemas = {name: body for name, body in schemas.items() if name in reachable}
    return {
        **schema,
        "components": {
            **components,
            "schemas": filtered_schemas,
        },
    }


@click.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="openapi.json",
    help="Output path for the OpenAPI specification file",
)
@click.option(
    "--public-only",
    is_flag=True,
    default=False,
    help="Filter paths to /api/public/v1/* only (produces the public API artifact for Mintlify).",
)
def generate_openapi(output: str, public_only: bool) -> None:
    """Generate OpenAPI specification from the FastAPI application."""
    try:
        from src.config import settings
        from src.main import app
    except ImportError as e:
        click.echo(f"Error: Failed to import FastAPI app: {e}", err=True)
        click.echo("Make sure you're running this from the opennotes-server directory", err=True)
        sys.exit(1)

    openapi_schema = normalize_openapi_metadata(app.openapi())
    if public_only:
        openapi_schema = prune_unreferenced_components(
            filter_public_paths(openapi_schema, settings.API_PUBLIC_V1_PREFIX)
        )

    output_path = Path(output)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        json.dump(openapi_schema, f, indent=2)
        f.write("\n")

    click.echo(f"✓ OpenAPI specification generated: {output_path.absolute()}")
    click.echo(f"  Title: {openapi_schema.get('info', {}).get('title', 'N/A')}")
    click.echo(f"  Version: {openapi_schema.get('info', {}).get('version', 'N/A')}")
    click.echo(f"  Endpoints: {len(openapi_schema.get('paths', {}))}")
    click.echo(
        f"  Components (schemas): {len(openapi_schema.get('components', {}).get('schemas', {}))}"
    )
    if public_only:
        click.echo(f"  Public-only filter: paths starting with {settings.API_PUBLIC_V1_PREFIX}")


if __name__ == "__main__":
    generate_openapi()
