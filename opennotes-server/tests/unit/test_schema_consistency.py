"""
Automated schema consistency validation across model variations.

This test suite automatically detects schema drift between related models
(Create, Update, InDB, Response) to prevent bugs from type mismatches or
missing field conversions.

Key validations:
- Field type consistency across schema chains
- Required validators for BigInteger → string conversions
- Missing fields in related schemas
- Proper Response schema validators for ORM conversion
- Model config consistency (from_attributes, extra, etc.)

Run with: mise run test:server tests/test_schema_consistency.py
"""

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from pydantic import BaseModel
from pydantic.fields import FieldInfo


class SchemaFamily:
    """
    Represents a family of related schemas (e.g., Note, Request, Rating).

    A schema family typically consists of:
    - Base: Common fields
    - Create: Fields for creation
    - Update: Optional fields for updates
    - InDB: Complete database representation
    - Response: API response format
    """

    def __init__(self, name: str):
        self.name = name
        self.base: type[BaseModel] | None = None
        self.create: type[BaseModel] | None = None
        self.update: type[BaseModel] | None = None
        self.indb: type[BaseModel] | None = None
        self.response: type[BaseModel] | None = None

    def add_schema(self, schema_class: type[BaseModel], suffix: str) -> None:
        """Add a schema to the family based on its suffix."""
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
        """Return all schemas in the family."""
        return [
            ("Base", self.base),
            ("Create", self.create),
            ("Update", self.update),
            ("InDB", self.indb),
            ("Response", self.response),
        ]

    def has_schemas(self) -> bool:
        """Check if family has any schemas."""
        return any(s is not None for _, s in self.get_all_schemas())


def discover_schema_families() -> dict[str, SchemaFamily]:
    """
    Discover all schema families in the codebase.

    Returns:
        dict mapping family name to SchemaFamily object
    """
    families: dict[str, SchemaFamily] = {}

    src_path = Path(__file__).parent.parent.parent / "src"

    exclude_patterns = [
        "__pycache__",
        ".pyc",
        "migrations/",
        "alembic/",
        "tests/",
    ]

    def should_check_module(module_path: str) -> bool:
        return not any(pattern in module_path for pattern in exclude_patterns)

    # Scan all modules for Pydantic schemas
    for _importer, modname, _ispkg in pkgutil.walk_packages(
        path=[str(src_path)],
        prefix="src.",
    ):
        if not should_check_module(modname):
            continue

        try:
            module = importlib.import_module(modname)

            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Only check Pydantic schemas defined in this module
                if (
                    not issubclass(obj, BaseModel)
                    or obj is BaseModel
                    or obj.__module__ != module.__name__
                ):
                    continue

                # Try to extract family name and suffix
                # Common patterns: NoteCreate, NoteInDB, NoteResponse, etc.
                for suffix in ["Base", "Create", "Update", "InDB", "Response"]:
                    if name.endswith(suffix):
                        family_name = name[: -len(suffix)]
                        if family_name not in families:
                            families[family_name] = SchemaFamily(family_name)
                        families[family_name].add_schema(obj, suffix)
                        break

        except Exception:
            # Skip modules that can't be imported
            pass

    # Filter out families that don't have meaningful schemas
    return {name: family for name, family in families.items() if family.has_schemas()}


def get_field_info(schema: type[BaseModel]) -> dict[str, tuple[type, FieldInfo]]:
    """
    Get field information from a Pydantic schema.

    Returns:
        dict mapping field name to (type, FieldInfo)
    """
    return {name: (field.annotation, field) for name, field in schema.model_fields.items()}


def is_biginteger_field(field_name: str) -> bool:
    """
    Check if a field name suggests it's a BigInteger field.

    BigInteger fields (like platform_message_id) need special handling
    for JavaScript BigInt compatibility.
    """
    # Common patterns for BigInteger fields
    bigint_patterns = ["_id", "platform_message_id", "note_id", "request_id", "message_id"]
    return any(pattern in field_name.lower() for pattern in bigint_patterns)


def normalize_type(type_annotation: Any) -> str:
    """
    Normalize a type annotation to a comparable string.

    Handles Union types, Optional types, etc.
    """
    origin = get_origin(type_annotation)
    args = get_args(type_annotation)

    if origin is None:
        # Simple type
        return str(type_annotation)

    # Handle Union types (including Optional)
    if origin is type(None) or str(origin) == "typing.Union":
        # Sort args to normalize "int | str" vs "str | int"
        normalized_args = sorted(normalize_type(arg) for arg in args)
        return f"Union[{', '.join(normalized_args)}]"

    # Handle list, dict, etc.
    if args:
        normalized_args = ", ".join(normalize_type(arg) for arg in args)
        return f"{origin.__name__}[{normalized_args}]"

    return str(origin)


