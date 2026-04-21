from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def check_openapi_sync(monkeypatch):
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    monkeypatch.setitem(
        sys.modules, "scoring", importlib.import_module("unittest.mock").MagicMock()
    )
    monkeypatch.setitem(
        sys.modules,
        "scoring.run_scoring",
        importlib.import_module("unittest.mock").MagicMock(),
    )
    return importlib.import_module("check_openapi_sync")


def test_diff_values_identical_schema_has_no_issues(check_openapi_sync) -> None:
    schema = {"paths": {}, "components": {"schemas": {}}}
    issues: list[str] = []

    check_openapi_sync._diff_values("", schema, dict(schema), issues)

    assert issues == []


def test_diff_values_reports_component_property_addition(check_openapi_sync) -> None:
    expected = {
        "components": {
            "schemas": {"Foo": {"type": "object", "properties": {"bar": {"type": "string"}}}}
        }
    }
    actual = {"components": {"schemas": {"Foo": {"type": "object", "properties": {}}}}}
    issues: list[str] = []

    check_openapi_sync._diff_values("", expected, actual, issues)

    assert any(issue.startswith("/components/schemas/Foo/properties/bar") for issue in issues)


def test_diff_values_reports_required_field_addition(check_openapi_sync) -> None:
    expected = {"components": {"schemas": {"Foo": {"required": ["id", "name"]}}}}
    actual = {"components": {"schemas": {"Foo": {"required": ["id"]}}}}
    issues: list[str] = []

    check_openapi_sync._diff_values("", expected, actual, issues)

    assert any(issue.startswith("/components/schemas/Foo/required") for issue in issues)


def test_diff_values_reports_enum_addition(check_openapi_sync) -> None:
    expected = {"components": {"schemas": {"Status": {"enum": ["open", "closed"]}}}}
    actual = {"components": {"schemas": {"Status": {"enum": ["open"]}}}}
    issues: list[str] = []

    check_openapi_sync._diff_values("", expected, actual, issues)

    assert any(issue.startswith("/components/schemas/Status/enum") for issue in issues)


def test_diff_values_reports_path_operation_addition(check_openapi_sync) -> None:
    expected = {"paths": {"/api/v1/notes": {"post": {"responses": {"200": {}}}}}}
    actual = {"paths": {"/api/v1/notes": {}}}
    issues: list[str] = []

    check_openapi_sync._diff_values("", expected, actual, issues)

    assert any(issue.startswith("/paths/~1api~1v1~1notes/post") for issue in issues)


def test_diff_values_reports_ref_change(check_openapi_sync) -> None:
    expected = {"schema": {"$ref": "#/components/schemas/NoteResponse"}}
    actual = {"schema": {"$ref": "#/components/schemas/OldNoteResponse"}}
    issues: list[str] = []

    check_openapi_sync._diff_values("", expected, actual, issues)

    assert (
        "/schema/$ref: was '#/components/schemas/NoteResponse', "
        "now '#/components/schemas/OldNoteResponse'"
    ) in issues


def test_compare_and_report_returns_one_for_deep_drift(
    check_openapi_sync,
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    committed = {"paths": {"/notes": {"get": {"responses": {"200": {"description": "old"}}}}}}
    expected = {"paths": {"/notes": {"get": {"responses": {"200": {"description": "new"}}}}}}
    schema_path = tmp_path / "openapi.json"
    schema_path.write_text(json.dumps(committed), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = check_openapi_sync._compare_and_report(
        "openapi.json",
        expected,
        "mise run docs:generate:openapi",
    )

    assert result == 1
    assert "/paths/~1notes/get/responses/200/description" in capsys.readouterr().out
