from __future__ import annotations

from io import BytesIO

import httpx
from PIL import Image

from src.x.thumbnail import materialize_og_image_png


def _image_bytes(*, image_format: str = "JPEG") -> bytes:
    image = Image.new("RGB", (2, 2), color=(200, 20, 80))
    out = BytesIO()
    image.save(out, format=image_format)
    return out.getvalue()


async def test_materialize_og_image_png_normalizes_image_response_to_png() -> None:
    jpeg = _image_bytes(image_format="JPEG")

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=jpeg, headers={"content-type": "image/jpeg"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await materialize_og_image_png("https://pbs.twimg.com/media/post.jpg", http=http)

    assert result is not None
    with Image.open(BytesIO(result)) as image:
        assert image.format == "PNG"
        assert image.size == (2, 2)


async def test_materialize_og_image_png_returns_none_for_bad_responses() -> None:
    responses = iter(
        [
            httpx.Response(404, content=b"missing", headers={"content-type": "image/jpeg"}),
            httpx.Response(200, content=b"not an image", headers={"content-type": "text/plain"}),
            httpx.Response(200, content=b"broken", headers={"content-type": "image/png"}),
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return next(responses)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        missing = await materialize_og_image_png("https://pbs.twimg.com/missing.jpg", http=http)
        wrong_type = await materialize_og_image_png("https://pbs.twimg.com/text.txt", http=http)
        corrupt = await materialize_og_image_png("https://pbs.twimg.com/corrupt.png", http=http)

    assert missing is None
    assert wrong_type is None
    assert corrupt is None


async def test_materialize_og_image_png_returns_none_for_oversized_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=b"",
            headers={"content-type": "image/jpeg", "content-length": "9000000"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await materialize_og_image_png("https://pbs.twimg.com/large.jpg", http=http)

    assert result is None
