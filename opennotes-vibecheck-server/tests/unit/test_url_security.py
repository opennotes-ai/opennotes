"""Tests for src.utils.url_security — SSRF guard for outbound HTTP(S).

Each test exercises one behavior of `validate_public_http_url`. Inputs and
expected `InvalidURL.reason` values are inline (DAMP) so failures immediately
reveal which category regressed. The suite covers four rejection categories:

1. Scheme not in {http, https}.
2. Host in explicit blocklist (`localhost`, GCE metadata) or suffix-matched
   against `.internal` / `.local`.
3. IP literals in private, loopback, link-local, reserved, multicast, or
   unspecified ranges — including 169.254.169.254 and IPv6 ULA (fd00::/8).
4. Hostnames that resolve (via `socket.getaddrinfo`) to any such IP.

The suite-wide autouse `_stub_dns` in `tests/conftest.py` forces
`socket.getaddrinfo` to return `8.8.8.8` for any hostname. Tests that need to
exercise the DNS-resolution rejection path override that fixture locally via
`monkeypatch.setattr(socket, "getaddrinfo", ...)`.
"""
from __future__ import annotations

import socket

import pytest

from src.utils.url_security import InvalidURL, validate_public_http_url


class TestValidUrls:
    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com",
            "http://example.com/",
            "https://quizlet.com/blog/posts/foo",
            "https://www.example.co.uk/path?q=1",
        ],
    )
    def test_public_http_urls_are_returned(self, url: str) -> None:
        assert validate_public_http_url(url) == url


class TestSchemeRejection:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "gopher://example.com/",
            "ftp://example.com/pub",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
        ],
    )
    def test_non_http_schemes_raise_scheme_not_allowed(self, url: str) -> None:
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url(url)
        assert exc_info.value.reason == "scheme_not_allowed"

    def test_missing_scheme_is_rejected(self) -> None:
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url("example.com/path")
        assert exc_info.value.reason == "scheme_not_allowed"

    def test_missing_hostname_is_rejected(self) -> None:
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url("http:///path")
        assert exc_info.value.reason == "missing_host"


class TestHostBlocklist:
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/",
            "http://localhost:8080/admin",
            "https://metadata.google.internal/computeMetadata/v1/",
            "http://metadata/",
        ],
    )
    def test_explicit_blocklist_hosts_raise_host_blocked(self, url: str) -> None:
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url(url)
        assert exc_info.value.reason == "host_blocked"

    @pytest.mark.parametrize(
        "url",
        [
            "http://foo.internal/",
            "http://svc.prod.internal/health",
            "http://foo.local/",
            "http://printer.local/",
        ],
    )
    def test_internal_and_local_suffixes_raise_host_blocked(self, url: str) -> None:
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url(url)
        assert exc_info.value.reason == "host_blocked"


class TestIpLiteralRejection:
    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/",
            "http://169.254.169.254/computeMetadata/v1/",
            "http://127.0.0.1/",
            "http://127.1.2.3/",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "http://172.16.0.1/",
            "http://0.0.0.0/",
            "http://224.0.0.1/",
        ],
    )
    def test_private_ipv4_literals_raise_private_ip(self, url: str) -> None:
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url(url)
        assert exc_info.value.reason == "private_ip"

    @pytest.mark.parametrize(
        "url",
        [
            "http://[::1]/",
            "http://[fd00::1]/",
            "http://[fe80::1]/",
            "http://[fc00::1]/",
        ],
    )
    def test_private_ipv6_literals_raise_private_ip(self, url: str) -> None:
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url(url)
        assert exc_info.value.reason == "private_ip"


class TestDnsResolutionRejection:
    def test_hostname_resolving_to_private_ipv4_raises_resolved_private_ip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _resolve_to_private(*_args: object, **_kwargs: object) -> list[object]:
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", _resolve_to_private)
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url("http://internal.example.com/")
        assert exc_info.value.reason == "resolved_private_ip"

    def test_hostname_resolving_to_metadata_ip_raises_resolved_private_ip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _resolve_to_metadata(*_args: object, **_kwargs: object) -> list[object]:
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", _resolve_to_metadata)
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url("http://evil.example.com/")
        assert exc_info.value.reason == "resolved_private_ip"

    def test_hostname_resolving_to_ipv6_ula_raises_resolved_private_ip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _resolve_to_ula(*_args: object, **_kwargs: object) -> list[object]:
            return [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("fd00::1", 0, 0, 0))]

        monkeypatch.setattr(socket, "getaddrinfo", _resolve_to_ula)
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url("http://dual-stack.example.com/")
        assert exc_info.value.reason == "resolved_private_ip"

    def test_hostname_with_mixed_records_rejects_if_any_is_private(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Any private record in the result set must block the request — an
        attacker can chain a public A record with a private AAAA record (or
        vice versa) and pick whichever the client's socket picks first.
        """

        def _resolve_mixed(*_args: object, **_kwargs: object) -> list[object]:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", _resolve_mixed)
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url("http://mixed.example.com/")
        assert exc_info.value.reason == "resolved_private_ip"

    def test_unresolvable_hostname_raises_unresolvable_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise_gaierror(*_args: object, **_kwargs: object) -> list[object]:
            raise socket.gaierror("no such host")

        monkeypatch.setattr(socket, "getaddrinfo", _raise_gaierror)
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url("http://does-not-resolve.example.com/")
        assert exc_info.value.reason == "unresolvable_host"


class TestInvalidUrlException:
    def test_reason_attribute_is_set(self) -> None:
        err = InvalidURL(reason="scheme_not_allowed")
        assert err.reason == "scheme_not_allowed"

    def test_default_message_is_the_reason(self) -> None:
        err = InvalidURL(reason="host_blocked")
        assert str(err) == "host_blocked"

    def test_custom_message_overrides_reason_in_str(self) -> None:
        err = InvalidURL(reason="private_ip", message="host is a private IP")
        assert str(err) == "host is a private IP"
        assert err.reason == "private_ip"

    def test_is_a_valueerror(self) -> None:
        assert issubclass(InvalidURL, ValueError)
