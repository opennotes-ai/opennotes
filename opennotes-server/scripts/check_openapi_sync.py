#!/usr/bin/env python3
"""
Check if static OpenAPI schema files are in sync with the FastAPI app.

Validates two artifacts:
  - openapi.json         — full schema (all paths)
  - openapi-public.json  — filtered to /api/public/v1/* only

Either file drifting fails the check with a distinct message pointing at the
correct regen command.

Exit codes:
  0 - Both schemas are in sync
  1 - At least one schema is out of sync
  2 - Error occurred
"""

import json
import sys
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

# Mock the scoring module to avoid import errors
sys.modules["scoring"] = MagicMock()
sys.modules["scoring.run_scoring"] = MagicMock()

from src.config import settings  # noqa: E402
from src.main import app  # noqa: E402 - Mock setup must precede app import


def normalize_schema(schema: dict) -> dict:
    """Normalize schema for comparison by removing volatile fields."""
    schema.pop("servers", None)
    return schema


def filter_public(schema: dict, prefix: str) -> dict:
    """Return a copy of ``schema`` with paths trimmed to entries under ``prefix``.

    Matches ``path == prefix`` or ``path.startswith(prefix + "/")`` so that
    a future ``/api/public/v10`` is not folded into the v1 artifact.
    """
    prefix_slash = prefix + "/"
    filtered = {**schema}
    filtered["paths"] = {
        path: op
        for path, op in schema.get("paths", {}).items()
        if path == prefix or path.startswith(prefix_slash)
    }
    return filtered


def _compare_and_report(artifact_name: str, expected_schema: dict, regen_hint: str) -> int:
    schema_path = Path(artifact_name)
    if not schema_path.exists():
        print(f"❌ Error: {artifact_name} not found")
        print(f"   To fix: {regen_hint}")
        return 1

    with schema_path.open() as f:
        committed_schema = json.load(f)
    committed_schema = normalize_schema(committed_schema)

    current_paths = set(expected_schema.get("paths", {}).keys())
    committed_paths = set(committed_schema.get("paths", {}).keys())

    if current_paths != committed_paths:
        print(f"❌ {artifact_name} is out of sync!")
        print()
        new_paths = current_paths - committed_paths
        removed_paths = committed_paths - current_paths

        if new_paths:
            print(f"   New endpoints ({len(new_paths)}):")
            for path in sorted(new_paths):
                print(f"     + {path}")

        if removed_paths:
            print(f"   Removed endpoints ({len(removed_paths)}):")
            for path in sorted(removed_paths):
                print(f"     - {path}")

        print()
        print(f"   To fix: {regen_hint}")
        return 1

    current_components = expected_schema.get("components", {}).get("schemas", {})
    committed_components = committed_schema.get("components", {}).get("schemas", {})

    if set(current_components.keys()) != set(committed_components.keys()):
        print(f"❌ {artifact_name} models have changed!")
        new_models = set(current_components.keys()) - set(committed_components.keys())
        removed_models = set(committed_components.keys()) - set(current_components.keys())

        if new_models:
            print(f"   New models ({len(new_models)}):")
            for model in sorted(new_models):
                print(f"     + {model}")

        if removed_models:
            print(f"   Removed models ({len(removed_models)}):")
            for model in sorted(removed_models):
                print(f"     - {model}")

        print()
        print(f"   To fix: {regen_hint}")
        return 1

    print(f"✅ {artifact_name} is in sync")
    print(f"   Verified {len(current_paths)} endpoints and {len(current_components)} models")
    return 0


def main() -> int:
    current_schema = normalize_schema(app.openapi())

    checks: list[tuple[str, Callable[[dict], dict], str]] = [
        ("openapi.json", lambda s: s, "mise run docs:generate:openapi"),
        (
            "openapi-public.json",
            lambda s: filter_public(s, settings.API_PUBLIC_V1_PREFIX),
            "mise run docs:generate:openapi",
        ),
    ]

    exit_code = 0
    for idx, (artifact, filter_fn, hint) in enumerate(checks):
        if idx > 0:
            print()
        expected = normalize_schema(filter_fn({**current_schema}))
        result = _compare_and_report(artifact, expected, hint)
        if result != 0:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"❌ Error checking schema: {e}")
        sys.exit(2)
