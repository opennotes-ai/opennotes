import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from src.database import _db_lock, _engines, _session_makers, close_db


class TestCloseDbErrorHandling:
    def setup_method(self):
        with _db_lock:
            _engines.clear()
            _session_makers.clear()

    def teardown_method(self):
        with _db_lock:
            _engines.clear()
            _session_makers.clear()

    @pytest.mark.asyncio
    async def test_dispose_error_logged_at_warning(self, caplog):
        mock_engine = AsyncMock()
        mock_engine.dispose.side_effect = Exception("connection reset by peer")

        loop = asyncio.get_running_loop()
        with _db_lock:
            _engines[id(loop)] = (mock_engine, loop)

        with caplog.at_level(logging.WARNING, logger="src.database"):
            await close_db()

        assert any("Error disposing" in r.message for r in caplog.records)
        assert all(
            r.levelno <= logging.WARNING for r in caplog.records if "Error disposing" in r.message
        )

    @pytest.mark.asyncio
    async def test_skips_background_loop_engines(self):
        mock_main_engine = AsyncMock()
        mock_bg_engine = AsyncMock()

        main_loop = asyncio.get_running_loop()
        bg_loop = asyncio.new_event_loop()

        with _db_lock:
            _engines[id(main_loop)] = (mock_main_engine, main_loop)
            _engines[id(bg_loop)] = (mock_bg_engine, bg_loop)

        await close_db()

        mock_main_engine.dispose.assert_awaited_once()
        mock_bg_engine.dispose.assert_not_awaited()
        bg_loop.close()

    @pytest.mark.asyncio
    async def test_clears_all_engines_including_skipped(self):
        mock_main_engine = AsyncMock()
        mock_bg_engine = AsyncMock()

        main_loop = asyncio.get_running_loop()
        bg_loop = asyncio.new_event_loop()

        with _db_lock:
            _engines[id(main_loop)] = (mock_main_engine, main_loop)
            _engines[id(bg_loop)] = (mock_bg_engine, bg_loop)

        await close_db()

        assert len(_engines) == 0
        assert len(_session_makers) == 0
        bg_loop.close()
