"""SSRF guard for outbound HTTP(S) — centralised scheme / host / IP allowlist.

Used by `POST /api/analyze`, `/api/frame-compat`, `/api/screenshot`, and the
post-Firecrawl redirect-final-URL re-check (see TASK-1473.12). Every outbound
URL built from untrusted input must flow through `validate_public_http_url`.

Rejection categories map to `InvalidURL.reason` so callers can log structured
error codes without string-matching the human message:

    scheme_not_allowed    scheme is not http or https
    missing_host          URL parsed successfully but hostname is empty
    host_blocked          literal hostname matches the blocklist or *.internal / *.local
    private_ip            host is an IP literal in a private/loopback/link-local/
                          reserved/multicast/unspecified range
    resolved_private_ip   hostname resolved (via getaddrinfo) to any such IP
    unresolvable_host     DNS resolution failed (gaierror)

DNS-rebinding (TOCTOU between resolution and socket connect) is explicitly out
of scope — that is Firecrawl's responsibility and is documented in the spec.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

_BLOCKED_HOSTS: frozenset[str] = frozenset(
    {
        "localhost",
        "metadata",
        "metadata.google.internal",
    }
)

_BLOCKED_SUFFIXES: tuple[str, ...] = (".internal", ".local")


class InvalidURL(ValueError):  # noqa: N818 — public integration surface fixed by TASK-1473 spec
    """SSRF / scheme / host violation.

    `reason` is a short machine-readable slug that callers can route on
    (log fields, JSON error responses). The human-readable message defaults to
    the reason slug so plain `str(err)` is still useful in traces.
    """

    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message or reason)
        self.reason = reason


def _resolve(hostname: str) -> list[str]:
    """Thin wrapper around `socket.getaddrinfo` so tests can monkeypatch it.

    Returns the list of IP strings from every `(family, type, proto, canonname,
    sockaddr)` record. The caller iterates and rejects the URL if any record is
    private — chaining a public A with a private AAAA must not slip through.
    """
    infos = socket.getaddrinfo(hostname, None)
    ips: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        addr = sockaddr[0]
        if isinstance(addr, str):
            ips.append(addr)
    return ips


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_http_url(raw: str) -> str:
    """Return `raw` unchanged when it is safe to fetch, else raise `InvalidURL`.

    The returned string is the input as provided — callers can still log the
    exact value the user supplied. Normalisation (lowercasing the scheme/host,
    stripping default ports) is intentionally NOT applied here so this can be
    composed with existing routes that echo the URL back.
    """
    parsed = urlsplit(raw)

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise InvalidURL(reason="scheme_not_allowed")

    hostname = parsed.hostname
    if not hostname:
        raise InvalidURL(reason="missing_host")
    hostname = hostname.lower()

    if hostname in _BLOCKED_HOSTS:
        raise InvalidURL(reason="host_blocked")
    if any(hostname.endswith(suffix) for suffix in _BLOCKED_SUFFIXES):
        raise InvalidURL(reason="host_blocked")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        if _is_disallowed_ip(literal):
            raise InvalidURL(reason="private_ip")
        return raw

    try:
        resolved_ips = _resolve(hostname)
    except socket.gaierror:
        raise InvalidURL(reason="unresolvable_host")

    for ip_str in resolved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _is_disallowed_ip(ip):
            raise InvalidURL(reason="resolved_private_ip")

    return raw


def revalidate_redirect_target(raw: str) -> str:
    """Re-run `validate_public_http_url` on a post-redirect URL.

    Dedicated alias so the orchestrator (TASK-1473.12) can wire the
    post-Firecrawl `metadata.source_url` check through a clearly named call site
    — the behaviour is identical but the name documents intent for reviewers
    and log correlation. Failure must discard the scrape and fail the job with
    `error_code='invalid_url'`, `error_detail='redirect to private host'`.
    """
    return validate_public_http_url(raw)
