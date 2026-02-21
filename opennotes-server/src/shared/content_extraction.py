import asyncio
import hashlib
import logging
import random
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import pendulum
import trafilatura

logger = logging.getLogger(__name__)

DEFAULT_BASE_DELAY = 1.0
DEFAULT_JITTER_RATIO = 0.5
DEFAULT_SCRAPE_TIMEOUT = 120

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
]


class ContentExtractionError(Exception):
    pass


@dataclass(frozen=True)
class ExtractionConfig:
    include_comments: bool = False
    include_tables: bool = True
    no_fallback: bool = False
    favor_precision: bool = True
    base_delay: float = 1.0
    jitter_ratio: float = 0.5


@dataclass
class ExtractedContent:
    text: str
    url: str
    domain: str
    extracted_at: pendulum.DateTime
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain:
            return domain
        url_hash = hashlib.sha256(url[:100].encode()).hexdigest()[:16]
        logger.warning(
            "Unable to extract domain from URL, using hash for rate limiting",
            extra={"url": url[:100], "domain_hash": url_hash},
        )
        return f"unknown-{url_hash}"
    except Exception:
        url_hash = hashlib.sha256(url[:100].encode()).hexdigest()[:16]
        logger.warning(
            "Error parsing URL, using hash for rate limiting",
            extra={"url": url[:100], "domain_hash": url_hash},
        )
        return f"unknown-{url_hash}"


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def scrape_url_content(url: str, user_agent: str | None = None) -> str | None:
    try:
        if user_agent is None:
            user_agent = get_random_user_agent()

        config = trafilatura.settings.use_config()  # pyright: ignore[reportAttributeAccessIssue]
        config.set("DEFAULT", "USER_AGENT", user_agent)

        downloaded = trafilatura.fetch_url(url, config=config)
        if not downloaded:
            logger.warning(f"Failed to download URL: {url}")
            return None

        content = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=True,
        )

        if not content:
            logger.warning(f"No content extracted from URL: {url}")
            return None

        return content.strip()

    except Exception as e:
        logger.exception(f"Error scraping URL {url}: {e}")
        return None


async def extract_content_from_url(
    url: str,
    config: ExtractionConfig | None = None,
) -> ExtractedContent:
    if config is None:
        config = ExtractionConfig()

    domain = extract_domain(url)
    user_agent = get_random_user_agent()

    jitter = random.uniform(0, config.base_delay * config.jitter_ratio)
    total_delay = config.base_delay + jitter
    await asyncio.sleep(total_delay)

    content = await asyncio.to_thread(scrape_url_content, url, user_agent)

    if not content:
        raise ContentExtractionError(f"Failed to extract content from URL: {url}")

    return ExtractedContent(
        text=content,
        url=url,
        domain=domain,
        extracted_at=pendulum.now("UTC"),
    )
