from unittest.mock import AsyncMock, patch

import pendulum
import pytest

from src.shared.content_extraction import (
    DEFAULT_BASE_DELAY,
    DEFAULT_JITTER_RATIO,
    DEFAULT_SCRAPE_TIMEOUT,
    USER_AGENTS,
    ContentExtractionError,
    ExtractedContent,
    ExtractionConfig,
    extract_content_from_url,
    extract_domain,
    get_random_user_agent,
    scrape_url_content,
)

pytestmark = pytest.mark.unit


class TestExtractionConfig:
    def test_default_values(self):
        config = ExtractionConfig()
        assert config.include_comments is False
        assert config.include_tables is True
        assert config.no_fallback is False
        assert config.favor_precision is True
        assert config.base_delay == 1.0
        assert config.jitter_ratio == 0.5

    def test_custom_values(self):
        config = ExtractionConfig(
            include_comments=True,
            include_tables=False,
            no_fallback=True,
            favor_precision=False,
            base_delay=2.0,
            jitter_ratio=0.3,
        )
        assert config.include_comments is True
        assert config.include_tables is False
        assert config.no_fallback is True
        assert config.favor_precision is False
        assert config.base_delay == 2.0
        assert config.jitter_ratio == 0.3

    def test_frozen(self):
        config = ExtractionConfig()
        with pytest.raises(AttributeError):
            config.base_delay = 5.0  # type: ignore[misc]


class TestExtractedContent:
    def test_fields(self):
        now = pendulum.now("UTC")
        content = ExtractedContent(
            text="Hello world",
            url="https://example.com",
            domain="example.com",
            extracted_at=now,
        )
        assert content.text == "Hello world"
        assert content.url == "https://example.com"
        assert content.domain == "example.com"
        assert content.extracted_at == now
        assert content.title is None
        assert content.metadata == {}

    def test_optional_fields(self):
        now = pendulum.now("UTC")
        content = ExtractedContent(
            text="Hello",
            url="https://example.com",
            domain="example.com",
            extracted_at=now,
            title="Test Title",
            metadata={"key": "value"},
        )
        assert content.title == "Test Title"
        assert content.metadata == {"key": "value"}


class TestConstants:
    def test_default_base_delay(self):
        assert DEFAULT_BASE_DELAY == 1.0

    def test_default_jitter_ratio(self):
        assert DEFAULT_JITTER_RATIO == 0.5

    def test_default_scrape_timeout(self):
        assert DEFAULT_SCRAPE_TIMEOUT == 120

    def test_user_agents_count(self):
        assert len(USER_AGENTS) >= 5

    def test_user_agents_are_modern(self):
        for ua in USER_AGENTS:
            assert "Mozilla/5.0" in ua
            assert any(browser in ua for browser in ["Chrome", "Firefox", "Safari"])


class TestExtractDomain:
    def test_simple_domain(self):
        assert extract_domain("https://example.com/page") == "example.com"

    def test_strips_www(self):
        assert extract_domain("https://www.example.com/page") == "example.com"

    def test_preserves_subdomains(self):
        assert extract_domain("https://blog.example.com/post") == "blog.example.com"

    def test_lowercases(self):
        assert extract_domain("https://EXAMPLE.COM/page") == "example.com"

    def test_port_numbers(self):
        assert extract_domain("https://example.com:8080/page") == "example.com:8080"

    def test_http_scheme(self):
        assert extract_domain("http://example.com/page") == "example.com"

    def test_path_only_returns_unknown_hash(self):
        result = extract_domain("/path/to/page")
        assert result.startswith("unknown-")

    def test_empty_string_returns_unknown_hash(self):
        result = extract_domain("")
        assert result.startswith("unknown-")

    def test_invalid_url_returns_unknown_hash(self):
        result = extract_domain("not a url")
        assert result.startswith("unknown-")

    def test_query_params_ignored(self):
        assert extract_domain("https://example.com/page?foo=bar") == "example.com"

    def test_fragment_ignored(self):
        assert extract_domain("https://example.com/page#section") == "example.com"


class TestGetRandomUserAgent:
    def test_returns_from_list(self):
        ua = get_random_user_agent()
        assert ua in USER_AGENTS

    def test_returns_string(self):
        assert isinstance(get_random_user_agent(), str)


