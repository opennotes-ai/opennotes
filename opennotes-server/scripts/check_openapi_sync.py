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

from generate_openapi import (  # noqa: E402
    filter_public_paths,
    normalize_openapi_metadata,
    prune_unreferenced_components,
)

from src.config import settings  # noqa: E402
from src.main import app  # noqa: E402 - Mock setup must precede app import


def normalize_schema(schema: dict) -> dict:
    """Normalize schema for comparison by removing volatile fields."""
    schema.pop("servers", None)
    return schema


def _pointer_join(pointer: str, segment: str) -> str:
    escaped = segment.replace("~", "~0").replace("/", "~1")
    return f"{pointer}/{escaped}" if pointer else f"/{escaped}"


def _diff_values(pointer: str, expected, actual, issues: list[str]) -> None:
    if expected == actual:
        return

    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            child_pointer = _pointer_join(pointer, str(key))
            if key not in actual:
                issues.append(f"{child_pointer}: present in expected, missing in actual")
            elif key not in expected:
                issues.append(f"{child_pointer}: absent in expected, present in actual")
            else:
                _diff_values(child_pointer, expected[key], actual[key], issues)
        return

    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            issues.append(f"{pointer}: expected {len(expected)} items, got {len(actual)}")
            return
        for idx, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=True)):
            _diff_values(_pointer_join(pointer, str(idx)), expected_item, actual_item, issues)
        return

    if type(expected) is not type(actual):
        issues.append(
            f"{pointer}: type changed from {type(expected).__name__} to {type(actual).__name__}"
        )
        return

    issues.append(f"{pointer}: was {expected!r}, now {actual!r}")


def _print_issue_bucket(header: str, issues: list[str]) -> None:
    if not issues:
        return
    print(f"  {header}:")
    for issue in issues:
        print(f"    - {issue}")


def _compare_and_report(artifact_name: str, expected_schema: dict, regen_hint: str) -> int:
    schema_path = Path(artifact_name)
    if not schema_path.exists():
        print(f"❌ Error: {artifact_name} not found")
        print(f"   To fix: {regen_hint}")
        return 1

    with schema_path.open() as f:
        committed_schema = json.load(f)
    committed_schema = normalize_schema(committed_schema)

    issues: list[str] = []
    _diff_values("", expected_schema, committed_schema, issues)

    if issues:
        print(f"❌ {artifact_name} is out of sync!")
        print()
        path_issues = [issue for issue in issues if issue.startswith("/paths/")]
        component_issues = [issue for issue in issues if issue.startswith("/components/")]
        top_level_issues = [
            issue
            for issue in issues
            if not issue.startswith("/paths/") and not issue.startswith("/components/")
        ]

        _print_issue_bucket("Path drift", path_issues)
        _print_issue_bucket("Component drift", component_issues)
        _print_issue_bucket("Top-level drift", top_level_issues)

        print()
        print(f"   To fix: {regen_hint}")
        return 1

    current_paths = set(expected_schema.get("paths", {}).keys())
    current_components = expected_schema.get("components", {}).get("schemas", {})
    print(f"✅ {artifact_name} is in sync")
    print(f"   Verified {len(current_paths)} endpoints and {len(current_components)} models")
    return 0


def main() -> int:
    current_schema = normalize_schema(normalize_openapi_metadata(app.openapi()))

    checks: list[tuple[str, Callable[[dict], dict], str]] = [
        ("openapi.json", lambda s: s, "mise run docs:generate:openapi"),
        (
            "openapi-public.json",
            lambda s: prune_unreferenced_components(
                filter_public_paths(s, settings.API_PUBLIC_V1_PREFIX)
            ),
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
