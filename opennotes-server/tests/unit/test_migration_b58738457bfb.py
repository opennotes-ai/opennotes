import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

MIGRATION_PATH = Path(__file__).resolve().parents[2] / (
    "alembic/versions/b58738457bfb_add_provider_scope_to_user_identity.py"
)
MODULE_NAME = "b58738457bfb_migration"

OLD_INDEX_COLUMNS = ["provider", "provider_user_id"]
NEW_INDEX_COLUMNS = ["provider", "provider_scope", "provider_user_id"]
INDEX_NAME = "idx_user_identities_provider_user"


@pytest.fixture
def migration_module():
    spec = importlib.util.spec_from_file_location(MODULE_NAME, MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop(MODULE_NAME, None)


def _make_inspector(columns: list[str], index_columns: list[str] | None):
    inspector = MagicMock()
    inspector.get_columns.return_value = [{"name": c} for c in columns]
    if index_columns is not None:
        inspector.get_indexes.return_value = [{"name": INDEX_NAME, "column_names": index_columns}]
    else:
        inspector.get_indexes.return_value = []
    return inspector


class TestUpgradeIdempotent:
    def test_fresh_db_adds_column_and_creates_index(self, migration_module):
        inspector = _make_inspector(
            columns=["id", "provider", "provider_user_id"],
            index_columns=OLD_INDEX_COLUMNS,
        )
        with (
            patch.object(migration_module, "op") as mock_op,
            patch.object(migration_module, "sa_inspect", return_value=inspector),
        ):
            mock_op.get_bind.return_value = MagicMock()
            migration_module.upgrade()

            mock_op.add_column.assert_called_once()
            mock_op.drop_index.assert_called_once()
            mock_op.create_index.assert_called_once()

    def test_column_already_exists_skips_add(self, migration_module):
        inspector = _make_inspector(
            columns=["id", "provider", "provider_user_id", "provider_scope"],
            index_columns=OLD_INDEX_COLUMNS,
        )
        with (
            patch.object(migration_module, "op") as mock_op,
            patch.object(migration_module, "sa_inspect", return_value=inspector),
        ):
            mock_op.get_bind.return_value = MagicMock()
            migration_module.upgrade()

            mock_op.add_column.assert_not_called()
            mock_op.drop_index.assert_called_once()
            mock_op.create_index.assert_called_once()

    def test_new_index_already_exists_skips_drop_and_create(self, migration_module):
        inspector = _make_inspector(
            columns=["id", "provider", "provider_user_id", "provider_scope"],
            index_columns=NEW_INDEX_COLUMNS,
        )
        with (
            patch.object(migration_module, "op") as mock_op,
            patch.object(migration_module, "sa_inspect", return_value=inspector),
        ):
            mock_op.get_bind.return_value = MagicMock()
            migration_module.upgrade()

            mock_op.add_column.assert_not_called()
            mock_op.drop_index.assert_not_called()
            mock_op.create_index.assert_not_called()

    def test_no_index_at_all_creates_new(self, migration_module):
        inspector = _make_inspector(
            columns=["id", "provider", "provider_user_id", "provider_scope"],
            index_columns=None,
        )
        with (
            patch.object(migration_module, "op") as mock_op,
            patch.object(migration_module, "sa_inspect", return_value=inspector),
        ):
            mock_op.get_bind.return_value = MagicMock()
            migration_module.upgrade()

            mock_op.drop_index.assert_not_called()
            mock_op.create_index.assert_called_once()

    def test_fully_applied_state_is_noop(self, migration_module):
        inspector = _make_inspector(
            columns=["id", "provider", "provider_user_id", "provider_scope"],
            index_columns=NEW_INDEX_COLUMNS,
        )
        with (
            patch.object(migration_module, "op") as mock_op,
            patch.object(migration_module, "sa_inspect", return_value=inspector),
        ):
            mock_op.get_bind.return_value = MagicMock()
            migration_module.upgrade()

            mock_op.add_column.assert_not_called()
            mock_op.drop_index.assert_not_called()
            mock_op.create_index.assert_not_called()


class TestDowngradeIdempotent:
    def test_normal_downgrade_removes_column_and_restores_index(self, migration_module):
        inspector = _make_inspector(
            columns=["id", "provider", "provider_user_id", "provider_scope"],
            index_columns=NEW_INDEX_COLUMNS,
        )
        with (
            patch.object(migration_module, "op") as mock_op,
            patch.object(migration_module, "sa_inspect", return_value=inspector),
        ):
            mock_op.get_bind.return_value = MagicMock()
            migration_module.downgrade()

            mock_op.drop_index.assert_called_once()
            mock_op.create_index.assert_called_once()
            mock_op.drop_column.assert_called_once()

    def test_column_already_removed_skips_drop_column(self, migration_module):
        inspector = _make_inspector(
            columns=["id", "provider", "provider_user_id"],
            index_columns=None,
        )
        with (
            patch.object(migration_module, "op") as mock_op,
            patch.object(migration_module, "sa_inspect", return_value=inspector),
        ):
            mock_op.get_bind.return_value = MagicMock()
            migration_module.downgrade()

            mock_op.drop_column.assert_not_called()

    def test_old_index_already_restored_skips_drop_and_create(self, migration_module):
        inspector = _make_inspector(
            columns=["id", "provider", "provider_user_id", "provider_scope"],
            index_columns=OLD_INDEX_COLUMNS,
        )
        with (
            patch.object(migration_module, "op") as mock_op,
            patch.object(migration_module, "sa_inspect", return_value=inspector),
        ):
            mock_op.get_bind.return_value = MagicMock()
            migration_module.downgrade()

            mock_op.drop_index.assert_not_called()
            mock_op.create_index.assert_not_called()

    def test_no_index_creates_old_index(self, migration_module):
        inspector = _make_inspector(
            columns=["id", "provider", "provider_user_id", "provider_scope"],
            index_columns=None,
        )
        with (
            patch.object(migration_module, "op") as mock_op,
            patch.object(migration_module, "sa_inspect", return_value=inspector),
        ):
            mock_op.get_bind.return_value = MagicMock()
            migration_module.downgrade()

            mock_op.drop_index.assert_not_called()
            mock_op.create_index.assert_called_once()
            mock_op.drop_column.assert_called_once()

    def test_fully_reverted_state_is_noop(self, migration_module):
        inspector = _make_inspector(
            columns=["id", "provider", "provider_user_id"],
            index_columns=OLD_INDEX_COLUMNS,
        )
        with (
            patch.object(migration_module, "op") as mock_op,
            patch.object(migration_module, "sa_inspect", return_value=inspector),
        ):
            mock_op.get_bind.return_value = MagicMock()
            migration_module.downgrade()

            mock_op.drop_index.assert_not_called()
            mock_op.create_index.assert_not_called()
            mock_op.drop_column.assert_not_called()
