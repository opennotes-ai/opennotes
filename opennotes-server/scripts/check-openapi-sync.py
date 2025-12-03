#!/usr/bin/env python3
"""
Check if static OpenAPI schema files are in sync with the FastAPI app.

This script generates a temporary OpenAPI schema and compares it with the
committed static files. If they differ, it means the static files need to
be regenerated using `mise run docs:generate`.

Exit codes:
  0 - Schemas are in sync
  1 - Schemas are out of sync
  2 - Error occurred
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock the scoring module to avoid import errors
sys.modules["scoring"] = MagicMock()
sys.modules["scoring.run_scoring"] = MagicMock()

from src.main import app  # noqa: E402 - Mock setup must precede app import


def normalize_schema(schema: dict) -> dict:
    """Normalize schema for comparison by removing volatile fields."""
    # Remove fields that change between runs
    schema.pop("servers", None)
    return schema


def main():
    # Generate current schema from FastAPI app
    current_schema = app.openapi()
    current_schema = normalize_schema(current_schema)

    # Read committed schema
    schema_path = Path("openapi.json")
    if not schema_path.exists():
        print("❌ Error: openapi.json not found")
        print("   Run: mise run docs:generate")
        return 2

    with schema_path.open() as f:
        committed_schema = json.load(f)
    committed_schema = normalize_schema(committed_schema)

    # Compare paths (main indicator of API changes)
    current_paths = set(current_schema.get("paths", {}).keys())
    committed_paths = set(committed_schema.get("paths", {}).keys())

    if current_paths != committed_paths:
        print("❌ OpenAPI schema is out of sync!")
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
        print("   To fix: mise run docs:generate")
        return 1

    # Compare component schemas (models)
    current_components = current_schema.get("components", {}).get("schemas", {})
    committed_components = committed_schema.get("components", {}).get("schemas", {})

    if set(current_components.keys()) != set(committed_components.keys()):
        print("❌ OpenAPI schema models have changed!")
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
        print("   To fix: mise run docs:generate")
        return 1

    print("✅ OpenAPI schema is in sync")
    print(f"   Verified {len(current_paths)} endpoints and {len(current_components)} models")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"❌ Error checking schema: {e}")
        sys.exit(2)
