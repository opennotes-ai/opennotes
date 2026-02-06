import base64
import json
import pickle
import uuid

import pytest

from src.dbos_workflows.serializer import DBOS_PICKLE_FALLBACK_TOTAL, SafeJsonSerializer

pytestmark = pytest.mark.unit


@pytest.fixture
def serializer() -> SafeJsonSerializer:
    return SafeJsonSerializer()


class TestJsonRoundtrip:
    def test_string(self, serializer: SafeJsonSerializer) -> None:
        assert serializer.deserialize(serializer.serialize("hello")) == "hello"

    def test_integer(self, serializer: SafeJsonSerializer) -> None:
        assert serializer.deserialize(serializer.serialize(42)) == 42

    def test_float(self, serializer: SafeJsonSerializer) -> None:
        assert serializer.deserialize(serializer.serialize(3.14)) == 3.14

    def test_none(self, serializer: SafeJsonSerializer) -> None:
        assert serializer.deserialize(serializer.serialize(None)) is None

    def test_bool(self, serializer: SafeJsonSerializer) -> None:
        assert serializer.deserialize(serializer.serialize(True)) is True
        assert serializer.deserialize(serializer.serialize(False)) is False

    def test_list_of_strings(self, serializer: SafeJsonSerializer) -> None:
        data = ["alpha", "bravo", "charlie"]
        assert serializer.deserialize(serializer.serialize(data)) == data

    def test_empty_list(self, serializer: SafeJsonSerializer) -> None:
        assert serializer.deserialize(serializer.serialize([])) == []

    def test_dict(self, serializer: SafeJsonSerializer) -> None:
        data = {"key": "value", "count": 7}
        assert serializer.deserialize(serializer.serialize(data)) == data

    def test_nested_structure(self, serializer: SafeJsonSerializer) -> None:
        data = {"items": [1, 2, 3], "meta": {"page": 1}}
        assert serializer.deserialize(serializer.serialize(data)) == data

    def test_large_uuid_list(self, serializer: SafeJsonSerializer) -> None:
        data = [str(uuid.uuid4()) for _ in range(1000)]
        result = serializer.deserialize(serializer.serialize(data))
        assert result == data

    def test_workflow_inputs_tuple(self, serializer: SafeJsonSerializer) -> None:
        data = {"args": ("task-123", None, 100), "kwargs": {"batch_size": 50}}
        result = serializer.deserialize(serializer.serialize(data))
        assert result["args"] == ["task-123", None, 100]
        assert result["kwargs"] == {"batch_size": 50}


class TestExceptionSerialization:
    def test_value_error_roundtrip(self, serializer: SafeJsonSerializer) -> None:
        exc = ValueError("something went wrong")
        result = serializer.deserialize(serializer.serialize(exc))
        assert isinstance(result, ValueError)
        assert str(result) == "something went wrong"

    def test_runtime_error_roundtrip(self, serializer: SafeJsonSerializer) -> None:
        exc = RuntimeError("timeout")
        result = serializer.deserialize(serializer.serialize(exc))
        assert isinstance(result, RuntimeError)
        assert str(result) == "timeout"

    def test_type_error_roundtrip(self, serializer: SafeJsonSerializer) -> None:
        exc = TypeError("bad type")
        result = serializer.deserialize(serializer.serialize(exc))
        assert isinstance(result, TypeError)
        assert str(result) == "bad type"

    def test_unknown_exception_becomes_runtime_error(self, serializer: SafeJsonSerializer) -> None:
        exc = ValueError("test")
        serialized = serializer.serialize(exc)
        raw = json.loads(serialized[len(SafeJsonSerializer.JSON_PREFIX) :])
        raw["module"] = "nonexistent.module"
        patched = SafeJsonSerializer.JSON_PREFIX + json.dumps(raw)
        result = serializer.deserialize(patched)
        assert isinstance(result, RuntimeError)

    def test_exception_with_multiple_args(self, serializer: SafeJsonSerializer) -> None:
        exc = OSError(2, "No such file", "/tmp/missing")
        result = serializer.deserialize(serializer.serialize(exc))
        assert isinstance(result, OSError)
        assert "No such file" in str(result)


class TestPickleFallback:
    def test_reads_pickle_encoded_data(self, serializer: SafeJsonSerializer) -> None:
        original = {"key": "value", "count": 42}
        pickle_data = base64.b64encode(pickle.dumps(original)).decode("utf-8")
        result = serializer.deserialize(pickle_data)
        assert result == original

    def test_reads_pickle_string(self, serializer: SafeJsonSerializer) -> None:
        original = "hello world"
        pickle_data = base64.b64encode(pickle.dumps(original)).decode("utf-8")
        result = serializer.deserialize(pickle_data)
        assert result == original

    def test_reads_pickle_list(self, serializer: SafeJsonSerializer) -> None:
        original = [1, 2, 3, "four"]
        pickle_data = base64.b64encode(pickle.dumps(original)).decode("utf-8")
        result = serializer.deserialize(pickle_data)
        assert result == original

    def test_unparseable_data_returned_as_string(self, serializer: SafeJsonSerializer) -> None:
        result = serializer.deserialize("not-json-not-pickle-not-base64!!!")
        assert result == "not-json-not-pickle-not-base64!!!"

    def test_prometheus_counter_increments_on_pickle_fallback(
        self, serializer: SafeJsonSerializer
    ) -> None:
        before = DBOS_PICKLE_FALLBACK_TOTAL._value.get()
        original = "test data"
        pickle_data = base64.b64encode(pickle.dumps(original)).decode("utf-8")
        serializer.deserialize(pickle_data)
        after = DBOS_PICKLE_FALLBACK_TOTAL._value.get()
        assert after == before + 1

    def test_no_counter_increment_on_json_deserialize(self, serializer: SafeJsonSerializer) -> None:
        before = DBOS_PICKLE_FALLBACK_TOTAL._value.get()
        serializer.deserialize(serializer.serialize("hello"))
        after = DBOS_PICKLE_FALLBACK_TOTAL._value.get()
        assert after == before


class TestSerializedFormat:
    def test_serialized_starts_with_json_prefix(self, serializer: SafeJsonSerializer) -> None:
        result = serializer.serialize("test")
        assert result.startswith("json:")

    def test_serialized_is_valid_json_after_prefix(self, serializer: SafeJsonSerializer) -> None:
        result = serializer.serialize({"a": 1})
        json_part = result[len("json:") :]
        parsed = json.loads(json_part)
        assert parsed == {"a": 1}

    def test_new_data_never_uses_pickle(self, serializer: SafeJsonSerializer) -> None:
        result = serializer.serialize([1, 2, 3])
        assert not result.startswith("gASV")
        assert result.startswith("json:")
