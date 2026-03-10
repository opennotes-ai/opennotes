"""Tests for src/notes/backfill_titles.py."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def setup_database():
    """Override autouse database fixture - unit tests don't need database."""
    return


@pytest.fixture(autouse=True)
def mock_external_services():
    """Override autouse mock fixture - unit tests don't need external services."""
    return


class TestFetchTitle:
    """Tests for fetch_title with special characters and edge cases."""

    @patch("src.notes.backfill_titles.extract_metadata")
    @patch("src.notes.backfill_titles.trafilatura")
    def test_returns_title_on_success(self, mock_traf, mock_extract):
        from src.notes.backfill_titles import fetch_title

        mock_traf.fetch_url.return_value = "<html>content</html>"
        mock_meta = MagicMock()
        mock_meta.title = "Simple Title"
        mock_extract.return_value = mock_meta

        result = fetch_title("https://example.com")
        assert result == "Simple Title"

    @patch("src.notes.backfill_titles.extract_metadata")
    @patch("src.notes.backfill_titles.trafilatura")
    def test_title_with_double_quotes(self, mock_traf, mock_extract):
        from src.notes.backfill_titles import fetch_title

        mock_traf.fetch_url.return_value = "<html>content</html>"
        mock_meta = MagicMock()
        mock_meta.title = 'He said "hello" to them'
        mock_extract.return_value = mock_meta

        result = fetch_title("https://example.com")
        assert result == 'He said "hello" to them'

    @patch("src.notes.backfill_titles.extract_metadata")
    @patch("src.notes.backfill_titles.trafilatura")
    def test_title_with_backslashes(self, mock_traf, mock_extract):
        from src.notes.backfill_titles import fetch_title

        mock_traf.fetch_url.return_value = "<html>content</html>"
        mock_meta = MagicMock()
        mock_meta.title = "path\\to\\file"
        mock_extract.return_value = mock_meta

        result = fetch_title("https://example.com")
        assert result == "path\\to\\file"

    @patch("src.notes.backfill_titles.extract_metadata")
    @patch("src.notes.backfill_titles.trafilatura")
    def test_title_with_unicode(self, mock_traf, mock_extract):
        from src.notes.backfill_titles import fetch_title

        mock_traf.fetch_url.return_value = "<html>content</html>"
        mock_meta = MagicMock()
        mock_meta.title = "日本語タイトル — «résumé»"
        mock_extract.return_value = mock_meta

        result = fetch_title("https://example.com")
        assert result == "日本語タイトル — «résumé»"

    @patch("src.notes.backfill_titles.extract_metadata")
    @patch("src.notes.backfill_titles.trafilatura")
    def test_title_with_newlines_and_tabs(self, mock_traf, mock_extract):
        from src.notes.backfill_titles import fetch_title

        mock_traf.fetch_url.return_value = "<html>content</html>"
        mock_meta = MagicMock()
        mock_meta.title = "Line1\nLine2\tTabbed"
        mock_extract.return_value = mock_meta

        result = fetch_title("https://example.com")
        assert result == "Line1\nLine2\tTabbed"

    @patch("src.notes.backfill_titles.trafilatura")
    def test_returns_none_on_download_failure(self, mock_traf):
        from src.notes.backfill_titles import fetch_title

        mock_traf.fetch_url.return_value = None

        result = fetch_title("https://example.com/notfound")
        assert result is None

    @patch("src.notes.backfill_titles.extract_metadata")
    @patch("src.notes.backfill_titles.trafilatura")
    def test_returns_none_when_no_metadata(self, mock_traf, mock_extract):
        from src.notes.backfill_titles import fetch_title

        mock_traf.fetch_url.return_value = "<html>content</html>"
        mock_extract.return_value = None

        result = fetch_title("https://example.com")
        assert result is None

    @patch("src.notes.backfill_titles.extract_metadata")
    @patch("src.notes.backfill_titles.trafilatura")
    def test_returns_none_when_title_empty(self, mock_traf, mock_extract):
        from src.notes.backfill_titles import fetch_title

        mock_traf.fetch_url.return_value = "<html>content</html>"
        mock_meta = MagicMock()
        mock_meta.title = ""
        mock_extract.return_value = mock_meta

        result = fetch_title("https://example.com")
        assert result is None

    @patch("src.notes.backfill_titles.trafilatura")
    def test_returns_none_on_exception(self, mock_traf):
        from src.notes.backfill_titles import fetch_title

        mock_traf.fetch_url.side_effect = ConnectionError("network error")

        result = fetch_title("https://example.com")
        assert result is None


