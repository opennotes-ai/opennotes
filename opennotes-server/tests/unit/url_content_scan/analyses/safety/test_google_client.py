from __future__ import annotations

import pytest

from src.url_content_scan.analyses.safety import google_client

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class _FakeCreds:
    def __init__(self) -> None:
        self.valid = False
        self.token: str | None = None
        self.refresh_calls = 0

    def refresh(self, _request: object) -> None:
        self.refresh_calls += 1
        self.valid = True
        self.token = f"token-{self.refresh_calls}"


@pytest.fixture(autouse=True)
def _reset_credential_cache() -> None:
    google_client.reset_cached_credentials_for_tests()


async def test_get_access_token_reuses_cached_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    creds = _FakeCreds()
    default_calls: list[list[str]] = []

    def fake_default(*, scopes: list[str]) -> tuple[_FakeCreds, str]:
        default_calls.append(scopes)
        return creds, "project-id"

    monkeypatch.setattr("google.auth.default", fake_default)
    monkeypatch.setattr("google.auth.transport.requests.Request", lambda: object())

    token_one = await google_client.get_access_token()
    token_two = await google_client.get_access_token()

    assert token_one == "token-1"
    assert token_two == "token-1"
    assert default_calls == [[google_client.CLOUD_PLATFORM_SCOPE]]
    assert creds.refresh_calls == 1


async def test_get_access_token_returns_none_when_refresh_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenCreds(_FakeCreds):
        def refresh(self, _request: object) -> None:
            raise RuntimeError("bad adc")

    monkeypatch.setattr(
        "google.auth.default",
        lambda *, scopes: (_BrokenCreds(), "project-id"),
    )
    monkeypatch.setattr("google.auth.transport.requests.Request", lambda: object())

    token = await google_client.get_access_token()

    assert token is None
