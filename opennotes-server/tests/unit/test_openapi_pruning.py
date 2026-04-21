from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture
def generate_openapi():
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module("generate_openapi")


def _schema_with_path_ref(ref_name: str, schemas: dict[str, dict]) -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "1.0"},
        "paths": {
            "/api/public/v1/items": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": f"#/components/schemas/{ref_name}"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {"schemas": schemas, "securitySchemes": {"HTTPBearer": {"type": "http"}}},
    }


def test_prune_unreferenced_components_keeps_linear_ref_chain(generate_openapi) -> None:
    schema = _schema_with_path_ref(
        "SchemaA",
        {
            "SchemaA": {"$ref": "#/components/schemas/SchemaB"},
            "SchemaB": {"properties": {"child": {"$ref": "#/components/schemas/SchemaC"}}},
            "SchemaC": {"type": "object"},
            "SchemaD": {"type": "object"},
            "SchemaE": {"type": "object"},
        },
    )

    pruned = generate_openapi.prune_unreferenced_components(schema)

    assert set(pruned["components"]["schemas"]) == {"SchemaA", "SchemaB", "SchemaC"}


def test_prune_unreferenced_components_walks_anyof(generate_openapi) -> None:
    schema = _schema_with_path_ref(
        "SchemaX",
        {
            "SchemaX": {"anyOf": [{"$ref": "#/components/schemas/SchemaY"}]},
            "SchemaY": {"type": "object"},
            "Unused": {"type": "object"},
        },
    )

    pruned = generate_openapi.prune_unreferenced_components(schema)

    assert set(pruned["components"]["schemas"]) == {"SchemaX", "SchemaY"}


def test_prune_unreferenced_components_walks_oneof_and_allof(generate_openapi) -> None:
    schema = _schema_with_path_ref(
        "SchemaRoot",
        {
            "SchemaRoot": {
                "oneOf": [{"$ref": "#/components/schemas/SchemaOne"}],
                "allOf": [{"$ref": "#/components/schemas/SchemaAll"}],
            },
            "SchemaOne": {"type": "object"},
            "SchemaAll": {"type": "object"},
            "Unused": {"type": "object"},
        },
    )

    pruned = generate_openapi.prune_unreferenced_components(schema)

    assert set(pruned["components"]["schemas"]) == {"SchemaRoot", "SchemaOne", "SchemaAll"}


def test_prune_unreferenced_components_prunes_all_when_no_paths(generate_openapi) -> None:
    schema = {
        "paths": {},
        "components": {"schemas": {"A": {"type": "object"}, "B": {"type": "object"}}},
    }

    pruned = generate_openapi.prune_unreferenced_components(schema)

    assert pruned["components"]["schemas"] == {}


def test_prune_unreferenced_components_returns_schema_without_components_unchanged(
    generate_openapi,
) -> None:
    schema = {"paths": {"/x": {"get": {}}}}

    pruned = generate_openapi.prune_unreferenced_components(schema)

    assert pruned == schema


def test_prune_unreferenced_components_preserves_top_level_shape(generate_openapi) -> None:
    retained = {"type": "object"}
    schema = _schema_with_path_ref("Retained", {"Retained": retained, "Unused": {"type": "object"}})

    pruned = generate_openapi.prune_unreferenced_components(schema)

    assert {"openapi", "info", "paths", "components"}.issubset(pruned)
    assert pruned["components"]["schemas"]["Retained"] is retained
    assert "HTTPBearer" in pruned["components"]["securitySchemes"]


def test_prune_unreferenced_components_is_idempotent(generate_openapi) -> None:
    schema = _schema_with_path_ref(
        "Retained",
        {"Retained": {"type": "object"}, "Unused": {"type": "object"}},
    )

    once = generate_openapi.prune_unreferenced_components(schema)
    twice = generate_openapi.prune_unreferenced_components(once)

    assert twice == once
