from __future__ import annotations

from uuid import uuid4

import pytest

from src.auth.models import APIKeyCreate
from src.users.models import APIKey


def _make_api_key(scopes: list[str] | None) -> APIKey:
    return APIKey(
        user_id=uuid4(),
        name="test-key",
        key_hash="fake-hash-value",
        scopes=scopes,
    )


@pytest.mark.unit
class TestAPIKeyHasScope:
    def test_none_scopes_grants_any_scope(self):
        key = _make_api_key(scopes=None)
        assert key.has_scope("simulations:read") is True
        assert key.has_scope("anything:else") is True

    def test_empty_list_denies_all_scopes(self):
        key = _make_api_key(scopes=[])
        assert key.has_scope("simulations:read") is False

    def test_matching_scope_returns_true(self):
        key = _make_api_key(scopes=["simulations:read"])
        assert key.has_scope("simulations:read") is True

    def test_non_matching_scope_returns_false(self):
        key = _make_api_key(scopes=["simulations:read"])
        assert key.has_scope("simulations:write") is False

    def test_multiple_scopes_match_one(self):
        key = _make_api_key(scopes=["simulations:read", "notes:read", "ratings:write"])
        assert key.has_scope("notes:read") is True

    def test_multiple_scopes_no_match(self):
        key = _make_api_key(scopes=["simulations:read", "notes:read"])
        assert key.has_scope("admin:all") is False

    def test_platform_adapter_scope(self):
        key = _make_api_key(scopes=["platform:adapter"])
        assert key.has_scope("platform:adapter") is True
        assert key.has_scope("simulations:read") is False


@pytest.mark.unit
class TestAPIKeyScopeValidation:
    def test_platform_adapter_scope_accepted(self):
        key_create = APIKeyCreate(name="adapter-key", scopes=["platform:adapter"])
        assert key_create.scopes == ["platform:adapter"]

    def test_simulations_read_scope_accepted(self):
        key_create = APIKeyCreate(name="sim-key", scopes=["simulations:read"])
        assert key_create.scopes == ["simulations:read"]

    def test_invalid_scope_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="Invalid scope"):
            APIKeyCreate(name="bad-key", scopes=["nonexistent:scope"])

    def test_none_scopes_accepted(self):
        key_create = APIKeyCreate(name="admin-key", scopes=None)
        assert key_create.scopes is None


@pytest.mark.unit
class TestAPIKeyIsScoped:
    def test_none_scopes_is_not_scoped(self):
        key = _make_api_key(scopes=None)
        assert key.is_scoped() is False

    def test_empty_list_is_not_scoped(self):
        key = _make_api_key(scopes=[])
        assert key.is_scoped() is False

    def test_populated_scopes_is_scoped(self):
        key = _make_api_key(scopes=["simulations:read"])
        assert key.is_scoped() is True

    def test_multiple_scopes_is_scoped(self):
        key = _make_api_key(scopes=["simulations:read", "notes:read"])
        assert key.is_scoped() is True