class TestJsonEscaping:
    """Verify json.dumps produces correct JSONB-safe values for edge cases."""

    def test_simple_title(self):
        title = "Hello World"
        result = json.dumps(title)
        assert result == '"Hello World"'

    def test_title_with_double_quotes(self):
        title = 'He said "hello"'
        result = json.dumps(title)
        assert result == '"He said \\"hello\\""'
        assert json.loads(result) == title

    def test_title_with_backslash(self):
        title = "C:\\Users\\test"
        result = json.dumps(title)
        assert result == '"C:\\\\Users\\\\test"'
        assert json.loads(result) == title

    def test_title_with_single_quotes(self):
        title = "it's a test"
        result = json.dumps(title)
        assert result == '"it\'s a test"'
        assert json.loads(result) == title

    def test_title_with_newlines(self):
        title = "line1\nline2"
        result = json.dumps(title)
        assert json.loads(result) == title

    def test_title_with_null_bytes(self):
        title = "before\x00after"
        result = json.dumps(title)
        assert json.loads(result) == title

    def test_old_fstring_bug_with_quotes(self):
        title = 'He said "hello"'
        old_result = f'"{title}"'
        assert old_result == '"He said "hello""'
        with pytest.raises(json.JSONDecodeError):
            json.loads(old_result)

        new_result = json.dumps(title)
        parsed = json.loads(new_result)
        assert parsed == title

    def test_old_fstring_bug_with_backslash(self):
        title = "path\\to\\file"
        old_result = f'"{title}"'
        assert old_result == '"path\\to\\file"'

        new_result = json.dumps(title)
        parsed = json.loads(new_result)
        assert parsed == title


class TestFetchTitleAsync:
    """Tests for the async wrapper around fetch_title."""

    @pytest.mark.asyncio
    @patch("src.notes.backfill_titles.fetch_title")
    async def test_returns_title(self, mock_fetch):
        from src.notes.backfill_titles import fetch_title_async

        mock_fetch.return_value = "Async Title"

        result = await fetch_title_async("https://example.com")
        assert result == "Async Title"

    @pytest.mark.asyncio
    @patch("src.notes.backfill_titles.fetch_title")
    async def test_returns_none_on_timeout(self, mock_fetch):
        import asyncio

        from src.notes.backfill_titles import fetch_title_async

        async def slow_fetch(*_args):  # pyright: ignore[reportUnknownParameterType]
            await asyncio.sleep(100)

        mock_fetch.side_effect = lambda *_a: asyncio.get_event_loop().run_until_complete(
            slow_fetch()
        )

        with patch("src.notes.backfill_titles.FETCH_TIMEOUT", 0.01):
            result = await fetch_title_async("https://example.com")
        assert result is None

    @pytest.mark.asyncio
    @patch("src.notes.backfill_titles.fetch_title")
    async def test_returns_none_on_exception(self, mock_fetch):
        from src.notes.backfill_titles import fetch_title_async

        mock_fetch.side_effect = RuntimeError("boom")

        result = await fetch_title_async("https://example.com")
        assert result is None


class TestBuildCandidatesQuery:
    """Tests for the _build_candidates_query helper."""

    def test_query_includes_limit(self):
        from src.notes.backfill_titles import BATCH_SIZE, _build_candidates_query

        stmt = _build_candidates_query()
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert f"LIMIT {BATCH_SIZE}" in compiled

    def test_query_with_last_id_adds_filter(self):
        from src.notes.backfill_titles import _build_candidates_query

        test_id = uuid4()
        stmt = _build_candidates_query(last_id=test_id)
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "message_archive.id >" in compiled

    def test_query_filters_missing_title_in_sql(self):
        from src.notes.backfill_titles import _build_candidates_query

        stmt = _build_candidates_query()
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "has_key" in compiled.lower() or "?" in compiled
        assert "title" in compiled

    def test_query_orders_by_id(self):
        from src.notes.backfill_titles import _build_candidates_query

        stmt = _build_candidates_query()
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY" in compiled


