"""Unit tests for database module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestResetDatabaseForTestLoop:
    """Tests for _reset_database_for_test_loop function."""

    def test_nulls_engine_without_disposing(self):
        from src import database

        mock_engine = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._async_session_maker = MagicMock()
            database._engine_loop = MagicMock()

            database._reset_database_for_test_loop()

            mock_engine.sync_engine.dispose.assert_not_called()
            assert database._engine is None
            assert database._async_session_maker is None
            assert database._engine_loop is None

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_handles_none_engine_gracefully(self):
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


class TestGetEngineLoopLiveness:
    """Tests for get_engine() behavior based on loop liveness (not identity)."""

    def test_recreates_engine_when_tracked_loop_is_closed(self):
        from src import database

        closed_loop = asyncio.new_event_loop()
        closed_loop.close()

        mock_old_engine = MagicMock()
        mock_new_engine = MagicMock()
        current_loop = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_old_engine
            database._engine_loop = closed_loop

            with (
                patch("src.database.asyncio.get_running_loop", return_value=current_loop),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                result = database.get_engine()

            assert result is mock_new_engine
            assert database._engine is mock_new_engine
            assert database._engine_loop is current_loop

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_keeps_engine_when_loop_differs_but_alive(self):
        from src import database

        alive_loop = asyncio.new_event_loop()
        different_loop = MagicMock()

        mock_engine = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._engine_loop = alive_loop

            with patch("src.database.asyncio.get_running_loop", return_value=different_loop):
                result = database.get_engine()

            assert result is mock_engine

        finally:
            alive_loop.close()
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_gc_module_not_imported(self):
        from src import database

        assert not hasattr(database, "gc")


class TestGetEngineFirstCreation:
    """Tests for get_engine() initial engine creation."""

    def test_creates_engine_when_none_exists_no_running_loop(self):
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
    """Tests for get_engine() when engine exists and loop is alive."""

    def test_returns_existing_engine_when_same_loop(self):
        from src import database

        alive_loop = asyncio.new_event_loop()
        mock_engine = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._engine_loop = alive_loop

            with patch(
                "src.database.asyncio.get_running_loop",
                return_value=alive_loop,
            ):
                result = database.get_engine()

            assert result is mock_engine

        finally:
            alive_loop.close()
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_returns_existing_engine_when_no_running_loop(self):
        from src import database

        mock_engine = MagicMock()
        alive_loop = asyncio.new_event_loop()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._engine_loop = alive_loop

            with patch(
                "src.database.asyncio.get_running_loop",
                side_effect=RuntimeError("no running loop"),
            ):
                result = database.get_engine()

            assert result is mock_engine

        finally:
            alive_loop.close()
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop


class TestGetSessionMaker:
    """Tests for get_session_maker() function."""

    def test_creates_session_maker_from_sync_context(self):
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

    def test_recreates_session_maker_when_tracked_loop_is_closed(self):
        from src import database

        closed_loop = asyncio.new_event_loop()
        closed_loop.close()

        mock_engine = MagicMock()
        mock_old_session_maker = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._async_session_maker = mock_old_session_maker
            database._engine_loop = closed_loop

            result = database.get_session_maker()

            assert result is not mock_old_session_maker
            assert database._async_session_maker is result

        finally:
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop

    def test_keeps_session_maker_when_loop_differs_but_alive(self):
        from src import database

        alive_loop = asyncio.new_event_loop()
        mock_engine = MagicMock()
        mock_session_maker = MagicMock()

        original_engine = database._engine
        original_session_maker = database._async_session_maker
        original_loop = database._engine_loop

        try:
            database._engine = mock_engine
            database._async_session_maker = mock_session_maker
            database._engine_loop = alive_loop

            different_loop = MagicMock()
            with patch("src.database.asyncio.get_running_loop", return_value=different_loop):
                result = database.get_session_maker()

            assert result is mock_session_maker

        finally:
            alive_loop.close()
            database._engine = original_engine
            database._async_session_maker = original_session_maker
            database._engine_loop = original_loop


class TestCloseDb:
    """Tests for close_db() function."""

    @pytest.mark.asyncio
    async def test_close_db_resets_engine_loop(self):
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
