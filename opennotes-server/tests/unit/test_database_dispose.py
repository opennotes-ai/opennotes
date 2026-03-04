from unittest.mock import MagicMock, patch

from src.database import _reset_database_for_test_loop, get_engine


class TestDisposeCloseParameter:
    @patch("src.database._create_engine")
    def test_get_engine_loop_change_disposes_with_close_false(
        self, mock_create_engine: MagicMock
    ) -> None:
        import asyncio

        import src.database as db_module

        old_engine = MagicMock()
        new_engine = MagicMock()
        mock_create_engine.return_value = new_engine

        loop = asyncio.new_event_loop()
        try:
            with db_module._db_lock:
                db_module._engine = old_engine
                db_module._engine_loop = "stale_loop_sentinel"

            with patch("src.database.asyncio.get_running_loop", return_value=loop):
                result = get_engine()

            assert result is new_engine
            old_engine.sync_engine.dispose.assert_called_once_with()
        finally:
            loop.close()
            with db_module._db_lock:
                db_module._engine = None
                db_module._async_session_maker = None
                db_module._engine_loop = None

    def test_reset_database_for_test_loop_disposes_with_close_false(self) -> None:
        import src.database as db_module

        mock_engine = MagicMock()

        with db_module._db_lock:
            db_module._engine = mock_engine
            db_module._async_session_maker = MagicMock()
            db_module._engine_loop = MagicMock()

        _reset_database_for_test_loop()

        mock_engine.sync_engine.dispose.assert_called_once_with()

        assert db_module._engine is None
        assert db_module._async_session_maker is None
        assert db_module._engine_loop is None
