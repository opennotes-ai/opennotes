"""GCS storage helper for PDF and image uploads.

Provides signed PUT URLs for direct browser/client uploads and metadata
lookup. Mirrors the vibecheck-server `pdf_storage.py` pattern but adapted
to use google-cloud-storage directly.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any

import google.auth
import google.auth.transport.requests
from google.cloud import storage


class PdfUploadStore:
    def __init__(
        self,
        *,
        bucket_name: str,
        storage_client: storage.Client | Any | None = None,
    ) -> None:
        if not bucket_name:
            raise ValueError("PdfUploadStore requires a non-empty bucket_name")
        self._bucket_name = bucket_name
        self._client = storage_client or storage.Client()

    def _bucket(self) -> Any:
        return self._client.bucket(self._bucket_name)

    async def signed_upload_url(
        self,
        object_key: str,
        *,
        ttl_seconds: int = 900,
        content_type: str | None = None,
    ) -> str:
        def _sign() -> str:
            credentials, _project = google.auth.default()
            credentials.refresh(google.auth.transport.requests.Request())
            signer_email = getattr(credentials, "service_account_email", None) or getattr(
                credentials, "signer_email", None
            )
            if not signer_email:
                raise RuntimeError(
                    "No service account email found in credentials; "
                    "Workload Identity or ADC with a service account is required."
                )
            blob = self._bucket().blob(object_key)
            expiration = datetime.timedelta(seconds=ttl_seconds)
            kwargs: dict[str, Any] = {
                "expiration": expiration,
                "method": "PUT",
                "version": "v4",
                "service_account_email": signer_email,
                "access_token": credentials.token,
            }
            if content_type:
                kwargs["content_type"] = content_type
            return blob.generate_signed_url(**kwargs)

        return await asyncio.to_thread(_sign)

    async def get_metadata(self, object_key: str) -> dict[str, Any] | None:
        def _get() -> dict[str, Any] | None:
            blob = self._bucket().blob(object_key)
            try:
                blob.reload()
            except Exception:
                return None
            return {
                "size": blob.size,
                "content_type": blob.content_type,
                "updated": blob.updated,
            }

        return await asyncio.to_thread(_get)

    async def read_bytes(self, object_key: str) -> bytes:
        def _read() -> bytes:
            blob = self._bucket().blob(object_key)
            return blob.download_as_bytes()

        return await asyncio.to_thread(_read)

    async def write_bytes(
        self,
        object_key: str,
        data: bytes,
        *,
        content_type: str = "application/pdf",
    ) -> None:
        def _write() -> None:
            blob = self._bucket().blob(object_key)
            blob.upload_from_string(data, content_type=content_type)

        await asyncio.to_thread(_write)
