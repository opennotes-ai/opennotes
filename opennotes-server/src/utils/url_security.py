"""SSRF guard for outbound HTTP(S)."""

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


class InvalidURL(ValueError):  # noqa: N818
    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message or reason)
        self.reason = reason


def _resolve(hostname: str) -> list[str]:
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
    stripped = hostname.rstrip(".")
    if not stripped:
        raise InvalidURL(reason="invalid_host")
    try:
        encoded = stripped.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidURL(reason="invalid_host") from exc
    return encoded.lower()


def _rebuild_netloc(parsed_netloc: str, normalized_host: str) -> str:
    userinfo = ""
    rest = parsed_netloc
    if "@" in rest:
        userinfo, rest = rest.rsplit("@", 1)
        userinfo += "@"
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
    parsed = urlsplit(raw)

    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise InvalidURL(reason="scheme_not_allowed")

    hostname = parsed.hostname
    if not hostname:
        raise InvalidURL(reason="missing_host")

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
    return validate_public_http_url(raw)
