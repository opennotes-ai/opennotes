from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastuuid import uuid7


@dataclass
class FakeMessageArchive:
    platform_message_id: str | None
    platform_channel_id: str | None
    platform_author_id: str | None
    platform_timestamp: datetime | None

    def get_content(self) -> str:
        return "Test message content"


@dataclass
class FakeRequest:
    id: UUID
    community_server_id: UUID
    requested_by: str
    message_archive: FakeMessageArchive | None
    request_metadata: dict | None
    dataset_item_id: str | None
    similarity_score: float | None
    dataset_name: str | None
    deleted_at: datetime | None = None
    created_at: datetime | None = None


def _make_fake_request(
    community_server_id: UUID,
    *,
    message_archive: FakeMessageArchive | None = None,
    request_metadata: dict | None = None,
    dataset_item_id: str | None = None,
    similarity_score: float | None = None,
    dataset_name: str | None = None,
) -> FakeRequest:
    if message_archive is None:
        message_archive = FakeMessageArchive(
            platform_message_id="msg_123",
            platform_channel_id="chan_456",
            platform_author_id="author_789",
            platform_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
    return FakeRequest(
        id=uuid7(),
        community_server_id=community_server_id,
        requested_by="user_abc",
        message_archive=message_archive,
        request_metadata=request_metadata,
        dataset_item_id=dataset_item_id,
        similarity_score=similarity_score,
        dataset_name=dataset_name,
    )


@pytest.fixture
def source_community_server_id() -> UUID:
    return uuid7()


@pytest.fixture
def target_community_server_id() -> UUID:
    return uuid7()


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


def _setup_db_to_return(mock_db: AsyncMock, requests: list[FakeRequest]) -> None:
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = requests
    result_mock.scalars.return_value = scalars_mock
    mock_db.execute.return_value = result_mock


@pytest.mark.asyncio
async def test_copy_requests_copies_all_with_correct_fields(
    mock_db: AsyncMock,
    source_community_server_id: UUID,
    target_community_server_id: UUID,
) -> None:
    source_requests = [
        _make_fake_request(
            source_community_server_id,
            request_metadata={"key": "value"},
            dataset_item_id="ds_item_1",
            similarity_score=0.95,
            dataset_name="snopes",
        ),
        _make_fake_request(
            source_community_server_id,
            request_metadata=None,
        ),
    ]
    _setup_db_to_return(mock_db, source_requests)

    with patch(
        "src.notes.copy_request_service.RequestService.create_from_message",
        new_callable=AsyncMock,
    ) as mock_create:
        from src.notes.copy_request_service import CopyRequestService

        result = await CopyRequestService.copy_requests(
            db=mock_db,
            source_community_server_id=source_community_server_id,
            target_community_server_id=target_community_server_id,
        )

    assert result.total_copied == 2
    assert result.total_skipped == 0
    assert result.total_failed == 0
    assert mock_create.call_count == 2

    first_call = mock_create.call_args_list[0]
    assert first_call.kwargs["community_server_id"] == target_community_server_id
    assert first_call.kwargs["note_id"] is None
    assert first_call.kwargs["content"] == "Test message content"
    assert first_call.kwargs["requested_by"] == "user_abc"
    assert first_call.kwargs["dataset_item_id"] == "ds_item_1"
    assert first_call.kwargs["similarity_score"] == 0.95
    assert first_call.kwargs["dataset_name"] == "snopes"
    assert first_call.kwargs["status"] == "PENDING"

    metadata = first_call.kwargs["request_metadata"]
    assert metadata["key"] == "value"
    assert metadata["copied_from"] == str(source_requests[0].id)

    second_call = mock_create.call_args_list[1]
    second_metadata = second_call.kwargs["request_metadata"]
    assert second_metadata["copied_from"] == str(source_requests[1].id)

    first_req_id = first_call.kwargs["request_id"]
    second_req_id = second_call.kwargs["request_id"]
    assert first_req_id != second_req_id
    assert first_req_id != str(source_requests[0].id)
    assert second_req_id != str(source_requests[1].id)


@pytest.mark.asyncio
async def test_copy_requests_skips_missing_message_archive(
    mock_db: AsyncMock,
    source_community_server_id: UUID,
    target_community_server_id: UUID,
) -> None:
    source_requests = [
        _make_fake_request(source_community_server_id, message_archive=None),
        _make_fake_request(source_community_server_id),
    ]
    source_requests[0].message_archive = None

    _setup_db_to_return(mock_db, source_requests)

    with patch(
        "src.notes.copy_request_service.RequestService.create_from_message",
        new_callable=AsyncMock,
    ) as mock_create:
        from src.notes.copy_request_service import CopyRequestService

        result = await CopyRequestService.copy_requests(
            db=mock_db,
            source_community_server_id=source_community_server_id,
            target_community_server_id=target_community_server_id,
        )

    assert result.total_copied == 1
    assert result.total_skipped == 1
    assert result.total_failed == 0
    assert mock_create.call_count == 1


@pytest.mark.asyncio
async def test_copy_requests_counts_failures(
    mock_db: AsyncMock,
    source_community_server_id: UUID,
    target_community_server_id: UUID,
) -> None:
    source_requests = [
        _make_fake_request(source_community_server_id),
        _make_fake_request(source_community_server_id),
    ]
    _setup_db_to_return(mock_db, source_requests)

    with patch(
        "src.notes.copy_request_service.RequestService.create_from_message",
        new_callable=AsyncMock,
        side_effect=[Exception("DB error"), AsyncMock()],
    ):
        from src.notes.copy_request_service import CopyRequestService

        result = await CopyRequestService.copy_requests(
            db=mock_db,
            source_community_server_id=source_community_server_id,
            target_community_server_id=target_community_server_id,
        )

    assert result.total_copied == 1
    assert result.total_skipped == 0
    assert result.total_failed == 1


@pytest.mark.asyncio
async def test_copy_requests_calls_on_progress(
    mock_db: AsyncMock,
    source_community_server_id: UUID,
    target_community_server_id: UUID,
) -> None:
    source_requests = [
        _make_fake_request(source_community_server_id),
        _make_fake_request(source_community_server_id),
        _make_fake_request(source_community_server_id, message_archive=None),
    ]
    source_requests[2].message_archive = None

    _setup_db_to_return(mock_db, source_requests)

    progress_calls: list[tuple[int, int]] = []

    def track_progress(current: int, total: int) -> None:
        progress_calls.append((current, total))

    with patch(
        "src.notes.copy_request_service.RequestService.create_from_message",
        new_callable=AsyncMock,
    ):
        from src.notes.copy_request_service import CopyRequestService

        result = await CopyRequestService.copy_requests(
            db=mock_db,
            source_community_server_id=source_community_server_id,
            target_community_server_id=target_community_server_id,
            on_progress=track_progress,
        )

    assert result.total_copied == 2
    assert result.total_skipped == 1
    assert len(progress_calls) == 3
    assert progress_calls == [(1, 3), (2, 3), (3, 3)]


@pytest.mark.asyncio
async def test_copy_requests_empty_source(
    mock_db: AsyncMock,
    source_community_server_id: UUID,
    target_community_server_id: UUID,
) -> None:
    _setup_db_to_return(mock_db, [])

    with patch(
        "src.notes.copy_request_service.RequestService.create_from_message",
        new_callable=AsyncMock,
    ) as mock_create:
        from src.notes.copy_request_service import CopyRequestService

        result = await CopyRequestService.copy_requests(
            db=mock_db,
            source_community_server_id=source_community_server_id,
            target_community_server_id=target_community_server_id,
        )

    assert result.total_copied == 0
    assert result.total_skipped == 0
    assert result.total_failed == 0
    assert mock_create.call_count == 0
