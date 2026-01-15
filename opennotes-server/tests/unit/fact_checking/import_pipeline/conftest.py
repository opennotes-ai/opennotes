"""
Shared test helpers for import pipeline unit tests.

Provides common mock factories for settings and database sessions
used by both test_scrape_batch_job.py and test_promotion_batch_job.py.
"""

from unittest.mock import MagicMock


def create_mock_settings():
    """Create mock settings for tests."""
    settings = MagicMock()
    settings.DB_POOL_SIZE = 5
    settings.DB_POOL_MAX_OVERFLOW = 10
    settings.DB_POOL_TIMEOUT = 30
    settings.DB_POOL_RECYCLE = 1800
    return settings


class MockSessionContextManager:
    """Async context manager for mock database sessions."""

    def __init__(self, mock_db):
        self.mock_db = mock_db

    async def __aenter__(self):
        return self.mock_db

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def create_mock_session_context(mock_db):
    """
    Create a mock async session context manager that works with multiple context entries.

    Returns a mock session maker that produces MockSessionContextManager instances.
    Each call returns a fresh context manager to support multiple `async with` blocks.
    """
    mock_session_maker = MagicMock()
    mock_session_maker.side_effect = lambda: MockSessionContextManager(mock_db)
    return mock_session_maker