class TestScrapeUrlContent:
    def test_returns_content_on_success(self):
        with (
            patch("src.shared.content_extraction.trafilatura.settings.use_config") as mock_config,
            patch(
                "src.shared.content_extraction.trafilatura.fetch_url",
                return_value="<html>content</html>",
            ),
            patch(
                "src.shared.content_extraction.trafilatura.extract",
                return_value="  Extracted text  ",
            ),
        ):
            mock_config.return_value.set = lambda *a: None
            result = scrape_url_content("https://example.com", user_agent="TestAgent")

        assert result == "Extracted text"

    def test_returns_none_when_fetch_fails(self):
        with (
            patch("src.shared.content_extraction.trafilatura.settings.use_config") as mock_config,
            patch(
                "src.shared.content_extraction.trafilatura.fetch_url",
                return_value=None,
            ),
        ):
            mock_config.return_value.set = lambda *a: None
            result = scrape_url_content("https://example.com")

        assert result is None

    def test_returns_none_when_extract_fails(self):
        with (
            patch("src.shared.content_extraction.trafilatura.settings.use_config") as mock_config,
            patch(
                "src.shared.content_extraction.trafilatura.fetch_url",
                return_value="<html></html>",
            ),
            patch(
                "src.shared.content_extraction.trafilatura.extract",
                return_value=None,
            ),
        ):
            mock_config.return_value.set = lambda *a: None
            result = scrape_url_content("https://example.com")

        assert result is None

    def test_returns_none_on_exception(self):
        with (
            patch("src.shared.content_extraction.trafilatura.settings.use_config") as mock_config,
            patch(
                "src.shared.content_extraction.trafilatura.fetch_url",
                side_effect=RuntimeError("Network error"),
            ),
        ):
            mock_config.return_value.set = lambda *a: None
            result = scrape_url_content("https://example.com")

        assert result is None

    def test_uses_random_agent_when_none_provided(self):
        with (
            patch("src.shared.content_extraction.trafilatura.settings.use_config") as mock_config,
            patch(
                "src.shared.content_extraction.trafilatura.fetch_url",
                return_value="<html></html>",
            ),
            patch(
                "src.shared.content_extraction.trafilatura.extract",
                return_value="text",
            ),
            patch(
                "src.shared.content_extraction.get_random_user_agent",
                return_value="RandomAgent",
            ) as mock_ua,
        ):
            config_instance = mock_config.return_value
            config_instance.set = lambda *a: None
            scrape_url_content("https://example.com")
            mock_ua.assert_called_once()


class TestExtractContentFromUrl:
    @pytest.mark.asyncio
    async def test_returns_extracted_content(self):
        with (
            patch(
                "src.shared.content_extraction.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.shared.content_extraction.random.uniform",
                return_value=0.1,
            ),
            patch(
                "src.shared.content_extraction.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="Extracted article text",
            ),
        ):
            result = await extract_content_from_url("https://example.com/article")

        assert isinstance(result, ExtractedContent)
        assert result.text == "Extracted article text"
        assert result.url == "https://example.com/article"
        assert result.domain == "example.com"
        assert isinstance(result.extracted_at, pendulum.DateTime)

    @pytest.mark.asyncio
    async def test_raises_on_failure(self):
        with (
            patch(
                "src.shared.content_extraction.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.shared.content_extraction.random.uniform",
                return_value=0.1,
            ),
            patch(
                "src.shared.content_extraction.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ContentExtractionError, match="Failed to extract content"),
        ):
            await extract_content_from_url("https://example.com/missing")

    @pytest.mark.asyncio
    async def test_applies_politeness_delay(self):
        with (
            patch(
                "src.shared.content_extraction.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            patch(
                "src.shared.content_extraction.random.uniform",
                return_value=0.25,
            ),
            patch(
                "src.shared.content_extraction.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="content",
            ),
        ):
            await extract_content_from_url("https://example.com")
            mock_sleep.assert_called_once_with(1.0 + 0.25)

    @pytest.mark.asyncio
    async def test_respects_custom_config(self):
        config = ExtractionConfig(base_delay=2.0, jitter_ratio=0.3)

        with (
            patch(
                "src.shared.content_extraction.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            patch(
                "src.shared.content_extraction.random.uniform",
                return_value=0.3,
            ) as mock_uniform,
            patch(
                "src.shared.content_extraction.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="content",
            ),
        ):
            await extract_content_from_url("https://example.com", config=config)
            mock_uniform.assert_called_once_with(0, 2.0 * 0.3)
            mock_sleep.assert_called_once_with(2.0 + 0.3)

    @pytest.mark.asyncio
    async def test_uses_random_user_agent(self):
        with (
            patch(
                "src.shared.content_extraction.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.shared.content_extraction.random.uniform",
                return_value=0.1,
            ),
            patch(
                "src.shared.content_extraction.get_random_user_agent",
                return_value="TestAgent/1.0",
            ),
            patch(
                "src.shared.content_extraction.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="content",
            ) as mock_thread,
        ):
            await extract_content_from_url("https://example.com")
            call_args = mock_thread.call_args
            assert call_args[0][2] == "TestAgent/1.0"

    @pytest.mark.asyncio
    async def test_raises_on_empty_string_content(self):
        with (
            patch(
                "src.shared.content_extraction.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.shared.content_extraction.random.uniform",
                return_value=0.1,
            ),
            patch(
                "src.shared.content_extraction.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="",
            ),
            pytest.raises(ContentExtractionError),
        ):
            await extract_content_from_url("https://example.com/empty")
