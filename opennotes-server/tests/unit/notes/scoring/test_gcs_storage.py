from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import UUID

SAMPLE_COMMUNITY_ID = UUID("01936b8a-0000-7000-8000-000000000001")

SAMPLE_SNAPSHOT_DATA = {
    "rater_factors": [
        {"rater_id": "abc-123", "intercept": 0.5, "factor1": -0.2},
        {"rater_id": "def-456", "intercept": -0.1, "factor1": 0.3},
    ],
    "note_factors": [
        {"note_id": "note-1", "intercept": 0.7, "factor1": 0.1, "status": "CRH"},
    ],
    "global_intercept": 0.35,
    "rater_count": 2,
    "note_count": 1,
    "tier": "intermediate",
    "scorer_name": "MFCoreScorerAdapter",
}


class TestUploadScoringSnapshot:
    @patch("src.notes.scoring.gcs_storage.settings")
    def test_upload_with_empty_bucket_config_is_noop(self, mock_settings: MagicMock) -> None:
        from src.notes.scoring.gcs_storage import upload_scoring_snapshot

        mock_settings.SCORING_HISTORY_BUCKET = ""
        upload_scoring_snapshot(SAMPLE_COMMUNITY_ID, SAMPLE_SNAPSHOT_DATA)

    @patch("src.notes.scoring.gcs_storage.settings")
    @patch("src.notes.scoring.gcs_storage.storage")
    def test_upload_creates_correct_gcs_path(
        self, mock_storage: MagicMock, mock_settings: MagicMock
    ) -> None:
        from src.notes.scoring.gcs_storage import upload_scoring_snapshot

        mock_settings.SCORING_HISTORY_BUCKET = "opennotes-scoring-history"
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        upload_scoring_snapshot(SAMPLE_COMMUNITY_ID, SAMPLE_SNAPSHOT_DATA)

        mock_client.bucket.assert_called_once_with("opennotes-scoring-history")
        blob_path = mock_bucket.blob.call_args[0][0]
        assert blob_path.startswith(f"{SAMPLE_COMMUNITY_ID}/")
        assert blob_path.endswith(".json")

    @patch("src.notes.scoring.gcs_storage.settings")
    @patch("src.notes.scoring.gcs_storage.storage")
    def test_upload_serializes_snapshot_as_json(
        self, mock_storage: MagicMock, mock_settings: MagicMock
    ) -> None:
        from src.notes.scoring.gcs_storage import upload_scoring_snapshot

        mock_settings.SCORING_HISTORY_BUCKET = "test-bucket"
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        upload_scoring_snapshot(SAMPLE_COMMUNITY_ID, SAMPLE_SNAPSHOT_DATA)

        mock_blob.upload_from_string.assert_called_once()
        uploaded_data = mock_blob.upload_from_string.call_args[0][0]
        parsed = json.loads(uploaded_data)
        assert parsed["rater_count"] == 2
        assert parsed["note_count"] == 1
        assert parsed["global_intercept"] == 0.35
        content_type = mock_blob.upload_from_string.call_args[1].get("content_type")
        assert content_type == "application/json"

    @patch("src.notes.scoring.gcs_storage.settings")
    @patch("src.notes.scoring.gcs_storage.storage")
    def test_upload_error_logs_but_doesnt_raise(
        self, mock_storage: MagicMock, mock_settings: MagicMock
    ) -> None:
        from src.notes.scoring.gcs_storage import upload_scoring_snapshot

        mock_settings.SCORING_HISTORY_BUCKET = "test-bucket"
        mock_storage.Client.side_effect = Exception("GCS unavailable")

        upload_scoring_snapshot(SAMPLE_COMMUNITY_ID, SAMPLE_SNAPSHOT_DATA)


