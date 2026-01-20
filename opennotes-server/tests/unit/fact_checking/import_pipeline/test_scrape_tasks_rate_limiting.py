"""
Unit tests for scrape_tasks rate limiting functionality.

Task: task-1015 - Rate-limit fact check scraping by domain

Tests cover:
- Domain extraction from URLs
- User agent rotation
- fetch_url_content rate-limited task
- Updated scrape_candidate_content with fetch_url_content dispatch
"""

import pytest

from src.fact_checking.import_pipeline.scrape_tasks import (
    DEFAULT_BASE_DELAY,
    USER_AGENTS,
    extract_domain,
    get_random_user_agent,
)

pytestmark = pytest.mark.unit


class TestExtractDomain:
    """Test domain extraction utility."""

    def test_extracts_simple_domain(self):
        """Extracts domain from simple URL."""
        assert extract_domain("https://example.com/page") == "example.com"

    def test_strips_www_prefix(self):
        """Strips www. prefix for normalization."""
        assert extract_domain("https://www.example.com/page") == "example.com"

    def test_handles_subdomains(self):
        """Preserves subdomains (except www)."""
        assert extract_domain("https://blog.example.com/post") == "blog.example.com"

    def test_lowercases_domain(self):
        """Normalizes domain to lowercase."""
        assert extract_domain("https://EXAMPLE.COM/page") == "example.com"

    def test_handles_port_numbers(self):
        """Includes port in domain if present."""
        assert extract_domain("https://example.com:8080/page") == "example.com:8080"

    def test_handles_http_scheme(self):
        """Works with http:// URLs."""
        assert extract_domain("http://example.com/page") == "example.com"

    def test_handles_path_only(self):
        """Returns unknown for path-only URLs."""
        assert extract_domain("/path/to/page") == "unknown"

    def test_handles_empty_string(self):
        """Returns unknown for empty string."""
        assert extract_domain("") == "unknown"

    def test_handles_invalid_url(self):
        """Returns unknown for invalid URLs."""
        assert extract_domain("not a url") == "unknown"

    def test_handles_url_with_query_params(self):
        """Extracts domain ignoring query parameters."""
        assert extract_domain("https://example.com/page?foo=bar") == "example.com"

    def test_handles_url_with_fragment(self):
        """Extracts domain ignoring fragment."""
        assert extract_domain("https://example.com/page#section") == "example.com"


class TestGetRandomUserAgent:
    """Test user agent rotation."""

    def test_returns_user_agent_from_list(self):
        """Returns a user agent from the predefined list."""
        user_agent = get_random_user_agent()
        assert user_agent in USER_AGENTS

    def test_returns_string(self):
        """Returns a string."""
        user_agent = get_random_user_agent()
        assert isinstance(user_agent, str)

    def test_user_agents_are_modern(self):
        """User agents contain modern browser identifiers."""
        for ua in USER_AGENTS:
            assert "Mozilla/5.0" in ua
            assert any(browser in ua for browser in ["Chrome", "Firefox", "Safari"])


class TestUserAgentList:
    """Test the USER_AGENTS constant."""

    def test_has_multiple_user_agents(self):
        """Has multiple user agents for rotation."""
        assert len(USER_AGENTS) >= 5

    def test_all_user_agents_are_non_empty(self):
        """All user agents are non-empty strings."""
        for ua in USER_AGENTS:
            assert isinstance(ua, str)
            assert len(ua) > 0


class TestDefaultConstants:
    """Test default configuration constants."""

    def test_default_base_delay_is_one_second(self):
        """Default base delay is 1 second."""
        assert DEFAULT_BASE_DELAY == 1.0


class TestFetchUrlContentTaskRegistration:
    """Test fetch_url_content task is properly registered with rate limiting."""

    def test_fetch_url_content_task_has_rate_limit_labels(self):
        """Verify fetch_url_content task has correct rate limit labels."""
        import src.fact_checking.import_pipeline.scrape_tasks  # noqa: F401
        from src.tasks.broker import get_registered_tasks

        registered_tasks = get_registered_tasks()
        assert "fact_check:fetch_url_content" in registered_tasks

        _, labels = registered_tasks["fact_check:fetch_url_content"]
        assert labels.get("rate_limit_name") == "scrape:domain:{domain}"
        assert labels.get("rate_limit_capacity") == "1"
        assert labels.get("component") == "import_pipeline"
        assert labels.get("task_type") == "scrape"
