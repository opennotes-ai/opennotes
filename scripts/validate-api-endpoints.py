#!/usr/bin/env python3
"""
Validate Discord bot API client endpoints against OpenAPI specification.

This script compares the endpoints used in the Discord bot's API client
with the OpenAPI specification generated from the FastAPI server to ensure
they match and prevent endpoint mismatches.

Usage:
    python scripts/validate-api-endpoints.py [--openapi PATH] [--api-client PATH]

Exit codes:
    0 - All endpoints match
    1 - Validation errors found
    2 - Script execution error
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


class EndpointValidator:
    """Validates API client endpoints against OpenAPI specification."""

    def __init__(self, openapi_path: Path, api_client_path: Path):
        self.openapi_path = openapi_path
        self.api_client_path = api_client_path
        self.openapi_endpoints: Dict[str, Set[str]] = {}
        self.client_endpoints: List[Tuple[str, str, str]] = []

    def load_openapi_spec(self) -> None:
        """Load and parse OpenAPI specification."""
        try:
            with self.openapi_path.open() as f:
                spec = json.load(f)

            for path, methods in spec.get("paths", {}).items():
                self.openapi_endpoints[path] = set()
                for method in methods.keys():
                    if method.upper() in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                        self.openapi_endpoints[path].add(method.upper())

        except FileNotFoundError:
            raise Exception(f"OpenAPI spec not found: {self.openapi_path}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON in OpenAPI spec: {e}")

    def parse_api_client(self) -> None:
        """Parse TypeScript API client to extract endpoint calls."""
        try:
            content = self.api_client_path.read_text()

            patterns = [
                r"this\.fetchWithRetry\s*<[^>]*>\s*\(\s*['\"]([^'\"]+)['\"](?:\s*,\s*\{[^}]*method:\s*['\"]([A-Z]+)['\"])?",
                r"this\.fetchWithRetry\s*\(\s*['\"]([^'\"]+)['\"](?:\s*,\s*\{[^}]*method:\s*['\"]([A-Z]+)['\"])?",
            ]

            for pattern in patterns:
                matches = re.finditer(pattern, content, re.MULTILINE)
                for match in matches:
                    endpoint = match.group(1)
                    method = match.group(2) if match.group(2) else "GET"

                    function_match = re.search(
                        rf"async\s+(\w+)\s*\([^)]*\)[^{{]*{{[^}}]*fetchWithRetry[^}}]*['\"]{ re.escape(endpoint)}['\"]",
                        content,
                        re.DOTALL,
                    )
                    function_name = (
                        function_match.group(1) if function_match else "unknown"
                    )

                    self.client_endpoints.append((endpoint, method, function_name))

        except FileNotFoundError:
            raise Exception(f"API client file not found: {self.api_client_path}")

    def normalize_path(self, path: str) -> List[str]:
        """
        Normalize path to handle path parameters.
        Returns a list of possible normalized paths.
        """
        normalized = []

        if "{" in path:
            normalized.append(path)
        else:
            parts = path.split("/")
            for i, part in enumerate(parts):
                if part and not part.startswith(":"):
                    test_path = "/".join(
                        parts[:i] + ["{" + part + "}"] + parts[i + 1 :]
                    )
                    normalized.append(test_path)

        return normalized if normalized else [path]

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate client endpoints against OpenAPI spec.
        Returns (is_valid, errors).
        """
        errors = []
        is_valid = True

        print("\n" + "=" * 70)
        print("API ENDPOINT VALIDATION REPORT")
        print("=" * 70)

        print(f"\nOpenAPI Spec: {self.openapi_path}")
        print(f"API Client: {self.api_client_path}")
        print(
            f"\nTotal OpenAPI endpoints: {sum(len(methods) for methods in self.openapi_endpoints.values())}"
        )
        print(f"Total client endpoint calls: {len(self.client_endpoints)}\n")

        print("-" * 70)
        print("CLIENT ENDPOINTS VALIDATION")
        print("-" * 70)

        for endpoint, method, function_name in self.client_endpoints:
            found = False

            if endpoint in self.openapi_endpoints:
                if method in self.openapi_endpoints[endpoint]:
                    print(f"✓ {method:6} {endpoint:40} [{function_name}]")
                    found = True

            if not found:
                possible_paths = self.normalize_path(endpoint)
                for norm_path in possible_paths:
                    if norm_path in self.openapi_endpoints:
                        if method in self.openapi_endpoints[norm_path]:
                            print(f"⚠ {method:6} {endpoint:40} [{function_name}]")
                            print(f"  → Matches OpenAPI path: {norm_path}")
                            found = True
                            break

            if not found:
                is_valid = False
                error_msg = f"✗ {method:6} {endpoint:40} [{function_name}]"
                print(error_msg)
                print("  → NOT FOUND in OpenAPI spec")
                errors.append(f"{method} {endpoint} (function: {function_name})")

        print("\n" + "-" * 70)
        print("AVAILABLE OPENAPI ENDPOINTS")
        print("-" * 70)

        for path in sorted(self.openapi_endpoints.keys()):
            methods_str = ", ".join(sorted(self.openapi_endpoints[path]))
            print(f"{methods_str:20} {path}")

        return is_valid, errors


def main() -> None:
    """Validate Discord bot API endpoints against OpenAPI specification."""
    parser = argparse.ArgumentParser(
        description="Validate Discord bot API endpoints against OpenAPI specification"
    )
    parser.add_argument(
        "--openapi",
        type=Path,
        default=Path("opennotes/opennotes-server/openapi.json"),
        help="Path to OpenAPI specification file",
    )
    parser.add_argument(
        "--api-client",
        type=Path,
        default=Path("opennotes/opennotes-discord/src/lib/api-client.ts"),
        help="Path to Discord bot API client file",
    )
    args = parser.parse_args()

    try:
        validator = EndpointValidator(args.openapi, args.api_client)

        print("Loading OpenAPI specification...")
        validator.load_openapi_spec()

        print("Parsing API client...")
        validator.parse_api_client()

        print("Validating endpoints...")
        is_valid, errors = validator.validate()

        if is_valid:
            print("\n" + "=" * 70)
            print("✓ ALL ENDPOINTS VALIDATED SUCCESSFULLY")
            print("=" * 70)
            sys.exit(0)
        else:
            print("\n" + "=" * 70)
            print(f"✗ VALIDATION FAILED: {len(errors)} ENDPOINT(S) NOT FOUND")
            print("=" * 70)
            print("\nErrors:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