def has_field_validator(schema: type[BaseModel], field_name: str) -> bool:
    """
    Check if a schema has a field validator for the given field.

    This is important for Response schemas that need to convert ORM values.
    """
    # Check if schema has any validators
    if not hasattr(schema, "__pydantic_decorators__"):
        return False

    decorators = schema.__pydantic_decorators__

    # Check field validators
    if hasattr(decorators, "field_validators"):
        validators = decorators.field_validators
        # Field validators can be registered under the field name or "__all__"
        return field_name in validators or "__all__" in validators

    return False


class TestSchemaConsistency:
    """
    Automated tests for schema consistency across Create/InDB/Response chains.

    These tests use introspection only and don't require database access.
    """

    @pytest.fixture
    def schema_families(self) -> dict[str, SchemaFamily]:
        """Discover all schema families in the codebase."""
        return discover_schema_families()

    def test_discover_schema_families(self, schema_families: dict[str, SchemaFamily]):
        """
        Verify that schema families are discovered correctly.

        This test documents which schema families exist in the codebase.
        """
        assert len(schema_families) > 0, "No schema families discovered"

        # Print discovered families for debugging
        print("\n=== Discovered Schema Families ===")
        for name, family in sorted(schema_families.items()):
            schemas = [suffix for suffix, schema in family.get_all_schemas() if schema is not None]
            print(f"{name}: {', '.join(schemas)}")

    def test_biginteger_fields_have_validators_in_response(
        self, schema_families: dict[str, SchemaFamily]
    ):
        """
        Verify that BigInteger fields have validators in Response schemas.

        BigInteger fields (like platform_message_id) must be converted to strings
        in Response schemas for JavaScript BigInt compatibility.
        """
        issues = []

        for family_name, family in schema_families.items():
            if not family.response:
                continue

            response_fields = get_field_info(family.response)

            for field_name, (_field_type, _field_info) in response_fields.items():
                # Skip non-BigInteger fields
                if not is_biginteger_field(field_name):
                    continue

                # Check if field is int or int|str in InDB (database type)
                if family.indb:
                    indb_fields = get_field_info(family.indb)
                    if field_name in indb_fields:
                        indb_type = normalize_type(indb_fields[field_name][0])
                        # If InDB has int, Response should convert to str
                        if (
                            "int" in indb_type.lower()
                            and "str" not in indb_type.lower()
                            and not has_field_validator(family.response, field_name)
                        ):
                            issues.append(
                                f"{family_name}.{field_name}: "
                                f"InDB type is {indb_type}, Response must have field_validator "
                                f"to convert int→str for JavaScript BigInt compatibility"
                            )

        if issues:
            error_msg = (
                "BigInteger fields missing validators in Response schemas:\n"
                + "\n".join(f"  - {issue}" for issue in issues)
                + "\n\nAdd field_validator to convert int→str:\n"
                + "  @field_validator('field_name', mode='before')\n"
                + "  @classmethod\n"
                + "  def convert_field_to_string(cls, value: int | str) -> str:\n"
                + "      return str(value)\n"
            )
            pytest.fail(error_msg)

    def test_field_type_consistency_create_to_indb(self, schema_families: dict[str, SchemaFamily]):
        """
        Verify field types are consistent between Create and InDB schemas.

        Create schemas define input types, InDB schemas define database types.
        They should match for shared fields (excluding auto-generated fields).
        """
        issues = []

        for family_name, family in schema_families.items():
            if not family.create or not family.indb:
                continue

            create_fields = get_field_info(family.create)
            indb_fields = get_field_info(family.indb)

            # Check fields present in both Create and InDB
            common_fields = set(create_fields.keys()) & set(indb_fields.keys())

            for field_name in common_fields:
                create_type = normalize_type(create_fields[field_name][0])
                indb_type = normalize_type(indb_fields[field_name][0])

                # Types should match or be compatible
                # Allow int|str in Create to become int in InDB (validated conversion)
                if create_type != indb_type:
                    # Check for acceptable conversions
                    acceptable_conversions = [
                        # Create accepts int|str, InDB stores int
                        (create_type, indb_type, "Union[int, str]", "int"),
                        # Create accepts str, InDB stores UUID
                        (create_type, indb_type, "str", "UUID"),
                    ]

                    is_acceptable = any(
                        expected_create in create_type and expected_indb in indb_type
                        for _, _, expected_create, expected_indb in acceptable_conversions
                    )

                    if not is_acceptable:
                        issues.append(
                            f"{family_name}.{field_name}: "
                            f"Create type ({create_type}) != InDB type ({indb_type})"
                        )

        if issues:
            error_msg = (
                "Field type mismatches between Create and InDB schemas:\n"
                + "\n".join(f"  - {issue}" for issue in issues)
                + "\n\nEnsure Create and InDB schemas have consistent types for shared fields.\n"
                + "If intentional (e.g., int|str → int), add a field_validator in Create schema.\n"
            )
            pytest.fail(error_msg)

    def test_response_schemas_have_from_attributes(self, schema_families: dict[str, SchemaFamily]):
        """
        Verify that Response schemas have from_attributes=True in model_config.

        Response schemas need to convert from ORM models, so they must have
        from_attributes=True.
        """
        issues = []

        for family_name, family in schema_families.items():
            if not family.response:
                continue

            config = family.response.model_config

            if not config.get("from_attributes"):
                issues.append(
                    f"{family_name}Response: missing from_attributes=True in model_config"
                )

        if issues:
            error_msg = (
                "Response schemas missing from_attributes=True:\n"
                + "\n".join(f"  - {issue}" for issue in issues)
                + "\n\nResponse schemas must have from_attributes=True to convert from ORM models.\n"
                + "Add to model_config:\n"
                + "  model_config = ConfigDict(from_attributes=True)\n"
            )
            pytest.fail(error_msg)

    def test_indb_schemas_forbid_extra_fields(self, schema_families: dict[str, SchemaFamily]):
        """
        Verify that InDB schemas have extra='forbid' in model_config.

        InDB schemas should forbid extra fields to catch schema/model mismatches
        during development.
        """
        issues = []

        for family_name, family in schema_families.items():
            if not family.indb:
                continue

            config = family.indb.model_config

            if config.get("extra") != "forbid":
                issues.append(f"{family_name}InDB: missing extra='forbid' in model_config")

        if issues:
            error_msg = (
                "InDB schemas missing extra='forbid':\n"
                + "\n".join(f"  - {issue}" for issue in issues)
                + "\n\nInDB schemas should forbid extra fields to catch schema/model mismatches.\n"
                + "Add to model_config:\n"
                + "  model_config = ConfigDict(extra='forbid', from_attributes=True)\n"
            )
            pytest.fail(error_msg)

    def test_missing_fields_in_response_vs_indb(self, schema_families: dict[str, SchemaFamily]):
        """
        Identify fields present in InDB but missing in Response.

        This catches cases where database fields aren't exposed in the API,
        which might be intentional (sensitive data) or a bug (forgot to add).
        """
        # Track potentially missing fields
        info_messages = []

        for family_name, family in schema_families.items():
            if not family.indb or not family.response:
                continue

            indb_fields = set(get_field_info(family.indb).keys())
            response_fields = set(get_field_info(family.response).keys())

            # Fields in InDB but not in Response
            missing_in_response = indb_fields - response_fields

            # Filter out known acceptable differences
            acceptable_missing = {
                "id",  # Often mapped differently
                "created_at",  # Inherited from base
                "updated_at",  # Inherited from base
            }

            missing_in_response = missing_in_response - acceptable_missing

            if missing_in_response:
                info_messages.append(
                    f"{family_name}: InDB fields not in Response: {', '.join(sorted(missing_in_response))}"
                )

        # This is informational, not a failure
        # Some fields might be intentionally excluded (sensitive data)
        if info_messages:
            print("\n=== Informational: Fields in InDB but not in Response ===")
            for msg in info_messages:
                print(f"  - {msg}")
            print(
                "\nNote: These might be intentional (sensitive fields) or bugs (forgot to add).\n"
            )


