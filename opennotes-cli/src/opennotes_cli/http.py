from __future__ import annotations

import sys
from typing import Any

import httpx
from rich.console import Console

from opennotes_cli.auth import AuthProvider

error_console = Console(stderr=True)

ENV_URLS: dict[str, str] = {
    "local": "http://localhost:8000",
    "staging": "https://opennotes-server-staging-bydmv6fnwq-uc.a.run.app",
    "production": "https://opennotes-server-bydmv6fnwq-uc.a.run.app",
}


def get_csrf_token(
    client: httpx.Client,
    base_url: str,
    auth: AuthProvider,
) -> str | None:
    headers: dict[str, str] = {}
    h = auth.get_headers()
    if "Authorization" in h:
        headers["Authorization"] = h["Authorization"]

    response = client.get(f"{base_url}/api/v2/scoring/health", headers=headers)

    if response.status_code == 403:
        error_console.print("[red]Error:[/red] Authentication failed (403)")
        sys.exit(1)

    if response.status_code != 200:
        error_console.print(
            f"[red]Error:[/red] Health check failed with status {response.status_code}"
        )
        sys.exit(1)

    return client.cookies.get("csrf_token")


def add_csrf(headers: dict[str, str], csrf_token: str | None) -> dict[str, str]:
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token
    return headers


def handle_error_response(
    response: httpx.Response,
    *,
    custom_handlers: dict[int, str] | None = None,
) -> None:
    custom_handlers = custom_handlers or {}

    if response.status_code < 400:
        return

    if response.status_code in custom_handlers:
        error_console.print(f"[red]Error:[/red] {custom_handlers[response.status_code]}")
        sys.exit(1)

    if response.status_code == 401:
        error_console.print("[red]Error:[/red] Authentication required.")
        sys.exit(1)

    if response.status_code == 403:
        error_console.print("[red]Error:[/red] Access denied.")
        sys.exit(1)

    error_console.print(
        f"[red]Error:[/red] Request failed with status {response.status_code}"
    )
    error_console.print(f"[dim]{response.text[:500]}[/dim]")
    sys.exit(1)
