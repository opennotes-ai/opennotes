from __future__ import annotations

from io import BytesIO

import httpx
from PIL import Image, UnidentifiedImageError

from src.monitoring import get_logger

logger = get_logger(__name__)

_MAX_OG_IMAGE_BYTES = 5 * 1024 * 1024


async def _download_image_bytes(
    image_url: str,
    *,
    http: httpx.AsyncClient,
) -> bytes | None:
    try:
        response = await http.get(image_url)
    except httpx.HTTPError as exc:
        logger.debug("x og image download failed for %s: %s", image_url, exc)
        return None
    if response.status_code >= 400:
        logger.debug(
            "x og image download failed for %s: status=%s",
            image_url,
            response.status_code,
        )
        return None

    content_length = response.headers.get("content-length")
    if (
        content_length
        and content_length.isdigit()
        and int(content_length) > _MAX_OG_IMAGE_BYTES
    ):
        return None

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type and not content_type.startswith("image/"):
        return None

    data = response.content
    if len(data) > _MAX_OG_IMAGE_BYTES:
        return None
    return data


async def materialize_og_image_png(
    image_url: str,
    *,
    http: httpx.AsyncClient,
) -> bytes | None:
    """Download a validated og:image asset and normalize it to PNG bytes."""
    data = await _download_image_bytes(image_url, http=http)
    if data is None:
        return None
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            normalized = image.convert(
                "RGBA" if image.mode in {"LA", "P", "RGBA"} else "RGB"
            )
            out = BytesIO()
            normalized.save(out, format="PNG")
    except (OSError, UnidentifiedImageError):
        return None
    return out.getvalue()
