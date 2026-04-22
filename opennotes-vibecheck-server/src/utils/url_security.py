"""SSRF guard for outbound HTTP(S) — centralised scheme / host / IP allowlist.

Used by `POST /api/analyze`, `/api/frame-compat`, `/api/screenshot`, and the
post-Firecrawl redirect-final-URL re-check (see TASK-1473.12). Every outbound
URL built from untrusted input must flow through `validate_public_http_url`.

Rejection categories map to `InvalidURL.reason` so callers can log structured
error codes without string-matching the human message:

    scheme_not_allowed    scheme is not http or https
    missing_host          URL parsed successfully but hostname is empty
    invalid_host          hostname is malformed per IDNA (empty label, label
                          longer than 63 chars, etc.) and cannot be safely
                          compared against the blocklist
    host_blocked          literal hostname matches the blocklist or *.internal / *.local
    private_ip            host is an IP literal in a private/loopback/link-local/
                          reserved/multicast/unspecified range
    resolved_private_ip   hostname resolved (via getaddrinfo) to any such IP
    unresolvable_host     DNS resolution failed (gaierror)

The validator also returns a **normalized** URL on success: scheme lowercased,
host IDNA-encoded + lowercased + trailing-dots stripped, fragment dropped,
path and query preserved verbatim. Downstream cache keys and dedupe paths rely
on this normalization — if two representations of the same URL disagree here
(e.g. `HTTP://Example.COM./` vs `http://example.com/`) the SSRF guard would
double-admit them.

DNS-rebinding (TOCTOU between resolution and socket connect) is explicitly out
of scope — that is Firecrawl's responsibility and is documented in the spec.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

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


def _normalize_host(hostname: str) -> str:
    """Collapse a hostname to the form we compare against the blocklist.

    Steps (order matters):

    1. Strip trailing dots. `localhost.` and `localhost` are the same host in
       DNS; without this step `parsed.hostname.endswith('.internal')` doesn't
       match `foo.internal.`, and `== 'localhost'` doesn't match `localhost.`.
    2. IDNA-encode to ASCII. `urlsplit` preserves Unicode labels verbatim, so
       without this a Unicode host that canonicalises to a blocked label can
       slip past the string comparison.
    3. Lowercase. IDNA preserves case; callers may have uppercased `Metadata.
       Google.Internal.` to bypass the existing `.lower()` path.

    Malformed hostnames (empty labels, labels >63 chars, etc.) raise
    `UnicodeError` from the stdlib IDNA codec — surface those as
    `InvalidURL(reason='invalid_host')` rather than letting the exception
    bubble into the caller.
    """
    stripped = hostname.rstrip(".")
    if not stripped:
        raise InvalidURL(reason="invalid_host")
    try:
        encoded = stripped.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidURL(reason="invalid_host") from exc
    return encoded.lower()


def _rebuild_netloc(parsed_netloc: str, normalized_host: str) -> str:
    """Replace the host component in `parsed_netloc` with `normalized_host`.

    `urlsplit.netloc` is the full `userinfo@host:port` string with original
    casing — we want to keep userinfo (an attacker-controlled URL should
    still be echoed back with its exact auth payload so log correlation
    works) and port, but swap the host for the canonicalised form.
    """
    userinfo = ""
    rest = parsed_netloc
    if "@" in rest:
        userinfo, rest = rest.rsplit("@", 1)
        userinfo += "@"
    # IPv6 literal hosts are bracketed in the netloc; port follows the ']'.
    if rest.startswith("["):
        bracket_end = rest.find("]")
        port_suffix = rest[bracket_end + 1 :] if bracket_end != -1 else ""
        return f"{userinfo}[{normalized_host}]{port_suffix}"
    port_suffix = ""
    if ":" in rest:
        _, port_suffix = rest.rsplit(":", 1)
        port_suffix = f":{port_suffix}"
    return f"{userinfo}{normalized_host}{port_suffix}"


def validate_public_http_url(raw: str) -> str:
    """Return a normalized URL when it is safe to fetch, else raise `InvalidURL`.

    The returned string is lowercase on scheme and host, IDNA-encoded on host,
    stripped of any trailing dot on host, and has any `#fragment` dropped.
    Path and query are preserved verbatim so route semantics remain intact.
    Callers that need the *exact* user input should log it separately before
    calling this — the validator intentionally canonicalises for cache-key
    and dedupe correctness.
    """
    parsed = urlsplit(raw)

    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise InvalidURL(reason="scheme_not_allowed")

    hostname = parsed.hostname
    if not hostname:
        raise InvalidURL(reason="missing_host")

    # IP literals must bypass IDNA normalization — `::1`, `fd00::1`, and IPv4
    # dotted-quads are not valid IDNA input and the codec would reject them.
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        if _is_disallowed_ip(literal):
            raise InvalidURL(reason="private_ip")
        normalized_host = hostname
    else:
        normalized_host = _normalize_host(hostname)

        if normalized_host in _BLOCKED_HOSTS:
            raise InvalidURL(reason="host_blocked")
        if any(normalized_host.endswith(suffix) for suffix in _BLOCKED_SUFFIXES):
            raise InvalidURL(reason="host_blocked")

        try:
            resolved_ips = _resolve(normalized_host)
        except socket.gaierror:
            raise InvalidURL(reason="unresolvable_host")

        for ip_str in resolved_ips:
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if _is_disallowed_ip(ip):
                raise InvalidURL(reason="resolved_private_ip")

    netloc = _rebuild_netloc(parsed.netloc, normalized_host)
    return urlunsplit((scheme, netloc, parsed.path, parsed.query, ""))


def revalidate_redirect_target(raw: str) -> str:
    """Re-run `validate_public_http_url` on a post-redirect URL.

    Dedicated alias so the orchestrator (TASK-1473.12) can wire the
    post-Firecrawl `metadata.source_url` check through a clearly named call site
    — the behaviour is identical but the name documents intent for reviewers
    and log correlation. Failure must discard the scrape and fail the job with
    `error_code='invalid_url'`, `error_detail='redirect to private host'`.
    """
    return validate_public_http_url(raw)
