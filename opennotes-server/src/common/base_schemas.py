from datetime import datetime
from typing import Any

import pendulum
from pydantic import BaseModel, ConfigDict, field_serializer, model_validator


class StrictInputSchema(BaseModel):
    """
    Base schema for API input schemas (Create/Update requests).

    Applies strict validation to catch client errors early:
    - Rejects unknown fields to catch typos
    - Strips ALL whitespace from strings (including Unicode control characters)
    - Validates on attribute assignment

    Note: Does NOT use strict=True to allow JSON-compatible coercion
    (e.g., string -> enum, string -> int) which is necessary for HTTP APIs.

    The custom validator ensures that string stripping matches Python's built-in
    .strip() method, which removes all Unicode whitespace including control
    characters (Cc category) like \\x1d (Group Separator) and \\x1f (Unit Separator).
    Pydantic's str_strip_whitespace=True only strips standard whitespace (space, tab, newline).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,  # Strip standard whitespace first
        validate_assignment=True,
        use_enum_values=True,
    )

    @model_validator(mode="before")
    @classmethod
    def strip_all_string_fields(cls, data: Any) -> Any:
        """
        Strip ALL whitespace from string fields, matching Python's .strip() behavior.

        This validator runs BEFORE Pydantic's str_strip_whitespace to ensure
        Unicode control characters are also stripped. Python's .strip() removes
        characters from the Unicode categories:
        - Cc (Control characters): \\x00-\\x1f, \\x7f-\\x9f
        - Zs (Space separators): space, NBSP, etc.
        - Zl (Line separators)
        - Zp (Paragraph separators)

        Pydantic's str_strip_whitespace only strips ASCII whitespace (space, tab, newline, etc.).
        """
        if isinstance(data, dict):
            return {key: cls._strip_value(value) for key, value in data.items()}
        return data

    @classmethod
    def _strip_value(cls, value: Any) -> Any:
        """Recursively strip strings, matching Python's .strip() behavior."""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return {k: cls._strip_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [cls._strip_value(item) for item in value]
        return value


class ResponseSchema(BaseModel):
    """
    Base schema for non-ORM response wrappers.

    Used for response schemas that are assembled manually from dicts,
    not constructed directly from SQLAlchemy ORM objects. Lighter than
    SQLAlchemySchema — only includes from_attributes=True.
    """

    model_config = ConfigDict(from_attributes=True)


class SQLAlchemySchema(BaseModel):
    """
    Base schema for SQLAlchemy-backed models with automatic ORM conversion.

    Used for Response and InDB schemas that need to convert from database models.
    """

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
    )


class StrictSQLAlchemySchema(SQLAlchemySchema):
    """
    Strict variant of SQLAlchemySchema for InDB schemas.

    Adds extra='forbid' to catch schema/model mismatches during development.
    """

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
        extra="forbid",
    )


class StrictEventSchema(BaseModel):
    """
    Base schema for event schemas and internal DTOs.

    Applies strict validation for inter-service communication:
    - Rejects unknown fields to catch integration bugs
    - Enforces strict type coercion
    - Validates on attribute assignment
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        strict=True,
    )


class TimestampSchema(SQLAlchemySchema):
    """Base schema for models with timestamp fields."""

    created_at: datetime
    updated_at: datetime | None = None

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        """Serialize created_at to ISO 8601 format with timezone for JavaScript compatibility."""
        # Ensure datetime is timezone-aware (assume UTC if naive)
        if value.tzinfo is None:
            value = value.replace(tzinfo=pendulum.UTC)
        return value.isoformat()

    @field_serializer("updated_at", when_used="json")
    def serialize_updated_at(self, value: datetime | None) -> str | None:
        """Serialize updated_at to ISO 8601 format with timezone for JavaScript compatibility."""
        if value is None:
            return None
        # Ensure datetime is timezone-aware (assume UTC if naive)
        if value.tzinfo is None:
            value = value.replace(tzinfo=pendulum.UTC)
        return value.isoformat()
