from types import SimpleNamespace
from unittest.mock import MagicMock


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
