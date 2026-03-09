import asyncio
from unittest.mock import MagicMock, patch

from src.database import _reset_database_for_test_loop, get_engine


class TestDisposeOnClosedLoop:
    @patch("src.database._create_engine")
    def test_get_engine_recreates_when_tracked_loop_is_closed(
        self, mock_create_engine: MagicMock
    ) -> None:
        import src.database as db_module

        old_engine = MagicMock()
        new_engine = MagicMock()
        mock_create_engine.return_value = new_engine

        closed_loop = asyncio.new_event_loop()
        closed_loop.close()

        current_loop = MagicMock()

        try:
            with db_module._db_lock:
                db_module._engine = old_engine
                db_module._engine_loop = closed_loop

            with patch("src.database.asyncio.get_running_loop", return_value=current_loop):
                result = get_engine()

            assert result is new_engine
            assert db_module._engine_loop is current_loop
        finally:
            with db_module._db_lock:
                db_module._engine = None
                db_module._async_session_maker = None
                db_module._engine_loop = None

    @patch("src.database._create_engine")
    def test_get_engine_does_not_recreate_when_loop_differs_but_alive(
        self, mock_create_engine: MagicMock
    ) -> None:
        import src.database as db_module

        existing_engine = MagicMock()

        alive_loop = asyncio.new_event_loop()
        different_loop = MagicMock()

        try:
            with db_module._db_lock:
                db_module._engine = existing_engine
                db_module._engine_loop = alive_loop

            with patch("src.database.asyncio.get_running_loop", return_value=different_loop):
                result = get_engine()

            assert result is existing_engine
            mock_create_engine.assert_not_called()
        finally:
            alive_loop.close()
            with db_module._db_lock:
                db_module._engine = None
                db_module._async_session_maker = None
                db_module._engine_loop = None

    def test_reset_database_for_test_loop_does_not_dispose(self) -> None:
        import src.database as db_module

        mock_engine = MagicMock()

        with db_module._db_lock:
            db_module._engine = mock_engine
            db_module._async_session_maker = MagicMock()
            db_module._engine_loop = MagicMock()

        _reset_database_for_test_loop()

        mock_engine.sync_engine.dispose.assert_not_called()
        assert db_module._engine is None
        assert db_module._async_session_maker is None
        assert db_module._engine_loop is None
