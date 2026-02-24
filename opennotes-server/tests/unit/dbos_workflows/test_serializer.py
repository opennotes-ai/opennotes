import json
import logging
import uuid
from unittest.mock import patch

import pendulum
import pytest

from src.dbos_workflows.serializer import SafeJsonSerializer

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


class TestModuleAllowlist:
    def test_blocked_module_returns_runtime_error(self, serializer: SafeJsonSerializer) -> None:
        raw = {
            "__dbos_exception__": True,
            "type": "system",
            "module": "os",
            "args": ["blocked"],
        }
        patched = SafeJsonSerializer.JSON_PREFIX + json.dumps(raw)
        result = serializer.deserialize(patched)
        assert isinstance(result, RuntimeError)
        assert "system" in str(result)
        assert "blocked" in str(result)

    def test_blocked_module_logs_warning(
        self, serializer: SafeJsonSerializer, caplog: pytest.LogCaptureFixture
    ) -> None:
        raw = {
            "__dbos_exception__": True,
            "type": "Exploit",
            "module": "subprocess",
            "args": ["pwned"],
        }
        patched = SafeJsonSerializer.JSON_PREFIX + json.dumps(raw)
        with caplog.at_level(logging.WARNING):
            serializer.deserialize(patched)
        assert "Blocked import of module subprocess" in caplog.text

    def test_builtins_module_allowed(self, serializer: SafeJsonSerializer) -> None:
        exc = ValueError("allowed")
        result = serializer.deserialize(serializer.serialize(exc))
        assert isinstance(result, ValueError)
        assert str(result) == "allowed"


class TestStrictTypeSerialization:
    def test_uuid_raises_type_error(self, serializer: SafeJsonSerializer) -> None:
        with pytest.raises(TypeError, match="UUID is not JSON serializable"):
            serializer.serialize(uuid.uuid4())

    def test_datetime_raises_type_error(self, serializer: SafeJsonSerializer) -> None:
        with pytest.raises(TypeError, match=r"[Dd]ate[Tt]ime is not JSON serializable"):
            serializer.serialize(pendulum.now("UTC"))

    def test_bytes_raises_type_error(self, serializer: SafeJsonSerializer) -> None:
        with pytest.raises(TypeError, match="bytes is not JSON serializable"):
            serializer.serialize(b"raw bytes")


class TestNonJsonFallback:
    def test_unparseable_data_returned_as_string(self, serializer: SafeJsonSerializer) -> None:
        result = serializer.deserialize("not-json-not-pickle-not-base64!!!")
        assert result == "not-json-not-pickle-not-base64!!!"

    def test_non_json_data_returns_raw_string(self, serializer: SafeJsonSerializer) -> None:
        raw_data = "some random legacy data"
        result = serializer.deserialize(raw_data)
        assert result == raw_data

    def test_non_json_data_logs_warning(
        self, serializer: SafeJsonSerializer, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            serializer.deserialize("legacy-data-format")
        assert "Non-JSON data encountered" in caplog.text

    def test_otel_counter_called_on_non_json_data(self, serializer: SafeJsonSerializer) -> None:
        with patch("src.dbos_workflows.serializer.DBOS_PICKLE_FALLBACK_TOTAL") as mock_counter:
            result = serializer.deserialize("not-json-prefixed-data")
            assert result == "not-json-prefixed-data"
            mock_counter.add.assert_called_once_with(1, {})

    def test_no_counter_on_json_deserialize(self, serializer: SafeJsonSerializer) -> None:
        with patch("src.dbos_workflows.serializer.DBOS_PICKLE_FALLBACK_TOTAL") as mock_counter:
            result = serializer.deserialize(serializer.serialize("hello"))
            assert result == "hello"
            mock_counter.add.assert_not_called()


class TestNestedExceptionSerialization:
    def test_exception_in_dict(self, serializer: SafeJsonSerializer) -> None:
        data = {"error": ValueError("bad"), "status": "failed"}
        result = serializer.deserialize(serializer.serialize(data))
        assert isinstance(result["error"], ValueError)
        assert str(result["error"]) == "bad"
        assert result["status"] == "failed"

    def test_exceptions_in_list(self, serializer: SafeJsonSerializer) -> None:
        data = [ValueError("a"), ValueError("b")]
        result = serializer.deserialize(serializer.serialize(data))
        assert len(result) == 2
        assert all(isinstance(e, ValueError) for e in result)
        assert str(result[0]) == "a"
        assert str(result[1]) == "b"

    def test_deeply_nested_exception(self, serializer: SafeJsonSerializer) -> None:
        data = {"results": [{"error": RuntimeError("deep")}]}
        result = serializer.deserialize(serializer.serialize(data))
        assert isinstance(result["results"][0]["error"], RuntimeError)
        assert str(result["results"][0]["error"]) == "deep"


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
