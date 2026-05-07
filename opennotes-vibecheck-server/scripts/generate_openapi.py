"""Regenerate openapi.json from the FastAPI app.

Mirrors the opennotes-server pattern. Used by the vibecheck-web build to
regenerate `src/lib/generated-types.ts` via `pnpm run types:generate`.

Usage:
    uv run python scripts/generate_openapi.py [--output openapi.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.analyses.synthesis._weather_schemas import _normalize_weather_schema_names
from src.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("openapi.json"),
        help="Path to write the OpenAPI JSON (default: openapi.json)",
    )
    args = parser.parse_args()

    schema = _normalize_weather_schema_names(app.openapi())
    args.output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
