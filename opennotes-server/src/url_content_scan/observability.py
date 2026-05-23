from __future__ import annotations

import random
import re
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic_ai.capabilities import Instrumentation
    from pydantic_ai.models.instrumented import InstrumentationSettings

    from src.config import Settings

PYDANTIC_AI_INSTRUMENTATION_VERSION: int = 2

URL_SCAN_LOGFIRE_BUILTIN_SCRUB_PATTERNS: tuple[str, ...] = (
    r"token=",
    r"X-Amz-Signature",
    r"X-Goog-Signature",
    r"signature",
    r"sign=",
    r"sig=",
    r"bearer",
)

_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_TOKEN_QUERY_RE = re.compile(r"(token=)[^&\s]+", re.IGNORECASE)
_AMZ_SIG_RE = re.compile(r"(X-Amz-Signature=)[^&\s]+", re.IGNORECASE)
_GOOG_SIG_RE = re.compile(r"(X-Goog-Signature=)[^&\s]+", re.IGNORECASE)
_GENERIC_SIG_RE = re.compile(r"((?:signature|sign|sig)=)[^&\s]+", re.IGNORECASE)

_REDACTED = "[REDACTED]"

_instrument_pydantic_ai_lock = threading.Lock()
_instrument_pydantic_ai_state = [False]


def _sanitize_value(value: str) -> str:
    value = _BEARER_RE.sub(f"Bearer {_REDACTED}", value)
    value = _TOKEN_QUERY_RE.sub(rf"\g<1>{_REDACTED}", value)
    value = _AMZ_SIG_RE.sub(rf"\g<1>{_REDACTED}", value)
    value = _GOOG_SIG_RE.sub(rf"\g<1>{_REDACTED}", value)
    return _GENERIC_SIG_RE.sub(rf"\g<1>{_REDACTED}", value)


def _url_scan_scrub_callback(match: Any) -> str | None:
    value = match.value
    if isinstance(value, str):
        sanitized = _sanitize_value(value)
        if sanitized != value:
            return sanitized
    return None


def _make_instrumentation_settings(include_content: bool) -> InstrumentationSettings:
    from pydantic_ai.models.instrumented import InstrumentationSettings  # noqa: PLC0415

    return InstrumentationSettings(
        include_content=include_content,
        include_binary_content=False,
        version=PYDANTIC_AI_INSTRUMENTATION_VERSION,
    )


def url_scan_instrumentation(settings: Settings | None = None) -> Instrumentation:
    from pydantic_ai.capabilities import Instrumentation as Cap  # noqa: PLC0415

    include_content: bool = False
    if settings is not None:
        include_content = bool(getattr(settings, "URL_SCAN_LOGFIRE_CONTENT", False))
    return Cap(_make_instrumentation_settings(include_content))


def url_scan_extractor_instrumentation(settings: Settings) -> InstrumentationSettings:
    rate: float = float(getattr(settings, "URL_SCAN_EXTRACTOR_SAMPLE_RATE", 0.05))
    rate = max(0.0, min(1.0, rate))
    if rate <= 0.0:
        include_content = False
    elif rate >= 1.0:
        include_content = True
    else:
        include_content = random.random() < rate
    return _make_instrumentation_settings(include_content)


def augment_logfire(
    *,
    extra_patterns: list[str] | None = None,
    enable_content: bool = False,
) -> None:
    try:
        import logfire  # noqa: PLC0415

        all_patterns = list(URL_SCAN_LOGFIRE_BUILTIN_SCRUB_PATTERNS)
        if extra_patterns:
            all_patterns.extend(extra_patterns)

        if enable_content:
            logfire.configure(
                scrubbing=logfire.ScrubbingOptions(
                    extra_patterns=all_patterns,
                    callback=_url_scan_scrub_callback,
                ),
            )

        with _instrument_pydantic_ai_lock:
            if not _instrument_pydantic_ai_state[0]:
                logfire.instrument_pydantic_ai(
                    include_content=False,
                    include_binary_content=False,
                )
                _instrument_pydantic_ai_state[0] = True
    except Exception:
        pass


__all__ = [
    "PYDANTIC_AI_INSTRUMENTATION_VERSION",
    "URL_SCAN_LOGFIRE_BUILTIN_SCRUB_PATTERNS",
    "augment_logfire",
    "url_scan_extractor_instrumentation",
    "url_scan_instrumentation",
]
