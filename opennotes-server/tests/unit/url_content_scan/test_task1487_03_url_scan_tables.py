from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_PATH = _REPO_ROOT / "alembic" / "versions" / "task1487_03_url_scan_tables.py"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "_task1487_03_migration_for_unit_test", _MIGRATION_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_get_application_role_name_parses_username_from_database_url():
    migration = _load_migration_module()

    assert (
        migration._get_application_role_name(
            "postgresql+asyncpg://url_scan_app:secret@example.com:5432/opennotes"
        )
        == "url_scan_app"
    )


@pytest.mark.unit
def test_get_application_role_name_returns_none_when_database_url_missing(monkeypatch):
    migration = _load_migration_module()

    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert migration._get_application_role_name(None) is None
    assert migration._get_application_role_name("") is None


@pytest.mark.unit
def test_get_application_role_name_raises_for_invalid_database_url():
    migration = _load_migration_module()

    with pytest.raises(ValueError, match="DATABASE_URL"):
        migration._get_application_role_name("not-a-postgres-url")


@pytest.mark.unit
def test_resolve_application_role_name_falls_back_to_current_user_when_database_url_absent(
    monkeypatch,
):
    migration = _load_migration_module()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    class _FakeBind:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str] | None]] = []

        def execute(self, statement, params=None):
            self.calls.append((str(statement), params))

            class _Result:
                @staticmethod
                def scalar_one():
                    return "migration_runner"

            return _Result()

    bind = _FakeBind()

    assert migration._resolve_application_role_name(bind, None) == "migration_runner"
    assert "SELECT current_user" in bind.calls[0][0]


@pytest.mark.unit
def test_enable_rls_and_role_policy_creates_policy_for_non_bypass_role(monkeypatch):
    migration = _load_migration_module()
    executed_sql: list[str] = []

    class _FakeIdentifierPreparer:
        @staticmethod
        def quote_identifier(identifier: str) -> str:
            return f'"{identifier}"'

    class _FakeDialect:
        identifier_preparer = _FakeIdentifierPreparer()

    class _FakeBind:
        dialect = _FakeDialect()

        def execute(self, statement, params=None):
            sql = str(statement)
            if "SELECT current_user" in sql:
                raise AssertionError("current_user fallback should not be used")
            if "SELECT EXISTS" in sql:
                if params == {"role_name": "url_scan_app"}:

                    class _ExistsResult:
                        @staticmethod
                        def scalar_one():
                            return True

                    return _ExistsResult()

                class _ExistsResult:
                    @staticmethod
                    def scalar_one():
                        return False

                return _ExistsResult()
            if "SELECT COALESCE(rolbypassrls" in sql:

                class _BypassResult:
                    @staticmethod
                    def scalar_one():
                        return False

                return _BypassResult()
            raise AssertionError(f"unexpected execute call: {sql}")

    monkeypatch.setattr(migration.op, "get_bind", lambda: _FakeBind())
    monkeypatch.setattr(migration.op, "execute", executed_sql.append)

    migration._enable_rls_and_role_policy(
        "url_scan_state",
        database_url="postgresql+asyncpg://url_scan_app:secret@example.com:5432/opennotes",
    )

    assert executed_sql[:2] == [
        "ALTER TABLE public.url_scan_state ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE public.url_scan_state FORCE ROW LEVEL SECURITY",
    ]
    assert (
        executed_sql[2] == 'CREATE POLICY "url_scan_state_url_scan_app_full_access" '
        'ON public.url_scan_state FOR ALL TO "url_scan_app" '
        "USING (true) WITH CHECK (true)"
    )


@pytest.mark.unit
def test_enable_rls_and_role_policy_skips_policy_for_bypass_role(monkeypatch):
    migration = _load_migration_module()
    executed_sql: list[str] = []

    class _FakeIdentifierPreparer:
        @staticmethod
        def quote_identifier(identifier: str) -> str:
            return f'"{identifier}"'

    class _FakeDialect:
        identifier_preparer = _FakeIdentifierPreparer()

    class _FakeBind:
        dialect = _FakeDialect()

        def execute(self, statement, params=None):
            sql = str(statement)
            if "SELECT EXISTS" in sql:
                if params == {"role_name": "url_scan_app"}:

                    class _ExistsResult:
                        @staticmethod
                        def scalar_one():
                            return True

                    return _ExistsResult()

                class _ExistsResult:
                    @staticmethod
                    def scalar_one():
                        return False

                return _ExistsResult()
            if "SELECT COALESCE(rolbypassrls" in sql:

                class _BypassResult:
                    @staticmethod
                    def scalar_one():
                        return True

                return _BypassResult()
            raise AssertionError(f"unexpected execute call: {sql}")

    monkeypatch.setattr(migration.op, "get_bind", lambda: _FakeBind())
    monkeypatch.setattr(migration.op, "execute", executed_sql.append)

    migration._enable_rls_and_role_policy(
        "url_scan_state",
        database_url="postgresql+asyncpg://url_scan_app:secret@example.com:5432/opennotes",
    )

    assert executed_sql == [
        "ALTER TABLE public.url_scan_state ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE public.url_scan_state FORCE ROW LEVEL SECURITY",
    ]


@pytest.mark.unit
def test_enable_rls_and_role_policy_raises_when_app_role_missing(monkeypatch):
    migration = _load_migration_module()

    class _FakeIdentifierPreparer:
        @staticmethod
        def quote_identifier(identifier: str) -> str:
            return f'"{identifier}"'

    class _FakeDialect:
        identifier_preparer = _FakeIdentifierPreparer()

    class _FakeBind:
        dialect = _FakeDialect()

        def execute(self, statement, params=None):
            sql = str(statement)
            if "SELECT EXISTS" in sql:

                class _ExistsResult:
                    @staticmethod
                    def scalar_one():
                        return False

                return _ExistsResult()
            raise AssertionError(f"unexpected execute call: {sql}")

    monkeypatch.setattr(migration.op, "get_bind", lambda: _FakeBind())

    with pytest.raises(RuntimeError, match="url_scan_app"):
        migration._enable_rls_and_role_policy(
            "url_scan_state",
            database_url="postgresql+asyncpg://url_scan_app:secret@example.com:5432/opennotes",
        )
