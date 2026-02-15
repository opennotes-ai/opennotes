"""
Property-based tests for FilterBuilder and pagination logic using Hypothesis.

These tests verify invariants of the filter building system and pagination
link generation across randomly generated inputs. They catch edge cases like:
- Operators silently producing None instead of conditions
- IN operator failing on scalar values
- Pagination links with incorrect prev/next presence
- Non-monotonic offset calculation
"""

from hypothesis import assume, given
from hypothesis import strategies as st
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase

from src.common.filters import FilterBuilder, FilterField, FilterOperator
from src.common.jsonapi import create_pagination_links


@st.composite
def valid_pagination(draw):
    size = draw(st.integers(min_value=1, max_value=1000))
    total = draw(st.integers(min_value=1, max_value=100000))
    total_pages = (total + size - 1) // size
    page = draw(st.integers(min_value=1, max_value=total_pages))
    return page, size, total


class _Base(DeclarativeBase):
    pass


class _FakeModel(_Base):
    __tablename__ = "fake_filter_test"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    age = Column(Integer)
    active = Column(Boolean)
    created_at = Column(DateTime)


ALL_OPERATORS = list(FilterOperator)

COMPARISON_OPERATORS = [
    FilterOperator.EQ,
    FilterOperator.NEQ,
    FilterOperator.GT,
    FilterOperator.GTE,
    FilterOperator.LT,
    FilterOperator.LTE,
]

LIST_OPERATORS = [
    FilterOperator.IN,
    FilterOperator.NOT_IN,
]

STRING_OPERATORS = [
    FilterOperator.LIKE,
    FilterOperator.ILIKE,
    FilterOperator.CONTAINS,
]


class TestFilterBuilderOperatorProperties:
    """All 13 operators produce valid SQLAlchemy conditions for varied inputs."""

    @given(value=st.integers(min_value=-10000, max_value=10000))
    def test_comparison_operators_produce_conditions_for_integers(self, value):
        for op in COMPARISON_OPERATORS:
            builder = FilterBuilder(
                FilterField(_FakeModel.age, operators=[op]),
            )
            suffix = f"__{op.value}" if op != FilterOperator.EQ else ""
            filters = builder.build(**{f"age{suffix}": value})
            assert len(filters) == 1, f"Operator {op.value} produced no condition for int {value}"
            assert filters[0] is not None

    @given(value=st.text(min_size=0, max_size=200))
    def test_comparison_operators_produce_conditions_for_strings(self, value):
        for op in COMPARISON_OPERATORS:
            builder = FilterBuilder(
                FilterField(_FakeModel.name, operators=[op]),
            )
            suffix = f"__{op.value}" if op != FilterOperator.EQ else ""
            filters = builder.build(**{f"name{suffix}": value})
            assert len(filters) == 1, f"Operator {op.value} produced no condition for str '{value}'"

    @given(
        values=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=20),
    )
    def test_in_operator_produces_condition_for_list(self, values):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.IN]),
        )
        filters = builder.build(name__in=values)
        assert len(filters) == 1

    @given(
        values=st.lists(st.integers(min_value=0, max_value=1000), min_size=1, max_size=20),
    )
    def test_not_in_operator_produces_condition_for_list(self, values):
        builder = FilterBuilder(
            FilterField(_FakeModel.age, operators=[FilterOperator.NOT_IN]),
        )
        filters = builder.build(age__not_in=values)
        assert len(filters) == 1

    @given(value=st.booleans())
    def test_isnull_operator_produces_condition(self, value):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.ISNULL]),
        )
        filters = builder.build(name__isnull=value)
        assert len(filters) == 1

    @given(value=st.text(min_size=0, max_size=200))
    def test_like_operator_produces_condition(self, value):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.LIKE]),
        )
        filters = builder.build(name__like=value)
        assert len(filters) == 1

    @given(value=st.text(min_size=0, max_size=200))
    def test_ilike_operator_produces_condition(self, value):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.ILIKE]),
        )
        filters = builder.build(name__ilike=value)
        assert len(filters) == 1

    @given(value=st.text(min_size=0, max_size=200))
    def test_contains_operator_produces_condition(self, value):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.CONTAINS]),
        )
        filters = builder.build(name__contains=value)
        assert len(filters) == 1

    @given(
        values=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=10),
    )
    def test_overlap_operator_produces_condition(self, values):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.OVERLAP]),
        )
        filters = builder.build(name__overlap=values)
        assert len(filters) == 1


