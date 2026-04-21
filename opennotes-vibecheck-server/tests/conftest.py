"""Shared pytest fixtures.

- Autouse `_stub_dns`: return a public-looking IP (8.8.8.8) for any hostname lookup
  so tests using fake hostnames like `blocked.example.com` survive the SSRF
  validator added to `src.routes.frame`. Production still does real DNS; the
  stub lives only in the test process.
"""
from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_getaddrinfo(
        host: str,
        port: object,
        family: int = 0,
        type: int = 0,  # noqa: A002
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        # Return a public IP regardless of hostname. Tests that need to exercise
        # the block-list path should call `src.routes.frame._validate_http_url`
        # directly with a hostname in `_BLOCKED_HOSTNAMES` or stub this fixture.
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
