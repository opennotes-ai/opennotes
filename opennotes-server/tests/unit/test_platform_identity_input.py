"""
Unit tests for PlatformIdentityInput schema.

Tests the new generic platform identity schema used by
get_or_create_profile_from_platform().
"""

import pytest
from pydantic import ValidationError

from src.users.profile_schemas import AuthProvider, PlatformIdentityInput


class TestPlatformIdentityInput:
    def test_minimal_discord_identity(self):
        identity = PlatformIdentityInput(
            provider=AuthProvider.DISCORD,
            provider_user_id="123456789",
        )
        assert identity.provider == AuthProvider.DISCORD.value
        assert identity.provider_user_id == "123456789"
        assert identity.provider_scope == "*"
        assert identity.username is None
        assert identity.display_name is None
        assert identity.avatar_url is None
        assert identity.metadata is None

    def test_full_discord_identity(self):
        identity = PlatformIdentityInput(
            provider=AuthProvider.DISCORD,
            provider_user_id="123456789",
            provider_scope="*",
            username="testuser",
            display_name="Test User",
            avatar_url="https://cdn.discordapp.com/avatars/123/abc.png",
            metadata={"global_name": "Test User"},
        )
        assert identity.provider == AuthProvider.DISCORD.value
        assert identity.provider_user_id == "123456789"
        assert identity.username == "testuser"
        assert identity.display_name == "Test User"
        assert identity.avatar_url == "https://cdn.discordapp.com/avatars/123/abc.png"
        assert identity.metadata == {"global_name": "Test User"}

    def test_discourse_identity_with_scope(self):
        identity = PlatformIdentityInput(
            provider=AuthProvider.DISCOURSE,
            provider_user_id="42",
            provider_scope="community.example.com",
            username="discourse_user",
            display_name="Discourse User",
            metadata={"trust_level": 3, "admin": False},
        )
        assert identity.provider == AuthProvider.DISCOURSE.value
        assert identity.provider_user_id == "42"
        assert identity.provider_scope == "community.example.com"
        assert identity.username == "discourse_user"
        assert identity.metadata == {"trust_level": 3, "admin": False}

    def test_provider_scope_defaults_to_wildcard(self):
        identity = PlatformIdentityInput(
            provider=AuthProvider.DISCORD,
            provider_user_id="111",
        )
        assert identity.provider_scope == "*"

    def test_invalid_provider_rejected(self):
        with pytest.raises(ValidationError, match="provider"):
            PlatformIdentityInput(
                provider="invalid_platform",
                provider_user_id="123",
            )

    def test_empty_provider_user_id_rejected(self):
        with pytest.raises(ValidationError, match="provider_user_id"):
            PlatformIdentityInput(
                provider=AuthProvider.DISCORD,
                provider_user_id="",
            )

    def test_provider_user_id_required(self):
        with pytest.raises(ValidationError, match="provider_user_id"):
            PlatformIdentityInput(
                provider=AuthProvider.DISCORD,
            )

    def test_whitespace_stripping(self):
        identity = PlatformIdentityInput(
            provider=AuthProvider.DISCORD,
            provider_user_id="  123  ",
            username="  user  ",
            display_name="  Name  ",
        )
        assert identity.provider_user_id == "123"
        assert identity.username == "user"
        assert identity.display_name == "Name"

    def test_email_provider(self):
        identity = PlatformIdentityInput(
            provider=AuthProvider.EMAIL,
            provider_user_id="user@example.com",
        )
        assert identity.provider == AuthProvider.EMAIL.value

    def test_github_provider(self):
        identity = PlatformIdentityInput(
            provider=AuthProvider.GITHUB,
            provider_user_id="gh_user_42",
        )
        assert identity.provider == AuthProvider.GITHUB.value
