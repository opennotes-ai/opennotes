from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import google.auth
import google.auth.transport.requests
from google.cloud import storage

from src.config import settings


class ScreenshotStore:
    def __init__(
        self,
        *,
        bucket_name: str,
        storage_client: storage.Client | Any | None = None,
    ) -> None:
        if not bucket_name:
            raise ValueError("ScreenshotStore requires a non-empty bucket_name")
        self._bucket_name = bucket_name
        self._client = storage_client or storage.Client()

    @classmethod
    def from_settings(cls) -> ScreenshotStore:
        return cls(bucket_name=settings.URL_SCAN_SCREENSHOT_BUCKET)

    def _bucket(self) -> Any:
        return self._client.bucket(self._bucket_name)

    async def upload(self, storage_key: str, screenshot_bytes: bytes) -> str:
        def _upload() -> str:
            blob = self._bucket().blob(storage_key)
            blob.upload_from_string(screenshot_bytes, content_type="image/png")
            return storage_key

        return await asyncio.to_thread(_upload)

    async def delete(self, storage_key: str) -> None:
        def _delete() -> None:
            self._bucket().blob(storage_key).delete()

        await asyncio.to_thread(_delete)

    async def sign_url(self, storage_key: str, *, ttl: timedelta) -> str:
        def _sign() -> str:
            credentials, _project = google.auth.default()
            credentials.refresh(google.auth.transport.requests.Request())
            signer_email = getattr(credentials, "service_account_email", None) or getattr(
                credentials, "signer_email", None
            )
            if not signer_email:
                raise RuntimeError(
                    "GCS signed URL generation requires service-account ADC credentials"
                )
            blob = self._bucket().blob(storage_key)
            return blob.generate_signed_url(
                version="v4",
                expiration=ttl,
                method="GET",
                service_account_email=signer_email,
                access_token=credentials.token,
            )

        return await asyncio.to_thread(_sign)
