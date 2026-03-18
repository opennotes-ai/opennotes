from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.notes.copy_request_service import CopyRequestService
from src.notes.message_archive_models import MessageArchive
from src.notes.models import Request
from src.notes.request_service import RequestService


@pytest.fixture
async def source_community_server(db_session):
    server = CommunityServer(
        platform="discord",
        platform_community_server_id=f"test_source_{uuid4().hex[:8]}",
        name="Test Source Server",
        is_active=True,
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    return server


@pytest.fixture
async def target_community_server(db_session):
    server = CommunityServer(
        platform="playground",
        platform_community_server_id=f"test_target_{uuid4().hex[:8]}",
        name="Test Target Server",
        is_active=True,
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    return server


@pytest.fixture
async def source_requests_with_ids(source_community_server):
    async with get_session_maker()() as db:
        request_ids = []
        for i in range(5):
            request = await RequestService.create_from_message(
                db=db,
                request_id=f"src_req_{uuid4().hex[:8]}_{i}",
                content=f"Test content for request {i}",
                community_server_id=source_community_server.id,
                requested_by="test_user",
                platform_message_id=f"msg_{uuid4().hex[:8]}_{i}",
                platform_channel_id=f"chan_{i}",
                status="COMPLETED",
                dataset_name=f"dataset_{i}" if i % 2 == 0 else None,
                similarity_score=0.85 if i % 2 == 0 else None,
            )
            request_ids.append(request.id)

        last_req = await db.get(Request, request_ids[-1])
        last_req.soft_delete()
        await db.commit()

    return request_ids


class TestCopyRequestsE2E:
    async def test_copy_requests_duplicates_with_correct_fields(
        self,
        source_community_server,
        target_community_server,
        source_requests_with_ids,
    ):
        source_ids = source_requests_with_ids
        active_source_ids = set(source_ids[:4])

        async with get_session_maker()() as db:
            result = await CopyRequestService.copy_requests(
                db=db,
                source_community_server_id=source_community_server.id,
                target_community_server_id=target_community_server.id,
            )
            await db.commit()

        assert result.total_copied == 4
        assert result.total_skipped == 0
        assert result.total_failed == 0

        async with get_session_maker()() as db:
            copied_stmt = select(Request).where(
                Request.community_server_id == target_community_server.id,
            )
            copied_result = await db.execute(copied_stmt)
            copied_requests = copied_result.scalars().all()

            assert len(copied_requests) == 4

            seen_copied_from = set()
            for req in copied_requests:
                assert req.id not in active_source_ids
                assert req.community_server_id == target_community_server.id
                assert req.note_id is None
                assert req.status == "PENDING"

                assert req.request_metadata is not None
                assert "copied_from" in req.request_metadata
                copied_from_id = req.request_metadata["copied_from"]
                from uuid import UUID

                copied_from_uuid = UUID(copied_from_id)
                assert copied_from_uuid in active_source_ids
                seen_copied_from.add(copied_from_uuid)

                assert req.message_archive_id is not None
                assert req.message_archive is not None
                assert req.message_archive.content_text is not None
                assert req.message_archive.content_text.startswith("Test content for request")

            assert seen_copied_from == active_source_ids

    async def test_deleted_requests_not_copied(
        self,
        source_community_server,
        target_community_server,
        source_requests_with_ids,
    ):
        deleted_source_id = source_requests_with_ids[-1]

        async with get_session_maker()() as db:
            result = await CopyRequestService.copy_requests(
                db=db,
                source_community_server_id=source_community_server.id,
                target_community_server_id=target_community_server.id,
            )
            await db.commit()

        assert result.total_copied == 4

        async with get_session_maker()() as db:
            copied_stmt = select(Request).where(
                Request.community_server_id == target_community_server.id,
            )
            copied_result = await db.execute(copied_stmt)
            copied_requests = copied_result.scalars().all()

            copied_from_ids = {
                req.request_metadata["copied_from"]
                for req in copied_requests
                if req.request_metadata and "copied_from" in req.request_metadata
            }
            assert str(deleted_source_id) not in copied_from_ids

    async def test_source_data_unchanged_after_copy(
        self,
        source_community_server,
        target_community_server,
        source_requests_with_ids,
    ):
        async with get_session_maker()() as db:
            before_stmt = select(Request).where(
                Request.community_server_id == source_community_server.id,
            )
            before_result = await db.execute(before_stmt)
            before_requests = before_result.scalars().all()
            before_snapshot = {
                req.id: {
                    "request_id": req.request_id,
                    "status": req.status,
                    "community_server_id": req.community_server_id,
                    "message_archive_id": req.message_archive_id,
                    "deleted_at": req.deleted_at,
                    "dataset_name": req.dataset_name,
                    "similarity_score": req.similarity_score,
                }
                for req in before_requests
            }

        async with get_session_maker()() as db:
            await CopyRequestService.copy_requests(
                db=db,
                source_community_server_id=source_community_server.id,
                target_community_server_id=target_community_server.id,
            )
            await db.commit()

        async with get_session_maker()() as db:
            after_stmt = select(Request).where(
                Request.community_server_id == source_community_server.id,
            )
            after_result = await db.execute(after_stmt)
            after_requests = after_result.scalars().all()

            assert len(after_requests) == 5

            for req in after_requests:
                snap = before_snapshot[req.id]
                assert req.request_id == snap["request_id"]
                assert req.status == snap["status"]
                assert req.community_server_id == snap["community_server_id"]
                assert req.message_archive_id == snap["message_archive_id"]
                assert req.deleted_at == snap["deleted_at"]
                assert req.dataset_name == snap["dataset_name"]
                assert req.similarity_score == snap["similarity_score"]

    async def test_copied_message_archives_are_independent(
        self,
        source_community_server,
        target_community_server,
        source_requests_with_ids,
    ):
        async with get_session_maker()() as db:
            await CopyRequestService.copy_requests(
                db=db,
                source_community_server_id=source_community_server.id,
                target_community_server_id=target_community_server.id,
            )
            await db.commit()

        async with get_session_maker()() as db:
            source_stmt = select(Request).where(
                Request.community_server_id == source_community_server.id,
                Request.deleted_at.is_(None),
            )
            source_result = await db.execute(source_stmt)
            source_reqs = source_result.scalars().all()
            source_archive_ids = {req.message_archive_id for req in source_reqs}

            target_stmt = select(Request).where(
                Request.community_server_id == target_community_server.id,
            )
            target_result = await db.execute(target_stmt)
            target_reqs = target_result.scalars().all()
            target_archive_ids = {req.message_archive_id for req in target_reqs}

            assert len(target_archive_ids) == 4
            assert source_archive_ids.isdisjoint(target_archive_ids)

            total_archives = (
                await db.execute(select(func.count()).select_from(MessageArchive))
            ).scalar()
            assert total_archives == 9  # 5 source + 4 copied

    async def test_copy_preserves_dataset_metadata(
        self,
        source_community_server,
        target_community_server,
        source_requests_with_ids,
    ):
        async with get_session_maker()() as db:
            source_stmt = (
                select(Request)
                .where(
                    Request.community_server_id == source_community_server.id,
                    Request.deleted_at.is_(None),
                )
                .order_by(Request.created_at)
            )
            source_result = await db.execute(source_stmt)
            source_reqs = source_result.scalars().all()
            source_metadata = {
                str(req.id): {
                    "dataset_name": req.dataset_name,
                    "similarity_score": req.similarity_score,
                }
                for req in source_reqs
            }

        async with get_session_maker()() as db:
            await CopyRequestService.copy_requests(
                db=db,
                source_community_server_id=source_community_server.id,
                target_community_server_id=target_community_server.id,
            )
            await db.commit()

        async with get_session_maker()() as db:
            target_stmt = select(Request).where(
                Request.community_server_id == target_community_server.id,
            )
            target_result = await db.execute(target_stmt)
            target_reqs = target_result.scalars().all()

            for req in target_reqs:
                copied_from = req.request_metadata["copied_from"]
                src = source_metadata[copied_from]
                assert req.dataset_name == src["dataset_name"]
                assert req.similarity_score == src["similarity_score"]
