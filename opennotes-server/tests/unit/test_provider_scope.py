"""Tests for provider_scope column and DISCOURSE AuthProvider."""

from src.users.profile_schemas import AuthProvider


class TestAuthProviderDiscourse:
    def test_discourse_enum_value_exists(self):
        assert AuthProvider.DISCOURSE == "discourse"

    def test_discourse_in_auth_providers(self):
        provider_values = [p.value for p in AuthProvider]
        assert "discourse" in provider_values


class TestProviderScopeColumn:
    def test_user_identity_has_provider_scope_attribute(self):
        from src.users.profile_models import UserIdentity

        mapper = UserIdentity.__table__.columns
        assert "provider_scope" in mapper, "UserIdentity should have a provider_scope column"

    def test_provider_scope_default_is_wildcard(self):
        from src.users.profile_models import UserIdentity

        col = UserIdentity.__table__.columns["provider_scope"]
        assert col.server_default is not None
        assert col.server_default.arg == "*"

    def test_provider_scope_not_nullable(self):
        from src.users.profile_models import UserIdentity

        col = UserIdentity.__table__.columns["provider_scope"]
        assert col.nullable is False

    def test_unique_constraint_includes_provider_scope(self):
        from src.users.profile_models import UserIdentity

        table = UserIdentity.__table__
        unique_indexes = [idx for idx in table.indexes if idx.unique]
        col_sets = [frozenset(c.name for c in idx.columns) for idx in unique_indexes]
        expected = frozenset({"provider", "provider_scope", "provider_user_id"})
        assert expected in col_sets, (
            f"Expected unique index on (provider, provider_scope, provider_user_id), "
            f"found: {col_sets}"
        )
