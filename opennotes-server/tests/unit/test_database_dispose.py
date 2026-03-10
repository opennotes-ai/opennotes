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
        current_loop.is_closed.return_value = False

        original_engines = dict(db_module._engines)
        original_session_makers = dict(db_module._session_makers)

        try:
            with db_module._db_lock:
                db_module._engines.clear()
                db_module._session_makers.clear()
                old_key = id(closed_loop)
                db_module._engines[old_key] = (old_engine, closed_loop)

            with patch("src.database.asyncio.get_running_loop", return_value=current_loop):
                result = get_engine()

            assert result is new_engine
            new_key = id(current_loop)
            assert new_key in db_module._engines
            assert db_module._engines[new_key] == (new_engine, current_loop)
        finally:
            with db_module._db_lock:
                db_module._engines.clear()
                db_module._engines.update(original_engines)
                db_module._session_makers.clear()
                db_module._session_makers.update(original_session_makers)

    @patch("src.database._create_engine")
    def test_get_engine_creates_new_for_different_alive_loop(
        self, mock_create_engine: MagicMock
    ) -> None:
        import src.database as db_module

        existing_engine = MagicMock()
        new_engine = MagicMock()
        mock_create_engine.return_value = new_engine

        alive_loop = asyncio.new_event_loop()
        different_loop = MagicMock()
        different_loop.is_closed.return_value = False

        original_engines = dict(db_module._engines)
        original_session_makers = dict(db_module._session_makers)

        try:
            with db_module._db_lock:
                db_module._engines.clear()
                db_module._session_makers.clear()
                alive_key = id(alive_loop)
                db_module._engines[alive_key] = (existing_engine, alive_loop)

            with patch("src.database.asyncio.get_running_loop", return_value=different_loop):
                result = get_engine()

            assert result is new_engine
            diff_key = id(different_loop)
            assert diff_key in db_module._engines
            assert db_module._engines[alive_key] == (existing_engine, alive_loop)
        finally:
            alive_loop.close()
            with db_module._db_lock:
                db_module._engines.clear()
                db_module._engines.update(original_engines)
                db_module._session_makers.clear()
                db_module._session_makers.update(original_session_makers)

    def test_reset_database_for_test_loop_does_not_dispose(self) -> None:
        import src.database as db_module

        mock_engine = MagicMock()

        original_engines = dict(db_module._engines)
        original_session_makers = dict(db_module._session_makers)

        try:
            with db_module._db_lock:
                db_module._engines.clear()
                db_module._session_makers.clear()
                db_module._engines[0] = (mock_engine, None)
                db_module._session_makers[0] = MagicMock()

            _reset_database_for_test_loop()

            mock_engine.sync_engine.dispose.assert_not_called()
            assert len(db_module._engines) == 0
            assert len(db_module._session_makers) == 0
        finally:
            with db_module._db_lock:
                db_module._engines.clear()
                db_module._engines.update(original_engines)
                db_module._session_makers.clear()
                db_module._session_makers.update(original_session_makers)
