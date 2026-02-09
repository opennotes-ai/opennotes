"""Shared FilterBuilder for JSON:API routers.

This module provides a reusable filter building utility that consolidates
duplicated filter logic across JSON:API routers while preserving JSON:API
spec compliance.

Usage:
    from src.common.filters import FilterBuilder, FilterField, FilterOperator

    builder = FilterBuilder(
        FilterField(Note.status, operators=[FilterOperator.EQ, FilterOperator.NEQ]),
        FilterField(Note.created_at, operators=[FilterOperator.GTE, FilterOperator.LTE]),
        FilterField(Note.author_id, alias="author_id"),
    )

    filters = builder.build(
        status="published",
        status__neq=None,
        created_at__gte=datetime(2024, 1, 1),
        author_id="user-123",
    )

    query = select(Note).where(and_(*filters))

See ADR-008 for design rationale.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy.orm import InstrumentedAttribute


class FilterOperator(str, Enum):
    """Standard filter operators for JSON:API."""

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    ISNULL = "isnull"
    LIKE = "like"
    ILIKE = "ilike"
    CONTAINS = "contains"
    OVERLAP = "overlap"


@dataclass
class FilterField:
    """Configuration for a filterable field.

    Attributes:
        column: SQLAlchemy column attribute to filter on.
        operators: List of allowed operators for this field. Defaults to [EQ].
        alias: JSON:API parameter name if different from the column name.
        transform: Optional function to transform the filter value before applying.
    """

    column: InstrumentedAttribute
    operators: list[FilterOperator] = field(default_factory=lambda: [FilterOperator.EQ])
    alias: str | None = None
    transform: Callable[[Any], Any] | None = None


class FilterBuilder:
    """Build SQLAlchemy filter conditions from JSON:API query parameters.

    Supports standard operators (eq, neq, gte, lte, in, not_in, isnull) and
    custom filter functions for complex conditions like subqueries.

    Example:
        builder = FilterBuilder(
            FilterField(Note.status, operators=[FilterOperator.EQ, FilterOperator.NEQ]),
            FilterField(Note.created_at, operators=[FilterOperator.GTE, FilterOperator.LTE]),
        ).add_custom_filter(
            "rated_by_not_in",
            lambda values: not_(exists(...))
        )

        filters = builder.build(status="published", created_at__gte=some_date)
    """

    def __init__(self, *fields: FilterField) -> None:
        """Initialize the filter builder with field configurations.

        Args:
            *fields: FilterField instances defining which columns can be filtered.
        """
        self._fields: dict[str, FilterField] = {}
        self._custom_filters: dict[str, Callable[[Any], Any]] = {}

        for f in fields:
            key = f.alias if f.alias else f.column.key
            self._fields[key] = f

    def add_custom_filter(
        self,
        name: str,
        builder_fn: Callable[[Any], Any],
    ) -> "FilterBuilder":
        """Register a custom filter builder for complex conditions.

        Custom filters are useful for subquery-based conditions that can't be
        expressed with simple column operators.

        Args:
            name: Parameter name for this custom filter.
            builder_fn: Function that takes a value and returns a SQLAlchemy condition.

        Returns:
            Self for method chaining.

        Example:
            builder.add_custom_filter(
                "rated_by_not_in",
                lambda values: not_(exists(
                    select(Rating.note_id).where(
                        Rating.rater_id.in_(values)
                    ).where(Rating.note_id == Note.id)
                ))
            )
        """
        self._custom_filters[name] = builder_fn
        return self

    def build(self, **kwargs: Any) -> list[Any]:
        """Build filter conditions from keyword arguments.

        Args:
            **kwargs: Filter parameters in format:
                - field=value (equality)
                - field__operator=value (other operators)

        Returns:
            List of SQLAlchemy filter conditions to use with query.where().
        """
        filters: list[Any] = []

        for param, value in kwargs.items():
            if value is None:
                continue

            if param in self._custom_filters:
                condition = self._custom_filters[param](value)
                if condition is not None:
                    filters.append(condition)
                continue

            field_name, operator = self._parse_param(param)

            filter_field = self._fields.get(field_name)
            if not filter_field:
                continue

            if operator not in filter_field.operators:
                continue

            transformed_value = value
            if filter_field.transform:
                transformed_value = filter_field.transform(value)

            condition = self._build_condition(filter_field.column, operator, transformed_value)
            if condition is not None:
                filters.append(condition)

        return filters

    def _parse_param(self, param: str) -> tuple[str, FilterOperator]:
        """Parse a parameter name into field name and operator.

        Args:
            param: Parameter name like "status" or "created_at__gte".

        Returns:
            Tuple of (field_name, operator).
        """
        if "__" in param:
            field_name, op_str = param.rsplit("__", 1)
            try:
                operator = FilterOperator(op_str)
            except ValueError:
                field_name = param
                operator = FilterOperator.EQ
        else:
            field_name = param
            operator = FilterOperator.EQ

        return field_name, operator

    def _build_condition(
        self,
        column: InstrumentedAttribute,
        operator: FilterOperator,
        value: Any,
    ) -> Any:
        """Build a single filter condition.

        Args:
            column: SQLAlchemy column to filter.
            operator: Filter operator to apply.
            value: Value to filter against.

        Returns:
            SQLAlchemy filter condition, or None if not applicable.
        """
        match operator:
            case FilterOperator.EQ:
                return column == value
            case FilterOperator.NEQ:
                return column != value
            case FilterOperator.GT:
                return column > value
            case FilterOperator.GTE:
                return column >= value
            case FilterOperator.LT:
                return column < value
            case FilterOperator.LTE:
                return column <= value
            case FilterOperator.IN:
                values = value if isinstance(value, list) else [value]
                return column.in_(values)
            case FilterOperator.NOT_IN:
                values = value if isinstance(value, list) else [value]
                return column.not_in(values)
            case FilterOperator.ISNULL:
                return column.is_(None) if value else column.is_not(None)
            case FilterOperator.LIKE:
                return column.like(value)
            case FilterOperator.ILIKE:
                return column.ilike(value)
            case FilterOperator.CONTAINS:
                return column.contains(value)
            case FilterOperator.OVERLAP:
                from sqlalchemy import cast
                from sqlalchemy.dialects.postgresql import ARRAY
                from sqlalchemy.types import Text

                return column.op("&&")(cast(value, ARRAY(Text)))
            case _:
                return None
