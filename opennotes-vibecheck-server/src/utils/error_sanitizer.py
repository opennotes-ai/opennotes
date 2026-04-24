"""PII / secret redaction for log messages and error details.

Applied in two places (see `src.monitoring`):

1. As a structlog-style processor (`sanitize_processor`) that walks an event
   dict and scrubs string values before they become a log line.
2. As a Logfire scrubbing callback so pydantic-ai tool traces (in particular
   `get_screenshot()` results that carry Supabase signed URLs) cannot leak
   credentials into the Logfire backend.

`_sanitize` is a pure function — no dependencies beyond `re`. Substitution
order matters: bearer tokens and auth URLs run before generic path patterns,
and signed-URL query-param redaction runs last so it catches query strings
that remain after earlier rules collapse.
"""
from __future__ import annotations

import re
from typing import Any

_REDACTED = "<redacted>"

_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_AUTH_URL_RE = re.compile(r"https?://[^\s]*auth[^\s]*", re.IGNORECASE)
_USER_HOME_RE = re.compile(r"/Users/[^/\s]+/")
_LINUX_HOME_RE = re.compile(r"/home/[^/\s]+/")
_GCP_PROJECT_RE = re.compile(r"google-mpf-[A-Za-z0-9\-]+?\.com", re.IGNORECASE)
# Case-insensitive so capitalized `?Token=` or mixed-case `?x-amz-signature=`
# still redact. `signature` appears before `sign` in the alternation so the
# longer alias wins; `sig` is the shortest alias and matches last.
_SIGNED_QUERY_RE = re.compile(
    r"(?P<prefix>[?&])(?:token|X-Amz-Signature|X-Goog-Signature|signature|sign|sig)=[^&\s]+",
    re.IGNORECASE,
)


def _sanitize(value: str | Exception | Any) -> str:
    """Redact PII/secrets from a string or Exception.

    Accepts anything stringifiable. Returns the redacted string. Never raises
    on malformed input — this runs inside logging paths, where a sanitizer
    exception would mask the original error.
    """
    text = str(value)
    text = _BEARER_RE.sub(_REDACTED, text)
    text = _AUTH_URL_RE.sub(_REDACTED, text)
    text = _USER_HOME_RE.sub(_REDACTED, text)
    text = _LINUX_HOME_RE.sub(_REDACTED, text)
    text = _GCP_PROJECT_RE.sub(_REDACTED, text)
    return _SIGNED_QUERY_RE.sub(lambda m: f"{m.group('prefix')}{_REDACTED}", text)


def sanitize_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog-compatible processor that redacts string values in-place.

    Signature matches the structlog processor protocol
    (`(logger, method_name, event_dict) -> event_dict`). Non-string values are
    left untouched so structured fields (counts, flags, lists) still serialize
    faithfully.
    """
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = _sanitize(value)
    return event_dict


def logfire_scrub_callback(match: Any) -> str | None:
    """Logfire ScrubbingOptions callback.

    Logfire calls this for each span attribute that matches its built-in
    scrubbing patterns. Returning the sanitized string keeps the attribute but
    with secrets stripped; returning `None` tells Logfire to apply its default
    `[Scrubbed due to '...']` placeholder. We always return the sanitized form
    so operators still see enough context to debug.
    """
    raw = match.value
    if isinstance(raw, str):
        return _sanitize(raw)
    return None
