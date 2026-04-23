"""Logging setup with PII redaction.

The vibecheck server uses stdlib `logging` (not structlog). To keep the
sanitizer API uniform across services, `sanitize_processor` still exposes the
structlog `(logger, method_name, event_dict)` signature — here we also
install a stdlib `logging.Filter` that runs the same `_sanitize` function on
every record's final message.

Async pipeline observability (TASK-1473.15) is layered on top via
`contextvars.ContextVar` + a `logging.Filter` (`_ContextFilter`) that copies
the current `job_id`, `attempt_id`, and `slug` onto every `LogRecord`. The
formatter then renders them as bracketed prefixes so Cloud Logging can pivot
on any of the three. `bind_contextvars` / `clear_contextvars` are the
caller-side helpers (used by `src.jobs.orchestrator`).

Logfire redaction is configured lazily on first call to `configure_logfire()`
so that unit tests and local runs that skip Logfire don't pay the cost. We
register a `ScrubbingOptions` callback because upstream Logfire does not ship
a `RedactProcessor` class — the callback achieves the same effect (every span
attribute flows through `_sanitize` before export).
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar, Token
from typing import Any

from src.utils.error_sanitizer import _sanitize, sanitize_processor

__all__ = [
    "bind_contextvars",
    "clear_contextvars",
    "configure_logfire",
    "get_logger",
    "sanitize_processor",
]

_LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "[job_id=%(job_id)s attempt_id=%(attempt_id)s slug=%(slug)s] %(message)s"
)
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


_job_id_var: ContextVar[str] = ContextVar("vibecheck_job_id", default="-")
_attempt_id_var: ContextVar[str] = ContextVar("vibecheck_attempt_id", default="-")
_slug_var: ContextVar[str] = ContextVar("vibecheck_slug", default="-")


def bind_contextvars(
    *,
    job_id: Any = None,
    attempt_id: Any = None,
    slug: Any = None,
) -> dict[str, Token[str]]:
    """Bind any subset of `job_id`, `attempt_id`, `slug` to the current context.

    Returns a dict of reset tokens the caller MUST hand to
    `clear_contextvars` in a `finally` block — otherwise the bindings leak
    to the next coroutine that runs on this event loop slot.

    Values are coerced via `str(...)` so UUID/Enum inputs serialize cleanly.
    Passing `None` skips that variable (so partial bindings — e.g., only
    `slug` from `_run_section` — don't clobber an outer `job_id`).
    """
    tokens: dict[str, Token[str]] = {}
    if job_id is not None:
        tokens["job_id"] = _job_id_var.set(str(job_id))
    if attempt_id is not None:
        tokens["attempt_id"] = _attempt_id_var.set(str(attempt_id))
    if slug is not None:
        slug_value = slug.value if hasattr(slug, "value") else slug
        tokens["slug"] = _slug_var.set(str(slug_value))
    return tokens


def clear_contextvars(tokens: dict[str, Token[str]]) -> None:
    """Reset any tokens previously returned by `bind_contextvars`."""
    if "job_id" in tokens:
        _job_id_var.reset(tokens["job_id"])
    if "attempt_id" in tokens:
        _attempt_id_var.reset(tokens["attempt_id"])
    if "slug" in tokens:
        _slug_var.reset(tokens["slug"])


class _ContextFilter(logging.Filter):
    """Inject `job_id`, `attempt_id`, `slug` from contextvars onto each record.

    Runs before `_SanitizeFilter` so the formatter's `%(job_id)s` placeholders
    always resolve — without this, `logging.Formatter` raises KeyError on
    records emitted outside an active orchestration context.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.job_id = _job_id_var.get()
        record.attempt_id = _attempt_id_var.get()
        record.slug = _slug_var.get()
        return True


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
    """Install a single default stdout handler with PII scrubbing.

    Idempotent via a sentinel attribute on the handler (`_vibecheck_default`).
    We stamp the sentinel via `setattr` + read via `getattr` rather than
    dotted access so basedpyright doesn't reject the dynamic attribute on
    the stdlib `StreamHandler` typed surface.
    """
    root = logging.getLogger()
    if any(getattr(h, "_vibecheck_default", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(_ContextFilter())
    handler.addFilter(_SanitizeFilter())
    setattr(handler, "_vibecheck_default", True)  # noqa: B010
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
#
# Must stay in sync with `_SIGNED_QUERY_RE` in `src.utils.error_sanitizer`:
# any alias the sanitizer rewrites must also trigger the Logfire callback,
# otherwise an attribute whose value matches the sanitizer regex still ships
# unredacted because Logfire never surfaces it to us. `sig=` is the shortest
# alias (used by Firecrawl and some Supabase variants) and was missed in
# the initial list — codex W3 P1-6.
_LOGFIRE_EXTRA_PATTERNS: tuple[str, ...] = (
    r"token",
    r"X-Amz-Signature",
    r"X-Goog-Signature",
    r"signature",
    r"sign=",
    r"sig=",
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
    configure_kwargs.setdefault("send_to_logfire", "if-token-present")
    logfire.configure(scrubbing=scrubbing, **configure_kwargs)
    _logfire_configured = True
