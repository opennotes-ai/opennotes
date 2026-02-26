from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from collections.abc import Callable
from pathlib import Path
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


def _try_load_provider_module(auth_type: str) -> None:
    module_path = os.environ.get("OPENNOTES_AUTH_MODULE")
    if module_path:
        if "/" in module_path or module_path.endswith(".py"):
            path = Path(module_path).resolve()
            spec = importlib.util.spec_from_file_location(path.stem, path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[path.stem] = mod
                spec.loader.exec_module(mod)
                return
        else:
            importlib.import_module(module_path)
            return
    for candidate in [f"opennotes_auth_{auth_type}", f"scripts.opennotes_auth_{auth_type}"]:
        try:
            importlib.import_module(candidate)
            return
        except ImportError:
            continue


def get_auth_provider(auth_type: str | None = None, **kwargs) -> AuthProvider:
    auth_type = auth_type or os.environ.get("OPENNOTES_AUTH_TYPE", "jwt")
    if auth_type == "jwt":
        return JwtAuthProvider(**kwargs)
    if auth_type not in _providers:
        _try_load_provider_module(auth_type)
    if auth_type in _providers:
        factory = _providers[auth_type]
        return factory(**kwargs)
    available = ["jwt"] + list(_providers.keys())
    raise ValueError(
        f"Unknown auth type: {auth_type}. Available: {', '.join(available)}"
    )
