"""Unit tests for database module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestResetDatabaseForTestLoop:
    """Tests for _reset_database_for_test_loop function."""

    def test_disposes_engine_before_setting_to_none(self):
        """Engine should be disposed before being set to None to avoid resource leak."""
        from src import database

        mock_sync_engine = MagicMock()
        mock_engine = MagicMock()
        mock_engine.sync_engine = mock_sync_engine

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._async_session_maker = MagicMock()
            database._engine_loop = MagicMock()

            database._reset_database_for_test_loop()

            mock_sync_engine.dispose.assert_called_once_with(close=False)

            assert database._engine is None
            assert database._async_session_maker is None
            assert database._engine_loop is None

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_handles_none_engine_gracefully(self):
        """When engine is None, reset should complete without error."""
        from src import database

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = None
            database._async_session_maker = None
            database._engine_loop = None

            database._reset_database_for_test_loop()

            assert database._engine is None
            assert database._async_session_maker is None
            assert database._engine_loop is None

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_dispose_called_before_engine_set_to_none(self):
        """Verify dispose is called BEFORE engine is set to None (ordering matters)."""
        from src import database

        call_order = []

        mock_sync_engine = MagicMock()

        def track_dispose(**kwargs):
            call_order.append(("dispose", database._engine is not None))

        mock_sync_engine.dispose.side_effect = track_dispose

        mock_engine = MagicMock()
        mock_engine.sync_engine = mock_sync_engine

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._async_session_maker = MagicMock()
            database._engine_loop = MagicMock()

            database._reset_database_for_test_loop()

            assert len(call_order) == 1
            assert call_order[0] == ("dispose", True)

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop


class TestGetEngineLoopChange:
    """Tests for get_engine() behavior when event loop changes."""

    def test_disposes_old_engine_on_loop_change(self):
        """get_engine() should dispose the old engine's connection pool when the loop changes."""
        from src import database

        old_loop = MagicMock()
        new_loop = MagicMock()

        mock_sync_engine = MagicMock()
        mock_old_engine = MagicMock()
        mock_old_engine.sync_engine = mock_sync_engine

        mock_new_engine = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_old_engine
            database._engine_loop = old_loop

            with (
                patch("src.database.asyncio.get_running_loop", return_value=new_loop),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                result = database.get_engine()

            mock_sync_engine.dispose.assert_called_once_with(close=False)
            assert result is mock_new_engine
            assert database._engine is mock_new_engine
            assert database._engine_loop is new_loop

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_gc_module_not_imported(self):
        """database module should not import gc (explicit dispose makes it unnecessary)."""
        from src import database

        assert not hasattr(database, "gc")


class TestGetEngineFirstCreation:
    """Tests for get_engine() initial engine creation."""

    def test_creates_engine_when_none_exists_no_running_loop(self):
        """get_engine() should create engine when _engine is None and no running loop."""
        from src import database

        mock_new_engine = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = None
            database._engine_loop = None

            with (
                patch(
                    "src.database.asyncio.get_running_loop",
                    side_effect=RuntimeError("no running loop"),
                ),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                result = database.get_engine()

            assert result is mock_new_engine
            assert database._engine is mock_new_engine
            assert database._engine_loop is None

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_creates_engine_when_none_exists_with_running_loop(self):
        """get_engine() should create engine and capture loop when _engine is None."""
        from src import database

        mock_new_engine = MagicMock()
        mock_loop = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = None
            database._engine_loop = None

            with (
                patch(
                    "src.database.asyncio.get_running_loop",
                    return_value=mock_loop,
                ),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                result = database.get_engine()

            assert result is mock_new_engine
            assert database._engine is mock_new_engine
            assert database._engine_loop is mock_loop

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop


class TestGetEngineExistingNoLoopChange:
    """Tests for get_engine() when engine exists and loop hasn't changed."""

    def test_returns_existing_engine_when_same_loop(self):
        """get_engine() should return existing engine when loop hasn't changed."""
        from src import database

        mock_loop = MagicMock()
        mock_engine = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._engine_loop = mock_loop

            with patch(
                "src.database.asyncio.get_running_loop",
                return_value=mock_loop,
            ):
                result = database.get_engine()

            assert result is mock_engine

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_returns_existing_engine_when_no_running_loop(self):
        """get_engine() should return existing engine when no loop is running (sync context)."""
        from src import database

        mock_engine = MagicMock()
        mock_loop = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._engine_loop = mock_loop

            with patch(
                "src.database.asyncio.get_running_loop",
                side_effect=RuntimeError("no running loop"),
            ):
                result = database.get_engine()

            assert result is mock_engine

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop


class TestGetSessionMaker:
    """Tests for get_session_maker() function."""

    def test_creates_session_maker_from_sync_context(self):
        """get_session_maker() should work when called from sync context (no running loop)."""
        from src import database

        mock_engine = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._async_session_maker = None
            database._engine_loop = None

            with patch(
                "src.database.asyncio.get_running_loop",
                side_effect=RuntimeError("no running loop"),
            ):
                result = database.get_session_maker()

            assert result is not None
            assert database._async_session_maker is result

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_returns_existing_session_maker_from_sync_context(self):
        """get_session_maker() should return existing maker from sync context."""
        from src import database

        mock_session_maker = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = MagicMock()
            database._async_session_maker = mock_session_maker
            database._engine_loop = None

            with patch(
                "src.database.asyncio.get_running_loop",
                side_effect=RuntimeError("no running loop"),
            ):
                result = database.get_session_maker()

            assert result is mock_session_maker

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_recreates_session_maker_on_loop_change(self):
        """get_session_maker() should recreate when event loop changes."""
        from src import database

        old_loop = MagicMock()
        new_loop = MagicMock()
        mock_engine = MagicMock()
        mock_old_session_maker = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._async_session_maker = mock_old_session_maker
            database._engine_loop = old_loop

            with patch(
                "src.database.asyncio.get_running_loop",
                return_value=new_loop,
            ):
                result = database.get_session_maker()

            assert result is not mock_old_session_maker
            assert database._async_session_maker is result

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop


class TestCloseDb:
    """Tests for close_db() function."""

    @pytest.mark.asyncio
    async def test_close_db_resets_engine_loop(self):
        """close_db() should reset _engine_loop to None."""
        from src import database

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._async_session_maker = MagicMock()
            database._engine_loop = MagicMock()

            await database.close_db()

            assert database._engine is None
            assert database._async_session_maker is None
            assert database._engine_loop is None

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop
