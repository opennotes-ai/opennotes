import pytest
from fastapi import HTTPException

from src.auth.scrape_token import require_scrape_token
from src.config import Settings


async def test_missing_authorization_header_raises_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_scrape_token(authorization=None, settings=Settings(VIBECHECK_SCRAPE_API_TOKEN="secret"))

    assert exc_info.value.status_code == 401


async def test_wrong_bearer_token_raises_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_scrape_token(authorization="Bearer wrong", settings=Settings(VIBECHECK_SCRAPE_API_TOKEN="secret"))

    assert exc_info.value.status_code == 401


async def test_configured_bearer_token_passes() -> None:
    await require_scrape_token(
        authorization="Bearer secret",
        settings=Settings(VIBECHECK_SCRAPE_API_TOKEN="secret"),
    )


async def test_empty_configured_token_always_rejects() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_scrape_token(authorization="Bearer secret", settings=Settings())

    assert exc_info.value.status_code == 401
