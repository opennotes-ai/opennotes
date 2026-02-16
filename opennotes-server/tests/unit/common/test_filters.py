"""Unit tests for FilterBuilder core operators.

This module tests the core filter operators in src/common/filters.py:
- Equality (eq) and inequality (neq) operators
- Comparison operators (gt, gte, lt, lte)
- List operators (in, not_in)
- Null checking (isnull)
- Text matching (like, ilike)
- Array operations (contains, overlap)
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.common.filters import FilterBuilder, FilterField, FilterOperator, FilterResult, JoinSpec


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
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=True)
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RelatedModel(Base):
    """Related model for join-based filter tests."""

    __tablename__ = "related_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(100))


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


class TestFilterBuilderTextAndArrayOperators:
    """Tests for text matching and array operators."""

    def test_like_operator(self):
        """Test LIKE pattern matching filter."""
        builder = FilterBuilder(FilterField(TestModel.name, operators=[FilterOperator.LIKE]))

        filters = builder.build(name__like="%john%")

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.name LIKE" in sql
        assert "john" in sql

    def test_ilike_operator(self):
        """Test case-insensitive ILIKE pattern matching filter."""
        builder = FilterBuilder(FilterField(TestModel.name, operators=[FilterOperator.ILIKE]))

        filters = builder.build(name__ilike="%john%")

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.name ILIKE" in sql
        assert "john" in sql

    def test_contains_operator(self):
        """Test CONTAINS substring matching filter."""
        builder = FilterBuilder(FilterField(TestModel.name, operators=[FilterOperator.CONTAINS]))

        filters = builder.build(name__contains="john")

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.name LIKE '%" in sql
        assert "john" in sql

    def test_overlap_operator(self):
        """Test PostgreSQL array OVERLAP (&&) operator."""
        builder = FilterBuilder(FilterField(TestModel.tags, operators=[FilterOperator.OVERLAP]))

        filters = builder.build(tags__overlap=["python", "rust"])

        assert len(filters) == 1
        sql = compile_condition(filters[0])
        assert "test_models.tags &&" in sql
        assert "python" in sql
        assert "rust" in sql


class TestFilterResult:
    """Tests for FilterResult backward compatibility with list."""

    def test_empty_filter_result(self):
        result = FilterResult()
        assert len(result) == 0
        assert not result
        assert list(result) == []
        assert result.joins == []

    def test_filter_result_with_conditions(self):
        cond1 = TestModel.status == "active"
        cond2 = TestModel.count > 0
        result = FilterResult(conditions=[cond1, cond2])
        assert len(result) == 2
        assert bool(result)
        assert result[0] is cond1
        assert result[1] is cond2

    def test_filter_result_iteration(self):
        cond1 = TestModel.status == "active"
        cond2 = TestModel.count > 0
        result = FilterResult(conditions=[cond1, cond2])
        collected = list(result)
        assert collected == [cond1, cond2]

    def test_filter_result_append(self):
        result = FilterResult()
        cond = TestModel.status == "active"
        result.append(cond)
        assert len(result) == 1
        assert result[0] is cond

    def test_filter_result_extend(self):
        result = FilterResult()
        conds = [TestModel.status == "active", TestModel.count > 0]
        result.extend(conds)
        assert len(result) == 2

    def test_filter_result_with_joins(self):
        join = JoinSpec(target=RelatedModel, onclause=TestModel.related_id == RelatedModel.id)
        result = FilterResult(conditions=[], joins=[join])
        assert len(result.joins) == 1
        assert result.joins[0].target is RelatedModel

    def test_filter_result_slice(self):
        conds = [TestModel.status == "a", TestModel.status == "b", TestModel.status == "c"]
        result = FilterResult(conditions=conds)
        sliced = result[0:2]
        assert len(sliced) == 2

    def test_filter_result_unpacking_with_and(self):
        """FilterResult can be unpacked with * for and_()."""
        from sqlalchemy import and_

        builder = FilterBuilder(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
            FilterField(TestModel.count, operators=[FilterOperator.GT]),
        )
        result = builder.build(status="active", count__gt=5)
        clause = and_(*result)
        sql = compile_condition(clause)
        assert "test_models.status = 'active'" in sql
        assert "test_models.count > 5" in sql


class TestJoinSpec:
    """Tests for JoinSpec dataclass."""

    def test_join_spec_creation(self):
        onclause = TestModel.related_id == RelatedModel.id
        spec = JoinSpec(target=RelatedModel, onclause=onclause)
        assert spec.target is RelatedModel
        assert spec.onclause is onclause


class TestJoinBasedFilters:
    """Tests for join-based filter support (AC#2)."""

    def test_build_returns_filter_result(self):
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.EQ]))
        result = builder.build(status="active")
        assert isinstance(result, FilterResult)

    def test_join_filter_collects_joins(self):
        join_specs = [
            JoinSpec(target=RelatedModel, onclause=TestModel.related_id == RelatedModel.id),
        ]
        builder = FilterBuilder(
            FilterField(
                RelatedModel.label,
                alias="related_label",
                operators=[FilterOperator.EQ],
                joins=join_specs,
            ),
        )
        result = builder.build(related_label="test")
        assert len(result) == 1
        assert len(result.joins) == 1
        assert result.joins[0].target is RelatedModel

    def test_no_joins_when_filter_not_active(self):
        join_specs = [
            JoinSpec(target=RelatedModel, onclause=TestModel.related_id == RelatedModel.id),
        ]
        builder = FilterBuilder(
            FilterField(
                RelatedModel.label,
                alias="related_label",
                operators=[FilterOperator.EQ],
                joins=join_specs,
            ),
        )
        result = builder.build(related_label=None)
        assert len(result) == 0
        assert len(result.joins) == 0

    def test_join_not_duplicated(self):
        shared_join = JoinSpec(
            target=RelatedModel, onclause=TestModel.related_id == RelatedModel.id
        )
        builder = FilterBuilder(
            FilterField(
                RelatedModel.label,
                alias="label_eq",
                operators=[FilterOperator.EQ],
                joins=[shared_join],
            ),
            FilterField(
                RelatedModel.label,
                alias="label_lk",
                operators=[FilterOperator.LIKE],
                joins=[shared_join],
            ),
        )
        result = builder.build(label_eq="test", label_lk__like="%test%")
        assert len(result) == 2
        assert len(result.joins) == 1

    def test_multiple_joins_in_chain(self):
        join1 = JoinSpec(target=RelatedModel, onclause=TestModel.related_id == RelatedModel.id)
        join2 = JoinSpec(target=TestModel, onclause=RelatedModel.id == TestModel.related_id)
        builder = FilterBuilder(
            FilterField(
                RelatedModel.label,
                alias="label",
                operators=[FilterOperator.EQ],
                joins=[join1, join2],
            ),
        )
        result = builder.build(label="test")
        assert len(result.joins) == 2

    def test_mixed_join_and_plain_filters(self):
        join_specs = [
            JoinSpec(target=RelatedModel, onclause=TestModel.related_id == RelatedModel.id),
        ]
        builder = FilterBuilder(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
            FilterField(
                RelatedModel.label,
                alias="label",
                operators=[FilterOperator.EQ],
                joins=join_specs,
            ),
        )
        result = builder.build(status="active", label="test")
        assert len(result) == 2
        assert len(result.joins) == 1


