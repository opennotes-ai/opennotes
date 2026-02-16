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

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, overload

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
class JoinSpec:
    """Specification for a JOIN clause needed by a filter.

    Attributes:
        target: The SQLAlchemy model or table to join to.
        onclause: The ON clause for the join (e.g., Note.request_id == Request.request_id).
    """

    target: Any
    onclause: Any


class FilterResult:
    """Result of FilterBuilder.build() containing conditions and joins.

    Backward-compatible with list[Any] -- supports iteration, len, bool,
    indexing, and append so existing code that treats build() output as a
    plain list continues to work unchanged.
    """

    def __init__(
        self,
        conditions: list[Any] | None = None,
        joins: list[JoinSpec] | None = None,
    ) -> None:
        self.conditions: list[Any] = conditions if conditions is not None else []
        self.joins: list[JoinSpec] = joins if joins is not None else []

    def __iter__(self) -> Iterator[Any]:
        return iter(self.conditions)

    def __len__(self) -> int:
        return len(self.conditions)

    def __bool__(self) -> bool:
        return bool(self.conditions)

    @overload
    def __getitem__(self, index: int) -> Any: ...

    @overload
    def __getitem__(self, index: slice) -> list[Any]: ...

    def __getitem__(self, index: int | slice) -> Any:
        return self.conditions[index]

    def append(self, item: Any) -> None:
        self.conditions.append(item)

    def extend(self, items: list[Any]) -> None:
        self.conditions.extend(items)


@dataclass
class FilterField:
    """Configuration for a filterable field.

    Attributes:
        column: SQLAlchemy column attribute to filter on.
        operators: List of allowed operators for this field. Defaults to [EQ].
        alias: JSON:API parameter name if different from the column name.
        transform: Optional function to transform the filter value before applying.
        joins: Optional list of JoinSpecs required when this filter is active.
    """

    column: InstrumentedAttribute
    operators: list[FilterOperator] = field(default_factory=lambda: [FilterOperator.EQ])
    alias: str | None = None
    transform: Callable[[Any], Any] | None = None
    joins: list[JoinSpec] = field(default_factory=list)


class FilterBuilder:
    """Build SQLAlchemy filter conditions from JSON:API query parameters.

    Supports standard operators (eq, neq, gte, lte, in, not_in, isnull),
    custom filter functions for complex conditions like subqueries,
    auth-gated filters that require async authorization checks, and
    join-based filters that add JOIN clauses to queries.

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
        self._auth_gated_fields: set[str] = set()

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

    def add_auth_gated_filter(
        self,
        filter_field: FilterField,
    ) -> "FilterBuilder":
        """Register a filter field that requires async authorization before use.

        Auth-gated filters work like normal FilterFields but are flagged so that
        build_async() knows to run the corresponding auth check before building
        the condition.

        Args:
            filter_field: FilterField to register as auth-gated.

        Returns:
            Self for method chaining.
        """
        key = filter_field.alias if filter_field.alias else filter_field.column.key
        self._fields[key] = filter_field
        self._auth_gated_fields.add(key)
        return self

    async def build_async(
        self,
        auth_checks: dict[str, Callable[[Any], Awaitable[None]]] | None = None,
        **kwargs: Any,
    ) -> "FilterResult":
        """Build filter conditions with async authorization checks.

        Runs auth checks for any auth-gated fields that have non-None values
        before delegating to build() for the actual conditions.

        Args:
            auth_checks: Mapping of field names to async callables. Each callable
                receives the filter value and should raise an exception (e.g.,
                HTTPException) if authorization fails.
            **kwargs: Filter parameters (same as build()).

        Returns:
            FilterResult containing conditions and any required joins.
        """
        if auth_checks:
            for name, check_fn in auth_checks.items():
                value = kwargs.get(name)
                if value is not None and name in self._auth_gated_fields:
                    await check_fn(value)

        return self.build(**kwargs)

    def build(self, **kwargs: Any) -> "FilterResult":
        """Build filter conditions from keyword arguments.

        Args:
            **kwargs: Filter parameters in format:
                - field=value (equality)
                - field__operator=value (other operators)

        Returns:
            FilterResult containing conditions and any required joins.
        """
        conditions: list[Any] = []
        joins: list[JoinSpec] = []
        seen_joins: set[int] = set()

        for param, value in kwargs.items():
            if value is None:
                continue

            if param in self._custom_filters:
                condition = self._custom_filters[param](value)
                if condition is not None:
                    conditions.append(condition)
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
                conditions.append(condition)
                for join_spec in filter_field.joins:
                    join_id = id(join_spec)
                    if join_id not in seen_joins:
                        seen_joins.add(join_id)
                        joins.append(join_spec)

        return FilterResult(conditions=conditions, joins=joins)

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
