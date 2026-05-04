from __future__ import annotations

import socket

import pytest

from src.url_content_scan.normalize import canonical_cache_key, normalize_url
from src.utils.url_security import InvalidURL, revalidate_redirect_target, validate_public_http_url


def _addrinfo_ipv4(ip: str) -> list[object]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]


def _addrinfo_ipv6(ip: str) -> list[object]:
    return [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", (ip, 0, 0, 0))]


@pytest.fixture(autouse=True)
def stub_dns_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    def _resolve_public(*_args: object, **_kwargs: object) -> list[object]:
        return _addrinfo_ipv4("8.8.8.8")

    monkeypatch.setattr(socket, "getaddrinfo", _resolve_public)


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


class TestNormalizedReturn:
    def test_mixed_case_scheme_and_host_are_lowercased(self) -> None:
        assert (
            validate_public_http_url("HTTPS://Example.COM/path?a=1")
            == "https://example.com/path?a=1"
        )

    def test_fragment_is_dropped(self) -> None:
        assert (
            validate_public_http_url("https://example.com/path#frag") == "https://example.com/path"
        )

    def test_trailing_dot_is_stripped_from_host(self) -> None:
        assert (
            validate_public_http_url("https://example.com./path?q=1")
            == "https://example.com/path?q=1"
        )

    def test_userinfo_and_port_are_preserved(self) -> None:
        assert (
            validate_public_http_url("HTTPS://User:Pw@Example.COM:8443/x")
            == "https://User:Pw@example.com:8443/x"
        )


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
            "http://foo.internal/",
            "http://foo.local/",
            "http://localhost./",
            "http://metadata.google.internal../",
        ],
    )
    def test_blocked_hosts_raise_host_blocked(self, url: str) -> None:
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url(url)
        assert exc_info.value.reason == "host_blocked"

    def test_unicode_internal_suffix_rejected_after_idna(self) -> None:
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url("http://вucher.internal/")
        assert exc_info.value.reason == "host_blocked"

    def test_malformed_idna_long_label_rejected_with_invalid_host(self) -> None:
        bad_label = "a" * 64
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url(f"http://{bad_label}.example.com/")
        assert exc_info.value.reason == "invalid_host"


class TestIpLiteralRejection:
    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/",
            "http://127.0.0.1/",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "http://172.16.0.1/",
            "http://0.0.0.0/",
            "http://224.0.0.1/",
            "http://[::1]/",
            "http://[fd00::1]/",
            "http://[fe80::1]/",
            "http://[fc00::1]/",
        ],
    )
    def test_private_literals_raise_private_ip(self, url: str) -> None:
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url(url)
        assert exc_info.value.reason == "private_ip"


class TestDnsResolutionRejection:
    def test_hostname_resolving_to_private_ipv4_raises_resolved_private_ip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            socket, "getaddrinfo", lambda *_args, **_kwargs: _addrinfo_ipv4("10.0.0.5")
        )
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url("http://internal.example.com/")
        assert exc_info.value.reason == "resolved_private_ip"

    def test_hostname_resolving_to_metadata_ip_raises_resolved_private_ip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            socket, "getaddrinfo", lambda *_args, **_kwargs: _addrinfo_ipv4("169.254.169.254")
        )
        with pytest.raises(InvalidURL) as exc_info:
            revalidate_redirect_target("http://evil.example.com/")
        assert exc_info.value.reason == "resolved_private_ip"

    def test_hostname_resolving_to_ipv6_ula_raises_resolved_private_ip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            socket, "getaddrinfo", lambda *_args, **_kwargs: _addrinfo_ipv6("fd00::1")
        )
        with pytest.raises(InvalidURL) as exc_info:
            validate_public_http_url("http://dual-stack.example.com/")
        assert exc_info.value.reason == "resolved_private_ip"

    @pytest.mark.parametrize(
        "answers",
        [
            [_addrinfo_ipv4("8.8.8.8"), _addrinfo_ipv4("10.0.0.5")],
            [_addrinfo_ipv6("2606:4700:4700::1111"), _addrinfo_ipv6("fd00::1")],
            [_addrinfo_ipv4("8.8.8.8"), _addrinfo_ipv6("fd00::1")],
        ],
    )
    def test_hostname_with_mixed_public_and_private_records_rejects(
        self,
        monkeypatch: pytest.MonkeyPatch,
        answers: list[list[object]],
    ) -> None:
        def _resolve_mixed(*_args: object, **_kwargs: object) -> list[object]:
            return [record for group in answers for record in group]

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


class TestNormalizeUrl:
    def test_normalize_url_strips_tracking_params(self) -> None:
        assert (
            normalize_url(
                "https://example.com/path/?utm_source=x&utm_medium=y&fbclid=a&gclid=b&mc_eid=c&ok=1"
            )
            == "https://example.com/path?ok=1"
        )

    def test_normalize_url_strips_one_trailing_slash(self) -> None:
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_canonical_cache_key_validates_then_normalizes(self) -> None:
        assert (
            canonical_cache_key("HTTPS://Example.COM/path/?utm_source=x&ok=1")
            == "https://example.com/path?ok=1"
        )


class TestInvalidUrlException:
    def test_reason_attribute_is_set(self) -> None:
        err = InvalidURL(reason="scheme_not_allowed")
        assert err.reason == "scheme_not_allowed"