class TestSchemaFamilyDocumentation:
    """
    Document all schema families for reference and code review.

    These tests use introspection only and don't require database access.
    """

    @pytest.fixture
    def schema_families(self) -> dict[str, SchemaFamily]:
        """Discover all schema families in the codebase."""
        return discover_schema_families()

    def test_document_all_schema_families(self, schema_families: dict[str, SchemaFamily]):
        """
        Generate comprehensive documentation of all schema families.

        This test always passes but produces detailed output about the schema
        structure for code review and documentation purposes.
        """
        print("\n" + "=" * 80)
        print("SCHEMA FAMILY DOCUMENTATION")
        print("=" * 80)

        for family_name in sorted(schema_families.keys()):
            family = schema_families[family_name]
            print(f"\n{family_name} Family:")
            print("-" * 40)

            for suffix, schema in family.get_all_schemas():
                if schema is None:
                    continue

                print(f"\n  {suffix}:")
                print(f"    Module: {schema.__module__}")

                # Document fields
                fields = get_field_info(schema)
                if fields:
                    print("    Fields:")
                    for field_name, (field_type, field_info) in sorted(fields.items()):
                        required = field_info.is_required()
                        default = field_info.default if not required else "REQUIRED"
                        print(f"      - {field_name}: {normalize_type(field_type)} = {default}")

                # Document model config
                if hasattr(schema, "model_config"):
                    config = schema.model_config
                    print("    Config:")
                    for key in ["from_attributes", "extra", "strict", "use_enum_values"]:
                        if key in config:
                            print(f"      - {key}: {config[key]}")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
