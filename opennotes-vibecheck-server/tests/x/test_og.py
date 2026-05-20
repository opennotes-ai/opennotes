from __future__ import annotations

import httpx

from src.x.og import fetch_x_og_image_url


async def test_fetch_x_og_image_url_returns_valid_public_image_url() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text=(
                "<html><head>"
                '<meta property="og:image" content="https://pbs.twimg.com/media/post.jpg">'
                "</head></html>"
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await fetch_x_og_image_url("https://x.com/alice/status/100", http=http)

    assert result == "https://pbs.twimg.com/media/post.jpg"
    assert requests[0].headers["user-agent"] == "Twitterbot/1.0"


async def test_fetch_x_og_image_url_resolves_relative_image_url() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='<meta name="og:image" content="/alice/status/100/photo.jpg">',
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await fetch_x_og_image_url("https://x.com/alice/status/100", http=http)

    assert result == "https://x.com/alice/status/100/photo.jpg"


async def test_fetch_x_og_image_url_returns_none_for_missing_or_private_image() -> None:
    responses = iter(
        [
            httpx.Response(200, text="<html><head></head></html>"),
            httpx.Response(
                200,
                text='<meta property="og:image" content="http://127.0.0.1/private.png">',
            ),
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return next(responses)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        missing = await fetch_x_og_image_url("https://x.com/alice/status/100", http=http)
        private = await fetch_x_og_image_url("https://x.com/alice/status/100", http=http)

    assert missing is None
    assert private is None


async def test_fetch_x_og_image_url_returns_none_for_upstream_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.ConnectError("blocked")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await fetch_x_og_image_url("https://x.com/alice/status/100", http=http)

    assert result is None
