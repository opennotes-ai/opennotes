"""Screenshot blob store abstraction (TASK-1480 follow-up).

The scrape cache writes a row to Postgres + a blob to object storage. The
two used to be coupled to Supabase (Postgres + Supabase Storage). When we
discovered the Supabase Storage bucket was missing in production we took
the opportunity to move the blob leg to GCS, which:

- Fits the rest of the platform — vibecheck-server already runs on GCP,
  is authenticated with ADC, and IAM the bucket directly to its SA.
- Removes the Supabase Storage dep entirely so we have one fewer
  bootstrap step in `docs/guides/vibecheck-deploy.md`.
- Lets us mint signed URLs through `iamcredentials.signBlob` instead of
  Supabase's PostgREST signed-URL endpoint, sidestepping the RLS surface
  that bit us in TASK-1480.

The Postgres leg stays on Supabase Supavisor; only the blob leg moved.

`ScreenshotStore` is the small contract `SupabaseScrapeCache` depends on.
`GCSScreenshotStore` is the production implementation. `InMemoryScreenshotStore`
is the deterministic test double (no GCS calls).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Protocol

from src.monitoring import get_logger

logger = get_logger(__name__)


class ScreenshotStore(Protocol):
    """Storage contract for the scrape cache's screenshot leg.

    All three methods are best-effort: failures should be logged but never
    raise — the cache treats a missing/failed blob as "no screenshot" and
    keeps the row consistent. The Postgres row is the source of truth for
    whether a key exists; the store just persists bytes.
    """

    def upload(self, key: str, data: bytes, *, content_type: str) -> bool:
        """Persist `data` at `key`. Return True on success, False on failure."""
        ...

    def signed_url(self, key: str, *, ttl_seconds: int) -> str | None:
        """Mint a time-limited GET URL for `key`. Return None on failure."""
        ...

    def delete(self, key: str) -> None:
        """Best-effort delete. Swallow errors (caller logs)."""
        ...


class GCSScreenshotStore:
    """Production screenshot store backed by Google Cloud Storage.

    Cloud Run service accounts have ADC but no private key bytes, so signed
    URL generation goes through `iamcredentials.signBlob`. The `google-cloud-
    storage` library does this transparently when `service_account_email` and
    `access_token` are passed to `generate_signed_url(version="v4", ...)`.

    The signing identity needs `roles/iam.serviceAccountTokenCreator` on
    itself (granted in infra). Without it, signing 403's at the IAM API.

    Initialization is lazy + cached so importing this module does not pull
    in the GCS client when the env var is unset (dev/test). The cached
    bucket reference and credentials live for the process lifetime.
    """

    def __init__(self, bucket_name: str) -> None:
        from google.cloud import storage  # noqa: PLC0415

        self._bucket_name = bucket_name
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    def upload(self, key: str, data: bytes, *, content_type: str) -> bool:
        try:
            blob = self._bucket.blob(key)
            blob.upload_from_string(data, content_type=content_type)
            return True
        except Exception as exc:
            logger.warning(
                "gcs screenshot upload failed bucket=%s key=%s: %s",
                self._bucket_name,
                key,
                exc,
            )
            return False

    def signed_url(self, key: str, *, ttl_seconds: int) -> str | None:
        # signBlob signs as the running SA, so credentials.signer_email is the
        # SA we authenticate as. Pass it explicitly so the library uses
        # iamcredentials.signBlob instead of demanding a private key file.
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
                    "gcs signed_url: ADC credentials have no signer email; "
                    "signing requires a service account identity"
                )
                return None
            blob = self._bucket.blob(key)
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=ttl_seconds),
                method="GET",
                service_account_email=signer_email,
                access_token=credentials.token,
            )
        except Exception as exc:
            logger.warning(
                "gcs signed_url failed bucket=%s key=%s: %s",
                self._bucket_name,
                key,
                exc,
            )
            return None

    def delete(self, key: str) -> None:
        try:
            self._bucket.blob(key).delete()
        except Exception as exc:
            logger.warning(
                "gcs delete failed bucket=%s key=%s: %s",
                self._bucket_name,
                key,
                exc,
            )


class InMemoryScreenshotStore:
    """Deterministic in-memory store for tests.

    Mirrors the GCS store's success/failure surface without touching the
    network. Tracks calls so tests can assert what the cache asked for.
    """

    def __init__(self) -> None:
        self.uploads: dict[str, bytes] = {}
        self.upload_calls: list[tuple[str, bytes, str]] = []
        self.signed_calls: list[tuple[str, int]] = []
        self.delete_calls: list[str] = []

    def upload(self, key: str, data: bytes, *, content_type: str) -> bool:
        self.upload_calls.append((key, data, content_type))
        self.uploads[key] = data
        return True

    def signed_url(self, key: str, *, ttl_seconds: int) -> str | None:
        self.signed_calls.append((key, ttl_seconds))
        if key not in self.uploads:
            return None
        return f"https://storage.googleapis.com/test/{key}?X-Goog-Expires={ttl_seconds}"

    def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        self.uploads.pop(key, None)