class TestBackfill:
    """Integration-style tests for the backfill function with mocked DB."""

    @pytest.mark.asyncio
    @patch("src.notes.backfill_titles.close_db", new_callable=AsyncMock)
    @patch("src.notes.backfill_titles.get_session_maker")
    @patch("src.notes.backfill_titles.fetch_title_async", new_callable=AsyncMock)
    async def test_backfill_updates_records(self, mock_fetch, mock_gsm, mock_close):
        from src.notes.backfill_titles import backfill

        archive_id = uuid4()
        mock_fetch.return_value = "Fetched Title"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = archive_id
        mock_row.message_metadata = {"source_url": "https://example.com"}

        mock_result.all.return_value = [mock_row]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        call_count = 0

        class FakeSessionMaker:
            def __call__(self):
                return self

            async def __aenter__(self):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    mock_result.all.return_value = [mock_row]
                elif call_count == 3:
                    mock_result.all.return_value = []
                return mock_session

            async def __aexit__(self, *_args):  # pyright: ignore[reportUnknownParameterType]
                pass

        mock_gsm.return_value = FakeSessionMaker()

        await backfill()

        assert mock_session.execute.call_count >= 2
        assert mock_session.commit.call_count >= 1
        mock_close.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.notes.backfill_titles.close_db", new_callable=AsyncMock)
    @patch("src.notes.backfill_titles.get_session_maker")
    async def test_backfill_no_candidates(self, mock_gsm, mock_close):
        from src.notes.backfill_titles import backfill

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        class FakeSessionMaker:
            def __call__(self):
                return self

            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *_args):  # pyright: ignore[reportUnknownParameterType]
                pass

        mock_gsm.return_value = FakeSessionMaker()

        await backfill()

        mock_close.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.notes.backfill_titles.close_db", new_callable=AsyncMock)
    @patch("src.notes.backfill_titles.get_session_maker")
    @patch("src.notes.backfill_titles.fetch_title_async", new_callable=AsyncMock)
    async def test_backfill_handles_db_error_gracefully(self, mock_fetch, mock_gsm, mock_close):
        from src.notes.backfill_titles import backfill

        archive_id = uuid4()
        mock_fetch.return_value = "Title"

        call_count = 0

        mock_session_read = AsyncMock()
        mock_session_write = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = archive_id
        mock_row.message_metadata = {"source_url": "https://example.com"}

        mock_session_write.execute = AsyncMock(side_effect=RuntimeError("DB connection lost"))

        class FakeSessionMaker:
            def __call__(self):
                return self

            async def __aenter__(self):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    mock_result.all.return_value = [mock_row]
                    return mock_session_read
                if call_count == 2:
                    return mock_session_write
                mock_result.all.return_value = []
                return mock_session_read

            async def __aexit__(self, *_args):  # pyright: ignore[reportUnknownParameterType]
                pass

        mock_session_read.execute = AsyncMock(return_value=mock_result)
        mock_gsm.return_value = FakeSessionMaker()

        await backfill()

        mock_close.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.notes.backfill_titles.close_db", new_callable=AsyncMock)
    @patch("src.notes.backfill_titles.get_session_maker")
    @patch("src.notes.backfill_titles.fetch_title_async", new_callable=AsyncMock)
    async def test_backfill_uses_json_dumps_for_title(self, mock_fetch, mock_gsm, _mock_close):
        from src.notes.backfill_titles import backfill

        archive_id = uuid4()
        title_with_quotes = 'He said "hello"'
        mock_fetch.return_value = title_with_quotes

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = archive_id
        mock_row.message_metadata = {"source_url": "https://example.com"}

        call_count = 0

        class FakeSessionMaker:
            def __call__(self):
                return self

            async def __aenter__(self):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    mock_result.all.return_value = [mock_row]
                elif call_count == 3:
                    mock_result.all.return_value = []
                return mock_session

            async def __aexit__(self, *_args):  # pyright: ignore[reportUnknownParameterType]
                pass

        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_gsm.return_value = FakeSessionMaker()

        await backfill()

        update_calls = [
            c
            for c in mock_session.execute.call_args_list
            if len(c.args) >= 2 and isinstance(c.args[1], dict) and "title" in c.args[1]
        ]
        assert len(update_calls) >= 1
        title_param = update_calls[0].args[1]["title"]
        assert title_param == json.dumps(title_with_quotes)
        assert json.loads(title_param) == title_with_quotes


class TestBackfillIdempotency:
    """Verify that records with existing titles are not re-processed."""

    def test_sql_filter_excludes_existing_titles(self):
        from src.notes.backfill_titles import _build_candidates_query

        stmt = _build_candidates_query()
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "title" in compiled.lower()
        assert "has_key" in compiled.lower() or "?" in compiled
