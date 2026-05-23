from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.url_content_scan.screenshot_store import ScreenshotStore


@dataclass
class _FakeBlob:
    path: str
    uploads: dict[str, bytes]
    content_types: dict[str, str]
    deletes: list[str]

    def upload_from_string(self, value: bytes, *, content_type: str) -> None:
        self.uploads[self.path] = value
        self.content_types[self.path] = content_type

    def delete(self) -> None:
        self.deletes.append(self.path)
        self.uploads.pop(self.path, None)
        self.content_types.pop(self.path, None)


class _FakeBucket:
    def __init__(self) -> None:
        self.uploads: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self.deletes: list[str] = []

    def blob(self, path: str) -> _FakeBlob:
        return _FakeBlob(
            path=path,
            uploads=self.uploads,
            content_types=self.content_types,
            deletes=self.deletes,
        )


class _FakeStorageClient:
    def __init__(self, bucket: _FakeBucket) -> None:
        self._bucket = bucket

    def bucket(self, _name: str) -> _FakeBucket:
        return self._bucket


def _make_store() -> tuple[ScreenshotStore, _FakeBucket]:
    bucket = _FakeBucket()
    store = ScreenshotStore(
        bucket_name="url-scan-screenshots",
        storage_client=_FakeStorageClient(bucket),
    )
    return store, bucket


@pytest.mark.asyncio
async def test_upload_uses_image_png_content_type_by_default() -> None:
    store, bucket = _make_store()

    key = await store.upload("ext/shots/abc.png", b"png-bytes")

    assert key == "ext/shots/abc.png"
    assert bucket.uploads["ext/shots/abc.png"] == b"png-bytes"
    assert bucket.content_types["ext/shots/abc.png"] == "image/png"


@pytest.mark.asyncio
async def test_upload_extension_screenshot_stores_with_correct_content_type() -> None:
    store, bucket = _make_store()

    key = await store.upload("ext/shots/abc.png", b"png-bytes", content_type="image/png")

    assert key == "ext/shots/abc.png"
    assert bucket.uploads["ext/shots/abc.png"] == b"png-bytes"
    assert bucket.content_types["ext/shots/abc.png"] == "image/png"


@pytest.mark.asyncio
async def test_upload_supports_jpeg_content_type() -> None:
    store, bucket = _make_store()

    key = await store.upload("ext/shots/abc.jpg", b"jpg-bytes", content_type="image/jpeg")

    assert key == "ext/shots/abc.jpg"
    assert bucket.content_types["ext/shots/abc.jpg"] == "image/jpeg"
