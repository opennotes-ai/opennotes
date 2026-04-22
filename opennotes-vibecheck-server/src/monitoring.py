"""Logging setup with PII redaction.

The vibecheck server uses stdlib `logging` (not structlog). To keep the
sanitizer API uniform across services, `sanitize_processor` still exposes the
structlog `(logger, method_name, event_dict)` signature — here we also
install a stdlib `logging.Filter` that runs the same `_sanitize` function on
every record's final message.

Logfire redaction is configured lazily on first call to `configure_logfire()`
so that unit tests and local runs that skip Logfire don't pay the cost. We
register a `ScrubbingOptions` callback because upstream Logfire does not ship
a `RedactProcessor` class — the callback achieves the same effect (every span
attribute flows through `_sanitize` before export).
"""
from __future__ import annotations

import logging
import sys
from typing import Any

from src.utils.error_sanitizer import _sanitize, sanitize_processor

__all__ = ["get_logger", "sanitize_processor", "configure_logfire"]

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


class _SanitizeFilter(logging.Filter):
    """Redact PII from every log record's formatted message.

    Runs late (as a filter on the root handler) so substitutions of
    `%s`/`%d` args have already happened and the final message — which is
    what hits stdout/Cloud Logging — is what we scrub.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        record.msg = _sanitize(message)
        record.args = ()
        return True


def _ensure_root_configured() -> None:
    root = logging.getLogger()
    if any(getattr(h, "_vibecheck_default", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(_SanitizeFilter())
    handler._vibecheck_default = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    if root.level == logging.WARNING:
        root.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    _ensure_root_configured()
    return logging.getLogger(name)


_logfire_configured = False

# Supabase signed URLs and upstream signed-URL formats carry these
# query-param and header substrings. Logfire's built-in scrubber matches
# on pydantic/OTel attribute names but does NOT scan attribute *values*
# for these tokens — we add them as `extra_patterns` so the scrubber
# surfaces matching span attributes to our callback, which then runs
# `_sanitize` to strip the credential while preserving surrounding
# debugging context.
_LOGFIRE_EXTRA_PATTERNS: tuple[str, ...] = (
    r"token",
    r"X-Amz-Signature",
    r"X-Goog-Signature",
    r"signature",
    r"sign=",
    r"bearer",
)


def configure_logfire(**configure_kwargs: Any) -> None:
    """Configure Logfire with `_sanitize`-based span attribute scrubbing.

    Idempotent: safe to call from multiple workers or tests. `configure_kwargs`
    are forwarded to `logfire.configure()` so callers can still pass
    `send_to_logfire`, `token`, service metadata, etc.

    We pass a `ScrubbingOptions(callback=..., extra_patterns=...)`. Logfire's
    built-in patterns miss signed-URL keys like `X-Amz-Signature`, so
    `extra_patterns` widens the trigger set; the callback then rewrites
    each matching value through `_sanitize` to preserve debugging context
    without leaking the credential.
    """
    global _logfire_configured
    if _logfire_configured:
        return
    try:
        import logfire
        from src.utils.error_sanitizer import logfire_scrub_callback
    except Exception as exc:
        logging.getLogger(__name__).warning("logfire unavailable, skipping configure: %s", exc)
        return

    scrubbing = logfire.ScrubbingOptions(
        callback=logfire_scrub_callback,
        extra_patterns=list(_LOGFIRE_EXTRA_PATTERNS),
    )
    logfire.configure(scrubbing=scrubbing, **configure_kwargs)
    _logfire_configured = True
