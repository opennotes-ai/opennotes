"""Unit tests for database module."""

from unittest.mock import MagicMock


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

            mock_sync_engine.dispose.assert_called_once()

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

        def track_dispose():
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
