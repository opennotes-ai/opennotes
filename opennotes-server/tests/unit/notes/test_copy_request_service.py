from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastuuid import uuid7

from src.notes.copy_request_service import CopyRequestService


@pytest.fixture(autouse=True)
def _ensure_mappers():
    from sqlalchemy.orm import configure_mappers

    import src.notes.note_publisher_models
    import src.users.profile_models  # noqa: F401

    configure_mappers()


@dataclass
class FakeRequest:
    id: UUID
    community_server_id: UUID
    requested_by: str
    message_archive_id: UUID | None
    request_metadata: dict | None
    dataset_item_id: str | None
    similarity_score: float | None
    dataset_name: str | None
    deleted_at: datetime | None = None
    created_at: datetime | None = None


def _make_fake_request(
    community_server_id: UUID,
    *,
    request_metadata: dict | None = None,
    dataset_item_id: str | None = None,
    similarity_score: float | None = None,
    dataset_name: str | None = None,
    with_archive: bool = True,
) -> FakeRequest:
    return FakeRequest(
        id=uuid7(),
        community_server_id=community_server_id,
        requested_by="user_abc",
        message_archive_id=uuid7() if with_archive else None,
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
    db = AsyncMock()
    db.add = MagicMock()
    return db


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

    result = await CopyRequestService.copy_requests(
        db=mock_db,
        source_community_server_id=source_community_server_id,
        target_community_server_id=target_community_server_id,
    )

    assert result.total_copied == 2
    assert result.total_skipped == 0
    assert result.total_failed == 0
    assert mock_db.add.call_count == 2

    first_req = mock_db.add.call_args_list[0][0][0]
    assert first_req.community_server_id == target_community_server_id
    assert first_req.message_archive_id == source_requests[0].message_archive_id
    assert first_req.note_id is None
    assert first_req.status == "PENDING"
    assert first_req.requested_by == "user_abc"
    assert first_req.dataset_item_id == "ds_item_1"
    assert first_req.similarity_score == 0.95
    assert first_req.dataset_name == "snopes"

    metadata = first_req.request_metadata
    assert metadata["key"] == "value"
    assert metadata["copied_from"] == str(source_requests[0].id)

    second_req = mock_db.add.call_args_list[1][0][0]
    assert second_req.request_metadata["copied_from"] == str(source_requests[1].id)
    assert second_req.message_archive_id == source_requests[1].message_archive_id

    assert first_req.request_id != second_req.request_id
    assert first_req.request_id != str(source_requests[0].id)


@pytest.mark.asyncio
async def test_copy_requests_copies_with_null_archive(
    mock_db: AsyncMock,
    source_community_server_id: UUID,
    target_community_server_id: UUID,
) -> None:
    source_requests = [
        _make_fake_request(source_community_server_id, with_archive=False),
        _make_fake_request(source_community_server_id),
    ]
    _setup_db_to_return(mock_db, source_requests)

    result = await CopyRequestService.copy_requests(
        db=mock_db,
        source_community_server_id=source_community_server_id,
        target_community_server_id=target_community_server_id,
    )

    assert result.total_copied == 2
    assert result.total_skipped == 0
    assert result.total_failed == 0
    assert mock_db.add.call_count == 2

    first_req = mock_db.add.call_args_list[0][0][0]
    assert first_req.message_archive_id is None

    second_req = mock_db.add.call_args_list[1][0][0]
    assert second_req.message_archive_id == source_requests[1].message_archive_id


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
    mock_db.add = MagicMock(side_effect=[Exception("DB error"), None])

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
        _make_fake_request(source_community_server_id, with_archive=False),
    ]
    _setup_db_to_return(mock_db, source_requests)

    progress_calls: list[tuple[int, int]] = []

    def track_progress(current: int, total: int) -> None:
        progress_calls.append((current, total))

    result = await CopyRequestService.copy_requests(
        db=mock_db,
        source_community_server_id=source_community_server_id,
        target_community_server_id=target_community_server_id,
        on_progress=track_progress,
    )

    assert result.total_copied == 3
    assert result.total_skipped == 0
    assert len(progress_calls) == 3
    assert progress_calls == [(1, 3), (2, 3), (3, 3)]


@pytest.mark.asyncio
async def test_copy_requests_empty_source(
    mock_db: AsyncMock,
    source_community_server_id: UUID,
    target_community_server_id: UUID,
) -> None:
    _setup_db_to_return(mock_db, [])

    result = await CopyRequestService.copy_requests(
        db=mock_db,
        source_community_server_id=source_community_server_id,
        target_community_server_id=target_community_server_id,
    )

    assert result.total_copied == 0
    assert result.total_skipped == 0
    assert result.total_failed == 0
    assert mock_db.add.call_count == 0