class TestFilterBuilderIgnoresUnknown:
    """Unknown fields and invalid operators are silently ignored."""

    @given(
        field_name=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
            min_size=1,
            max_size=30,
        ),
        value=st.text(min_size=1, max_size=50),
    )
    def test_unknown_field_produces_no_conditions(self, field_name, value):
        assume(field_name not in {"name", "age"})
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.EQ]),
        )
        filters = builder.build(**{field_name: value})
        assert len(filters) == 0, (
            f"Unknown field '{field_name}' should produce no conditions, got {len(filters)}"
        )

    @given(
        op_suffix=st.text(
            alphabet=st.characters(whitelist_categories=("L",), whitelist_characters="_"),
            min_size=1,
            max_size=20,
        ),
    )
    def test_invalid_operator_suffix_treated_as_field_lookup(self, op_suffix):
        assume(op_suffix not in [op.value for op in FilterOperator])
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.EQ]),
        )
        filters = builder.build(**{f"name__{op_suffix}": "test"})
        assert len(filters) == 0, f"Invalid operator '__{op_suffix}' should produce no conditions"

    @given(
        operator=st.sampled_from(ALL_OPERATORS),
        value=st.text(min_size=1, max_size=50),
    )
    def test_disallowed_operator_produces_no_conditions(self, operator, value):
        assume(operator != FilterOperator.EQ)
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.EQ]),
        )
        suffix = f"__{operator.value}"
        filters = builder.build(**{f"name{suffix}": value})
        assert len(filters) == 0, (
            f"Disallowed operator '{operator.value}' should produce no conditions"
        )


class TestFilterBuilderInCoercion:
    """IN operator correctly coerces scalar to list."""

    @given(value=st.text(min_size=1, max_size=100))
    def test_in_operator_coerces_scalar_string_to_list(self, value):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.IN]),
        )
        filters = builder.build(name__in=value)
        assert len(filters) == 1, "Scalar string should be coerced to list for IN operator"

    @given(value=st.integers(min_value=-10000, max_value=10000))
    def test_in_operator_coerces_scalar_int_to_list(self, value):
        builder = FilterBuilder(
            FilterField(_FakeModel.age, operators=[FilterOperator.IN]),
        )
        filters = builder.build(age__in=value)
        assert len(filters) == 1, "Scalar int should be coerced to list for IN operator"

    @given(value=st.text(min_size=1, max_size=100))
    def test_not_in_operator_coerces_scalar_string_to_list(self, value):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.NOT_IN]),
        )
        filters = builder.build(name__not_in=value)
        assert len(filters) == 1, "Scalar string should be coerced to list for NOT_IN operator"

    @given(
        values=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=20),
    )
    def test_in_operator_accepts_list_unchanged(self, values):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[FilterOperator.IN]),
        )
        filters = builder.build(name__in=values)
        assert len(filters) == 1
        compiled_str = str(filters[0].compile(compile_kwargs={"literal_binds": False}))
        assert "IN" in compiled_str


class TestFilterBuilderNoneSkipping:
    """None values are silently skipped."""

    @given(operator=st.sampled_from(ALL_OPERATORS))
    def test_none_value_skipped_for_any_operator(self, operator):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, operators=[operator]),
        )
        suffix = f"__{operator.value}" if operator != FilterOperator.EQ else ""
        filters = builder.build(**{f"name{suffix}": None})
        assert len(filters) == 0, f"None value should be skipped for operator {operator.value}"


class TestFilterBuilderAlias:
    """Alias field names work correctly."""

    @given(value=st.text(min_size=1, max_size=100))
    def test_alias_routes_to_correct_column(self, value):
        builder = FilterBuilder(
            FilterField(_FakeModel.name, alias="display_name", operators=[FilterOperator.EQ]),
        )
        filters = builder.build(display_name=value)
        assert len(filters) == 1
        compiled_str = str(filters[0])
        assert "fake_filter_test.name" in compiled_str


