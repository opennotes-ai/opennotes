#!/usr/bin/env python3
"""
Standalone schema consistency checker.

Run with: mise run schema:check
   or: uv run python scripts/check_schema_consistency.py (requires .env.yaml)

This script performs the same checks as test_schema_consistency.py but can be
run independently without pytest or database setup.
"""

import importlib
import inspect
import pkgutil
import sys
from pathlib import Path

from pydantic import BaseModel
from pydantic.fields import FieldInfo


class SchemaFamily:
    """Represents a family of related schemas."""

    def __init__(self, name: str):
        self.name = name
        self.base: type[BaseModel] | None = None
        self.create: type[BaseModel] | None = None
        self.update: type[BaseModel] | None = None
        self.indb: type[BaseModel] | None = None
        self.response: type[BaseModel] | None = None

    def add_schema(self, schema_class: type[BaseModel], suffix: str) -> None:
        suffix_lower = suffix.lower()
        if suffix_lower == "base":
            self.base = schema_class
        elif suffix_lower == "create":
            self.create = schema_class
        elif suffix_lower == "update":
            self.update = schema_class
        elif suffix_lower == "indb":
            self.indb = schema_class
        elif suffix_lower == "response":
            self.response = schema_class

    def get_all_schemas(self) -> list[tuple[str, type[BaseModel] | None]]:
        return [
            ("Base", self.base),
            ("Create", self.create),
            ("Update", self.update),
            ("InDB", self.indb),
            ("Response", self.response),
        ]

    def has_schemas(self) -> bool:
        return any(s is not None for _, s in self.get_all_schemas())


def discover_schema_families() -> dict[str, SchemaFamily]:
    """Discover all schema families in the codebase."""
    families: dict[str, SchemaFamily] = {}
    src_path = Path(__file__).parent.parent / "src"

    exclude_patterns = ["__pycache__", ".pyc", "migrations/", "alembic/", "tests/"]

    def should_check_module(module_path: str) -> bool:
        return not any(pattern in module_path for pattern in exclude_patterns)

    for _importer, modname, _ispkg in pkgutil.walk_packages(path=[str(src_path)], prefix="src."):
        if not should_check_module(modname):
            continue

        try:
            module = importlib.import_module(modname)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    not issubclass(obj, BaseModel)
                    or obj is BaseModel
                    or obj.__module__ != module.__name__
                ):
                    continue

                for suffix in ["Base", "Create", "Update", "InDB", "Response"]:
                    if name.endswith(suffix):
                        family_name = name[: -len(suffix)]
                        if family_name not in families:
                            families[family_name] = SchemaFamily(family_name)
                        families[family_name].add_schema(obj, suffix)
                        break
        except Exception:
            pass

    return {name: family for name, family in families.items() if family.has_schemas()}


def get_field_info(schema: type[BaseModel]) -> dict[str, tuple[type | None, FieldInfo]]:
    return {name: (field.annotation, field) for name, field in schema.model_fields.items()}


def is_biginteger_field(field_name: str) -> bool:
    bigint_patterns = ["_id", "tweet_id", "note_id", "request_id", "message_id"]
    return any(pattern in field_name.lower() for pattern in bigint_patterns)


def has_field_validator(schema: type[BaseModel], field_name: str) -> bool:
    if not hasattr(schema, "__pydantic_decorators__"):
        return False
    decorators = schema.__pydantic_decorators__
    if hasattr(decorators, "field_validators"):
        validators = decorators.field_validators
        return field_name in validators or "__all__" in validators
    return False


def check_biginteger_validators(families: dict[str, SchemaFamily]) -> list[str]:
    """Check that BigInteger fields have validators in Response schemas."""
    issues = []
    for family_name, family in families.items():
        if not family.response:
            continue
        response_fields = get_field_info(family.response)
        for field_name in response_fields:
            if not is_biginteger_field(field_name):
                continue
            if family.indb:
                indb_fields = get_field_info(family.indb)
                if field_name in indb_fields:
                    indb_type = str(indb_fields[field_name][0])
                    if (
                        "int" in indb_type.lower()
                        and "str" not in indb_type.lower()
                        and not has_field_validator(family.response, field_name)
                    ):
                        issues.append(
                            f"{family_name}.{field_name}: InDB has int, "
                            f"Response needs field_validator for int→str conversion"
                        )
    return issues


def check_response_from_attributes(families: dict[str, SchemaFamily]) -> list[str]:
    """Check that Response schemas that inherit from InDB have from_attributes=True."""
    issues = []
    for family_name, family in families.items():
        if not family.response or not family.indb:
            continue  # Only check if both Response and InDB exist
        # Check if Response inherits from InDB (common pattern: class NoteResponse(NoteInDB))
        if family.indb in family.response.__mro__:
            config = family.response.model_config
            if not config.get("from_attributes"):
                issues.append(
                    f"{family_name}Response: inherits from InDB but missing from_attributes=True"
                )
    return issues


def check_indb_forbid_extra(families: dict[str, SchemaFamily]) -> list[str]:
    """Check that InDB schemas forbid extra fields."""
    issues = []
    for family_name, family in families.items():
        if not family.indb:
            continue
        config = family.indb.model_config
        if config.get("extra") != "forbid":
            issues.append(f"{family_name}InDB: missing extra='forbid'")
    return issues


