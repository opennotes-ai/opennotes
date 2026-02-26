from __future__ import annotations

import pytest

from opennotes_cli.auth import (
    AuthProvider,
    JwtAuthProvider,
    _providers,
    get_auth_provider,
    register_auth_provider,
)


class TestJwtAuthProvider:
    def test_reads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENNOTES_TOKEN", "test-token")
        monkeypatch.setenv("OPENNOTES_SERVER_URL", "https://example.com")
        monkeypatch.setenv("OPENNOTES_API_KEY", "key-123")

        provider = JwtAuthProvider()
        assert provider.token == "test-token"
        assert provider.get_server_url() == "https://example.com"

    def test_explicit_args_override_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENNOTES_TOKEN", "env-token")
        provider = JwtAuthProvider(token="explicit-token", server_url="http://local:8000")
        assert provider.token == "explicit-token"
        assert provider.get_server_url() == "http://local:8000"

    def test_get_headers_with_token(self) -> None:
        provider = JwtAuthProvider(token="my-token")
        headers = provider.get_headers()
        assert headers["Authorization"] == "Bearer my-token"
        assert headers["Content-Type"] == "application/json"

    def test_get_headers_with_api_key(self) -> None:
        provider = JwtAuthProvider(api_key="key-456")
        headers = provider.get_headers()
        assert headers["X-API-Key"] == "key-456"

    def test_get_headers_empty_when_no_creds(self) -> None:
        provider = JwtAuthProvider(token="", api_key="")
        headers = provider.get_headers()
        assert "Authorization" not in headers
        assert "X-API-Key" not in headers

    def test_get_jsonapi_headers(self) -> None:
        provider = JwtAuthProvider(token="tok", api_key="key")
        headers = provider.get_jsonapi_headers()
        assert headers["Content-Type"] == "application/vnd.api+json"
        assert headers["Accept"] == "application/vnd.api+json"
        assert headers["Authorization"] == "Bearer tok"
        assert headers["X-API-Key"] == "key"

    def test_default_server_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENNOTES_SERVER_URL", raising=False)
        provider = JwtAuthProvider()
        assert provider.get_server_url() == "http://localhost:8000"

    def test_satisfies_protocol(self) -> None:
        provider = JwtAuthProvider(token="t")
        assert isinstance(provider, AuthProvider)


class TestGetAuthProvider:
    def test_default_is_jwt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENNOTES_AUTH_TYPE", raising=False)
        provider = get_auth_provider()
        assert isinstance(provider, JwtAuthProvider)

    def test_env_var_selects_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENNOTES_AUTH_TYPE", "jwt")
        provider = get_auth_provider()
        assert isinstance(provider, JwtAuthProvider)

    def test_explicit_auth_type(self) -> None:
        provider = get_auth_provider(auth_type="jwt")
        assert isinstance(provider, JwtAuthProvider)

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown auth type"):
            get_auth_provider(auth_type="nonexistent")


class TestRegisterAuthProvider:
    def test_register_and_use_custom_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class CustomAuth:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def get_headers(self) -> dict[str, str]:
                return {"X-Custom": "yes"}

            def get_jsonapi_headers(self) -> dict[str, str]:
                return {"X-Custom": "yes"}

            def get_server_url(self) -> str:
                return "http://custom:9000"

        monkeypatch.setitem(_providers, "custom", CustomAuth)
        provider = get_auth_provider(auth_type="custom")
        assert provider.get_server_url() == "http://custom:9000"
        assert provider.get_headers()["X-Custom"] == "yes"
