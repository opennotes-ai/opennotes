"""Signed URL helper for direct PDF uploads (TASK-1498).

`POST /api/upload-pdf` needs a short-lived GCS signed PUT URL. This file
houses that storage contract so the route can stay focused on HTTP details
and dependency injection.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from src.monitoring import get_logger

logger = get_logger(__name__)


class PdfUploadStore:
    """Production-backed signer for direct PDF uploads into a GCS bucket."""

    def __init__(self, bucket_name: str) -> None:
        from google.cloud import storage  # noqa: PLC0415

        self._bucket_name = bucket_name
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)
        self._credentials: Any = None

    def signed_upload_url(self, key: str, *, ttl_seconds: int = 900) -> str | None:
        """Mint a versioned signed PUT URL for a PDF object key."""
        return self._signed_url(key, method="PUT", ttl_seconds=ttl_seconds)

    def signed_read_url(self, key: str, *, ttl_seconds: int = 900) -> str | None:
        """Mint a versioned signed GET URL for a previously uploaded PDF."""
        return self._signed_url(key, method="GET", ttl_seconds=ttl_seconds)

    def _get_credentials(self) -> Any:
        import google.auth  # noqa: PLC0415
        import google.auth.transport.requests  # noqa: PLC0415

        if self._credentials is None:
            self._credentials, _project = google.auth.default()

        creds = self._credentials
        token = getattr(creds, "token", None)
        expiry = getattr(creds, "expiry", None)
        needs_refresh = not token
        if not needs_refresh and expiry is not None:
            now = datetime.now(UTC)
            if expiry.tzinfo is None:
                expiry_aware = expiry.replace(tzinfo=UTC)
            else:
                expiry_aware = expiry
            if expiry_aware <= now + timedelta(seconds=60):
                needs_refresh = True
        if needs_refresh:
            creds.refresh(google.auth.transport.requests.Request())
        return creds

    def _signed_url(self, key: str, *, method: str, ttl_seconds: int) -> str | None:
        try:
            credentials = self._get_credentials()
            signer_email = getattr(credentials, "service_account_email", None) or getattr(
                credentials, "signer_email", None
            )
            if not signer_email:
                logger.warning(
                    "gcs pdf upload signing failed: missing service-account signer email"
                )
                return None

            blob = self._bucket.blob(key)
            kwargs = {
                "version": "v4",
                "expiration": timedelta(seconds=ttl_seconds),
                "method": method,
                "service_account_email": signer_email,
                "access_token": credentials.token,
            }
            if method == "PUT":
                kwargs["content_type"] = "application/pdf"
            return blob.generate_signed_url(**kwargs)
        except Exception as exc:
            logger.warning(
                "gcs pdf %s signing failed bucket=%s key=%s: %s",
                method.lower(),
                self._bucket_name,
                key,
                exc,
            )
            return None

    def get_metadata(self, key: str) -> dict[str, object] | None:
        """Return object metadata for a previously uploaded PDF key.

        The upload path stores the object directly in GCS; this method is
        a lightweight existence + header check before analysis starts.
        """
        try:
            blob = self._bucket.blob(key)
            blob.reload()
            return {
                "size": blob.size,
                "content_type": blob.content_type,
            }
        except Exception as exc:
            logger.warning(
                "gcs pdf metadata lookup failed bucket=%s key=%s: %s",
                self._bucket_name,
                key,
                exc,
            )
            return None


_pdf_store: PdfUploadStore | None = None
_pdf_store_bucket: str | None = None


def get_pdf_upload_store(bucket_name: str) -> PdfUploadStore:
    """Return a process-wide `PdfUploadStore` for `bucket_name`.

    The underlying `storage.Client()` performs synchronous service-account
    credential discovery on construction, so caching the instance avoids
    repeating that work on every request. A bucket-name change rebuilds
    the singleton (covers test/dev rebinds and configuration reloads).
    """
    global _pdf_store, _pdf_store_bucket
    if _pdf_store is None or _pdf_store_bucket != bucket_name:
        _pdf_store = PdfUploadStore(bucket_name)
        _pdf_store_bucket = bucket_name
    return _pdf_store