class TestListScoringSnapshots:
    @patch("src.notes.scoring.gcs_storage.settings")
    def test_list_returns_empty_when_no_bucket(self, mock_settings: MagicMock) -> None:
        from src.notes.scoring.gcs_storage import list_scoring_snapshots

        mock_settings.SCORING_HISTORY_BUCKET = ""
        result = list_scoring_snapshots(SAMPLE_COMMUNITY_ID)
        assert result == []

    @patch("src.notes.scoring.gcs_storage.settings")
    @patch("src.notes.scoring.gcs_storage.storage")
    def test_list_returns_snapshot_entries(
        self, mock_storage: MagicMock, mock_settings: MagicMock
    ) -> None:
        from src.notes.scoring.gcs_storage import list_scoring_snapshots

        mock_settings.SCORING_HISTORY_BUCKET = "test-bucket"
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket

        blob1 = MagicMock()
        blob1.name = f"{SAMPLE_COMMUNITY_ID}/2025-01-15T10:30:00Z.json"
        blob1.size = 1024
        blob2 = MagicMock()
        blob2.name = f"{SAMPLE_COMMUNITY_ID}/2025-01-16T14:00:00Z.json"
        blob2.size = 2048

        mock_bucket.list_blobs.return_value = [blob1, blob2]

        result = list_scoring_snapshots(SAMPLE_COMMUNITY_ID)

        assert len(result) == 2
        assert result[0]["timestamp"] == "2025-01-15T10:30:00Z"
        assert result[0]["size"] == 1024
        assert result[1]["timestamp"] == "2025-01-16T14:00:00Z"

    @patch("src.notes.scoring.gcs_storage.settings")
    @patch("src.notes.scoring.gcs_storage.storage")
    def test_list_error_returns_empty(
        self, mock_storage: MagicMock, mock_settings: MagicMock
    ) -> None:
        from src.notes.scoring.gcs_storage import list_scoring_snapshots

        mock_settings.SCORING_HISTORY_BUCKET = "test-bucket"
        mock_storage.Client.side_effect = Exception("GCS unavailable")

        result = list_scoring_snapshots(SAMPLE_COMMUNITY_ID)
        assert result == []


class TestFetchScoringSnapshot:
    @patch("src.notes.scoring.gcs_storage.settings")
    def test_fetch_returns_none_when_no_bucket(self, mock_settings: MagicMock) -> None:
        from src.notes.scoring.gcs_storage import fetch_scoring_snapshot

        mock_settings.SCORING_HISTORY_BUCKET = ""
        result = fetch_scoring_snapshot(SAMPLE_COMMUNITY_ID, "2025-01-15T10:30:00Z")
        assert result is None

    @patch("src.notes.scoring.gcs_storage.settings")
    @patch("src.notes.scoring.gcs_storage.storage")
    def test_fetch_returns_parsed_json(
        self, mock_storage: MagicMock, mock_settings: MagicMock
    ) -> None:
        from src.notes.scoring.gcs_storage import fetch_scoring_snapshot

        mock_settings.SCORING_HISTORY_BUCKET = "test-bucket"
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.download_as_text.return_value = json.dumps(SAMPLE_SNAPSHOT_DATA)

        result = fetch_scoring_snapshot(SAMPLE_COMMUNITY_ID, "2025-01-15T10:30:00Z")

        expected_path = f"{SAMPLE_COMMUNITY_ID}/2025-01-15T10:30:00Z.json"
        mock_bucket.blob.assert_called_once_with(expected_path)
        assert result is not None
        assert result["rater_count"] == 2
        assert result["global_intercept"] == 0.35

    @patch("src.notes.scoring.gcs_storage.settings")
    @patch("src.notes.scoring.gcs_storage.storage")
    def test_fetch_returns_none_on_not_found(
        self, mock_storage: MagicMock, mock_settings: MagicMock
    ) -> None:
        from src.notes.scoring.gcs_storage import fetch_scoring_snapshot

        mock_settings.SCORING_HISTORY_BUCKET = "test-bucket"
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.download_as_text.side_effect = Exception("404 Not Found")

        result = fetch_scoring_snapshot(SAMPLE_COMMUNITY_ID, "2025-01-15T10:30:00Z")
        assert result is None