def check_uuid_v7_primary_keys() -> list[str]:  # noqa: PLR0912
    """Check that SQLAlchemy models use UUID v7 for primary keys correctly.

    Requires checking primary key type, server defaults, and platform ID fields.
    """
    issues = []
    src_path = Path(__file__).parent.parent / "src"
    models_path = src_path / "models"

    if not models_path.exists():
        return []

    exclude_patterns = ["__pycache__", ".pyc", "migrations/", "alembic/", "tests/"]

    def should_check_module(module_path: str) -> bool:
        return not any(pattern in module_path for pattern in exclude_patterns)

    for _importer, modname, _ispkg in pkgutil.walk_packages(
        path=[str(models_path)], prefix="src.models."
    ):
        if not should_check_module(modname):
            continue

        try:
            module = importlib.import_module(modname)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Skip non-model classes
                if not hasattr(obj, "__tablename__") or obj.__module__ != module.__name__:
                    continue

                # Check for 'id' field (primary key)
                if not hasattr(obj, "id"):
                    continue

                # Get the id column definition
                id_attr = obj.id
                if not hasattr(id_attr, "expression"):
                    continue

                id_col = id_attr.expression
                if not hasattr(id_col, "type"):
                    continue

                # Check if it's a UUID type
                col_type = str(type(id_col.type).__name__)
                if "UUID" in col_type:
                    # Check for server_default
                    server_default = getattr(id_col, "server_default", None)
                    if server_default is None:
                        issues.append(f"{name} (id field): UUID primary key missing server_default")
                    else:
                        # Check if it uses uuidv7() (native PG18+) or uuid_generate_v7() (pg_uuidv7 extension) vs v4 (incorrect)
                        default_text = (
                            str(server_default.arg)
                            if hasattr(server_default, "arg")
                            else str(server_default)
                        )
                        if (
                            "uuid_generate_v7" not in default_text
                            and "uuidv7" not in default_text
                            and ("uuid4" in default_text or "uuid_generate_v4" in default_text)
                        ):
                            issues.append(
                                f"{name} (id field): uses UUID v4 instead of UUID v7 (use server_default=text('uuidv7()'), recommended for PG18+)"
                            )

                # Check for external platform IDs (should be BigInteger or String, not UUID)
                for attr_name in dir(obj):
                    if attr_name.startswith("_") or attr_name == "id":
                        continue

                    # Check for platform ID fields (discord_id, twitter_id, github_id, snowflake_id, etc.)
                    platform_patterns = [
                        "discord_id",
                        "twitter_id",
                        "github_id",
                        "snowflake_id",
                        "platform_id",
                    ]
                    if not any(pattern in attr_name.lower() for pattern in platform_patterns):
                        continue

                    attr = getattr(obj, attr_name)
                    if not hasattr(attr, "expression"):
                        continue

                    col = attr.expression
                    if not hasattr(col, "type"):
                        continue

                    # External IDs should NOT be UUID type
                    col_type_str = str(type(col.type).__name__)
                    if "UUID" in col_type_str:
                        issues.append(
                            f"{name} ({attr_name}): external platform ID should be BigInteger or String, not UUID"
                        )

        except Exception:
            pass

    return issues


def main():  # noqa: PLR0912
    """Run all schema consistency checks.

    Orchestration function running multiple independent validation checks.
    """
    print("=" * 80)
    print("SCHEMA CONSISTENCY VALIDATION")
    print("=" * 80)

    families = discover_schema_families()
    print(f"\nDiscovered {len(families)} schema families")

    # Run checks
    all_issues = []

    print("\n1. Checking BigInteger field validators...")
    bigint_issues = check_biginteger_validators(families)
    if bigint_issues:
        print(f"   ❌ Found {len(bigint_issues)} issues:")
        for issue in bigint_issues:
            print(f"      - {issue}")
        all_issues.extend(bigint_issues)
    else:
        print("   ✅ All BigInteger fields have proper validators")

    print("\n2. Checking Response schemas have from_attributes=True...")
    from_attrs_issues = check_response_from_attributes(families)
    if from_attrs_issues:
        print(f"   ❌ Found {len(from_attrs_issues)} issues:")
        for issue in from_attrs_issues:
            print(f"      - {issue}")
        all_issues.extend(from_attrs_issues)
    else:
        print("   ✅ All Response schemas have from_attributes=True")

    print("\n3. Checking InDB schemas forbid extra fields...")
    forbid_issues = check_indb_forbid_extra(families)
    if forbid_issues:
        print(f"   ❌ Found {len(forbid_issues)} issues:")
        for issue in forbid_issues:
            print(f"      - {issue}")
        all_issues.extend(forbid_issues)
    else:
        print("   ✅ All InDB schemas forbid extra fields")

    print("\n4. Checking UUID v7 primary key usage...")
    uuid_issues = check_uuid_v7_primary_keys()
    if uuid_issues:
        print(f"   ❌ Found {len(uuid_issues)} issues:")
        for issue in uuid_issues:
            print(f"      - {issue}")
        all_issues.extend(uuid_issues)
    else:
        print("   ✅ All UUID primary keys follow v7 standards")

    # Summary
    print("\n" + "=" * 80)
    if all_issues:
        print(f"❌ FAILED: Found {len(all_issues)} schema consistency issues")
        print("=" * 80)
        return 1
    print("✅ SUCCESS: All schema consistency checks passed")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
