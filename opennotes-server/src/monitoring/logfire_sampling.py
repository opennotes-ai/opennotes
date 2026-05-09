"""Logfire tail-sampling policies."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from logfire._internal.constants import LevelName
    from logfire.sampling import TailSamplingSpanInfo

_LEVEL_ORDER = {
    "trace": 10,
    "debug": 20,
    "info": 30,
    "notice": 35,
    "warn": 40,
    "warning": 40,
    "error": 50,
    "fatal": 60,
}


def _level_value(level: Any) -> int:
    return _LEVEL_ORDER.get(str(level).lower(), 0)


def _is_logfire_datastore_span(service_name: str, span: Any) -> bool:
    attrs_raw: Any = getattr(span, "attributes", None)
    attrs: dict[str, Any] = dict(attrs_raw) if attrs_raw else {}
    scope = getattr(getattr(span, "instrumentation_scope", None), "name", "") or ""
    name = getattr(span, "name", "") or ""
    service_name_lower = service_name.lower()
    scope_lower = scope.lower()
    name_lower = name.lower()
    db_system = str(attrs.get("db.system", "")).lower()

    is_common_datastore_span = (
        db_system in {"redis", "postgresql", "postgres", "sqlalchemy"}
        or "redis" in scope_lower
        or "sqlalchemy" in scope_lower
        or "postgres" in scope_lower
    )
    is_dbos_worker_internal_span = service_name_lower == "opennotes-dbos-worker" and (
        "dbos" in scope_lower or "dbos" in name_lower
    )

    return is_common_datastore_span or is_dbos_worker_internal_span


def build_logfire_tail_sampler(
    *,
    service_name: str,
    background_sample_rate: float,
    dbos_datastore_sample_rate: float,
    tail_level_threshold: LevelName | None,
    tail_duration_threshold: float | None,
) -> Callable[[TailSamplingSpanInfo], float]:
    """Build the Logfire tail sampler used by application observability setup."""
    safe_background_rate = min(max(background_sample_rate, 0.0), 1.0)
    safe_datastore_rate = min(max(dbos_datastore_sample_rate, 0.0), 0.01)
    level_threshold = _level_value(tail_level_threshold) if tail_level_threshold else None

    def tail_sampler(info: TailSamplingSpanInfo) -> float:
        if level_threshold is not None and _level_value(info.level) >= level_threshold:
            return 1.0
        if tail_duration_threshold and info.duration >= tail_duration_threshold:
            return 1.0

        span = info.span
        attrs_raw: Any = getattr(span, "attributes", None)
        attrs: dict[str, Any] = dict(attrs_raw) if attrs_raw else {}
        name = getattr(span, "name", "") or ""

        if attrs.get("gen_ai.system") or "anthropic" in name.lower() or "openai" in name.lower():
            return 0.2
        if _is_logfire_datastore_span(service_name, span):
            return safe_datastore_rate

        return safe_background_rate

    return tail_sampler
