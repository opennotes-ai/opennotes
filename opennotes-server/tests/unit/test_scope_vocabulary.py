import pytest

from src.auth.models import ALLOWED_API_KEY_SCOPES, RESTRICTED_SCOPES, APIKeyCreate


def test_all_scopes_present():
    expected = {
        "simulations:read",
        "requests:read",
        "requests:write",
        "notes:read",
        "notes:write",
        "notes:delete",
        "ratings:write",
        "profiles:read",
        "community-servers:read",
        "moderation-actions:read",
        "api-keys:create",
    }
    assert expected == ALLOWED_API_KEY_SCOPES


def test_restricted_scopes():
    assert "api-keys:create" in RESTRICTED_SCOPES


def test_restricted_scopes_subset_of_allowed():
    assert RESTRICTED_SCOPES.issubset(ALLOWED_API_KEY_SCOPES)


def test_api_key_create_accepts_all_scopes():
    for scope in ALLOWED_API_KEY_SCOPES:
        key = APIKeyCreate(name="test", scopes=[scope])
        assert scope in key.scopes


def test_api_key_create_rejects_invalid_scope():
    with pytest.raises(ValueError, match="Invalid scope"):
        APIKeyCreate(name="test", scopes=["invalid:scope"])
