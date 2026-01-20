"""
Unit tests for scrape_tasks rate limiting functionality.

Task: task-1015 - Rate-limit fact check scraping by domain

Tests cover:
- Domain extraction from URLs
- User agent rotation
- fetch_url_content rate-limited task
- Updated scrape_candidate_content with fetch_url_content dispatch
- Delay/jitter behavior tests
- Error handling and timeout cases
- Integration test for dispatch via kiq()/wait_result()
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.fact_checking.import_pipeline.scrape_tasks import (
    DEFAULT_BASE_DELAY,
    DEFAULT_JITTER_RATIO,
    USER_AGENTS,
    extract_domain,
    fetch_url_content,
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
        """Returns unknown-hash for path-only URLs to avoid bucket conflation."""
        result = extract_domain("/path/to/page")
        assert result.startswith("unknown-")
        assert len(result) > len("unknown-")

    def test_handles_empty_string(self):
        """Returns unknown-hash for empty string."""
        result = extract_domain("")
        assert result.startswith("unknown-")

    def test_handles_invalid_url(self):
        """Returns unknown-hash for invalid URLs."""
        result = extract_domain("not a url")
        assert result.startswith("unknown-")

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


class TestExtractDomainEdgeCases:
    """Test extract_domain with edge case URLs."""

    def test_url_with_basic_auth(self):
        """Extracts domain from URL with username:password authentication."""
        result = extract_domain("https://user:pass@example.com/page")
        assert result == "user:pass@example.com"

    def test_url_with_username_only(self):
        """Extracts domain from URL with username only."""
        result = extract_domain("https://user@example.com/page")
        assert result == "user@example.com"

    def test_ipv4_address(self):
        """Extracts IPv4 address as domain."""
        result = extract_domain("http://192.168.1.1/path")
        assert result == "192.168.1.1"

    def test_ipv4_address_with_port(self):
        """Extracts IPv4 address with port."""
        result = extract_domain("http://192.168.1.1:8080/path")
        assert result == "192.168.1.1:8080"

    def test_ipv6_address_bracketed(self):
        """Extracts bracketed IPv6 address."""
        result = extract_domain("http://[::1]/path")
        assert result == "[::1]"

    def test_ipv6_address_full(self):
        """Extracts full IPv6 address."""
        result = extract_domain("http://[2001:db8::1]:8080/path")
        assert result == "[2001:db8::1]:8080"

    def test_internationalized_domain_ascii(self):
        """Extracts ASCII-encoded internationalized domain."""
        result = extract_domain("https://xn--e1afmkfd.xn--p1ai/page")
        assert result == "xn--e1afmkfd.xn--p1ai"

    def test_internationalized_domain_unicode(self):
        """Extracts Unicode internationalized domain."""
        result = extract_domain("https://münchen.example/page")
        assert result == "münchen.example"

    def test_ftp_scheme(self):
        """Extracts domain from FTP URL."""
        result = extract_domain("ftp://files.example.com/download")
        assert result == "files.example.com"


class TestFetchUrlContentDelayBehavior:
    """Test fetch_url_content actual delay/jitter behavior."""

    @pytest.mark.asyncio
    async def test_applies_base_delay_with_jitter(self):
        """Verifies asyncio.sleep is called with base_delay + jitter."""
        fixed_jitter = 0.25

        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.random.uniform",
                return_value=fixed_jitter,
            ) as mock_uniform,
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.scrape_url_content",
                return_value="test content",
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="test content",
            ),
        ):
            await fetch_url_content(
                url="https://example.com/page",
                domain="example.com",
                base_delay=1.0,
            )

            mock_uniform.assert_called_once_with(0, 1.0 * DEFAULT_JITTER_RATIO)
            mock_sleep.assert_called_once_with(1.0 + fixed_jitter)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("base_delay", [0.1, 1.0, 5.0])
    async def test_applies_different_base_delays(self, base_delay: float):
        """Verifies different base_delay values are applied correctly."""
        fixed_jitter = 0.1

        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.random.uniform",
                return_value=fixed_jitter,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="content",
            ),
        ):
            await fetch_url_content(
                url="https://example.com",
                domain="example.com",
                base_delay=base_delay,
            )

            expected_delay = base_delay + fixed_jitter
            mock_sleep.assert_called_once_with(expected_delay)

    @pytest.mark.asyncio
    async def test_jitter_range_is_correct(self):
        """Verifies random.uniform is called with correct jitter range."""
        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.random.uniform",
                return_value=0.2,
            ) as mock_uniform,
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="content",
            ),
        ):
            await fetch_url_content(
                url="https://example.com",
                domain="example.com",
                base_delay=1.0,
            )

            mock_uniform.assert_called_once_with(0, 1.0 * DEFAULT_JITTER_RATIO)

    @pytest.mark.asyncio
    async def test_zero_base_delay_still_applies_jitter(self):
        """Verifies that even with zero base delay, jitter is still applied."""
        fixed_jitter = 0.3

        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.random.uniform",
                return_value=fixed_jitter,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="content",
            ),
        ):
            await fetch_url_content(
                url="https://example.com",
                domain="example.com",
                base_delay=0.0,
            )

            mock_sleep.assert_called_once_with(fixed_jitter)


class TestFetchUrlContentErrorHandling:
    """Test fetch_url_content error handling and return values."""

    @pytest.mark.asyncio
    async def test_returns_content_on_success(self):
        """Returns dict with content key on successful extraction."""
        expected_content = "This is the extracted article content."

        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.random.uniform",
                return_value=0.1,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=expected_content,
            ),
        ):
            result = await fetch_url_content(
                url="https://example.com/article",
                domain="example.com",
                base_delay=0.1,
            )

            assert result == {"content": expected_content}

    @pytest.mark.asyncio
    async def test_returns_error_when_scrape_returns_none(self):
        """Returns dict with error key when scrape_url_content returns None."""
        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.random.uniform",
                return_value=0.1,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await fetch_url_content(
                url="https://example.com/missing",
                domain="example.com",
                base_delay=0.1,
            )

            assert "error" in result
            assert "Failed to extract content" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_error_when_scrape_returns_empty_string(self):
        """Returns error when scrape_url_content returns empty string (falsy)."""
        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.random.uniform",
                return_value=0.1,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="",
            ),
        ):
            result = await fetch_url_content(
                url="https://example.com/empty",
                domain="example.com",
                base_delay=0.1,
            )

            assert "error" in result

    @pytest.mark.asyncio
    async def test_uses_random_user_agent(self):
        """Verifies get_random_user_agent is called for each request."""
        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.random.uniform",
                return_value=0.1,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.get_random_user_agent",
                return_value="Mozilla/5.0 Test Agent",
            ) as mock_ua,
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="content",
            ) as mock_thread,
        ):
            await fetch_url_content(
                url="https://example.com",
                domain="example.com",
            )

            mock_ua.assert_called_once()
            call_args = mock_thread.call_args
            # asyncio.to_thread(scrape_url_content, url, user_agent) - user_agent is third arg (index 2)
            assert call_args[0][2] == "Mozilla/5.0 Test Agent"


class TestScrapeCandidateContentDispatch:
    """Test scrape_candidate_content dispatches to fetch_url_content via kiq()."""

    @pytest.mark.asyncio
    async def test_dispatches_fetch_url_content_with_correct_params(self):
        """Verifies kiq() is called with correct url, domain, and base_delay."""
        from uuid import uuid4

        from src.fact_checking.candidate_models import CandidateStatus

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.status = CandidateStatus.PENDING.value
        mock_candidate.content = None
        mock_candidate.source_url = "https://news.example.com/article/123"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_candidate
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_task_handle = AsyncMock()
        mock_task_result = MagicMock()
        mock_task_result.return_value = {"content": "Article content here"}
        mock_task_handle.wait_result = AsyncMock(return_value=mock_task_result)

        async def mock_get_db():
            yield mock_session

        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.get_db",
                mock_get_db,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.fetch_url_content"
            ) as mock_fetch_task,
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.promote_candidate",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_fetch_task.kiq = AsyncMock(return_value=mock_task_handle)

            from src.fact_checking.import_pipeline.scrape_tasks import (
                scrape_candidate_content,
            )

            await scrape_candidate_content(
                candidate_id=str(candidate_id),
                auto_promote=True,
                base_delay=2.0,
            )

            mock_fetch_task.kiq.assert_called_once_with(
                url="https://news.example.com/article/123",
                domain="news.example.com",
                base_delay=2.0,
            )

    @pytest.mark.asyncio
    async def test_wait_result_called_with_timeout(self):
        """Verifies wait_result() is called with expected timeout."""
        from uuid import uuid4

        from src.fact_checking.candidate_models import CandidateStatus

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.status = CandidateStatus.PENDING.value
        mock_candidate.content = None
        mock_candidate.source_url = "https://example.com/page"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_candidate
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_task_handle = AsyncMock()
        mock_task_result = MagicMock()
        mock_task_result.return_value = {"content": "content"}
        mock_task_handle.wait_result = AsyncMock(return_value=mock_task_result)

        async def mock_get_db():
            yield mock_session

        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.get_db",
                mock_get_db,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.fetch_url_content"
            ) as mock_fetch_task,
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.promote_candidate",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_fetch_task.kiq = AsyncMock(return_value=mock_task_handle)

            from src.fact_checking.import_pipeline.scrape_tasks import (
                scrape_candidate_content,
            )

            await scrape_candidate_content(candidate_id=str(candidate_id))

            mock_task_handle.wait_result.assert_called_once_with(timeout=120)

    @pytest.mark.asyncio
    async def test_handles_successful_fetch_result(self):
        """Updates candidate status to SCRAPED on successful fetch."""
        from uuid import uuid4

        from src.fact_checking.candidate_models import CandidateStatus

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.status = CandidateStatus.PENDING.value
        mock_candidate.content = None
        mock_candidate.source_url = "https://example.com/article"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_candidate
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_task_handle = AsyncMock()
        mock_task_result = MagicMock()
        mock_task_result.return_value = {"content": "Scraped article content"}
        mock_task_handle.wait_result = AsyncMock(return_value=mock_task_result)

        async def mock_get_db():
            yield mock_session

        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.get_db",
                mock_get_db,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.fetch_url_content"
            ) as mock_fetch_task,
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.promote_candidate",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_fetch_task.kiq = AsyncMock(return_value=mock_task_handle)

            from src.fact_checking.import_pipeline.scrape_tasks import (
                scrape_candidate_content,
            )

            result = await scrape_candidate_content(
                candidate_id=str(candidate_id),
                auto_promote=False,
            )

            assert result["status"] == "scraped"
            assert result["content_length"] == len("Scraped article content")

    @pytest.mark.asyncio
    async def test_handles_failed_fetch_result(self):
        """Updates candidate status to SCRAPE_FAILED when fetch fails."""
        from uuid import uuid4

        from src.fact_checking.candidate_models import CandidateStatus

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.status = CandidateStatus.PENDING.value
        mock_candidate.content = None
        mock_candidate.source_url = "https://example.com/broken"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_candidate
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_task_handle = AsyncMock()
        mock_task_result = MagicMock()
        mock_task_result.return_value = {"error": "Failed to extract content from URL"}
        mock_task_handle.wait_result = AsyncMock(return_value=mock_task_result)

        async def mock_get_db():
            yield mock_session

        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.get_db",
                mock_get_db,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.fetch_url_content"
            ) as mock_fetch_task,
        ):
            mock_fetch_task.kiq = AsyncMock(return_value=mock_task_handle)

            from src.fact_checking.import_pipeline.scrape_tasks import (
                scrape_candidate_content,
            )

            result = await scrape_candidate_content(candidate_id=str(candidate_id))

            assert result["status"] == "scrape_failed"
            assert "message" in result

    @pytest.mark.asyncio
    async def test_handles_none_return_value(self):
        """Handles case where wait_result returns None return_value."""
        from uuid import uuid4

        from src.fact_checking.candidate_models import CandidateStatus

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.status = CandidateStatus.PENDING.value
        mock_candidate.content = None
        mock_candidate.source_url = "https://example.com/timeout"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_candidate
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_task_handle = AsyncMock()
        mock_task_result = MagicMock()
        mock_task_result.return_value = None
        mock_task_handle.wait_result = AsyncMock(return_value=mock_task_result)

        async def mock_get_db():
            yield mock_session

        with (
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.get_db",
                mock_get_db,
            ),
            patch(
                "src.fact_checking.import_pipeline.scrape_tasks.fetch_url_content"
            ) as mock_fetch_task,
        ):
            mock_fetch_task.kiq = AsyncMock(return_value=mock_task_handle)

            from src.fact_checking.import_pipeline.scrape_tasks import (
                scrape_candidate_content,
            )

            result = await scrape_candidate_content(candidate_id=str(candidate_id))

            assert result["status"] == "scrape_failed"
