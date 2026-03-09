from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import pendulum
from google.cloud import storage

from src.config import settings

logger = logging.getLogger(__name__)


def upload_scoring_snapshot(
    community_server_id: UUID,
    snapshot_data: dict[str, Any],
) -> None:
    if not settings.SCORING_HISTORY_BUCKET:
        return

    try:
        client = storage.Client()
        bucket = client.bucket(settings.SCORING_HISTORY_BUCKET)
        timestamp = pendulum.now("UTC").format("YYYY-MM-DDTHH:mm:ss") + "Z"
        blob_path = f"{community_server_id}/{timestamp}.json"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(snapshot_data, default=str),
            content_type="application/json",
        )
        logger.info(
            "Uploaded scoring snapshot to GCS",
            extra={
                "community_server_id": str(community_server_id),
                "blob_path": blob_path,
            },
        )
    except Exception:
        logger.exception(
            "Failed to upload scoring snapshot to GCS",
            extra={"community_server_id": str(community_server_id)},
        )


def list_scoring_snapshots(
    community_server_id: UUID,
) -> list[dict[str, Any]]:
    if not settings.SCORING_HISTORY_BUCKET:
        return []

    try:
        client = storage.Client()
        bucket = client.bucket(settings.SCORING_HISTORY_BUCKET)
        prefix = f"{community_server_id}/"
        blobs = bucket.list_blobs(prefix=prefix)

        snapshots: list[dict[str, Any]] = []
        for blob in blobs:
            name = blob.name
            timestamp = name.removeprefix(prefix).removesuffix(".json")
            snapshots.append(
                {
                    "timestamp": timestamp,
                    "path": name,
                    "size": blob.size,
                }
            )
        return snapshots
    except Exception:
        logger.exception(
            "Failed to list scoring snapshots from GCS",
            extra={"community_server_id": str(community_server_id)},
        )
        return []


def fetch_scoring_snapshot(
    community_server_id: UUID,
    timestamp: str,
) -> dict[str, Any] | None:
    if not settings.SCORING_HISTORY_BUCKET:
        return None

    try:
        client = storage.Client()
        bucket = client.bucket(settings.SCORING_HISTORY_BUCKET)
        blob_path = f"{community_server_id}/{timestamp}.json"
        blob = bucket.blob(blob_path)
        content = blob.download_as_text()
        return json.loads(content)
    except Exception:
        logger.exception(
            "Failed to fetch scoring snapshot from GCS",
            extra={
                "community_server_id": str(community_server_id),
                "timestamp": timestamp,
            },
        )
        return None
