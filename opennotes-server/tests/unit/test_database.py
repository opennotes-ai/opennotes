"""Unit tests for database module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


class TestGetDirectSyncUrl:
    def test_prefers_direct_url(self):
        with patch("src.database.get_settings") as mock:
            mock.return_value.DATABASE_DIRECT_URL = "postgresql://user:pass@direct:5432/db"
            mock.return_value.DATABASE_URL = "postgresql+asyncpg://user:pass@pooled:6543/db"
            from src.database import get_direct_sync_url

            result = get_direct_sync_url()
            assert result == "postgresql://user:pass@direct:5432/db"

    def test_falls_back_to_database_url(self):
        with patch("src.database.get_settings") as mock:
            mock.return_value.DATABASE_DIRECT_URL = None
            mock.return_value.DATABASE_URL = "postgresql+asyncpg://user:pass@pooled:6543/db"
            from src.database import get_direct_sync_url

            result = get_direct_sync_url()
            assert result == "postgresql://user:pass@pooled:6543/db"

    def test_converts_asyncpg_prefix_on_direct_url(self):
        with patch("src.database.get_settings") as mock:
            mock.return_value.DATABASE_DIRECT_URL = "postgresql+asyncpg://user:pass@direct:5432/db"
            mock.return_value.DATABASE_URL = "postgresql+asyncpg://user:pass@pooled:6543/db"
            from src.database import get_direct_sync_url

            result = get_direct_sync_url()
            assert result == "postgresql://user:pass@direct:5432/db"

    def test_handles_bare_url(self):
        with patch("src.database.get_settings") as mock:
            mock.return_value.DATABASE_DIRECT_URL = "user:pass@direct:5432/db"
            mock.return_value.DATABASE_URL = "postgresql+asyncpg://x:y@pooled/db"
            from src.database import get_direct_sync_url

            result = get_direct_sync_url()
            assert result == "postgresql://user:pass@direct:5432/db"

    def test_raises_when_no_url(self):
        with patch("src.database.get_settings") as mock:
            mock.return_value.DATABASE_DIRECT_URL = None
            mock.return_value.DATABASE_URL = None
            from src.database import get_direct_sync_url

            with pytest.raises(ValueError, match="DATABASE_URL"):
                get_direct_sync_url()

    def test_converts_postgres_scheme_alias(self):
        with patch("src.database.get_settings") as mock:
            mock.return_value.DATABASE_DIRECT_URL = "postgres://user:pass@host:5432/db"
            mock.return_value.DATABASE_URL = "postgresql+asyncpg://x:y@pooled/db"
            from src.database import get_direct_sync_url

            result = get_direct_sync_url()
            assert result == "postgresql://user:pass@host:5432/db"

    def test_empty_direct_url_falls_back(self):
        with patch("src.database.get_settings") as mock:
            mock.return_value.DATABASE_DIRECT_URL = ""
            mock.return_value.DATABASE_URL = "postgresql+asyncpg://user:pass@pooled:6543/db"
            from src.database import get_direct_sync_url

            result = get_direct_sync_url()
            assert result == "postgresql://user:pass@pooled:6543/db"


class TestResetDatabaseForTestLoop:
    """Tests for _reset_database_for_test_loop function."""

    def test_clears_all_entries_without_disposing(self):
        from src import database

        mock_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines[0] = (mock_engine, None)
            database._session_makers[0] = MagicMock()

            database._reset_database_for_test_loop()

            mock_engine.sync_engine.dispose.assert_not_called()
            assert len(database._engines) == 0
            assert len(database._session_makers) == 0

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_handles_empty_dicts_gracefully(self):
        from src import database

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()

            database._reset_database_for_test_loop()

            assert len(database._engines) == 0
            assert len(database._session_makers) == 0

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)


class TestGetEngineLoopLiveness:
    """Tests for get_engine() behavior based on loop liveness."""

    def test_recreates_engine_when_tracked_loop_is_closed(self):
        from src import database

        closed_loop = asyncio.new_event_loop()
        closed_loop.close()

        mock_old_engine = MagicMock()
        mock_new_engine = MagicMock()
        current_loop = MagicMock()
        current_loop.is_closed.return_value = False

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            loop_key = id(current_loop)
            old_key = id(closed_loop)
            database._engines.clear()
            database._session_makers.clear()
            database._engines[old_key] = (mock_old_engine, closed_loop)

            with (
                patch("src.database.asyncio.get_running_loop", return_value=current_loop),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                result = database.get_engine()

            assert result is mock_new_engine
            assert loop_key in database._engines
            assert database._engines[loop_key] == (mock_new_engine, current_loop)
            assert old_key not in database._engines

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_different_loop_gets_different_engine(self):
        from src import database

        alive_loop = asyncio.new_event_loop()
        different_loop = MagicMock()
        different_loop.is_closed.return_value = False

        mock_existing_engine = MagicMock()
        mock_new_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()
            alive_key = id(alive_loop)
            database._engines[alive_key] = (mock_existing_engine, alive_loop)

            with (
                patch("src.database.asyncio.get_running_loop", return_value=different_loop),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                result = database.get_engine()

            assert result is mock_new_engine
            assert database._engines[alive_key] == (mock_existing_engine, alive_loop)
            diff_key = id(different_loop)
            assert database._engines[diff_key] == (mock_new_engine, different_loop)

        finally:
            alive_loop.close()
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_gc_module_not_imported(self):
        from src import database

        assert not hasattr(database, "gc")


class TestGetEngineFirstCreation:
    """Tests for get_engine() initial engine creation."""

    def test_creates_engine_when_none_exists_no_running_loop(self):
        from src import database

        mock_new_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()

            with (
                patch(
                    "src.database.asyncio.get_running_loop",
                    side_effect=RuntimeError("no running loop"),
                ),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                result = database.get_engine()

            assert result is mock_new_engine
            assert 0 in database._engines
            engine, tracked_loop = database._engines[0]
            assert engine is mock_new_engine
            assert tracked_loop is None

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_creates_engine_when_none_exists_with_running_loop(self):
        from src import database

        mock_new_engine = MagicMock()
        mock_loop = MagicMock()
        mock_loop.is_closed.return_value = False

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()

            with (
                patch(
                    "src.database.asyncio.get_running_loop",
                    return_value=mock_loop,
                ),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                result = database.get_engine()

            assert result is mock_new_engine
            loop_key = id(mock_loop)
            assert loop_key in database._engines
            engine, tracked_loop = database._engines[loop_key]
            assert engine is mock_new_engine
            assert tracked_loop is mock_loop

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)


class TestGetEngineExistingNoLoopChange:
    """Tests for get_engine() when engine exists and loop is alive."""

    def test_returns_existing_engine_when_same_loop(self):
        from src import database

        alive_loop = asyncio.new_event_loop()
        mock_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()
            loop_key = id(alive_loop)
            database._engines[loop_key] = (mock_engine, alive_loop)

            with patch(
                "src.database.asyncio.get_running_loop",
                return_value=alive_loop,
            ):
                result = database.get_engine()

            assert result is mock_engine

        finally:
            alive_loop.close()
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_returns_existing_engine_when_no_running_loop(self):
        from src import database

        mock_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()
            database._engines[0] = (mock_engine, None)

            with patch(
                "src.database.asyncio.get_running_loop",
                side_effect=RuntimeError("no running loop"),
            ):
                result = database.get_engine()

            assert result is mock_engine

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)


class TestGetSessionMaker:
    """Tests for get_session_maker() function."""

    def test_creates_session_maker_from_sync_context(self):
        from src import database

        mock_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()
            database._engines[0] = (mock_engine, None)

            with patch(
                "src.database.asyncio.get_running_loop",
                side_effect=RuntimeError("no running loop"),
            ):
                result = database.get_session_maker()

            assert result is not None
            assert 0 in database._session_makers
            assert database._session_makers[0] is result

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_returns_existing_session_maker_from_sync_context(self):
        from src import database

        mock_session_maker = MagicMock()
        mock_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()
            database._engines[0] = (mock_engine, None)
            database._session_makers[0] = mock_session_maker

            with patch(
                "src.database.asyncio.get_running_loop",
                side_effect=RuntimeError("no running loop"),
            ):
                result = database.get_session_maker()

            assert result is mock_session_maker

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_recreates_session_maker_when_tracked_loop_is_closed(self):
        from src import database

        closed_loop = asyncio.new_event_loop()
        closed_loop.close()

        mock_engine = MagicMock()
        mock_new_engine = MagicMock()
        mock_old_session_maker = MagicMock()
        current_loop = MagicMock()
        current_loop.is_closed.return_value = False

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()
            old_key = id(closed_loop)
            database._engines[old_key] = (mock_engine, closed_loop)
            database._session_makers[old_key] = mock_old_session_maker

            with (
                patch("src.database.asyncio.get_running_loop", return_value=current_loop),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                result = database.get_session_maker()

            assert result is not mock_old_session_maker
            new_key = id(current_loop)
            assert new_key in database._session_makers
            assert database._session_makers[new_key] is result

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_different_loop_gets_different_session_maker(self):
        from src import database

        alive_loop = asyncio.new_event_loop()
        mock_engine = MagicMock()
        mock_session_maker = MagicMock()
        mock_new_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()
            alive_key = id(alive_loop)
            database._engines[alive_key] = (mock_engine, alive_loop)
            database._session_makers[alive_key] = mock_session_maker

            different_loop = MagicMock()
            different_loop.is_closed.return_value = False
            with (
                patch("src.database.asyncio.get_running_loop", return_value=different_loop),
                patch("src.database._create_engine", return_value=mock_new_engine),
            ):
                result = database.get_session_maker()

            assert result is not mock_session_maker
            diff_key = id(different_loop)
            assert diff_key in database._session_makers

        finally:
            alive_loop.close()
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)


class TestCloseDb:
    """Tests for close_db() function."""

    @pytest.mark.asyncio
    async def test_close_db_disposes_all_engines_and_clears(self):
        from src import database

        mock_engine_current = MagicMock()
        mock_engine_current.dispose = AsyncMock()
        mock_engine_other = MagicMock()
        mock_engine_other.dispose = AsyncMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            loop = asyncio.get_running_loop()
            loop_key = id(loop)
            database._engines.clear()
            database._session_makers.clear()
            database._engines[loop_key] = (mock_engine_current, loop)
            database._engines[999] = (mock_engine_other, None)
            database._session_makers[loop_key] = MagicMock()
            database._session_makers[999] = MagicMock()

            await database.close_db()

            mock_engine_current.dispose.assert_awaited_once()
            mock_engine_other.dispose.assert_awaited_once()
            assert len(database._engines) == 0
            assert len(database._session_makers) == 0

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    @pytest.mark.asyncio
    async def test_close_db_with_empty_engines(self):
        from src import database

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()

            await database.close_db()

            assert len(database._engines) == 0
            assert len(database._session_makers) == 0
        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    @pytest.mark.asyncio
    async def test_close_db_disposes_no_loop_key_entries(self):
        from src import database

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()
            database._engines[0] = (mock_engine, None)
            database._session_makers[0] = MagicMock()

            await database.close_db()

            mock_engine.dispose.assert_awaited_once()
            assert len(database._engines) == 0
            assert len(database._session_makers) == 0
        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)


class TestPerLoopDictBehavior:
    """Tests for per-loop dictionary engine behavior."""

    def test_same_loop_returns_same_engine(self):
        from src import database

        mock_engine = MagicMock()
        mock_loop = MagicMock()
        mock_loop.is_closed.return_value = False

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()

            with (
                patch("src.database.asyncio.get_running_loop", return_value=mock_loop),
                patch(
                    "src.database._create_engine", return_value=mock_engine
                ) as mock_create_engine,
            ):
                engine1 = database.get_engine()
                engine2 = database.get_engine()

            assert engine1 is engine2
            assert engine1 is mock_engine
            mock_create_engine.assert_called_once()

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_lazy_cleanup_removes_closed_loop_entries(self):
        from src import database

        closed_loop = asyncio.new_event_loop()
        closed_loop.close()
        stale_engine = MagicMock()

        current_loop = MagicMock()
        current_loop.is_closed.return_value = False
        new_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()
            stale_key = id(closed_loop)
            database._engines[stale_key] = (stale_engine, closed_loop)
            database._session_makers[stale_key] = MagicMock()

            with (
                patch("src.database.asyncio.get_running_loop", return_value=current_loop),
                patch("src.database._create_engine", return_value=new_engine),
            ):
                result = database.get_engine()

            assert result is new_engine
            assert stale_key not in database._engines
            assert stale_key not in database._session_makers

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_reset_clears_all_dicts(self):
        from src import database

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines[1] = (MagicMock(), None)
            database._engines[2] = (MagicMock(), None)
            database._session_makers[1] = MagicMock()
            database._session_makers[2] = MagicMock()

            database._reset_database_for_test_loop()

            assert len(database._engines) == 0
            assert len(database._session_makers) == 0

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)


class TestGetAttrCompat:
    """Tests for __getattr__ backwards compatibility shim."""

    def test_getattr_engine_returns_engine(self):
        from src import database

        mock_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()

            with patch("src.database._create_engine", return_value=mock_engine):
                result = database.engine

            assert result is mock_engine

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_getattr_async_session_maker_returns_maker(self):
        from src import database

        mock_engine = MagicMock()

        original_engines = dict(database._engines)
        original_session_makers = dict(database._session_makers)

        try:
            database._engines.clear()
            database._session_makers.clear()

            with patch("src.database._create_engine", return_value=mock_engine):
                result = database.async_session_maker

            assert result is not None
            assert 0 in database._session_makers

        finally:
            database._engines.clear()
            database._engines.update(original_engines)
            database._session_makers.clear()
            database._session_makers.update(original_session_makers)

    def test_getattr_unknown_raises_attribute_error(self):
        from src import database

        with pytest.raises(AttributeError, match="has no attribute 'nonexistent_attr'"):
            _ = database.nonexistent_attr
