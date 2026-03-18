import logging

import pytest

from src.monitoring.otel import (
    InvalidAttributeTypeFilter,
    _install_attribute_warning_filter,
    _remove_attribute_warning_filter,
)


@pytest.mark.unit
class TestInvalidAttributeTypeFilter:
    def test_suppresses_invalid_type_warning(self) -> None:
        f = InvalidAttributeTypeFilter()
        record = logging.LogRecord(
            name="opentelemetry.attributes",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Invalid type %s for attribute '%s' value. Expected one of %s or a sequence of those types",
            args=("Omit", "test.attr", ["bool", "str", "bytes", "int", "float"]),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_suppresses_not_given_type_warning(self) -> None:
        f = InvalidAttributeTypeFilter()
        record = logging.LogRecord(
            name="opentelemetry.attributes",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Invalid type %s for attribute '%s' value. Expected one of %s or a sequence of those types",
            args=("NotGiven", "test.stream", ["bool", "str", "bytes", "int", "float"]),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_suppresses_mixed_types_warning(self) -> None:
        f = InvalidAttributeTypeFilter()
        record = logging.LogRecord(
            name="opentelemetry.attributes",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Attribute %r mixes types %s and %s in attribute value sequence",
            args=("test.attr", "str", "int"),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_passes_unrelated_warning(self) -> None:
        f = InvalidAttributeTypeFilter()
        record = logging.LogRecord(
            name="opentelemetry.attributes",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Some other warning message",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_passes_error_level_messages(self) -> None:
        f = InvalidAttributeTypeFilter()
        record = logging.LogRecord(
            name="opentelemetry.attributes",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Invalid type something serious",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False


@pytest.mark.unit
class TestInstallRemoveFilter:
    def test_install_adds_filter_to_otel_logger(self) -> None:
        _remove_attribute_warning_filter()
        otel_logger = logging.getLogger("opentelemetry.attributes")
        initial_count = sum(
            1 for f in otel_logger.filters if isinstance(f, InvalidAttributeTypeFilter)
        )
        assert initial_count == 0

        _install_attribute_warning_filter()
        after_count = sum(
            1 for f in otel_logger.filters if isinstance(f, InvalidAttributeTypeFilter)
        )
        assert after_count == 1

        _remove_attribute_warning_filter()

    def test_install_is_idempotent(self) -> None:
        _remove_attribute_warning_filter()
        _install_attribute_warning_filter()
        _install_attribute_warning_filter()

        otel_logger = logging.getLogger("opentelemetry.attributes")
        count = sum(1 for f in otel_logger.filters if isinstance(f, InvalidAttributeTypeFilter))
        assert count == 1

        _remove_attribute_warning_filter()

    def test_remove_clears_all_filters(self) -> None:
        _remove_attribute_warning_filter()
        _install_attribute_warning_filter()

        otel_logger = logging.getLogger("opentelemetry.attributes")
        assert any(isinstance(f, InvalidAttributeTypeFilter) for f in otel_logger.filters)

        _remove_attribute_warning_filter()
        assert not any(isinstance(f, InvalidAttributeTypeFilter) for f in otel_logger.filters)

    def test_filter_suppresses_warnings_on_real_otel_logger(self) -> None:
        _remove_attribute_warning_filter()
        _install_attribute_warning_filter()

        otel_logger = logging.getLogger("opentelemetry.attributes")

        record = logging.LogRecord(
            name="opentelemetry.attributes",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Invalid type %s for attribute '%s' value. Expected one of %s or a sequence of those types",
            args=("Omit", "llm.is_streaming", ["bool", "str", "bytes", "int", "float"]),
            exc_info=None,
        )
        assert otel_logger.filter(record) is False

        _remove_attribute_warning_filter()
