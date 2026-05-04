"""Signed URL helper for direct PDF uploads (TASK-1498).

`POST /api/upload-pdf` needs a short-lived GCS signed PUT URL. This file
houses that storage contract so the route can stay focused on HTTP details
and dependency injection.
"""
from __future__ import annotations

from datetime import timedelta

from src.monitoring import get_logger

logger = get_logger(__name__)


class PdfUploadStore:
    """Production-backed signer for direct PDF uploads into a GCS bucket."""

    def __init__(self, bucket_name: str) -> None:
        from google.cloud import storage  # noqa: PLC0415

        self._bucket_name = bucket_name
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    def signed_upload_url(self, key: str, *, ttl_seconds: int = 900) -> str | None:
        """Mint a versioned signed PUT URL for a PDF object key."""
        try:
            import google.auth  # noqa: PLC0415
            import google.auth.transport.requests  # noqa: PLC0415

            credentials, _project = google.auth.default()
            credentials.refresh(google.auth.transport.requests.Request())
            signer_email = getattr(credentials, "service_account_email", None) or getattr(
                credentials, "signer_email", None
            )
            if not signer_email:
                logger.warning(
                    "gcs pdf upload signing failed: missing service-account signer email"
                )
                return None

            blob = self._bucket.blob(key)
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=ttl_seconds),
                method="PUT",
                content_type="application/pdf",
                service_account_email=signer_email,
                access_token=credentials.token,
            )
        except Exception as exc:
            logger.warning(
                "gcs pdf upload signing failed bucket=%s key=%s: %s",
                self._bucket_name,
                key,
                exc,
            )
            return None
