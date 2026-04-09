from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.users.models import APIKey


def _make_api_key(scopes: list[str] | None) -> APIKey:
    return APIKey(
        user_id=uuid4(),
        name="test-key",
        key_hash="fake-hash-value",
        scopes=scopes,
    )


def _make_request(
    headers: dict[str, str] | None = None,
    api_key: APIKey | None = None,
) -> MagicMock:
    request = MagicMock()
    request.headers = headers or {}
    state = MagicMock(spec=[])
    if api_key is not None:
        state.api_key = api_key
    request.state = state
    return request


@pytest.mark.unit
class TestPlatformIdentityDataclass:
    def test_basic_construction(self) -> None:
        from src.auth.platform_claims import PlatformIdentity

        identity = PlatformIdentity(
            platform="discourse",
            scope="forum.example.com",
            sub="42",
            community_id="forum.example.com",
            can_administer_community=True,
        )
        assert identity.platform == "discourse"
        assert identity.scope == "forum.example.com"
        assert identity.sub == "42"
        assert identity.community_id == "forum.example.com"
        assert identity.can_administer_community is True
        assert identity.extra_claims == {}

    def test_extra_claims(self) -> None:
        from src.auth.platform_claims import PlatformIdentity

        identity = PlatformIdentity(
            platform="discourse",
            scope="forum.example.com",
            sub="42",
            community_id="forum.example.com",
            can_administer_community=False,
            extra_claims={"username": "alice", "trust_level": "2"},
        )
        assert identity.extra_claims["username"] == "alice"
        assert identity.extra_claims["trust_level"] == "2"

    def test_defaults(self) -> None:
        from src.auth.platform_claims import PlatformIdentity

        identity = PlatformIdentity(
            platform="discourse",
            scope="forum.example.com",
            sub="42",
            community_id="forum.example.com",
        )
        assert identity.can_administer_community is False
        assert identity.extra_claims == {}


@pytest.mark.unit
class TestResolvePlatformIdentityFromAdapterHeaders:
    def test_resolves_from_adapter_headers_with_platform_adapter_scope(self) -> None:
        from src.auth.platform_claims import resolve_platform_identity

        api_key = _make_api_key(scopes=["platform:adapter"])
        request = _make_request(
            headers={
                "x-adapter-platform": "discourse",
                "x-adapter-user-id": "42",
                "x-adapter-username": "alice",
                "x-adapter-trust-level": "2",
                "x-adapter-admin": "true",
                "x-adapter-moderator": "false",
                "x-adapter-scope": "forum.example.com",
            },
            api_key=api_key,
        )

        identity = resolve_platform_identity(request)
        assert identity is not None
        assert identity.platform == "discourse"
        assert identity.sub == "42"
        assert identity.community_id == "forum.example.com"
        assert identity.can_administer_community is True
        assert identity.extra_claims["username"] == "alice"
        assert identity.extra_claims["trust_level"] == "2"
        assert identity.extra_claims["moderator"] == "false"

    def test_adapter_headers_ignored_without_platform_adapter_scope(self) -> None:
        from src.auth.platform_claims import resolve_platform_identity

        api_key = _make_api_key(scopes=["simulations:read"])
        request = _make_request(
            headers={
                "x-adapter-platform": "discourse",
                "x-adapter-user-id": "42",
                "x-adapter-scope": "forum.example.com",
            },
            api_key=api_key,
        )

        identity = resolve_platform_identity(request)
        assert identity is None

    def test_adapter_headers_ignored_without_api_key(self) -> None:
        from src.auth.platform_claims import resolve_platform_identity

        request = _make_request(
            headers={
                "x-adapter-platform": "discourse",
                "x-adapter-user-id": "42",
                "x-adapter-scope": "forum.example.com",
            },
        )

        identity = resolve_platform_identity(request)
        assert identity is None

    def test_adapter_headers_require_platform_header(self) -> None:
        from src.auth.platform_claims import resolve_platform_identity

        api_key = _make_api_key(scopes=["platform:adapter"])
        request = _make_request(
            headers={
                "x-adapter-user-id": "42",
                "x-adapter-scope": "forum.example.com",
            },
            api_key=api_key,
        )

        identity = resolve_platform_identity(request)
        assert identity is None

    def test_adapter_headers_require_user_id(self) -> None:
        from src.auth.platform_claims import resolve_platform_identity

        api_key = _make_api_key(scopes=["platform:adapter"])
        request = _make_request(
            headers={
                "x-adapter-platform": "discourse",
                "x-adapter-scope": "forum.example.com",
            },
            api_key=api_key,
        )

        identity = resolve_platform_identity(request)
        assert identity is None

    def test_adapter_headers_require_scope(self) -> None:
        from src.auth.platform_claims import resolve_platform_identity

        api_key = _make_api_key(scopes=["platform:adapter"])
        request = _make_request(
            headers={
                "x-adapter-platform": "discourse",
                "x-adapter-user-id": "42",
            },
            api_key=api_key,
        )

        identity = resolve_platform_identity(request)
        assert identity is None

    def test_admin_false_sets_can_administer_false(self) -> None:
        from src.auth.platform_claims import resolve_platform_identity

        api_key = _make_api_key(scopes=["platform:adapter"])
        request = _make_request(
            headers={
                "x-adapter-platform": "discourse",
                "x-adapter-user-id": "42",
                "x-adapter-admin": "false",
                "x-adapter-scope": "forum.example.com",
            },
            api_key=api_key,
        )

        identity = resolve_platform_identity(request)
        assert identity is not None
        assert identity.can_administer_community is False

    def test_unscoped_api_key_rejects_adapter_headers(self) -> None:
        from src.auth.platform_claims import resolve_platform_identity

        api_key = _make_api_key(scopes=None)
        request = _make_request(
            headers={
                "x-adapter-platform": "discourse",
                "x-adapter-user-id": "42",
                "x-adapter-scope": "forum.example.com",
            },
            api_key=api_key,
        )

        identity = resolve_platform_identity(request)
        assert identity is None


