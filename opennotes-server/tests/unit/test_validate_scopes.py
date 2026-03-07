import pytest
from pydantic import ValidationError

from src.auth.models import APIKeyCreate


class TestValidateScopes:
    def test_valid_scope(self):
        key = APIKeyCreate(name="test", scopes=["simulations:read"])
        assert key.scopes == ["simulations:read"]

    def test_none_scopes_means_unrestricted(self):
        key = APIKeyCreate(name="test", scopes=None)
        assert key.scopes is None

    def test_omitted_scopes_defaults_to_none(self):
        key = APIKeyCreate(name="test")
        assert key.scopes is None

    def test_empty_list(self):
        key = APIKeyCreate(name="test", scopes=[])
        assert key.scopes == []

    def test_invalid_scope_rejected(self):
        with pytest.raises(ValidationError, match="Invalid scope"):
            APIKeyCreate(name="test", scopes=["bogus:write"])

    def test_mixed_valid_and_invalid(self):
        with pytest.raises(ValidationError, match="Invalid scope"):
            APIKeyCreate(name="test", scopes=["simulations:read", "bogus:write"])

    def test_multiple_invalid_scopes(self):
        with pytest.raises(ValidationError, match="Invalid scope"):
            APIKeyCreate(name="test", scopes=["foo", "bar"])
