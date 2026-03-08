import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class _FakeSpan:
    """Minimal fake ReadableSpan with mutable _attributes."""

    def __init__(self, attributes: dict):
        self._attributes = attributes


class TestAttributeSanitizingSpanProcessor:
    def _make_processor(self):
        from src.monitoring.otel import AttributeSanitizingSpanProcessor

        return AttributeSanitizingSpanProcessor()

    def test_valid_primitives_pass_through(self):
        processor = self._make_processor()
        attrs = {
            "str_key": "hello",
            "int_key": 42,
            "float_key": 3.14,
            "bool_key": True,
            "bytes_key": b"raw",
        }
        span = _FakeSpan(dict(attrs))
        processor.on_end(span)
        assert span._attributes == attrs

    def test_omit_sentinel_removed(self):
        sentinel = SimpleNamespace(name="Omit")
        processor = self._make_processor()
        span = _FakeSpan({"good": "value", "bad": sentinel})
        processor.on_end(span)
        assert span._attributes == {"good": "value"}

    def test_none_values_removed(self):
        processor = self._make_processor()
        span = _FakeSpan({"good": 1, "none_val": None})
        processor.on_end(span)
        assert span._attributes == {"good": 1}

    def test_list_of_valid_primitives_passes(self):
        processor = self._make_processor()
        attrs = {"tags": ["a", "b", "c"], "ids": [1, 2, 3]}
        span = _FakeSpan(dict(attrs))
        processor.on_end(span)
        assert span._attributes == attrs

    def test_list_containing_non_primitives_removed(self):
        processor = self._make_processor()
        sentinel = SimpleNamespace(name="Omit")
        span = _FakeSpan({"good": "ok", "mixed": [1, sentinel, "x"]})
        processor.on_end(span)
        assert span._attributes == {"good": "ok"}

    def test_tuple_of_valid_primitives_passes(self):
        processor = self._make_processor()
        span = _FakeSpan({"scores": (1.0, 2.0, 3.0)})
        processor.on_end(span)
        assert span._attributes == {"scores": (1.0, 2.0, 3.0)}

    def test_empty_attributes_no_error(self):
        processor = self._make_processor()
        span = _FakeSpan({})
        processor.on_end(span)
        assert span._attributes == {}

    def test_no_attributes_attr_no_error(self):
        processor = self._make_processor()
        span = MagicMock(spec=[])
        processor.on_end(span)

    def test_none_attributes_no_error(self):
        processor = self._make_processor()
        span = _FakeSpan({})
        span._attributes = None
        processor.on_end(span)

    def test_on_start_is_noop(self):
        processor = self._make_processor()
        processor.on_start(MagicMock(), None)

    def test_shutdown_is_noop(self):
        processor = self._make_processor()
        processor.shutdown()

    def test_force_flush_returns_true(self):
        processor = self._make_processor()
        assert processor.force_flush() is True

    def test_custom_object_attribute_removed(self):
        processor = self._make_processor()

        class CustomObj:
            pass

        span = _FakeSpan({"valid": "yes", "obj": CustomObj()})
        processor.on_end(span)
        assert span._attributes == {"valid": "yes"}

    def test_on_end_exception_does_not_propagate(self):
        processor = self._make_processor()
        span = _FakeSpan({"key": "value"})
        span._attributes = property(lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
        processor.on_end(span)


class TestAttributeSanitizingProcessorFactory:
    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        from src.monitoring.otel import AttributeSanitizingSpanProcessor

        AttributeSanitizingSpanProcessor.instance = None
        yield
        AttributeSanitizingSpanProcessor.instance = None

    def test_factory_on_end_filters_invalid_attributes(self):
        from src.monitoring.otel import _get_attribute_sanitizing_processor

        processor = _get_attribute_sanitizing_processor()
        sentinel = SimpleNamespace(name="Omit")
        span = _FakeSpan({"good": "value", "bad": sentinel})
        processor.on_end(span)
        assert span._attributes == {"good": "value"}

    def test_factory_returns_singleton(self):
        from src.monitoring.otel import _get_attribute_sanitizing_processor

        first = _get_attribute_sanitizing_processor()
        second = _get_attribute_sanitizing_processor()
        assert first is second

    def test_factory_instance_is_span_processor(self):
        from opentelemetry.sdk.trace import SpanProcessor as SpanProcessorBase

        from src.monitoring.otel import _get_attribute_sanitizing_processor

        processor = _get_attribute_sanitizing_processor()
        assert isinstance(processor, SpanProcessorBase)

    def test_factory_full_integration_sentinel_removed(self):
        from src.monitoring.otel import _get_attribute_sanitizing_processor

        processor = _get_attribute_sanitizing_processor()
        sentinel = type("NOT_GIVEN", (), {})()
        span = _FakeSpan(
            {
                "http.method": "GET",
                "http.url": "https://example.com",
                "llm.api_key": sentinel,
                "count": 42,
            }
        )
        processor.on_end(span)
        assert span._attributes == {
            "http.method": "GET",
            "http.url": "https://example.com",
            "count": 42,
        }

    def test_factory_on_end_exception_is_suppressed(self, caplog):
        from src.monitoring.otel import _get_attribute_sanitizing_processor

        processor = _get_attribute_sanitizing_processor()

        class _ExplodingSpan:
            @property
            def _attributes(self):
                raise RuntimeError("kaboom")

        with caplog.at_level(logging.WARNING, logger="src.monitoring.otel"):
            processor.on_end(_ExplodingSpan())

    def test_factory_on_end_with_empty_span(self):
        from src.monitoring.otel import _get_attribute_sanitizing_processor

        processor = _get_attribute_sanitizing_processor()
        span = _FakeSpan({})
        processor.on_end(span)
        assert span._attributes == {}


class TestBaggageSpanProcessorFactory:
    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        from src.monitoring.otel import BaggageSpanProcessor

        BaggageSpanProcessor.instance = None
        yield
        BaggageSpanProcessor.instance = None

    def test_factory_on_start_sets_baggage_attributes(self):
        from opentelemetry import baggage, context

        from src.monitoring.otel import _get_baggage_span_processor

        processor = _get_baggage_span_processor()
        ctx = baggage.set_baggage("request_id", "req-123", context.get_current())
        mock_span = MagicMock()
        processor.on_start(mock_span, ctx)
        mock_span.set_attribute.assert_any_call("request_id", "req-123")