@pytest.mark.unit
class TestResolvePlatformIdentityFromJWT:
    def test_resolves_from_jwt_fallback(self) -> None:
        from src.auth.platform_claims import (
            create_platform_claims_token,
            resolve_platform_identity,
        )

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123456789",
            community_id="987654321",
            can_administer_community=True,
        )

        request = _make_request(headers={"x-platform-claims": token})

        identity = resolve_platform_identity(request)
        assert identity is not None
        assert identity.platform == "discord"
        assert identity.sub == "123456789"
        assert identity.community_id == "987654321"
        assert identity.can_administer_community is True

    def test_invalid_jwt_returns_none(self) -> None:
        from src.auth.platform_claims import resolve_platform_identity

        request = _make_request(headers={"x-platform-claims": "invalid.jwt.token"})

        identity = resolve_platform_identity(request)
        assert identity is None

    def test_no_headers_returns_none(self) -> None:
        from src.auth.platform_claims import resolve_platform_identity

        request = _make_request()

        identity = resolve_platform_identity(request)
        assert identity is None

    def test_adapter_headers_take_priority_over_jwt(self) -> None:
        from src.auth.platform_claims import (
            create_platform_claims_token,
            resolve_platform_identity,
        )

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="jwt-user",
            community_id="jwt-community",
            can_administer_community=False,
        )

        api_key = _make_api_key(scopes=["platform:adapter"])
        request = _make_request(
            headers={
                "x-platform-claims": token,
                "x-adapter-platform": "discourse",
                "x-adapter-user-id": "adapter-user",
                "x-adapter-scope": "adapter-community",
                "x-adapter-admin": "true",
            },
            api_key=api_key,
        )

        identity = resolve_platform_identity(request)
        assert identity is not None
        assert identity.platform == "discourse"
        assert identity.sub == "adapter-user"
        assert identity.community_id == "adapter-community"
        assert identity.can_administer_community is True


@pytest.mark.unit
class TestGetRequestPlatform:
    def test_returns_platform_from_platform_identity(self) -> None:
        from src.auth.platform_claims import PlatformIdentity, get_request_platform

        request = _make_request(headers={"x-platform-type": "discord"})
        request.state.platform_identity = PlatformIdentity(
            platform="discourse",
            scope="forum.example.com",
            sub="42",
            community_id="forum.example.com",
        )

        assert get_request_platform(request) == "discourse"

    def test_falls_back_to_x_platform_type_header(self) -> None:
        from src.auth.platform_claims import get_request_platform

        request = _make_request(headers={"x-platform-type": "discourse"})

        assert get_request_platform(request) == "discourse"

    def test_defaults_to_discord_when_no_identity_or_header(self) -> None:
        from src.auth.platform_claims import get_request_platform

        request = _make_request()

        assert get_request_platform(request) == "discord"

    def test_identity_takes_priority_over_header(self) -> None:
        from src.auth.platform_claims import PlatformIdentity, get_request_platform

        request = _make_request(headers={"x-platform-type": "discord"})
        request.state.platform_identity = PlatformIdentity(
            platform="discourse",
            scope="forum.example.com",
            sub="42",
            community_id="forum.example.com",
        )

        assert get_request_platform(request) == "discourse"

    def test_skips_identity_when_not_set_on_state(self) -> None:
        from src.auth.platform_claims import get_request_platform

        request = _make_request(headers={"x-platform-type": "discourse"})

        assert get_request_platform(request) == "discourse"

    def test_handles_mock_state_without_platform_identity_attr(self) -> None:
        from src.auth.platform_claims import get_request_platform

        request = MagicMock()
        request.headers = {}
        request.state = MagicMock(spec=[])

        assert get_request_platform(request) == "discord"

    def test_lazily_resolves_adapter_headers_when_identity_not_set(self) -> None:
        from src.auth.platform_claims import get_request_platform

        api_key = _make_api_key(scopes=["platform:adapter"])
        request = _make_request(
            headers={
                "x-adapter-platform": "discourse",
                "x-adapter-user-id": "42",
                "x-adapter-scope": "forum.example.com",
            },
            api_key=api_key,
        )

        assert get_request_platform(request) == "discourse"

    def test_lazy_resolution_skipped_without_adapter_scope(self) -> None:
        from src.auth.platform_claims import get_request_platform

        api_key = _make_api_key(scopes=["simulations:read"])
        request = _make_request(
            headers={
                "x-adapter-platform": "discourse",
                "x-adapter-user-id": "42",
                "x-adapter-scope": "forum.example.com",
            },
            api_key=api_key,
        )

        assert get_request_platform(request) == "discord"

    def test_lazy_resolution_falls_back_to_header_without_api_key(self) -> None:
        from src.auth.platform_claims import get_request_platform

        request = _make_request(
            headers={
                "x-adapter-platform": "discourse",
                "x-adapter-user-id": "42",
                "x-adapter-scope": "forum.example.com",
                "x-platform-type": "discourse",
            },
        )

        assert get_request_platform(request) == "discourse"
