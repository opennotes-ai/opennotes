"""Unit tests for FilterBuilder core operators.

This module tests the core filter operators in src/common/filters.py:
- Equality (eq) and inequality (neq) operators
- Comparison operators (gt, gte, lt, lte)
- List operators (in, not_in)
- Null checking (isnull)
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.common.filters import FilterBuilder, FilterField, FilterOperator


class Base(DeclarativeBase):
    pass


class TestModel(Base):
    """Test model for filter builder tests."""

    __tablename__ = "test_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50))
    count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)


def compile_condition(condition) -> str:
    """Compile a SQLAlchemy condition to a string for comparison.

    Uses PostgreSQL dialect for consistent output format.
    """
    return str(
        condition.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


class TestFilterBuilderCoreOperators:
    """Tests for FilterBuilder core operators."""

    def test_eq_operator(self):
        """Test equality filter (default operator)."""
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.EQ]))

        filters = builder.build(status="active")

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.status = 'active'" in sql

    def test_eq_operator_is_default(self):
        """Test that equality is the default operator when no suffix provided."""
        builder = FilterBuilder(FilterField(TestModel.name, operators=[FilterOperator.EQ]))

        filters = builder.build(name="John")

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.name = 'John'" in sql

    def test_neq_operator(self):
        """Test not equal filter."""
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.NEQ]))

        filters = builder.build(status__neq="deleted")

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.status != 'deleted'" in sql

    def test_gt_operator(self):
        """Test greater than filter."""
        builder = FilterBuilder(FilterField(TestModel.count, operators=[FilterOperator.GT]))

        filters = builder.build(count__gt=10)

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.count > 10" in sql

    def test_gte_operator(self):
        """Test greater than or equal filter."""
        builder = FilterBuilder(FilterField(TestModel.count, operators=[FilterOperator.GTE]))

        filters = builder.build(count__gte=5)

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.count >= 5" in sql

    def test_lt_operator(self):
        """Test less than filter."""
        builder = FilterBuilder(FilterField(TestModel.count, operators=[FilterOperator.LT]))

        filters = builder.build(count__lt=100)

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.count < 100" in sql

    def test_lte_operator(self):
        """Test less than or equal filter."""
        builder = FilterBuilder(FilterField(TestModel.count, operators=[FilterOperator.LTE]))

        filters = builder.build(count__lte=50)

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.count <= 50" in sql

    def test_in_operator(self):
        """Test IN list filter."""
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.IN]))

        filters = builder.build(status__in=["active", "pending", "approved"])

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.status IN ('active', 'pending', 'approved')" in sql

    def test_in_operator_with_single_value(self):
        """Test IN operator with a single value (not a list)."""
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.IN]))

        filters = builder.build(status__in="active")

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.status IN ('active')" in sql

    def test_not_in_operator(self):
        """Test NOT IN list filter."""
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.NOT_IN]))

        filters = builder.build(status__not_in=["deleted", "archived"])

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.status NOT IN ('deleted', 'archived')" in sql

    def test_not_in_operator_with_single_value(self):
        """Test NOT IN operator with a single value (not a list)."""
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.NOT_IN]))

        filters = builder.build(status__not_in="deleted")

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.status NOT IN ('deleted')" in sql

    def test_isnull_operator_true(self):
        """Test IS NULL when value is True."""
        builder = FilterBuilder(FilterField(TestModel.name, operators=[FilterOperator.ISNULL]))

        filters = builder.build(name__isnull=True)

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.name IS NULL" in sql

    def test_isnull_operator_false(self):
        """Test IS NOT NULL when value is False."""
        builder = FilterBuilder(FilterField(TestModel.name, operators=[FilterOperator.ISNULL]))

        filters = builder.build(name__isnull=False)

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.name IS NOT NULL" in sql

    def test_datetime_comparison(self):
        """Test comparison operators work with datetime values."""
        builder = FilterBuilder(
            FilterField(TestModel.created_at, operators=[FilterOperator.GTE, FilterOperator.LTE])
        )
        test_date = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        filters = builder.build(created_at__gte=test_date)

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.created_at >=" in sql
        assert "2024-01-01" in sql


class TestFilterBuilderEdgeCases:
    """Tests for edge case handling in FilterBuilder."""

    def test_none_value_skipped(self):
        """None values should not create filters."""
        builder = FilterBuilder(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )

        filters = builder.build(status=None)

        assert len(filters) == 0

    def test_empty_list_for_in_operator(self):
        """Empty list for IN operator still creates condition."""
        builder = FilterBuilder(
            FilterField(TestModel.status, operators=[FilterOperator.IN]),
        )

        filters = builder.build(status__in=[])

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "IN" in sql

    def test_unknown_field_skipped(self):
        """Unknown field names are silently skipped."""
        builder = FilterBuilder(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )

        filters = builder.build(unknown_field="value")

        assert len(filters) == 0

    def test_unsupported_operator_skipped(self):
        """Operators not in field's allowed list are skipped."""
        builder = FilterBuilder(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )

        filters = builder.build(status__neq="pending")

        assert len(filters) == 0

    def test_invalid_operator_treated_as_field_name(self):
        """'field__unknown' where 'unknown' is not a valid operator is treated as field name."""
        builder = FilterBuilder(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )

        filters = builder.build(status__unknown="value")

        assert len(filters) == 0


