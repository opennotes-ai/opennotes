from __future__ import annotations

import os
from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class AuthProvider(Protocol):
    def get_headers(self) -> dict[str, str]: ...
    def get_jsonapi_headers(self) -> dict[str, str]: ...
    def get_server_url(self) -> str: ...


class JwtAuthProvider:
    def __init__(
        self,
        token: str | None = None,
        server_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.token = token or os.environ.get("OPENNOTES_TOKEN", "")
        self.server_url = server_url or os.environ.get(
            "OPENNOTES_SERVER_URL", "http://localhost:8000"
        )
        self.api_key = api_key or os.environ.get("OPENNOTES_API_KEY", "")

    def get_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def get_jsonapi_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def get_server_url(self) -> str:
        return self.server_url


AuthProviderFactory = type[AuthProvider] | Callable[..., AuthProvider]
_providers: dict[str, AuthProviderFactory] = {}


def register_auth_provider(name: str, factory: AuthProviderFactory) -> None:
    _providers[name] = factory


def get_auth_provider(auth_type: str | None = None, **kwargs) -> AuthProvider:
    auth_type = auth_type or os.environ.get("OPENNOTES_AUTH_TYPE", "jwt")
    if auth_type == "jwt":
        return JwtAuthProvider(**kwargs)
    if auth_type in _providers:
        factory = _providers[auth_type]
        return factory(**kwargs)
    available = ["jwt"] + list(_providers.keys())
    raise ValueError(
        f"Unknown auth type: {auth_type}. Available: {', '.join(available)}"
    )
