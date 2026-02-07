"""Custom JSON serializer for DBOS workflows.

Replaces pickle with JSON to avoid CPython #125756 memo deserialization bugs
on large payloads. Non-JSON data is returned as a raw string.
"""

import importlib
import json
import logging
from typing import Any

from dbos._serialization import Serializer
from prometheus_client import Counter

logger = logging.getLogger(__name__)

DBOS_PICKLE_FALLBACK_TOTAL = Counter(
    "dbos_pickle_fallback_total",
    "Number of times DBOS deserialization fell back to pickle from JSON",
)

_SAFE_EXCEPTION_MODULES = frozenset(
    {
        "builtins",
    }
)


class SafeJsonSerializer(Serializer):
    """JSON-based serializer for DBOS workflow data.

    New data is always serialized as JSON (prefixed with 'json:').
    Exceptions are serialized as structured dicts and reconstructed on read.
    Only exceptions from allowlisted modules are reconstructed.
    """

    JSON_PREFIX = "json:"

    def _json_default(self, obj: Any) -> Any:
        raise TypeError(
            f"Object of type {type(obj).__name__} is not JSON serializable. "
            f"Convert to a JSON-compatible type before passing to DBOS."
        )

    def serialize(self, data: Any) -> str:
        json_data = self._to_json_safe(data)
        return self.JSON_PREFIX + json.dumps(json_data, default=self._json_default)

    def deserialize(self, data: str) -> Any:
        if data.startswith(self.JSON_PREFIX):
            json_str = data[len(self.JSON_PREFIX) :]
            raw = json.loads(json_str)
            return self._from_json_safe(raw)
        DBOS_PICKLE_FALLBACK_TOTAL.inc()
        logger.warning("Non-JSON data encountered in DBOS deserialization, returning as raw string")
        return data

    def _to_json_safe(self, obj: Any) -> Any:
        if isinstance(obj, BaseException):
            return {
                "__dbos_exception__": True,
                "type": type(obj).__name__,
                "module": type(obj).__module__,
                "args": [str(a) for a in obj.args],
            }
        if isinstance(obj, dict):
            return {k: self._to_json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._to_json_safe(item) for item in obj]
        return obj

    def _from_json_safe(self, data: Any) -> Any:
        if isinstance(data, dict) and data.get("__dbos_exception__"):
            exc_type_name = data["type"]
            exc_module = data.get("module", "builtins")
            exc_args = data.get("args", [])
            if exc_module not in _SAFE_EXCEPTION_MODULES:
                logger.warning(
                    "Blocked import of module %s during exception deserialization",
                    exc_module,
                )
                return RuntimeError(f"{exc_type_name}: {', '.join(exc_args)}")
            try:
                mod = importlib.import_module(exc_module)
                exc_class = getattr(mod, exc_type_name)
                if issubclass(exc_class, BaseException):
                    return exc_class(*exc_args)
            except (ImportError, AttributeError, TypeError):
                pass
            return RuntimeError(f"{exc_type_name}: {', '.join(exc_args)}")
        if isinstance(data, dict):
            return {k: self._from_json_safe(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._from_json_safe(item) for item in data]
        return data