class TestFilterBuilderConfiguration:
    """Tests for FilterBuilder configuration options."""

    def test_alias_mapping(self):
        """Alias param maps to column correctly."""
        builder = FilterBuilder(
            FilterField(
                TestModel.status,
                alias="state",
                operators=[FilterOperator.EQ],
            ),
        )

        filters = builder.build(state="active")

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.status = 'active'" in sql

    def test_value_transform(self):
        """Transform function is applied to value."""
        builder = FilterBuilder(
            FilterField(
                TestModel.name,
                operators=[FilterOperator.EQ],
                transform=lambda v: v.upper(),
            ),
        )

        filters = builder.build(name="test")

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.name = 'TEST'" in sql

    def test_multiple_operators_same_field(self):
        """Multiple operators for same field work correctly (status + status__neq)."""
        builder = FilterBuilder(
            FilterField(
                TestModel.status,
                operators=[FilterOperator.EQ, FilterOperator.NEQ],
            ),
        )

        filters = builder.build(status="active", status__neq="deleted")

        assert len(filters) == 2
        sql_combined = " ".join(compile_condition(f) for f in filters)
        assert "= 'active'" in sql_combined
        assert "!= 'deleted'" in sql_combined


class TestFilterBuilderCustomFilters:
    """Tests for custom filter functionality."""

    def test_add_custom_filter(self):
        """Custom filter function is called and returns expected condition."""
        builder = FilterBuilder().add_custom_filter(
            "has_items",
            lambda val: TestModel.count > 0 if val else TestModel.count == 0,
        )

        filters = builder.build(has_items=True)

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.count > 0" in sql

    def test_custom_filter_none_result_skipped(self):
        """Custom filter returning None is skipped."""
        builder = FilterBuilder().add_custom_filter(
            "maybe_filter",
            lambda val: None,
        )

        filters = builder.build(maybe_filter="anything")

        assert len(filters) == 0

    def test_custom_filter_with_none_value_skipped(self):
        """Custom filters are not called when value is None."""
        call_count = 0

        def counting_filter(val):
            nonlocal call_count
            call_count += 1
            return TestModel.count > 0

        builder = FilterBuilder().add_custom_filter("counter", counting_filter)

        filters = builder.build(counter=None)

        assert len(filters) == 0
        assert call_count == 0

    def test_custom_filter_chaining(self):
        """Multiple custom filters can be chained via fluent API."""
        builder = (
            FilterBuilder()
            .add_custom_filter("filter_a", lambda v: TestModel.count > 0)
            .add_custom_filter("filter_b", lambda v: TestModel.status == v)
        )

        filters = builder.build(filter_a=True, filter_b="active")

        assert len(filters) == 2
