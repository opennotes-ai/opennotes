"""Custom JSON serializer for DBOS workflows.

Replaces pickle with JSON to avoid CPython #125756 memo deserialization bugs
on large payloads. Falls back to pickle for reading old workflow data during
the transition period.
"""

import base64
import importlib
import json
import pickle
from typing import Any

from dbos._serialization import Serializer
from prometheus_client import Counter

DBOS_PICKLE_FALLBACK_TOTAL = Counter(
    "dbos_pickle_fallback_total",
    "Number of times DBOS deserialization fell back to pickle from JSON",
)


class SafeJsonSerializer(Serializer):
    """JSON-based serializer with pickle fallback for reading old data.

    New data is always serialized as JSON (prefixed with 'json:').
    Old pickle data (base64-encoded) can still be read during the transition.
    Exceptions are serialized as structured dicts and reconstructed on read.
    """

    JSON_PREFIX = "json:"

    def serialize(self, data: Any) -> str:
        json_data = self._to_json_safe(data)
        return self.JSON_PREFIX + json.dumps(json_data, default=str)

    def deserialize(self, data: str) -> Any:
        if data.startswith(self.JSON_PREFIX):
            json_str = data[len(self.JSON_PREFIX) :]
            raw = json.loads(json_str)
            return self._from_json_safe(raw)
        DBOS_PICKLE_FALLBACK_TOTAL.inc()
        try:
            return pickle.loads(base64.b64decode(data))
        except Exception:
            return data

    def _to_json_safe(self, obj: Any) -> Any:
        if isinstance(obj, BaseException):
            return {
                "__dbos_exception__": True,
                "type": type(obj).__name__,
                "module": type(obj).__module__,
                "args": [str(a) for a in obj.args],
            }
        return obj

    def _from_json_safe(self, data: Any) -> Any:
        if isinstance(data, dict) and data.get("__dbos_exception__"):
            exc_type_name = data["type"]
            exc_module = data.get("module", "builtins")
            exc_args = data.get("args", [])
            try:
                mod = importlib.import_module(exc_module)
                exc_class = getattr(mod, exc_type_name)
                if issubclass(exc_class, BaseException):
                    return exc_class(*exc_args)
            except (ImportError, AttributeError, TypeError):
                pass
            return RuntimeError(f"{exc_type_name}: {', '.join(exc_args)}")
        return data