class TestAuthGatedFilters:
    """Tests for auth-gated filter support (AC#1)."""

    def test_add_auth_gated_filter(self):
        builder = FilterBuilder().add_auth_gated_filter(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )
        assert "status" in builder._auth_gated_fields
        assert "status" in builder._fields

    def test_add_auth_gated_filter_chaining(self):
        builder = (
            FilterBuilder()
            .add_auth_gated_filter(
                FilterField(TestModel.status, operators=[FilterOperator.EQ]),
            )
            .add_auth_gated_filter(
                FilterField(TestModel.name, operators=[FilterOperator.EQ]),
            )
        )
        assert "status" in builder._auth_gated_fields
        assert "name" in builder._auth_gated_fields

    @pytest.mark.asyncio
    async def test_build_async_runs_auth_check(self):
        check_called_with = []

        async def mock_auth_check(value):
            check_called_with.append(value)

        builder = FilterBuilder().add_auth_gated_filter(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )
        result = await builder.build_async(
            auth_checks={"status": mock_auth_check},
            status="active",
        )
        assert len(result) == 1
        assert check_called_with == ["active"]

    @pytest.mark.asyncio
    async def test_build_async_skips_check_for_none_value(self):
        check_called = False

        async def mock_auth_check(value):
            nonlocal check_called
            check_called = True

        builder = FilterBuilder().add_auth_gated_filter(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )
        result = await builder.build_async(
            auth_checks={"status": mock_auth_check},
            status=None,
        )
        assert len(result) == 0
        assert not check_called

    @pytest.mark.asyncio
    async def test_build_async_raises_on_auth_failure(self):
        async def failing_auth_check(value):
            raise PermissionError("Not authorized")

        builder = FilterBuilder().add_auth_gated_filter(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )
        with pytest.raises(PermissionError, match="Not authorized"):
            await builder.build_async(
                auth_checks={"status": failing_auth_check},
                status="active",
            )

    @pytest.mark.asyncio
    async def test_build_async_skips_check_for_non_auth_gated_field(self):
        check_called = False

        async def mock_auth_check(value):
            nonlocal check_called
            check_called = True

        builder = FilterBuilder(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )
        result = await builder.build_async(
            auth_checks={"status": mock_auth_check},
            status="active",
        )
        assert len(result) == 1
        assert not check_called

    @pytest.mark.asyncio
    async def test_build_async_without_auth_checks(self):
        builder = FilterBuilder(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )
        result = await builder.build_async(status="active")
        assert len(result) == 1
        sql = compile_condition(result[0])
        assert "test_models.status = 'active'" in sql

    @pytest.mark.asyncio
    async def test_build_async_returns_filter_result(self):
        builder = FilterBuilder(
            FilterField(TestModel.status, operators=[FilterOperator.EQ]),
        )
        result = await builder.build_async(status="active")
        assert isinstance(result, FilterResult)

    @pytest.mark.asyncio
    async def test_build_async_with_joins(self):
        join_specs = [
            JoinSpec(target=RelatedModel, onclause=TestModel.related_id == RelatedModel.id),
        ]
        builder = FilterBuilder().add_auth_gated_filter(
            FilterField(
                RelatedModel.label,
                alias="label",
                operators=[FilterOperator.EQ],
                joins=join_specs,
            ),
        )
        check_called_with = []

        async def mock_auth_check(value):
            check_called_with.append(value)

        result = await builder.build_async(
            auth_checks={"label": mock_auth_check},
            label="test",
        )
        assert len(result) == 1
        assert len(result.joins) == 1
        assert check_called_with == ["test"]


class TestBackwardCompatibility:
    """Tests that existing code patterns still work with FilterResult."""

    def test_build_result_works_with_len(self):
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.EQ]))
        result = builder.build(status="active")
        assert len(result) == 1

    def test_build_result_works_with_bool(self):
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.EQ]))
        result = builder.build(status="active")
        assert result

    def test_build_result_works_with_indexing(self):
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.EQ]))
        result = builder.build(status="active")
        _ = result[0]

    def test_build_result_works_with_iteration(self):
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.EQ]))
        result = builder.build(status="active")
        for condition in result:
            sql = compile_condition(condition)
            assert "test_models.status" in sql

    def test_build_result_works_with_append(self):
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.EQ]))
        result = builder.build(status="active")
        result.append(TestModel.count > 0)
        assert len(result) == 2

    def test_build_result_falsy_when_empty(self):
        builder = FilterBuilder(FilterField(TestModel.status, operators=[FilterOperator.EQ]))
        result = builder.build(status=None)
        assert not result