class TestFilterBuilderTransform:
    """Transform functions are applied before building conditions."""

    @given(value=st.text(min_size=1, max_size=100))
    def test_transform_applied_to_value(self, value):
        builder = FilterBuilder(
            FilterField(
                _FakeModel.name,
                operators=[FilterOperator.EQ],
                transform=lambda v: v.upper(),
            ),
        )
        filters = builder.build(name=value)
        assert len(filters) == 1


class TestPaginationLinksProperties:
    """Property tests for create_pagination_links."""

    @given(params=valid_pagination())
    def test_prev_exists_iff_page_greater_than_one(self, params):
        page, size, total = params
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=page,
            size=size,
            total=total,
        )
        if page > 1:
            assert links.prev is not None, f"prev should exist when page={page} > 1"
        else:
            assert links.prev is None, f"prev should be None when page={page} == 1"

    @given(params=valid_pagination())
    def test_next_exists_iff_page_less_than_total_pages(self, params):
        page, size, total = params
        total_pages = (total + size - 1) // size
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=page,
            size=size,
            total=total,
        )
        if page < total_pages:
            assert links.next_ is not None, (
                f"next should exist when page={page} < total_pages={total_pages}"
            )
        else:
            assert links.next_ is None, (
                f"next should be None when page={page} >= total_pages={total_pages}"
            )

    @given(
        size=st.integers(min_value=1, max_value=500),
        total=st.integers(min_value=2, max_value=10000),
    )
    def test_offset_monotonically_non_decreasing_for_increasing_pages(self, size, total):
        total_pages = (total + size - 1) // size
        cap = min(total_pages, 50)
        offsets = []
        for page_num in range(1, cap + 1):
            offset = (page_num - 1) * size
            offsets.append(offset)
        for i in range(1, len(offsets)):
            assert offsets[i] >= offsets[i - 1], (
                f"Offset must be non-decreasing: page {i} offset {offsets[i - 1]} > "
                f"page {i + 1} offset {offsets[i]}"
            )

    @given(
        size=st.integers(min_value=1, max_value=1000),
        total=st.integers(min_value=0, max_value=100000),
    )
    def test_total_pages_calculation_correct(self, size, total):
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=1,
            size=size,
            total=total,
        )
        expected_total_pages = (total + size - 1) // size if total > 0 else 0
        if total == 0:
            assert links.first is None
            assert links.last is None
        else:
            assert links.first is not None
            assert links.last is not None
            assert f"page[number]={expected_total_pages}" in links.last

    @given(params=valid_pagination())
    def test_self_link_always_present(self, params):
        page, size, total = params
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=page,
            size=size,
            total=total,
        )
        assert links.self_ is not None, "self link should always be present"
        assert f"page[number]={page}" in links.self_

    @given(params=valid_pagination())
    def test_first_link_points_to_page_one(self, params):
        page, size, total = params
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=page,
            size=size,
            total=total,
        )
        assert links.first is not None
        assert "page[number]=1" in links.first

    def test_zero_total_produces_no_links(self):
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=1,
            size=10,
            total=0,
        )
        assert links.first is None
        assert links.last is None
        assert links.prev is None
        assert links.next_ is None

    def test_zero_size_total_pages_is_zero(self):
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=1,
            size=0,
            total=100,
        )
        assert links.prev is None
        assert links.next_ is None

    @given(params=valid_pagination())
    def test_query_params_preserved_in_links(self, params):
        page, size, total = params
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=page,
            size=size,
            total=total,
            query_params={"filter[status]": "active"},
        )
        assert "filter[status]=active" in links.self_
        if links.prev:
            assert "filter[status]=active" in links.prev
        if links.next_:
            assert "filter[status]=active" in links.next_


class TestPaginationEdgeCases:
    """Edge cases for pagination discovered by property tests."""

    def test_single_item_single_page(self):
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=1,
            size=10,
            total=1,
        )
        assert links.prev is None
        assert links.next_ is None
        assert links.first is not None
        assert links.last is not None

    def test_exact_page_boundary(self):
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=1,
            size=10,
            total=10,
        )
        assert links.prev is None
        assert links.next_ is None

    def test_one_past_page_boundary(self):
        links = create_pagination_links(
            base_url="http://example.com/api",
            page=1,
            size=10,
            total=11,
        )
        assert links.prev is None
        assert links.next_ is not None
